from fastapi.testclient import TestClient

from slaifi.core.config.settings import Settings
from slaifi.main import create_app


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
