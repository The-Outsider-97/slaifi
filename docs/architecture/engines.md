# Engines Layer

Engines are deterministic or statistical transformations of already-normalized inputs. They may import only Core and Domain.

Implemented engines:

- `features`: returns, rolling returns/means/maxima/volatility, drawdown, volume changes;
- `technical`: SMA, EMA, momentum, Wilder RSI, MACD, Wilder ATR;
- `portfolio`: weighted-average cost accounting, realized/unrealized P/L, cash, income aggregation, weights, valuation;
- `risk`: volatility, downside deviation, maximum drawdown, Sharpe, Sortino, Pearson correlation, correlation matrices, concentration HHI;
- `goals`: income-target annualization and explicit target-vs-assumption feasibility arithmetic.

Engines do not fetch data, access databases, call SLAI, construct HTTP responses, or generate BUY/SELL recommendations.

Time-series functions either validate ordering or consume sequence order as supplied; they never shuffle or forward-fill missing observations.
