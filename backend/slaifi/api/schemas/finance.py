"""Request bodies for the finance routes. Responses are built by :mod:`slaifi.api.serializers`."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WatchlistAdd(_Body):
    symbol: str = Field(min_length=1, max_length=32)
    exchange: str | None = Field(default=None, max_length=16)


class ScreenRequest(_Body):
    symbols: list[str] = Field(min_length=1, max_length=20)
    strategy_id: str | None = None
    portfolio_id: str | None = None


class CreatePortfolio(_Body):
    name: str = Field(min_length=1, max_length=60)
    starting_capital: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    strategy_id: str | None = None


class CashRequest(_Body):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    note: str | None = Field(default=None, max_length=200)


class ApplyAllocation(_Body):
    """Which suggested orders to place. ``symbols`` empty or missing means all of them."""

    suggestion_id: str = Field(min_length=3, max_length=40)
    symbols: list[str] | None = Field(default=None, max_length=20)


class PlatformFeesBody(_Body):
    """Either fee may be sent on its own; zero means the platform charges nothing."""

    per_trade: Decimal | None = Field(default=None, ge=0, le=1000, max_digits=8, decimal_places=2)
    per_withdrawal: Decimal | None = Field(
        default=None, ge=0, le=1000, max_digits=8, decimal_places=2
    )


class OrderRequestBody(_Body):
    symbol: str = Field(min_length=1, max_length=32)
    side: str = Field(pattern="^(buy|sell|short|cover)$")
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=8)
    notional: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    close_position: bool = False
    client_order_id: str | None = Field(default=None, min_length=1, max_length=80)
    exchange: str | None = Field(default=None, max_length=16)
    asset_class: str | None = Field(default=None, max_length=16)


class ResetRequest(_Body):
    confirm: bool = False
    starting_capital: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)


class PortfolioStrategy(_Body):
    strategy_id: str | None = None


class StrategyCreate(_Body):
    name: str = Field(min_length=1, max_length=60)
    preset_id: str | None = None
    fields: dict[str, Any] = Field(default_factory=dict)
    activate: bool = False


class StrategyUpdate(_Body):
    fields: dict[str, Any] = Field(min_length=1)
    acknowledge_loosening: bool = False


class GoalCreate(_Body):
    name: str = Field(min_length=1, max_length=80)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    basis: str | None = None
    target_amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    period: str | None = None
    target_value: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    target_annual_rate: float | None = Field(default=None, gt=-1, le=10)
    horizon_years: float | None = Field(default=None, gt=0, le=100)
    starting_capital: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    monthly_contribution: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=2
    )
    monthly_withdrawal: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    risk_tolerance: str | None = None
    max_acceptable_drawdown_rate: float | None = Field(default=None, gt=0, le=1)
    portfolio_id: str | None = None


class GoalAnalyze(_Body):
    assumed_annual_return_rate: float | None = Field(default=None, gt=-1, le=10)
    portfolio_id: str | None = None


class AdvisorRequest(_Body):
    text: str = Field(min_length=1, max_length=2000)
    portfolio_id: str | None = None
    explain: bool = True


class AdvisorConfirm(_Body):
    acknowledge_limit_changes: bool = False
    acknowledge_contradictions: bool = False


class ProviderKey(BaseModel):
    """A market-data API key typed into Settings. Never returned by any endpoint."""

    key: SecretStr = Field(max_length=512, repr=False)


class AgentSwitch(_Body):
    enabled: bool
