"""Strategy constraint evaluation.

Constraint hierarchy (documented in docs/finance/strategy-model.md):

1. **Hard limits** - excluded assets, prohibited / non-allowed asset classes, the volatility cap
   for new purchases, maximum position weight, cash reserve, portfolio drawdown limit and the
   concentration limit. A hard finding always wins over an optimisation preference or a
   bullish signal.
2. **Soft preferences** - preferred asset classes and diagnostics such as unknown volatility.
   They never block anything; they are reported.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from slaifi.domain.assets import AssetClass, AssetId
from slaifi.domain.portfolio import PortfolioSnapshot
from slaifi.domain.recommendations import ConstraintFinding
from slaifi.domain.strategies import StrategyProfile

# With fewer holdings than this, concentration is inherent; the position-weight cap and the
# cash reserve govern instead of the HHI limit.
MIN_POSITIONS_FOR_HHI = 3
_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class PortfolioSuggestion:
    """Deterministic, quantified portfolio improvement suggestion."""

    kind: str
    symbol: str | None
    message: str
    quantity: Decimal | None = None
    amount: Decimal | None = None


@dataclass(frozen=True, slots=True)
class AlignmentReport:
    strategy_id: str
    aligned: bool
    findings: tuple[ConstraintFinding, ...]
    suggestions: tuple[PortfolioSuggestion, ...]
    metrics: Mapping[str, float | None]


def asset_eligibility(
    asset: AssetId,
    strategy: StrategyProfile,
    *,
    annualized_volatility: float | None = None,
) -> tuple[ConstraintFinding, ...]:
    """Whether the strategy permits holding / buying the asset at all."""

    findings: list[ConstraintFinding] = []
    constraints = strategy.constraints
    if asset.symbol in strategy.excluded_symbols:
        findings.append(
            ConstraintFinding(
                "excluded_asset",
                "hard",
                f"{asset.display_symbol} is on the strategy's excluded list.",
            )
        )
    if asset.asset_class in constraints.prohibited_asset_classes:
        findings.append(
            ConstraintFinding(
                "prohibited_asset_class",
                "hard",
                f"The strategy prohibits the {asset.asset_class.value} asset class.",
            )
        )
    allowed = constraints.allowed_asset_classes
    if allowed and asset.asset_class not in allowed:
        label = (
            "unknown asset class"
            if asset.asset_class is AssetClass.UNKNOWN
            else asset.asset_class.value
        )
        findings.append(
            ConstraintFinding(
                "asset_class_not_allowed",
                "hard",
                f"The strategy only allows specific asset classes; this instrument is {label}.",
            )
        )
    cap = strategy.max_annualized_volatility
    if cap is not None:
        if annualized_volatility is None:
            findings.append(
                ConstraintFinding(
                    "volatility_unknown",
                    "soft",
                    "Volatility could not be measured, so the strategy's volatility cap "
                    "could not be checked.",
                    limit=cap,
                )
            )
        elif annualized_volatility > cap:
            findings.append(
                ConstraintFinding(
                    "volatility_cap",
                    "hard",
                    f"Annualized volatility {annualized_volatility:.1%} exceeds the "
                    f"strategy cap of {cap:.1%}.",
                    limit=cap,
                    observed=annualized_volatility,
                )
            )
    preferred = strategy.preferred_asset_classes
    if preferred and asset.asset_class not in preferred:
        findings.append(
            ConstraintFinding(
                "not_preferred_class",
                "soft",
                f"{asset.asset_class.value} is not among the strategy's preferred asset classes.",
            )
        )
    return tuple(findings)


def _asset_market_value(snapshot: PortfolioSnapshot, asset: AssetId) -> Decimal:
    """Absolute market value of the holding (long or short) in this asset."""
    for valuation in snapshot.positions:
        if valuation.position.asset == asset:
            return abs(valuation.market_value)
    return _ZERO


def _invested_weights(values: Mapping[AssetId, Decimal]) -> list[float]:
    total = sum((abs(v) for v in values.values()), _ZERO)
    if total <= 0:
        return []
    return [float(abs(value) / total) for value in values.values() if value != 0]


def check_buy(
    snapshot: PortfolioSnapshot,
    asset: AssetId,
    *,
    trade_value: Decimal,
    fee: Decimal,
    strategy: StrategyProfile,
    annualized_volatility: float | None = None,
    portfolio_drawdown: float | None = None,
) -> tuple[ConstraintFinding, ...]:
    """Check a proposed purchase against the active strategy. Sells are never blocked here."""

    findings = list(asset_eligibility(asset, strategy, annualized_volatility=annualized_volatility))
    total = snapshot.total_value
    if total <= 0:
        return tuple(findings)

    cap = strategy.max_position_weight
    current_value = _asset_market_value(snapshot, asset)
    if cap is not None:
        weight_after = float((current_value + trade_value) / total)
        if weight_after > cap + 1e-12:
            findings.append(
                ConstraintFinding(
                    "max_position_weight",
                    "hard",
                    f"The purchase would make {asset.display_symbol} {weight_after:.1%} of the "
                    f"portfolio, above the {cap:.1%} position limit.",
                    limit=cap,
                    observed=weight_after,
                )
            )

    reserve = strategy.cash_reserve_rate
    if reserve > 0:
        # Cash locked as collateral for shorts is not available to meet the reserve.
        cash_after = snapshot.free_cash - trade_value - fee
        required = total * Decimal(str(reserve))
        if cash_after < required:
            findings.append(
                ConstraintFinding(
                    "cash_reserve",
                    "hard",
                    f"The purchase would leave {cash_after:.2f} cash, below the required "
                    f"reserve of {required:.2f} ({reserve:.0%} of portfolio value).",
                    limit=reserve,
                    observed=float(cash_after / total),
                )
            )

    dd_limit = strategy.max_drawdown_rate
    if dd_limit is not None and portfolio_drawdown is not None and -portfolio_drawdown > dd_limit:
        findings.append(
            ConstraintFinding(
                "drawdown_limit_breached",
                "hard",
                f"Portfolio drawdown {-portfolio_drawdown:.1%} exceeds the {dd_limit:.1%} limit; "
                "new purchases are blocked until it recovers or the limit is changed.",
                limit=dd_limit,
                observed=-portfolio_drawdown,
            )
        )

    hhi_cap = strategy.max_concentration_hhi
    if hhi_cap is not None:
        values = {v.position.asset: v.market_value for v in snapshot.positions}
        before = _hhi(_invested_weights(values))
        values_after = dict(values)
        values_after[asset] = values_after.get(asset, _ZERO) + trade_value
        after_weights = _invested_weights(values_after)
        after = _hhi(after_weights)
        if len(after_weights) >= MIN_POSITIONS_FOR_HHI and after > hhi_cap and after > before:
            findings.append(
                ConstraintFinding(
                    "concentration_hhi",
                    "hard",
                    f"The purchase would raise portfolio concentration (HHI {after:.2f}) above "
                    f"the {hhi_cap:.2f} limit.",
                    limit=hhi_cap,
                    observed=after,
                )
            )
    return tuple(findings)


def check_short(
    snapshot: PortfolioSnapshot,
    asset: AssetId,
    *,
    trade_value: Decimal,
    fee: Decimal,
    strategy: StrategyProfile,
    annualized_volatility: float | None = None,
    portfolio_drawdown: float | None = None,
) -> tuple[ConstraintFinding, ...]:
    """Check a proposed short sale. Short selling is off unless the strategy allows exposure.

    Covering a short is never blocked here: it only reduces risk.
    """

    findings = list(asset_eligibility(asset, strategy, annualized_volatility=annualized_volatility))
    limit = strategy.constraints.max_short_exposure
    total = snapshot.total_value
    if limit is None or limit <= 0:
        findings.append(
            ConstraintFinding(
                "short_not_allowed",
                "hard",
                "Short selling is switched off in the active strategy (short exposure limit 0%). "
                "Raise 'largest short exposure' in Strategies to allow it.",
                limit=0.0,
                observed=None,
            )
        )
        return tuple(findings)
    if total <= 0:
        return tuple(findings)

    short_after = snapshot.short_value + trade_value
    exposure_after = float(short_after / total)
    if exposure_after > limit + 1e-12:
        findings.append(
            ConstraintFinding(
                "max_short_exposure",
                "hard",
                f"This short would put {exposure_after:.1%} of the portfolio into short positions, "
                f"above the {limit:.1%} limit.",
                limit=limit,
                observed=exposure_after,
            )
        )
    cap = strategy.max_position_weight
    if cap is not None:
        weight_after = float((_asset_market_value(snapshot, asset) + trade_value) / total)
        if weight_after > cap + 1e-12:
            findings.append(
                ConstraintFinding(
                    "max_position_weight",
                    "hard",
                    f"The short would make {asset.display_symbol} {weight_after:.1%} of the "
                    f"portfolio, above the {cap:.1%} position limit.",
                    limit=cap,
                    observed=weight_after,
                )
            )
    dd_limit = strategy.max_drawdown_rate
    if dd_limit is not None and portfolio_drawdown is not None and -portfolio_drawdown > dd_limit:
        findings.append(
            ConstraintFinding(
                "drawdown_limit_breached",
                "hard",
                f"Portfolio drawdown {-portfolio_drawdown:.1%} exceeds the {dd_limit:.1%} limit; "
                "new short positions are blocked until it recovers or the limit is changed.",
                limit=dd_limit,
                observed=-portfolio_drawdown,
            )
        )
    return tuple(findings)


def _hhi(weights: list[float]) -> float:
    return sum(weight * weight for weight in weights) if weights else 0.0


def evaluate_alignment(
    snapshot: PortfolioSnapshot,
    strategy: StrategyProfile,
    *,
    portfolio_drawdown: float | None = None,
    annualized_volatility: Mapping[AssetId, float] | None = None,
) -> AlignmentReport:
    """Whether current holdings still satisfy the strategy, with quantified fixes."""

    findings: list[ConstraintFinding] = []
    suggestions: list[PortfolioSuggestion] = []
    total = snapshot.total_value
    vols = annualized_volatility or {}
    metrics: dict[str, float | None] = {
        "cash_weight": float(snapshot.cash_balance / total) if total > 0 else None,
        "largest_position_weight": None,
        "concentration_hhi": None,
        "portfolio_drawdown": portfolio_drawdown,
    }

    values = {v.position.asset: v.market_value for v in snapshot.positions}
    weights = _invested_weights(values)
    if weights:
        metrics["concentration_hhi"] = _hhi(weights)

    cap = strategy.max_position_weight
    for valuation in snapshot.positions:
        asset = valuation.position.asset
        weight = float(abs(valuation.market_value) / total) if total > 0 else 0.0
        metrics["largest_position_weight"] = max(metrics["largest_position_weight"] or 0.0, weight)
        for finding in asset_eligibility(asset, strategy, annualized_volatility=vols.get(asset)):
            if finding.severity == "hard" or finding.code == "volatility_unknown":
                findings.append(finding)
            if finding.code in {
                "excluded_asset",
                "prohibited_asset_class",
                "asset_class_not_allowed",
            }:
                suggestions.append(
                    PortfolioSuggestion(
                        "exit_disallowed_asset",
                        asset.display_symbol,
                        f"Close {asset.display_symbol}: {finding.message}",
                        quantity=valuation.position.quantity,
                    )
                )
        if cap is not None and weight > cap + 1e-12 and valuation.market_price > 0:
            excess_value = abs(valuation.market_value) - total * Decimal(str(cap))
            quantity = (excess_value / valuation.market_price).quantize(Decimal("0.0001"))
            findings.append(
                ConstraintFinding(
                    "max_position_weight",
                    "hard",
                    f"{asset.display_symbol} is {weight:.1%} of the portfolio, above the "
                    f"{cap:.1%} limit.",
                    limit=cap,
                    observed=weight,
                )
            )
            suggestions.append(
                PortfolioSuggestion(
                    "reduce_overweight",
                    asset.display_symbol,
                    f"Sell about {quantity} units of {asset.display_symbol} to return to the "
                    f"{cap:.1%} limit (before costs and price moves).",
                    quantity=quantity,
                    amount=excess_value.quantize(Decimal("0.01")),
                )
            )

    reserve = strategy.cash_reserve_rate
    if reserve > 0 and total > 0:
        required = total * Decimal(str(reserve))
        if snapshot.free_cash < required:
            shortfall = (required - snapshot.free_cash).quantize(Decimal("0.01"))
            findings.append(
                ConstraintFinding(
                    "cash_reserve",
                    "hard",
                    f"Free cash {snapshot.free_cash:.2f} is below the required reserve of "
                    f"{required:.2f} ({reserve:.0%}).",
                    limit=reserve,
                    observed=metrics["cash_weight"],
                )
            )
            suggestions.append(
                PortfolioSuggestion(
                    "raise_cash",
                    None,
                    f"Raise about {shortfall} in cash (sell holdings or add cash) to meet the "
                    f"{reserve:.0%} reserve.",
                    amount=shortfall,
                )
            )

    if snapshot.has_shorts:
        short_limit = strategy.constraints.max_short_exposure or 0.0
        exposure = float(snapshot.short_value / total) if total > 0 else 0.0
        metrics["short_exposure"] = exposure
        if exposure > short_limit + 1e-12:
            findings.append(
                ConstraintFinding(
                    "max_short_exposure",
                    "hard",
                    f"Short positions are {exposure:.1%} of the portfolio, above the "
                    f"{short_limit:.1%} limit.",
                    limit=short_limit,
                    observed=exposure,
                )
            )
            suggestions.append(
                PortfolioSuggestion(
                    "cover_shorts",
                    None,
                    "Buy back (cover) part of the short positions to return within the limit.",
                )
            )
        if snapshot.cash_balance < snapshot.margin_required:
            gap = (snapshot.margin_required - snapshot.cash_balance).quantize(Decimal("0.01"))
            findings.append(
                ConstraintFinding(
                    "margin_shortfall",
                    "hard",
                    f"Cash {snapshot.cash_balance:.2f} is below the {snapshot.margin_required:.2f} "
                    "held as collateral for short positions (a margin call in a real account).",
                )
            )
            suggestions.append(
                PortfolioSuggestion(
                    "cover_shorts",
                    None,
                    f"Cover shorts or add about {gap} in cash to restore the collateral.",
                    amount=gap,
                )
            )

    hhi_cap = strategy.max_concentration_hhi
    hhi_now = metrics["concentration_hhi"]
    if (
        hhi_cap is not None
        and hhi_now is not None
        and len(weights) >= MIN_POSITIONS_FOR_HHI
        and hhi_now > hhi_cap
    ):
        findings.append(
            ConstraintFinding(
                "concentration_hhi",
                "hard",
                f"Portfolio concentration (HHI {hhi_now:.2f}) is above the {hhi_cap:.2f} limit.",
                limit=hhi_cap,
                observed=hhi_now,
            )
        )
        suggestions.append(
            PortfolioSuggestion(
                "diversify",
                None,
                "Add positions in other assets or trim the largest holdings to lower "
                "concentration.",
            )
        )

    dd_limit = strategy.max_drawdown_rate
    if dd_limit is not None and portfolio_drawdown is not None and -portfolio_drawdown > dd_limit:
        findings.append(
            ConstraintFinding(
                "drawdown_limit_breached",
                "hard",
                f"Portfolio drawdown {-portfolio_drawdown:.1%} exceeds the {dd_limit:.1%} limit.",
                limit=dd_limit,
                observed=-portfolio_drawdown,
            )
        )
        suggestions.append(
            PortfolioSuggestion(
                "de_risk",
                None,
                "The drawdown limit is breached: avoid new purchases and review the largest "
                "or most volatile positions.",
            )
        )

    hard = [finding for finding in findings if finding.severity == "hard"]
    return AlignmentReport(
        strategy_id=strategy.strategy_id,
        aligned=not hard,
        findings=tuple(findings),
        suggestions=tuple(suggestions),
        metrics=metrics,
    )
