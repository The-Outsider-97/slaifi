"""Optional: hand SLAIFI's measured recommendation outcomes to SLAI's Learning agent.

This only *reads* the track record SLAIFI already keeps and passes it on. It never changes the
rule-based learning, the recommendations or any number SLAIFI shows elsewhere.
"""

from __future__ import annotations

from slaifi.application.contracts import (
    FinanceStore,
    LearningMemory,
    LearningOutcome,
    LearningRecall,
    LearningShare,
)

MAX_HISTORY = 1000


class LearningSharing:
    def __init__(self, store: FinanceStore, memory: LearningMemory) -> None:
        self._store = store
        self._memory = memory

    def outcomes(self) -> tuple[LearningOutcome, ...]:
        """Every recommendation that has been scored against real prices, oldest first."""
        rows: list[LearningOutcome] = []
        for record, outcome in self._store.list_recommendation_history()[:MAX_HISTORY]:
            if outcome is None:
                continue
            rows.append(
                LearningOutcome(
                    outcome_id=record.record_id,
                    action=record.action,
                    symbol=record.symbol,
                    asset_class=record.asset_class,
                    strategy_id=record.strategy_id,
                    horizon_trading_days=record.horizon_trading_days,
                    forward_return=outcome.forward_return,
                    correct=outcome.correct,
                    data_source=outcome.data_source,
                    evaluated_at=outcome.evaluated_at.isoformat(),
                )
            )
        rows.sort(key=lambda o: o.evaluated_at)
        return tuple(rows)

    def share(self) -> LearningShare:
        return self._memory.share(self.outcomes())

    def recall(self) -> LearningRecall:
        return self._memory.recall()
