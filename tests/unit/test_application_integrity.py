from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from slaifi.application.analysis import AnalyzeMarketSeries, AnalyzePortfolio
from slaifi.core.exceptions import ValidationError
from slaifi.domain.assets import AssetId
from slaifi.domain.market import OHLCVBar
from slaifi.domain.portfolio import Portfolio, Trade, TradeSide


def _bar(asset: AssetId, day: int) -> OHLCVBar:
    start = datetime(2026, 1, day, tzinfo=UTC)
    return OHLCVBar(
        asset=asset,
        start_at=start,
        end_at=start + timedelta(days=1),
        open=Decimal("100"),
        high=Decimal("102"),
        low=Decimal("99"),
        close=Decimal("101"),
        volume=Decimal("1000"),
    )


def test_market_analysis_rejects_mixed_asset_series() -> None:
    expected = AssetId("AAA", exchange="XNAS")
    other = AssetId("BBB", exchange="XNAS")
    with pytest.raises(ValidationError, match="asset being analyzed"):
        AnalyzeMarketSeries().execute(
            expected,
            (_bar(expected, 1), _bar(other, 2)),
            periods_per_year=252,
        )


def test_portfolio_analysis_rejects_future_trade_for_snapshot() -> None:
    asset = AssetId("AAA", exchange="XNAS", currency="USD")
    portfolio = Portfolio(
        portfolio_id="p1",
        name="Primary",
        base_currency="USD",
        trades=(
            Trade(
                trade_id="future",
                asset=asset,
                side=TradeSide.BUY,
                quantity=Decimal("1"),
                unit_price=Decimal("100"),
                fee=Decimal("0"),
                occurred_at=datetime(2026, 2, 1, tzinfo=UTC),
                currency="USD",
            ),
        ),
    )
    with pytest.raises(ValidationError, match="trades after as_of"):
        AnalyzePortfolio().execute(
            portfolio,
            {asset: Decimal("110")},
            as_of=datetime(2026, 1, 31, tzinfo=UTC),
            initial_cash=Decimal("1000"),
        )
