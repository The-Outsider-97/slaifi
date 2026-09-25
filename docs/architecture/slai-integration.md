# SLAI Integration Boundary

SLAI is an integration, not the SLAIFI domain model.

## Direction

```text
SLAIFI application
      ↓ depends on
SLAIFI-owned reasoning contract
      ↑ implemented by
integrations/slai adapter
      ↓ translates to
SLAI API / runtime
```

SLAI-specific classes, agent registries, prompts, transport details, and runtime configuration must not leak into domain or quantitative engines.

## SLAI responsibilities

SLAI may contribute contextual synthesis, conflicting-signal analysis, scenario reasoning, goal interpretation, qualitative evidence assessment, and human-readable explanations.

SLAI must not be the authoritative calculator for prices, returns, volatility, portfolio accounting, risk measures, feature values, or backtest results when deterministic/statistical implementations exist.

## Failure behavior

A future SLAI adapter must expose explicit timeout/unavailable/error states. A missing reasoning response must not be converted into fabricated confidence or silently treated as a positive signal. Quantitative outputs remain usable without SLAI when the use case permits.

## Versioning

Recommendation provenance will record the SLAI reasoning contract version and, where available, the concrete SLAI model/agent/runtime version used for the assessment.
