"""Optional adapter: share SLAIFI's measured recommendation outcomes with SLAI's Learning agent.

What it does, and does not do
-----------------------------
* It sends each *scored* recommendation (what was advised, what the real price did over the
  following weeks) to the Learning agent as one ``outcome`` signal, and can read back what the
  agent recorded.
* The signals use the metric ``forward_return`` and are not marked as validated, so they never
  train the agent's strategy selector and never touch its internal reward statistics. They are
  evidence the agent keeps; SLAIFI's own rule-based learning is unchanged and does not read this.
* Sending is idempotent: the signal id is derived from the recommendation id, so a second send is
  reported as a duplicate by the agent.
* When the agent cannot be run (for example PyTorch is missing) the result says so; nothing else
  in SLAIFI is affected.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from logs.logger import get_logger

from slaifi.application.contracts import (
    LearningActionSummary,
    LearningOutcome,
    LearningRecall,
    LearningShare,
)

logger = get_logger("SLAIFI SLAI Learning")

SOURCE_AGENT = "slaifi"
METRIC = "forward_return"
MAX_PER_CALL = 200


def signal_for(outcome: LearningOutcome) -> dict[str, Any]:
    """The Learning agent's ``observe`` signal for one scored recommendation."""
    return {
        "signal_id": f"slaifi:outcome:{outcome.outcome_id}",
        "source_agent": SOURCE_AGENT,
        "kind": "outcome",
        "metric": METRIC,
        "value": float(outcome.forward_return),
        "direction": "higher_better",
        "confidence": 1.0,
        "validated": False,  # an observed outcome is evidence, not a supervised label
        "provenance": "evaluator",
        "strategy": outcome.action,
        "context": {
            "app": "slaifi",
            "asset_class": outcome.asset_class,
            "horizon_trading_days": outcome.horizon_trading_days,
        },
        "metadata": {
            "symbol": outcome.symbol,
            "strategy_id": outcome.strategy_id,
            "correct": outcome.correct,
            "data_source": outcome.data_source,
        },
        "timestamp": outcome.evaluated_at,
    }


def summarise(signals: list[dict[str, Any]]) -> tuple[int, tuple[LearningActionSummary, ...]]:
    """Count and average what the agent returned, per action. Anything malformed is skipped."""
    values: dict[str, list[float]] = defaultdict(list)
    for item in signals:
        if not isinstance(item, dict) or item.get("source_agent") != SOURCE_AGENT:
            continue
        if item.get("metric") != METRIC:
            continue
        action = item.get("strategy")
        value = item.get("value")
        if not isinstance(action, str) or isinstance(value, bool):
            continue
        if not isinstance(value, int | float) or not math.isfinite(value):
            continue
        values[action].append(float(value))
    rows = tuple(
        LearningActionSummary(action, len(vals), sum(vals) / len(vals))
        for action, vals in sorted(values.items())
    )
    return sum(r.count for r in rows), rows


class SlaiLearningMemory:
    """Talks to SLAI's Learning agent. Idle (no agent is created) while the switch is off."""

    def __init__(
        self,
        agent_provider: Callable[[str], Any],
        *,
        enabled: Callable[[], bool] = lambda: True,
        report: Callable[[bool, str | None], None] | None = None,
        agent_type: str = "learning",
    ) -> None:
        self._agent_provider = agent_provider
        self._enabled = enabled
        self._report = report or (lambda ok, detail: None)
        self._agent_type = agent_type

    def _fail(self, exc: Exception) -> str:
        detail = f"{type(exc).__name__}: {exc}"[:240]
        logger.warning("SLAI learning agent unavailable: %s", detail)
        self._report(False, detail)
        return detail

    def share(self, outcomes: tuple[LearningOutcome, ...]) -> LearningShare:
        if not self._enabled():
            return LearningShare("disabled", detail="The Learning agent is switched off.")
        if not outcomes:
            return LearningShare(
                "nothing_to_share",
                detail="No recommendation has been checked against real prices yet.",
            )
        batch = outcomes[:MAX_PER_CALL]
        try:
            agent = self._agent_provider(self._agent_type)
            sent = duplicates = refused = 0
            for outcome in batch:
                try:
                    answer = agent.perform_task({"mode": "observe", "signal": signal_for(outcome)})
                except ValueError:
                    refused += 1  # the agent's own validation said no; the rest still go
                    continue
                learning = (answer or {}).get("learning") or {}
                if learning.get("status") == "duplicate":
                    duplicates += 1
                else:
                    sent += 1
        except Exception as exc:  # noqa: BLE001 - an unavailable agent must not break the app
            detail = self._fail(exc)
            return LearningShare(
                "unavailable", detail=f"The Learning agent is not available ({detail})."
            )
        self._report(True, None)
        note = None
        if len(outcomes) > len(batch):
            note = f"Only the first {len(batch)} of {len(outcomes)} were sent; share again for the rest."
        return LearningShare("ok", sent=sent, duplicates=duplicates, refused=refused, detail=note)

    def recall(self, limit: int = 500) -> LearningRecall:
        if not self._enabled():
            return LearningRecall("disabled", detail="The Learning agent is switched off.")
        try:
            agent = self._agent_provider(self._agent_type)
            answer = agent.perform_task(
                {
                    "mode": "query",
                    "source_agent": SOURCE_AGENT,
                    "kind": "outcome",
                    "metric": METRIC,
                    "limit": max(1, min(int(limit), 1000)),
                }
            )
            signals = list((answer or {}).get("signals") or [])
        except Exception as exc:  # noqa: BLE001
            detail = self._fail(exc)
            return LearningRecall(
                "unavailable", detail=f"The Learning agent is not available ({detail})."
            )
        self._report(True, None)
        total, rows = summarise(signals)
        if total == 0:
            return LearningRecall("empty", detail="SLAI has not recorded any SLAIFI outcomes yet.")
        return LearningRecall("ok", total=total, by_action=rows)
