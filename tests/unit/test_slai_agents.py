"""Optional SLAI agents: switches, Knowledge adapter, allocation maths and the Optimization adapter."""

from __future__ import annotations

import types as pytypes
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from slaifi.application.agents import AgentSwitches
from slaifi.application.contracts import AgentName, AllocationProblem
from slaifi.domain.strategies import get_preset
from slaifi.engines.allocation import (
    aligned_returns,
    allocation_bounds,
    annualised_statistics,
    portfolio_statistics,
    return_preference,
    verify_allocation,
)
from slaifi.infrastructure.persistence import SqliteFinanceStore
from slaifi.integrations.slai.knowledge import (
    ID_PREFIX,
    SlaiKnowledgeLibrary,
    chunk_markdown,
    load_documents,
)
from slaifi.integrations.slai.optimizer import (
    SlaiPortfolioOptimizer,
    build_problem,
    interpret,
    variable_name,
)


@pytest.fixture()
def store(tmp_path: Path) -> Any:
    s = SqliteFinanceStore(tmp_path / "f.db", backups_dir=tmp_path / "b")
    yield s
    s.close()


# ----------------------------------------------------------------------------- switches
def test_agents_are_off_until_switched_on_and_the_choice_is_stored_and_audited(store: Any) -> None:
    switches = AgentSwitches(store, {AgentName.KNOWLEDGE: False, AgentName.OPTIMIZATION: True})
    assert not switches.is_enabled("knowledge") and switches.is_enabled("optimization")
    assert switches.status("knowledge").state == "disabled"
    assert switches.status("optimization").state == "untested"

    switches.set_enabled("knowledge", True)
    assert switches.is_enabled("knowledge")
    # The person's choice wins over the configured default, including switching a default off.
    switches.set_enabled("optimization", False)
    assert not switches.is_enabled("optimization")
    again = AgentSwitches(store, {AgentName.OPTIMIZATION: True})  # e.g. after a restart
    assert again.is_enabled("knowledge") and not again.is_enabled("optimization")
    actions = [(e.action, e.subject) for e in store.list_audit(10)]
    assert ("agent.enabled", "agent:knowledge") in actions
    assert ("agent.disabled", "agent:optimization") in actions
    assert store.verify_audit_chain()[0]


def test_status_follows_how_the_last_use_went_and_a_new_choice_resets_it(store: Any) -> None:
    switches = AgentSwitches(store, {AgentName.LEARNING: True})
    switches.note_result("learning", False, "ImportError: torch")
    status = switches.status("learning")
    assert (status.state, status.detail) == ("unavailable", "ImportError: torch")
    switches.note_result("learning", True)
    assert switches.status("learning").state == "ready"
    switches.set_enabled("learning", True)
    assert switches.status("learning").state == "untested"


def test_nothing_is_enabled_when_slai_itself_is_switched_off(store: Any) -> None:
    switches = AgentSwitches(store, {AgentName.KNOWLEDGE: True}, slai_enabled=False)
    switches.set_enabled("knowledge", True)
    assert not switches.is_enabled("knowledge")
    assert "switched off" in (switches.status("knowledge").detail or "")
    with pytest.raises(KeyError):
        switches.is_enabled("nonsense")


# ---------------------------------------------------------------------------- knowledge
DOC = """# Title

Intro paragraph that is long enough to be kept as a passage of its own in the index.

## Short selling (simulated)

A short sells borrowed shares. The proceeds stay locked as collateral together with a further
half. Borrow fees and dividends owed are not modelled in this simulation at all.

```
# not a heading
```

## Tiny

x
"""


def test_markdown_is_cut_at_headings_and_tiny_or_code_lines_do_not_split_it() -> None:
    chunks = chunk_markdown(DOC, "docs/finance/methodology.md")
    headings = [h for _, h, _ in chunks]
    assert "Short selling (simulated)" in headings and "Tiny" not in headings
    body = next(b for _, h, b in chunks if h == "Short selling (simulated)")
    assert "# not a heading" in body  # inside a code fence: not a heading
    assert all(
        doc_id.startswith(ID_PREFIX + "docs/finance/methodology.md#") for doc_id, _, _ in chunks
    )


