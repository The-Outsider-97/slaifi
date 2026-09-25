"""Deterministic mock provider used only to prove the architecture vertical slice."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from logs.logger import get_logger

from slaifi.core.types import CurrencyCode
from slaifi.domain.market.models import AssetRef, PriceQuote

logger = get_logger("SLAIFI Mock Market Data")


class MockMarketDataProvider:
    """Translate a provider-shaped mock payload into SLAIFI domain quotes."""

    _prices = {
        "SPY": ("100.00", "0.42"),
        "QQQ": ("200.00", "-0.18"),
        "DIA": ("150.00", "0.11"),
    }

    async def get_quotes(self, assets: Sequence[AssetRef]) -> Sequence[PriceQuote]:
        observed_at = datetime.now(UTC)
        raw_payload = [self._raw_quote(asset, observed_at) for asset in assets]
        quotes = [
            self._normalize(item, asset)
            for item, asset in zip(raw_payload, assets, strict=True)
        ]
        logger.debug("Generated %d deterministic mock quote(s)", len(quotes))
        return quotes

    def _raw_quote(
        self,
        asset: AssetRef,
        observed_at: datetime,
    ) -> dict[str, str]:
        price, change = self._prices.get(asset.symbol, ("50.00", "0.00"))
        return {
            "ticker": asset.symbol,
            "last": price,
            "pct_change": change,
            "currency_code": "USD",
            "captured_at": observed_at.isoformat(),
        }

    @staticmethod
    def _normalize(payload: dict[str, str], asset: AssetRef) -> PriceQuote:
        return PriceQuote(
            asset=asset,
            price=Decimal(payload["last"]),
            change_rate=float(Decimal(payload["pct_change"]) / Decimal("100")),
            currency=CurrencyCode(payload["currency_code"]),
            observed_at=datetime.fromisoformat(payload["captured_at"]),
            source="mock",
        )
