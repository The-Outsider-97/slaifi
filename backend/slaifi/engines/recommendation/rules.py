"""Score-to-action rules. Strategy hard limits always override a bullish score."""

from __future__ import annotations

from dataclasses import dataclass

from slaifi.domain.recommendations import RecommendationAction, RiskLevel
from slaifi.domain.strategies import InvestmentHorizon, RiskTolerance, StrategyProfile

# Eligibility codes that make the asset unsuitable regardless of signal strength.
ELIGIBILITY_CODES = frozenset(
    {"excluded_asset", "prohibited_asset_class", "asset_class_not_allowed", "volatility_cap"}
)


@dataclass(frozen=True, slots=True)
class ActionThresholds:
    buy: float
    reduce: float
    sell: float
    min_weight_coverage: float = 0.60


_THRESHOLDS = {
    RiskTolerance.AGGRESSIVE: ActionThresholds(buy=0.25, reduce=-0.20, sell=-0.45),
    RiskTolerance.MODERATE: ActionThresholds(buy=0.35, reduce=-0.25, sell=-0.50),
    RiskTolerance.CONSERVATIVE: ActionThresholds(buy=0.45, reduce=-0.20, sell=-0.45),
}


def thresholds_for(strategy: StrategyProfile) -> ActionThresholds:
    return _THRESHOLDS[strategy.risk_tolerance]


def risk_level_from_volatility(annualized_volatility: float | None) -> RiskLevel | None:
    if annualized_volatility is None:
        return None
    if annualized_volatility < 0.15:
        return RiskLevel.LOW
    if annualized_volatility < 0.30:
        return RiskLevel.MODERATE
    if annualized_volatility < 0.50:
        return RiskLevel.HIGH
    return RiskLevel.VERY_HIGH


def choose_action(
    score: float,
    *,
    strategy: StrategyProfile,
    holding: bool,
    eligibility_blocked: bool,
    purchase_blocked: bool,
    short_holding: bool = False,
    short_allowed: bool = False,
) -> tuple[RecommendationAction, str]:
    """Return (action, short reason).

    SHORT and COVER are produced only when the strategy permits short exposure
    (``short_allowed``) or a short is already held (``short_holding``).
    """

    th = thresholds_for(strategy)
    if short_holding:
        if eligibility_blocked:
            return RecommendationAction.COVER, "The asset violates a hard strategy limit; cover."
        if score >= th.buy:
            return (
                RecommendationAction.COVER,
                "Signals have turned favourable; buy back the short before it loses more.",
            )
        if score > 0.10:  # mildly positive: the short thesis is weakening
            return (
                RecommendationAction.HOLD,
                "Signals no longer support the short; watch closely and be ready to cover.",
            )
        return RecommendationAction.HOLD, "Signals still lean negative; the short is unchanged."
    if eligibility_blocked:
        if holding:
            return RecommendationAction.SELL, "The asset violates a hard strategy limit; exit."
        return RecommendationAction.AVOID, "The asset is not permitted by the active strategy."
    if score >= th.buy:
        if purchase_blocked:
            return (
                RecommendationAction.WATCH,
                "Signals are favourable but a portfolio limit blocks adding to the position.",
            )
        return RecommendationAction.BUY, "Signals clear the strategy's buy threshold."
    if score <= th.sell:
        if holding:
            return (
                RecommendationAction.SELL,
                "Signals are broadly negative and clear the sell threshold.",
            )
        if short_allowed:
            return (
                RecommendationAction.SHORT,
                "Signals are broadly negative and the strategy allows short exposure. A short "
                "can lose more than it gains, so size it within the short limit.",
            )
        return RecommendationAction.AVOID, "Signals are broadly negative; do not open a position."
    if score <= th.reduce:
        if holding:
            return RecommendationAction.REDUCE, "Signals have weakened; trim the position."
        return RecommendationAction.WATCH, "Signals are weak; wait for improvement."
    if (
        strategy.horizon is InvestmentHorizon.LONG
        and score > 0.10
        and not purchase_blocked
        and strategy.trading_frequency.value == "low"
    ):
        return (
            RecommendationAction.DCA,
            "Mildly positive signals and a long horizon favour gradual accumulation.",
        )
    if holding:
        return RecommendationAction.HOLD, "Signals are mixed; no change is indicated."
    return RecommendationAction.WATCH, "Signals are mixed; wait for a clearer setup."
