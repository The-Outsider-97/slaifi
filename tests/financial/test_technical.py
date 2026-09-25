from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaifi.core.exceptions import ValidationError
from slaifi.domain.assets import AssetId
from slaifi.domain.market import OHLCVBar
from slaifi.engines.technical import atr, ema, momentum, rsi, sma


def test_sma_and_ema_reference_values() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert sma(values, 3) == (None, None, 2.0, 3.0)
    assert ema(values, 3) == (None, None, 2.0, 3.0)


def test_momentum_reference() -> None:
    assert momentum([100.0, 110.0, 121.0], 2) == (
        None,
        None,
        pytest.approx(0.21),
    )


def test_rsi_reference_monotonic_and_flat_cases() -> None:
    assert rsi([1.0, 2.0, 3.0, 4.0], period=3)[-1] == pytest.approx(100.0)
    assert rsi([2.0, 2.0, 2.0, 2.0], period=3)[-1] == pytest.approx(50.0)


def _bar(day: int, high: str, low: str, close: str) -> OHLCVBar:
    start = datetime(2026, 1, day, tzinfo=UTC)
    return OHLCVBar(
        asset=AssetId("ABC"),
        start_at=start,
        end_at=start + timedelta(days=1),
        open=Decimal(close),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
    )


def test_atr_reference_values() -> None:
    bars = [
        _bar(1, "11", "9", "10"),
        _bar(2, "13", "10", "12"),
        _bar(3, "14", "11", "13"),
    ]
    result = atr(bars, period=2)
    assert result == (None, pytest.approx(2.5), pytest.approx(2.75))


def test_atr_rejects_unordered_bar_timestamps() -> None:
    first = _bar(2, "13", "10", "12")
    second = _bar(1, "11", "9", "10")
    with pytest.raises(ValidationError, match="strictly ordered"):
        atr([first, second], period=2)
