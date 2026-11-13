# Verification report

Results below are from commands actually executed in the development sandbox (no network, so
`pip`/`npm` installs were unavailable). Items that could **not** be run are listed explicitly.

## Executed and passing

| Check | Result |
| --- | --- |
| `pytest` (backend: unit, financial, API, architecture, integration workflow, degraded operation, provider adapters, multi-provider failover, last-known cache) | **358 passed** |
| `ruff check backend tests` (E501 ignored; `ruff format` owns line length) | all checks passed |
| `ruff format --check` | 237 files formatted |
| `mypy --strict` on the whole package | no defects in SLAIFI code; the only reports are sandbox artefacts (SLAI host modules and the `pydantic_settings` shim have no type stubs) |
| TypeScript `tsc --noEmit` (app source) | clean, except `import.meta.env` types that need `vite/client` (absent in the sandbox) |
| esbuild bundle of the UI | builds |
| Browser end-to-end (Playwright/Chromium vs. the real launcher `python -m applications.slaifi` (token link, cookie, shared security headers and Content-Security-Policy) serving the built UI, with the four configured providers answered by a **local stand-in HTTP server** that serves documented response shapes): live → failover (one provider rate-limited, one down) → last known data → NOT AVAILABLE; orders refused on last-known prices; holdings labelled by price basis; Check providers; keys never displayed or logged; last-known data survives a backend restart; plus analysis, watchlist, comparison, paper orders, advisor, strategies, goals, settings, backup, mobile overflow, console errors, 5xx | **54 / 54**, plus a second run for the new work (clear error messages, new goal types, strategy suggestions, track-record panel): **16 / 16**; a third run for the interactive chart, 5-year range, comparison, zoom, watchlist and mobile layout: **28 / 28**; and a fourth for short selling in the UI (refusal while off, Short, SHORT badge, collateral summary, partial cover, Cover, ledger replay): **14 / 14** |
| Frontend unit tests (48: format, number parsing, App, finance components, chart helpers, series cache) | 48 passed — on a minimal stand-in for vitest (see below) |
| Standalone API smoke from CI (`/health`, `system/status`, overview, SLAI status) | passed |

The integration workflow covers: select a strategy → search → quote/series → recommendation →
preview → place paper order → persistence across a restart → goal evaluation → advisor change
with confirmation → rejected order → reconcile → reset with confirmation.

## NOT executed / limitations (please read)

1. **Real vitest and the page tests (`MarketOverviewPage.test.tsx`, `MyPortfolioPage.test.tsx`) were not run**:
   vitest and Testing Library cannot be installed offline. `MarketOverviewPage.test.tsx` was rewritten for the new chart, watchlist and strategies endpoints and has only been type-checked, so expect to fix small selector details on its first real run. The 48 unit tests above ran on a tiny
   stand-in runner that implements only the matchers they use. Run `npm install && npm test`.
2. **`mypy` on `slaifi.core`** reports one error caused by a sandbox-only `pydantic_settings` shim
   (`BaseSettings` typed as `Any`). It was not a defect in the repository; the real package was not available.
   Settings behaviour was exercised through that shim, so run the suite once with the real package installed.
3. **SLAI's agent runtime was not available** in the sandbox. The SLAI host used for testing had
   SLAI's `applications.tools.*` and `logs.*` modules but not `src.agents.*`.
   `AgentFactory`, `SharedMemory`, the reasoning agent and the SafetyAgent were therefore exercised
   only through test doubles and the "unavailable/disabled" paths. The SLAI-backed explanation and
   safety review have **not** been run against the real agents.
4. **The real provider APIs (Twelve Data, Tiingo, FMP, Finnhub, Alpha Vantage) were never reached**:
   the sandbox has no network access to them and no keys. The adapters were written from each
   provider's documented request/response format and tested against fakes and a local stand-in
   server whose **numbers are synthetic test data (never shipped)**. A field that a provider
   renamed, or a plan restriction not yet known, will only show up with real keys. Settings →
   *Market data sources* → **Check providers** makes one real request per key and reports exactly
   what failed. Free-tier limits (e.g. Alpha Vantage 25/day) are assumptions that may have changed.
   When a provider omits a currency, USD is assumed.
