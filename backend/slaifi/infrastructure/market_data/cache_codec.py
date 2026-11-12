"""Serialisation of quotes, bars and instruments for the local last-known cache."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.market import InstrumentInfo, PriceQuote


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def from_text(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def key(asset: AssetId) -> str:
    return asset.symbol.upper()


def asset_dict(asset: AssetId) -> dict[str, Any]:
    return {
        "symbol": asset.symbol,
        "asset_class": asset.asset_class.value,
        "exchange": asset.exchange,
        "currency": str(asset.currency) if asset.currency is not None else None,
    }


def asset_from(data: dict[str, Any]) -> AssetId:
    return AssetId(
        symbol=data["symbol"],
        asset_class=AssetClass(data.get("asset_class") or "unknown"),
        exchange=data.get("exchange"),
        currency=CurrencyCode(data["currency"]) if data.get("currency") else None,
    )


def quote_dict(q: PriceQuote) -> dict[str, Any]:
    return {
        "asset": asset_dict(q.asset),
        "price": format(q.price, "f"),
        "currency": str(q.currency),
        "observed_at": utc_text(q.observed_at),
        "source": q.source,
        "change_rate": q.change_rate,
        "is_market_open": q.is_market_open,
        "delayed": q.delayed,
        "previous_close": format(q.previous_close, "f") if q.previous_close is not None else None,
    }


def quote_from(data: dict[str, Any]) -> PriceQuote:
    return PriceQuote(
        asset=asset_from(data["asset"]),
        price=Decimal(data["price"]),
        currency=CurrencyCode(data["currency"]),
        observed_at=from_text(data["observed_at"]),
        source=data["source"],
        change_rate=data.get("change_rate"),
        is_market_open=data.get("is_market_open"),
        delayed=data.get("delayed"),
        previous_close=Decimal(data["previous_close"]) if data.get("previous_close") else None,
    )


def instrument_dict(i: InstrumentInfo) -> dict[str, Any]:
    return {
        "asset": asset_dict(i.asset),
        "name": i.name,
        "country": i.country,
        "instrument_type": i.instrument_type,
    }


def instrument_from(data: dict[str, Any]) -> InstrumentInfo:
    return InstrumentInfo(
        asset=asset_from(data["asset"]),
        name=data["name"],
        country=data.get("country"),
        instrument_type=data.get("instrument_type"),
    )
