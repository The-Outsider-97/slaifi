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
    "short_term_balanced",
    "long_term_hawkish",
    "long_term_care_bear",
    "long_term_growth",
    "balanced_core",
    "dividend_income",
    "capital_preservation",
    "steady_accumulation",
)

# One plain sentence per preset: who it is for and what its limits do. Never a promise of results.
PRESET_DESCRIPTIONS: dict[str, str] = {
    "short_term_hawkish": "Active, about a month. Accepts large swings and concentrated positions.",
    "short_term_care_bear": "About three months with tight limits and a large cash cushion.",
    "short_term_balanced": "Three to six months, moderate swings, trades roughly weekly.",
    "long_term_hawkish": "Five years. Accepts deep drops for growth; light on income.",
    "long_term_care_bear": "Ten years, small positions, broad funds, modest income tilt.",
    "long_term_growth": "Five years of equity-led growth with moderate limits and no income focus.",
    "balanced_core": "Three years. Middle-of-the-road limits for a mix of growth and income.",
    "dividend_income": "Five years leaning on dividend and interest income; small positions.",
    "capital_preservation": "One year, very tight loss limit and large cash share. Protects first.",
    "steady_accumulation": "Ten years of patient, low-turnover buying with dividends reinvested.",
}


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
        "short_term_balanced": StrategyProfile(
            strategy_id="short_term_balanced",
            name="Short-term · Balanced",
            preset="short_term_balanced",
            risk_tolerance=RiskTolerance.MODERATE,
            horizon_days=120,
            constraints=RiskConstraints(
                max_drawdown_rate=0.15,
                max_position_weight=0.15,
                max_leverage=1.0,
                max_short_exposure=0.0,
            ),
            max_concentration_hhi=0.25,
            cash_reserve_rate=0.10,
            max_annualized_volatility=0.40,
            trading_frequency=TradingFrequency.MEDIUM,
            costs=costs,
            reinvest_dividends=True,
            income_weight=0.1,
        ),
        "long_term_growth": StrategyProfile(
            strategy_id="long_term_growth",
            name="Long-term · Growth",
            preset="long_term_growth",
            risk_tolerance=RiskTolerance.MODERATE,
            horizon_days=1826,
            constraints=RiskConstraints(
                max_drawdown_rate=0.30,
                max_position_weight=0.15,
                max_leverage=1.0,
                max_short_exposure=0.0,
                prohibited_asset_classes=frozenset({AssetClass.FOREX}),
            ),
            max_concentration_hhi=0.20,
            cash_reserve_rate=0.05,
            max_annualized_volatility=0.40,
            preferred_asset_classes=frozenset({AssetClass.EQUITY, AssetClass.ETF}),
            trading_frequency=TradingFrequency.LOW,
            costs=costs,
            reinvest_dividends=True,
            income_weight=0.0,
        ),
        "balanced_core": StrategyProfile(
            strategy_id="balanced_core",
            name="Balanced core",
            preset="balanced_core",
            risk_tolerance=RiskTolerance.MODERATE,
            horizon_days=1095,
            constraints=RiskConstraints(
                max_drawdown_rate=0.20,
                max_position_weight=0.12,
                max_leverage=1.0,
                max_short_exposure=0.0,
                prohibited_asset_classes=frozenset({AssetClass.CRYPTO}),
            ),
            max_concentration_hhi=0.20,
            cash_reserve_rate=0.08,
            max_annualized_volatility=0.30,
            preferred_asset_classes=frozenset({AssetClass.ETF, AssetClass.EQUITY, AssetClass.BOND}),
            trading_frequency=TradingFrequency.LOW,
            costs=costs,
            reinvest_dividends=True,
            income_weight=0.15,
        ),
        "dividend_income": StrategyProfile(
            strategy_id="dividend_income",
            name="Dividend income",
            preset="dividend_income",
            risk_tolerance=RiskTolerance.MODERATE,
            horizon_days=1826,
            constraints=RiskConstraints(
                max_drawdown_rate=0.18,
                max_position_weight=0.08,
                max_leverage=1.0,
                max_short_exposure=0.0,
                prohibited_asset_classes=frozenset({AssetClass.CRYPTO, AssetClass.FOREX}),
            ),
            max_concentration_hhi=0.15,
            cash_reserve_rate=0.10,
            max_annualized_volatility=0.28,
            preferred_asset_classes=frozenset({AssetClass.EQUITY, AssetClass.ETF, AssetClass.BOND}),
            trading_frequency=TradingFrequency.LOW,
            costs=costs,
            reinvest_dividends=False,
            income_weight=0.8,
        ),
        "capital_preservation": StrategyProfile(
            strategy_id="capital_preservation",
            name="Capital preservation",
            preset="capital_preservation",
            risk_tolerance=RiskTolerance.CONSERVATIVE,
            horizon_days=365,
            constraints=RiskConstraints(
                max_drawdown_rate=0.05,
                max_position_weight=0.08,
                max_leverage=1.0,
                max_short_exposure=0.0,
                prohibited_asset_classes=frozenset(
                    {AssetClass.CRYPTO, AssetClass.FOREX, AssetClass.COMMODITY}
                ),
            ),
            max_concentration_hhi=0.15,
            cash_reserve_rate=0.35,
            max_annualized_volatility=0.15,
            preferred_asset_classes=frozenset({AssetClass.BOND, AssetClass.ETF, AssetClass.INDEX}),
            trading_frequency=TradingFrequency.LOW,
            costs=costs,
            reinvest_dividends=True,
            income_weight=0.4,
        ),
        "steady_accumulation": StrategyProfile(
            strategy_id="steady_accumulation",
            name="Steady accumulation",
            preset="steady_accumulation",
            risk_tolerance=RiskTolerance.MODERATE,
            horizon_days=3650,
            constraints=RiskConstraints(
                max_drawdown_rate=0.25,
                max_position_weight=0.12,
                max_leverage=1.0,
                max_short_exposure=0.0,
                prohibited_asset_classes=frozenset({AssetClass.CRYPTO}),
            ),
            max_concentration_hhi=0.18,
            cash_reserve_rate=0.05,
            max_annualized_volatility=0.35,
            preferred_asset_classes=frozenset({AssetClass.ETF, AssetClass.INDEX}),
            trading_frequency=TradingFrequency.LOW,
            costs=costs,
            reinvest_dividends=True,
            income_weight=0.1,
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
