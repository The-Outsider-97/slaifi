# Portfolio Calculations

The initial portfolio engine is deterministic, long-only, single-currency-per-calculation accounting.

## Weighted-average cost

For a buy:

`new_cost_basis = old_cost_basis + quantity * unit_price + buy_fee`

`average_cost = cost_basis / open_quantity`

Buy fees are capitalized into basis.

For a sell:

`proceeds = quantity * unit_price - sell_fee`

`realized_pnl = proceeds - average_cost * sold_quantity`

Sell fees therefore reduce realized proceeds. Selling more than the available long quantity is rejected rather than silently creating a short position.

## Valuation

`market_value = open_quantity * market_price`

`unrealized_pnl = (market_price - average_cost) * open_quantity`

Invested-only weights divide each security market value by total securities value. Snapshot `portfolio_weight` uses total portfolio value including cash when total value is positive.

## Currency

No hidden FX conversion exists. Trades/cash flows not in portfolio base currency cause a calculation error until an explicit FX layer is introduced.

Tax-lot methods and jurisdiction-specific tax accounting are intentionally deferred.
