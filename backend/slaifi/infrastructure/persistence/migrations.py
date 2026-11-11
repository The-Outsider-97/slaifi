"""Versioned SQLite schema for the SLAIFI ledger (applied by SLAI's shared Database tool)."""

from __future__ import annotations

from applications.tools.database import Migration

_V1 = (
    """CREATE TABLE portfolios (
        portfolio_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        base_currency TEXT NOT NULL,
        starting_capital TEXT NOT NULL,
        strategy_id TEXT,
        created_at TEXT NOT NULL,
        epoch INTEGER NOT NULL DEFAULT 1
    )""",
    """CREATE TABLE cash_flows (
        flow_id TEXT PRIMARY KEY,
        portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
        epoch INTEGER NOT NULL,
        kind TEXT NOT NULL,
        amount TEXT NOT NULL,
        currency TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        asset_json TEXT,
        note TEXT,
        origin TEXT NOT NULL DEFAULT 'user'
    )""",
    "CREATE INDEX idx_cash_flows_portfolio ON cash_flows(portfolio_id, epoch, occurred_at)",
    """CREATE TABLE trades (
        trade_id TEXT PRIMARY KEY,
        portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
        epoch INTEGER NOT NULL,
        client_order_id TEXT NOT NULL,
        asset_json TEXT NOT NULL,
        side TEXT NOT NULL,
        quantity TEXT NOT NULL,
        unit_price TEXT NOT NULL,
        fee TEXT NOT NULL,
        currency TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        execution_json TEXT,
        UNIQUE (portfolio_id, client_order_id)
    )""",
    "CREATE INDEX idx_trades_portfolio ON trades(portfolio_id, epoch, occurred_at)",
    """CREATE TABLE rejected_orders (
        rejection_id TEXT PRIMARY KEY,
        portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
        client_order_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        summary TEXT NOT NULL,
        rejections_json TEXT NOT NULL
    )""",
    """CREATE TABLE valuation_points (
        point_id INTEGER PRIMARY KEY AUTOINCREMENT,
        portfolio_id TEXT NOT NULL REFERENCES portfolios(portfolio_id) ON DELETE CASCADE,
        epoch INTEGER NOT NULL,
        at TEXT NOT NULL,
        total_value TEXT NOT NULL,
        net_flow TEXT NOT NULL,
        cash TEXT NOT NULL,
        source TEXT NOT NULL
    )""",
    "CREATE INDEX idx_valuation_portfolio ON valuation_points(portfolio_id, epoch, at)",
    """CREATE TABLE strategies (
        strategy_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    """CREATE TABLE goals (
        goal_id TEXT PRIMARY KEY,
        body TEXT NOT NULL
    )""",
    """CREATE TABLE watchlist (
        symbol TEXT NOT NULL,
        exchange TEXT NOT NULL DEFAULT '',
        asset_json TEXT NOT NULL,
        name TEXT,
        added_at TEXT NOT NULL,
        PRIMARY KEY (symbol, exchange)
    )""",
    """CREATE TABLE proposals (
        proposal_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        kind TEXT NOT NULL,
        text TEXT NOT NULL,
        payload TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
    )""",
    """CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )""",
    """CREATE TABLE audit_log (
        seq INTEGER PRIMARY KEY,
        at TEXT NOT NULL,
        actor TEXT NOT NULL,
        action TEXT NOT NULL,
        subject TEXT NOT NULL,
        detail TEXT NOT NULL,
        prev_hash TEXT NOT NULL,
        hash TEXT NOT NULL
    )""",
    "CREATE INDEX idx_audit_subject ON audit_log(subject, seq)",
)

MIGRATIONS: tuple[Migration, ...] = (Migration(1, "initial SLAIFI ledger schema", _V1),)
