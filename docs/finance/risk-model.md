# Risk Model — Design Contract

Risk is an independent analysis axis, not a penalty appended to a return forecast after the fact.

Planned measures include volatility, downside volatility, beta, VaR/CVaR where methodologically justified, maximum drawdown, concentration, correlation, liquidity, leverage, exposure, Sharpe and Sortino ratios.

Each metric must define units, lookback window, sampling frequency, missing-data behavior, benchmark assumptions, and known limitations. Historical estimates must not be presented as guaranteed future risk.

Financial calculation tests will use fixed datasets and known expected values before metrics are used in recommendations.
