# Operating SLAIFI

* **Market Overview / Stock Analysis** – search a symbol, choose interval and range (only
  intervals at least one configured source supports are offered), toggle indicators, compare symbols,
  add to the watchlist. Every figure carries source, observation time, delay and a badge:
  *Live*, *Delayed*, *Provider data · delay unknown*, *Retrieved* (history), *Last known data ·
  observed <time>* (saved real data shown because no source answered) or *NOT AVAILABLE*.
  Last-known history never produces BUY/SELL, and last-known prices are never used to fill an order.
* **Recommendations** – one of BUY, HOLD, SELL, WATCH, AVOID, REDUCE, DCA, or an explicit
  "insufficient evidence" with the reasons. Includes supporting and conflicting signals, risks
  and invalidation conditions. "Explain with SLAI" adds an interpretation that cannot change the action.
* **Paper Trading** – create a portfolio (virtual cash), deposit/withdraw, preview then place
  buy/sell orders by quantity or value, close positions, see history and performance, reconcile,
  and reset (type the portfolio name to confirm). Rejected orders show every reason.
* **SLAI Advisor** – type an instruction ("Keep a 20% cash reserve, never buy crypto, buy
  $500 of JNJ"). SLAIFI shows what it understood, what would change and any contradictions.
  Nothing persistent or transactional happens until you confirm; loosening a hard limit needs an
  explicit acknowledgement. Temporary ("for this analysis") changes are not saved.
* **Strategies & Goals** – edit numeric parameters (horizon, drawdown, position, cash reserve,
  volatility cap, costs, …). Presets (Short/Long-term × Hawkish/Care-Bear) only initialise values
  and do not lock them. Hard limits override optimisation preferences. Goals report feasibility,
  required return, conflicts, measured progress and hypothetical scenarios.
* **Settings** – market-data sources (configured, working, calls used, last problem, *Check providers*), ledger health, audit-chain verification, backup.

## Backup and recovery
`POST /api/v1/system/backup` (Settings → Back up) writes a coherent SQLite backup. Startup
integrity is checked; when storage is not `ok`, orders are refused until fixed.
`GET /api/v1/system/reconcile` replays the ledger and compares cash, holdings and valuations.
