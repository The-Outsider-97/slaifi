# SLAIFI — SLAI Financial Intelligence

SLAIFI is an architecture-first financial-intelligence web application. It is designed to combine normalized market data, deterministic quantitative analysis, explicit risk and goal evaluation, and a bounded SLAI reasoning layer into explainable financial decision support.

> SLAIFI is decision-support software. Forecasts, scenarios, targets, confidence values, and recommendations are uncertain and are not guarantees of financial outcomes.

## Architecture status

The repository is currently in the **Architecture Foundation** milestone. The implementation is a modular monolith with strict dependency boundaries and one minimal end-to-end market-overview slice.

```text
Frontend / API
      ↓
Application
      ↓
Engines (pure computation) + Domain
      ↓
Core contracts and shared primitives

Infrastructure and integrations implement lower-level contracts and are wired only at the composition root.
```

The central rule is that domain and quantitative logic do not know about FastAPI, React, databases, market-data vendors, or SLAI internals.

## Repository layout

```text
backend/slaifi/       Python application package
frontend/             React + TypeScript client
docs/                 Architecture, finance, and ADR documentation
tests/                Unit, API, financial, integration, and architecture tests
.github/workflows/     CI validation
```

Directories for persistence, predictive models, advanced engines, background jobs, and additional product areas are added only when a concrete implementation milestone requires them.

## Backend quick start

Requires Python 3.12+.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
# source .venv/bin/activate

python -m pip install -e ".[dev]"
uvicorn slaifi.main:app --app-dir backend --reload
```

Backend API: `http://127.0.0.1:8000`

Health: `GET /health`

Market vertical slice: `GET /api/v1/market/overview`

## Frontend quick start

Requires a current Node.js LTS release.

```bash
cd frontend
npm install
npm run dev
```

Create `frontend/.env.local` when the API is not available at the default URL:

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## Validation

```bash
pytest
ruff check backend tests
mypy backend

cd frontend
npm run typecheck
npm run build
```

Architecture tests parse imports and fail when a forbidden layer dependency or package cycle is introduced.

## Core design principles

1. Numerical finance logic is deterministic or statistical where possible; SLAI does not replace quantitative calculation.
2. Observations, calculated indicators, model predictions, assumptions, uncertainty, SLAI interpretation, and recommendations remain distinguishable.
3. Market-data vendors are adapters behind normalized provider contracts.
4. Risk analysis is independent from expected-return prediction.
5. Recommendations are reproducible records, not free-form labels.
6. User goals are constraints and targets, never guarantees.
7. The system starts as a modular monolith; distributed services are deferred until operational evidence justifies them.

See [`docs/architecture/overview.md`](docs/architecture/overview.md) for the system design and [`docs/architecture/dependency-rules.md`](docs/architecture/dependency-rules.md) for enforceable import rules.
