"""Paper-trading vocabulary. Nothing here can place a real-money order."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from slaifi.core.types import CurrencyCode
from slaifi.domain.assets import AssetId
from slaifi.domain.portfolio import Trade, TradeSide
from slaifi.domain.utils import DomainValidationError, require_aware_datetime, require_non_blank


class OrderStatus(StrEnum):
    FILLED = "filled"
    REJECTED = "rejected"


class RejectionCode(StrEnum):
    INVALID_ORDER = "invalid_order"
    QUOTE_UNAVAILABLE = "quote_unavailable"
    QUOTE_STALE = "quote_stale"
    MARKET_CLOSED = "market_closed"
    QUOTE_LAST_KNOWN = "quote_last_known"
    CURRENCY_MISMATCH = "currency_mismatch"
    INSUFFICIENT_CASH = "insufficient_cash"
    INSUFFICIENT_POSITION = "insufficient_position"
    INSUFFICIENT_MARGIN = "insufficient_margin"
    SHORT_NOT_ALLOWED = "short_not_allowed"
    WRONG_DIRECTION = "wrong_direction"
    QUANTITY_TOO_SMALL = "quantity_too_small"
    STRATEGY_CONSTRAINT = "strategy_constraint"
    DUPLICATE_ORDER = "duplicate_order"


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    """How a simulated market order is priced and when it must be refused."""

    max_quote_age_seconds: int = 900
    allow_closed_market: bool = False
    quantity_decimals: int = 4

    def __post_init__(self) -> None:
        if self.max_quote_age_seconds <= 0:
            raise DomainValidationError("max_quote_age_seconds must be positive")
        if not 0 <= self.quantity_decimals <= 8:
            raise DomainValidationError("quantity_decimals must be between 0 and 8")


MAX_PLATFORM_FEE = Decimal("1000")


@dataclass(frozen=True, slots=True)
class PlatformFees:
    """What the trading platform charges: a flat amount per trade and per withdrawal.

    These are cash amounts in the portfolio's currency (not percentages) and are chosen by the
    person to mirror the platform they trade on. They sit on top of the strategy's proportional
    slippage and commission assumptions.
    """

    per_trade: Decimal
    per_withdrawal: Decimal

    @classmethod
    def none(cls) -> PlatformFees:
        return cls(Decimal("0"), Decimal("0"))

    def __post_init__(self) -> None:
        for name, value in (("per_trade", self.per_trade), ("per_withdrawal", self.per_withdrawal)):
            if not value.is_finite() or value < 0:
                raise DomainValidationError(f"{name} fee must be zero or a positive amount")
            if value > MAX_PLATFORM_FEE:
                raise DomainValidationError(f"{name} fee cannot exceed {MAX_PLATFORM_FEE}")


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """A simulated market order. Exactly one sizing mode must be used."""

    portfolio_id: str
    asset: AssetId
    side: TradeSide
    client_order_id: str
    quantity: Decimal | None = None
    notional: Decimal | None = None
    close_position: bool = False

    def __post_init__(self) -> None:
        require_non_blank(self.portfolio_id, name="portfolio_id")
        require_non_blank(self.client_order_id, name="client_order_id")
        modes = sum(
            (
                self.quantity is not None,
                self.notional is not None,
                self.close_position,
            )
        )
        if modes != 1:
            raise DomainValidationError(
                "specify exactly one of quantity, notional, or close_position"
            )
        if self.quantity is not None and self.quantity <= 0:
            raise DomainValidationError("quantity must be positive")
        if self.notional is not None and self.notional <= 0:
            raise DomainValidationError("notional must be positive")
        if self.close_position and self.side not in (TradeSide.SELL, TradeSide.COVER):
            raise DomainValidationError("close_position is only valid for sell or cover orders")


@dataclass(frozen=True, slots=True)
class Rejection:
    code: RejectionCode
    message: str


@dataclass(frozen=True, slots=True)
class ExecutionDetails:
    """Audit record separating the provider quotation from the simulated fill."""

    quote_price: Decimal
    execution_price: Decimal
    slippage_per_unit: Decimal
    commission: Decimal
    gross_amount: Decimal
    net_cash_effect: Decimal
    currency: CurrencyCode
    quote_observed_at: datetime
    quote_source: str
    data_mode: str
    executed_at: datetime
    market_open: bool | None
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_aware_datetime(self.quote_observed_at, name="quote_observed_at")
        require_aware_datetime(self.executed_at, name="executed_at")


@dataclass(frozen=True, slots=True)
class OrderDecision:
    status: OrderStatus
    request: OrderRequest
    trade: Trade | None = None
    execution: ExecutionDetails | None = None
    rejections: tuple[Rejection, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status is OrderStatus.FILLED and (self.trade is None or self.execution is None):
            raise DomainValidationError("a filled order requires a trade and execution details")
        if self.status is OrderStatus.REJECTED and not self.rejections:
            raise DomainValidationError("a rejected order requires at least one reason")


@dataclass(frozen=True, slots=True)
class PaperPortfolio:
    """Identity and configuration of a simulated portfolio (the ledger itself is separate)."""

    portfolio_id: str
    name: str
    base_currency: CurrencyCode
    starting_capital: Decimal
    created_at: datetime
    strategy_id: str | None = None
    epoch: int = 1  # incremented by every confirmed reset; the ledger only counts the current epoch

    def __post_init__(self) -> None:
        require_non_blank(self.portfolio_id, name="portfolio_id")
        require_non_blank(self.name, name="portfolio name")
        require_aware_datetime(self.created_at, name="created_at")
        if not isinstance(self.base_currency, CurrencyCode):
            object.__setattr__(self, "base_currency", CurrencyCode(str(self.base_currency)))
        if self.starting_capital < 0:
            raise DomainValidationError("starting_capital cannot be negative")
        if self.epoch < 1:
            raise DomainValidationError("epoch must be at least 1")
