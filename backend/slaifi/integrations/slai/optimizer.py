"""Adapter from SLAIFI's allocation port to SLAI's OptimizationAgent.

SLAIFI states the problem (a bounded quadratic: minimise variance, optionally leaning towards past
return) and SLAI's solver finds the weights. The result is advice: the caller re-checks it against
the strategy and the person decides whether to act on it.
"""

from __future__ import annotations

import importlib
import math
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from logs.logger import get_logger

from slaifi.application.contracts import AllocationProblem, AllocationSolution

logger = get_logger("SLAIFI SLAI Optimization")

TYPES_MODULE = "src.agents.optimization.optimization_types"
SOLVER_TIMEOUT_SECONDS = 20.0
_FAILED_STATUSES = {"failed", "error", "infeasible", "unbounded", "invalid"}


def variable_name(index: int) -> str:
    """Solver variable names must be identifiers; the symbol itself may not be (e.g. ``BRK.B``)."""

    return f"w{index}"


def build_problem(types: Any, problem: AllocationProblem) -> Any:
    """Build SLAI's OptimizationProblem for ``w'Σw − λ·μ'w``, Σw = budget, lower ≤ w ≤ upper."""

    n = len(problem.symbols)
    names = [variable_name(i) for i in range(n)]
    variables = tuple(
        types.Variable(names[i], types.VariableDomain.real(problem.lower[i], problem.upper[i]))
        for i in range(n)
    )
    # SLAI stores *literal* coefficients c·xi·xj, so a symmetric covariance contributes σii on the
    # diagonal and 2σij once per pair.
    quadratic: dict[tuple[str, str], float] = {}
    for i in range(n):
        quadratic[(names[i], names[i])] = problem.covariance[i][i]
        for j in range(i + 1, n):
            quadratic[(names[i], names[j])] = 2.0 * problem.covariance[i][j]
    linear = (
        {names[i]: -problem.risk_aversion * problem.expected_returns[i] for i in range(n)}
        if problem.risk_aversion > 0
        else {}
    )
    objective = types.Objective("portfolio_variance", linear=linear, quadratic=quadratic)
    budget = types.Constraint(
        "budget", sense="==", rhs=problem.budget, linear={name: 1.0 for name in names}
    )
    return types.OptimizationProblem(
        "slaifi_allocation",
        variables,
        (objective,),
        (budget,),
        problem_class=types.ProblemClass.QP,
        known_convex=True,
    )


def interpret(payload: Any, problem: AllocationProblem) -> AllocationSolution:
    """Turn the agent's result into weights, refusing anything that is not clearly a success."""

    if not isinstance(payload, Mapping):
        return AllocationSolution("failed", detail="The Optimization agent returned no result.")
    solution = payload.get("solution")
    status = str(payload.get("status", "")).lower()
    solver = solution.get("solver") if isinstance(solution, Mapping) else None
    if not payload.get("success") or status in _FAILED_STATUSES:
        reason = None
        if isinstance(solution, Mapping):
            reason = solution.get("termination_reason") or solution.get("feasibility")
        warnings = payload.get("warnings") or ()
        detail = f"The solver did not find a solution (status {status or 'unknown'}"
        detail += f", {reason})." if reason else ")."
        if warnings:
            detail += " " + "; ".join(str(w) for w in list(warnings)[:2])
        kind = "infeasible" if "infeasible" in f"{status} {reason}".lower() else "failed"
        return AllocationSolution(kind, solver=solver, detail=detail[:400])
    variables = solution.get("decision_variables") if isinstance(solution, Mapping) else None
    if not isinstance(variables, Mapping):
        return AllocationSolution("failed", solver=solver, detail="The result held no weights.")
    weights: list[float] = []
    for index in range(len(problem.symbols)):
        value = variables.get(variable_name(index))
        if value is None or not math.isfinite(float(value)):
            return AllocationSolution("failed", solver=solver, detail="A weight was missing.")
        weights.append(float(value))
    return AllocationSolution("ok", tuple(weights), solver=solver)


class SlaiPortfolioOptimizer:
    """Solve an allocation with SLAI's OptimizationAgent; degrades to "unavailable"."""

    def __init__(
        self,
        agent_provider: Callable[[str], Any],
        *,
        enabled: Callable[[], bool],
        report: Callable[[bool, str | None], None] | None = None,
        agent_type: str = "optimization",
    ) -> None:
        self._agent_provider = agent_provider
        self._enabled = enabled
        self._report = report or (lambda ok, detail: None)
        self._agent_type = agent_type

    def solve(self, problem: AllocationProblem) -> AllocationSolution:
        if not self._enabled():
            return AllocationSolution("disabled", detail="The Optimization agent is switched off.")
        try:
            types = importlib.import_module(TYPES_MODULE)
            agent = self._agent_provider(self._agent_type)
            payload = agent.optimize(
                {
                    "problem": build_problem(types, problem),
                    "request_id": f"slaifi-alloc-{uuid.uuid4().hex[:12]}",
                    "publish": False,
                    "time_limit_seconds": SOLVER_TIMEOUT_SECONDS,
                    "metadata": {"source": "slaifi", "purpose": "paper_allocation_suggestion"},
                }
            )
        except Exception as exc:  # noqa: BLE001 - an unavailable agent must not break the app
            detail = f"{type(exc).__name__}: {exc}"[:240]
            logger.warning("SLAI optimization unavailable: %s", detail)
            self._report(False, detail)
            return AllocationSolution(
                "unavailable", detail=f"The Optimization agent is not available ({detail})."
            )
        result = interpret(payload, problem)
        # A solver that ran but found nothing is a correct answer, not a broken agent.
        self._report(True, None)
        return result
