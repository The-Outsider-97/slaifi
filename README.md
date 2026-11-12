SLAIFI — SLAI Financial Intelligence
SLAIFI combines normalized financial data, deterministic quantitative analysis, explicit risk/goal evaluation, and bounded SLAI reasoning into explainable decision support.

SLAIFI is decision-support software. Scenarios, forecasts, targets, confidence values and interpretations are uncertain and are not guarantees of financial outcomes. SLAIFI offers **paper trading only**: simulated orders against virtual cash. Real-money trading does not exist in the code and cannot be enabled.

Quick start (same as SPlanner, Reader and SPADRA; from the SLAI root, e.g. `G:\GAIA\AI\SLAI`)
```powershell
python -m pip install "fastapi>=0.115,<1.0" "httpx>=0.27,<1.0" "pydantic>=2.9,<3.0" "pydantic-settings>=2.5,<3.0" "uvicorn[standard]>=0.30,<1.0"

cd applications\slaifi
npm.cmd run build            # installs the UI's packages and builds dist/

cd G:\GAIA\AI\SLAI
python -m applications.slaifi
```
It prints a banner and a link such as `http://127.0.0.1:8777/?token=...` (port 8777; the link carries a one-time access token and opens in your browser). Free market-data keys go in `G:\GAIA\AI\SLAI\.env` (or the environment) as `SLAIFI_TWELVEDATA_API_KEY=...`, `SLAIFI_TIINGO_API_KEY=...`, `SLAIFI_FMP_API_KEY=...` (and optionally `SLAIFI_FINNHUB_API_KEY`, `SLAIFI_ALPHAVANTAGE_API_KEY`). Data lives in `%LOCALAPPDATA%\SLAI\SLAIFI`; settings in `applications\slaifi\configs\config.yaml`. Then open Settings → Market data sources → **Check providers**.

Runtime location
SLAIFI is designed to live at:

SLAI/
├── logs/
├── src/
└── applications/
    └── slaifi/

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
ruff check backend tests
mypy backend
Frontend development
Requires a current Node.js LTS release.

cd frontend
npm install
npm run typecheck
npm test
npm run build
npm run dev
For `npm run dev` the UI talks to an API on http://127.0.0.1:8000 (start it with `python -m uvicorn slaifi.main:app`); set VITE_API_BASE_URL to change that. The built UI served by `python -m applications.slaifi` uses its own address.

Core design principles
Financial calculations are authoritative in Domain/Engines; SLAI provides contextual reasoning only.
Observations, assumptions, uncertainty, calculations and interpretations remain distinguishable.
No silent annualization, FX conversion, missing-data substitution, or fake provider/SLAI availability.
Goals are targets/constraints, not guarantees.
Market data is real or labelled last-known or NOT AVAILABLE; no sample values exist in the package.
SLAI logging is owned by SLAI/logs/logger.py.
Architecture tests enforce dependency direction and prohibit cwd/sys.path runtime hacks.
