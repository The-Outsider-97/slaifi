# Initial Risk Model

The current risk engine provides measurement only; it does not classify a security as safe/unsafe and does not produce recommendations.

- **Historical volatility:** sample standard deviation of periodic simple returns multiplied by `sqrt(periods_per_year)`.
- **Downside deviation:** square root of the mean squared negative deviation from the converted periodic target, annualized by `sqrt(periods_per_year)`. The denominator is all observations.
- **Maximum drawdown:** minimum of `value / running_peak - 1`; output is in `[-1, 0]`.
- **Sharpe ratio:** mean periodic excess return divided by sample standard deviation, multiplied by `sqrt(periods_per_year)`. Annual risk-free rate is converted to an equivalent compound periodic rate.
- **Sortino ratio:** annualized arithmetic mean excess over target divided by annualized downside deviation.
- **Correlation:** sample Pearson correlation; constant series are mathematically undefined and rejected.
- **Concentration HHI:** squared normalized non-negative weights summed after normalization.

VaR/CVaR are intentionally not implemented in this milestone because methodology/distribution assumptions have not yet been selected.
