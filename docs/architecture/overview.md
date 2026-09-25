# SLAIFI Architecture Overview

## Architectural style

SLAIFI starts as a **modular monolith**. The choice is intentional: financial calculations, portfolio state, recommendation provenance, and model governance benefit from transactional consistency and simple local observability while the product is young. Module boundaries are nevertheless explicit so a workload can later be extracted if operational evidence justifies it.

## Dependency direction

```text
frontend ──HTTP──> api
                 ↓
             application
                 ↓
        ┌────────┴────────┐
        ↓                 ↓
     engines            domain
        ↓                 ↓
        └────────┬────────┘
                 ↓
                core

infrastructure ──implements──> domain/core contracts
integrations    ──implements──> domain/core contracts

main.py is the composition root and is the only place allowed to wire concrete adapters to application services.
```

## Layer responsibilities

### `core`
Foundational primitives that are independent of business workflows: validated settings, base exceptions, structured logging, common enums/types, and low-level protocols that do not require domain objects.

### `domain`
Financially meaningful records, invariants, value objects, and contracts. Domain code never imports FastAPI, database libraries, provider SDKs, frontend concerns, or SLAI implementations.

### `engines`
Pure or near-pure quantitative services. An engine may consume domain values and return domain analysis values. Engines do not perform HTTP, database, filesystem, or SLAI calls. Recommendation policy will eventually live here only after its mathematical contract is defined.

### `application`
Use-case orchestration. It coordinates domain contracts and engines, defines workflow-level input/output objects, and controls transaction boundaries when persistence is introduced. Provider-specific code is forbidden.

### `infrastructure`
Concrete technical adapters: relational persistence, cache, provider clients, repositories, schedulers, and telemetry integrations. It implements contracts owned by lower layers.

### `integrations`
Explicit bounded integrations whose semantics are broader than infrastructure, especially SLAI. SLAI adapters translate between SLAIFI contracts and SLAI-specific requests/responses; SLAIFI core never imports SLAI internals.

### `api`
HTTP delivery only: routing, request/response validation, middleware, and dependency access. It calls application services and never calculates financial indicators or queries providers/databases directly.

### `frontend`
User interface and interaction state. It consumes API contracts. Financial calculations displayed in the browser are presentation transformations only; authoritative finance logic stays on the backend.

## Product-area boundaries

The target domain modules are assets, market, portfolio, goals, predictions, risk, recommendations, and education. They are added incrementally. Cross-domain coordination belongs in `application`, not by importing one domain package's internals into another.

## Deferred components

The following are intentionally not scaffolded until their first use: SQLAlchemy models/Alembic migrations, Redis caching, worker queues, model registry, prediction models, advanced feature/technical/fundamental/sentiment/regime engines, backtesting, authentication, and brokerage execution. Their boundaries are documented now, but empty packages would add false structure without executable responsibility.
