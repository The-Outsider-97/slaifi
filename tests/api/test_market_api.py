from collections.abc import Sequence
from datetime import datetime

from fastapi.testclient import TestClient

from slaifi.core.config.settings import Settings
from slaifi.core.utils.errors import InfrastructureError
from slaifi.domain.assets import AssetId
from slaifi.domain.market.models import OHLCVBar, PriceQuote
from slaifi.main import create_app


class FailingMarketProvider:
    data_mode = "live"

    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        raise InfrastructureError(
            "Market data provider is unavailable",
            component="market_data",
            operation="quote",
            retryable=True,
        )

    async def get_bars(
        self,
        asset: AssetId,
        *,
        start_at: datetime,
        end_at: datetime,
        interval: str = "1day",
    ) -> Sequence[OHLCVBar]:
        raise InfrastructureError(
            "Market data provider is unavailable",
            component="market_data",
            operation="history",
            retryable=True,
        )


def test_health_endpoint() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_market_overview_endpoint_exposes_normalized_contract() -> None:
    settings = Settings(market_overview_symbols=["SPY", "QQQ"])
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/market/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_mode"] == "mock"
    assert [quote["symbol"] for quote in payload["quotes"]] == ["SPY", "QQQ"]
    assert all(quote["source"] == "mock" for quote in payload["quotes"])


def test_market_provider_failure_is_explicit_service_unavailable() -> None:
    app = create_app(
        Settings(environment="test", market_overview_symbols=["SPY"]),
        market_provider=FailingMarketProvider(),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/market/overview")

    assert response.status_code == 503
    assert response.json() == {
        "error": "infrastructure_unavailable",
        "detail": "Market data provider is unavailable",
        "retryable": True,
    }