def test_long_sections_are_split_at_paragraph_breaks() -> None:
    text = "## Long\n\n" + "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(8))
    chunks = chunk_markdown(text, "docs/x.md")
    assert len(chunks) > 1 and all(len(b) <= 1200 for _, _, b in chunks)


class FakeKnowledgeAgent:
    """Stands in for SLAI's KnowledgeAgent: a shared index that also holds foreign documents."""

    def __init__(self) -> None:
        self.docs: list[dict[str, Any]] = [
            {"doc_id": "other:1", "text": "short selling in another product", "metadata": {}}
        ]
        self.added = 0

    def add_document(self, text: str, doc_id: str | None = None, metadata: Any = None) -> None:
        assert metadata["visibility"] == "public"  # SLAI's index refuses anything else
        self.docs.append({"doc_id": doc_id, "text": text, "metadata": dict(metadata)})
        self.added += 1

    def retrieve(self, query: str, k: int = 5) -> list[tuple[float, dict[str, Any]]]:
        words = set(query.lower().split())
        scored = [(float(len(words & set(d["text"].lower().split()))), d) for d in self.docs]
        return sorted((x for x in scored if x[0] > 0), key=lambda x: -x[0])[:k]


def _docs(tmp: Path) -> Path:
    root = tmp / "docs"
    (root / "finance").mkdir(parents=True, exist_ok=True)
    (root / "finance" / "methodology.md").write_text(DOC, encoding="utf-8")
    return root


def test_library_indexes_only_slaifis_guides_and_returns_only_those(tmp_path: Path) -> None:
    agent = FakeKnowledgeAgent()
    results: list[tuple[bool, str | None]] = []
    library = SlaiKnowledgeLibrary(
        lambda name: agent,
        _docs(tmp_path),
        enabled=lambda: True,
        report=lambda ok, detail: results.append((ok, detail)),
    )
    answer = library.search("short selling collateral")
    assert answer.status == "ok"
    (passage,) = answer.passages  # the foreign "other:1" document is filtered out
    assert passage.source == "docs/finance/methodology.md"
    assert passage.heading == "Short selling (simulated)"
    assert passage.text.startswith("A short sells borrowed shares")
    assert results == [(True, None)]
    library.search("collateral again")
    assert agent.added == 2  # indexed once, not on every search


def test_library_is_inert_when_off_and_honest_when_the_agent_fails(tmp_path: Path) -> None:
    calls: list[str] = []

    def provider(name: str) -> Any:
        calls.append(name)
        raise RuntimeError("no runtime")

    reported: list[tuple[bool, str | None]] = []
    off = SlaiKnowledgeLibrary(provider, _docs(tmp_path), enabled=lambda: False)
    assert off.search("short").status == "disabled" and calls == []

    on = SlaiKnowledgeLibrary(
        provider,
        _docs(tmp_path),
        enabled=lambda: True,
        report=lambda ok, d: reported.append((ok, d)),
    )
    answer = on.search("short selling")
    assert answer.status == "unavailable" and "no runtime" in (answer.detail or "")
    assert reported and reported[0][0] is False
    assert on.search("x").status == "no_match"  # too short to search, no agent call needed


def test_library_says_no_match_instead_of_inventing_an_answer(tmp_path: Path) -> None:
    library = SlaiKnowledgeLibrary(
        lambda n: FakeKnowledgeAgent(), _docs(tmp_path), enabled=lambda: True
    )
    answer = library.search("zebra giraffe")
    assert answer.status == "no_match" and answer.passages == ()


def test_missing_guides_make_the_agent_unavailable_not_silently_empty(tmp_path: Path) -> None:
    library = SlaiKnowledgeLibrary(
        lambda n: FakeKnowledgeAgent(), tmp_path / "nowhere", enabled=lambda: True
    )
    assert library.search("short selling").status == "unavailable"
    assert load_documents(tmp_path / "nowhere") == []


# ----------------------------------------------------------------------- allocation maths
def _closes(prices: list[float], start: date = date(2026, 1, 1)) -> list[tuple[date, float]]:
    return [(start + timedelta(days=i), p) for i, p in enumerate(prices)]


