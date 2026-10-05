"""Deterministic mock provider used only for tests and explicit demo mode."""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal


from slaifi.core.types import CurrencyCode
from slaifi.domain.market.models import AssetRef, OHLCVBar, PriceQuote
from logs.logger import get_logger

logger = get_logger("SLAIFI Mock Market Data")


class MockMarketDataProvider:
    """Explicit deterministic test/demo market provider."""

    data_mode = "mock"

    _prices = {
        "SPY": ("100.00", "0.42"),
        "QQQ": ("200.00", "-0.18"),
        "DIA": ("150.00", "0.11"),
        "VIX": ("20.00", "0.00"),
    }

    async def get_quotes(self, assets: Sequence[AssetRef]) -> Sequence[PriceQuote]:
        observed_at = datetime.now(UTC)
        raw_payload = [self._raw_quote(asset, observed_at) for asset in assets]
        quotes = [
            self._normalize(item, asset)
            for item, asset in zip(
                raw_payload,
                assets,
                strict=True,
            )
        ]

        logger.debug("Generated %d deterministic mock quote(s)", len(quotes))
        return quotes

    async def get_bars(
        self,
        asset: AssetRef,
        *,
        start_at: datetime,
        end_at: datetime,
        interval: str = "1day",
    ) -> Sequence[OHLCVBar]:
        # Deliberately empty.
        #
        # The frontend must show "historical data unavailable"
        # instead of drawing fabricated chart data.
        return ()

    def _raw_quote(self, asset: AssetRef, observed_at: datetime) -> dict[str, str]:
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
            change_rate=float(
                Decimal(payload["pct_change"])
                / Decimal("100")
            ),
            currency=CurrencyCode(payload["currency_code"]),
            observed_at=datetime.fromisoformat(payload["captured_at"]),
            source="mock",
        )
