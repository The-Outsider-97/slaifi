"""Optional SLAI agents: names, status, and the ports the application depends on.

Every SLAI agent beyond reasoning/quality/safety is *optional*: it is off until the person switches
it on, it is never required, and when it is missing or fails the feature says so (``unavailable``)
and the deterministic SLAIFI behaviour carries on unchanged. Results from an agent are advice only:
SLAIFI re-checks them against the strategy's hard limits and never acts on them by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class AgentName(StrEnum):
    KNOWLEDGE = "knowledge"
    FINANCIAL = "financial"
    LEARNING = "learning"


AGENT_INFO: dict[AgentName, tuple[str, str]] = {
    AgentName.KNOWLEDGE: (
        "Knowledge",
        "Looks things up in SLAIFI's own guides and methodology and quotes the passage it found.",
    ),
    AgentName.FINANCIAL: (
        "Financial",
        "Works out a mix of holdings that would have been steadier from real price history, "
        "within your strategy's limits (SLAI's Financial agent, which uses SLAI's Optimization agent).",
    ),
    AgentName.LEARNING: (
        "Learning",
        "Shares how past recommendations turned out with SLAI's learning memory and shows what SLAI has recorded.",
    ),
}


@dataclass(frozen=True, slots=True)
class AgentStatus:
    """What the person sees for one optional agent.

    ``state``: ``disabled`` (switched off) · ``untested`` (on, not used yet) · ``ready`` (last use
    worked) · ``unavailable`` (last use failed; ``detail`` says why).
    """

    name: str
    label: str
    purpose: str
    enabled: bool
    state: str
    detail: str | None = None


# ------------------------------------------------------------------------------------ knowledge
@dataclass(frozen=True, slots=True)
class KnowledgePassage:
    source: str  # the SLAIFI document the passage comes from, e.g. docs/finance/methodology.md
    heading: str
    text: str
    score: float


@dataclass(frozen=True, slots=True)
class KnowledgeAnswer:
    """``status``: ``ok`` · ``no_match`` · ``disabled`` · ``unavailable``."""

    status: str
    passages: tuple[KnowledgePassage, ...] = ()
    detail: str | None = None


class KnowledgeLibrary(Protocol):
    def search(self, query: str, limit: int = 5) -> KnowledgeAnswer: ...


# ------------------------------------------------------------------------------------ financial
@dataclass(frozen=True, slots=True)
class PriceSeries:
    """Real daily closes of one asset, with where they came from (nothing here is generated)."""

    symbol: str
    closes: tuple[tuple[date, Decimal], ...]
    source: str
    currency: str


@dataclass(frozen=True, slots=True)
class AllocationProblem:
    """A long-only allocation: minimise ``w'Σw − risk_aversion · μ'w`` subject to the bounds.

    ``expected_returns`` and ``covariance`` are *historical* annualised statistics from real
    prices, not forecasts; SLAIFI uses them to check what the agent proposes. The agent itself
    works from ``series`` (the same real closes). ``budget`` is the total weight to allocate
    (1 − cash reserve).
    """

    symbols: tuple[str, ...]
    expected_returns: tuple[float, ...]
    covariance: tuple[tuple[float, ...], ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    budget: float
    risk_aversion: float = 0.0
    series: tuple[PriceSeries, ...] = ()


@dataclass(frozen=True, slots=True)
class AllocationSolution:
    """``status``: ``ok`` · ``infeasible`` · ``failed`` · ``disabled`` · ``unavailable``."""

    status: str
    weights: tuple[float, ...] | None = None
    solver: str | None = None
    detail: str | None = None
    warnings: tuple[str, ...] = ()


class FinancialAnalyst(Protocol):
    """SLAI's Financial agent, as far as SLAIFI uses it."""

    def solve(self, problem: AllocationProblem) -> AllocationSolution: ...

    def check(self) -> None:
        """Start the agent and run a read-only request; raises when it cannot."""


# ------------------------------------------------------------------------------------- learning
@dataclass(frozen=True, slots=True)
class LearningOutcome:
    """One real, scored recommendation, as SLAIFI measured it. Nothing here is a forecast."""

    outcome_id: str  # stable, so sending the same outcome twice is recognised as a duplicate
    action: str
    symbol: str
    asset_class: str
    strategy_id: str
    horizon_trading_days: int
    forward_return: float
    correct: bool | None
    data_source: str
    evaluated_at: str


@dataclass(frozen=True, slots=True)
class LearningShare:
    """``status``: ``ok`` · ``nothing_to_share`` · ``disabled`` · ``unavailable``."""

    status: str
    sent: int = 0
    duplicates: int = 0
    refused: int = 0
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class LearningActionSummary:
    action: str
    count: int
    mean_forward_return: float | None


@dataclass(frozen=True, slots=True)
class LearningRecall:
    """What SLAI's learning memory holds that SLAIFI sent it.

    ``status``: ``ok`` · ``empty`` · ``disabled`` · ``unavailable``.
    """

    status: str
    total: int = 0
    by_action: tuple[LearningActionSummary, ...] = ()
    detail: str | None = None


class LearningMemory(Protocol):
    def share(self, outcomes: tuple[LearningOutcome, ...]) -> LearningShare: ...

    def recall(self, limit: int = 500) -> LearningRecall: ...


__all__ = [
    "LearningActionSummary",
    "LearningMemory",
    "LearningOutcome",
    "LearningRecall",
    "LearningShare",
    "AGENT_INFO",
    "AgentName",
    "AgentStatus",
    "AllocationProblem",
    "AllocationSolution",
    "FinancialAnalyst",
    "KnowledgeAnswer",
    "KnowledgeLibrary",
    "KnowledgePassage",
    "PriceSeries",
]
