# SLAI Integration Boundary

SLAIFI is designed to live at `SLAI/applications/slaifi/` while keeping its financial core independently importable and testable.

## Ownership

SLAIFI owns observations, financial domain objects, deterministic/statistical calculations, assumptions, and result provenance. SLAI contributes contextual reasoning and synthesis through an Application-owned interface.

```text
SLAIFI Application
       ↓
FinancialReasoner protocol
       ↑
SlaiFinancialReasoner
       ↓
SLAI AgentFactory
       ↓
ReasoningAgent
       ↕
SLAI SharedMemory
```

Core, Domain, and Engines never import SLAI. API routes never import SLAI. The concrete adapter is created at the composition root.

## Runtime integration

`SlaiFinancialReasoner` lazily imports:

- `src.agents.agent_factory.AgentFactory`;
- `src.agents.collaborative.shared_memory.SharedMemory`.

It creates the registered reasoning agent through `AgentFactory.create("reasoning", shared_memory=...)`. This follows SLAI's runtime ownership model instead of constructing a `ReasoningAgent` directly.

For each reasoning call the adapter creates a versioned evidence envelope containing:

- operation;
- objective;
- authoritative SLAIFI evidence;
- constraints;
- assumptions;
- uncertainty metadata;
- correlation identifier.

The request and result are written to SharedMemory under `slaifi:reasoning:*` keys with a configurable TTL and tags. SharedMemory is coordination/audit context, not SLAIFI's future durable financial database.

## Numerical authority

The reasoning context explicitly tells SLAI not to alter or recalculate authoritative numerical evidence. The returned interpretation is stored separately from calculated features, portfolio snapshots, risk results, and goal evaluations.

This prevents a qualitative reasoning result from silently becoming financial truth.

## Availability modes

`SLAIFI_SLAI_ENABLED=false` disables the integration while keeping the financial API operational.

By default SLAI is optional. If the wider runtime is absent, financial calculations still execute and the reasoning result reports `unavailable`.

`SLAIFI_SLAI_REQUIRED=true` changes this to fail-fast behavior: application creation fails when SLAI cannot initialize, and required reasoning failures use a typed `ReasoningUnavailableError` mapped to HTTP 503 when they occur during a request.

## Scope of integration

The adapter deliberately uses the SLAI component that owns `reasoning`, `inference`, and `decision_support`. It does not indiscriminately invoke Language, Browser, Knowledge, Safety, or other agents for every financial request. Additional agents should be added only through explicit SLAIFI application contracts when their outputs have a defined provenance and responsibility. This avoids turning AgentFactory into an implicit service locator inside business logic.
