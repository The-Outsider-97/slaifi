# Financial Data Flow

## Target flow

```text
External Market Provider
        ↓
Provider adapter (infrastructure)
        ↓
Raw payload validation
        ↓
Normalization into SLAIFI domain values
        ↓
Cache / persistent market snapshot
        ↓
Feature Engine
        ↓
Technical / Fundamental / Sentiment / Regime analysis
        ↓
Prediction Engine
        ↓
Risk Engine
        ↓
Goal Engine
        ↓
Strategy evaluation
        ↓
SLAI reasoning adapter
        ↓
Recommendation Engine
        ↓
Application use case
        ↓
API
        ↓
Frontend / user
```

The initial vertical slice stops after normalization and application orchestration:

```text
Mock provider → normalized PriceQuote → GetMarketOverview → FastAPI → Home dashboard
```

## Provenance rule

Later stages must retain provenance instead of replacing earlier evidence. A recommendation record should reference the market snapshot, portfolio snapshot, goal, prediction, risk result, strategy evaluation, model versions, and SLAI reasoning version that produced it.

## Time semantics

All authoritative timestamps are timezone-aware UTC values. Provider observation time, ingestion time, prediction time, and recommendation time are separate concepts and must not be silently collapsed.
