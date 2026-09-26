# SLAIFI — SLAI Financial Intelligence

SLAIFI combines normalized financial data, deterministic quantitative analysis, explicit risk/goal evaluation, and bounded SLAI reasoning into explainable decision support.

> SLAIFI is decision-support software. Illustrative scenarios, forecasts, targets, confidence values and interpretations are uncertain and are not guarantees of financial outcomes. The current product does not execute trades.

## Runtime location

SLAIFI is designed to live at:

```text
SLAI/
├── run_slaifi.py
├── logs/
├── src/
└── application/
    └── slaifi/
```

The repository copy of `run_slaifi.py` is written for its final location at `SLAI/run_slaifi.py`.

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
AgentFactory → Reasoning Agent ↔ SharedMemory
```

Core, Domain and Engines never depend on FastAPI, React or SLAI agents. The Reasoning Agent interprets already-calculated evidence and cannot replace Engine calculations.

## Market Overview product state

The React Market Overview implements the supplied SLAIFI visual design: fixed desktop workspace navigation, summary cards, understated performance chart, SLAI insight, market watch, goal guidance and educational footer, with responsive sidebar/panel behavior.

Data provenance is explicit. The current market provider is a mock provider, so screenshot-aligned market levels, historical chart data and market-watch signals are labelled illustrative. SLAI availability is never faked: the insight CTA becomes operational only when the status endpoint reports an available/degraded runtime, and an actual insight request flows through SLAIFI Engines before the Reasoning Agent receives evidence.

See `docs/architecture/frontend-runtime.md` and `docs/architecture/slai-integration.md` for the final data and agent flows.

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

1. Financial calculations are authoritative in Domain/Engines; SLAI provides contextual reasoning only.
2. Observations, assumptions, uncertainty, calculations and interpretations remain distinguishable.
3. No silent annualization, FX conversion, missing-data substitution, or fake provider/SLAI availability.
4. Goals are targets/constraints, not guarantees.
5. Market-watch demo statuses are not production recommendations.
6. SLAI logging is owned by `SLAI/logs/logger.py`.
7. Architecture tests enforce dependency direction and prohibit cwd/`sys.path` runtime hacks.
