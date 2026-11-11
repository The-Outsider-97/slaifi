"""Guards applied to SLAI's free-text interpretations before they reach the user.

SLAI explains evidence SLAIFI has already calculated. It may not introduce probabilities,
guarantees or invented figures. A flagged interpretation is withheld (not edited) and the
deterministic result is shown on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CERTAINTY = re.compile(
    r"\b(guarantee[ds]?|risk[- ]free|can'?t lose|cannot lose|sure thing|certain(?:ly)? (?:will|to)|"
    r"definitely (?:will|going)|no risk)\b",
    re.I,
)
_PROBABILITY = re.compile(
    r"\b\d{1,3}(?:\.\d+)?\s*%\s*(?:chance|probability|likelihood|likely|confidence|confident|accuracy|accurate)\b"
    r"|\b(?:probability|chance|likelihood|confidence)\s+(?:of|is|at)\s+\d{1,3}(?:\.\d+)?\s*%",
    re.I,
)
MAX_INTERPRETATION_CHARS = 4000


@dataclass(frozen=True, slots=True)
class GuardResult:
    text: str | None
    withheld: bool
    reasons: tuple[str, ...] = ()


def guard_interpretation(text: str | None) -> GuardResult:
    """Return the text unchanged if acceptable, otherwise withhold it with reasons."""

    if text is None or not text.strip():
        return GuardResult(None, False)
    reasons: list[str] = []
    if _CERTAINTY.search(text):
        reasons.append("it claims certainty or a guaranteed outcome")
    if _PROBABILITY.search(text):
        reasons.append(
            "it states a probability, confidence or accuracy figure SLAIFI did not calculate"
        )
    if reasons:
        return GuardResult(None, True, tuple(reasons))
    cleaned = text.strip()
    if len(cleaned) > MAX_INTERPRETATION_CHARS:
        cleaned = cleaned[:MAX_INTERPRETATION_CHARS].rstrip() + "…"
    return GuardResult(cleaned, False)
