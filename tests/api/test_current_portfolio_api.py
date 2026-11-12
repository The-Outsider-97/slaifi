import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from tests.support import SyntheticFeed, synthetic_gateway

from slaifi.application.contracts import ReasoningRequest, ReasoningResult, ReasoningStatus
from slaifi.core.config import Settings
from slaifi.core.types import CurrencyCode
from slaifi.core.utils.errors import MarketDataUnavailableError
from slaifi.domain.assets import AssetId
from slaifi.domain.market.models import PriceQuote
from slaifi.main import create_app


class PortfolioFeed(SyntheticFeed):
    """A provider that prices the test portfolio's only holding at a fixed 120."""

    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        observed_at = datetime.now(UTC)
        return tuple(
            PriceQuote(
                asset=asset,
                price=Decimal("120"),
                currency=CurrencyCode("USD"),
                observed_at=observed_at,
                source="testfeed",
                delayed=False,
            )
            for asset in assets
        )


class DownFeed(SyntheticFeed):
    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        raise MarketDataUnavailableError("down", component="testfeed", operation="quote")


class RecordingReasoner:
    def __init__(self) -> None:
        self.requests: list[ReasoningRequest] = []

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.requests.append(request)
        return ReasoningResult(
            status=ReasoningStatus.AVAILABLE,
            interpretation="Portfolio evidence reviewed.",
            agent="reasoning",
            request_id=request.request_id,
            correlation_id="portfolio-correlation",
            validation_status="passed",
        )

    def status(self) -> ReasoningResult:
        return ReasoningResult(status=ReasoningStatus.AVAILABLE, interpretation=None)


def write_portfolio(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "portfolio_id": "primary",
                "name": "Primary",
                "base_currency": "USD",
                "trades": [
                    {
                        "trade_id": "buy-1",
                        "asset": {
                            "symbol": "ABC",
                            "asset_class": "equity",
                            "currency": "USD",
                        },
                        "side": "buy",
                        "quantity": "2",
                        "unit_price": "100",
                        "fee": "0",
                        "occurred_at": "2026-01-02T00:00:00+00:00",
                        "currency": "USD",
                    }
                ],
                "cash_flows": [
                    {
                        "flow_id": "funding-1",
                        "kind": "contribution",
                        "amount": "1000",
                        "occurred_at": "2026-01-01T00:00:00+00:00",
                        "currency": "USD",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_current_portfolio_is_deterministic_by_default(tmp_path: Path) -> None:
    portfolio_file = tmp_path / "portfolio.json"
    write_portfolio(portfolio_file)
    reasoner = RecordingReasoner()
    app = create_app(
        Settings(environment="test", portfolio_file=portfolio_file),
        market_gateway=synthetic_gateway(PortfolioFeed()),
        financial_reasoner=reasoner,
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/portfolio/current")

    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["total_value"] == "1040"
    assert body["snapshot"]["positions"][0]["market_price"] == "120"
    assert body["reasoning"] is None
    assert reasoner.requests == []
    assert body["price_basis"]["mode"] == "live"
    assert body["price_basis"]["sources"] == ["testfeed"]
    assert body["price_basis"]["last_known_symbols"] == []


def test_current_portfolio_runs_slai_only_when_explicitly_requested(tmp_path: Path) -> None:
    portfolio_file = tmp_path / "portfolio.json"
    write_portfolio(portfolio_file)
    reasoner = RecordingReasoner()
    app = create_app(
        Settings(environment="test", portfolio_file=portfolio_file),
        market_gateway=synthetic_gateway(PortfolioFeed()),
        financial_reasoner=reasoner,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/portfolio/current?include_reasoning=true",
            headers={"X-Request-ID": "portfolio-ui-1"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["reasoning"]["interpretation"] == "Portfolio evidence reviewed."
    assert body["reasoning"]["request_id"] == "portfolio-ui-1"
    assert len(reasoner.requests) == 1
    evidence = reasoner.requests[0].evidence
    assert evidence["total_value"] == "1040"
    assert evidence["positions"][0]["asset"] == "ABC"


def test_current_portfolio_returns_no_content_when_source_is_unconfigured() -> None:
    app = create_app(
        Settings(environment="test", portfolio_file=None),
        market_gateway=synthetic_gateway(PortfolioFeed()),
        financial_reasoner=RecordingReasoner(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/portfolio/current")

    assert response.status_code == 204
    assert response.content == b""


def test_portfolio_is_valued_at_last_known_prices_and_says_so(tmp_path: Path) -> None:
    portfolio_file = tmp_path / "portfolio.json"
    write_portfolio(portfolio_file)
    gateway = synthetic_gateway(PortfolioFeed())
    app = create_app(
        Settings(environment="test", portfolio_file=portfolio_file),
        market_gateway=gateway,
        financial_reasoner=RecordingReasoner(),
    )
    with TestClient(app) as client:
        assert client.get("/api/v1/portfolio/current").json()["price_basis"]["mode"] == "live"
        gateway._providers[0].get_quotes = DownFeed().get_quotes  # type: ignore[method-assign]
        gateway._quotes.clear()
        body = client.get("/api/v1/portfolio/current").json()

    assert body["snapshot"]["positions"][0]["market_price"] == "120"
    assert body["price_basis"]["mode"] == "last_known"
    assert body["price_basis"]["last_known_symbols"] == ["ABC"]


def test_portfolio_without_any_price_is_not_available_not_estimated(tmp_path: Path) -> None:
    portfolio_file = tmp_path / "portfolio.json"
    write_portfolio(portfolio_file)
    app = create_app(
        Settings(environment="test", portfolio_file=portfolio_file),
        market_gateway=synthetic_gateway(DownFeed()),
        financial_reasoner=RecordingReasoner(),
    )
    with TestClient(app) as client:
        response = client.get("/api/v1/portfolio/current")
    assert response.status_code == 503
    assert "NOT AVAILABLE" in response.json()["detail"]
