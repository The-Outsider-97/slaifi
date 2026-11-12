"""The recommendation log: what SLAIFI said, so it can later be checked against real prices."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from slaifi.application.contracts import FinanceStore
from slaifi.domain.learning import RecommendationRecord, TrackRecord, direction_of
from slaifi.domain.recommendations import RecommendationReport, ReportStatus
from slaifi.engines.learning import summarize


class RecommendationLog:
    def __init__(self, store: FinanceStore, *, clock: Callable[[], datetime] | None = None) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))

    def record(self, report: RecommendationReport, reference_price: Decimal | None) -> bool:
        """Log a real, current recommendation. Returns whether a new row was written.

        Reports built from last-known data and insufficient-evidence reports are never logged:
        the first would be judged against a stale price, the second made no call at all. One row
        per symbol, strategy and day keeps repeated page loads from inflating the sample.
        """

        if (
            report.status is not ReportStatus.RECOMMENDATION
            or report.action is None
            or report.last_known
            or reference_price is None
            or reference_price <= 0
        ):
            return False
        record = RecommendationRecord(
            record_id=f"R-{uuid.uuid4().hex[:12]}",
            symbol=report.asset.symbol,
            exchange=report.asset.exchange,
            asset_class=report.asset.asset_class.value,
            action=report.action.value,
            signal_score=report.signal_score,
            strategy_id=report.strategy_id,
            issued_at=report.generated_at,
            reference_price=reference_price,
        )
        try:
            return bool(self._store.log_recommendation(record))
        except Exception:  # noqa: BLE001 - self-measurement must never break a recommendation
            return False

    def summary(self) -> TrackRecord:
        return summarize(self._store.list_recommendation_history())

    def context(self) -> dict[str, Any]:
        """A compact, JSON-safe account of past reliability for SLAI's reasoning."""

        record = self.summary()
        return {
            "recommendations_logged": record.logged,
            "decisive_results": record.scored,
            "hit_rate": record.hit_rate,
            "verdict": record.verdict.value,
            "note": record.note,
            "directional_actions": sorted(
                {a.action for a in record.by_action if direction_of(a.action).value != "neutral"}
            ),
        }
