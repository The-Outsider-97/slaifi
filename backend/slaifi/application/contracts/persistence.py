"""Application-owned persistence port for the authoritative financial ledger.

The ledger (trades + cash flows of the current epoch) is the single source of truth for paper
portfolios. Positions, cash, performance and allocation are always *derived* from it by the
engines; nothing derived is stored as authoritative state. SLAI SharedMemory is never used for
any of this.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from slaifi.domain.assets import AssetId
from slaifi.domain.goals import GoalSpec
from slaifi.domain.ledger import (
    AuditEntry,
    Proposal,
    StoredCashFlow,
    StoredRejection,
    StoredTrade,
    ValuationPoint,
    WatchlistItem,
)
from slaifi.domain.market import PriceQuote
from slaifi.domain.paper import ExecutionDetails, PaperPortfolio, Rejection
from slaifi.domain.portfolio import CashFlow, Portfolio, Trade
from slaifi.domain.strategies import StrategyProfile


@dataclass(frozen=True, slots=True)
class ReconciliationIssue:
    severity: str  # error | warning
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    portfolio_id: str | None
    checked_at: datetime
    trade_count: int
    cash_flow_count: int
    cash_balance: Decimal | None
    issues: tuple[ReconciliationIssue, ...] = field(default_factory=tuple)
    database_integrity: str = "ok"
    audit_chain_intact: bool = True

    @property
    def consistent(self) -> bool:
        return (
            self.database_integrity == "ok"
            and self.audit_chain_intact
            and not any(i.severity == "error" for i in self.issues)
        )


class FinanceStore(Protocol):
    """Durable store for portfolios, strategies, goals, proposals and the audit log."""

    def transaction(self) -> AbstractContextManager[Any]: ...
    def close(self) -> None: ...

    # portfolios / ledger ------------------------------------------------------------------
    def create_portfolio(
        self, portfolio: PaperPortfolio, initial_flow: CashFlow | None
    ) -> None: ...
    def list_portfolios(self) -> Sequence[PaperPortfolio]: ...
    def get_portfolio(self, portfolio_id: str) -> PaperPortfolio | None: ...
    def set_portfolio_strategy(self, portfolio_id: str, strategy_id: str | None) -> None: ...
    def load_ledger(self, portfolio_id: str) -> Portfolio: ...
    def list_trades(self, portfolio_id: str) -> Sequence[StoredTrade]: ...
    def list_cash_flows(self, portfolio_id: str) -> Sequence[StoredCashFlow]: ...
    def find_trade_by_client_order(
        self, portfolio_id: str, client_order_id: str
    ) -> StoredTrade | None: ...
    def append_trade(
        self, portfolio_id: str, trade: Trade, client_order_id: str, execution: ExecutionDetails
    ) -> None: ...
    def append_cash_flow(
        self, portfolio_id: str, flow: CashFlow, *, note: str | None = None, origin: str = "user"
    ) -> None: ...
    def record_rejection(
        self,
        portfolio_id: str,
        client_order_id: str,
        at: datetime,
        summary: str,
        rejections: Sequence[Rejection],
    ) -> None: ...
    def list_rejections(self, portfolio_id: str, limit: int = 50) -> Sequence[StoredRejection]: ...
    def reset_portfolio(
        self,
        portfolio_id: str,
        *,
        starting_capital: Decimal,
        initial_flow: CashFlow | None,
        now: datetime,
    ) -> int: ...
    def delete_portfolio(self, portfolio_id: str) -> None: ...

    # valuation history ---------------------------------------------------------------------
    def record_valuation(self, portfolio_id: str, point: ValuationPoint) -> None: ...
    def list_valuations(self, portfolio_id: str, limit: int = 2000) -> Sequence[ValuationPoint]: ...

    # strategies / goals / watchlist ------------------------------------------------------------
    def save_strategy(self, strategy: StrategyProfile, *, now: datetime) -> None: ...
    def list_strategies(self) -> Sequence[StrategyProfile]: ...
    def get_strategy(self, strategy_id: str) -> StrategyProfile | None: ...
    def delete_strategy(self, strategy_id: str) -> None: ...
    def get_active_strategy_id(self) -> str | None: ...
    def set_active_strategy_id(self, strategy_id: str) -> None: ...
    def save_goal(self, goal: GoalSpec) -> None: ...
    def list_goals(self) -> Sequence[GoalSpec]: ...
    def get_goal(self, goal_id: str) -> GoalSpec | None: ...
    def delete_goal(self, goal_id: str) -> None: ...
    def list_watchlist(self) -> Sequence[WatchlistItem]: ...
    def add_watchlist(self, item: WatchlistItem) -> None: ...
    def remove_watchlist(self, symbol: str, exchange: str | None) -> bool: ...

    # confirmations -------------------------------------------------------------------------------
    def save_proposal(self, proposal: Proposal) -> None: ...
    def get_proposal(self, proposal_id: str) -> Proposal | None: ...
    def set_proposal_status(self, proposal_id: str, status: str) -> None: ...

    # audit & health ---------------------------------------------------------------------------------
    def append_audit(
        self, *, at: datetime, actor: str, action: str, subject: str, detail: dict[str, Any]
    ) -> AuditEntry: ...
    def list_audit(self, limit: int = 100, subject: str | None = None) -> Sequence[AuditEntry]: ...
    def verify_audit_chain(self) -> tuple[bool, str | None]: ...
    def integrity(self) -> str: ...
    def backup(self, label: str) -> str: ...


class QuoteSource(Protocol):
    """Subset of the market service needed by paper trading."""

    async def quote(self, asset: AssetId) -> PriceQuote | None: ...
