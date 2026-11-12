SLAIFI — SLAI Financial Intelligence
SLAIFI combines normalized financial data, deterministic quantitative analysis, explicit risk/goal evaluation, and bounded SLAI reasoning into explainable decision support.

SLAIFI is decision-support software. Scenarios, forecasts, targets, confidence values and interpretations are uncertain and are not guarantees of financial outcomes. SLAIFI offers **paper trading only**: simulated orders against virtual cash. Real-money trading does not exist in the code and cannot be enabled.

Quick start (from the SLAI root, e.g. `G:\GAIA\AI\SLAI`)
1. `python -m pip install "fastapi>=0.115,<1.0" "httpx>=0.27,<1.0" "pydantic>=2.9,<3.0" "pydantic-settings>=2.5,<3.0" "uvicorn[standard]>=0.30,<1.0"`
2. Set at least one – ideally three – free market-data keys, e.g. `$env:SLAIFI_TWELVEDATA_API_KEY`, `$env:SLAIFI_TIINGO_API_KEY`, `$env:SLAIFI_FMP_API_KEY` (all variables: `.env.example`).
3. `python run_slaifi.py` starts the API on http://127.0.0.1:8000.
4. UI: `cd applications\slaifi\frontend` (the `package.json` is there), then `npm.cmd install` and `npm.cmd run dev`.
5. Open Settings → Market data sources → **Check providers** to confirm each key works.

Runtime location
SLAIFI is designed to live at:

SLAI/
├── run_slaifi.py
├── logs/
├── src/
└── applications/
    └── slaifi/
The repository copy of run_slaifi.py is written for its final location at SLAI/run_slaifi.py.

Architecture
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
Core, Domain and Engines never depend on FastAPI, React or SLAI agents. The Reasoning Agent interprets already-calculated evidence and cannot replace Engine calculations.

Product state
Sections: Market Overview, Stock Analysis, My Portfolio, Paper Trading, SLAI Advisor, Strategies & Goals, Settings (plus SLAI Academy).
All market figures carry source, observation time, delay and a badge. SLAIFI shows **real market data only**: it asks up to five free-tier providers in order (Twelve Data, Tiingo, Financial Modeling Prep, Finnhub, Alpha Vantage – one free key each, at least three recommended); if none can be reached it shows the last real observation it saved, labelled **LAST KNOWN DATA** with the time it was observed; if it has none it shows **NOT AVAILABLE**. Nothing is ever illustrative, simulated or invented. Orders are never filled on last-known prices and last-known history never yields a BUY/SELL. See `docs/guides/setup-and-configuration.md` for keys and `.env.example` for the variables.
Recommendations are limited to BUY/HOLD/SELL/WATCH/AVOID/REDUCE/DCA or an explicit "insufficient evidence"; no probabilities, confidence scores or expected returns are manufactured. The paper-trading ledger is SQLite (via SLAI's Database tool), is the single source of truth and is never SharedMemory.

Documentation
- docs/REUSE_AUDIT.md — repository audit and what is reused from SLAI
- docs/guides/ — setup and configuration, operation, troubleshooting
- docs/finance/methodology.md — how recommendations, predictions, back-tests, paper trading, goals and the advisor work
- docs/api/finance-api.md — endpoint reference
- docs/VERIFICATION.md — verification results and outstanding issues
- CHANGES.md — change summary

Backend development
Requires Python 3.11+ and the wider SLAI repository when exercising operational logging/agent integration.

python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
ruff check backend tests run_slaifi.py
mypy backend
Frontend development
Requires a current Node.js LTS release.

cd frontend
npm install
npm run typecheck
npm test
npm run build
npm run dev
Set VITE_API_BASE_URL when FastAPI is not available at http://127.0.0.1:8000.

Core design principles
Financial calculations are authoritative in Domain/Engines; SLAI provides contextual reasoning only.
Observations, assumptions, uncertainty, calculations and interpretations remain distinguishable.
No silent annualization, FX conversion, missing-data substitution, or fake provider/SLAI availability.
Goals are targets/constraints, not guarantees.
Market data is real or labelled last-known or NOT AVAILABLE; no sample values exist in the package.
SLAI logging is owned by SLAI/logs/logger.py.
Architecture tests enforce dependency direction and prohibit cwd/sys.path runtime hacks.
