"""Small helpers shared by adapters for building validated bars and quotes."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetId
from slaifi.domain.market import OHLCVBar
from slaifi.domain.utils import DomainValidationError

STEPS: dict[str, timedelta] = {
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


def make_bar(
    asset: AssetId,
    start_at: datetime,
    interval: str,
    *,
    open_: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    volume: Decimal,
) -> OHLCVBar | None:
    """Return a bar, or ``None`` when the provider's numbers are internally inconsistent."""

    try:
        return OHLCVBar(
            asset=asset,
            start_at=start_at,
            end_at=start_at + STEPS[interval],
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )
    except (DomainValidationError, ValueError):
        return None


def currency_of(asset: AssetId, reported: object = None) -> CurrencyCode:
    """Currency the provider reported, else the asset's own, else USD (documented assumption)."""

    if reported:
        try:
            return CurrencyCode(str(reported).strip().upper())
        except ValueError:
            pass
    if asset.currency is not None:
        return asset.currency
    return CurrencyCode("USD")


def within(bars: list[OHLCVBar], start_at: datetime, end_at: datetime) -> tuple[OHLCVBar, ...]:
    return tuple(
        sorted(
            (b for b in bars if start_at <= b.start_at <= end_at),
            key=lambda b: b.start_at,
        )
    )
