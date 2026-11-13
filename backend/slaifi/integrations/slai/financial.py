"""Adapter from SLAIFI's allocation port to SLAI's Financial agent.

SLAIFI hands the agent real daily closes (with where they came from); the agent estimates the
historical moments, solves the mean-variance problem through SLAI's Optimization agent and returns
weights. SLAIFI neither re-implements the optimizer nor the moment estimation: it translates the
strategy's limits into the agent's request and then re-checks the answer itself (the caller's
``verify_allocation``), because the result is advice and the person decides.

Mapping of SLAIFI's problem onto the agent's (fully invested, uniform bounds) one:

* The strategy keeps ``cash reserve`` uninvested, so only ``budget = 1 − reserve`` is allocated.
  The agent finds fully invested weights ``v`` and SLAIFI reports ``w = budget · v`` with the cap
  per position divided by the budget so that ``w`` respects the cap.
* SLAIFI minimises ``w'Σw − λ·μ'w``; the agent minimises ``γ·v'Σv − μ'v``. Substituting
  ``w = b·v`` gives ``γ = b / λ``. "Steadiest" (λ = 0) is a very large γ, which makes the return
  term negligible.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Any

from logs.logger import get_logger

from slaifi.application.contracts import AllocationProblem, AllocationSolution

logger = get_logger("SLAIFI SLAI Financial")

PERIODS_PER_YEAR = 252
INGEST_CHUNK = 1000
STEADIEST_RISK_AVERSION = Decimal("1000000")
_FAILED_STATUSES = {"failed", "error", "partial"}


def _day(day: Any) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def _fixed(value: float) -> str:
    return format(Decimal(repr(float(value))), "f")


def observation_requests(problem: AllocationProblem) -> Iterator[dict[str, Any]]:
    """The agent's ``data.ingest_observations`` requests for the real closes SLAIFI holds.

    ``retrieved_at`` is the observation time: re-sending the same closes later changes nothing in
    the agent's store, so repeated suggestions do not pile up copies.
    """

    batch: list[dict[str, Any]] = []
    for series in problem.series:
        for day, close in series.closes:
            moment = _day(day).isoformat()
            batch.append(
                {
                    "instrument_id": series.symbol,
                    "field_name": "close",
                    "value": format(close, "f"),
                    "observed_at": moment,
                    "currency": series.currency,
                    "source": {"source_id": series.source, "retrieved_at": moment},
                }
            )
            if len(batch) >= INGEST_CHUNK:
                yield _ingest(batch)
                batch = []
    if batch:
        yield _ingest(batch)


def _ingest(observations: list[dict[str, Any]]) -> dict[str, Any]:
    return {"operation": "data.ingest_observations", "parameters": {"observations": observations}}


def optimize_request(problem: AllocationProblem, as_of: datetime) -> dict[str, Any]:
    """The agent's ``portfolio.optimize_allocation`` request for SLAIFI's allocation problem."""

    budget = problem.budget
    if budget <= 0:
        raise ValueError("nothing to invest: the strategy's cash reserve leaves no budget")
    days = [day for series in problem.series for day, _ in series.closes]
    if not days:
        raise ValueError("no price history was supplied")
    cap = min(1.0, max(problem.upper) / budget)
    gamma = (
        Decimal(repr(budget / problem.risk_aversion))
        if problem.risk_aversion > 0
        else STEADIEST_RISK_AVERSION
    )
    return {
        "operation": "portfolio.optimize_allocation",
        "parameters": {
            "instrument_ids": list(problem.symbols),
            "from_time": _day(min(days)).isoformat(),
            "until_time": _day(max(days)).isoformat(),
            "as_of": as_of.isoformat(),
            "periods_per_year": PERIODS_PER_YEAR,
            "risk_aversion": format(gamma, "f"),
            "min_weight": _fixed(min(problem.lower) / budget),
            "max_weight": _fixed(cap),
        },
        "request_id": f"slaifi-alloc-{uuid.uuid4().hex[:12]}",
    }


def failure_text(envelope: Mapping[str, Any]) -> str:
    error = envelope.get("error")
    if isinstance(error, Mapping) and error.get("message"):
        return str(error["message"])
    return f"status {envelope.get('status', 'unknown')}"


def interpret(envelope: Any, problem: AllocationProblem) -> AllocationSolution:
    """Turn the agent's answer into weights over the budget, refusing anything unclear."""

    if not isinstance(envelope, Mapping):
        return AllocationSolution("failed", detail="The Financial agent returned no result.")
    status = str(envelope.get("status", "")).lower()
    if not envelope.get("success") or status in _FAILED_STATUSES:
        text = failure_text(envelope)
        kind = "infeasible" if "admit no" in text or "infeasible" in text.lower() else "failed"
        return AllocationSolution(
            kind, detail=f"The Financial agent could not allocate: {text}"[:400]
        )
    result = envelope.get("result")
    weights = result.get("weights") if isinstance(result, Mapping) else None
    solver_info = result.get("solver") if isinstance(result, Mapping) else None
    solver = solver_info.get("solver") if isinstance(solver_info, Mapping) else None
    if not isinstance(weights, Mapping):
        return AllocationSolution("failed", solver=solver, detail="The result held no weights.")
    scaled: list[float] = []
    for symbol in problem.symbols:
        raw = weights.get(symbol)
        try:
            value = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            value = math.nan
        if not math.isfinite(value):
            return AllocationSolution("failed", solver=solver, detail="A weight was missing.")
        scaled.append(value * problem.budget)
    advisory = tuple(str(w) for w in (envelope.get("warnings") or ()))
    return AllocationSolution("ok", tuple(scaled), solver=solver, warnings=advisory)


