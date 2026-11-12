"""Durable ledger records shared by the application ports and their adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from slaifi.domain.assets import AssetId
from slaifi.domain.paper import ExecutionDetails, Rejection
from slaifi.domain.portfolio import CashFlow, Trade


@dataclass(frozen=True, slots=True)
class StoredTrade:
    trade: Trade
    client_order_id: str
    execution: ExecutionDetails | None = None


@dataclass(frozen=True, slots=True)
class StoredCashFlow:
    flow: CashFlow
    note: str | None = None
    origin: str = "user"  # initial | user | reset


@dataclass(frozen=True, slots=True)
class StoredRejection:
    rejection_id: str
    client_order_id: str
    occurred_at: datetime
    summary: str
    rejections: tuple[Rejection, ...]


@dataclass(frozen=True, slots=True)
class ValuationPoint:
    at: datetime
    total_value: Decimal
    net_flow: Decimal
    cash: Decimal
    source: str


@dataclass(frozen=True, slots=True)
class AuditEntry:
    seq: int
    at: datetime
    actor: str
    action: str
    subject: str
    detail: dict[str, Any]
    hash: str


@dataclass(frozen=True, slots=True)
class Proposal:
    proposal_id: str
    created_at: datetime
    expires_at: datetime
    kind: str
    text: str
    payload: dict[str, Any]
    status: str = "pending"  # pending | applied | rejected | expired


@dataclass(frozen=True, slots=True)
class WatchlistItem:
    asset: AssetId
    name: str | None
    added_at: datetime
