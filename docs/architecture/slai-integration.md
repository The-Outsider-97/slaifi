# SLAI Integration Boundary

SLAIFI lives at `SLAI/application/slaifi/`. Full SLAI integration means integration through explicit runtime boundaries, not direct SLAI imports throughout financial code.

## Authority and dependency direction

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

Core, Domain and Engines never import SLAI agents or SharedMemory. API routes never import concrete integrations. The composition root wires the adapter.

## Logging ownership

SLAI owns process-level logging through `SLAI/logs/logger.py`. SLAIFI does not configure an independent root logger and contains no local formatter/handler implementation. Operational SLAIFI modules that log use `logs.logger.get_logger(...)`. Domain and deterministic Engines intentionally remain logging-free.

## Canonical embedded startup

When the wider SLAI process already owns AgentFactory and SharedMemory, inject both as a pair:

```python
app = create_app(
    slai_factory=agent_factory,
    slai_shared_memory=shared_memory,
)
```

Injected runtime objects remain host-owned. SLAIFI does not release or close them.

## Standalone SLAIFI process inside SLAI

`SLAI/run_slaifi.py` configures the canonical SLAI logger, loads SLAIFI settings and starts the FastAPI app. The SLAI reasoning adapter may lazily create AgentFactory and SharedMemory only when the host did not inject them; those adapter-owned resources are then released during application shutdown.

No current-working-directory or `sys.path` mutation is used.

## Reasoning transaction

Each request contains authoritative financial evidence, constraints, assumptions, uncertainty metadata and optional caller `request_id`. The adapter creates a unique reasoning `correlation_id` and records request/result envelopes in SharedMemory under:

```text
slaifi:reasoning:request:<correlation_id>
slaifi:reasoning:result:<correlation_id>
```

SLAI interpretation remains separate from Engine calculations. SharedMemory is coordination/provenance context, not durable financial persistence.
