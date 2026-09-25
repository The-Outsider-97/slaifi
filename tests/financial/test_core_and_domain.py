from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaifi.core.exceptions import ValidationError
from slaifi.core.types import CurrencyCode, percent_to_rate, rate_to_percent
from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.goals import IncomePeriod, IncomeTarget, ReturnTarget, RiskConstraints
from slaifi.domain.market import MarketSnapshot, OHLCVBar, PriceQuote
from slaifi.domain.predictions import ConfidenceMeasure, Prediction, UncertaintyMeasure


def test_rate_conversion_convention() -> None:
    assert percent_to_rate(10.0) == pytest.approx(0.10)
    assert rate_to_percent(0.10) == pytest.approx(10.0)


def test_currency_code_normalizes_and_validates() -> None:
    assert CurrencyCode(" usd ") == "USD"
    with pytest.raises(ValidationError):
        CurrencyCode("US")


def test_asset_identity_distinguishes_exchanges() -> None:
    nyse = AssetId(
        "ABC",
        AssetClass.EQUITY,
        exchange="NYSE",
        currency=CurrencyCode("USD"),
    )
    nasdaq = AssetId(
        "ABC",
        AssetClass.EQUITY,
        exchange="NASDAQ",
        currency=CurrencyCode("USD"),
    )
    assert nyse != nasdaq
    assert nyse.display_symbol == "NYSE:ABC"


def test_quote_rejects_naive_timestamp_and_non_positive_price() -> None:
    asset = AssetId("ABC")
    with pytest.raises(ValidationError, match="timezone-aware"):
        PriceQuote(
            asset,
            Decimal("1"),
            CurrencyCode("USD"),
            datetime(2026, 1, 1),
            "test",
        )
    with pytest.raises(ValidationError, match="positive"):
        PriceQuote(
            asset,
            Decimal("0"),
            CurrencyCode("USD"),
            datetime.now(UTC),
            "test",
        )


def test_ohlcv_invariants() -> None:
    asset = AssetId("ABC")
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = start + timedelta(days=1)
    bar = OHLCVBar(
        asset=asset,
        start_at=start,
        end_at=end,
        open=Decimal("10"),
        high=Decimal("12"),
        low=Decimal("9"),
        close=Decimal("11"),
        volume=Decimal("100"),
    )
    assert bar.high == Decimal("12")
    with pytest.raises(ValidationError, match="high"):
        OHLCVBar(
            asset=asset,
            start_at=start,
            end_at=end,
            open=Decimal("10"),
            high=Decimal("10"),
            low=Decimal("9"),
            close=Decimal("11"),
            volume=Decimal("100"),
        )
    with pytest.raises(ValidationError, match="volume"):
        OHLCVBar(
            asset=asset,
            start_at=start,
            end_at=end,
            open=Decimal("10"),
            high=Decimal("12"),
            low=Decimal("9"),
            close=Decimal("11"),
            volume=Decimal("-1"),
        )


def test_market_snapshot_rejects_future_and_duplicate_quotes() -> None:
    asset = AssetId("ABC")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    quote = PriceQuote(
        asset,
        Decimal("10"),
        CurrencyCode("USD"),
        now,
        "test",
    )
    with pytest.raises(ValidationError, match="duplicate"):
        MarketSnapshot(as_of=now, quotes=(quote, quote))
    future = PriceQuote(
        asset,
        Decimal("10"),
        CurrencyCode("USD"),
        now + timedelta(seconds=1),
        "test",
    )
    with pytest.raises(ValidationError, match="future"):
        MarketSnapshot(as_of=now, quotes=(future,))


def test_goal_constraints_separate_allowed_and_prohibited_assets() -> None:
    with pytest.raises(ValidationError, match="both allowed and prohibited"):
        RiskConstraints(
            allowed_asset_classes=frozenset({AssetClass.EQUITY}),
            prohibited_asset_classes=frozenset({AssetClass.EQUITY}),
        )


def test_goal_targets_validate_without_implying_guarantee() -> None:
    assert ReturnTarget(0.10).annual_rate == pytest.approx(0.10)
    target = IncomeTarget(Decimal("150"), IncomePeriod.WEEKLY)
    assert target.amount == Decimal("150")


def test_prediction_separates_confidence_and_uncertainty() -> None:
    prediction = Prediction(
        asset=AssetId("ABC"),
        horizon=timedelta(days=30),
        generated_at=datetime(2026, 1, 2, tzinfo=UTC),
        input_data_at=datetime(2026, 1, 1, tzinfo=UTC),
        model_name="baseline",
        model_version="1.0",
        expected_return_rate=0.05,
        confidence=ConfidenceMeasure("calibration_probability", 0.7),
        uncertainty=UncertaintyMeasure("forecast_std", 0.12, "return_rate"),
    )
    assert prediction.confidence is not None
    assert prediction.uncertainty is not None
    assert prediction.confidence.value != prediction.uncertainty.value
