# Frontend Runtime and Data Provenance

The Market Overview desktop page follows the supplied SLAIFI reference design: a fixed workspace sidebar, compact top bar, four market-summary cards, a large market-performance panel, an SLAI insight panel, market watch, goals, and the educational footer. Desktop fidelity is the primary layout target; the sidebar becomes an overlay below 900 px and the two-column panels stack.

## Component responsibilities

```text
MarketOverviewPage
├── AppShell
│   ├── Sidebar
│   └── TopBar
├── MarketSummaryCard × 4
├── MarketPerformanceChart
├── SlaiInsightCard
├── MarketWatchTable
└── GoalsCard
```

Components represent product responsibilities rather than individual labels. Financial calculations are not duplicated in React.

## Data provenance

The UI shows real market data only and always says what kind it is. There are no sample, mock or
placeholder values anywhere in the package.

- `GET /api/v1/market/overview` supplies quotes with `source`, `observed_at` and `last_known`,
  plus `unavailable` (symbols with neither a fresh nor a saved quote) and `data_mode`
  (`live`, `delayed`, `live_delay_unknown`, `last_known`, `unavailable`).
- A fresh quote is badged *Live*, *Delayed* or *Provider data · delay unknown*; a saved one is
  badged **LAST KNOWN DATA · observed <time>** and the page shows a "Showing last known data"
  banner; a symbol with nothing shows **NOT AVAILABLE** (summary card, watch-list row, chart).
- The performance chart plots the retrieved history of the first overview symbol and states its
  source and, for saved data, when it was saved. With no history it says NOT AVAILABLE.
- Market-watch rows show real price, change and source only; no signals or recommendations are
  implied by the table.
- The insight card's CTA is disabled unless `/api/v1/integrations/slai` reports `available` or
  `degraded` and at least two real bars are loaded. `Explore the reasoning` posts those bars to
  `/api/v1/analysis/market`; they traverse Domain and Engines before the SLAI Reasoning Agent sees
  the calculated evidence.
- Hovering a badge lists each source that was tried and its outcome (never a key).
- Settings → *Market data sources* shows each source's state, calls used, last success/problem,
  the environment variable that holds its key, and a **Check providers** button.

## Failure states

If the market API fails, the page says NOT AVAILABLE with the reason; it never substitutes other
numbers. SLAI status or reasoning failure never removes deterministic financial content. Runtime
state is shown as available, degraded, unavailable, or disabled according to the backend contract.

## Presentation conversions

Formatting such as decimal-to-display percentage, currency separators, selected chart range, and responsive layout belongs to React. Indicator, risk, goal, portfolio and return calculations remain backend responsibilities.
