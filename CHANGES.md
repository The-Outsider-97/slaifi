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

## Interactive market chart, your own assets, short selling and speed (this revision)

* **Market performance is interactive**: pick any asset by name or ticker (up to three, compared as % change on shared days), ranges 1W · 1M · 3M · 6M · YTD · 1Y · 2Y · **5Y** (up to 1,830 days), SMA 20/50 overlays, hover and keyboard readout (←/→/Home/End), drag-to-zoom, and a table-equivalent live-region summary. Missing data is never drawn: a symbol with no history says NOT AVAILABLE. Your last choice is remembered in this browser.
* **On your data shows your assets**: Market watch is your own watchlist (add by name or ticker, remove, chart or analyse from a row) with a filter by asset class and by the active strategy's preferred classes. Until you add assets it shows the default market indicators and says so. VIX stays NOT AVAILABLE unless a configured provider supplies it.
* **Short selling** (paper trading only): `short` and `cover` orders, signed positions, collateral/free cash, margin-shortfall warning, a Short/Cover button and SHORT badge in the UI, recommendation and advisor support, and a *Tactical long/short* preset. Off unless a strategy's *Largest short exposure* is above 0. Simulation limits (no borrow fees, dividends owed, recalls or forced liquidation) are stated in the order warning and in `docs/finance/methodology.md`.
* **Speed**: UI bundle for the first page about 400 KB → about 87 KB transferred (gzip + route-level code splitting); hashed UI files are cached for a year so a reload downloads nothing; the Market overview no longer re-runs instrument search every load for symbols no provider can classify (retried every 5 minutes); the chart's series requests are de-duplicated and cached for the session and drawn from at most about 700 points.
* **Fixed**: the order ticket kept the previous portfolio's preview/result after switching portfolio (and a pending preview could be confirmed against the other portfolio); a bar without a close was drawn as a price of 0.

## Financial agent, keys in Settings, Apply, platform costs (this revision)

* **SLAI's Financial agent replaces the Optimization adapter.** "Suggested allocation" now sends the real daily closes to the Financial agent, which estimates the historical moments and optimises; SLAIFI re-checks the answer. The Settings switch is *Financial* (an earlier Optimization choice carries over; `SLAIFI_SLAI_OPTIMIZATION_*` are no longer read, use `SLAIFI_SLAI_FINANCIAL_*`). Other Financial-agent operations (VaR/ES, beta/alpha, rebalance costs) are not used because SLAIFI has its own tested engines for those; this is stated rather than hidden.
* **Apply / Apply all.** Each suggested line has **Apply**, and **Apply all (n)** asks for confirmation (order count and fees) before placing simulated orders, sells first, safe to press twice, refused if the portfolio changed since the suggestion.
* **API keys in Settings.** Type, replace or remove a key per market-data source; it is stored owner-only in the data folder, overrides `.env`, and is never displayed, returned, logged or audited. Removing it falls back to `.env`. Each source can be checked on its own.
* **Platform costs.** Flat fee per trade and per withdrawal (default 1.00 each, in the portfolio's currency), editable in Settings, applied to fills and withdrawals, shown in the order ticket, withdrawal form and Apply confirmation. The default proportional commission is now 0 so a trade costs exactly the platform fee; saved strategies keep their values. Back-tests do not include the flat fee.
* New API: `POST paper/portfolios/{id}/allocation/apply`, `GET/PUT paper/fees`, `GET/PUT/DELETE system/provider-keys[/{name}]`, `POST system/providers/check?provider=`.
* Fixed: tables on Settings and in the allocation panel no longer push the page wider than a phone screen.

## Optional SLAI agents: Knowledge, Optimization (now Financial), Learning (earlier revision)

* **Opt-in, off by default, never forced.** Settings → *Extra help from SLAI* has a switch and a Check button per agent. The choice is remembered, every change is audited, and a missing or failing agent shows NOT AVAILABLE with the reason while everything else works as before. Agents only advise or keep records: nothing is ordered and no SLAIFI number changes.
* **Knowledge** (Advisor page, "Look something up"): passages from SLAIFI's own guides, with their source. Never reads your data or the web.
* **Optimization** (Paper trading, "Suggested allocation"): a steadier mix of the portfolio's holdings within your strategy's limits, from real price history, with current-vs-suggested weights, the money to move, what was left out and why, and the checks SLAIFI ran on the answer. A proposal that breaks a limit is refused, not shown. The statistics are historical, not a forecast.
* **Learning** (Strategies & goals, "Share results with SLAI"): copies recommendations that have been checked against real prices into SLAI's learning memory, safe to repeat, and shows what SLAI recorded. It cannot train SLAI's selector (signals are unvalidated evidence) and SLAIFI's own rule-based learning is unchanged.
* New API: `system/agents`, `knowledge/search`, `paper/portfolios/{id}/allocation`, `learning/slai-memory[/share]`. New settings: `SLAIFI_SLAI_{KNOWLEDGE,OPTIMIZATION,LEARNING}_ENABLED` (first-start default, all `false`) and `…_AGENT` names.
* Needs on your machine: SciPy for Optimization, PyTorch for Learning. See `docs/VERIFICATION.md` for what was and was not run against SLAI's real agents.