def test_returns_use_only_days_every_series_has_and_never_fill_a_gap() -> None:
    a = _closes([100, 110, 121, 133.1])
    b = [pt for pt in _closes([50, 55, 55, 60.5]) if pt[0] != date(2026, 1, 3)]  # a missing day
    out = aligned_returns({"A": a, "B": b})
    assert len(out["A"]) == len(out["B"]) == 2  # days 1, 2, 4 shared: two returns
    assert out["A"][0] == pytest.approx(0.10)
    assert out["A"][1] == pytest.approx(133.1 / 110 - 1)
    assert out["B"][0] == pytest.approx(0.10)
    with pytest.raises(ValueError):
        aligned_returns({"A": _closes([100, 0, 5])})


def test_statistics_are_annualised_sample_statistics() -> None:
    r = {"A": [0.01, -0.01, 0.02, 0.0], "B": [0.02, 0.0, 0.04, 0.0]}
    symbols, mean, cov = annualised_statistics(r)
    assert symbols == ("A", "B")
    assert mean[0] == pytest.approx(0.005 * 252)
    assert cov[0][1] == cov[1][0]
    assert cov[1][1] > cov[0][0]  # B moves more than A
    assert cov[0][0] == pytest.approx(0.0005 / 3 * 252)  # sample variance of A (n-1), annualised
    with pytest.raises(ValueError):
        annualised_statistics({"A": [0.1]})
    with pytest.raises(ValueError):
        annualised_statistics({"A": [0.1, 0.2], "B": [0.1]})


def test_bounds_come_from_the_strategy_and_return_preference_from_its_risk_tolerance() -> None:
    cautious = get_preset("capital_preservation")
    lower, upper, budget = allocation_bounds(cautious, 4)
    assert lower == (0.0,) * 4 and len(upper) == 4
    assert upper[0] == min(1.0, cautious.max_position_weight or 1.0)
    assert budget == pytest.approx(1.0 - cautious.cash_reserve_rate)
    assert return_preference(cautious, "steadiest") == 0.0
    bold = get_preset("short_term_hawkish")
    assert return_preference(bold, "strategy") > return_preference(cautious, "strategy") - 1e-12


COV = ((0.04, 0.0), (0.0, 0.09))
MU = (0.05, 0.10)


def _verify(weights: tuple[float, ...], strategy: Any, **kw: Any) -> dict[str, bool]:
    lower, upper, budget = allocation_bounds(strategy, 2)
    checks = verify_allocation(
        weights,
        expected_returns=MU,
        covariance=COV,
        lower=kw.get("lower", lower),
        upper=kw.get("upper", upper),
        budget=kw.get("budget", budget),
        strategy=strategy,
    )
    return {c.code: c.ok for c in checks}


def test_every_proposal_is_re_checked_against_the_strategy() -> None:
    strategy = get_preset("balanced_core")
    _, upper, budget = allocation_bounds(strategy, 2)
    good = (budget * 0.5, budget * 0.5)
    # Only meaningful when the cap lets two assets hold the budget; otherwise the bounds check says so.
    ok = _verify(good, strategy, upper=(1.0, 1.0))
    assert ok["finite"] and ok["position_bounds"] and ok["budget"]
    assert not _verify((budget + 0.2, -0.2), strategy, upper=(1.0, 1.0))["position_bounds"]
    assert not _verify((0.1, 0.1), strategy, upper=(1.0, 1.0))["budget"]
    assert not _verify((float("nan"), 0.5), strategy)["finite"]
    assert _verify((0.9,), strategy, upper=(1.0, 1.0)) == {
        "finite": True
    }  # wrong length stops early


