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
several parser phrasings; watchlist removal by symbol.

**Outstanding** — see "NOT executed / limitations" in `docs/VERIFICATION.md`.

## Real market data only (this revision)

* **Removed** the mock provider and every illustrative/placeholder value (backend, UI, settings, docs).
* **Added** a multi-source gateway over five free-tier providers (Twelve Data, Tiingo, FMP, Finnhub,
  Alpha Vantage; keys `SLAIFI_<NAME>_API_KEY`): ordered failover, per-source cooldown and free-tier
  request budgets (`SLAIFI_MARKET_LIMITS`), wide-window history caching, and a durable SQLite cache of
  the last real observations (`market_cache.db`).
* **Behaviour**: real data → else **LAST KNOWN DATA** (with its observation time) → else **NOT AVAILABLE**.
  Paper orders are refused on last-known prices; last-known history gives "insufficient evidence";
  holdings are labelled with their `price_basis`.
* **API/UI**: richer `provenance` (source, attempts, `last_known`, `saved_at`, `available`),
  `GET system/providers`, `POST system/providers/check`, Settings → *Market data sources*.
* **Docs**: setup order (install dependencies first, run `npm` from `frontend`), key sign-up, variables.
* **One command**: `python run_slaifi.py` now builds the web UI when needed and the API serves it at
  http://127.0.0.1:8000 (no separate `npm run dev`). `frontend/src/lib/` (formatting helpers) had been
  excluded by a Python `.gitignore` rule and is now tracked.
