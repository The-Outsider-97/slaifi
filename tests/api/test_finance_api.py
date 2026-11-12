"""HTTP behaviour of the finance API: write protection, error mapping, safety and degraded modes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from tests.support import synthetic_gateway

from slaifi.application.contracts import (
    ReasoningRequest,
    ReasoningResult,
    ReasoningStatus,
    SafetyReview,
)
from slaifi.core.config import Settings
from slaifi.core.utils.errors import (
    MarketDataRateLimitedError,
    MarketDataUnavailableError,
    SymbolNotFoundError,
)
from slaifi.main import create_app as _create_app

H = {"X-SLAIFI-Client": "test"}


def create_app(s: Settings, **kw: Any) -> Any:
    """The real application over a real gateway whose only provider is the deterministic test feed."""

    kw.setdefault("market_gateway", synthetic_gateway())
    return _create_app(s, **kw)


def settings(tmp: Path, **kw: Any) -> Settings:
    return Settings(environment="test", data_dir=tmp / "d", slai_enabled=False, **kw)


@pytest.fixture()
def client(tmp_path: Path) -> Any:
    with TestClient(create_app(settings(tmp_path)), raise_server_exceptions=False) as c:
        yield c


def make_portfolio(c: TestClient, capital: str = "10000") -> str:
    r = c.post(
        "/api/v1/paper/portfolios", headers=H, json={"name": "T", "starting_capital": capital}
    )
    assert r.status_code == 201, r.text
    return str(r.json()["portfolio"]["portfolio_id"])


# ------------------------------------------------------------------ write protection
def test_mutations_require_the_client_header(client: TestClient) -> None:
    body = {"name": "T", "starting_capital": "100"}
    refused = client.post("/api/v1/paper/portfolios", json=body)
    assert refused.status_code == 403
    assert refused.json()["error"] == "client_header_required"
    assert client.post("/api/v1/paper/portfolios", headers=H, json=body).status_code == 201


def test_reads_and_previews_do_not_need_the_header(client: TestClient) -> None:
    pid = make_portfolio(client)
    assert client.get("/api/v1/paper/portfolios").status_code == 200
    preview = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders/preview",
        json={"symbol": "KO", "side": "buy", "quantity": "1"},
    )
    assert preview.status_code == 200 and preview.json()["dry_run"] is True


def test_header_requirement_can_be_disabled_by_setting(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path, api_require_client_header=False))) as c:
        assert (
            c.post(
                "/api/v1/paper/portfolios", json={"name": "T", "starting_capital": "100"}
            ).status_code
            == 201
        )


def test_cors_preflight_allows_client_header_and_patch(client: TestClient) -> None:
    r = client.options(
        "/api/v1/strategies/default",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "x-slaifi-client,content-type",
        },
    )
    assert r.status_code == 200
    assert "PATCH" in r.headers["access-control-allow-methods"]
    assert "x-slaifi-client" in r.headers["access-control-allow-headers"].lower()


def test_unknown_origin_is_not_granted_cors(client: TestClient) -> None:
    r = client.get("/api/v1/system/status", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in r.headers


# ------------------------------------------------------------------ validation and errors
def test_unknown_portfolio_is_404_and_bad_bodies_are_422(client: TestClient) -> None:
    assert client.get("/api/v1/paper/portfolios/P-nope").status_code == 404
    assert (
        client.post(
            "/api/v1/paper/portfolios", headers=H, json={"name": "T", "starting_capital": "-5"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/paper/portfolios",
            headers=H,
            json={"name": "T", "starting_capital": "5", "surprise": 1},
        ).status_code
        == 422
    )


def test_order_must_specify_exactly_one_size(client: TestClient) -> None:
    pid = make_portfolio(client)
    r = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders", headers=H, json={"symbol": "KO", "side": "buy"}
    )
    assert r.status_code == 422
    r = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        headers=H,
        json={"symbol": "KO", "side": "buy", "quantity": "1", "notional": "50"},
    )
    assert r.status_code == 422


def test_symbol_with_no_data_is_not_available_never_fabricated(client: TestClient) -> None:
    body = client.get("/api/v1/market/quote/NOSUCH").json()
    assert body["available"] is False
    assert body["price"] is None and body["observed_at"] is None and body["source"] is None
    assert body["provenance"]["mode"] == "unavailable"
    assert body["provenance"]["attempts"][0]["source"] == "testfeed"


def test_reset_needs_explicit_confirmation(client: TestClient) -> None:
    pid = make_portfolio(client)
    assert (
        client.post(f"/api/v1/paper/portfolios/{pid}/reset", headers=H, json={}).status_code == 422
    )
    assert (
        client.post(
            f"/api/v1/paper/portfolios/{pid}/reset", headers=H, json={"confirm": False}
        ).status_code
        == 422
    )


def test_money_stays_exact(client: TestClient) -> None:
    pid = make_portfolio(client, "100.00")
    for _ in range(3):
        r = client.post(
            f"/api/v1/paper/portfolios/{pid}/deposit", headers=H, json={"amount": "0.10"}
        )
    assert r.json()["cash_balance"] == "100.30"


def test_withdrawal_cannot_exceed_cash(client: TestClient) -> None:
    pid = make_portfolio(client, "100")
    r = client.post(f"/api/v1/paper/portfolios/{pid}/withdraw", headers=H, json={"amount": "1000"})
    assert r.status_code in {409, 422}
    assert client.get(f"/api/v1/paper/portfolios/{pid}").json()["cash_balance"] == "100.00"


def test_orders_are_idempotent_by_client_order_id(client: TestClient) -> None:
    pid = make_portfolio(client)
    order = {"symbol": "KO", "side": "buy", "quantity": "3", "client_order_id": "same"}
    first = client.post(f"/api/v1/paper/portfolios/{pid}/orders", headers=H, json=order).json()
    second = client.post(f"/api/v1/paper/portfolios/{pid}/orders", headers=H, json=order).json()
    assert first["decision"]["status"] == "filled" and second["duplicate"] is True
    assert client.get(f"/api/v1/paper/portfolios/{pid}/history").text.count("BUY") == 1


def test_rejected_orders_leave_cash_and_positions_untouched(client: TestClient) -> None:
    pid = make_portfolio(client, "1000")
    r = client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        headers=H,
        json={"symbol": "KO", "side": "buy", "quantity": "100000"},
    ).json()
    assert r["decision"]["status"] == "rejected" and r["decision"]["trade"] is None
    view = client.get(f"/api/v1/paper/portfolios/{pid}").json()
    assert view["cash_balance"] == "1000.00" and view["positions"] == []


def test_every_state_change_is_audited_and_chain_is_intact(client: TestClient) -> None:
    pid = make_portfolio(client)
    client.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        headers=H,
        json={"symbol": "KO", "side": "buy", "quantity": "1"},
    )
    entries = client.get("/api/v1/system/audit").json()["entries"]
    actions = {e["action"] for e in entries}
    assert "paper.portfolio.created" in actions
    assert client.get("/api/v1/system/status").json()["audit_chain_intact"] is True


def test_tampering_with_the_audit_log_is_detected(tmp_path: Path) -> None:
    import sqlite3

    s = settings(tmp_path)
    with TestClient(create_app(s)) as c:
        make_portfolio(c)
    db = tmp_path / "d" / "slaifi.db"
    con = sqlite3.connect(db)
    con.execute("UPDATE audit_log SET subject = 'tampered' WHERE seq = 1")
    con.commit()
    con.close()
    with TestClient(create_app(s), raise_server_exceptions=False) as c2:
        status = c2.get("/api/v1/system/status").json()
        assert status["audit_chain_intact"] is False
        assert status["storage_status"] != "ok"
        pid = c2.get("/api/v1/paper/portfolios").json()["portfolios"][0]["portfolio_id"]
        refused = c2.post(
            f"/api/v1/paper/portfolios/{pid}/orders",
            headers=H,
            json={"symbol": "KO", "side": "buy", "quantity": "1"},
        )
        assert refused.status_code == 409  # trading disabled, reads still work
        assert c2.get(f"/api/v1/paper/portfolios/{pid}").status_code == 200


def test_state_survives_restart(tmp_path: Path) -> None:
    s = settings(tmp_path)
    with TestClient(create_app(s)) as c:
        pid = make_portfolio(c)
        c.post(
            f"/api/v1/paper/portfolios/{pid}/orders",
            headers=H,
            json={"symbol": "KO", "side": "buy", "quantity": "4"},
        )
        before = c.get(f"/api/v1/paper/portfolios/{pid}").json()
    with TestClient(create_app(s)) as c2:
        after = c2.get(f"/api/v1/paper/portfolios/{pid}").json()
    assert after["cash_balance"] == before["cash_balance"]
    assert [p["quantity"] for p in after["positions"]] == [
        p["quantity"] for p in before["positions"]
    ]


# ------------------------------------------------------------------ market error mapping
def test_market_errors_map_to_stable_http_statuses(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path))
    router = APIRouter()

    @router.get("/_t/rate")
    async def rate() -> None:
        raise MarketDataRateLimitedError("slow down", retry_after_seconds=12)

    @router.get("/_t/down")
    async def down() -> None:
        raise MarketDataUnavailableError("provider down")

    @router.get("/_t/sym")
    async def sym() -> None:
        raise SymbolNotFoundError("nope")

    @router.get("/_t/boom")
    async def boom() -> None:
        raise RuntimeError("secret-api-key-123 at /home/x")

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/_t/rate")
        assert (
            r.status_code == 429
            and r.headers["retry-after"] == "12"
            and r.json()["retryable"] is True
        )
        assert c.get("/_t/down").status_code == 503
        assert c.get("/_t/sym").status_code == 404
        boom_response = c.get("/_t/boom")
        assert boom_response.status_code == 500
        assert "secret" not in boom_response.text and "/home" not in boom_response.text


# ------------------------------------------------------------------ strategies
def test_loosening_a_hard_limit_requires_acknowledgement(client: TestClient) -> None:
    current = client.get("/api/v1/strategies/default").json()["max_position_weight"]
    looser = min(1.0, current + 0.1)
    refused = client.patch(
        "/api/v1/strategies/default", headers=H, json={"fields": {"max_position_weight": looser}}
    )
    assert refused.status_code in {409, 422}
    assert client.get("/api/v1/strategies/default").json()["max_position_weight"] == current
    ok = client.patch(
        "/api/v1/strategies/default",
        headers=H,
        json={"fields": {"max_position_weight": looser}, "acknowledge_loosening": True},
    )
    assert ok.status_code == 200 and ok.json()["max_position_weight"] == pytest.approx(looser)
    # tightening never needs acknowledgement
    assert (
        client.patch(
            "/api/v1/strategies/default", headers=H, json={"fields": {"max_position_weight": 0.05}}
        ).status_code
        == 200
    )


def test_presets_initialise_but_do_not_lock(client: TestClient) -> None:
    presets = client.get("/api/v1/strategies").json()["presets"]
    made = client.post(
        "/api/v1/strategies", headers=H, json={"name": "Mine", "preset_id": presets[0]["preset"]}
    ).json()
    edited = client.patch(
        f"/api/v1/strategies/{made['strategy_id']}",
        headers=H,
        json={"fields": {"horizon_days": 45}},
    ).json()
    assert edited["horizon_days"] == 45


def test_unknown_strategy_field_is_rejected(client: TestClient) -> None:
    assert (
        client.patch(
            "/api/v1/strategies/default", headers=H, json={"fields": {"made_up": 1}}
        ).status_code
        == 422
    )


# ------------------------------------------------------------------ advisor
def interpret(c: TestClient, text: str, pid: str | None = None) -> dict[str, Any]:
    r = c.post(
        "/api/v1/advisor/interpret", json={"text": text, "portfolio_id": pid, "explain": False}
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


def test_advisor_never_changes_anything_until_confirmed(client: TestClient) -> None:
    before = client.get("/api/v1/strategies/default").json()
    result = interpret(client, "Never buy TSLA and keep any single position under 5%.")
    assert result["requires_confirmation"] is True and result["proposal"]
    assert client.get("/api/v1/strategies/default").json() == before
    confirmed = client.post(
        f"/api/v1/advisor/proposals/{result['proposal']['proposal_id']}/confirm", headers=H, json={}
    )
    assert confirmed.status_code == 200
    after = client.get("/api/v1/strategies/default").json()
    assert "TSLA" in after["excluded_symbols"] and after["max_position_weight"] == pytest.approx(
        0.05
    )


def test_advisor_confirmation_needs_the_client_header_and_cannot_repeat(client: TestClient) -> None:
    result = interpret(client, "Never buy TSLA.")
    pid = result["proposal"]["proposal_id"]
    assert client.post(f"/api/v1/advisor/proposals/{pid}/confirm", json={}).status_code == 403
    assert (
        client.post(f"/api/v1/advisor/proposals/{pid}/confirm", headers=H, json={}).status_code
        == 200
    )
    assert (
        client.post(f"/api/v1/advisor/proposals/{pid}/confirm", headers=H, json={}).status_code
        == 409
    )


def test_rejected_proposal_changes_nothing(client: TestClient) -> None:
    before = client.get("/api/v1/strategies/default").json()
    pid = interpret(client, "Never buy TSLA.")["proposal"]["proposal_id"]
    assert client.post(f"/api/v1/advisor/proposals/{pid}/reject", headers=H).status_code == 200
    assert client.get("/api/v1/strategies/default").json() == before
    assert (
        client.post(f"/api/v1/advisor/proposals/{pid}/confirm", headers=H, json={}).status_code
        == 409
    )


def test_loosening_via_advisor_needs_acknowledgement(client: TestClient) -> None:
    result = interpret(client, "Allow up to 40% in a single position.")
    assert result["needs_acknowledgement_of_limits"] is True
    pid = result["proposal"]["proposal_id"]
    refused = client.post(f"/api/v1/advisor/proposals/{pid}/confirm", headers=H, json={})
    assert refused.status_code == 409
    assert client.get("/api/v1/strategies/default").json()["max_position_weight"] != pytest.approx(
        0.4
    )
    ok = client.post(
        f"/api/v1/advisor/proposals/{pid}/confirm",
        headers=H,
        json={"acknowledge_limit_changes": True},
    )
    assert ok.status_code == 200


def test_temporary_instruction_is_not_persisted(client: TestClient) -> None:
    before = client.get("/api/v1/strategies/default").json()
    result = interpret(
        client, "For now, treat me as an aggressive investor, just for this analysis."
    )
    assert result["temporary_changes"] and not result["changes"]
    assert client.get("/api/v1/strategies/default").json() == before


def test_advisor_order_is_previewed_then_executed_only_on_confirmation(client: TestClient) -> None:
    pid = make_portfolio(client)
    result = interpret(client, "Buy $500 of KO.", pid)
    assert result["orders"][0]["preview"]["decision"]["status"] == "filled"
    assert client.get(f"/api/v1/paper/portfolios/{pid}").json()["positions"] == []
    client.post(
        f"/api/v1/advisor/proposals/{result['proposal']['proposal_id']}/confirm", headers=H, json={}
    )
    assert len(client.get(f"/api/v1/paper/portfolios/{pid}").json()["positions"]) == 1


def test_noop_exclusion_is_reported_as_already_in_effect(client: TestClient) -> None:
    result = interpret(client, "Never buy crypto.")
    assert result["unrecognised"] is False and result["requires_confirmation"] is False
    assert any("Already in effect" in line for line in result["understood"])


def test_contradictory_request_requires_acknowledgement(client: TestClient) -> None:
    result = interpret(client, "I want to be fully invested, but keep a 20% cash reserve.")
    assert result["contradictions"]
    if result["proposal"]:
        pid = result["proposal"]["proposal_id"]
        assert (
            client.post(f"/api/v1/advisor/proposals/{pid}/confirm", headers=H, json={}).status_code
            == 409
        )


# ------------------------------------------------------------------ SLAI degraded / guarded
class StubReasoner:
    def __init__(
        self, text: str | None = None, status: ReasoningStatus = ReasoningStatus.AVAILABLE
    ) -> None:
        self.text, self.status_value = text, status
        self.calls: list[str] = []

    def reason(self, request: ReasoningRequest) -> ReasoningResult:
        self.calls.append(request.operation)
        return ReasoningResult(
            status=self.status_value,
            interpretation=self.text,
            raw_result={},
            agent="reasoning",
            agent_version="t",
            correlation_id="c",
            request_id=request.request_id,
        )

    def status(self) -> ReasoningResult:
        return ReasoningResult(status=self.status_value, interpretation=None)


class Blocker:
    def review(self, text: str, *, purpose: str) -> SafetyReview:
        return SafetyReview(
            available=True,
            allowed=False,
            risk_level="high",
            blockers=("not allowed",),
            warnings=(),
            reviewer="stub",
            detail=None,
        )


def test_unavailable_slai_does_not_affect_the_deterministic_result(tmp_path: Path) -> None:
    down = StubReasoner(None, ReasoningStatus.UNAVAILABLE)
    with TestClient(create_app(settings(tmp_path), financial_reasoner=down)) as c:
        plain = c.get("/api/v1/recommendations/KO").json()
        explained = c.get("/api/v1/recommendations/KO", params={"explain": "true"}).json()
    strip = lambda r: {k: v for k, v in r.items() if k != "generated_at"}  # noqa: E731
    assert strip(explained["report"]) == strip(plain["report"])
    assert explained["explanation"]["status"] != "available"


def test_slai_text_claiming_probability_is_withheld(tmp_path: Path) -> None:
    liar = StubReasoner(
        "There is an 85% probability this stock will rise 20% next month, guaranteed."
    )
    with TestClient(create_app(settings(tmp_path), financial_reasoner=liar)) as c:
        body = c.get("/api/v1/recommendations/KO", params={"explain": "true"}).json()
    text = (body["explanation"] or {}).get("text") or ""
    assert "85%" not in text and "guaranteed" not in text.lower()


def test_safety_block_prevents_any_proposal(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path), safety_reviewer=Blocker())) as c:
        r = c.post(
            "/api/v1/advisor/interpret", json={"text": "Never buy TSLA.", "explain": False}
        ).json()
        assert r["blocked"] is True and r["proposal"] is None and r["changes"] == []


def test_slai_unavailable_is_surfaced_never_treated_as_approval(tmp_path: Path) -> None:
    with TestClient(create_app(settings(tmp_path))) as c:
        r = c.post(
            "/api/v1/advisor/interpret", json={"text": "Never buy TSLA.", "explain": False}
        ).json()
    assert (
        r["safety"] is None or r["safety"]["available"] is False or r["safety"]["allowed"] is True
    )
    assert r["requires_confirmation"] is True


# ------------------------------------------------------------------ watchlist, goals, misc
def test_watchlist_roundtrip(client: TestClient) -> None:
    assert (
        client.post("/api/v1/market/watchlist", headers=H, json={"symbol": "ko"}).status_code == 201
    )
    items = client.get("/api/v1/market/watchlist").json()["items"]
    assert [i["asset"]["symbol"] for i in items] == ["KO"]
    assert items[0]["quote"]["provenance"]["mode"] == "live"
    assert "illustrative" not in items[0]["quote"]["provenance"]
    assert client.delete("/api/v1/market/watchlist/KO", headers=H).json() == {"removed": True}
    assert client.get("/api/v1/market/watchlist").json()["items"] == []


def test_goal_crud_and_feasibility(client: TestClient) -> None:
    made = client.post(
        "/api/v1/goal-tracker",
        headers=H,
        json={
            "name": "m",
            "target_amount": "200",
            "period": "monthly",
            "basis": "realized_profit",
            "starting_capital": "10000",
        },
    )
    assert made.status_code == 201
    gid = made.json()["goal_id"]
    report = client.post(
        f"/api/v1/goal-tracker/{gid}/analyze", json={"assumed_annual_return_rate": 0.05}
    ).json()
    assert report["required_annual_return_rate"] == pytest.approx(
        0.24, rel=0.01
    )  # $2,400 a year on $10,000
    assert report["status"] != "guaranteed"
    assert "guarantee" in report["disclaimer"].lower()
    assert client.delete(f"/api/v1/goal-tracker/{gid}", headers=H).status_code == 200
    assert client.get("/api/v1/goal-tracker").json()["goals"] == []


def test_goal_with_invalid_enum_is_422(client: TestClient) -> None:
    r = client.post(
        "/api/v1/goal-tracker",
        headers=H,
        json={"name": "x", "basis": "nonsense", "target_amount": "10", "period": "monthly"},
    )
    assert r.status_code == 422


def test_market_responses_carry_real_provenance_and_no_mock_labels(client: TestClient) -> None:
    q = client.get("/api/v1/market/quote/KO").json()
    assert q["provenance"]["mode"] == "live" and q["provenance"]["source"] == "testfeed"
    assert q["last_known"] is False and "illustrative" not in q["provenance"]
    s = client.get("/api/v1/market/series/KO", params={"range": "3M"}).json()
    assert s["provenance"]["mode"] == "retrieved" and s["bars"]
    meta = client.get("/api/v1/market/meta").json()
    assert meta["intervals"] == ["1day"] and meta["configured"] is True
    assert [p["name"] for p in meta["providers"]] == ["testfeed"]
    assert "mock" not in str(meta).lower()


def test_unsupported_interval_is_explained_not_faked(client: TestClient) -> None:
    s = client.get("/api/v1/market/series/KO", params={"interval": "1h", "range": "1M"}).json()
    assert s["bars"] == [] and s["provenance"]["mode"] == "unavailable"
    assert any("not offered" in n for n in s["notes"])


def test_invalid_range_and_overlay_are_422(client: TestClient) -> None:
    assert client.get("/api/v1/market/series/KO", params={"range": "7Y"}).status_code == 422
    assert client.get("/api/v1/market/series/KO", params={"overlays": "bogus"}).status_code == 422


def test_no_real_money_route_exists(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert not [p for p in paths if "broker" in p or "live-trade" in p or "real" in p]
    assert client.get("/api/v1/system/status").json()["real_money_trading"] == "unavailable"


def test_balance_goal_end_to_end_with_replanning(client: TestClient) -> None:
    made = client.post(
        "/api/v1/goal-tracker",
        headers=H,
        json={
            "name": "Down payment",
            "basis": "target_balance",
            "target_value": "15000",
            "horizon_years": 4,
            "starting_capital": "10000",
        },
    )
    assert made.status_code == 201, made.text
    goal = made.json()
    assert goal["target_value"] == "15000.00" or goal["target_value"] == "15000"
    gid = goal["goal_id"]

    report = client.post(
        f"/api/v1/goal-tracker/{gid}/analyze", json={"assumed_annual_return_rate": 0.04}
    ).json()
    plan = report["plan"]
    assert plan["kind"] == "target_balance"
    assert plan["required_annual_return_rate"] == pytest.approx(1.5 ** (1 / 4) - 1, abs=1e-4)
    assert float(plan["required_monthly_contribution"]) > 0
    assert plan["replanned_from_today"] is False  # no portfolio attached: original plan

    portfolio = make_portfolio(client, "10000")
    attached = client.post(
        f"/api/v1/goal-tracker/{gid}/analyze",
        json={"assumed_annual_return_rate": 0.04, "portfolio_id": portfolio},
    ).json()
    assert attached["plan"]["capital"] is not None
    assert attached["progress"] is None or attached["progress"]["basis"] == "target_balance"


def test_withdrawal_goal_needs_its_inputs_and_reports_duration(client: TestClient) -> None:
    bad = client.post(
        "/api/v1/goal-tracker",
        headers=H,
        json={"name": "w", "basis": "sustainable_withdrawal", "horizon_years": 5},
    )
    assert bad.status_code == 422 and "withdrawal goal needs" in bad.json()["detail"]
    ok = client.post(
        "/api/v1/goal-tracker",
        headers=H,
        json={
            "name": "Retire",
            "basis": "sustainable_withdrawal",
            "monthly_withdrawal": "1000",
            "horizon_years": 5,
            "starting_capital": "60000",
        },
    )
    assert ok.status_code == 201, ok.text
    report = client.post(
        f"/api/v1/goal-tracker/{ok.json()['goal_id']}/analyze",
        json={"assumed_annual_return_rate": 0.0},
    ).json()
    assert report["plan"]["months_capital_lasts"] == 60
    assert report["plan"]["lasts_beyond_100_years"] is False
