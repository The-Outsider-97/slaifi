"""Rule-based recommendation engine."""

from slaifi.engines.recommendation.engine import RecommendationInputs, build_report
from slaifi.engines.recommendation.rules import (
    ActionThresholds,
    choose_action,
    risk_level_from_volatility,
    thresholds_for,
)
from slaifi.engines.recommendation.signals import (
    MIN_BARS_FOR_SIGNALS,
    IndicatorFrame,
    aggregate_score,
    build_frame,
    readings_at,
)

__all__ = [
    "MIN_BARS_FOR_SIGNALS",
    "ActionThresholds",
    "IndicatorFrame",
    "RecommendationInputs",
    "aggregate_score",
    "build_frame",
    "build_report",
    "choose_action",
    "readings_at",
    "risk_level_from_volatility",
    "thresholds_for",
]
