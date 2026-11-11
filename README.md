SLAIFI — SLAI Financial Intelligence
SLAIFI combines normalized financial data, deterministic quantitative analysis, explicit risk/goal evaluation, and bounded SLAI reasoning into explainable decision support.

SLAIFI is decision-support software. Illustrative scenarios, forecasts, targets, confidence values and interpretations are uncertain and are not guarantees of financial outcomes. SLAIFI offers **paper trading only**: simulated orders against virtual cash. Real-money trading does not exist in the code and cannot be enabled.

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
All market figures carry provider, observation time, delay and a mode badge. The default provider is a mock whose data is labelled illustrative everywhere and never yields a BUY/SELL; configure Twelve Data for real quotes.
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
Market-watch demo statuses are not production recommendations.
SLAI logging is owned by SLAI/logs/logger.py.
Architecture tests enforce dependency direction and prohibit cwd/sys.path runtime hacks.
