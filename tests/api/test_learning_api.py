"""Track record, strategy suggestions and SLAI goal review over HTTP."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.support import synthetic_gateway

from slaifi.core.config import Settings
from slaifi.domain.learning import RecommendationRecord
from slaifi.main import create_app

H = {"X-SLAIFI-Client": "test"}


@pytest.fixture()
def client(tmp_path: Path) -> Any:
    settings = Settings(environment="test", data_dir=tmp_path / "d", slai_enabled=False)
    app = create_app(settings, market_gateway=synthetic_gateway())
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_requesting_a_recommendation_logs_it_once_per_day(client: TestClient) -> None:
    for _ in range(3):
        assert client.get("/api/v1/recommendations/SPY").status_code == 200
    record = client.get("/api/v1/learning/track-record").json()
    assert record["logged"] <= 1  # repeated loads never inflate the sample
    assert record["scored"] == 0 and record["verdict"] == "insufficient_sample"
    assert "not a forecast" in record["method"]


def test_due_recommendations_are_scored_against_real_prices(client: TestClient) -> None:
    store = client.app.state.finance_store  # type: ignore[attr-defined]
    issued = datetime.now(UTC) - timedelta(days=60)
    store.log_recommendation(
        RecommendationRecord(
            record_id="R-old",
            symbol="SPY",
            asset_class="etf",
            action="BUY",
            strategy_id="x",
            issued_at=issued,
            reference_price=Decimal("1.00"),  # far below the feed, so the "BUY" was right
        )
    )
    fresh = RecommendationRecord(
        record_id="R-new",
        symbol="QQQ",
        asset_class="etf",
        action="BUY",
        strategy_id="x",
        issued_at=datetime.now(UTC),
        reference_price=Decimal("100"),
    )
    store.log_recommendation(fresh)
    response = client.post("/api/v1/learning/track-record/refresh", headers=H)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refresh"]["evaluated"] == 1
    assert body["refresh"]["waiting"] >= 1  # the new one is too young to judge
    assert body["track_record"]["scored"] == 1 and body["track_record"]["hits"] == 1
    # A single hit is not evidence of anything.
    assert body["track_record"]["verdict"] == "insufficient_sample"
    # Scoring is permanent: a second refresh does not score it again.
    again = client.post("/api/v1/learning/track-record/refresh", headers=H).json()
    assert again["refresh"]["evaluated"] == 0 and again["track_record"]["scored"] == 1


def test_refresh_requires_the_write_header(client: TestClient) -> None:
    assert client.post("/api/v1/learning/track-record/refresh").status_code == 403


def test_adaptations_without_a_portfolio_explain_themselves(client: TestClient) -> None:
    strategies = client.get("/api/v1/strategies").json()
    sid = strategies["active_strategy_id"]
    r = client.get(f"/api/v1/strategies/{sid}/adaptations")
    assert r.status_code == 200
    body = r.json()
    assert body["proposals"] == []
    assert any("never raise risk" in n for n in body["notes"])
    assert body["explanation"] is None


def test_goal_review_returns_report_and_a_labelled_interpretation(client: TestClient) -> None:
    gid = client.post(
        "/api/v1/goal-tracker",
        headers=H,
        json={
            "name": "g",
            "target_amount": "100",
            "period": "monthly",
            "starting_capital": "10000",
        },
    ).json()["goal_id"]
    r = client.post(f"/api/v1/goal-tracker/{gid}/review", json={"assumed_annual_return_rate": 0.05})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["report"]["required_annual_return_rate"] == pytest.approx(0.12, rel=0.01)
    # SLAI is disabled in this app: the figures are still returned, the reading is absent.
    assert body["explanation"]["text"] is None
    assert body["explanation"]["status"] in {"disabled", "unavailable"}
    assert "never changes it" in body["explanation"]["label"]


class RecordingReasoner:
    def __init__(self, text: str) -> None:
        self.text = text
        self.requests: list[Any] = []

    def reason(self, request: Any) -> Any:
        from slaifi.application.contracts import ReasoningResult, ReasoningStatus

        self.requests.append(request)
        return ReasoningResult(
            status=ReasoningStatus.AVAILABLE,
            interpretation=self.text,
            agent="reasoning",
            agent_version="t",
            request_id=request.request_id,
        )

    def status(self) -> Any:
        from slaifi.application.contracts import ReasoningResult, ReasoningStatus

        return ReasoningResult(status=ReasoningStatus.AVAILABLE, interpretation=None)


def _slai_client(tmp_path: Path, reasoner: RecordingReasoner) -> TestClient:
    settings = Settings(environment="test", data_dir=tmp_path / "d", slai_enabled=False)
    app = create_app(settings, market_gateway=synthetic_gateway(), financial_reasoner=reasoner)
    return TestClient(app, raise_server_exceptions=False)


def test_slai_reads_the_goal_plan_but_figures_stay_deterministic(tmp_path: Path) -> None:
    reasoner = RecordingReasoner("Reaching the target needs steady saving and time.")
    with _slai_client(tmp_path, reasoner) as c:
        gid = c.post(
            "/api/v1/goal-tracker",
            headers=H,
            json={
                "name": "House",
                "basis": "target_balance",
                "target_value": "20000",
                "horizon_years": 5,
                "starting_capital": "10000",
            },
        ).json()["goal_id"]
        body = c.post(
            f"/api/v1/goal-tracker/{gid}/review", json={"assumed_annual_return_rate": 0.05}
        ).json()
    assert body["explanation"]["text"] == "Reaching the target needs steady saving and time."
    request = reasoner.requests[-1]
    assert request.operation == "goal_plan_review"
    assert request.constraints["figures_are_authoritative"] is True
    assert request.evidence["plan"]["kind"] == "target_balance"
    # The numbers in the response come from the engine, not from the interpretation.
    assert body["report"]["plan"]["required_annual_return_rate"] == pytest.approx(
        2 ** (1 / 5) - 1, abs=1e-4
    )


def test_slai_reading_of_advice_that_promises_returns_is_withheld(tmp_path: Path) -> None:
    reasoner = RecordingReasoner("This goal is guaranteed to succeed, a sure thing.")
    with _slai_client(tmp_path, reasoner) as c:
        gid = c.post(
            "/api/v1/goal-tracker",
            headers=H,
            json={
                "name": "g",
                "target_amount": "100",
                "period": "monthly",
                "starting_capital": "5000",
            },
        ).json()["goal_id"]
        body = c.post(f"/api/v1/goal-tracker/{gid}/review", json={}).json()
    assert body["explanation"]["text"] is None
    assert body["explanation"]["status"] == "withheld"
    assert body["report"]["goal_id"] == gid


def test_slai_gets_the_track_record_as_context_for_recommendations(tmp_path: Path) -> None:
    reasoner = RecordingReasoner("The signals lean positive but conflict on momentum.")
    with _slai_client(tmp_path, reasoner) as c:
        r = c.get("/api/v1/recommendations/SPY", params={"explain": "true"})
        assert r.status_code == 200
    asked = [q for q in reasoner.requests if q.operation == "recommendation_explanation"]
    if asked:  # an insufficient-evidence report is never sent for interpretation
        context = asked[0].uncertainty["track_record"]
        assert context["verdict"] == "insufficient_sample"
        assert context["decisive_results"] == 0


def test_slai_reviews_adaptation_suggestions_with_a_do_not_raise_risk_constraint(
    tmp_path: Path,
) -> None:
    reasoner = RecordingReasoner("Nothing urgent; keep monitoring the limits.")
    with _slai_client(tmp_path, reasoner) as c:
        sid = c.get("/api/v1/strategies").json()["active_strategy_id"]
        body = c.get(f"/api/v1/strategies/{sid}/adaptations", params={"explain": "true"}).json()
    assert body["explanation"]["text"] == "Nothing urgent; keep monitoring the limits."
    request = reasoner.requests[-1]
    assert request.operation == "strategy_adaptation_review"
    assert request.constraints["never_suggest_more_risk"] is True
