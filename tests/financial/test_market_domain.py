from datetime import UTC, datetime
from decimal import Decimal

import pytest

from slaifi.domain.market.models import AssetRef, PriceQuote


def test_price_quote_rejects_non_positive_price() -> None:
    with pytest.raises(ValueError, match="price must be positive"):
        PriceQuote(
            asset=AssetRef("TEST"),
            price=Decimal("0"),
            currency="USD",
            observed_at=datetime.now(UTC),
            source="test",
        )


def test_price_quote_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        PriceQuote(
            asset=AssetRef("TEST"),
            price=Decimal("1"),
            currency="USD",
            observed_at=datetime(2026, 9, 25),
            source="test",
        )
