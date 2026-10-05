# SLAI Integration Boundary

SLAIFI lives at `SLAI/applications/slaifi/`. Full SLAI integration means using the wider runtime through explicit application contracts where it improves financial decision support, not importing agents throughout deterministic finance code.

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
        ├── Reasoning Agent
        └── Quality Agent
               ↓
         pass / warn / block
               ↓
       optional single refinement
        ↕
SLAI SharedMemory
```

Core, Domain, and Engines never import SLAI agents or SharedMemory. API routes depend on application contracts/services, not concrete SLAI implementations. The composition root wires the adapter.

## Responsibilities

### Reasoning Agent

The Reasoning Agent receives structured authoritative evidence produced by SLAIFI, including available market state, deterministic indicators, risk measurements, portfolio valuation/allocation, goal constraints, missing evidence, assumptions, and uncertainty. It may synthesize and explain that evidence but may not silently recalculate or replace authoritative values.

### Quality Agent

When enabled, the Quality Agent reviews the reasoning artifact. The adapter treats its verdict as follows:

```text
pass
→ expose interpretation with normal provenance

warn
→ expose interpretation, mark result degraded/partial

block
→ run at most one controlled Reasoning Agent refinement

block after refinement
→ hide interpretation, preserve deterministic finance, return degraded/failed provenance
```

The Quality Agent may internally use SLAI workflow-control integrations such as Handler/Safety according to SLAI configuration. SLAIFI does not duplicate that general orchestration locally.

### SharedMemory

SharedMemory stores bounded request/result audit records with TTLs. It is coordination/provenance state, not durable market or portfolio persistence. Financial facts remain in their authoritative financial sources.

### AgentFactory

AgentFactory creates/reuses SLAI agents and provides lifecycle ownership. When the SLAI host injects AgentFactory and SharedMemory, SLAIFI does not release or close those host-owned resources. When SLAIFI lazily creates its own integration runtime, it releases only the agents/resources it owns.

## Reasoning transaction

Each reasoning operation receives a correlation ID that is independent from user IDs, portfolio IDs, ticker symbols, and caller request IDs.

```text
slaifi:reasoning:request:<correlation_id>
slaifi:reasoning:result:<correlation_id>
```

The version-3 request envelope records:

- source and operation;
- objective;
- authoritative evidence;
- constraints;
- assumptions;
- uncertainty;
- caller request ID;
- correlation ID;
- timestamp;
- requested agent and reasoning mode.

The result envelope records a compact audit summary: completion time, duration, runtime status, reasoning metadata, quality result, interpretation, warnings, agent identity/version, and correlation/request IDs. Raw private portfolio payloads are not written to logs.

## Guardrails

The reasoning context explicitly states that:

- Domain/Engine calculations are authoritative;
- agents may not replace or silently recalculate authoritative values;
- missing prices, holdings, goals, performance, or confidence may not be fabricated;
- guaranteed returns may not be implied;
- analysis may not be converted into a trade-execution instruction;
- uncertainty and missing evidence must be reported.

The public API exposes safe reasoning provenance only: status, interpretation, agent identity/version, strategy, confidence when actually supplied, outcome, validation status, degraded state, correlation/request IDs, and warnings.

## Why other SLAI agents are not invoked by default

Total integration does not mean maximum agent count.

- **Planning Agent:** current market and portfolio pipelines are short, known workflows with deterministic stages. Application orchestration is faster and more reliable than invoking a planner for every request. A planner becomes justified when evidence acquisition itself becomes conditional or multi-path.
- **Execution Agent:** SLAIFI currently performs no trades or irreversible financial actions, so an execution agent would add no valid responsibility.
- **Learning / Adaptive Agents:** they can alter strategy based on feedback, but SLAIFI currently lacks a validated outcome-feedback dataset suitable for learning. They are therefore not allowed to modify price history, trades, accounting, indicators, or deterministic risk. They should be introduced only around explicitly separated preferences/analysis strategy when trustworthy feedback exists.
- **Evaluation Agent:** broad system evaluation is better suited to offline/release assessment. The Quality Agent is the narrower per-artifact check required in the online reasoning path.
- **Observability Agent:** provider latency, request IDs, agent IDs, degraded state, cache behavior, and analysis duration are deterministic telemetry and are logged directly. An AI agent is not required to record those facts.
- **Knowledge / Reader / Browser / Network Agents:** live financial truth comes from provider contracts, not agent browsing. These agents may later support contextual research, but their output must never substitute authoritative price/portfolio data.
- **Alignment / Privacy / Safety Agents:** current SLAIFI output is non-executing decision support. Quality Agent workflow control may use configured SLAI Handler/Safety collaboration internally. Explicit additional stages should be added only when personalized actions or higher-risk execution capabilities exist.

## Failure semantics

```text
SLAI available
→ deterministic finance + quality-reviewed interpretation + provenance

SLAI degraded
→ deterministic finance + limited/degraded interpretation + warnings

SLAI unavailable and optional
→ deterministic finance remains valid; interpretation is absent

SLAI required and unavailable
→ controlled ReasoningUnavailableError
```

A healthy agent process does not automatically make a reasoning artifact healthy. Per-result degradation, validation state, and Quality Agent verdicts determine what SLAIFI exposes.

## Portfolio latency policy

`GET /api/v1/portfolio/current` does not invoke SLAI by default. It returns valuation and other deterministic results first. SLAI reasoning is requested explicitly with `include_reasoning=true`, allowing the user-facing portfolio to remain responsive and useful during SLAI degradation or outage.
