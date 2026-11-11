"""Natural-language instruction vocabulary: what SLAIFI understood, before anything changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class InstructionIntent(StrEnum):
    SET_PREFERENCE = "set_preference"
    SET_GOAL = "set_goal"
    PLACE_ORDER = "place_order"
    ANALYZE_PORTFOLIO = "analyze_portfolio"
    EVALUATE_GOAL = "evaluate_goal"
    SUGGEST_ALLOCATION = "suggest_allocation"
    FIND_INVESTMENTS = "find_investments"
    EXPLAIN = "explain"
    QUESTION = "question"


class Persistence(StrEnum):
    PERSISTENT = "persistent"
    TEMPORARY = "temporary"


@dataclass(frozen=True, slots=True)
class ProposedChange:
    """A change to strategy settings that only applies after explicit confirmation."""

    field: str
    old_value: Any
    new_value: Any
    persistence: Persistence
    description: str
    modifies_hard_limit: bool = False


@dataclass(frozen=True, slots=True)
class Contradiction:
    description: str
    fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GoalDraft:
    """A goal extracted from an instruction; created only after confirmation."""

    name: str
    target_amount: str | None = None
    period: str | None = None
    target_annual_rate: float | None = None
    horizon_years: float | None = None
    basis: str = "total_return"
    starting_capital: str | None = None


@dataclass(frozen=True, slots=True)
class OrderDraft:
    """A simulated order extracted from an instruction; never executed without confirmation."""

    side: str  # buy | sell
    symbol: str
    quantity: str | None = None
    notional: str | None = None
    close_position: bool = False


@dataclass(frozen=True, slots=True)
class ParsedInstruction:
    text: str
    intents: tuple[InstructionIntent, ...]
    changes: tuple[ProposedChange, ...] = ()
    goal_drafts: tuple[GoalDraft, ...] = ()
    order_drafts: tuple[OrderDraft, ...] = ()
    symbols: tuple[str, ...] = ()
    contradictions: tuple[Contradiction, ...] = ()
    warnings: tuple[str, ...] = ()
    unrecognised: bool = False
    already_in_effect: tuple[str, ...] = ()
    temporary_context: dict[str, Any] = field(default_factory=dict)
