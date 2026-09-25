# ADR 0001 — Start as a Modular Monolith

**Status:** Accepted

## Context

SLAIFI needs strong internal separation but does not yet have independent scaling, release, ownership, or availability requirements that justify distributed services.

## Decision

Use one backend deployable with explicit Python package boundaries. Keep provider, persistence, quantitative, application, API, and SLAI integration responsibilities separate and enforce import direction in tests.

## Consequences

Transactions, local development, testing, observability, and refactoring remain simple. A future service extraction must be justified by measured operational needs rather than assumed scale.
