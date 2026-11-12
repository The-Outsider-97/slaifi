"""Self-measurement and strategy-adaptation calculations."""

from slaifi.engines.learning.adaptation import (
    AdaptationInputs,
    AdaptationProposal,
    AdaptationReport,
    GoalSignal,
    propose_adaptations,
)
from slaifi.engines.learning.track_record import score_outcome, summarize, wilson_interval

__all__ = [
    "AdaptationInputs",
    "AdaptationProposal",
    "AdaptationReport",
    "GoalSignal",
    "propose_adaptations",
    "score_outcome",
    "summarize",
    "wilson_interval",
]