class SlaiFinancialAgent:
    """Allocate with SLAI's Financial agent; degrades to "unavailable" instead of failing the app."""

    def __init__(
        self,
        agent_provider: Callable[[str], Any],
        *,
        enabled: Callable[[], bool],
        report: Callable[[bool, str | None], None] | None = None,
        agent_type: str = "financial",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._agent_provider = agent_provider
        self._enabled = enabled
        self._report = report or (lambda ok, detail: None)
        self._agent_type = agent_type
        self._clock = clock or (lambda: datetime.now(UTC))

    def _perform(self, agent: Any, request: Mapping[str, Any]) -> Mapping[str, Any]:
        envelope = agent.perform_task(dict(request))
        if not isinstance(envelope, Mapping):
            raise RuntimeError("the agent returned no result")
        return envelope

    def solve(self, problem: AllocationProblem) -> AllocationSolution:
        if not self._enabled():
            return AllocationSolution("disabled", detail="The Financial agent is switched off.")
        try:
            request_ = optimize_request(problem, self._clock())
        except ValueError as exc:
            return AllocationSolution("failed", detail=str(exc))
        try:
            agent = self._agent_provider(self._agent_type)
            for request in observation_requests(problem):
                stored = self._perform(agent, request)
                if not stored.get("success"):
                    raise RuntimeError(
                        f"it did not accept the price history: {failure_text(stored)}"
                    )
            envelope = self._perform(agent, request_)
        except Exception as exc:  # noqa: BLE001 - an unavailable agent must not break the app
            detail = f"{type(exc).__name__}: {exc}"[:240]
            logger.warning("SLAI financial agent unavailable: %s", detail)
            self._report(False, detail)
            return AllocationSolution(
                "unavailable", detail=f"The Financial agent is not available ({detail})."
            )
        result = interpret(envelope, problem)
        # An agent that ran but found no allocation is a correct answer, not a broken agent.
        self._report(True, None)
        return result

    def check(self) -> None:
        """Start the agent and run a read-only request. Sends no market data."""

        try:
            agent = self._agent_provider(self._agent_type)
            envelope = self._perform(agent, {"operation": "data.counts", "parameters": {}})
            if not envelope.get("success"):
                raise RuntimeError(failure_text(envelope))
        except Exception as exc:
            self._report(False, f"{type(exc).__name__}: {exc}"[:240])
            raise
        self._report(True, None)


__all__: Sequence[str] = ["SlaiFinancialAgent"]