def test_volatility_and_concentration_caps_are_enforced_independently() -> None:
    strategy = get_preset("capital_preservation")
    assert strategy.max_annualized_volatility == 0.15
    ret, vol = portfolio_statistics((0.0, 1.0), MU, COV)
    assert ret == pytest.approx(0.10) and vol == pytest.approx(0.30)
    # All-in on the 30 %-volatility asset breaches the 15 % cap; the 20 %-volatility one does not.
    assert not _verify((0.0, 1.0), strategy, upper=(1.0, 1.0), budget=1.0)["volatility_cap"]
    assert _verify((1.0, 0.0), strategy, upper=(1.0, 1.0), budget=1.0)["volatility_cap"] is False
    uncapped = replace(strategy, max_annualized_volatility=None)
    assert _verify((0.0, 1.0), uncapped, upper=(1.0, 1.0), budget=1.0)["volatility_cap"]

    # Concentration only counts once there are three holdings, as in the strategy engine.
    cov3 = ((0.01, 0, 0), (0, 0.01, 0), (0, 0, 0.01))
    spread = replace(strategy, max_annualized_volatility=None, max_concentration_hhi=0.5)

    def hhi_ok(weights: tuple[float, ...]) -> bool:
        checks = verify_allocation(
            weights,
            expected_returns=(0.0, 0.0, 0.0),
            covariance=cov3,
            lower=(0.0,) * 3,
            upper=(1.0,) * 3,
            budget=1.0,
            strategy=spread,
        )
        return next(c.ok for c in checks if c.code == "concentration")

    assert hhi_ok((1 / 3, 1 / 3, 1 / 3))
    assert not hhi_ok((0.9, 0.05, 0.05))


# -------------------------------------------------------------------- optimizer adapter
class _T:
    """A minimal stand-in for SLAI's optimization_types that records what it is given."""

    class VariableDomain:
        @staticmethod
        def real(lo: float, hi: float) -> tuple[str, float, float]:
            return ("real", lo, hi)

    ProblemClass = pytypes.SimpleNamespace(QP="QP")

    @staticmethod
    def Variable(name: str, domain: Any) -> tuple[str, Any]:  # noqa: N802
        return (name, domain)

    @staticmethod
    def Objective(name: str, linear: Any = None, quadratic: Any = None) -> dict[str, Any]:  # noqa: N802
        return {"name": name, "linear": linear, "quadratic": quadratic}

    @staticmethod
    def Constraint(name: str, sense: str, rhs: float, linear: Any) -> dict[str, Any]:  # noqa: N802
        return {"name": name, "sense": sense, "rhs": rhs, "linear": linear}

    @staticmethod
    def OptimizationProblem(
        name: str, variables: Any, objectives: Any, constraints: Any, **kw: Any
    ) -> dict[str, Any]:  # noqa: N802
        return {
            "name": name,
            "variables": variables,
            "objectives": objectives,
            "constraints": constraints,
            **kw,
        }


PROBLEM = AllocationProblem(
    ("BRK.B", "KO"),
    MU,
    ((0.04, 0.01), (0.01, 0.09)),
    (0.0, 0.0),
    (0.7, 0.7),
    1.0,
    risk_aversion=0.0,
)


def test_the_problem_uses_slais_literal_quadratic_convention_and_safe_variable_names() -> None:
    built = build_problem(_T, PROBLEM)
    names = [v[0] for v in built["variables"]]
    assert (
        names == ["w0", "w1"] == [variable_name(0), variable_name(1)]
    )  # "BRK.B" is not an identifier
    quad = built["objectives"][0]["quadratic"]
    # w'Σw = 0.04·w0² + 0.09·w1² + 2·0.01·w0·w1, each pair listed once
    assert quad == {("w0", "w0"): 0.04, ("w0", "w1"): 0.02, ("w1", "w1"): 0.09}
    assert built["objectives"][0]["linear"] == {}
    assert built["constraints"][0]["sense"] == "==" and built["constraints"][0]["rhs"] == 1.0
    assert built["problem_class"] == "QP"
    leaning = build_problem(
        _T,
        AllocationProblem(
            PROBLEM.symbols, MU, PROBLEM.covariance, PROBLEM.lower, PROBLEM.upper, 1.0, 2.0
        ),
    )
    assert leaning["objectives"][0]["linear"] == {"w0": -2.0 * 0.05, "w1": -2.0 * 0.10}


def _payload(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "status": "success",
        "success": True,
        "solution": {"solver": "scipy_quadratic", "decision_variables": {"w0": 0.6, "w1": 0.4}},
    }
    base.update(kw)
    return base


