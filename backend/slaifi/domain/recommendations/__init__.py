"""Recommendation domain vocabulary."""

from slaifi.domain.recommendations.models import (
    ModelVersion,
    Recommendation,
    RecommendationAction,
    RiskLevel,
)
from slaifi.domain.recommendations.report import (
    ConstraintFinding,
    PredictionValidation,
    RecommendationReport,
    ReportStatus,
    SignalDirection,
    SignalReading,
)

__all__ = [
    "ConstraintFinding",
    "ModelVersion",
    "PredictionValidation",
    "Recommendation",
    "RecommendationAction",
    "RecommendationReport",
    "ReportStatus",
    "RiskLevel",
    "SignalDirection",
    "SignalReading",
]