5. The first full run in your environment should be `npm.cmd run build` in `applications\slaifi` and then `python -m applications.slaifi` from the SLAI root;
   no such run was possible here.
6. The CI workflow changes (SLAI host checkout, new smoke) have not been executed on GitHub.

7. **SLAI-backed goal review, adaptation review and the track-record context** were exercised with test doubles only (same limitation as item 3). The track record has been verified only against the synthetic feed and the local stand-in server; no real recommendation has yet aged 28 days against live prices, so expect "too early to say" for the first weeks of use.
8. **Learning is rule-based measurement, not a trained model.** Suggestion thresholds (80 % of the drawdown limit, ×0.75 position cap, +5 % reserve, 20-result minimum) are product defaults, not tuned on data.

9. **The optional agents (Knowledge, Financial, Learning) were tested mostly against test doubles on the SLAI side.** The Financial adapter was additionally run against SLAI's real Financial and Optimization agent source (staged in the sandbox, not repo code): the request shapes, the cash-reserve scaling and the resulting weights were compared with independent solvers and agree. The browser E2E used that real agent through a sandbox wrapper, because the sandbox's SLAI runtime cannot start; on your machine the agent comes from SLAI's runtime, which was **not** exercised. The real `KnowledgeAgent` and `LearningAgent` were **not** run (the sandbox host has no `src.agents`), so their call shapes were written from reading the source and are unconfirmed at run time.
10. **Dependencies on your machine are unknown:** the Financial agent needs SciPy (its optimizer); Learning needs PyTorch (the Learning agent imports it at load). Without them Settings shows *On, but SLAI could not run it* and the feature says NOT AVAILABLE. Use Settings → **Check** after switching an agent on.
11. **Allocation inputs are historical**, annualised from real daily returns, and the "steadiest / balance risk and return" preference weights (0, 0.0 / 1.0 / 3.0 by risk tolerance) are product defaults, not tuned.
12. **Platform fees** are a flat amount per trade and per withdrawal in the portfolio's currency (no currency conversion). Back-tests do not include the flat fee, only the strategy's proportional commission and slippage; the default `commission_rate` is now 0 (strategies saved earlier keep their value).
13. **Saved API keys override `.env`.** Removing a saved key falls back to `.env`. Live providers were exercised only through a local stand-in server in the sandbox; the real vendor endpoints were not called, and vitest/vite were replaced by the sandbox's own unit runner and bundler, so run `npm.cmd run build` and your usual test command on your machine.

## Known behaviour worth knowing

* Last-known (saved) history always yields "insufficient evidence", and last-known quotes are never used to fill orders — by design.
* A source that rejects its key stays marked *API key rejected* until SLAIFI is restarted.
* The first overview load costs about eight provider calls (it classifies the four default symbols); the results are saved.
* Advisor parsing is rule-based and covers a limited set of phrasings; unrecognised text is shown as not understood.
* Prediction intervals appear only when walk-forward validation passes; with short histories none will.
* **Short selling is a simulation**: no borrow fees, dividends owed, share recalls or forced liquidation are modelled, so a short's result is better than a real broker's would be. Verified by 21 dedicated tests and the browser run above.
* **Build tool**: the browser runs used an esbuild bundle with the same entry point and code splitting; the production build uses Vite, which was not available here. Vite emits hashed `assets/name-<hash>.ext` files, which is what the long-lived cache rule matches (the test build was named to match).

## Performance (measured here, against a local stand-in for the providers)

| Measure | Before | After |
| --- | --- | --- |
| Bytes transferred for the first page (JS + CSS) | about 399 KB (361,603 + 37,777, uncompressed) | about 87 KB (gzip, first page code only) |
| Bytes re-downloaded on reload | about 400 KB (`no-store`) | none (cached) |
| Main script before compression | 361,603 B | 223,351 B (the other pages load when first opened) |
| Provider calls for one overview load | 4 searches + 4 quotes + 1 series | unchanged on the first load; repeat searches for unclassifiable symbols are limited to one per 5 minutes (unit-tested) |

Timings (about 1.1–1.3 s first load, about 0.3 s reload) were within noise on a local machine and are not claimed as an improvement; real-network gains are expected from the size reduction but were not measured.
