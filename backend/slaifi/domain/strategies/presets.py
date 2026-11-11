"""Strategy presets.

Each preset only initialises explicit numeric parameters. The numbers are product defaults,
not forecasts and not personalised advice; users are expected to review and change them.
"""

from __future__ import annotations

from dataclasses import replace

from slaifi.domain.assets import AssetClass
from slaifi.domain.goals import RiskConstraints
from slaifi.domain.strategies.models import (
    RiskTolerance,
    StrategyProfile,
    TradingFrequency,
    TransactionCosts,
)

PRESET_IDS: tuple[str, ...] = (
    "short_term_hawkish",
    "short_term_care_bear",
    "long_term_hawkish",
    "long_term_care_bear",
)


def _presets() -> dict[str, StrategyProfile]:
    costs = TransactionCosts()
    return {
        "short_term_hawkish": StrategyProfile(
            strategy_id="short_term_hawkish",
            name="Short-term · Hawkish",
            preset="short_term_hawkish",
            risk_tolerance=RiskTolerance.AGGRESSIVE,
            horizon_days=30,
            constraints=RiskConstraints(
                max_drawdown_rate=0.25,
                max_position_weight=0.30,
                max_leverage=1.0,
                max_short_exposure=0.0,
            ),
            max_concentration_hhi=0.40,
            cash_reserve_rate=0.05,
            max_annualized_volatility=0.60,
            trading_frequency=TradingFrequency.HIGH,
            costs=costs,
            reinvest_dividends=True,
            income_weight=0.0,
        ),
        "short_term_care_bear": StrategyProfile(
            strategy_id="short_term_care_bear",
            name="Short-term · Care-Bear",
            preset="short_term_care_bear",
            risk_tolerance=RiskTolerance.CONSERVATIVE,
            horizon_days=90,
            constraints=RiskConstraints(
                max_drawdown_rate=0.08,
                max_position_weight=0.10,
                max_leverage=1.0,
                max_short_exposure=0.0,
                prohibited_asset_classes=frozenset({AssetClass.CRYPTO}),
            ),
            max_concentration_hhi=0.20,
            cash_reserve_rate=0.20,
            max_annualized_volatility=0.25,
            preferred_asset_classes=frozenset({AssetClass.ETF, AssetClass.INDEX}),
            trading_frequency=TradingFrequency.LOW,
            costs=costs,
            reinvest_dividends=True,
            income_weight=0.3,
        ),
        "long_term_hawkish": StrategyProfile(
            strategy_id="long_term_hawkish",
            name="Long-term · Hawkish",
            preset="long_term_hawkish",
            risk_tolerance=RiskTolerance.AGGRESSIVE,
            horizon_days=1826,
            constraints=RiskConstraints(
                max_drawdown_rate=0.35,
                max_position_weight=0.25,
                max_leverage=1.0,
                max_short_exposure=0.0,
            ),
            max_concentration_hhi=0.30,
            cash_reserve_rate=0.05,
            max_annualized_volatility=0.50,
            trading_frequency=TradingFrequency.MEDIUM,
            costs=costs,
            reinvest_dividends=True,
            income_weight=0.0,
        ),
        "long_term_care_bear": StrategyProfile(
            strategy_id="long_term_care_bear",
            name="Long-term · Care-Bear",
            preset="long_term_care_bear",
            risk_tolerance=RiskTolerance.CONSERVATIVE,
            horizon_days=3650,
            constraints=RiskConstraints(
                max_drawdown_rate=0.15,
                max_position_weight=0.10,
                max_leverage=1.0,
                max_short_exposure=0.0,
                prohibited_asset_classes=frozenset({AssetClass.CRYPTO}),
            ),
            max_concentration_hhi=0.15,
            cash_reserve_rate=0.10,
            max_annualized_volatility=0.25,
            preferred_asset_classes=frozenset({AssetClass.ETF, AssetClass.INDEX}),
            trading_frequency=TradingFrequency.LOW,
            costs=costs,
            reinvest_dividends=True,
            income_weight=0.3,
        ),
    }


def list_presets() -> tuple[StrategyProfile, ...]:
    presets = _presets()
    return tuple(presets[preset_id] for preset_id in PRESET_IDS)


def get_preset(preset_id: str) -> StrategyProfile:
    presets = _presets()
    if preset_id not in presets:
        raise KeyError(preset_id)
    return presets[preset_id]


def instantiate_preset(
    preset_id: str, *, strategy_id: str, name: str | None = None
) -> StrategyProfile:
    """Copy a preset into an editable strategy with a new identity."""

    base = get_preset(preset_id)
    return replace(base, strategy_id=strategy_id, name=name or base.name)


DEFAULT_PRESET_ID = "long_term_care_bear"
