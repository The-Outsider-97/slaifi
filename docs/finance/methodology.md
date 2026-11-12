# Methodology

All money is `Decimal` (strings in JSON). Rates are fractions (`0.10` = 10 %). Times are timezone-aware.

## Recommendations (`engines/recommendation`)
Six weighted votes, each in [−1, 1], over **daily** bars: price vs 50-bar average (0.25), vs
200-bar (0.15), 63-bar momentum (0.20), MACD histogram (0.15), RSI-14 (0.10), 20/50 crossover
(0.15). The weighted sum is the **rule score** in [−1, 1]. It is an aggregate of rules,
**not a probability and not a confidence level**, and is labelled so everywhere.

The score maps to an action using thresholds set by the strategy's risk tolerance
(buy ≥ 0.25/0.35/0.45 for aggressive/moderate/conservative; reduce and sell thresholds are
negative). Holdings, hard limits and the portfolio context can change the action:
a violated hard limit ⇒ SELL (held) or AVOID; a favourable score blocked by a limit ⇒ WATCH.
Actions are limited to BUY, HOLD, SELL, WATCH, AVOID, REDUCE and DCA.

**Insufficient evidence** is returned (no action) when there are too few bars, the data is stale
or has gaps, or the only history available is saved (last-known) data rather than a fresh retrieval. Reasons are listed.

## Prediction (`engines/prediction`)
The only forecast is an empirical-quantile *interval* of historical horizon returns, released only
if a walk-forward test validates it: origins spaced one horizon apart, intervals built from returns
realised before each origin, ≥ 20 independent tests, realised coverage compatible with the nominal
80 %. Otherwise no prediction is shown and the reason is stated. Model id/version
(`empirical_quantile_interval 1.0.0`), horizon, supporting/conflicting signals and invalidation
conditions accompany any interval. No probabilities, expected returns or accuracy claims are
produced beyond measured coverage.

## Back-test (`engines/backtest`)
Long-only, fully invested or in cash, fixed rule thresholds (not fitted to the data). Signals use
data up to bar *t*; fills occur at the **next bar's open** (no look-ahead), with the strategy's
commission and slippage. Reports total/annualised return, volatility, drawdown, trade count and a
**buy-and-hold benchmark**. Needs ≥ 252 bars. It is a historical simulation, not a forecast.

## Paper trading (`engines/paper`, `application/paper`)
Buy/sell by quantity or value, fractional quantities (default 4 decimals), no shorting or leverage. Fill price =
latest quote ± slippage; commission from the strategy. Orders are refused for: stale/unavailable
quotes, closed market (unless enabled), insufficient cash/holdings, hard-limit breaches, storage
not healthy. Orders carry an idempotent `client_order_id`. The SQLite ledger is the single source
of truth; every change is appended to a hash-chained audit log; `reconcile` replays the ledger
and compares to stored valuations. Reset requires explicit confirmation and starts a new epoch.

## Strategies (`domain/strategies`, `engines/strategy`)
A strategy is a set of numeric parameters (horizon, risk tolerance, max drawdown, max position
weight, concentration HHI cap, cash reserve, volatility cap, prohibited/preferred asset classes,
costs, income weight, …). Presets are starting values only. **Hard limits always take precedence
over preferences and optimisation.**

## Goals (`engines/goals/planning.py`)
For an amount target per period (e.g. $200/month, $50/day) the required annual return is the
annualised target divided by capital (daily targets use 252 trading days; other periods use calendar
periods; taxes ignored). A rate target (e.g. 9 %/yr) is used directly; if both exist the more demanding
rate applies. Findings flag demanding targets (> 15 %/yr),
very demanding (> 30 %), risk/drawdown conflicts, and progress measured from the ledger in the
current UTC calendar window. Scenarios use hypothetical rates (0, 4, 8, 12 %) and a −20 % stress.
Targets are objectives, not guarantees.

## Advisor (`engines/instructions`, `application/advisor`)
Rule-based parser → validation → preview → persisted *proposal* (30 min TTL) → confirmation.
It detects contradictions and states whether each change is temporary or persistent. Contradictions
and any loosening of a hard limit need explicit acknowledgement. Stale proposals (state changed
since) are refused. The parser recognises a limited phrasing set; unrecognised text is reported
as such rather than guessed.
