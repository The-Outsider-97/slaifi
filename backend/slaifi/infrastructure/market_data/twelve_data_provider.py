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
from slaifi.domain.assets import AssetId
from slaifi.domain.market.models import OHLCVBar, PriceQuote

_INTERVAL_DELTAS: dict[str, timedelta] = {
    "1min": timedelta(minutes=1),
    "5min": timedelta(minutes=5),
    "15min": timedelta(minutes=15),
    "30min": timedelta(minutes=30),
    "45min": timedelta(minutes=45),
    "1h": timedelta(hours=1),
    "2h": timedelta(hours=2),
    "4h": timedelta(hours=4),
    "8h": timedelta(hours=8),
    "1day": timedelta(days=1),
    "1week": timedelta(weeks=1),
}


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
        resolved: dict[AssetId, PriceQuote] = {}
        missing: list[AssetId] = []
        seen_missing: set[AssetId] = set()

        for asset in assets:
            cached = self._quote_cache.get(asset)
            if cached is not None and now - cached[0] <= self._quote_cache_ttl_seconds:
                resolved[asset] = cached[1]
            elif asset not in seen_missing:
                seen_missing.add(asset)
                missing.append(asset)

        if missing:
            fetched = await asyncio.gather(*(self._get_quote(asset) for asset in missing))
            stored_at = time.monotonic()
            for asset, quote in zip(missing, fetched, strict=True):
                resolved[asset] = quote
                if self._quote_cache_ttl_seconds > 0:
                    self._quote_cache[asset] = (stored_at, quote)

        return tuple(resolved[asset] for asset in assets if asset in resolved)

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
        interval_delta = self._interval_delta(interval)

        normalized_start = start_at.astimezone(UTC)
        normalized_end = end_at.astimezone(UTC)
        cache_key = (asset, normalized_start, normalized_end, interval)
        cached = self._history_cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and now - cached[0] <= self._history_cache_ttl_seconds:
            return cached[1]

        response = await self._client.get(
            "/time_series",
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
        payload = self._decode(response)
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
                    end_at=opened_at + interval_delta,
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
        response = await self._client.get(
            "/quote",
            params={"symbol": asset.symbol, "apikey": self._api_key},
        )
        payload = self._decode(response)
        price = self._decimal(payload.get("close"))

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

        return PriceQuote(
            asset=asset,
            price=price,
            currency=CurrencyCode(str(currency_raw).upper()),
            observed_at=observed_at,
            source="twelvedata",
            change_rate=change_rate,
        )

    @staticmethod
    def _interval_delta(interval: str) -> timedelta:
        try:
            return _INTERVAL_DELTAS[interval]
        except KeyError as exc:
            raise ValueError(
                f"unsupported market interval {interval!r}; supported intervals: "
                f"{', '.join(_INTERVAL_DELTAS)}"
            ) from exc

    @staticmethod
    def _decode(response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("market provider returned an invalid response object")
        if payload.get("status") == "error":
            raise RuntimeError(str(payload.get("message") or "market provider error"))
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
