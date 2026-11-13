# SLAI Integration Boundary

SLAIFI lives at `SLAI/applications/slaifi/`. Full SLAI integration means integration through explicit runtime boundaries, not direct SLAI imports throughout financial code.

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

## Operations sent to SLAI

All go through `RecommendationService.run_reasoner(request, purpose)` (guard + safety review, labelled interpretation, optional):

| Operation | Purpose |
|---|---|
| `recommendation_explanation` | explain a deterministic recommendation; its uncertainty block now carries the measured track record (verdict, decisive results, hit rate) |
| `goal_plan_review` | read a goal's figures, plan and progress in plain language (`POST goal-tracker/{id}/review`) |
| `strategy_adaptation_review` | comment on rule-based strategy suggestions; constraint `never_suggest_more_risk` (`GET strategies/{id}/adaptations?explain=true`) |
| advisor / guidance operations | unchanged |

See `docs/finance/learning-and-adaptation.md`. A SLAI reply that states probabilities or guarantees is withheld, not shown.

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


## Optional agents: Knowledge, Financial, Learning

Beyond reasoning, quality and safety, three more SLAI agents can be used. They are **opt-in and off by
default** (Settings → *Extra help from SLAI*; first-start defaults `SLAIFI_SLAI_KNOWLEDGE_ENABLED`,
`…_FINANCIAL_ENABLED`, `…_LEARNING_ENABLED`, all `false`). The choice is stored in SLAIFI's own
`settings` table, a change is written to the audit log (`agent.enabled` / `agent.disabled`), and
`SLAIFI_SLAI_ENABLED=false` still turns every SLAI agent off. A switched-off agent is never created. The former
Optimization switch is read as the Financial switch when no Financial choice was saved; the old
`SLAIFI_SLAI_OPTIMIZATION_*` variables are no longer read.

Rules that hold for all three:

* **Advice and records only.** Nothing an agent returns places an order, changes a strategy or alters
  a number SLAIFI computes. Financial-agent output is re-checked by SLAIFI's own engine
  (`engines/allocation.verify_allocation`) and shown only if every check passes; otherwise the
  result is `rejected` with the reason. The one exception to "nothing places an order" is the person pressing
  **Apply** / **Apply all** on a checked suggestion: SLAIFI then places ordinary simulated orders through
  the paper-trading service (same checks, same fees), not the agent.
* **Honest when absent.** If an agent cannot run (module missing, PyTorch or SciPy not installed,
  failure) the feature shows NOT AVAILABLE with the reason and the rest of SLAIFI is unaffected.
  Settings shows each agent as *Off*, *On (not used yet)*, *On and working* or *On, but SLAI could not run it*.
* **Layering unchanged.** Ports and result types live in `application/contracts/agents.py`; the adapters
  in `integrations/slai/{knowledge,financial,learning}.py` take callables (switch, report, agent
  provider) rather than importing application services. They share the single SLAI runtime created for
  reasoning (`SlaiFinancialReasoner.agent_for`).

| Agent | What SLAIFI uses it for | SLAI calls | Notes |
| --- | --- | --- | --- |
| Knowledge | "Look something up" on the Advisor page: passages from SLAIFI's own `docs/` | `add_document`, `retrieve` | Indexes only SLAIFI's markdown, by heading (ids `slaifi:<file>#n`); results are filtered to that prefix. No user data, no web. |
| Financial | "Suggested allocation" on Paper trading, with **Apply** per line and **Apply all** | `data.ingest_observations` (the real daily closes SLAIFI holds, with their source), then `portfolio.optimize_allocation` (the agent estimates the historical moments and delegates to SLAI's Optimization agent), `data.counts` for Check | Statistics are historical, annualised from real aligned daily returns (≥ 60 observations); not a forecast. SLAIFI's cash reserve is mapped onto the agent's fully-invested problem by scaling (`w = b·v`, cap `/b`, `γ = b/λ`; "steadiest" is a very large γ). SLAIFI re-checks the answer itself (`verify_allocation`). Needs SciPy for the solver. Not used: the agent's other operations (VaR/ES, beta/alpha, rebalance amounts and costs, …) because SLAIFI already has its own tested engines for what it shows; a Risk check through the agent is possible later. |
| Learning | "Share results with SLAI" on Strategies & goals | `perform_task` modes `observe`, `query` | Sends each *scored* recommendation as an `outcome` signal with metric `forward_return`, `validated=false` (so it can never train the agent's selector or its reward statistics) and a stable id (`slaifi:outcome:<record id>`), so repeats are duplicates. SLAIFI's own rule-based learning does not read anything back. Needs PyTorch (the agent imports it). |
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

### Applying a suggestion

`POST paper/portfolios/{id}/allocation/apply` takes only a `suggestion_id` (and optionally the symbols to
apply). The plan stays on the server, so the browser cannot change an amount. It is refused if the
portfolio changed since the suggestion (staleness marker) or after the plan expired. Sells go first so
their cash is available; each order has a deterministic client order id, so pressing Apply twice places
one order. Every order passes through `PaperTradingService.place_order` (market-hours, quote-age,
strategy-limit and cash checks, platform fee). When the *whole* remaining plan is applied the per-order
concentration test is waived only because the complete mix has already been verified; a single **Apply**
is always checked line by line.
