"""Shared plumbing for the HTTP market-data adapters.

* one place that maps transport and HTTP failures to SLAIFI market-data errors,
* a self-imposed request budget so a free key is not burned through,
* helpers that parse numbers and times strictly (a bad value is dropped, never guessed).

API keys are never placed in error messages, and the HTTP client libraries' request logging
(which would print a query-string key) is silenced.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from slaifi.core.utils.errors import (
    MarketDataNotEntitledError,
    MarketDataRateLimitedError,
    MarketDataUnavailableError,
    SymbolNotFoundError,
)
from slaifi.domain.assets import AssetId
from slaifi.domain.market import InstrumentInfo, OHLCVBar, PriceQuote, ProviderPolicy

# httpx logs every request URL at INFO; several providers only accept the key in the query string.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)

DAY = 86_400.0


class RequestBudget:
    """Sliding-window limiter for calls we are willing to make (not a promise from the provider)."""

    def __init__(self, policy: ProviderPolicy, clock: Callable[[], float] = time.monotonic) -> None:
        self._policy = policy
        self._clock = clock
        self._calls: deque[float] = deque()

    def _trim(self, now: float) -> None:
        while self._calls and now - self._calls[0] > DAY:
            self._calls.popleft()

    def _within(self, now: float, seconds: float) -> int:
        return sum(1 for t in self._calls if now - t <= seconds)

    def counts(self) -> tuple[int, int]:
        now = self._clock()
        self._trim(now)
        return self._within(now, 60.0), len(self._calls)

    def acquire(self, *, source: str) -> None:
        """Reserve one call or raise ``MarketDataRateLimitedError`` without contacting the provider."""

        now = self._clock()
        self._trim(now)
        p = self._policy
        for limit, window, label in (
            (p.per_minute, 60.0, "per-minute"),
            (p.per_hour, 3600.0, "hourly"),
            (p.per_day, DAY, "daily"),
        ):
            if limit is None:
                continue
            inside = [t for t in self._calls if now - t <= window]
            if len(inside) >= limit:
                wait = max(1.0, window - (now - inside[0]))
                raise MarketDataRateLimitedError(
                    f"{source}: the {label} request budget ({limit}) is used up; "
                    f"next call possible in about {int(wait)} s",
                    retry_after_seconds=wait,
                    component=source,
                )
        self._calls.append(now)


class HttpMarketProvider:
    """Base for adapters. Subclasses define ``_inspect`` to turn in-body errors into exceptions."""

    name = "provider"
    label = "Provider"
    capabilities: tuple[str, ...] = ()
    supported_intervals: tuple[str, ...] = ()
    data_mode = "live"
    quotes_delayed: bool | None = None  # what the provider documents for its free plan
    default_policy = ProviderPolicy()
    default_base_url = ""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        timeout_seconds: float = 10.0,
        policy: ProviderPolicy | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        key = api_key.strip()
        if not key:
            raise ValueError(f"{self.label} API key must not be blank")
        self._api_key = key
        self.policy = policy or self.default_policy
        self.budget = RequestBudget(self.policy, clock)
        self._client = httpx.AsyncClient(
            base_url=base_url or self.default_base_url,
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Accept": "application/json",
                "User-Agent": "SLAIFI/0.4",
                **self._auth_headers(),
            },
            transport=transport,
        )

    # -- subclass hooks -------------------------------------------------------------
    def _auth_headers(self) -> dict[str, str]:
        return {}

    def _auth_params(self) -> dict[str, str]:
        return {}

    def _inspect(self, payload: Any, *, path: str, symbol: str) -> None:
        """Raise a market-data error if a 200 response body actually reports a failure."""

    # -- shared ------------------------------------------------------------------------
    async def close(self) -> None:
        await self._client.aclose()

    # -- capability surface (adapters override what they offer) -----------------------------
    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        raise NotImplementedError(f"{self.label} does not provide quotes")

    async def get_bars(
        self, asset: AssetId, *, start_at: datetime, end_at: datetime, interval: str = "1day"
    ) -> Sequence[OHLCVBar]:
        return ()  # a provider without history offers nothing; the gateway never asks it

    async def search_instruments(self, query: str, *, limit: int = 10) -> Sequence[InstrumentInfo]:
        raise NotImplementedError(f"{self.label} does not provide search")

    async def _get(
        self,
        path: str,
        params: Mapping[str, str | int] | None = None,
        *,
        symbol: str,
        not_found_ok: bool = False,
    ) -> Any:
        self.budget.acquire(source=self.name)
        query: dict[str, str | int] = {**(params or {}), **self._auth_params()}
        try:
            response = await self._client.get(path, params=query)
        except httpx.TimeoutException as exc:
            raise MarketDataUnavailableError(
                f"{self.label} timed out", component=self.name, operation=path
            ) from exc
        except httpx.HTTPError as exc:
            raise MarketDataUnavailableError(
                f"{self.label} could not be reached ({type(exc).__name__})",
                component=self.name,
                operation=path,
            ) from exc
        status = response.status_code
        if status == 429:
            retry = response.headers.get("Retry-After", "")
            raise MarketDataRateLimitedError(
                f"{self.label} rate limit reached",
                retry_after_seconds=float(retry) if retry.replace(".", "", 1).isdigit() else None,
                component=self.name,
                operation=path,
            )
        if status == 401:
            raise MarketDataUnavailableError(
                f"{self.label} rejected the configured API key",
                component=self.name,
                operation=path,
                retryable=False,
            )
        if status in (402, 403):
            raise MarketDataNotEntitledError(
                f"{self.label}: the free plan does not include this data (HTTP {status})",
                component=self.name,
                operation=path,
            )
        if status == 404:
            if not_found_ok:
                return None
            raise SymbolNotFoundError(
                f"{symbol} was not found at {self.label}", component=self.name, operation=path
            )
        if status >= 500:
            raise MarketDataUnavailableError(
                f"{self.label} failed (HTTP {status})", component=self.name, operation=path
            )
        if status >= 400:
            raise MarketDataUnavailableError(
                f"{self.label} refused the request (HTTP {status})",
                component=self.name,
                operation=path,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise MarketDataUnavailableError(
                f"{self.label} returned an unreadable response", component=self.name, operation=path
            ) from exc
        self._inspect(payload, path=path, symbol=symbol)
        return payload

    # -- strict parsing ------------------------------------------------------------------
    @staticmethod
    def decimal(value: object, *, default: Decimal | None = None) -> Decimal:
        if value is None or (isinstance(value, str) and not value.strip()):
            if default is not None:
                return default
            raise ValueError("missing number")
        try:
            result = Decimal(str(value).strip().rstrip("%"))
        except InvalidOperation as exc:
            raise ValueError("not a number") from exc
        if not result.is_finite():
            raise ValueError("number must be finite")
        return result

    @staticmethod
    def utc_from_epoch(value: object) -> datetime:
        number = float(str(value))
        if number <= 0:
            raise ValueError("timestamp must be positive")
        if number > 1e12:  # milliseconds
            number /= 1000.0
        return datetime.fromtimestamp(number, tz=UTC)

    @staticmethod
    def utc_from_text(value: object) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("missing timestamp")
        text = value.strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def percent_to_rate(value: object) -> float | None:
        """Convert a percentage such as ``"-1.25%"`` or ``-1.25`` into a fraction (``-0.0125``)."""

        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            return float(Decimal(str(value).strip().rstrip("%")) / Decimal(100))
        except (InvalidOperation, ValueError):
            return None
