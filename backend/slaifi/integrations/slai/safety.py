"""Adapter from SLAIFI's safety-review port to SLAI's SafetyAgent."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from logs.logger import get_logger

from slaifi.application.contracts import SafetyReview

logger = get_logger("SLAIFI SLAI Safety")

_BLOCKING_DECISIONS = {"block", "blocked", "deny", "denied", "reject", "rejected", "unsafe"}
MAX_REVIEW_CHARS = 4000


class SlaiSafetyReviewer:
    """Screen free text with SLAI's SafetyAgent; degrades to "not available", never to "approved"."""

    def __init__(
        self,
        agent_provider: Callable[[str], Any],
        *,
        agent_type: str = "safety",
        enabled: bool = True,
    ) -> None:
        self._agent_provider = agent_provider
        self._agent_type = agent_type
        self._enabled = enabled

    def review(self, text: str, *, purpose: str) -> SafetyReview:
        if not self._enabled:
            return SafetyReview(
                available=False, allowed=True, detail="SLAI safety review is disabled."
            )
        try:
            agent = self._agent_provider(self._agent_type)
            raw = agent.perform_task(
                text[:MAX_REVIEW_CHARS],
                {"purpose": purpose, "domain": "financial_decision_support"},
            )
        except Exception as exc:  # noqa: BLE001 - an unavailable reviewer must not break the app
            logger.warning("SLAI safety review unavailable: %s", type(exc).__name__)
            return SafetyReview(
                available=False,
                allowed=True,
                detail=f"SLAI safety review was unavailable ({type(exc).__name__}).",
            )
        return _interpret(raw, self._agent_type)


def _strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value)
    return (str(value),)


def _interpret(raw: Any, reviewer: str) -> SafetyReview:
    if not isinstance(raw, Mapping):
        return SafetyReview(
            available=False,
            allowed=True,
            detail="SLAI safety review returned no structured result.",
        )
    decision = str(raw.get("decision") or "").lower()
    blockers = _strings(raw.get("blockers"))
    is_safe = raw.get("is_safe")
    allowed = not blockers and is_safe is not False and decision not in _BLOCKING_DECISIONS
    risk = raw.get("risk_level")
    return SafetyReview(
        available=True,
        allowed=allowed,
        risk_level=str(risk) if risk is not None else None,
        blockers=blockers,
        warnings=_strings(raw.get("warnings")),
        reviewer=reviewer,
        detail=decision or None,
    )
