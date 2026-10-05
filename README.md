# SLAIFI — SLAI Financial Intelligence

SLAIFI combines normalized financial data, deterministic quantitative analysis, explicit portfolio/risk/goal evaluation, and bounded SLAI interpretation into explainable financial decision support.

SLAIFI does not execute trades. Market data, portfolio accounting, indicators, risk statistics, and goal arithmetic remain deterministic and authoritative. SLAI augments those facts with contextual interpretation and quality control; it does not replace financial mathematics.

## Runtime location

SLAIFI is designed to live inside the wider SLAI repository at:

```text
SLAI/
├── run_slaifi.py
├── logs/
├── src/
└── applications/
    └── slaifi/
```

The repository root contains a real `__init__.py` so `applications.slaifi` is an importable SLAI application package. The implementation remains physically below `backend/slaifi` to preserve standalone packaging without global `sys.path` mutation.

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
SlaiFinancialReasoner adapter
      ↓
SLAI AgentFactory
      ├── Reasoning Agent
      └── Quality Agent
             ↓
       bounded verdict/refinement
      ↕
SLAI SharedMemory
```

Core, Domain, and Engines do not import SLAI agents. The adapter is created at the composition boundary. A Quality Agent review may trigger at most one controlled Reasoning Agent refinement pass; a final blocking quality verdict prevents the interpretation from being exposed while preserving deterministic financial output.

## Market data

`SLAIFI_MARKET_PROVIDER` explicitly selects the provider:

- `mock` — deterministic development/test provider only;
- `twelvedata` — external live/delayed provider through the provider-neutral market contract.

Production refuses to start with the mock provider. Twelve Data requires `SLAIFI_MARKET_API_KEY`. Provider credentials stay backend-side.

Quote and historical requests use bounded TTL caches to suppress duplicate provider calls without turning stale data into permanent state. Cache duration is configured separately for quotes and history.

The Market Overview frontend consumes only backend API contracts. It does not contain production demo price arrays, fake market-watch rows, fake signals, or synthetic OHLCV analysis input. When the mock provider is configured, financial values are intentionally hidden instead of being presented as real market information.

## Portfolio runtime

`SLAIFI_PORTFOLIO_FILE` may point to an actual portfolio ledger. If no portfolio source is configured, `/api/v1/portfolio/current` returns an empty/no-content state instead of inventing holdings.

Normal portfolio loading is deterministic and does not invoke SLAI. The frontend explicitly requests `include_reasoning=true` only when the user asks for contextual reasoning. Only currently open positions require current market quotes; fully closed historical positions do not cause unnecessary provider requests.

## SLAI behavior

SLAIFI currently uses SLAI where the general AI runtime adds measurable value:

- **Reasoning Agent** — interprets structured, already-calculated market/portfolio evidence;
- **Quality Agent** — checks the reasoning artifact and can return pass/warn/block;
- **SharedMemory** — records bounded request/result provenance with TTLs and correlation IDs;
- **AgentFactory** — owns agent creation/reuse and lifecycle integration.

Quality warnings degrade provenance explicitly. A blocking verdict can trigger exactly one refinement pass. A second block hides the interpretation rather than looping or fabricating a replacement.

SLAIFI intentionally does not invoke every SLAI agent. Planning is unnecessary for the current short, deterministic analysis pipelines; Execution is inappropriate because SLAIFI executes no trades; Adaptive/Learning agents are not used to mutate financial truth or learn from unvalidated outcomes. Quality Agent workflow control may use SLAI's configured Handler/Safety collaboration internally without SLAIFI recreating those systems.

## Degraded operation

```text
SLAI available
→ deterministic finance + validated contextual interpretation

SLAI degraded
→ deterministic finance + explicitly degraded interpretation/provenance

SLAI unavailable and optional
→ deterministic finance continues; no AI interpretation is fabricated

SLAI unavailable and required
→ explicit startup/runtime failure
```

## Development

Backend requires Python 3.12 for the integrated SLAI validation path:

```text
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check backend tests run_slaifi.py
mypy backend
```

Frontend:

```text
cd frontend
npm install
npm run typecheck
npm test
npm run build
npm run dev
```

Set `VITE_API_BASE_URL` when the API is not available at `http://127.0.0.1:8000`.

See `.env.example`, `docs/architecture/frontend-runtime.md`, and `docs/architecture/slai-integration.md` for the current runtime contracts.
