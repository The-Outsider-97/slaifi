"""Portfolio ledger and calculated portfolio state domain objects."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetId
from slaifi.domain.utils import DomainValidationError, require_aware_datetime, require_non_blank

# Simulated margin: the proceeds of a short sale stay locked as collateral and a further 50 % of the
# short's value must be held in cash (the common 150 % initial requirement). A deliberate
# simplification: no borrow fee, no recall, no dividends owed on the borrowed shares.
SHORT_MARGIN_RATE = Decimal("1.5")


class TradeSide(StrEnum):
    BUY = "buy"  # open or add to a long position
    SELL = "sell"  # reduce or close a long position
    SHORT = "short"  # sell borrowed shares to open or add to a short position
    COVER = "cover"  # buy back shares to reduce or close a short position

    @property
    def opens_or_adds_cash(self) -> bool:
        """True when the trade brings cash in (a sell or a short sale)."""
        return self in (TradeSide.SELL, TradeSide.SHORT)


class CashFlowKind(StrEnum):
    CONTRIBUTION = "contribution"
    WITHDRAWAL = "withdrawal"
    DIVIDEND = "dividend"
    FEE = "fee"


@dataclass(frozen=True, slots=True)
class Trade:
    """Executed simulated trade (long or short)."""

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
    """Aggregated position calculated from the trade ledger.

    ``quantity`` is signed: positive for a long position, negative for a short one. For a short,
    ``average_cost`` is the average price (net of fees) at which the shares were sold.
    """

    asset: AssetId
    quantity: Decimal
    average_cost: Decimal
    realized_pnl: Decimal
    currency: CurrencyCode

    def __post_init__(self) -> None:
        if self.average_cost < 0:
            raise DomainValidationError("average_cost cannot be negative")
        if self.quantity == 0 and self.average_cost != 0:
            raise DomainValidationError("closed positions must have zero average_cost")
        if not isinstance(self.currency, CurrencyCode):
            object.__setattr__(self, "currency", CurrencyCode(str(self.currency)))

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def cost_basis(self) -> Decimal:
        """Amount paid (long) or received (short) at the average price, always non-negative."""
        return abs(self.quantity) * self.average_cost


@dataclass(frozen=True, slots=True)
class PositionValuation:
    """Point-in-time valuation for one position.

    ``market_value`` carries the sign of the position: a short is a liability, so its value is
    negative and reduces the portfolio total.
    """

    position: Position
    market_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    portfolio_weight: float | None

    def __post_init__(self) -> None:
        if self.market_price <= 0:
            raise DomainValidationError("market_price must be positive")
        if (self.market_value < 0) != (self.position.quantity < 0) and self.market_value != 0:
            raise DomainValidationError("market_value must have the same sign as the position")
        if self.portfolio_weight is not None and not -10.0 <= self.portfolio_weight <= 10.0:
            raise DomainValidationError("portfolio_weight is outside any plausible range")


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
        if self.total_value != self.cash_balance + self.securities_market_value:
            raise DomainValidationError("total_value must equal cash plus securities market value")

    @property
    def short_value(self) -> Decimal:
        """Current market value of every short position (a positive amount owed)."""
        return sum((-v.market_value for v in self.positions if v.market_value < 0), Decimal(0))

    @property
    def margin_required(self) -> Decimal:
        return self.short_value * SHORT_MARGIN_RATE

    @property
    def free_cash(self) -> Decimal:
        """Cash that is not locked as collateral for short positions (may be negative)."""
        return self.cash_balance - self.margin_required

    @property
    def has_shorts(self) -> bool:
        return any(v.position.quantity < 0 for v in self.positions)
