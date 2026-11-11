# Verification report

Results below are from commands actually executed in the development sandbox (no network, so
`pip`/`npm` installs were unavailable). Items that could **not** be run are listed explicitly.

## Executed and passing

| Check | Result |
| --- | --- |
| `pytest` (backend: unit, financial, API, architecture, 12-step integration workflow, degraded operation) | **163 passed** |
| `ruff check backend tests run_slaifi.py` (E501 ignored; `ruff format` owns line length) | all checks passed |
| `ruff format --check` | 167 files formatted |
| `mypy --strict` on `slaifi.api/application/domain/engines/infrastructure/integrations` and `slaifi.main` | no issues |
| TypeScript `tsc --noEmit` (app source) | clean, except `import.meta.env` types that need `vite/client` (absent in the sandbox) |
| esbuild bundle of the UI | builds |
| Browser end-to-end (Playwright/Chromium vs. live uvicorn + built UI, mock provider): analysis, watchlist, comparison, paper order preview/execute/persist-after-reload/reconcile/reset guard, advisor confirm flow, strategy hard-limit acknowledgement, goals, settings, backup, mobile overflow, console errors, 5xx | **41 / 41** |
| Frontend unit tests (21) | 21 passed — on a minimal stand-in for vitest (see below) |
| Standalone API smoke from CI (`/health`, `system/status`, overview, SLAI status) | passed |

The integration workflow covers: select a strategy → search → quote/series → recommendation →
preview → place paper order → persistence across a restart → goal evaluation → advisor change
with confirmation → rejected order → reconcile → reset with confirmation.

## NOT executed / limitations (please read)

1. **Real vitest and the pre-existing frontend tests (`MarketOverviewPage.test.tsx`,
   `MyPortfolioPage.test.tsx`) were not run**: vitest cannot be installed offline. The 21 new
   frontend unit tests were run on a tiny stand-in runner that implements only the matchers they use.
   Run `npm install && npm test` to execute them with the real runner.
2. **`mypy` on `slaifi.core`** reports one error caused by a sandbox-only `pydantic_settings` shim
   (`BaseSettings` typed as `Any`). It was not a defect in the repository; the real package was not available.
   Settings behaviour was exercised through that shim, so run the suite once with the real package installed.
3. **SLAI's agent runtime was not available** in the sandbox. The SLAI host used for testing had
   SLAI's `applications.tools.*` and `logs.*` modules but not `src.agents.*`.
   `AgentFactory`, `SharedMemory`, the reasoning agent and the SafetyAgent were therefore exercised
   only through test doubles and the "unavailable/disabled" paths. The SLAI-backed explanation and
   safety review have **not** been run against the real agents.
4. **Live market data** (Twelve Data) was not exercised: there is no API key or network. Provider
   error mapping (rate limit, timeout, unusable response) is unit-tested with fakes; live behaviour is unverified.
5. The first full run in your environment should be `python run_slaifi.py` followed by the UI;
   no such run was possible here.
6. The CI workflow changes (SLAI host checkout, new smoke) have not been executed on GitHub.

## Known behaviour worth knowing

* Mock/illustrative data always yields "insufficient evidence" — by design, so no BUY/SELL is derived from synthetic prices.
* Advisor parsing is rule-based and covers a limited set of phrasings; unrecognised text is shown as not understood.
* Prediction intervals appear only when walk-forward validation passes; with short histories none will.
