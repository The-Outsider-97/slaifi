# Frontend Runtime and Data Provenance

The frontend is a presentation layer over authoritative SLAIFI API contracts. It does not own portfolio accounting, risk arithmetic, technical-indicator calculations, market-history generation, or SLAI reasoning.

## Component responsibilities

```text
MarketOverviewPage
├── AppShell
│   ├── Sidebar
│   └── TopBar
├── MarketSummaryCard
├── MarketPerformanceChart
├── SlaiInsightCard
├── MarketWatchTable
└── GoalsCard

MyPortfolioPage
├── AppShell
├── Portfolio summary
├── Holdings
├── Allocation
├── Risk
└── SLAI portfolio insight
```

Components represent product responsibilities rather than financial business logic.

## Market data provenance

`GET /api/v1/market/overview` supplies normalized quote data and the backend-owned `data_mode`. The UI does not convert mock values into apparently live values. Production configuration rejects the mock provider.

`GET /api/v1/market/history/{symbol}` supplies the historical OHLCV series used by the performance chart and by market-analysis requests. If real history is unavailable, the chart renders an explicit unavailable/empty state. No replacement chart series is generated in React.

Market analysis is only requested after historical evidence exists. The frontend sends that backend-sourced series to `POST /api/v1/analysis/market`; deterministic SLAIFI engines calculate financial evidence before the SLAI adapter receives it.

## Portfolio provenance

`GET /api/v1/portfolio/current` loads the configured portfolio ledger and returns deterministic valuation without invoking SLAI by default. The UI does not reconstruct positions or valuation locally.

SLAI portfolio interpretation is opt-in through the same route with `include_reasoning=true`. This keeps normal dashboard loading deterministic and avoids unnecessary agent latency.

If no portfolio source is configured, the API returns no content and the UI presents an empty state. Missing portfolio history leaves risk/performance metrics unavailable instead of being approximated in React.

## SLAI provenance

`GET /api/v1/integrations/slai` reports runtime availability. Analysis responses may additionally expose bounded provenance including agent, strategy, confidence, validation status, Safety status, correlation ID and warnings.

The UI never fabricates an SLAI interpretation. When SLAI is degraded or unavailable, deterministic market/portfolio information remains usable and the status is presented explicitly.

## Failure and stale-data behavior

Provider failures are API failures, not triggers for realistic-looking fallback values. Loading, error, no-data and degraded SLAI states remain visually distinct. Market-source timestamps and provider source values originate in backend responses.

## Presentation conversions

Display-only operations such as locale formatting, decimal-to-display percentage conversion, selected chart range, responsive layout and accessibility state belong to React. Indicator, risk, goal, portfolio and return calculations remain backend responsibilities.
