"""Scoring recommendations against realised prices and summarising honestly.

The summary says how many outcomes it rests on and whether that is enough to say anything. A
hit rate near 50% is "no clear edge", not "slightly good"; below the minimum sample there is no
verdict at all.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from math import sqrt

from slaifi.domain.learning import (
    FLAT_BAND,
    MINIMUM_SCORED_FOR_VERDICT,
    ActionTrack,
    Direction,
    RecommendationOutcome,
    RecommendationRecord,
    TrackRecord,
    Verdict,
)

_Z95 = 1.959964


def score_outcome(
    record: RecommendationRecord,
    *,
    end_price: Decimal,
    evaluated_at: datetime,
    data_source: str = "",
) -> RecommendationOutcome:
    forward = float(end_price / record.reference_price - 1)
    correct: bool | None
    if record.direction is Direction.NEUTRAL or abs(forward) < FLAT_BAND:
        correct = None
    elif record.direction is Direction.BULLISH:
        correct = forward > 0
    else:
        correct = forward < 0
    return RecommendationOutcome(
        record_id=record.record_id,
        evaluated_at=evaluated_at,
        end_price=end_price,
        forward_return=forward,
        correct=correct,
        data_source=data_source,
    )


def wilson_interval(hits: int, n: int) -> tuple[float, float] | None:
    """95% Wilson score interval for a proportion; ``None`` when there is nothing to measure."""

    if n <= 0:
        return None
    p = hits / n
    denom = 1 + _Z95**2 / n
    centre = (p + _Z95**2 / (2 * n)) / denom
    half = _Z95 * sqrt(p * (1 - p) / n + _Z95**2 / (4 * n**2)) / denom
    return max(centre - half, 0.0), min(centre + half, 1.0)


def summarize(
    history: Sequence[tuple[RecommendationRecord, RecommendationOutcome | None]],
    *,
    minimum_for_verdict: int = MINIMUM_SCORED_FOR_VERDICT,
) -> TrackRecord:
    logged = len(history)
    pending = sum(1 for _, outcome in history if outcome is None)
    per_action: dict[str, list[tuple[bool, float]]] = defaultdict(list)
    for record, outcome in history:
        if outcome is None or outcome.correct is None:
            continue
        per_action[record.action].append((outcome.correct, outcome.forward_return))
    scored = sum(len(v) for v in per_action.values())
    hits = sum(1 for v in per_action.values() for ok, _ in v if ok)
    interval = wilson_interval(hits, scored)
    hit_rate = hits / scored if scored else None

    if scored < minimum_for_verdict or interval is None:
        verdict = Verdict.INSUFFICIENT_SAMPLE
        note = (
            f"{scored} decisive result(s) so far; at least {minimum_for_verdict} are needed "
            "before this says anything about reliability. Until then treat every recommendation "
            "on its own evidence."
        )
    elif interval[0] > 0.5:
        verdict = Verdict.BETTER_THAN_CHANCE
        note = (
            "Directional calls beat a coin flip over this sample. That describes the past "
            "sample only; it is not a promise about the next call."
        )
    elif interval[1] < 0.5:
        verdict = Verdict.WORSE_THAN_CHANCE
        note = (
            "Directional calls did worse than a coin flip over this sample. Give recommendations "
            "less weight and rely on your own limits."
        )
    else:
        verdict = Verdict.NO_CLEAR_EDGE
        note = "The hit rate cannot be told apart from a coin flip with this much data."

    by_action = tuple(
        ActionTrack(
            action=action,
            scored=len(rows),
            hits=sum(1 for ok, _ in rows if ok),
            mean_forward_return=sum(r for _, r in rows) / len(rows),
        )
        for action, rows in sorted(per_action.items())
    )
    return TrackRecord(
        logged=logged,
        pending=pending,
        scored=scored,
        hits=hits,
        hit_rate=hit_rate,
        interval_low=interval[0] if interval else None,
        interval_high=interval[1] if interval else None,
        verdict=verdict,
        minimum_for_verdict=minimum_for_verdict,
        by_action=by_action,
        note=note,
    )
