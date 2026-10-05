# SLAI Integration Boundary

SLAIFI integrates into the wider ecosystem at `SLAI/applications/slaifi/`. Full SLAI integration means using explicit runtime boundaries, not importing SLAI throughout financial code.

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
SLAI AgentFactory + SharedMemory
        ↓
Reasoning Agent
        ↓
Quality Agent
        ↓
optional one-pass refinement
        ↓
Safety Agent (generated interpretation only)
```

Core, Domain and Engines never import SLAI agents or SharedMemory. API routes never import concrete SLAI integrations. The composition root wires the adapter.

## Agent responsibilities

- **Reasoning Agent** interprets structured, already-calculated financial evidence. It does not own prices, portfolio accounting, indicators, risk arithmetic or goal arithmetic.
- **Quality Agent** checks the generated reasoning artifact. A blocking verdict may trigger exactly one controlled refinement pass; there is no recursive agent loop.
- **Safety Agent** reviews only the final generated interpretation. Raw financial evidence and private portfolio state are deliberately not copied into the Safety Agent payload. `allow`, `review`, and `block` are exposed as provenance; `block` suppresses the interpretation while leaving deterministic financial output intact.
- **SharedMemory** stores short-lived request/result provenance under a configured TTL. It is coordination memory, not durable financial persistence.

Planning, Learning, Adaptive, Evaluation and other SLAI agents are intentionally not invoked on every financial request. The current market/portfolio pipelines are fixed and deterministic, so a planner would add latency without changing the plan. Learning/Adaptive require an explicit, validated outcome/reward contract before they may influence future analytical strategy. Evaluation is not duplicated where the Quality Agent already owns artifact validation.

## Runtime contracts

The adapter uses the SLAI runtime through:

- `AgentFactory.create(agent_type, shared_memory=...)` for lazily shared agent instances;
- `ReasoningAgent.reason(problem, reasoning_type=None, context=None)` for contextual reasoning;
- `QualityAgent.perform_task(...)` for bounded artifact quality assessment;
- `SafetyAgent.perform_task(data_to_assess, context=...)` for interpretation safety review;
- `AgentFactory.release(agent_type)` for adapter-owned lifecycle cleanup;
- SharedMemory `set(..., ttl=..., tags=...)` for correlation/provenance records.

When AgentFactory and SharedMemory are injected by the wider SLAI host, both remain host-owned. SLAIFI does not close or release them. When SLAIFI creates its own SLAI runtime, it releases only the resources it owns.

## Reasoning transaction

Every analysis gets a correlation ID independent of portfolio IDs, symbols, users and HTTP request IDs:

```text
slaifi:reasoning:request:<correlation_id>
slaifi:reasoning:result:<correlation_id>
```

The request envelope records source, operation, objective, authoritative evidence, constraints, assumptions, uncertainty, caller request ID, correlation ID, timestamp and requested reasoning mode. The result envelope records a compact audit summary: agent/version, status, reasoning metadata, Quality result, public-safe Safety result, interpretation, warnings, IDs and duration. Raw Safety/Quality internals are not exposed through the public API.

Both records use the configured TTL and the tags `slaifi` and `financial_reasoning`.

## Reasoning authority

The Reasoning Agent receives structured evidence covering, where available, market state, observed metrics, portfolio relevance, risk, goals, conflicting signals, uncertainty and conditions that could change the interpretation.

Domain/Engine values are authoritative. SLAI may explain and synthesize; it may not fabricate prices, holdings, performance, goals or confidence, silently replace calculations, imply guaranteed returns, or convert analysis into an execution instruction.

Public responses expose only bounded provenance: runtime status, interpretation, agent identity/version, strategy, confidence, outcome, validation status, Safety status/agent, degraded flag, correlation ID, request ID and warnings. Raw reasoning output and SharedMemory keys remain internal.

## Failure semantics

```text
SLAI available
→ deterministic financial output + reviewed interpretation + provenance

Quality warning / Safety review
→ deterministic output + interpretation + explicit degraded status

Quality block after one refinement / Safety block
→ deterministic output + interpretation suppressed + explicit degraded status

SLAI runtime unavailable and optional
→ deterministic financial output remains valid; reasoning unavailable

SLAI runtime unavailable and required
→ controlled ReasoningUnavailableError
```

A healthy agent process does not automatically make an individual reasoning result healthy. Per-analysis degradation, validation and Safety outcomes are propagated independently from runtime health.
