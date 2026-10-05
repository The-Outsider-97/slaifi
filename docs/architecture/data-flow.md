# Financial Data Flow

SLAIFI separates financial truth from AI interpretation. Provider data and portfolio ledgers become domain values first; deterministic engines calculate metrics; SLAI may then interpret the resulting evidence.

## Market overview flow

```text
External Market Provider
        ↓
MarketDataProvider adapter
        ↓
provider payload validation
        ↓
normalized PriceQuote / OHLCVBar
        ↓
bounded TTL cache at provider boundary
        ↓
GetMarketOverview / GetMarketHistory
        ↓
FastAPI market endpoints
        ↓
frontend API client
        ↓
Market Overview UI
```

The mock provider is a development/test adapter. Production configuration rejects it. The frontend never converts mock values into apparently-live financial information.

## Market analysis flow

```text
normalized historical OHLCV
        ↓
AnalyzeMarketSeries
        ↓
Feature + Technical + Risk engines
        ↓
structured authoritative evidence
        ↓
FinancialReasoner contract
        ↓
SLAI Reasoning Agent
        ↓
SLAI Quality Agent
        ↓
pass / warn / one bounded refinement / block
        ↓
public interpretation + provenance
        ↓
API
        ↓
frontend insight panel
```

The Reasoning Agent never receives authority to change source bars or deterministic calculations. A quality failure cannot cause a fabricated replacement value.

## Portfolio flow

```text
configured actual portfolio ledger
        ↓
Portfolio domain validation
        ↓
build open positions
        ↓
fetch current prices only for open positions
        ↓
Portfolio Engine valuation / P&L / weights
        ↓
optional Risk + Goal engines when required evidence exists
        ↓
PortfolioAnalysisResult
        ↓
FastAPI
        ↓
frontend portfolio page
```

Normal portfolio loading stops here and does not invoke SLAI.

When the user explicitly requests interpretation:

```text
PortfolioAnalysisResult
        ↓
structured evidence + constraints + uncertainty
        ↓
SLAI Reasoning + Quality workflow
        ↓
public interpretation/provenance
        ↓
existing deterministic portfolio remains visible
```

## Provenance rule

Later stages append interpretation/provenance instead of replacing earlier evidence. Facts, derived deterministic metrics, AI interpretation, and any future learned preferences must remain distinguishable.

## Time semantics

Authoritative timestamps are timezone-aware. Provider observation time, SLAIFI generation time, portfolio valuation time, reasoning completion time, and caller request/correlation IDs are distinct concepts and are not silently collapsed.

## Caching rule

Caching exists only at the market-provider infrastructure boundary and has explicit short TTLs. Cached financial observations retain their original `observed_at` timestamps. A cache hit does not pretend that the observation was refreshed.
