# Frontend Runtime and Data Provenance

The React frontend is a presentation layer over authoritative backend contracts. It does not own portfolio accounting, risk calculations, technical indicators, provider authentication, or SLAI orchestration.

## Market Overview

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
```

The page flow is:

```text
market provider
→ SLAIFI provider adapter
→ application market services
→ FastAPI market endpoints
→ frontend API client
→ useMarketDashboard
→ presentation components
```

`GET /api/v1/market/overview` supplies normalized quotes and provider mode. `GET /api/v1/market/history/{symbol}` supplies chronological provider-derived OHLCV bars for the selected range. The chart does not interpolate invented market observations.

The production runtime contains no `demoMarket.ts`, static market-price arrays, fake market-watch securities, or synthetic analysis series. When `data_mode="mock"`, the frontend deliberately hides financial values rather than presenting deterministic test values as market truth.

Only the primary overview instrument currently loads a historical series for the main chart. Summary instruments without an authoritative series display no fabricated sparkline. This avoids multiple unnecessary history requests merely for decoration.

## SLAI market insight

Market-page SLAI analysis is explicitly user-triggered. The frontend does not send a synthetic reasoning payload. It converts the same backend historical bars already loaded for the chart into the typed market-analysis request and calls `/api/v1/analysis/market` only when:

- SLAI reports `available` or `degraded`;
- at least two real/provider bars exist;
- the user requests reasoning.

Deterministic feature/technical/risk calculations occur on the backend before structured evidence reaches SLAI. The frontend displays the public interpretation and provenance returned by the backend, not raw agent internals.

## Portfolio

The normal page load calls:

```text
GET /api/v1/portfolio/current?include_reasoning=false
```

This returns authoritative portfolio valuation without paying SLAI latency. If no actual portfolio source is configured, HTTP 204 becomes an explicit empty state.

SLAI portfolio interpretation is a separate user action:

```text
GET /api/v1/portfolio/current?include_reasoning=true
X-Request-ID: slaifi-ui-...
```

If SLAI fails, the already-loaded deterministic portfolio remains visible. No AI outage invalidates portfolio accounting.

Historical portfolio performance and historical risk metrics are not fabricated. Until an authoritative portfolio equity/return series is supplied, those panels state that the evidence is unavailable.

## State semantics

The UI keeps these conditions distinct:

- loading;
- empty/no configured source;
- unavailable/provider failure;
- SLAI unavailable;
- SLAI degraded;
- successful deterministic data;
- successful reasoning with provenance.

API errors never trigger realistic-looking financial fallback values.

## Presentation-only transformations

React may perform display transformations such as:

- currency/number formatting;
- converting backend fractional weights to displayed percentages;
- chart geometry from already-authoritative observations;
- client-side table filtering;
- navigation and responsive layout.

React does not calculate portfolio valuation, cost basis, realized/unrealized P&L, risk statistics, technical indicators, or recommendation signals.

## Request efficiency

Market overview and SLAI runtime status are loaded concurrently. Historical data is fetched only for the selected primary chart/range. Portfolio reasoning is on-demand. Backend provider TTL caching coalesces repeated short-lived quote/history requests while preserving explicit freshness semantics.
