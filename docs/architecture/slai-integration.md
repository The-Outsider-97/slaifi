# SLAI Integration Boundary

SLAIFI is designed to live at `SLAI/applications/slaifi/` while keeping its financial core independently importable and testable. “Full SLAI integration” therefore means complete integration through an explicit boundary, not direct SLAI imports throughout the financial codebase.

## Authority and dependency direction

SLAIFI owns normalized observations, financial Domain objects, deterministic/statistical calculations, assumptions and result provenance. SLAI contributes contextual reasoning and synthesis through an Application-owned interface.

```text
SLAIFI Core / Domain / Engines
              ↓
      Application use case
              ↓
     FinancialReasoner port
              ↑
    SlaiFinancialReasoner
              ↓
      SLAI AgentFactory
              ↓
       Reasoning Agent
              ↕
       SLAI SharedMemory
```

Core, Domain and Engines never import SLAI. API routes never import SLAI. Only the concrete integration adapter knows SLAI runtime module names, and only the composition root wires that adapter to use cases.

## Canonical embedded startup

Inside the wider SLAI runtime, inject the host-owned objects as a pair:

```python
app = create_app(
    slai_factory=agent_factory,
    slai_shared_memory=shared_memory,
)
```

The pair requirement is deliberate: a host Factory with a separately auto-created SharedMemory, or vice versa, can create inconsistent agent coordination state. Partial injection therefore raises a configuration error.

Injected runtime objects are host-owned. SLAIFI never releases the injected Factory's agent or closes injected SharedMemory during API shutdown.

## Standalone startup

When SLAIFI runs independently and SLAI is importable, `SlaiFinancialReasoner` lazily imports `src.agents.agent_factory.AgentFactory` and `src.agents.collaborative.shared_memory.SharedMemory`, creates the configured registered reasoning agent through `AgentFactory.create(...)`, and owns those lazily-created resources. The API lifespan then closes the SLAIFI-owned adapter; the adapter releases its managed reasoning agent through the Factory and closes its own SharedMemory.

When SLAI is absent and integration is optional, financial calculations remain available and reasoning reports `unavailable`. No `sys.path` mutation or current-working-directory assumption is used.

## Reasoning transaction

Each reasoning request contains:

- operation name;
- objective;
- authoritative SLAIFI evidence;
- hard constraints;
- explicit assumptions;
- uncertainty metadata;
- optional caller `request_id` trace metadata.

The adapter generates a unique `correlation_id` for each reasoning operation unless an internal caller explicitly supplies one. It writes versioned request/result envelopes to SharedMemory under:

```text
slaifi:reasoning:request:<correlation_id>
slaifi:reasoning:result:<correlation_id>
```

with configurable TTL and the tags `slaifi` and `financial_reasoning`.

This avoids collisions when the same asset, portfolio or goal is analyzed repeatedly. Business IDs are evidence/context, not memory transaction IDs.

## Reasoning instruction

The Reasoning Agent receives an explicit instruction that the supplied numerical evidence is authoritative. It may interpret relationships, conflicts, uncertainty and goal implications, but it must not replace or silently recalculate the supplied financial truth and must not imply guaranteed returns.

The adapter preserves the raw SLAI output internally for integration diagnostics/provenance, but the public API does not expose raw output or SharedMemory keys.

## Health and availability

The adapter can summarize agent runtime state and, when available, SLAI Factory and SharedMemory health. Public API status is intentionally narrower than internal diagnostics.

Configuration modes:

- `SLAIFI_SLAI_ENABLED=false`: reasoning disabled; financial calculations stay operational.
- default optional mode: missing/failing SLAI produces an explicit unavailable/degraded reasoning result while calculations remain available.
- `SLAIFI_SLAI_REQUIRED=true`: startup or reasoning availability failure is explicit and mapped to service-unavailable behavior.

## Why SLAI is not the calculator

SLAI integration is intentionally downstream of Engines. This keeps the system auditable:

```text
observed inputs → deterministic/statistical calculations → structured evidence
                                                       ↓
                                                SLAI interpretation
```

A future Recommendation layer may consume both calculated evidence and SLAI interpretation, but it must preserve provenance and cannot treat qualitative interpretation as a substitute for risk, return, portfolio or goal calculations.

## Future SLAI agents

The registered Reasoning Agent is the correct current integration because its responsibility includes reasoning/inference/decision-support interpretation. Browser, Knowledge, Language, Safety and other SLAI agents should not be invoked indiscriminately. If later required, each must sit behind a purpose-specific Application contract with defined input provenance, output semantics, failure behavior and authority limits.
