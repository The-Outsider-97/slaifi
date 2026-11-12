# Repository audit and SLAI reuse

SLAIFI is a modular monolith (FastAPI + React/Vite) with enforced layering
(`core ← domain ← engines ← application`; `infrastructure → {core, domain}`;
`integrations → {core, domain, application.contracts}`; `api → {core, domain, application}`).
`tests/architecture` checks these imports; they still pass.

## State found at the start (HEAD 55cd325)

| Area | Found | Gap |
| --- | --- | --- |
| Market data | provider port, mock + Twelve Data adapters, overview endpoint (the mock adapter has since been deleted) | no search, quote, OHLCV by interval/range, indicators, comparison, watchlist; mock data not clearly distinguished from live |
| Analysis | stateless market/portfolio/goal calculators fed by the caller | no recommendations, no validated prediction, no back-test |
| Portfolio | pure valuation maths, one read-only "actual portfolio" JSON | no paper trading, no ledger, no persistence |
| Strategies / goals | none (goal feasibility arithmetic only) | no strategy model, presets, constraints, goal tracking |
| SLAI | reasoning adapter (AgentFactory + SharedMemory) | no safety review, no advisor |
| UI | Market Overview, My Portfolio, SLAI Academy | the other sections of the brief |

## What SLAIFI reuses from SLAI (nothing re-implemented)

| Need | SLAI component reused | Where |
| --- | --- | --- |
| SQLite persistence (WAL, foreign keys, re-entrant transactions, versioned migrations, pre-migration backups, integrity check, online backup) | `applications.tools.database.Database` / `Migration` | `infrastructure/persistence/{sqlite_store,migrations}.py` |
| Per-application data folder | `applications.tools.storage.default_data_dir("slaifi", "SLAIFI")` | `main._resolve_data_dir` |
| Logging | `logs.logger.get_logger` | `main.py`, `api/errors.py`, adapters |
| Reasoning | `src.agents.agent_factory.AgentFactory` + `SharedMemory` (reasoning agent) | `integrations/slai/reasoner.py` (existing) |
| Last-known market cache (durable SQLite beside the ledger, separate file `market_cache.db`) | same `applications.tools.database.Database` | `infrastructure/market_data/sqlite_cache.py` (falls back to an in-memory cache if the host Database is unavailable) |
| Safety screening of SLAI text | SLAI `SafetyAgent`, created through the **same** factory/shared runtime via `SlaiFinancialReasoner.agent_for` | `integrations/slai/safety.py` |

The learning feature added in this revision reuses rather than duplicates: its recommendation log is
one more `Migration` (schema v2) on the same `Database`; its SLAI calls (`goal_plan_review`,
`strategy_adaptation_review`) go through the **existing** guarded runner
`RecommendationService.run_reasoner` (interpretation guard + SafetyAgent review) that the advisor and
guidance already share — no second SLAI path, no second guard.

New code was written only where SLAI has no equivalent: financial calculations,
the strategy/goal/paper-trading domain and the hash-chained audit log (which sits on top of
SLAI's `Database`). The SLAI reasoning port is the only route to SLAI agents; the
deterministic engines never import them.

## SLAI is interpretation, never authority

* Engines compute actions, limits, goal feasibility and order outcomes. SLAI receives that
  evidence and may explain it. The explanation cannot change an action.
* Every SLAI text passes `guard_interpretation` (rejects probabilities, confidence figures,
  price targets, guarantees) and the SafetyAgent review. An unavailable safety review is reported
  as "not reviewed", never as approval.
* `SharedMemory` is not used for ledger, strategy or goal data. Those live in SQLite.

## Defects fixed in existing code

* `api/schemas/goals.py` failed strict mypy (typing).
* Test-suite fixtures and some existing tests assumed a stateless app; adjusted to the new store.
* `docs/` and `.env.example` described `application/slaifi`; the real SLAI layout is
  `applications/slaifi` (matching `applications.tools.*`). Docs corrected and the CI guard now
  forbids the *singular* path instead.
* `pyproject.toml` declared Python 3.10 while the code uses `StrEnum` and `datetime.UTC` → 3.11.

## Real-data pass (no mock, three or more providers)

* The mock provider, `SLAIFI_MARKET_PROVIDER`, `SLAIFI_MOCK_ILLUSTRATIVE_HISTORY` and
  `SLAIFI_PAPER_ALLOW_ILLUSTRATIVE_EXECUTION` were removed; an architecture test fails if any
  generated-data code appears in the package.
* Five adapters (Twelve Data, Tiingo, FMP, Finnhub, Alpha Vantage), one class per API on a shared
  `HttpMarketProvider` base, combined by `MultiSourceGateway` (failover, cooldown, free-tier
  budgets, last-known cache). SLAI offers no market-data provider, so nothing was duplicated.
* Test doubles (`tests/support`) are not part of the shipped package.
