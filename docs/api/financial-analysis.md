# Financial Analysis API

All analysis endpoints operate on caller-supplied, normalized data in this milestone. They do not fetch providers or persist portfolios.

## Market analysis

`POST /api/v1/analysis/market`

Supplies one provider-neutral asset plus chronological OHLCV bars and explicit annualization frequency. SLAIFI returns quantitative features and technical measurements. Add `reasoning_objective` to request a separate SLAI interpretation of those calculated measurements.

## Portfolio analysis

`POST /api/v1/analysis/portfolio`

Supplies a portfolio ledger, point-in-time prices and snapshot timestamp. Optional return/equity series enable Risk Engine calculations; if one of `returns`, `equity_values` or `periods_per_year` is supplied, all are required. Optional goal data enables deterministic goal feasibility arithmetic. `reasoning_objective` asks SLAI to interpret the completed valuation/risk/goal evidence without changing it.

## Goal evaluation

`POST /api/v1/goals/evaluate`

Evaluates return and/or income targets against supplied capital and explicit assumptions. The response has two top-level fields:

- `evaluation`: authoritative Engine-derived arithmetic;
- `reasoning`: optional SLAI interpretation, present only when a reasoning objective is requested.

A target remains a target. SLAIFI does not convert target arithmetic into a guarantee or trading strategy.

## SLAI status

`GET /api/v1/integrations/slai`

Reports whether the configured reasoning integration is available, degraded, unavailable or disabled, together with public-safe agent provenance and warnings. Internal SLAI raw payloads and SharedMemory identifiers are not returned.

## Request tracing

Analysis and goal requests may carry `X-Request-ID`. SLAIFI returns it inside reasoning provenance when reasoning is used. Every SLAI reasoning operation also has a separate unique `correlation_id`; this is the identifier for the reasoning transaction and SharedMemory envelope.

## Numerical conventions

Rates use fractional internal/API form unless a field explicitly says otherwise: `0.10` means 10%. Monetary inputs use decimal-compatible JSON numbers/strings and Domain uses `Decimal` where monetary precision matters. Time values must include timezone information where the Domain requires an instant.
