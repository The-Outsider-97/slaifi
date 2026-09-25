# ADR 0003 — Normalize Market Providers Behind Domain Contracts

**Status:** Accepted

## Decision

The market domain owns a provider protocol expressed in SLAIFI domain values. Concrete vendor adapters live in infrastructure and translate provider payloads before the application sees them.

## Rationale

Provider SDK objects and naming conventions are unstable dependencies. Normalization at the boundary allows failover, multi-provider validation, deterministic tests, and future asset-class expansion without rewriting application services.

## Constraint

Raw responses may be persisted for audit/debug purposes, but raw vendor payloads must not become the public domain API.
