"""Records that let SLAIFI measure its own recommendations against what the market then did.

Nothing here predicts anything. A record is "what was said, when, at what price"; an outcome is
"what the real price did afterwards". Summaries state how many outcomes they rest on.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from slaifi.domain.utils import DomainValidationError, require_aware_datetime, require_non_blank

# Trading days a recommendation is judged over, and the move below which nothing is "right".
EVALUATION_TRADING_DAYS = 20
FLAT_BAND = 0.005  # a move of less than 0.5% either way is treated as flat, not a hit or a miss
MINIMUM_SCORED_FOR_VERDICT = 20


class Direction(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


_DIRECTION = {
    "BUY": Direction.BULLISH,
    "STRONG_BUY": Direction.BULLISH,
    "DCA": Direction.BULLISH,
    "SELL": Direction.BEARISH,
    "PARTIAL_SELL": Direction.BEARISH,
    "REDUCE": Direction.BEARISH,
    "SHORT": Direction.BEARISH,
    "AVOID": Direction.BEARISH,
}


def direction_of(action: str) -> Direction:
    """Bullish and bearish actions can be right or wrong; HOLD/WATCH/COVER make no price call."""

    return _DIRECTION.get(action.upper(), Direction.NEUTRAL)


@dataclass(frozen=True, slots=True)
class RecommendationRecord:
    record_id: str
    symbol: str
    asset_class: str
    action: str
    strategy_id: str
    issued_at: datetime
    reference_price: Decimal
    exchange: str | None = None
    signal_score: float | None = None
    horizon_trading_days: int = EVALUATION_TRADING_DAYS

    def __post_init__(self) -> None:
        require_non_blank(self.record_id, name="record_id")
        require_non_blank(self.symbol, name="symbol")
        require_aware_datetime(self.issued_at, name="issued_at")
        if self.reference_price <= 0:
            raise DomainValidationError("reference_price must be positive")
        if self.horizon_trading_days < 1:
            raise DomainValidationError("horizon_trading_days must be at least 1")

    @property
    def direction(self) -> Direction:
        return direction_of(self.action)


@dataclass(frozen=True, slots=True)
class RecommendationOutcome:
    record_id: str
    evaluated_at: datetime
    end_price: Decimal
    forward_return: float
    # True/False for bullish and bearish calls; None when the action made no price call or the
    # move was inside the flat band.
    correct: bool | None
    data_source: str = ""

    def __post_init__(self) -> None:
        require_aware_datetime(self.evaluated_at, name="evaluated_at")
        if self.end_price <= 0:
            raise DomainValidationError("end_price must be positive")


class Verdict(StrEnum):
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    BETTER_THAN_CHANCE = "better_than_chance"
    NO_CLEAR_EDGE = "no_clear_edge"
    WORSE_THAN_CHANCE = "worse_than_chance"


@dataclass(frozen=True, slots=True)
class ActionTrack:
    action: str
    scored: int
    hits: int
    mean_forward_return: float | None


@dataclass(frozen=True, slots=True)
class TrackRecord:
    logged: int
    pending: int  # logged, not yet old enough or not yet checked against real prices
    scored: int  # directional calls with a decisive outcome
    hits: int
    hit_rate: float | None
    interval_low: float | None  # 95% Wilson interval on the hit rate
    interval_high: float | None
    verdict: Verdict
    minimum_for_verdict: int
    by_action: tuple[ActionTrack, ...]
    note: str