def test_only_a_clear_success_with_every_weight_becomes_a_solution() -> None:
    ok = interpret(_payload(), PROBLEM)
    assert ok.status == "ok" and ok.weights == (0.6, 0.4) and ok.solver == "scipy_quadratic"
    assert interpret("nonsense", PROBLEM).status == "failed"
    assert interpret(_payload(success=False, status="failed"), PROBLEM).status == "failed"
    infeasible = interpret(
        _payload(success=False, status="failed", solution={"feasibility": "infeasible"}), PROBLEM
    )
    assert infeasible.status == "infeasible"
    missing = _payload(solution={"solver": "s", "decision_variables": {"w0": 0.6}})
    assert interpret(missing, PROBLEM).status == "failed"
    not_finite = _payload(
        solution={"solver": "s", "decision_variables": {"w0": 0.6, "w1": float("nan")}}
    )
    assert interpret(not_finite, PROBLEM).status == "failed"
    assert interpret(_payload(solution={"solver": "s"}), PROBLEM).status == "failed"


def test_the_optimizer_is_inert_when_off_and_reports_a_broken_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import slaifi.integrations.slai.optimizer as module

    monkeypatch.setattr(module.importlib, "import_module", lambda name: _T)
    called: list[str] = []
    off = SlaiPortfolioOptimizer(lambda n: called.append(n), enabled=lambda: False)
    assert off.solve(PROBLEM).status == "disabled" and called == []

    reports: list[tuple[bool, str | None]] = []

    class Agent:
        def optimize(self, request: dict[str, Any]) -> dict[str, Any]:
            assert request["publish"] is False and request["time_limit_seconds"] > 0
            return _payload()

    working = SlaiPortfolioOptimizer(
        lambda n: Agent(), enabled=lambda: True, report=lambda ok, d: reports.append((ok, d))
    )
    assert working.solve(PROBLEM).weights == (0.6, 0.4) and reports == [(True, None)]

    def broken(name: str) -> Any:
        raise ImportError("No module named 'scipy'")

    failing = SlaiPortfolioOptimizer(
        broken, enabled=lambda: True, report=lambda ok, d: reports.append((ok, d))
    )
    result = failing.solve(PROBLEM)
    assert result.status == "unavailable" and "scipy" in (result.detail or "")
    assert reports[-1][0] is False


# ----------------------------------------------------------------------------- learning
from slaifi.application.contracts import LearningOutcome  # noqa: E402
from slaifi.integrations.slai.learning import (  # noqa: E402
    MAX_PER_CALL,
    SlaiLearningMemory,
    signal_for,
    summarise,
)


def _outcome(n: int = 1, *, action: str = "BUY", value: float = 0.04) -> LearningOutcome:
    return LearningOutcome(
        outcome_id=f"R-{n}",
        action=action,
        symbol="KO",
        asset_class="equity",
        strategy_id="default",
        horizon_trading_days=20,
        forward_return=value,
        correct=value > 0,
        data_source="twelvedata",
        evaluated_at="2026-11-01T10:00:00+00:00",
    )


class FakeLearningAgent:
    """Mimics the real agent's contract: ``observe`` ingests (duplicates reported), ``query`` echoes."""

    def __init__(self) -> None:
        self.signals: dict[str, dict[str, object]] = {}
        self.calls: list[dict[str, object]] = []

    def perform_task(self, task: dict[str, object]) -> dict[str, object]:
        self.calls.append(task)
        if task["mode"] == "observe":
            signal = dict(task["signal"])  # type: ignore[call-overload]
            if signal["kind"] != "outcome":
                raise ValueError("bad kind")
            if signal["signal_id"] in self.signals:
                return {"status": "ok", "learning": {"status": "duplicate"}}
            self.signals[str(signal["signal_id"])] = signal
            return {"status": "ok", "learning": {"status": "recorded"}}
        if task["mode"] == "query":
            rows = [s for s in self.signals.values() if s["source_agent"] == task["source_agent"]]
            return {"status": "ok", "count": len(rows), "signals": list(reversed(rows))}
        raise AssertionError(task)


