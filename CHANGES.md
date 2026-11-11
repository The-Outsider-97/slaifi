# Change summary

Branch `feature/slaifi-completion-2026-11`.

**Backend** — new domain models (paper ledger, strategies, goals, advisor instructions), engines
(technical/quality, recommendation, validated prediction interval, walk-forward back-test, paper execution,
portfolio performance, strategy constraints, goal planning, instruction parser), application services
(market, paper trading, strategies, goals, recommendations, portfolio guidance, advisor), SQLite
persistence on SLAI's `Database` with a hash-chained audit log, SLAI safety adapter, ~45 new API routes,
write protection (`X-SLAIFI-Client`), and new settings.

**Frontend** — Stock Analysis, Paper Trading, SLAI Advisor, Strategies & Goals and Settings pages; shared
components (freshness badge, price chart, order ticket, notices); new navigation; styles that keep the existing identity.

**Housekeeping** — Python ≥ 3.11, ruff config, CI (SLAI host checkout, extended smoke, path guard),
`.env.example`, docs path correction (`applications/slaifi`), README, new docs (`docs/REUSE_AUDIT.md`,
`docs/guides/*`, `docs/finance/methodology.md`, `docs/api/finance-api.md`, `docs/VERIFICATION.md`).

**Fixed** — strict-mypy error in `api/schemas/goals.py`; Starlette exception-handler resolution for symbol errors;
mock provider interval handling; several parser phrasings; watchlist removal by symbol.

**Outstanding** — see "NOT executed / limitations" in `docs/VERIFICATION.md`.
