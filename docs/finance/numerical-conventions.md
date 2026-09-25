# Numerical Conventions

## Rates and percentages

Internal returns, yields, drawdowns, weights, and rate constraints use fractional form:

- `0.10` = 10%
- `-0.05` = -5%

Presentation layers may convert to human percentages. Provider payloads must be normalized at the adapter boundary.

## Money

Prices, fees, cash, income, cost basis, and P/L use `Decimal`. The current portfolio engine does not perform FX conversion; combining unlike currencies raises a calculation error.

## Statistical values

Returns and statistical calculations use finite `float` values. NaN and infinity are rejected. Undefined quantities such as correlation of a constant series, Sharpe with zero volatility, or Sortino with zero downside deviation are not replaced with arbitrary zeroes.

## Annualization

No engine silently assumes 252 periods per year. Callers supply `periods_per_year`. Volatility scales by `sqrt(periods_per_year)`. Annual risk-free/target rates are converted to equivalent compound periodic rates where required.

## Missing values and warm-up

Aligned indicators use `None` during warm-up. Engines do not silently forward-fill. A zero previous volume makes percentage volume change undefined (`None`).

## Time

Domain timestamps must be timezone-aware. Ordered OHLCV calculations require strictly increasing bar end timestamps and reject duplicates or reverse ordering.
