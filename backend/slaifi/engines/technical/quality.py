"""Historical-bar normalisation and quality assessment. Missing bars are never fabricated."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from slaifi.domain.market import OHLCVBar

# Calendar days that cover a normal weekend plus a market holiday for daily data.
_DAILY_GAP_DAYS = 5


@dataclass(frozen=True, slots=True)
class BarQuality:
    count: int
    first_at: datetime | None
    last_at: datetime | None
    duplicates_removed: int
    reordered: bool
    gap_count: int
    largest_gap_days: float | None
    complete: bool


def normalize_bars(bars: Sequence[OHLCVBar]) -> tuple[tuple[OHLCVBar, ...], int, bool]:
    """Sort chronologically and drop exact-timestamp duplicates (last one wins)."""

    reordered = any(
        later.start_at < earlier.start_at for earlier, later in zip(bars, bars[1:], strict=False)
    )
    by_start: dict[datetime, OHLCVBar] = {}
    for bar in bars:
        by_start[bar.start_at] = bar
    ordered = tuple(sorted(by_start.values(), key=lambda bar: bar.start_at))
    return ordered, len(bars) - len(ordered), reordered


def assess_bars(bars: Sequence[OHLCVBar], interval: str = "1day") -> BarQuality:
    """Describe a normalised series; gaps are only measured for daily-or-longer data."""

    ordered, duplicates, reordered = normalize_bars(bars)
    if not ordered:
        return BarQuality(0, None, None, duplicates, reordered, 0, None, False)
    gap_count = 0
    largest: timedelta | None = None
    if interval in {"1day", "1week", "1month"}:
        threshold = timedelta(days=_DAILY_GAP_DAYS if interval == "1day" else 12)
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            gap = later.start_at - earlier.start_at
            if gap > threshold:
                gap_count += 1
            if largest is None or gap > largest:
                largest = gap
    return BarQuality(
        count=len(ordered),
        first_at=ordered[0].start_at,
        last_at=ordered[-1].start_at,
        duplicates_removed=duplicates,
        reordered=reordered,
        gap_count=gap_count,
        largest_gap_days=largest.total_seconds() / 86400.0 if largest is not None else None,
        complete=gap_count == 0 and duplicates == 0,
    )
