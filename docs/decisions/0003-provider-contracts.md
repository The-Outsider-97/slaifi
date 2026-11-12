# ADR 0003 — Normalize Market Providers Behind Domain Contracts

**Status:** Accepted

## Decision

The market domain owns a provider protocol expressed in SLAIFI domain values. Concrete vendor adapters live in infrastructure and translate provider payloads before the application sees them.

## Rationale

Provider SDK objects and naming conventions are unstable dependencies. Normalization at the boundary allows failover, multi-provider validation, deterministic tests, and future asset-class expansion without rewriting application services.

## Constraint

Raw responses may be persisted for audit/debug purposes, but raw vendor payloads must not become the public domain API.

## Consequence (multi-source gateway)

Failover is implemented as a `MultiSourceGateway` that composes one adapter per vendor behind the
domain `MarketGateway` contract: ordered failover, per-source cooldown and free-tier request
budgets, a durable cache of the last real observations, and per-result provenance (source, attempts,
`last_known`). Adapters are written against the vendors' documented response shapes; the in-app
*Check providers* action verifies them against the live services with the user's own keys. No
generated data exists in the package; tests use doubles that live only under `tests/`.
