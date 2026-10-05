"""Twelve Data market-data adapter."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from logs.logger import get_logger

from slaifi.core.types import CurrencyCode
from slaifi.core.utils.errors import InfrastructureError
from slaifi.domain.assets import AssetId
from slaifi.domain.market.models import OHLCVBar, PriceQuote

logger = get_logger("SLAIFI Twelve Data")


class TwelveDataMarketDataProvider:
    """Translate Twelve Data responses into provider-neutral SLAIFI objects."""

    data_mode = "live"

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 10.0,
        quote_cache_ttl_seconds: float = 5.0,
        history_cache_ttl_seconds: float = 60.0,
    ) -> None:
        normalized_key = api_key.strip()
        if not normalized_key:
            raise ValueError("Twelve Data API key must not be blank")

        self._api_key = normalized_key
        self._quote_cache_ttl_seconds = max(0.0, quote_cache_ttl_seconds)
        self._history_cache_ttl_seconds = max(0.0, history_cache_ttl_seconds)
        self._quote_cache: dict[AssetId, tuple[float, PriceQuote]] = {}
        self._history_cache: dict[
            tuple[AssetId, datetime, datetime, str], tuple[float, tuple[OHLCVBar, ...]]
        ] = {}
        self._client = httpx.AsyncClient(
            base_url="https://api.twelvedata.com",
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": "SLAIFI/0.3"},
        )

    async def close(self) -> None:
        self._quote_cache.clear()
        self._history_cache.clear()
        await self._client.aclose()

    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        if not assets:
            return ()

        now = time.monotonic()
        results: list[PriceQuote | None] = [None] * len(assets)
        missing: list[tuple[int, AssetId]] = []

        for index, asset in enumerate(assets):
            cached = self._quote_cache.get(asset)
            if cached is not None and now - cached[0] <= self._quote_cache_ttl_seconds:
                results[index] = cached[1]
            else:
                missing.append((index, asset))

        if missing:
            fetched = await asyncio.gather(*(self._get_quote(asset) for _, asset in missing))
            stored_at = time.monotonic()
            for (index, asset), quote in zip(missing, fetched, strict=True):
                results[index] = quote
                if self._quote_cache_ttl_seconds > 0:
                    self._quote_cache[asset] = (stored_at, quote)

        logger.debug(
            "Quote batch completed | requested=%d | cache_hits=%d | fetched=%d",
            len(assets),
            len(assets) - len(missing),
            len(missing),
        )
        return tuple(quote for quote in results if quote is not None)

    async def get_bars(
        self,
        asset: AssetId,
        *,
        start_at: datetime,
        end_at: datetime,
        interval: str = "1day",
    ) -> Sequence[OHLCVBar]:
        if start_at.tzinfo is None or start_at.utcoffset() is None:
            raise ValueError("start_at must be timezone-aware")
        if end_at.tzinfo is None or end_at.utcoffset() is None:
            raise ValueError("end_at must be timezone-aware")
        if end_at <= start_at:
            raise ValueError("end_at must be later than start_at")

        normalized_start = start_at.astimezone(UTC)
        normalized_end = end_at.astimezone(UTC)
        cache_key = (asset, normalized_start, normalized_end, interval)
        cached = self._history_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and now - cached[0] <= self._history_cache_ttl_seconds:
            logger.debug("History cache hit | symbol=%s | interval=%s", asset.symbol, interval)
            return cached[1]

        payload = await self._request_json(
            "/time_series",
            operation="history",
            params={
                "symbol": asset.symbol,
                "interval": interval,
                "start_date": normalized_start.strftime("%Y-%m-%d"),
                "end_date": normalized_end.strftime("%Y-%m-%d"),
                "order": "ASC",
                "timezone": "UTC",
                "apikey": self._api_key,
            },
        )
        raw_values = payload.get("values")
        if not isinstance(raw_values, list):
            return ()

        bars: list[OHLCVBar] = []
        for item in raw_values:
            if not isinstance(item, Mapping):
                continue
            try:
                opened_at = self._parse_datetime(item.get("datetime"))
                open_price = self._decimal(item.get("open"))
                high_price = self._decimal(item.get("high"))
                low_price = self._decimal(item.get("low"))
                close_price = self._decimal(item.get("close"))
                volume = self._decimal(item.get("volume"), default=Decimal("0"))
            except (TypeError, ValueError, InvalidOperation):
                continue

            bars.append(
                OHLCVBar(
                    asset=asset,
                    start_at=opened_at,
                    end_at=opened_at + timedelta(days=1),
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                )
            )

        normalized_bars = tuple(sorted(bars, key=lambda bar: bar.start_at))
        if normalized_bars and self._history_cache_ttl_seconds > 0:
            self._history_cache[cache_key] = (time.monotonic(), normalized_bars)
        return normalized_bars

    async def _get_quote(self, asset: AssetId) -> PriceQuote:
        payload = await self._request_json(
            "/quote",
            operation="quote",
            params={"symbol": asset.symbol, "apikey": self._api_key},
        )
        try:
            price = self._decimal(payload.get("close"))
            percent_change_raw = payload.get("percent_change")
            change_rate = (
                float(self._decimal(percent_change_raw) / Decimal("100"))
                if percent_change_raw not in (None, "")
                else None
            )

            currency_raw = payload.get("currency")
            if not currency_raw and asset.currency is not None:
                currency_raw = str(asset.currency)
            if not currency_raw:
                currency_raw = "USD"

            timestamp_raw = payload.get("last_quote_at") or payload.get("timestamp")
            observed_at = (
                datetime.fromtimestamp(int(timestamp_raw), tz=UTC)
                if timestamp_raw is not None
                else datetime.now(UTC)
            )
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise InfrastructureError(
                "Market provider returned an invalid quote payload",
                component="market_data",
                operation="quote",
                cause=exc,
                context={"symbol": asset.symbol},
                retryable=False,
            ) from exc

        return PriceQuote(
            asset=asset,
            price=price,
            currency=CurrencyCode(str(currency_raw).upper()),
            observed_at=observed_at,
            source="twelvedata",
            change_rate=change_rate,
        )

    async def _request_json(
        self,
        path: str,
        *,
        operation: str,
        params: Mapping[str, str],
    ) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            response = await self._client.get(path, params=dict(params))
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(
                "Market provider request failed | operation=%s | error_type=%s",
                operation,
                type(exc).__name__,
            )
            raise InfrastructureError(
                "Market data provider is unavailable",
                component="market_data",
                operation=operation,
                cause=exc,
                retryable=True,
            ) from exc
        finally:
            logger.debug(
                "Market provider request completed | operation=%s | duration_ms=%.2f",
                operation,
                max((time.perf_counter() - started) * 1000.0, 0.0),
            )

        if not isinstance(payload, dict):
            raise InfrastructureError(
                "Market provider returned an invalid response object",
                component="market_data",
                operation=operation,
                retryable=False,
            )
        if payload.get("status") == "error":
            provider_code = payload.get("code")
            raise InfrastructureError(
                "Market data provider rejected the request",
                component="market_data",
                operation=operation,
                context={"provider_code": provider_code} if provider_code is not None else None,
                retryable=provider_code in {429, 500, 502, 503, 504},
            )
        return payload

    @staticmethod
    def _decimal(value: object, *, default: Decimal | None = None) -> Decimal:
        if value in (None, ""):
            if default is not None:
                return default
            raise ValueError("missing decimal value")
        result = Decimal(str(value))
        if not result.is_finite():
            raise ValueError("market value must be finite")
        return result

    @staticmethod
    def _parse_datetime(value: object) -> datetime:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("missing market timestamp")
        parsed = datetime.fromisoformat(value.strip())
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
