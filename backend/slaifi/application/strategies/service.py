"""Strategy management: presets, custom strategies, activation and portfolio alignment."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from slaifi.application.contracts import FinanceStore
from slaifi.application.strategies.changes import (
    HARD_LIMIT_FIELDS,
    apply_changes,
    current_value,
    describe_change,
    is_loosening,
)
from slaifi.core.utils.errors import ConflictError, NotFoundError, ValidationError
from slaifi.domain.portfolio import PortfolioSnapshot
from slaifi.domain.strategies import (
    DEFAULT_PRESET_ID,
    StrategyProfile,
    get_preset,
    instantiate_preset,
    list_presets,
)
from slaifi.engines.strategy import AlignmentReport, evaluate_alignment

ACTOR_USER = "user"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class StrategyService:
    """CRUD over persisted strategies. Presets are templates, never locks."""

    def __init__(self, store: FinanceStore, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._store = store
        self._clock = clock

    # ------------------------------------------------------------------ reads
    def presets(self) -> tuple[StrategyProfile, ...]:
        return tuple(list_presets())

    def list(self) -> list[StrategyProfile]:
        self.ensure_default()
        return list(self._store.list_strategies())

    def get(self, strategy_id: str) -> StrategyProfile:
        strategy = self._store.get_strategy(strategy_id)
        if strategy is None:
            raise NotFoundError(f"strategy {strategy_id!r} does not exist")
        return strategy

    def active(self) -> StrategyProfile:
        return self.ensure_default()

    def active_id(self) -> str:
        return self.ensure_default().strategy_id

    def ensure_default(self) -> StrategyProfile:
        """Create the default strategy from the default preset on first use."""

        with self._store.transaction():
            active_id = self._store.get_active_strategy_id()
            if active_id:
                found = self._store.get_strategy(active_id)
                if found is not None:
                    return found
            existing = list(self._store.list_strategies())
            if existing:
                self._store.set_active_strategy_id(existing[0].strategy_id)
                return existing[0]
            strategy = instantiate_preset(
                DEFAULT_PRESET_ID, strategy_id="default", name="My strategy"
            )
            self._store.save_strategy(strategy, now=self._clock())
            self._store.set_active_strategy_id(strategy.strategy_id)
            self._store.append_audit(
                at=self._clock(),
                actor="system",
                action="strategy.created",
                subject="default",
                detail={"preset": DEFAULT_PRESET_ID, "reason": "initial default strategy"},
            )
            return strategy

    def resolve(self, strategy_id: str | None) -> StrategyProfile:
        return self.get(strategy_id) if strategy_id else self.active()

    # ------------------------------------------------------------------ writes
    def create(
        self,
        *,
        name: str,
        preset_id: str | None = None,
        fields: Mapping[str, Any] | None = None,
        activate: bool = False,
        actor: str = ACTOR_USER,
    ) -> StrategyProfile:
        strategy_id = f"S-{uuid.uuid4().hex[:10]}"
        if preset_id is not None:
            try:
                get_preset(preset_id)
            except Exception as exc:  # noqa: BLE001
                raise ValidationError(f"unknown preset {preset_id!r}") from exc
            base = instantiate_preset(preset_id, strategy_id=strategy_id, name=name)
        else:
            base = instantiate_preset(DEFAULT_PRESET_ID, strategy_id=strategy_id, name=name)
        strategy = apply_changes(base, dict(fields or {})) if fields else base
        if preset_id is None:
            # A strategy not started from a preset must not claim to be one.
            strategy = replace(strategy, preset=None)
        with self._store.transaction():
            self._store.save_strategy(strategy, now=self._clock())
            if activate:
                self._store.set_active_strategy_id(strategy.strategy_id)
            self._store.append_audit(
                at=self._clock(),
                actor=actor,
                action="strategy.created",
                subject=strategy.strategy_id,
                detail={"name": strategy.name, "preset": preset_id, "activated": activate},
            )
        return strategy

    def update(
        self,
        strategy_id: str,
        fields: Mapping[str, Any],
        *,
        actor: str = ACTOR_USER,
        acknowledge_loosening: bool = False,
    ) -> StrategyProfile:
        """Apply field edits. Loosening a hard limit needs an explicit acknowledgement."""

        if not fields:
            raise ValidationError("no changes were supplied")
        with self._store.transaction():
            old = self.get(strategy_id)
            loosened = [f for f, v in fields.items() if is_loosening(f, current_value(old, f), v)]
            if loosened and not acknowledge_loosening:
                raise ConflictError(
                    "This loosens a hard limit (" + ", ".join(sorted(loosened)) + "); "
                    "confirm explicitly with acknowledge_loosening=true.",
                    context={"loosened": sorted(loosened)},
                )
            new = apply_changes(old, fields)
            self._store.save_strategy(new, now=self._clock())
            self._store.append_audit(
                at=self._clock(),
                actor=actor,
                action="strategy.updated",
                subject=strategy_id,
                detail={
                    "changes": [
                        {
                            "field": f,
                            "old": current_value(old, f),
                            "new": current_value(new, f),
                            "hard_limit": f in HARD_LIMIT_FIELDS,
                            "loosened": f in loosened,
                            "summary": describe_change(
                                f, current_value(old, f), current_value(new, f)
                            ),
                        }
                        for f in fields
                    ]
                },
            )
        return new

    def activate(self, strategy_id: str, *, actor: str = ACTOR_USER) -> StrategyProfile:
        strategy = self.get(strategy_id)
        with self._store.transaction():
            self._store.set_active_strategy_id(strategy_id)
            self._store.append_audit(
                at=self._clock(),
                actor=actor,
                action="strategy.activated",
                subject=strategy_id,
                detail={},
            )
        return strategy

    def delete(self, strategy_id: str, *, actor: str = ACTOR_USER) -> None:
        self.get(strategy_id)
        if self._store.get_active_strategy_id() == strategy_id:
            raise ConflictError(
                "The active strategy cannot be deleted; activate another one first."
            )
        for portfolio in self._store.list_portfolios():
            if portfolio.strategy_id == strategy_id:
                raise ConflictError(
                    f"Portfolio {portfolio.name!r} uses this strategy; reassign it first."
                )
        with self._store.transaction():
            self._store.delete_strategy(strategy_id)
            self._store.append_audit(
                at=self._clock(),
                actor=actor,
                action="strategy.deleted",
                subject=strategy_id,
                detail={},
            )

    # ------------------------------------------------------------------ alignment
    def alignment(
        self,
        snapshot: PortfolioSnapshot,
        strategy: StrategyProfile,
        *,
        portfolio_drawdown: float | None = None,
    ) -> AlignmentReport:
        return evaluate_alignment(snapshot, strategy, portfolio_drawdown=portfolio_drawdown)
