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

The UI never silently mixes demo and live values.

- `GET /api/v1/market/overview` supplies normalized quote data. The current backend explicitly returns `data_mode="mock"`; while that remains true, the screenshot-aligned headline index values stay illustrative instead of presenting mock SPY/QQQ/DIA placeholder prices as live indices.
- When a future provider changes `data_mode` away from `mock`, matching summary-card quotes may use API values.
- The performance chart is explicitly labelled `Illustrative data · Not a live market feed` because SLAIFI does not yet expose a historical-series market provider.
- Market-watch status labels are explicitly described as `Illustrative sample signals — not recommendations.` No recommendation engine is implied.
- The insight card starts with an illustrative scenario. Its CTA is disabled unless `/api/v1/integrations/slai` reports `available` or `degraded`.
- Selecting `Explore the reasoning` posts the illustrative OHLCV series to `/api/v1/analysis/market`. Those bars then traverse Domain and Engines before the real SLAI Reasoning Agent sees the calculated evidence. A returned interpretation is therefore real SLAI reasoning over clearly labelled illustrative market data, not fabricated SLAI availability.

## Failure states

Market API failure leaves the educational dashboard available with an explicit fallback warning. SLAI status or reasoning failure never removes deterministic/illustrative financial content. Runtime state is shown as available, degraded, unavailable, or disabled according to the backend contract.

## Presentation conversions

Formatting such as decimal-to-display percentage, currency separators, selected chart range, and responsive layout belongs to React. Indicator, risk, goal, portfolio and return calculations remain backend responsibilities.
