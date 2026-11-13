"""Optional SLAI agents over HTTP: opt-in switches, Knowledge look-ups and allocation suggestions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from tests.api.test_finance_api import H, create_app, make_portfolio

from slaifi.application.contracts import (
    AllocationProblem,
    AllocationSolution,
    KnowledgeAnswer,
    KnowledgePassage,
    LearningActionSummary,
    LearningRecall,
    LearningShare,
)
from slaifi.core.config.settings import Settings


class CappedEqualWeights:
    """A stand-in Financial agent: equal weights within the caps. It records what it was asked."""

    def __init__(self, *, weights: tuple[float, ...] | None = None, status: str = "ok") -> None:
        self.fixed = weights
        self.status = status
        self.problems: list[AllocationProblem] = []

    def check(self) -> None:
        self.problems.append(AllocationProblem((), (), (), (), (), 1.0))

    def solve(self, problem: AllocationProblem) -> AllocationSolution:
        self.problems.append(problem)
        if self.status != "ok":
            return AllocationSolution(self.status, detail="stand-in refusal")
        n = len(problem.symbols)
        weights = self.fixed or tuple(min(problem.upper[0], problem.budget / n) for _ in range(n))
        return AllocationSolution("ok", weights, solver="stand-in")


class FixedLibrary:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, limit: int = 5) -> KnowledgeAnswer:
        self.queries.append(query)
        return KnowledgeAnswer(
            "ok", (KnowledgePassage("docs/finance/methodology.md", "Short selling", "text", 1.0),)
        )


def app_client(tmp: Path, **kw: Any) -> Any:
    # The shared helper switches SLAI off; the agents' master switch needs it on.
    cfg = Settings(environment="test", data_dir=tmp / "d", slai_enabled=True)
    return TestClient(create_app(cfg, **kw), raise_server_exceptions=False)


def buy(c: TestClient, pid: str, symbol: str, qty: str) -> None:
    r = c.post(
        f"/api/v1/paper/portfolios/{pid}/orders",
        headers=H,
        json={"symbol": symbol, "side": "buy", "quantity": qty},
    )
    assert r.json()["decision"]["status"] == "filled", r.text


def loosen(c: TestClient, cap: float = 0.4, **more: Any) -> None:
    """The default 10% cap and 0.15 concentration limit need many holdings; tests use a few, so widen them."""
    r = c.patch(
        "/api/v1/strategies/default",
        headers=H,
        json={
            "fields": {"max_position_weight": cap, "max_concentration_hhi": 0.5, **more},
            "acknowledge_loosening": True,
        },
    )
    assert r.status_code == 200, r.text


def enable(c: TestClient, name: str) -> None:
    r = c.put(f"/api/v1/system/agents/{name}", headers=H, json={"enabled": True})
    assert r.status_code == 200 and r.json()["enabled"] is True, r.text


# ----------------------------------------------------------------------------- switches
def test_every_optional_agent_starts_off_and_switching_needs_the_client_header(
    tmp_path: Path,
) -> None:
    with app_client(
        tmp_path, knowledge_library=FixedLibrary(), financial_analyst=CappedEqualWeights()
    ) as c:
        listing = c.get("/api/v1/system/agents").json()
        assert [a["name"] for a in listing["agents"]] == ["knowledge", "financial", "learning"]
        assert all(a["enabled"] is False and a["state"] == "disabled" for a in listing["agents"])
        assert "advise" in listing["note"]

        assert c.put("/api/v1/system/agents/knowledge", json={"enabled": True}).status_code == 403
        assert (
            c.put("/api/v1/system/agents/nonsense", headers=H, json={"enabled": True}).status_code
            == 404
        )
        assert (
            c.put("/api/v1/system/agents/knowledge", headers=H, json={"enabled": "x"}).status_code
            == 422
        )

        status = c.put("/api/v1/system/agents/knowledge", headers=H, json={"enabled": True}).json()
        assert status["enabled"] and status["state"] == "untested"
        audit = c.get("/api/v1/system/audit", params={"subject": "agent:knowledge"}).json()
        assert [e["action"] for e in audit["entries"]] == ["agent.enabled"]
        off = c.put("/api/v1/system/agents/knowledge", headers=H, json={"enabled": False}).json()
        assert off["state"] == "disabled"


def test_a_first_start_default_can_come_from_configuration(tmp_path: Path) -> None:
    s = Settings(
        environment="test", data_dir=tmp_path / "d", slai_enabled=True, slai_knowledge_enabled=True
    )
    with TestClient(create_app(s, knowledge_library=FixedLibrary())) as c:
        states = {a["name"]: a["enabled"] for a in c.get("/api/v1/system/agents").json()["agents"]}
        assert states == {"knowledge": True, "financial": False, "learning": False}


def test_check_starts_only_agents_that_are_switched_on(tmp_path: Path) -> None:
    library, optimizer = FixedLibrary(), CappedEqualWeights()
    with app_client(tmp_path, knowledge_library=library, financial_analyst=optimizer) as c:
        assert (
            c.post("/api/v1/system/agents/knowledge/check", headers=H).json()["state"] == "disabled"
        )
        assert library.queries == []
        enable(c, "knowledge")
        enable(c, "financial")
        assert c.post("/api/v1/system/agents/knowledge/check", headers=H).status_code == 200
        assert c.post("/api/v1/system/agents/financial/check", headers=H).status_code == 200
        assert library.queries == ["strategy"] and len(optimizer.problems) == 1
        assert c.post("/api/v1/system/agents/knowledge/check").status_code == 403


# ---------------------------------------------------------------------------- knowledge
def test_knowledge_search_answers_only_when_switched_on(tmp_path: Path) -> None:
    library = FixedLibrary()
    with app_client(tmp_path, knowledge_library=library) as c:
        found = c.get("/api/v1/knowledge/search", params={"q": "short selling"}).json()
        assert found["status"] == "ok" and found["passages"][0]["source"].endswith("methodology.md")
        assert c.get("/api/v1/knowledge/search", params={"q": "x"}).status_code == 422


def test_the_real_library_is_off_until_enabled_and_never_invents_an_answer(tmp_path: Path) -> None:
    with app_client(tmp_path) as c:  # SLAI itself is not running here: honest "unavailable"
        assert (
            c.get("/api/v1/knowledge/search", params={"q": "short selling"}).json()["status"]
            == "disabled"
        )
        enable(c, "knowledge")
        answer = c.get("/api/v1/knowledge/search", params={"q": "short selling"}).json()
        assert answer["status"] == "unavailable" and answer["passages"] == []
        agents = {a["name"]: a for a in c.get("/api/v1/system/agents").json()["agents"]}
        assert agents["knowledge"]["state"] == "unavailable" and agents["knowledge"]["detail"]


# -------------------------------------------------------------------------- allocation
def test_allocation_is_off_until_the_agent_is_switched_on_and_fetches_nothing_when_off(
    tmp_path: Path,
) -> None:
    optimizer = CappedEqualWeights()
    with app_client(tmp_path, financial_analyst=optimizer) as c:
        pid = make_portfolio(c)
        got = c.get(f"/api/v1/paper/portfolios/{pid}/allocation").json()
        assert got["status"] == "disabled" and got["lines"] == [] and optimizer.problems == []
        assert (
            c.get(f"/api/v1/paper/portfolios/{pid}/allocation", params={"focus": "x"}).status_code
            == 422
        )
        assert c.get("/api/v1/paper/portfolios/P-nope/allocation").status_code == 404


def test_a_suggestion_compares_with_the_current_mix_and_is_checked_by_slaifi(
    tmp_path: Path,
) -> None:
    optimizer = CappedEqualWeights()
    with app_client(tmp_path, financial_analyst=optimizer) as c:
        loosen(c)
        pid = make_portfolio(c, "20000")
        for symbol, qty in (("KO", "30"), ("JNJ", "10"), ("SPY", "5"), ("DIA", "5")):
            buy(c, pid, symbol, qty)
        enable(c, "financial")
        got = c.get(f"/api/v1/paper/portfolios/{pid}/allocation").json()
        assert got["status"] == "ok", got
        assert got["observations"] >= 60 and got["window_start"] < got["window_end"]
        assert "not a forecast" in got["basis"]
        lines = {line["symbol"]: line for line in got["lines"]}
        assert set(lines) == {"KO", "JNJ", "SPY", "DIA"}
        assert sum(line["suggested_weight"] for line in got["lines"]) == pytest.approx(
            1.0 - got["cash_weight"]
        )
        assert all(c_["ok"] for c_ in got["checks"]) and {c_["code"] for c_ in got["checks"]} >= {
            "finite",
            "position_bounds",
            "budget",
            "volatility_cap",
            "concentration",
        }
        for line in got["lines"]:
            assert (
                float(line["amount"]) * (line["change"]) >= 0
            )  # the money follows the weight change
        assert got["suggested"]["annual_volatility"] > 0 and got["current"]["annual_volatility"] > 0
        assert set(optimizer.problems[0].symbols) == set(lines)
        assert got["solver"] == "stand-in"
        # Whatever it says, nothing was ordered.
        assert (
            len(c.get(f"/api/v1/paper/portfolios/{pid}/history").json()["entries"]) == 5
        )  # 4 buys + start


def test_a_proposal_that_breaks_a_limit_is_refused_not_shown(tmp_path: Path) -> None:
    with app_client(
        tmp_path, financial_analyst=CappedEqualWeights(weights=(0.9, 0.9, 0.9, 0.9))
    ) as c:
        loosen(c)
        pid = make_portfolio(c, "20000")
        for symbol in ("KO", "JNJ", "SPY", "DIA"):
            buy(c, pid, symbol, "5")
        enable(c, "financial")
        got = c.get(f"/api/v1/paper/portfolios/{pid}/allocation").json()
        assert got["status"] == "rejected" and got["lines"] == []
        assert "did not accept" in got["detail"]
        failed = [x for x in got["checks"] if not x["ok"]]
        assert {x["code"] for x in failed} >= {"position_bounds", "budget"}


def test_a_missing_or_failing_optimizer_is_reported_as_it_is(tmp_path: Path) -> None:
    for status in ("unavailable", "infeasible", "failed"):
        with app_client(
            tmp_path / status, financial_analyst=CappedEqualWeights(status=status)
        ) as c:
            loosen(c)
            pid = make_portfolio(c, "20000")
            for symbol in ("KO", "JNJ", "SPY", "DIA"):
                buy(c, pid, symbol, "5")
            enable(c, "financial")
            got = c.get(f"/api/v1/paper/portfolios/{pid}/allocation").json()
            expected = status if status != "failed" else "unavailable"
            assert got["status"] == expected and got["lines"] == [] and "stand-in" in got["detail"]


def test_too_little_to_work_with_says_so_and_unknown_symbols_are_excluded(tmp_path: Path) -> None:
    with app_client(tmp_path, financial_analyst=CappedEqualWeights()) as c:
        loosen(c)
        pid = make_portfolio(c, "20000")
        buy(c, pid, "KO", "5")
        enable(c, "financial")
        got = c.get(
            f"/api/v1/paper/portfolios/{pid}/allocation", params={"symbols": "NOSUCH"}
        ).json()
        assert got["status"] == "insufficient_data" and got["lines"] == []
        assert any(e["symbol"] == "NOSUCH" for e in got["excluded"])
        with_extra = c.get(
            f"/api/v1/paper/portfolios/{pid}/allocation", params={"symbols": "JNJ, SPY, DIA"}
        ).json()
        assert with_extra["status"] == "ok" and len(with_extra["lines"]) == 4
        assert {line["symbol"] for line in with_extra["lines"]} == {"KO", "JNJ", "SPY", "DIA"}


def test_too_few_holdings_for_the_position_cap_is_infeasible_and_says_how_many_are_needed(
    tmp_path: Path,
) -> None:
    optimizer = CappedEqualWeights()
    with app_client(tmp_path, financial_analyst=optimizer) as c:
        pid = make_portfolio(c, "20000")  # default strategy: 10% cap per position
        for symbol in ("KO", "JNJ", "SPY"):
            buy(c, pid, symbol, "5")
        enable(c, "financial")
        got = c.get(f"/api/v1/paper/portfolios/{pid}/allocation").json()
        assert got["status"] == "infeasible" and got["lines"] == [] and optimizer.problems == []
        assert "cap" in got["detail"].lower() or "at least" in got["detail"].lower()


def test_assets_the_strategy_forbids_are_left_out_with_the_reason(tmp_path: Path) -> None:
    with app_client(tmp_path, financial_analyst=CappedEqualWeights()) as c:
        loosen(c, 0.6)
        pid = make_portfolio(c, "20000")
        for symbol in ("KO", "JNJ", "SPY", "DIA"):
            buy(c, pid, symbol, "5")
        patch = c.patch(
            "/api/v1/strategies/default", headers=H, json={"fields": {"excluded_symbols": ["JNJ"]}}
        )
        assert patch.status_code == 200, patch.text
        enable(c, "financial")
        got = c.get(f"/api/v1/paper/portfolios/{pid}/allocation").json()
        assert {line["symbol"] for line in got["lines"]} == {"KO", "SPY", "DIA"}, got
        assert any(e["symbol"].endswith("JNJ") and e["reason"] for e in got["excluded"])


# ---------------------------------------------------------------------------- learning
class FixedMemory:
    def __init__(self) -> None:
        self.shared: list[tuple[Any, ...]] = []

    def share(self, outcomes: tuple[Any, ...]) -> LearningShare:
        self.shared.append(outcomes)
        return LearningShare("ok", sent=len(outcomes))

    def recall(self, limit: int = 500) -> LearningRecall:
        return LearningRecall("ok", 1, (LearningActionSummary("BUY", 1, 0.07),))


def score_one(c: TestClient) -> None:
    from datetime import UTC, datetime, timedelta
    from decimal import Decimal

    from slaifi.domain.learning import RecommendationRecord

    c.app.state.finance_store.log_recommendation(  # type: ignore[attr-defined]
        RecommendationRecord(
            record_id="R-old",
            symbol="SPY",
            asset_class="etf",
            action="BUY",
            strategy_id="x",
            issued_at=datetime.now(UTC) - timedelta(days=60),
            reference_price=Decimal("1.00"),
        )
    )
    assert (
        c.post("/api/v1/learning/track-record/refresh", headers=H).json()["refresh"]["evaluated"]
        == 1
    )


def test_learning_shares_only_checked_outcomes_and_only_when_switched_on(tmp_path: Path) -> None:
    memory = FixedMemory()
    with app_client(tmp_path, learning_memory=memory) as c:
        score_one(c)
        assert c.post("/api/v1/learning/slai-memory/share").status_code == 403
        enable(c, "learning")
        shared = c.post("/api/v1/learning/slai-memory/share", headers=H).json()
        assert shared["status"] == "ok" and shared["sent"] == 1
        (batch,) = memory.shared
        assert [o.outcome_id for o in batch] == ["R-old"] and batch[0].action == "BUY"
        assert batch[0].forward_return > 0 and batch[0].correct is True
        recalled = c.get("/api/v1/learning/slai-memory").json()
        assert recalled["total"] == 1 and recalled["by_action"][0]["action"] == "BUY"
        assert c.post("/api/v1/system/agents/learning/check", headers=H).status_code == 200


def test_unscored_recommendations_are_never_shared(tmp_path: Path) -> None:
    memory = FixedMemory()
    with app_client(tmp_path, learning_memory=memory) as c:
        assert c.get("/api/v1/recommendations/SPY").status_code == 200  # logged, not yet scored
        enable(c, "learning")
        c.post("/api/v1/learning/slai-memory/share", headers=H)
        assert memory.shared == [()]


def test_the_real_learning_adapter_is_off_by_default_and_honest_when_slai_is_missing(
    tmp_path: Path,
) -> None:
    with app_client(tmp_path) as c:
        score_one(c)
        assert (
            c.post("/api/v1/learning/slai-memory/share", headers=H).json()["status"] == "disabled"
        )
        assert c.get("/api/v1/learning/slai-memory").json()["status"] == "disabled"
        enable(c, "learning")
        got = c.post("/api/v1/learning/slai-memory/share", headers=H).json()
        assert got["status"] == "unavailable" and got["sent"] == 0 and got["detail"]
        agents = {a["name"]: a for a in c.get("/api/v1/system/agents").json()["agents"]}
        assert agents["learning"]["state"] == "unavailable"
        # SLAIFI's own measurement is untouched by any of this.
        assert c.get("/api/v1/learning/track-record").json()["scored"] == 1
