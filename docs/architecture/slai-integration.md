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

## Canonical embedded startup

When SLAIFI is hosted by the wider SLAI process, the host should inject its already-created runtime components instead of relying on working-directory imports:

```python
app = create_app(
    slai_factory=agent_factory,
    slai_shared_memory=shared_memory,
)
```

This keeps the canonical `SLAI/applications/slaifi/` installation independent of `os.getcwd()` and avoids `sys.path` manipulation. Lazy imports remain a standalone convenience when `src` is already importable.

SLAIFI logging also preserves existing root handlers by default, so embedding the application does not replace SLAI's logging ownership.

## Runtime integration

`SlaiFinancialReasoner` uses `AgentFactory.create("reasoning", shared_memory=...)`. It does not instantiate `ReasoningAgent` directly.

For each reasoning call the adapter creates a versioned evidence envelope containing operation, objective, authoritative SLAIFI evidence, constraints, assumptions, uncertainty metadata, and a correlation identifier. Request and result envelopes are written to SharedMemory under `slaifi:reasoning:*` keys with configurable TTL and tags.

SharedMemory is coordination/audit context, not SLAIFI's future durable financial database.

## Numerical authority

The reasoning context explicitly tells SLAI not to alter or recalculate authoritative numerical evidence. Returned interpretation remains separate from calculated features, portfolio snapshots, risk results, and goal evaluations.

## Availability modes

`SLAIFI_SLAI_ENABLED=false` disables contextual reasoning while keeping financial calculations operational. SLAI is optional by default; absence produces an `unavailable` reasoning state. `SLAIFI_SLAI_REQUIRED=true` changes this to fail-fast behavior and uses `ReasoningUnavailableError` for explicit service-unavailable handling.

## Scope

The adapter uses the SLAI component whose registered responsibility includes reasoning, inference, and decision support. It does not indiscriminately invoke Language, Browser, Knowledge, Safety, or other agents for every financial request. Additional SLAI agents should be integrated only behind explicit application contracts with defined provenance and responsibility; this prevents AgentFactory from becoming an implicit service locator inside business logic.
