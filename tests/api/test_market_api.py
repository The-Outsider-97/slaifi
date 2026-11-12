from fastapi.testclient import TestClient
from tests.support import synthetic_gateway

from slaifi.core.config.settings import Settings
from slaifi.main import create_app


def test_health_endpoint() -> None:
    with TestClient(create_app(Settings())) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_market_overview_endpoint_exposes_normalized_contract() -> None:
    settings = Settings(market_overview_symbols=["SPY", "QQQ"])
    with TestClient(create_app(settings, market_gateway=synthetic_gateway())) as client:
        response = client.get("/api/v1/market/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_mode"] == "live"
    assert [quote["symbol"] for quote in payload["quotes"]] == ["SPY", "QQQ"]
    assert all(quote["source"] == "testfeed" for quote in payload["quotes"])
    assert payload["unavailable"] == []


def test_overview_without_any_api_key_says_not_available_and_invents_nothing(
    tmp_path, monkeypatch
) -> None:
    for name in ("TWELVEDATA", "TIINGO", "FMP", "FINNHUB", "ALPHAVANTAGE"):
        monkeypatch.delenv(f"SLAIFI_{name}_API_KEY", raising=False)
    monkeypatch.delenv("SLAIFI_MARKET_API_KEY", raising=False)
    settings = Settings(
        environment="test",
        data_dir=tmp_path / "d",
        slai_enabled=False,
        market_overview_symbols=["SPY", "QQQ"],
    )
    with TestClient(create_app(settings)) as client:
        payload = client.get("/api/v1/market/overview").json()
        providers = client.get("/api/v1/system/providers").json()

    assert payload["data_mode"] == "unavailable"
    assert payload["quotes"] == []
    assert payload["unavailable"] == ["SPY", "QQQ"]
    assert providers["configured"] is False
    assert {p["name"] for p in providers["providers"]} == {
        "twelvedata",
        "tiingo",
        "fmp",
        "finnhub",
        "alphavantage",
    }
    assert all(p["state"] == "not_configured" for p in providers["providers"])
