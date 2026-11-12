"""Three real adapters wired from settings, failing over end-to-end through the HTTP API.

The only fake is the network: an ``httpx.MockTransport`` answers per provider host with the
documented response shapes. Everything else (settings, factory, adapters, gateway, cache,
services, routes) is the shipped code.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from slaifi.core.config import Settings
from slaifi.infrastructure.market_data import InMemoryMarketCache, build_gateway
from slaifi.main import create_app

EPOCH = 1762801800
H = {"X-SLAIFI-Client": "test"}


SEARCH: dict[str, Any] = {
    "api.twelvedata.com": {
        "data": [
            {
                "symbol": "AAPL",
                "instrument_name": "Apple Inc",
                "exchange": "NASDAQ",
                "instrument_type": "Common Stock",
                "country": "United States",
                "currency": "USD",
            }
        ]
    },
    "api.tiingo.com": [
        {
            "ticker": "AAPL",
            "name": "Apple Inc",
            "assetType": "Stock",
            "isActive": True,
            "countryCode": "US",
        }
    ],
    "financialmodelingprep.com": [
        {"symbol": "AAPL", "name": "Apple Inc.", "currency": "USD", "exchange": "NASDAQ"}
    ],
    "finnhub.io": {
        "result": [{"symbol": "AAPL", "description": "APPLE INC", "type": "Common Stock"}]
    },
    "www.alphavantage.co": {
        "bestMatches": [
            {
                "1. symbol": "AAPL",
                "2. name": "Apple Inc",
                "3. type": "Equity",
                "4. region": "United States",
                "8. currency": "USD",
            }
        ]
    },
}


class Network:
    """Per-host scripted answers; records every request."""

    def __init__(self) -> None:
        self.mode: dict[str, str] = {}
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        host = request.url.host
        mode = self.mode.get(host, "ok")
        if mode == "down":
            return httpx.Response(503, text="unavailable")
        if mode == "limited":
            return httpx.Response(429, headers={"Retry-After": "600"})
        if mode == "badkey":
            return httpx.Response(401, json={})
        path = request.url.path
        if path in {"/symbol_search", "/tiingo/utilities/search", "/search-symbol", "/search"} or (
            request.url.params.get("function") == "SYMBOL_SEARCH"
        ):
            return httpx.Response(200, json=SEARCH[host])
        if host == "api.twelvedata.com":
            return httpx.Response(
                200,
                json={
                    "close": "228.52",
                    "currency": "USD",
                    "timestamp": EPOCH,
                    "last_quote_at": EPOCH,
                    "previous_close": "225.7",
                    "percent_change": "1.249",
                    "is_market_open": False,
                },
            )
        if host == "api.tiingo.com":
            return httpx.Response(
                200,
                json=[
                    {
                        "ticker": "AAPL",
                        "lastSaleTimestamp": "2026-11-10T20:59:58+00:00",
                        "tngoLast": 228.4,
                        "prevClose": 225.7,
                    }
                ],
            )
        if host == "financialmodelingprep.com":
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "AAPL",
                        "price": 228.3,
                        "previousClose": 225.7,
                        "changePercentage": 1.1,
                        "timestamp": EPOCH,
                    }
                ],
            )
        if host == "finnhub.io":
            return httpx.Response(200, json={"c": 228.2, "pc": 225.7, "dp": 1.1, "t": EPOCH})
        if host == "www.alphavantage.co":
            return httpx.Response(
                200,
                json={
                    "Global Quote": {
                        "05. price": "228.1000",
                        "07. latest trading day": "2026-11-10",
                    }
                },
            )
        return httpx.Response(404)

    def hosts(self) -> list[str]:
        """Hosts that received a *quote* request (symbol look-ups are excluded)."""

        searches = {"/symbol_search", "/tiingo/utilities/search", "/search-symbol", "/search"}
        return [
            r.url.host
            for r in self.seen
            if r.url.path not in searches and r.url.params.get("function") != "SYMBOL_SEARCH"
        ]


def settings(tmp: Path, **kw: Any) -> Settings:
    kw.setdefault("market_overview_symbols", ["AAPL"])
    kw.setdefault("market_quote_cache_ttl_seconds", 0.0)  # every request reaches the network
    return Settings(environment="test", data_dir=tmp / "d", slai_enabled=False, **kw)


def app_with(net: Network, tmp: Path, **kw: Any) -> TestClient:
    s = settings(tmp, **kw)
    gateway = build_gateway(s, cache=InMemoryMarketCache(), transport=httpx.MockTransport(net))
    return TestClient(create_app(s, market_gateway=gateway))


THREE = dict(twelvedata_api_key="k1", tiingo_api_key="k2", fmp_api_key="k3")


def test_first_configured_provider_serves_when_healthy(tmp_path: Path) -> None:
    net = Network()
    with app_with(net, tmp_path, **THREE) as c:
        body = c.get("/api/v1/market/quote/AAPL").json()
    assert body["source"] == "twelvedata" and body["price"] == "228.52"
    assert net.hosts() == ["api.twelvedata.com"]


def test_two_providers_down_third_answers_and_everything_is_reported(tmp_path: Path) -> None:
    net = Network()
    net.mode.update({"api.twelvedata.com": "limited", "api.tiingo.com": "down"})
    with app_with(net, tmp_path, **THREE) as c:
        body = c.get("/api/v1/market/quote/AAPL").json()
        status = {p["name"]: p for p in c.get("/api/v1/system/providers").json()["providers"]}
    assert body["source"] == "fmp" and body["price"] == "228.3" and body["last_known"] is False
    # Neither FMP nor Twelve Data documents a delay for free keys, so SLAIFI never says "real time".
    assert body["provenance"]["mode"] == "live_delay_unknown"
    attempts = [(a["source"], a["outcome"]) for a in body["provenance"]["attempts"]]
    assert [name for name, _ in attempts] == ["twelvedata", "tiingo", "fmp"]
    assert attempts[-1][1] == "ok" and all(outcome != "ok" for _, outcome in attempts[:2])
    assert status["twelvedata"]["state"] == "cooling_down"
    assert status["fmp"]["state"] == "ready" and status["fmp"]["last_success_at"]
    assert status["finnhub"]["state"] == "not_configured"


def test_all_five_providers_can_be_configured_and_order_is_respected(tmp_path: Path) -> None:
    net = Network()
    keys = dict(
        twelvedata_api_key="a",
        tiingo_api_key="b",
        fmp_api_key="c",
        finnhub_api_key="d",
        alphavantage_api_key="e",
    )
    with app_with(
        net, tmp_path, market_provider_order="alphavantage,finnhub,fmp,tiingo,twelvedata", **keys
    ) as c:
        body = c.get("/api/v1/market/quote/AAPL").json()
        listing = c.get("/api/v1/system/providers").json()["providers"]
    assert body["source"] == "alphavantage" and body["provenance"]["mode"] == "delayed"
    assert [p["name"] for p in listing] == [
        "alphavantage",
        "finnhub",
        "fmp",
        "tiingo",
        "twelvedata",
    ]
    assert all(p["configured"] for p in listing)


def test_every_provider_down_serves_last_known_then_not_available(tmp_path: Path) -> None:
    net = Network()
    with app_with(net, tmp_path, **THREE) as c:
        live = c.get("/api/v1/market/quote/AAPL").json()
        assert live["provenance"]["mode"] == "live_delay_unknown" and live["last_known"] is False
        net.mode.update(
            {
                h: "down"
                for h in ("api.twelvedata.com", "api.tiingo.com", "financialmodelingprep.com")
            }
        )
        stale = c.get("/api/v1/market/quote/AAPL").json()
        assert stale["last_known"] is True and stale["provenance"]["mode"] == "last_known"
        assert stale["price"] == "228.52" and stale["source"] == "twelvedata"
        assert stale["observed_at"] == live["observed_at"]  # original observation time
        assert stale["provenance"]["saved_at"]
        never_seen = c.get("/api/v1/market/quote/MSFT").json()
    assert never_seen["available"] is False and never_seen["price"] is None
    assert never_seen["provenance"]["mode"] == "unavailable"


def test_last_known_quote_cannot_be_used_to_execute_a_paper_order(tmp_path: Path) -> None:
    net = Network()
    with app_with(net, tmp_path, **THREE) as c:
        pid = c.post(
            "/api/v1/paper/portfolios", headers=H, json={"name": "T", "starting_capital": "100000"}
        ).json()["portfolio"]["portfolio_id"]
        c.get("/api/v1/market/quote/AAPL")  # saves a real observation
        net.mode.update(
            {
                h: "down"
                for h in ("api.twelvedata.com", "api.tiingo.com", "financialmodelingprep.com")
            }
        )
        placed = c.post(
            f"/api/v1/paper/portfolios/{pid}/orders",
            headers=H,
            json={"symbol": "AAPL", "side": "buy", "quantity": "1", "client_order_id": "x1"},
        ).json()
    assert placed["decision"]["status"] == "rejected"
    assert "quote_last_known" in {r["code"] for r in placed["decision"]["rejections"]}


def test_overview_uses_the_next_provider_when_the_first_is_down(tmp_path: Path) -> None:
    net = Network()
    net.mode["api.twelvedata.com"] = "down"
    with app_with(net, tmp_path, market_overview_symbols=["AAPL", "MSFT"], **THREE) as c:
        ov = c.get("/api/v1/market/overview").json()
    assert [q["symbol"] for q in ov["quotes"]] == ["AAPL", "MSFT"]
    assert {q["source"] for q in ov["quotes"]} == {"tiingo"}
    assert ov["data_mode"] == "live_delay_unknown" and ov["unavailable"] == []


def test_overview_with_all_providers_down_and_nothing_saved_is_not_available(
    tmp_path: Path,
) -> None:
    net = Network()
    net.mode.update(
        {h: "down" for h in ("api.twelvedata.com", "api.tiingo.com", "financialmodelingprep.com")}
    )
    with app_with(net, tmp_path, **THREE) as c:
        ov = c.get("/api/v1/market/overview").json()
    assert ov["data_mode"] == "unavailable" and ov["quotes"] == [] and ov["unavailable"] == ["AAPL"]


def test_provider_check_endpoint_probes_each_configured_provider(tmp_path: Path) -> None:
    net = Network()
    net.mode["api.tiingo.com"] = "badkey"
    with app_with(net, tmp_path, **THREE) as c:
        refused = c.post("/api/v1/system/providers/check")
        checks = {
            x["name"]: x
            for x in c.post("/api/v1/system/providers/check", headers=H).json()["checks"]
        }
    assert refused.status_code == 403  # a probe spends free-tier quota, so it needs the header
    assert checks["twelvedata"]["ok"] is True and "228.52" in checks["twelvedata"]["detail"]
    assert checks["tiingo"]["ok"] is False and "key" in checks["tiingo"]["detail"].lower()
    assert checks["fmp"]["ok"] is True
    assert checks["finnhub"]["configured"] is False


def test_api_keys_never_appear_in_any_response(tmp_path: Path) -> None:
    net = Network()
    keys = dict(
        twelvedata_api_key="SUPERSECRET-1",
        tiingo_api_key="SUPERSECRET-2",
        fmp_api_key="SUPERSECRET-3",
    )
    net.mode["api.twelvedata.com"] = "badkey"
    with app_with(net, tmp_path, **keys) as c:
        texts = [
            c.get("/api/v1/market/quote/AAPL").text,
            c.get("/api/v1/market/meta").text,
            c.get("/api/v1/system/status").text,
            c.get("/api/v1/system/providers").text,
            c.post("/api/v1/system/providers/check", headers=H).text,
        ]
    assert not any("SUPERSECRET" in t for t in texts)


def test_keys_are_sent_the_way_each_provider_documents(tmp_path: Path) -> None:
    net = Network()
    net.mode.update(
        {
            "api.twelvedata.com": "down",
            "api.tiingo.com": "down",
            "financialmodelingprep.com": "down",
        }
    )
    keys = dict(**THREE, finnhub_api_key="k4", alphavantage_api_key="k5")
    with app_with(net, tmp_path, **keys) as c:
        c.get("/api/v1/market/quote/AAPL")
    by_host = {r.url.host: r for r in net.seen if r.url.params.get("symbol", "AAPL") == "AAPL"}
    assert by_host["api.twelvedata.com"].url.params["apikey"] == "k1"
    assert by_host["api.tiingo.com"].headers["Authorization"] == "Token k2"
    assert by_host["financialmodelingprep.com"].url.params["apikey"] == "k3"
    assert by_host["finnhub.io"].headers["X-Finnhub-Token"] == "k4"
    assert "api.tiingo.com" in by_host and "k2" not in str(by_host["api.tiingo.com"].url)


@pytest.mark.parametrize("path", ["/api/v1/market/overview", "/api/v1/market/quote/AAPL"])
def test_app_with_no_keys_makes_no_network_calls(tmp_path: Path, path: str) -> None:
    net = Network()
    with app_with(net, tmp_path) as c:
        body = c.get(path).json()
    assert net.seen == []
    assert body.get("data_mode") == "unavailable" or body.get("available") is False
