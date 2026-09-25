"""Portfolio ledger and calculated portfolio state domain objects."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetId
from slaifi.domain.utils import DomainValidationError, require_aware_datetime, require_non_blank


class TradeSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class CashFlowKind(StrEnum):
    CONTRIBUTION = "contribution"
    WITHDRAWAL = "withdrawal"
    DIVIDEND = "dividend"
    FEE = "fee"


@dataclass(frozen=True, slots=True)
class Trade:
    """Executed long-portfolio trade used by the initial accounting engine."""

    trade_id: str
    asset: AssetId
    side: TradeSide
    quantity: Decimal
    unit_price: Decimal
    fee: Decimal
    occurred_at: datetime
    currency: CurrencyCode

    def __post_init__(self) -> None:
        require_non_blank(self.trade_id, name="trade_id")
        if self.quantity <= 0:
            raise DomainValidationError("trade quantity must be positive")
        if self.unit_price <= 0:
            raise DomainValidationError("trade unit_price must be positive")
        if self.fee < 0:
            raise DomainValidationError("trade fee must be non-negative")
        require_aware_datetime(self.occurred_at, name="occurred_at")
        if not isinstance(self.currency, CurrencyCode):
            object.__setattr__(self, "currency", CurrencyCode(str(self.currency)))


@dataclass(frozen=True, slots=True)
class CashFlow:
    """Non-trade portfolio cash movement."""

    flow_id: str
    kind: CashFlowKind
    amount: Decimal
    occurred_at: datetime
    currency: CurrencyCode
    asset: AssetId | None = None

    def __post_init__(self) -> None:
        require_non_blank(self.flow_id, name="flow_id")
        if self.amount <= 0:
            raise DomainValidationError("cash-flow amount must be positive")
        require_aware_datetime(self.occurred_at, name="occurred_at")
        if not isinstance(self.currency, CurrencyCode):
            object.__setattr__(self, "currency", CurrencyCode(str(self.currency)))
        if self.kind is CashFlowKind.DIVIDEND and self.asset is None:
            raise DomainValidationError("dividend cash flows must identify an asset")


@dataclass(frozen=True, slots=True)
class Portfolio:
    """Provider- and persistence-neutral portfolio ledger."""

    portfolio_id: str
    name: str
    base_currency: CurrencyCode
    trades: tuple[Trade, ...] = ()
    cash_flows: tuple[CashFlow, ...] = ()

    def __post_init__(self) -> None:
        require_non_blank(self.portfolio_id, name="portfolio_id")
        require_non_blank(self.name, name="portfolio name")
        if not isinstance(self.base_currency, CurrencyCode):
            object.__setattr__(self, "base_currency", CurrencyCode(str(self.base_currency)))


@dataclass(frozen=True, slots=True)
class Position:
    """Aggregated long position calculated from the trade ledger."""

    asset: AssetId
    quantity: Decimal
    average_cost: Decimal
    realized_pnl: Decimal
    currency: CurrencyCode

    def __post_init__(self) -> None:
        if self.quantity < 0:
            raise DomainValidationError("position quantity cannot be negative")
        if self.average_cost < 0:
            raise DomainValidationError("average_cost cannot be negative")
        if self.quantity == 0 and self.average_cost != 0:
            raise DomainValidationError("closed positions must have zero average_cost")
        if not isinstance(self.currency, CurrencyCode):
            object.__setattr__(self, "currency", CurrencyCode(str(self.currency)))

    @property
    def cost_basis(self) -> Decimal:
        return self.quantity * self.average_cost


@dataclass(frozen=True, slots=True)
class PositionValuation:
    """Point-in-time valuation for one position."""

    position: Position
    market_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    portfolio_weight: float | None

    def __post_init__(self) -> None:
        if self.market_price <= 0:
            raise DomainValidationError("market_price must be positive")
        if self.market_value < 0:
            raise DomainValidationError("market_value cannot be negative")
        if self.portfolio_weight is not None and not 0.0 <= self.portfolio_weight <= 1.0:
            raise DomainValidationError("portfolio_weight must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class PortfolioSnapshot:
    """Calculated portfolio state at a declared point in time."""

    portfolio_id: str
    as_of: datetime
    base_currency: CurrencyCode
    cash_balance: Decimal
    positions: tuple[PositionValuation, ...]
    securities_market_value: Decimal
    total_value: Decimal

    def __post_init__(self) -> None:
        require_aware_datetime(self.as_of, name="as_of")
        if not isinstance(self.base_currency, CurrencyCode):
            object.__setattr__(self, "base_currency", CurrencyCode(str(self.base_currency)))
        if self.securities_market_value < 0:
            raise DomainValidationError("securities_market_value cannot be negative")
        if self.total_value != self.cash_balance + self.securities_market_value:
            raise DomainValidationError("total_value must equal cash plus securities market value")
