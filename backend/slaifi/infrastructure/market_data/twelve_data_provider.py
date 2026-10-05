"""Twelve Data market-data adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetId
from slaifi.domain.market.models import OHLCVBar, PriceQuote


class TwelveDataMarketDataProvider:
    """Translate Twelve Data responses into provider-neutral SLAIFI objects."""

    data_mode = "live"

    def __init__(self, *, api_key: str, timeout_seconds: float = 10.0) -> None:
        normalized_key = api_key.strip()
        if not normalized_key:
            raise ValueError("Twelve Data API key must not be blank")

        self._api_key = normalized_key
        self._client = httpx.AsyncClient(
            base_url="https://api.twelvedata.com",
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "Accept": "application/json",
                "User-Agent": "SLAIFI/0.3",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        if not assets:
            return ()

        quotes = await asyncio.gather(*(self._get_quote(asset) for asset in assets))
        return tuple(quotes)

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

        response = await self._client.get(
            "/time_series",
            params={
                "symbol": asset.symbol,
                "interval": interval,
                "start_date": start_at.astimezone(UTC).strftime("%Y-%m-%d"),
                "end_date": end_at.astimezone(UTC).strftime("%Y-%m-%d"),
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

            # Current SLAIFI market history endpoint requests daily bars.
            # Keep the domain timestamps explicit.
            closed_at = opened_at + timedelta(days=1)

            bars.append(
                OHLCVBar(
                    asset=asset,
                    start_at=opened_at,
                    end_at=closed_at,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                )
            )

        bars.sort(key=lambda bar: bar.start_at)
        return tuple(bars)

    async def _get_quote(self, asset: AssetId) -> PriceQuote:
        response = await self._client.get(
            "/quote",
            params={
                "symbol": asset.symbol,
                "apikey": self._api_key,
            },
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

        timestamp_raw = (payload.get("last_quote_at") or payload.get("timestamp"))

        if timestamp_raw is not None:
            observed_at = datetime.fromtimestamp(int(timestamp_raw), tz=UTC)
        else:
            observed_at = datetime.now(UTC)

        return PriceQuote(
            asset=asset,
            price=price,
            currency=CurrencyCode(str(currency_raw).upper()),
            observed_at=observed_at,
            source="twelvedata",
            change_rate=change_rate,
        )

    @staticmethod
    def _decode(response: httpx.Response) -> dict[str, Any]:
        response.raise_for_status()

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("market provider returned an invalid response object")

        if payload.get("status") == "error":
            message = payload.get("message") or "market provider error"
            raise RuntimeError(str(message))

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
