# SLAIFI — SLAI Financial Intelligence

SLAIFI combines normalized financial data, deterministic quantitative analysis, explicit risk/goal evaluation, and bounded SLAI reasoning into explainable financial decision support.

SLAIFI is decision-support software. Forecasts, targets, confidence values and AI interpretations are uncertain and are not guarantees of financial outcomes. The current product does not execute trades.

## Runtime location

SLAIFI is designed to live at:

```text
SLAI/
├── run_slaifi.py
├── logs/
├── src/
└── applications/
    └── slaifi/
```

The repository copy of `run_slaifi.py` supports installation inside the wider SLAI tree while keeping the financial core independently importable and testable.

## Architecture

```text
React frontend
      ↓
FastAPI delivery layer
      ↓
Application orchestration
      ↓
Domain + deterministic Engines
      ↓
authoritative financial evidence
      ↓
Application-owned FinancialReasoner port
      ↑
SLAI integration adapter
      ↓
Reasoning Agent → Quality Agent → optional one-pass refinement → Safety Agent
                         ↕
                    SharedMemory
```

Core, Domain and Engines never depend on FastAPI, React or SLAI agents. SLAI interprets already-calculated evidence and cannot replace authoritative financial calculations.

## Market and portfolio data

Production runtime does not silently substitute illustrative financial values.

- `SLAIFI_MARKET_PROVIDER=mock` is intended for development/test use only and is rejected when `SLAIFI_ENVIRONMENT=production`.
- `SLAIFI_MARKET_PROVIDER=twelvedata` uses the configured market-data API key and exposes normalized quotes/history through SLAIFI-owned provider contracts.
- Historical market charts use backend market-history data. Missing history produces an explicit unavailable/empty state rather than a fabricated series.
- The current portfolio route reads an explicitly configured portfolio ledger and values only open positions with current provider prices.
- Portfolio risk metrics are returned only when the required historical portfolio evidence exists; the frontend does not manufacture missing risk values.

## SLAI behavior

SLAI is optional unless `SLAIFI_SLAI_REQUIRED=true`.

- **Reasoning Agent** interprets structured financial evidence.
- **Quality Agent** validates the reasoning artifact and may trigger one bounded refinement pass.
- **Safety Agent** reviews the generated interpretation only. Private portfolio evidence is not copied into its payload.
- **SharedMemory** stores short-lived reasoning provenance/correlation records, not authoritative financial state.

When optional SLAI is unavailable, deterministic finance remains operational and the API/UI reports the unavailable/degraded state explicitly. SLAI never substitutes missing prices, holdings, returns, goals or deterministic metrics.

Planning, Learning, Adaptive and Evaluation agents are not called on every request. Fixed financial workflows do not benefit from a planner, and learning/adaptation is intentionally withheld until a validated outcome/feedback contract exists. This avoids unnecessary latency and prevents learned state from modifying financial truth.

See `docs/architecture/frontend-runtime.md` and `docs/architecture/slai-integration.md` for the detailed runtime boundaries.

## Backend development

Requires Python 3.12+ and the wider SLAI repository when exercising operational logging/agent integration.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check backend tests run_slaifi.py
mypy backend
```

## Frontend development

Requires a current Node.js LTS release.

```bash
cd frontend
npm install
npm run typecheck
npm test
npm run build
npm run dev
```

Set `VITE_API_BASE_URL` when FastAPI is not available at `http://127.0.0.1:8000`.

## Core design principles

- Financial calculations are authoritative in Domain/Engines; SLAI provides contextual intelligence only.
- Facts, derived metrics, AI interpretation and learned/adaptive state remain separate concerns.
- No silent annualization, FX conversion, missing-data substitution or fake provider/SLAI availability.
- Goals are targets/constraints, not guarantees.
- Provider failures are surfaced as explicit infrastructure failures rather than hidden behind fallback values.
- SLAI logging is owned by `SLAI/logs/logger.py`.
- Architecture tests enforce dependency direction and prohibit cwd/`sys.path` runtime hacks.
