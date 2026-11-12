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
Buy/sell/short/cover by quantity or value, fractional quantities (default 4 decimals), no leverage on long positions. Fill price =
latest quote ± slippage; commission from the strategy. Orders are refused for: stale/unavailable
quotes, closed market (unless enabled), insufficient cash/holdings, hard-limit breaches, storage
not healthy. Orders carry an idempotent `client_order_id`. The SQLite ledger is the single source
of truth; every change is appended to a hash-chained audit log; `reconcile` replays the ledger
and compares to stored valuations. Reset requires explicit confirmation and starts a new epoch.

## Short selling (simulated)

A short sells shares you do not own, hoping to buy them back cheaper. It is available **only** in
paper trading, and **only** when the active strategy sets a *largest short exposure* above 0 — every
preset except *Tactical long/short* keeps it at 0, so shorting is off unless you switch it on (raising the limit is a
loosening and needs the usual acknowledgement).

* **Signed positions.** A short has a negative quantity and a negative market value (a liability);
  `total value = cash + net securities`. A position is either long or short, never both: *Sell*
  closes only longs and *Cover* closes only shorts, otherwise the order is refused (`WRONG_DIRECTION`).
* **Collateral.** The proceeds stay in the account but are locked, together with a further 50 %
  (`SHORT_MARGIN_RATE = 1.5` × the shorts' current value). Buying and the cash reserve use *free
  cash* = cash − collateral. A short that would leave free cash negative is refused
  (`INSUFFICIENT_MARGIN`); one that would exceed the strategy's short limit is refused
  (`SHORT_NOT_ALLOWED` when the limit is 0).
* **Prices.** A short fills at the quote *minus* slippage (you sell), a cover at the quote *plus*
  slippage (you buy). Realised profit on a cover = average net proceeds × quantity − (cost to buy
  back + fee).
* **Risk shown to the user.** The order ticket says plainly that a short can lose more than the
  amount received. If the market moves against a short far enough to leave less cash than the
  collateral, the portfolio shows a *margin shortfall* warning.
* **Not modelled** (stated in the order warning): borrow fees, dividends owed on the borrowed shares,
  share recalls, and forced liquidation. Results on shorts are therefore more favourable than a real
  broker's would be.
* **Recommendations** may say *Short* only when shorting is allowed, nothing is held, and the signals are broadly
  negative; for an existing short they say *Cover* or *Hold*. The advisor understands
  "short" and "cover".


## Optional: suggested allocation and knowledge look-up (`engines/allocation`, `application/allocation`)

Both need an SLAI agent the person has switched on; both are advice only.

**Suggested allocation.** From the portfolio's long holdings (plus optional extra symbols or the watchlist)
SLAIFI keeps the assets the strategy allows (the same eligibility rules as orders), with real, non-last-known
daily history of at least 61 closes, and aligns their daily returns (at least 60 shared observations, at most 20 assets, about 420 days).
It annualises mean and covariance (252 periods) and asks SLAI's optimizer to minimise `w'Σw − λ·μ'w` subject to
`Σw = 1 − cash reserve` and `0 ≤ w ≤ max position weight`. `λ` is 0 for "steadiest" and 0 / 1 / 3 for a
conservative / moderate / aggressive strategy under "balance risk and return" (product defaults). The result is
accepted only if SLAIFI's own checks pass: finite numbers, each weight within bounds, the budget, the strategy's
volatility cap and (with at least 3 holdings) the concentration limit. These are **historical** statistics: they say
how the mix would have behaved, not how it will behave. If the position cap times the number of assets is below the
budget the problem is reported as infeasible with how many assets would be needed.

**Knowledge look-up.** Retrieval over SLAIFI's own markdown guides, chunked by heading. It returns the passage and
its source; it does not generate an answer and it never reads portfolios, orders or the web.
## Strategies (`domain/strategies`, `engines/strategy`)
A strategy is a set of numeric parameters (horizon, risk tolerance, max drawdown, max position
weight, concentration HHI cap, cash reserve, volatility cap, prohibited/preferred asset classes,
costs, income weight, …). Presets are starting values only. **Hard limits always take precedence
over preferences and optimisation.** Eleven presets are offered (short-term hawkish / care-bear / balanced,
long-term hawkish / care-bear / growth, balanced core, dividend income, capital preservation, steady
accumulation, tactical long/short); each has a one-sentence description and every value stays editable, including how often you
trade, income focus, preferred asset classes and dividend reinvestment.

## Goals (`engines/goals/planning.py`)
For an amount target per period (e.g. $200/month, $50/day) the required annual return is the
annualised target divided by capital (daily targets use 252 trading days; other periods use calendar
periods; taxes ignored). A rate target (e.g. 9 %/yr) is used directly; if both exist the more demanding
rate applies. Findings flag demanding targets (> 15 %/yr),
very demanding (> 30 %), risk/drawdown conflicts, and progress measured from the ledger in the
current UTC calendar window. Scenarios use hypothetical rates (0, 4, 8, 12 %) and a −20 % stress.
Targets are objectives, not guarantees.

Two further goal types: **reach a balance by a date** (`target_value`, years, optional monthly saving) solves
the compound annual return that reaches the balance (monthly compounding, end-of-month saving; bisection,
exact to 1e-6), and with an assumed return shows the projected balance, the gap and the extra monthly saving
required. **Fund withdrawals** (`monthly_withdrawal`, years) shows the return needed for the money to last,
how long it lasts at the assumed return (up to 100 years) and the level withdrawal that ends at zero. If the
required return is zero or negative the capital already covers it and the UI says "none needed". When no
return can reach the target the report says so rather than inventing a number. See
`learning-and-adaptation.md` for re-planning and progress.

## Advisor (`engines/instructions`, `application/advisor`)
Rule-based parser → validation → preview → persisted *proposal* (30 min TTL) → confirmation.
It detects contradictions and states whether each change is temporary or persistent. Contradictions
and any loosening of a hard limit need explicit acknowledgement. Stale proposals (state changed
since) are refused. The parser recognises a limited phrasing set; unrecognised text is reported
as such rather than guessed.
