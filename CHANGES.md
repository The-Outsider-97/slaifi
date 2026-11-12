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
* **Starts like the other SLAI apps**: `npm.cmd run build` in `applications\slaifi`, then
  `python -m applications.slaifi` from the SLAI root (shared `applications/tools` launcher and banner, port 8777,
  token link, data in `%LOCALAPPDATA%\SLAI\SLAIFI`, `configs/config.yaml`, keys in `applications\slaifi\.env` (copy of `.env.example`) or `<SLAI root>\.env`). The API serves the built UI
  from `dist/` and applies the same local-access rules as the shared server (token cookie, Host/Origin checks, CSP and
  security headers). `run_slaifi.py` is removed. `frontend/src/lib/` (formatting helpers) had been excluded by a Python
  `.gitignore` rule and is now tracked.

## Clearer errors, more strategies and goals, learning and SLAI review (this revision)

* **Errors**: the API's 422 now names the field and says what to type ("Starting capital must be a plain number such as 5000 — you entered “USD”") with a `fields` list; the forms validate before sending, accept `$5,000`, `5000 USD`, `6%`, and show the problem under the box. A non-numeric value in a strategy edit is now a 422, not a server error.
* **Strategies**: six new presets (short-term balanced, long-term growth, balanced core, dividend income, capital preservation, steady accumulation) with descriptions; the editor exposes trading frequency, income focus, preferred asset classes and dividend reinvestment.
* **Goals**: *reach a balance* and *fund withdrawals* goals with plan arithmetic, *protect my capital*, and per-goal monthly saving, largest-drop and risk options; goals behind pace are re-planned from today.
* **Learning**: recommendation log + track record (honest sample sizes), rule-based tightening suggestions from paper-portfolio behaviour (never more risk, never automatic), see `docs/finance/learning-and-adaptation.md`. New migration 2 (`recommendation_log`).
* **SLAI**: goal-plan review, adaptation review, and the track record passed as context to recommendation explanations, all through the existing guard and safety review.
* **Launcher**: binds with `SO_REUSEADDR` on POSIX so a quick restart is not refused while old connections wind down.
