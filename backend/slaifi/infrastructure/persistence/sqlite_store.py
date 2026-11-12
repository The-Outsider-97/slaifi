"""SQLite implementation of :class:`FinanceStore` on SLAI's shared ``Database`` tool.

Reuses ``applications.tools.database`` (WAL, foreign keys, re-entrant transactions, numbered
migrations with a pre-migration backup, online backups, integrity check) instead of
re-implementing a SQLite wrapper.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from contextlib import AbstractContextManager
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from applications.tools.database import Database

from slaifi.core.types import CurrencyCode
from slaifi.domain.goals import GoalSpec
from slaifi.domain.learning import RecommendationOutcome, RecommendationRecord
from slaifi.domain.ledger import (
    AuditEntry,
    Proposal,
    StoredCashFlow,
    StoredRejection,
    StoredTrade,
    ValuationPoint,
    WatchlistItem,
)
from slaifi.domain.paper import ExecutionDetails, PaperPortfolio, Rejection, RejectionCode
from slaifi.domain.portfolio import CashFlow, CashFlowKind, Portfolio, Trade, TradeSide
from slaifi.domain.strategies import StrategyProfile
from slaifi.infrastructure.persistence import codec
from slaifi.infrastructure.persistence.migrations import MIGRATIONS

_GENESIS = "0" * 64
_ACTIVE_STRATEGY_KEY = "active_strategy_id"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class SqliteFinanceStore:
    """Authoritative durable store. One instance per database file."""

    def __init__(self, path: Path | str, *, backups_dir: Path | str | None = None) -> None:
        self.path = Path(path)
        self._db = Database(self.path, MIGRATIONS, backups_dir=backups_dir)

    # ------------------------------------------------------------------ lifecycle
    def close(self) -> None:
        self._db.close()

    def transaction(self) -> AbstractContextManager[Any]:
        ctx: AbstractContextManager[Any] = self._db.transaction()
        return ctx

    def integrity(self) -> str:
        return str(self._db.integrity())

    def backup(self, label: str) -> str:
        return str(self._db.backup(label))

    @property
    def schema_version(self) -> int:
        return int(self._db.schema_version)

    # ------------------------------------------------------------------ portfolios
    def _portfolio_from(self, row: dict[str, Any]) -> PaperPortfolio:
        return PaperPortfolio(
            portfolio_id=row["portfolio_id"],
            name=row["name"],
            base_currency=CurrencyCode(row["base_currency"]),
            starting_capital=Decimal(row["starting_capital"]),
            created_at=codec.dt_from_text(row["created_at"]),
            strategy_id=row["strategy_id"],
            epoch=int(row["epoch"]),
        )

    def create_portfolio(self, portfolio: PaperPortfolio, initial_flow: CashFlow | None) -> None:
        with self._db.transaction():
            self._db.execute(
                "INSERT INTO portfolios (portfolio_id, name, base_currency, starting_capital, strategy_id, created_at, epoch)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    portfolio.portfolio_id,
                    portfolio.name,
                    str(portfolio.base_currency),
                    str(portfolio.starting_capital),
                    portfolio.strategy_id,
                    codec.dt_to_text(portfolio.created_at),
                    portfolio.epoch,
                ),
            )
            if initial_flow is not None:
                self.append_cash_flow(
                    portfolio.portfolio_id, initial_flow, note="Starting capital", origin="initial"
                )

    def list_portfolios(self) -> Sequence[PaperPortfolio]:
        rows = self._db.rows("SELECT * FROM portfolios ORDER BY created_at, portfolio_id")
        return tuple(self._portfolio_from(row) for row in rows)

    def get_portfolio(self, portfolio_id: str) -> PaperPortfolio | None:
        row = self._db.row("SELECT * FROM portfolios WHERE portfolio_id = ?", (portfolio_id,))
        return self._portfolio_from(row) if row else None

    def set_portfolio_strategy(self, portfolio_id: str, strategy_id: str | None) -> None:
        self._db.execute(
            "UPDATE portfolios SET strategy_id = ? WHERE portfolio_id = ?",
            (strategy_id, portfolio_id),
        )

    def _epoch(self, portfolio_id: str) -> int:
        epoch = self._db.scalar(
            "SELECT epoch FROM portfolios WHERE portfolio_id = ?", (portfolio_id,)
        )
        if epoch is None:
            raise KeyError(portfolio_id)
        return int(epoch)

    @staticmethod
    def _trade_from(row: dict[str, Any]) -> Trade:
        return Trade(
            trade_id=row["trade_id"],
            asset=codec.asset_from_dict(json.loads(row["asset_json"])),
            side=TradeSide(row["side"]),
            quantity=Decimal(row["quantity"]),
            unit_price=Decimal(row["unit_price"]),
            fee=Decimal(row["fee"]),
            occurred_at=codec.dt_from_text(row["occurred_at"]),
            currency=CurrencyCode(row["currency"]),
        )

    @staticmethod
    def _flow_from(row: dict[str, Any]) -> CashFlow:
        asset = codec.asset_from_dict(json.loads(row["asset_json"])) if row["asset_json"] else None
        return CashFlow(
            flow_id=row["flow_id"],
            kind=CashFlowKind(row["kind"]),
            amount=Decimal(row["amount"]),
            occurred_at=codec.dt_from_text(row["occurred_at"]),
            currency=CurrencyCode(row["currency"]),
            asset=asset,
        )

    def load_ledger(self, portfolio_id: str) -> Portfolio:
        meta = self.get_portfolio(portfolio_id)
        if meta is None:
            raise KeyError(portfolio_id)
        trades = tuple(s.trade for s in self.list_trades(portfolio_id))
        flows = tuple(s.flow for s in self.list_cash_flows(portfolio_id))
        return Portfolio(
            portfolio_id=meta.portfolio_id,
            name=meta.name,
            base_currency=meta.base_currency,
            trades=trades,
            cash_flows=flows,
        )

    def list_trades(self, portfolio_id: str) -> Sequence[StoredTrade]:

        epoch = self._epoch(portfolio_id)
        rows = self._db.rows(
            "SELECT rowid AS _r, * FROM trades WHERE portfolio_id = ? AND epoch = ? ORDER BY occurred_at, _r",
            (portfolio_id, epoch),
        )
        return tuple(self._stored_trade(row) for row in rows)

    def _stored_trade(self, row: dict[str, Any]) -> StoredTrade:

        execution = (
            codec.execution_from_dict(json.loads(row["execution_json"]))
            if row["execution_json"]
            else None
        )
        return StoredTrade(self._trade_from(row), row["client_order_id"], execution)

    def list_cash_flows(self, portfolio_id: str) -> Sequence[StoredCashFlow]:

        epoch = self._epoch(portfolio_id)
        rows = self._db.rows(
            "SELECT rowid AS _r, * FROM cash_flows WHERE portfolio_id = ? AND epoch = ? ORDER BY occurred_at, _r",
            (portfolio_id, epoch),
        )
        return tuple(StoredCashFlow(self._flow_from(r), r["note"], r["origin"]) for r in rows)

    def find_trade_by_client_order(
        self, portfolio_id: str, client_order_id: str
    ) -> StoredTrade | None:
        row = self._db.row(
            "SELECT * FROM trades WHERE portfolio_id = ? AND client_order_id = ?",
            (portfolio_id, client_order_id),
        )
        return self._stored_trade(row) if row else None

    def append_trade(
        self, portfolio_id: str, trade: Trade, client_order_id: str, execution: ExecutionDetails
    ) -> None:
        epoch = self._epoch(portfolio_id)
        self._db.execute(
            "INSERT INTO trades (trade_id, portfolio_id, epoch, client_order_id, asset_json, side, quantity, unit_price,"
            " fee, currency, occurred_at, execution_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trade.trade_id,
                portfolio_id,
                epoch,
                client_order_id,
                _canonical(codec.asset_to_dict(trade.asset)),
                trade.side.value,
                str(trade.quantity),
                str(trade.unit_price),
                str(trade.fee),
                str(trade.currency),
                codec.dt_to_text(trade.occurred_at),
                _canonical(codec.execution_to_dict(execution)),
            ),
        )

    def append_cash_flow(
        self, portfolio_id: str, flow: CashFlow, *, note: str | None = None, origin: str = "user"
    ) -> None:
        epoch = self._epoch(portfolio_id)
        self._db.execute(
            "INSERT INTO cash_flows (flow_id, portfolio_id, epoch, kind, amount, currency, occurred_at, asset_json, note, origin)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                flow.flow_id,
                portfolio_id,
                epoch,
                flow.kind.value,
                str(flow.amount),
                str(flow.currency),
                codec.dt_to_text(flow.occurred_at),
                _canonical(codec.asset_to_dict(flow.asset)) if flow.asset else None,
                note,
                origin,
            ),
        )

    def record_rejection(
        self,
        portfolio_id: str,
        client_order_id: str,
        at: datetime,
        summary: str,
        rejections: Sequence[Rejection],
    ) -> None:
        import uuid

        self._db.execute(
            "INSERT INTO rejected_orders (rejection_id, portfolio_id, client_order_id, occurred_at, summary, rejections_json)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                f"R-{uuid.uuid4().hex[:16]}",
                portfolio_id,
                client_order_id,
                codec.dt_to_text(at),
                summary,
                _canonical([{"code": r.code.value, "message": r.message} for r in rejections]),
            ),
        )

    def list_rejections(self, portfolio_id: str, limit: int = 50) -> Sequence[StoredRejection]:

        rows = self._db.rows(
            "SELECT * FROM rejected_orders WHERE portfolio_id = ? ORDER BY occurred_at DESC LIMIT ?",
            (portfolio_id, limit),
        )
        return tuple(
            StoredRejection(
                r["rejection_id"],
                r["client_order_id"],
                codec.dt_from_text(r["occurred_at"]),
                r["summary"],
                tuple(
                    Rejection(RejectionCode(x["code"]), x["message"])
                    for x in json.loads(r["rejections_json"])
                ),
            )
            for r in rows
        )

    def reset_portfolio(
        self,
        portfolio_id: str,
        *,
        starting_capital: Decimal,
        initial_flow: CashFlow | None,
        now: datetime,
    ) -> int:
        with self._db.transaction():
            epoch = self._epoch(portfolio_id) + 1
            self._db.execute(
                "UPDATE portfolios SET epoch = ?, starting_capital = ? WHERE portfolio_id = ?",
                (epoch, str(starting_capital), portfolio_id),
            )
            if initial_flow is not None:
                self.append_cash_flow(
                    portfolio_id, initial_flow, note="Starting capital after reset", origin="reset"
                )
        return epoch

    def delete_portfolio(self, portfolio_id: str) -> None:
        self._db.execute("DELETE FROM portfolios WHERE portfolio_id = ?", (portfolio_id,))

    # ------------------------------------------------------------------ valuation history
    def record_valuation(self, portfolio_id: str, point: ValuationPoint) -> None:
        self._db.execute(
            "INSERT INTO valuation_points (portfolio_id, epoch, at, total_value, net_flow, cash, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                portfolio_id,
                self._epoch(portfolio_id),
                codec.dt_to_text(point.at),
                str(point.total_value),
                str(point.net_flow),
                str(point.cash),
                point.source,
            ),
        )

    def list_valuations(self, portfolio_id: str, limit: int = 2000) -> Sequence[ValuationPoint]:

        rows = self._db.rows(
            "SELECT * FROM (SELECT * FROM valuation_points WHERE portfolio_id = ? AND epoch = ? ORDER BY at DESC, point_id DESC LIMIT ?)"
            " ORDER BY at, point_id",
            (portfolio_id, self._epoch(portfolio_id), limit),
        )
        return tuple(
            ValuationPoint(
                codec.dt_from_text(r["at"]),
                Decimal(r["total_value"]),
                Decimal(r["net_flow"]),
                Decimal(r["cash"]),
                r["source"],
            )
            for r in rows
        )

    # ------------------------------------------------------------------ strategies / goals / watchlist
    def save_strategy(self, strategy: StrategyProfile, *, now: datetime) -> None:
        body = _canonical(codec.strategy_to_dict(strategy))
        stamp = codec.dt_to_text(now)
        self._db.execute(
            "INSERT INTO strategies (strategy_id, name, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(strategy_id) DO UPDATE SET name = excluded.name, body = excluded.body, updated_at = excluded.updated_at",
            (strategy.strategy_id, strategy.name, body, stamp, stamp),
        )

    def list_strategies(self) -> Sequence[StrategyProfile]:
        rows = self._db.rows("SELECT body FROM strategies ORDER BY created_at, strategy_id")
        return tuple(codec.strategy_from_dict(json.loads(r["body"])) for r in rows)

    def get_strategy(self, strategy_id: str) -> StrategyProfile | None:
        row = self._db.row("SELECT body FROM strategies WHERE strategy_id = ?", (strategy_id,))
        return codec.strategy_from_dict(json.loads(row["body"])) if row else None

    def delete_strategy(self, strategy_id: str) -> None:
        self._db.execute("DELETE FROM strategies WHERE strategy_id = ?", (strategy_id,))

    def get_active_strategy_id(self) -> str | None:
        value = self._db.scalar("SELECT value FROM settings WHERE key = ?", (_ACTIVE_STRATEGY_KEY,))
        return str(value) if value is not None else None

    def set_active_strategy_id(self, strategy_id: str) -> None:
        self._db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_ACTIVE_STRATEGY_KEY, strategy_id),
        )

    def get_setting(self, key: str) -> str | None:
        value = self._db.scalar("SELECT value FROM settings WHERE key = ?", (key,))
        return str(value) if value is not None else None

    def set_setting(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def save_goal(self, goal: GoalSpec) -> None:
        self._db.execute(
            "INSERT INTO goals (goal_id, body) VALUES (?, ?) ON CONFLICT(goal_id) DO UPDATE SET body = excluded.body",
            (goal.goal_id, _canonical(codec.goal_to_dict(goal))),
        )

    def list_goals(self) -> Sequence[GoalSpec]:
        rows = self._db.rows("SELECT body FROM goals ORDER BY rowid")
        return tuple(codec.goal_from_dict(json.loads(r["body"])) for r in rows)

    def get_goal(self, goal_id: str) -> GoalSpec | None:
        row = self._db.row("SELECT body FROM goals WHERE goal_id = ?", (goal_id,))
        return codec.goal_from_dict(json.loads(row["body"])) if row else None

    # ------------------------------------------------------------------ recommendation log
    def log_recommendation(self, record: RecommendationRecord) -> bool:
        key = f"{record.symbol}|{record.strategy_id}|{record.issued_at.date().isoformat()}"
        if self._db.row("SELECT 1 AS x FROM recommendation_log WHERE dedupe_key = ?", (key,)):
            return False
        self._db.execute(
            "INSERT INTO recommendation_log (record_id, dedupe_key, issued_at, body) VALUES (?, ?, ?, ?)",
            (
                record.record_id,
                key,
                codec.dt_to_text(record.issued_at),
                _canonical(codec.recommendation_to_dict(record)),
            ),
        )
        return True

    def list_pending_recommendations(
        self, issued_before: datetime, limit: int = 200
    ) -> Sequence[RecommendationRecord]:
        rows = self._db.rows(
            "SELECT body FROM recommendation_log WHERE outcome IS NULL AND issued_at <= ? ORDER BY issued_at LIMIT ?",
            (codec.dt_to_text(issued_before), limit),
        )
        return tuple(codec.recommendation_from_dict(json.loads(r["body"])) for r in rows)

    def save_recommendation_outcome(self, outcome: RecommendationOutcome) -> None:
        self._db.execute(
            "UPDATE recommendation_log SET outcome = ? WHERE record_id = ?",
            (_canonical(codec.outcome_to_dict(outcome)), outcome.record_id),
        )

    def list_recommendation_history(
        self, limit: int = 2000
    ) -> Sequence[tuple[RecommendationRecord, RecommendationOutcome | None]]:
        rows = self._db.rows(
            "SELECT body, outcome FROM recommendation_log ORDER BY issued_at DESC LIMIT ?",
            (limit,),
        )
        return tuple(
            (
                codec.recommendation_from_dict(json.loads(r["body"])),
                codec.outcome_from_dict(json.loads(r["outcome"])) if r["outcome"] else None,
            )
            for r in rows
        )

    def delete_goal(self, goal_id: str) -> None:
        self._db.execute("DELETE FROM goals WHERE goal_id = ?", (goal_id,))

    def list_watchlist(self) -> Sequence[WatchlistItem]:

        rows = self._db.rows("SELECT * FROM watchlist ORDER BY added_at, symbol")
        return tuple(
            WatchlistItem(
                codec.asset_from_dict(json.loads(r["asset_json"])),
                r["name"],
                codec.dt_from_text(r["added_at"]),
            )
            for r in rows
        )

    def add_watchlist(self, item: WatchlistItem) -> None:
        self._db.execute(
            "INSERT OR REPLACE INTO watchlist (symbol, exchange, asset_json, name, added_at) VALUES (?, ?, ?, ?, ?)",
            (
                item.asset.symbol,
                item.asset.exchange or "",
                _canonical(codec.asset_to_dict(item.asset)),
                item.name,
                codec.dt_to_text(item.added_at),
            ),
        )

    def remove_watchlist(self, symbol: str, exchange: str | None) -> bool:
        if exchange:
            cursor = self._db.execute(
                "DELETE FROM watchlist WHERE symbol = ? AND exchange = ?",
                (symbol.upper(), exchange.upper()),
            )
        else:  # no exchange given: remove the instrument whichever listing it was saved under
            cursor = self._db.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol.upper(),))
        return bool(cursor.rowcount > 0)

    # ------------------------------------------------------------------ proposals
    def save_proposal(self, proposal: Proposal) -> None:
        self._db.execute(
            "INSERT INTO proposals (proposal_id, created_at, expires_at, kind, text, payload, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                proposal.proposal_id,
                codec.dt_to_text(proposal.created_at),
                codec.dt_to_text(proposal.expires_at),
                proposal.kind,
                proposal.text,
                _canonical(proposal.payload),
                proposal.status,
            ),
        )

    def get_proposal(self, proposal_id: str) -> Proposal | None:

        row = self._db.row("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,))
        if row is None:
            return None
        return Proposal(
            row["proposal_id"],
            codec.dt_from_text(row["created_at"]),
            codec.dt_from_text(row["expires_at"]),
            row["kind"],
            row["text"],
            json.loads(row["payload"]),
            row["status"],
        )

    def set_proposal_status(self, proposal_id: str, status: str) -> None:
        self._db.execute(
            "UPDATE proposals SET status = ? WHERE proposal_id = ?", (status, proposal_id)
        )

    # ------------------------------------------------------------------ audit log (hash chained)
    @staticmethod
    def _entry_hash(
        prev: str, seq: int, at: str, actor: str, action: str, subject: str, detail: str
    ) -> str:
        return hashlib.sha256(
            _canonical([prev, seq, at, actor, action, subject, detail]).encode("utf-8")
        ).hexdigest()

    def append_audit(
        self, *, at: datetime, actor: str, action: str, subject: str, detail: dict[str, Any]
    ) -> AuditEntry:

        with self._db.transaction():
            last = self._db.row("SELECT seq, hash FROM audit_log ORDER BY seq DESC LIMIT 1")
            seq = (int(last["seq"]) + 1) if last else 1
            prev = last["hash"] if last else _GENESIS
            stamp = codec.dt_to_text(at)
            body = _canonical(detail)
            digest = self._entry_hash(prev, seq, stamp, actor, action, subject, body)
            self._db.execute(
                "INSERT INTO audit_log (seq, at, actor, action, subject, detail, prev_hash, hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (seq, stamp, actor, action, subject, body, prev, digest),
            )
        return AuditEntry(seq, at, actor, action, subject, detail, digest)

    def list_audit(self, limit: int = 100, subject: str | None = None) -> Sequence[AuditEntry]:

        if subject:
            rows = self._db.rows(
                "SELECT * FROM audit_log WHERE subject = ? ORDER BY seq DESC LIMIT ?",
                (subject, limit),
            )
        else:
            rows = self._db.rows("SELECT * FROM audit_log ORDER BY seq DESC LIMIT ?", (limit,))
        return tuple(
            AuditEntry(
                r["seq"],
                codec.dt_from_text(r["at"]),
                r["actor"],
                r["action"],
                r["subject"],
                json.loads(r["detail"]),
                r["hash"],
            )
            for r in rows
        )

    def verify_audit_chain(self) -> tuple[bool, str | None]:
        prev = _GENESIS
        expected = 1
        for row in self._db.rows("SELECT * FROM audit_log ORDER BY seq"):
            if row["seq"] != expected:
                return False, f"audit entry {expected} is missing (found {row['seq']})"
            if row["prev_hash"] != prev:
                return False, f"audit entry {row['seq']} does not link to its predecessor"
            digest = self._entry_hash(
                prev,
                row["seq"],
                row["at"],
                row["actor"],
                row["action"],
                row["subject"],
                row["detail"],
            )
            if digest != row["hash"]:
                return False, f"audit entry {row['seq']} was modified"
            prev = row["hash"]
            expected += 1
        return True, None
