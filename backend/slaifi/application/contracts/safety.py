"""SLAIFI-owned contract for optional safety review of free text."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SafetyReview:
    """Outcome of screening text. ``available=False`` means no review was performed."""

    available: bool
    allowed: bool
    risk_level: str | None = None
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reviewer: str | None = None
    detail: str | None = None


class SafetyReviewer(Protocol):
    def review(self, text: str, *, purpose: str) -> SafetyReview: ...


@dataclass(frozen=True, slots=True)
class NullSafetyReviewer:
    """Used when SLAI's safety agent is disabled: reports that no review took place."""

    reason: str = "SLAI safety review is not configured."
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def review(self, text: str, *, purpose: str) -> SafetyReview:
        return SafetyReview(available=False, allowed=True, detail=self.reason)
