"""SLAI advisor: natural-language instructions become validated, confirmable proposals.

Division of labour:

* the deterministic parser (``engines.instructions``) extracts bounded, structured values;
* SLAIFI validates them (limits, contradictions, goal arithmetic, order previews);
* SLAI's reasoning agent explains what was understood and the trade-offs (never changes values);
* SLAI's safety agent screens the text when available;
* **nothing persistent happens without an explicit confirmation**, and loosening a hard limit or
  confirming despite a detected contradiction each need their own acknowledgement.

Proposals live in the SQLite ledger (not in SLAI SharedMemory) with an expiry.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from slaifi.application.contracts import (
    FinanceStore,
    FinancialReasoner,
    NullSafetyReviewer,
    ReasoningRequest,
    SafetyReview,
    SafetyReviewer,
)
from slaifi.application.goals import GoalTracker
from slaifi.application.paper import OrderOutcome, PaperTradingService
from slaifi.application.portfolio import PortfolioGuidanceService
from slaifi.application.recommendations import Explanation, RecommendationService
from slaifi.application.strategies import (
    HARD_LIMIT_FIELDS,
    StrategyService,
    apply_changes,
    current_value,
    describe_change,
    is_loosening,
)
from slaifi.core.types import CurrencyCode
from slaifi.core.utils.errors import ConflictError, NotFoundError, SlaifiError, ValidationError
from slaifi.domain.goals import GoalBasis, GoalFeasibilityReport, GoalSpec, IncomePeriod
from slaifi.domain.instructions import (
    Contradiction,
    GoalDraft,
    OrderDraft,
    ParsedInstruction,
    Persistence,
)
from slaifi.domain.ledger import Proposal
from slaifi.domain.portfolio import TradeSide
from slaifi.domain.strategies import StrategyProfile
from slaifi.engines.instructions import MAX_TEXT_LENGTH, parse_instruction

PROPOSAL_TTL = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class ChangeView:
    index: int
    field: str
    old: Any
    new: Any
    persistence: str
    description: str
    hard_limit: bool
    loosening: bool


@dataclass(frozen=True, slots=True)
class GoalPreview:
    draft: GoalDraft
    report: GoalFeasibilityReport | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class OrderPreview:
    draft: OrderDraft
    outcome: OrderOutcome | None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class TemporaryAnalysis:
    description: str
    changes: tuple[str, ...]
    new_findings: tuple[str, ...]
    resolved_findings: tuple[str, ...]
    aligned_before: bool | None
    aligned_after: bool | None


@dataclass(frozen=True, slots=True)
class AdvisorResult:
    text: str
    understood: tuple[str, ...]
    intents: tuple[str, ...]
    blocked: bool
    safety: SafetyReview
    changes: tuple[ChangeView, ...]
    temporary_changes: tuple[ChangeView, ...]
    goals: tuple[GoalPreview, ...]
    orders: tuple[OrderPreview, ...]
    contradictions: tuple[Contradiction, ...]
    warnings: tuple[str, ...]
    temporary_analysis: TemporaryAnalysis | None
    proposal: Proposal | None
    explanation: Explanation | None
    requires_confirmation: bool
    unrecognised: bool
    needs_acknowledgement_of_limits: bool
    needs_acknowledgement_of_contradictions: bool


@dataclass(frozen=True, slots=True)
class ConfirmResult:
    proposal_id: str
    applied_changes: tuple[str, ...]
    created_goal_ids: tuple[str, ...]
    orders: tuple[OrderOutcome, ...]
    strategy: StrategyProfile


def _norm(value: Any) -> Any:
    if isinstance(value, (set, frozenset, tuple)):
        return sorted(value)
    if isinstance(value, list):
        return sorted(value) if all(isinstance(v, str) for v in value) else value
    if isinstance(value, float):
        return round(value, 10)
    return value


class AdvisorService:
    def __init__(
        self,
        store: FinanceStore,
        strategies: StrategyService,
        goals: GoalTracker,
        paper: PaperTradingService,
        recommender: RecommendationService,
        guidance: PortfolioGuidanceService,
        *,
        reasoner: FinancialReasoner | None = None,
        safety: SafetyReviewer | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._strategies = strategies
        self._goals = goals
        self._paper = paper
        self._recommender = recommender
        self._guidance = guidance
        self._reasoner = reasoner
        self._safety = safety or NullSafetyReviewer()
        self._clock = clock or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------ interpret
    async def interpret(
        self, text: str, *, portfolio_id: str | None = None, explain: bool = True
    ) -> AdvisorResult:
        cleaned = " ".join(text.split())
        if not cleaned:
            raise ValidationError("the instruction is empty")
        if len(cleaned) > MAX_TEXT_LENGTH:
            raise ValidationError(f"the instruction is longer than {MAX_TEXT_LENGTH} characters")
        if portfolio_id is not None:
            self._paper.get_portfolio(portfolio_id)

        safety = await asyncio.to_thread(
            self._safety.review, cleaned, purpose="advisor_instruction"
        )
        now = self._clock()
        strategy = self._strategies.resolve(
            self._paper.get_portfolio(portfolio_id).strategy_id if portfolio_id else None
        )
        if safety.available and not safety.allowed:
            self._store.append_audit(
                at=now,
                actor="user",
                action="advisor.blocked",
                subject=strategy.strategy_id,
                detail={"blockers": list(safety.blockers)},
            )
            return AdvisorResult(
                text=cleaned,
                understood=(),
                intents=(),
                blocked=True,
                safety=safety,
                changes=(),
                temporary_changes=(),
                goals=(),
                orders=(),
                contradictions=(),
                warnings=(
                    "The safety review blocked this instruction: " + "; ".join(safety.blockers),
                ),
                temporary_analysis=None,
                proposal=None,
                explanation=None,
                requires_confirmation=False,
                unrecognised=False,
                needs_acknowledgement_of_limits=False,
                needs_acknowledgement_of_contradictions=False,
            )

        parsed = parse_instruction(cleaned, strategy)
        changes: list[ChangeView] = []
        temporary: list[ChangeView] = []
        for change in parsed.changes:
            view = ChangeView(
                index=-1,
                field=change.field,
                old=change.old_value,
                new=change.new_value,
                persistence=change.persistence.value,
                description=change.description,
                hard_limit=change.field in HARD_LIMIT_FIELDS,
                loosening=is_loosening(
                    change.field, current_value(strategy, change.field), change.new_value
                ),
            )
            (temporary if change.persistence is Persistence.TEMPORARY else changes).append(view)
        changes = [
            ChangeView(
                i,
                c.field,
                c.old,
                c.new,
                c.persistence,
                describe_change(c.field, c.old, c.new),
                c.hard_limit,
                c.loosening,
            )
            for i, c in enumerate(changes)
        ]

        # validate every proposed change by actually applying it to a copy of the strategy
        warnings = list(parsed.warnings)
        valid_changes: list[ChangeView] = []
        for c in changes:
            try:
                apply_changes(strategy, {c.field: c.new})
                valid_changes.append(c)
            except SlaifiError as exc:
                warnings.append(f"Ignored {c.field}: {exc.message}")
        changes = valid_changes

        capital = await self._capital(parsed, portfolio_id, strategy)
        goal_previews = [
            await self._preview_goal(draft, capital, portfolio_id) for draft in parsed.goal_drafts
        ]
        order_previews = [await self._preview_order(d, portfolio_id) for d in parsed.order_drafts]
        contradictions = list(parsed.contradictions)
        for gp in goal_previews:
            if gp.report is not None:
                for finding in gp.report.findings:
                    if finding.code in {"risk_conflict", "drawdown_conflict"}:
                        contradictions.append(Contradiction(finding.message, ("goal", "strategy")))
        loosening = any(c.loosening for c in changes)

        temp_analysis = (
            await self._temporary(strategy, temporary, portfolio_id) if temporary else None
        )
        proposal: Proposal | None = None
        has_actions = bool(changes or parsed.goal_drafts or parsed.order_drafts)
        if has_actions:
            payload = {
                "strategy_id": strategy.strategy_id,
                "portfolio_id": portfolio_id,
                "changes": [
                    {"field": c.field, "old": c.old, "new": c.new, "loosening": c.loosening}
                    for c in changes
                ],
                "goals": [
                    asdict(g.draft)
                    for g in goal_previews
                    if g.error is None or g.report is not None
                ],
                "orders": [asdict(o.draft) for o in order_previews],
                "has_contradictions": bool(contradictions),
            }
            proposal = Proposal(
                proposal_id=f"A-{uuid.uuid4().hex[:12]}",
                created_at=now,
                expires_at=now + PROPOSAL_TTL,
                kind="advisor_actions",
                text=cleaned,
                payload=payload,
            )
            with self._store.transaction():
                self._store.save_proposal(proposal)
                self._store.append_audit(
                    at=now,
                    actor="user",
                    action="advisor.proposed",
                    subject=proposal.proposal_id,
                    detail={
                        "changes": [c.description for c in changes],
                        "goals": len(goal_previews),
                        "orders": len(order_previews),
                        "contradictions": len(contradictions),
                    },
                )

        understood = self._understood(changes, temporary, goal_previews, order_previews, parsed)
        result = AdvisorResult(
            text=cleaned,
            understood=tuple(understood),
            intents=tuple(i.value for i in parsed.intents),
            blocked=False,
            safety=safety,
            changes=tuple(changes),
            temporary_changes=tuple(temporary),
            goals=tuple(goal_previews),
            orders=tuple(order_previews),
            contradictions=tuple(contradictions),
            warnings=tuple(dict.fromkeys(warnings)),
            temporary_analysis=temp_analysis,
            proposal=proposal,
            explanation=None,
            requires_confirmation=proposal is not None,
            unrecognised=parsed.unrecognised,
            needs_acknowledgement_of_limits=loosening,
            needs_acknowledgement_of_contradictions=bool(contradictions),
        )
        if explain and not parsed.unrecognised:
            explanation = await self._explain(result, strategy)
            result = replace(result, explanation=explanation)
        return result

    async def _capital(
        self, parsed: ParsedInstruction, portfolio_id: str | None, strategy: StrategyProfile
    ) -> Decimal | None:
        raw = parsed.temporary_context.get("starting_capital")
        if raw:
            try:
                return Decimal(str(raw))
            except InvalidOperation:
                return None
        if portfolio_id:
            return (await self._paper.view(portfolio_id, record=False)).snapshot.total_value
        return strategy.capital

    async def _preview_goal(
        self, draft: GoalDraft, capital: Decimal | None, portfolio_id: str | None
    ) -> GoalPreview:
        try:
            spec = self._spec_from_draft(draft, "USD", portfolio_id)
            use_capital = Decimal(draft.starting_capital) if draft.starting_capital else capital
            report = await self._goals.analyze_spec(
                spec, portfolio_id=portfolio_id, capital_override=use_capital
            )
            return GoalPreview(draft, report)
        except SlaifiError as exc:
            return GoalPreview(draft, None, exc.message)
        except (ValueError, ArithmeticError) as exc:
            return GoalPreview(draft, None, str(exc))

    @staticmethod
    def _spec_from_draft(draft: GoalDraft, currency: str, portfolio_id: str | None) -> GoalSpec:
        return GoalSpec(
            goal_id="preview",
            name=draft.name,
            currency=CurrencyCode(currency),
            created_at=datetime.now(UTC),
            basis=GoalBasis(draft.basis),
            target_amount=Decimal(draft.target_amount) if draft.target_amount else None,
            period=IncomePeriod(draft.period) if draft.period else None,
            target_annual_rate=draft.target_annual_rate,
            horizon_years=draft.horizon_years,
            starting_capital=Decimal(draft.starting_capital) if draft.starting_capital else None,
            portfolio_id=portfolio_id,
        )

    async def _preview_order(self, draft: OrderDraft, portfolio_id: str | None) -> OrderPreview:
        if portfolio_id is None:
            return OrderPreview(draft, None, "Select a paper portfolio to preview this order.")
        try:
            outcome = await self._paper.place_order(
                portfolio_id,
                symbol=draft.symbol,
                side=TradeSide(draft.side),
                quantity=Decimal(draft.quantity) if draft.quantity else None,
                notional=Decimal(draft.notional) if draft.notional else None,
                close_position=draft.close_position,
                dry_run=True,
            )
            return OrderPreview(draft, outcome)
        except SlaifiError as exc:
            return OrderPreview(draft, None, exc.message)
        except (ValueError, ArithmeticError) as exc:
            return OrderPreview(draft, None, str(exc))

    async def _temporary(
        self, strategy: StrategyProfile, temporary: list[ChangeView], portfolio_id: str | None
    ) -> TemporaryAnalysis:
        fields = {c.field: c.new for c in temporary}
        descriptions = tuple(describe_change(c.field, c.old, c.new) for c in temporary)
        try:
            alt = apply_changes(strategy, fields)
        except SlaifiError as exc:
            return TemporaryAnalysis(
                f"The temporary settings are invalid: {exc.message}",
                descriptions,
                (),
                (),
                None,
                None,
            )
        if portfolio_id is None:
            return TemporaryAnalysis(
                "Applies to this analysis only and is not saved. Select a portfolio to see its effect.",
                descriptions,
                (),
                (),
                None,
                None,
            )
        view = await self._paper.view(portfolio_id, record=False)
        before = await self._guidance.alignment(view, strategy)
        after = await self._guidance.alignment(view, alt)
        b = {f.message for f in before.findings if f.severity == "hard"}
        a = {f.message for f in after.findings if f.severity == "hard"}
        return TemporaryAnalysis(
            "Applies to this analysis only and is not saved.",
            descriptions,
            tuple(sorted(a - b)),
            tuple(sorted(b - a)),
            before.aligned,
            after.aligned,
        )

    @staticmethod
    def _understood(
        changes: list[ChangeView],
        temporary: list[ChangeView],
        goals: list[GoalPreview],
        orders: list[OrderPreview],
        parsed: ParsedInstruction,
    ) -> list[str]:
        lines = [f"Persistent setting — {c.description}" for c in changes]
        lines += [
            f"Temporary (not saved) — {describe_change(c.field, c.old, c.new)}" for c in temporary
        ]
        for g in goals:
            d = g.draft
            if d.target_amount:
                lines.append(
                    f"Goal — {Decimal(d.target_amount):,.2f} per {d.period} ({d.basis.replace('_', ' ')})"
                )
            elif d.target_annual_rate is not None:
                lines.append(
                    f"Goal — {d.target_annual_rate:.1%} per year"
                    + (f" over {d.horizon_years:g} years" if d.horizon_years else "")
                )
        for o in orders:
            d2 = o.draft
            size = (
                "the whole position"
                if d2.close_position
                else (f"{d2.quantity} units" if d2.quantity else f"{d2.notional} worth")
            )
            lines.append(f"Simulated order — {d2.side} {size} of {d2.symbol}")
        lines += [f"Already in effect — {text}" for text in parsed.already_in_effect]
        if not lines and not parsed.unrecognised:
            lines.append("No settings, goals or orders were recognised; this reads as a question.")
        return lines

    async def _explain(
        self, result: AdvisorResult, strategy: StrategyProfile
    ) -> Explanation | None:
        if self._reasoner is None:
            return Explanation("disabled", None, warnings=("SLAI reasoning is not configured.",))
        evidence = {
            "instruction": result.text,
            "understood": list(result.understood),
            "proposed_changes": [
                {
                    "field": c.field,
                    "old": c.old,
                    "new": c.new,
                    "hard_limit": c.hard_limit,
                    "loosens_limit": c.loosening,
                }
                for c in result.changes
            ],
            "goal_feasibility": [
                {
                    "goal": g.draft.name,
                    "status": g.report.status.value if g.report else None,
                    "required_annual_return_rate": g.report.required_annual_return_rate
                    if g.report
                    else None,
                    "findings": [f.message for f in g.report.findings] if g.report else [g.error],
                }
                for g in result.goals
            ],
            "orders": [
                {
                    "order": f"{o.draft.side} {o.draft.symbol}",
                    "status": o.outcome.decision.status.value if o.outcome else None,
                    "rejections": [r.message for r in o.outcome.decision.rejections]
                    if o.outcome
                    else [o.error],
                }
                for o in result.orders
            ],
            "contradictions": [c.description for c in result.contradictions],
            "active_strategy": {
                "risk_tolerance": strategy.risk_tolerance.value,
                "horizon_days": strategy.horizon_days,
            },
        }
        request = ReasoningRequest(
            operation="advisor_interpretation",
            evidence=evidence,
            objective=(
                "Explain to the user what their instruction was understood to mean, what would change, which "
                "hard limits or contradictions matter, and the trade-offs of their goals. Do not add settings, "
                "amounts, probabilities or guarantees, and do not state that a goal will be achieved."
            ),
            constraints={
                "confirmation_required_before_any_change": True,
                "hard_limits_override_preferences": True,
            },
        )
        return await self._recommender.run_reasoner(request, purpose="advisor_interpretation")

    # ------------------------------------------------------------------ confirm / reject
    def _load_pending(self, proposal_id: str) -> Proposal:
        proposal = self._store.get_proposal(proposal_id)
        if proposal is None:
            raise NotFoundError(f"proposal {proposal_id!r} does not exist")
        if proposal.status != "pending":
            raise ConflictError(f"This proposal was already {proposal.status}.")
        if self._clock() > proposal.expires_at:
            self._store.set_proposal_status(proposal_id, "expired")
            raise ConflictError("This proposal expired; ask the advisor again.")
        return proposal

    def reject(self, proposal_id: str) -> None:
        self._load_pending(proposal_id)
        with self._store.transaction():
            self._store.set_proposal_status(proposal_id, "rejected")
            self._store.append_audit(
                at=self._clock(),
                actor="user",
                action="advisor.rejected",
                subject=proposal_id,
                detail={},
            )

    async def confirm(
        self,
        proposal_id: str,
        *,
        acknowledge_limit_changes: bool = False,
        acknowledge_contradictions: bool = False,
    ) -> ConfirmResult:
        proposal = self._load_pending(proposal_id)
        payload = proposal.payload
        strategy = self._strategies.get(payload["strategy_id"])
        changes = payload.get("changes", [])
        if payload.get("has_contradictions") and not acknowledge_contradictions:
            raise ConflictError(
                "The advisor detected contradictions in this request; review them and confirm with "
                "acknowledge_contradictions=true."
            )
        for change in changes:
            if _norm(current_value(strategy, change["field"])) != _norm(change["old"]):
                raise ConflictError(
                    f"{change['field']} changed since this proposal was made; nothing was applied. Ask again."
                )
        loosened = [c["field"] for c in changes if c.get("loosening")]
        if loosened and not acknowledge_limit_changes:
            raise ConflictError(
                "This loosens a hard limit ("
                + ", ".join(loosened)
                + "); confirm with acknowledge_limit_changes=true.",
                context={"loosened": loosened},
            )
        applied: list[str] = []
        new_strategy = strategy
        if changes:
            new_strategy = self._strategies.update(
                strategy.strategy_id,
                {c["field"]: c["new"] for c in changes},
                actor="advisor(confirmed by user)",
                acknowledge_loosening=bool(loosened),
            )
            applied = [describe_change(c["field"], c["old"], c["new"]) for c in changes]
        goal_ids: list[str] = []
        for draft in payload.get("goals", []):
            spec = self._goals.create(
                {
                    "name": draft["name"],
                    "basis": draft["basis"],
                    "target_amount": draft.get("target_amount"),
                    "period": draft.get("period"),
                    "target_annual_rate": draft.get("target_annual_rate"),
                    "horizon_years": draft.get("horizon_years"),
                    "starting_capital": draft.get("starting_capital"),
                    "portfolio_id": payload.get("portfolio_id"),
                },
                actor="advisor(confirmed by user)",
            )
            goal_ids.append(spec.goal_id)
        outcomes: list[OrderOutcome] = []
        orders = payload.get("orders", [])
        if orders and not payload.get("portfolio_id"):
            raise ValidationError(
                "A portfolio is required to run the simulated orders in this proposal."
            )
        for index, order in enumerate(orders):
            outcomes.append(
                await self._paper.place_order(
                    payload["portfolio_id"],
                    symbol=order["symbol"],
                    side=TradeSide(order["side"]),
                    quantity=Decimal(order["quantity"]) if order.get("quantity") else None,
                    notional=Decimal(order["notional"]) if order.get("notional") else None,
                    close_position=bool(order.get("close_position")),
                    client_order_id=f"{proposal_id}-{index}",
                    actor="advisor(confirmed by user)",
                )
            )
        with self._store.transaction():
            self._store.set_proposal_status(proposal_id, "applied")
            self._store.append_audit(
                at=self._clock(),
                actor="user",
                action="advisor.confirmed",
                subject=proposal_id,
                detail={
                    "applied_changes": applied,
                    "goals": goal_ids,
                    "orders": [o.decision.status.value for o in outcomes],
                },
            )
        return ConfirmResult(
            proposal_id, tuple(applied), tuple(goal_ids), tuple(outcomes), new_strategy
        )
