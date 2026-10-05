import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from slaifi.application.contracts import ReasoningRequest, ReasoningResult, ReasoningStatus
from slaifi.core.config import Settings
from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetId
from slaifi.domain.market.models import OHLCVBar, PriceQuote
from slaifi.main import create_app


class PortfolioMarketProvider:
    data_mode = "test"

    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        observed_at = datetime.now(UTC)
        return tuple(
            PriceQuote(
                asset=asset,
                price=Decimal("120"),
                currency=CurrencyCode("USD"),
                observed_at=observed_at,
                source="test",
            )
            for asset in assets
        )

    async def get_bars(
        self,
        asset: AssetId,
        *,
        start_at: datetime,
        end_at: datetime,
        interval: str = "1day",
    ) -> Sequence[OHLCVBar]:
        return ()


class MissingQuoteProvider(PortfolioMarketProvider):
    async def get_quotes(self, assets: Sequence[AssetId]) -> Sequence[PriceQuote]:
        return ()


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
        market_provider=PortfolioMarketProvider(),
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


def test_current_portfolio_runs_slai_only_when_explicitly_requested(tmp_path: Path) -> None:
    portfolio_file = tmp_path / "portfolio.json"
    write_portfolio(portfolio_file)
    reasoner = RecordingReasoner()
    app = create_app(
        Settings(environment="test", portfolio_file=portfolio_file),
        market_provider=PortfolioMarketProvider(),
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
        market_provider=PortfolioMarketProvider(),
        financial_reasoner=RecordingReasoner(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/portfolio/current")

    assert response.status_code == 204
    assert response.content == b""


def test_invalid_portfolio_json_is_a_configuration_failure(tmp_path: Path) -> None:
    portfolio_file = tmp_path / "portfolio.json"
    portfolio_file.write_text("{not valid json", encoding="utf-8")
    app = create_app(
        Settings(environment="test", portfolio_file=portfolio_file),
        market_provider=PortfolioMarketProvider(),
        financial_reasoner=RecordingReasoner(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/portfolio/current")

    assert response.status_code == 500
    assert response.json() == {
        "error": "configuration_error",
        "detail": "Configured portfolio source is not valid JSON",
    }


def test_missing_open_position_quote_is_service_unavailable(tmp_path: Path) -> None:
    portfolio_file = tmp_path / "portfolio.json"
    write_portfolio(portfolio_file)
    app = create_app(
        Settings(environment="test", portfolio_file=portfolio_file),
        market_provider=MissingQuoteProvider(),
        financial_reasoner=RecordingReasoner(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/portfolio/current")

    assert response.status_code == 503
    assert response.json() == {
        "error": "infrastructure_unavailable",
        "detail": "Current market prices are unavailable for one or more open positions",
        "retryable": True,
    }
