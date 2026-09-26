# SLAI Integration Boundary

SLAIFI lives at `SLAI/application/slaifi/`. Full SLAI integration means integration through explicit runtime boundaries, not direct SLAI imports throughout financial code.

## Authority and dependency direction

```text
Market / portfolio input
        ↓
SLAIFI Domain
        ↓
SLAIFI Engines
        ↓
Application use case
        ↓
Authoritative financial evidence
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

## Actual SLAI v2.3 contracts

The adapter uses the real SLAI APIs:

- `AgentFactory.create(agent_type, shared_memory=...)` creates or retrieves the registered Reasoning Agent;
- `ReasoningAgent.reason(problem, reasoning_type=None, context=None)` performs typed reasoning;
- `AgentFactory.release(agent_type)` releases an adapter-owned agent;
- SharedMemory `set(..., ttl=..., tags=...)` supports the SLAIFI transaction records;
- Reasoning Agent runtime/health data is used for status rather than inferred from import success.

## Logging ownership

SLAI owns process-level logging through `SLAI/logs/logger.py`. SLAIFI does not configure an independent root logger. Domain and deterministic Engines remain logging-free.

## Lifecycle ownership

When the wider SLAI host injects AgentFactory and SharedMemory, both must be supplied together and remain host-owned. SLAIFI does not release or close them.

When the root SLAIFI launcher is running inside SLAI without injected objects, the adapter lazily obtains AgentFactory and SharedMemory and owns that integration lifecycle for its process. On shutdown it releases the Reasoning Agent through the Factory and closes only the memory object it obtained for that lifecycle.

## Versioned reasoning transaction

Every reasoning operation receives a unique correlation ID independent of portfolio IDs, ticker symbols, users, or request IDs.

```text
slaifi:reasoning:request:<correlation_id>
slaifi:reasoning:result:<correlation_id>
```

The version-2 request envelope records source, operation, objective, authoritative evidence, constraints, assumptions, uncertainty, caller request ID, correlation ID, timestamp, requested agent and reasoning mode. The result envelope intentionally stores a compact audit summary instead of the Reasoning Agent's potentially large native output: agent/version, runtime result status, strategy, confidence, outcome, validation status, degraded flag, interpretation, warnings, IDs and completion timestamp.

Both records use the configured TTL and the tags `slaifi` and `financial_reasoning`. SharedMemory remains coordination/provenance context, not durable financial persistence.

## Reasoning intelligence

The Reasoning Agent receives structured evidence and an explicit authority contract. SLAIFI asks it, where the available evidence supports the topic, to reason across:

1. market context;
2. observed evidence;
3. portfolio relevance;
4. risk considerations;
5. goal alignment;
6. conflicting signals;
7. uncertainty;
8. conditions that could change the interpretation.

The guardrails state that Domain/Engine values are authoritative. The agent may explain and synthesize; it may not fabricate missing prices, holdings, goals or confidence, silently replace calculations, imply guaranteed returns, or convert illustrative analysis into an execution instruction.

The public API exposes only safe provenance: status, interpretation, agent identity/version, strategy, confidence, outcome, validation status, degraded flag, correlation ID, request ID and warnings. Raw Reasoning Agent output and SharedMemory keys stay internal.

## Failure semantics

```text
SLAI available
→ financial output + interpretation + provenance

Reasoning result degraded
→ financial output + degraded interpretation/warnings

Runtime unavailable and optional
→ financial output remains valid; reasoning status unavailable

Runtime unavailable and required
→ controlled ReasoningUnavailableError
```

A healthy agent process does not automatically make an individual reasoning result healthy: Phase-3 `degraded` and validation status are reflected in the per-result SLAIFI status.
