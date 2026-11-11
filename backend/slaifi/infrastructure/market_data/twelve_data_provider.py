"""Twelve Data market-data adapter."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from slaifi.core.types import CurrencyCode
from slaifi.core.utils.errors import (
    MarketDataRateLimitedError,
    MarketDataUnavailableError,
    SymbolNotFoundError,
    ValidationError,
)
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market.models import InstrumentInfo, OHLCVBar, PriceQuote

SUPPORTED_INTERVALS: dict[str, timedelta] = {
    "1min": timedelta(minutes=1),
    "5min": timedelta(minutes=5),
    "15min": timedelta(minutes=15),
    "30min": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1day": timedelta(days=1),
    "1week": timedelta(days=7),
    "1month": timedelta(days=31),
}
_MAX_OUTPUT = 5000
_TYPE_TO_CLASS = {
    "common stock": AssetClass.EQUITY,
    "equity": AssetClass.EQUITY,
    "etf": AssetClass.ETF,
    "index": AssetClass.INDEX,
    "digital currency": AssetClass.CRYPTO,
    "physical currency": AssetClass.FOREX,
    "bond": AssetClass.BOND,
    "commodity": AssetClass.COMMODITY,
}


class TwelveDataMarketDataProvider:
    """Translate Twelve Data responses into provider-neutral SLAIFI objects."""

    data_mode = "live"
    source_name = "twelvedata"
    supported_intervals: tuple[str, ...] = tuple(SUPPORTED_INTERVALS)

    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 10.0,
        quote_cache_ttl_seconds: float = 5.0,
        history_cache_ttl_seconds: float = 60.0,
        data_delay_minutes: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
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
        self._data_delay_minutes = data_delay_minutes
        self._client = httpx.AsyncClient(
            base_url="https://api.twelvedata.com",
            timeout=httpx.Timeout(timeout_seconds),
            headers={"Accept": "application/json", "User-Agent": "SLAIFI/0.3"},
            transport=transport,
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
        step = SUPPORTED_INTERVALS.get(interval)
        if step is None:
            raise ValidationError(
                f"unsupported interval {interval!r}; choose one of {sorted(SUPPORTED_INTERVALS)}"
            )

        normalized_start = start_at.astimezone(UTC)
        normalized_end = end_at.astimezone(UTC)
        cache_key = (asset, normalized_start, normalized_end, interval)
        cached = self._history_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and now - cached[0] <= self._history_cache_ttl_seconds:
            return cached[1]

        intraday = step < timedelta(days=1)
        date_format = "%Y-%m-%d %H:%M:%S" if intraday else "%Y-%m-%d"
        params: dict[str, str | int] = {
            "symbol": asset.symbol,
            "interval": interval,
            "start_date": normalized_start.strftime(date_format),
            "end_date": normalized_end.strftime(date_format),
            "order": "ASC",
            "timezone": "UTC",
            "outputsize": _MAX_OUTPUT,
            "apikey": self._api_key,
        }
        if asset.exchange:
            params["exchange"] = asset.exchange
        payload = await self._request("/time_series", params, symbol=asset.symbol)
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
                    end_at=opened_at + step,
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
        params: dict[str, str] = {"symbol": asset.symbol, "apikey": self._api_key}
        if asset.exchange:
            params["exchange"] = asset.exchange
        payload = await self._request("/quote", params, symbol=asset.symbol)
        try:
            price = self._decimal(payload.get("close"))
        except (ValueError, InvalidOperation) as exc:
            raise MarketDataUnavailableError(
                f"the provider returned no usable price for {asset.symbol}", component="twelvedata"
            ) from exc

        percent_change_raw = payload.get("percent_change")
        change_rate: float | None = None
        if percent_change_raw not in (None, ""):
            change_rate = float(self._decimal(percent_change_raw) / Decimal("100"))

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

        market_open_raw = payload.get("is_market_open")
        previous_close: Decimal | None = None
        try:
            previous_close = self._decimal(payload.get("previous_close"))
        except (ValueError, InvalidOperation):
            previous_close = None
        delay = self._data_delay_minutes
        return PriceQuote(
            asset=asset,
            price=price,
            currency=CurrencyCode(str(currency_raw).upper()),
            observed_at=observed_at,
            source="twelvedata",
            change_rate=change_rate,
            is_market_open=market_open_raw if isinstance(market_open_raw, bool) else None,
            delayed=None if delay is None else delay > 0,
            previous_close=previous_close,
            illustrative=False,
        )

    async def search_instruments(self, query: str, *, limit: int = 10) -> Sequence[InstrumentInfo]:
        term = query.strip()
        if not term:
            return ()
        payload = await self._request(
            "/symbol_search",
            {"symbol": term, "outputsize": max(1, min(limit, 30)), "apikey": self._api_key},
            symbol=term,
            not_found_ok=True,
        )
        data = payload.get("data")
        results: list[InstrumentInfo] = []
        if not isinstance(data, list):
            return ()
        for item in data:
            if not isinstance(item, Mapping) or not item.get("symbol"):
                continue
            instrument_type = str(item.get("instrument_type") or "")
            currency = item.get("currency")
            try:
                asset = AssetId(
                    symbol=str(item["symbol"]),
                    asset_class=_TYPE_TO_CLASS.get(instrument_type.lower(), AssetClass.UNKNOWN),
                    exchange=str(item["exchange"]) if item.get("exchange") else None,
                    currency=CurrencyCode(str(currency).upper()) if currency else None,
                )
                results.append(
                    InstrumentInfo(
                        asset=asset,
                        name=str(item.get("instrument_name") or item["symbol"]),
                        country=str(item["country"]) if item.get("country") else None,
                        instrument_type=instrument_type or None,
                        illustrative=False,
                    )
                )
            except ValueError:
                continue
        return tuple(results[:limit])

    async def _request(
        self,
        path: str,
        params: Mapping[str, str | int],
        *,
        symbol: str,
        not_found_ok: bool = False,
    ) -> dict[str, Any]:
        """GET with every failure mapped to a SLAIFI market-data error (never leaking the key)."""

        try:
            response = await self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise MarketDataUnavailableError(
                "the market-data provider timed out", component="twelvedata", operation=path
            ) from exc
        except httpx.HTTPError as exc:
            raise MarketDataUnavailableError(
                "the market-data provider could not be reached",
                component="twelvedata",
                operation=path,
            ) from exc
        if response.status_code == 429:
            retry = response.headers.get("Retry-After")
            raise MarketDataRateLimitedError(
                "the market-data provider rate limit was reached",
                retry_after_seconds=float(retry)
                if retry and retry.replace(".", "", 1).isdigit()
                else None,
                component="twelvedata",
                operation=path,
            )
        if response.status_code in (401, 403):
            raise MarketDataUnavailableError(
                "the market-data provider rejected the configured credentials",
                component="twelvedata",
                operation=path,
                retryable=False,
            )
        if response.status_code >= 500:
            raise MarketDataUnavailableError(
                f"the market-data provider failed (HTTP {response.status_code})",
                component="twelvedata",
                operation=path,
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise MarketDataUnavailableError(
                "the market-data provider returned an unreadable response",
                component="twelvedata",
                operation=path,
            ) from exc
        if not isinstance(payload, dict):
            raise MarketDataUnavailableError(
                "the market-data provider returned an invalid response object",
                component="twelvedata",
                operation=path,
            )
        if payload.get("status") == "error":
            code = payload.get("code")
            message = str(payload.get("message") or "market provider error")
            lowered = message.lower()
            if code == 429 or "api credits" in lowered or "rate limit" in lowered:
                raise MarketDataRateLimitedError(message, component="twelvedata", operation=path)
            if code in (401, 403) or "apikey" in lowered or "api key" in lowered:
                raise MarketDataUnavailableError(
                    "the market-data provider rejected the configured credentials",
                    component="twelvedata",
                    operation=path,
                    retryable=False,
                )
            if code in (400, 404) and not not_found_ok:
                raise SymbolNotFoundError(
                    f"{symbol}: {message}", component="twelvedata", operation=path
                )
            raise MarketDataUnavailableError(message, component="twelvedata", operation=path)
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