def test_an_outcome_becomes_an_unvalidated_evidence_signal() -> None:
    signal = signal_for(_outcome(7, action="SHORT", value=-0.02))
    assert signal["signal_id"] == "slaifi:outcome:R-7"
    assert signal["kind"] == "outcome" and signal["metric"] == "forward_return"
    assert signal["value"] == -0.02 and signal["strategy"] == "SHORT"
    # Evidence only: it must never be able to train the agent's strategy selector or its rewards.
    assert signal["validated"] is False and signal["metric"] != "reward"
    assert signal["context"] == {
        "app": "slaifi",
        "asset_class": "equity",
        "horizon_trading_days": 20,
    }


def test_learning_memory_is_inert_while_off() -> None:
    def provider(name: str) -> object:
        raise AssertionError("must not start an agent while switched off")

    memory = SlaiLearningMemory(provider, enabled=lambda: False)
    assert memory.share((_outcome(),)).status == "disabled"
    assert memory.recall().status == "disabled"


def test_sharing_sends_once_and_reports_repeats_as_duplicates() -> None:
    agent = FakeLearningAgent()
    results: list[tuple[bool, str | None]] = []
    memory = SlaiLearningMemory(
        lambda name: agent, report=lambda ok, detail: results.append((ok, detail))
    )
    outcomes = (_outcome(1), _outcome(2, action="SELL", value=-0.05))
    first = memory.share(outcomes)
    assert (first.status, first.sent, first.duplicates) == ("ok", 2, 0)
    again = memory.share(outcomes)
    assert (again.status, again.sent, again.duplicates) == ("ok", 0, 2)
    assert results[-1] == (True, None)
    assert memory.share(()).status == "nothing_to_share"


def test_a_signal_the_agent_refuses_does_not_stop_the_rest() -> None:
    class Picky(FakeLearningAgent):
        def perform_task(self, task: dict[str, object]) -> dict[str, object]:
            if task["mode"] == "observe" and task["signal"]["signal_id"].endswith("R-2"):  # type: ignore[index]
                raise ValueError("rejected")
            return super().perform_task(task)

    share = SlaiLearningMemory(lambda name: Picky()).share((_outcome(1), _outcome(2), _outcome(3)))
    assert (share.status, share.sent, share.refused) == ("ok", 2, 1)


def test_a_large_backlog_is_sent_in_bounded_batches_and_says_so() -> None:
    agent = FakeLearningAgent()
    share = SlaiLearningMemory(lambda name: agent).share(
        tuple(_outcome(i) for i in range(MAX_PER_CALL + 5))
    )
    assert share.sent == MAX_PER_CALL and share.detail and "share again" in share.detail


def test_a_missing_runtime_is_reported_not_raised() -> None:
    seen: list[tuple[bool, str | None]] = []

    def provider(name: str) -> object:
        raise ModuleNotFoundError("No module named 'torch'")

    memory = SlaiLearningMemory(provider, report=lambda ok, detail: seen.append((ok, detail)))
    share, recall = memory.share((_outcome(),)), memory.recall()
    assert share.status == "unavailable" and "torch" in (share.detail or "")
    assert recall.status == "unavailable" and "torch" in (recall.detail or "")
    assert seen and seen[-1][0] is False


def test_recall_summarises_only_what_slaifi_sent() -> None:
    agent = FakeLearningAgent()
    memory = SlaiLearningMemory(lambda name: agent)
    assert memory.recall().status == "empty"
    memory.share(
        (_outcome(1, value=0.04), _outcome(2, value=0.02), _outcome(3, action="SELL", value=-0.03))
    )
    recall = memory.recall()
    assert recall.status == "ok" and recall.total == 3
    rows = {r.action: r for r in recall.by_action}
    assert rows["BUY"].count == 2 and rows["BUY"].mean_forward_return == pytest.approx(0.03)
    assert rows["SELL"].count == 1


def test_summarise_skips_other_sources_and_malformed_rows() -> None:
    good = {"source_agent": "slaifi", "metric": "forward_return", "strategy": "BUY", "value": 0.1}
    total, rows = summarise(
        [
            good,
            {**good, "source_agent": "someone-else"},
            {**good, "metric": "reward"},
            {**good, "value": float("nan")},
            {**good, "value": True},
            {**good, "strategy": None},
            "junk",  # type: ignore[list-item]
        ]
    )
    assert total == 1 and rows[0].action == "BUY"
