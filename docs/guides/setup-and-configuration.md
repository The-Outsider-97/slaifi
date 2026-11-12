# Setup and configuration

## Requirements
* Python 3.11+ (3.12 recommended); Node.js LTS for the UI.
* The SLAI host (provides `applications.tools.*`, `logs.logger`, and optionally `src.agents.*`).
  SLAIFI imports these and does not copy them.
* At least one free market-data key (three or more recommended) — see below.

## Install inside SLAI
```
<SLAI_ROOT>\applications\slaifi        # this repository
<SLAI_ROOT>\run_slaifi.py              # launcher (copy of ./run_slaifi.py)
```

**1. Install the Python dependencies first** (the launcher fails with `No module named
'pydantic_settings'` otherwise):
```
cd <SLAI_ROOT>
python -m pip install "fastapi>=0.115,<1.0" "httpx>=0.27,<1.0" "pydantic>=2.9,<3.0" "pydantic-settings>=2.5,<3.0" "uvicorn[standard]>=0.30,<1.0"
```
(or `python -m pip install -e applications/slaifi[dev]` to also get the test tools).

**2. Set your market-data keys** in the same terminal:
```
$env:SLAIFI_TWELVEDATA_API_KEY = "..."      # PowerShell; use `export` on Linux/macOS
$env:SLAIFI_TIINGO_API_KEY     = "..."
$env:SLAIFI_FMP_API_KEY        = "..."
```

**3. Start SLAIFI — one command:**
```
python run_slaifi.py
```
Then open **http://127.0.0.1:8000**. The launcher builds the web UI the first time (and again after
the UI sources change) using Node.js LTS, and the API serves it, so there is no second terminal and
no `npm` command to run. If Node.js is missing the API still starts (docs at `/docs`) and the log
says what to install. `SLAIFI_SKIP_UI_BUILD=1` skips the build step.

*Developing the UI instead?* From `applications\slaifi\frontend` (the folder that holds
`package.json`) run `npm.cmd install` then `npm.cmd run dev` (http://localhost:5173, talks to the API
on port 8000).

**4. Check the sources.** Open Settings → *Market data sources* and press **Check providers**. Each
configured source is called once and reports *Working* or the exact problem (key rejected, plan
does not include the data, rate-limited, unreachable). The page never displays a key.

## Market data: free keys and what they provide
SLAIFI shows real data only. A request is answered by the first source in the order that has the
data; if a source is rate-limited, down, unauthorised or lacks the symbol, the next is tried. If
every source fails, the last real observation SLAIFI saved is shown, labelled **LAST KNOWN DATA**
with the time it was observed. If there is none, the UI shows **NOT AVAILABLE**.

| Source | Variable | Sign up | Free limits (enforced by SLAIFI on itself) | Provides |
| --- | --- | --- | --- | --- |
| Twelve Data | `SLAIFI_TWELVEDATA_API_KEY` | twelvedata.com | 8/min, 800/day | quotes, all intervals, search |
| Tiingo | `SLAIFI_TIINGO_API_KEY` | tiingo.com | 50/hour, 1000/day | IEX quotes, daily/weekly/monthly history |
| Financial Modeling Prep | `SLAIFI_FMP_API_KEY` | financialmodelingprep.com | 250/day | quotes, daily history, search (some symbols are premium) |
| Finnhub | `SLAIFI_FINNHUB_API_KEY` | finnhub.io | 55/min (plan: 60) | quotes, search |
| Alpha Vantage | `SLAIFI_ALPHAVANTAGE_API_KEY` | alphavantage.co | 5/min, 25/day | end-of-day quotes, daily/weekly/monthly history |

Free plans change; the limits above are what the adapters assume. Override them for a paid plan
with `SLAIFI_MARKET_LIMITS` (e.g. `{"twelvedata":{"per_minute":55}}`). A free-tier source that
runs out of quota is skipped until its window resets rather than being hammered. The legacy
`SLAIFI_MARKET_API_KEY` is read as the Twelve Data key.

A first load of the overview classifies the four default symbols (about eight calls) and saves
the result; later loads use the cache. With only the 25-call Alpha Vantage key, expect to run out
quickly — that is why three or more sources are recommended.

## Configuration (environment variables, prefix `SLAIFI_`)
See `.env.example` for a complete annotated file.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SLAIFI_ENVIRONMENT` | `development` | `development`, `test` or `production` |
| `SLAIFI_FRONTEND_DIST_DIR` | `<slaifi>/frontend/dist` | where the built UI is served from (rarely needed) |
| `SLAIFI_DATA_DIR` | SLAI per-app folder | ledger database (`slaifi.db`), last-known market cache (`market_cache.db`), backups |
| `SLAIFI_<SOURCE>_API_KEY` | – | one per source above; stored as a secret, never logged or returned |
| `SLAIFI_<SOURCE>_BASE_URL` | provider default | override only for a proxy or a compatible endpoint |
| `SLAIFI_MARKET_PROVIDER_ORDER` | `twelvedata,tiingo,fmp,finnhub,alphavantage` | which source is asked first |
| `SLAIFI_MARKET_LIMITS` | free-tier defaults | JSON per-source `per_minute` / `per_hour` / `per_day` |
| `SLAIFI_MARKET_QUOTE_CACHE_TTL_SECONDS` | `60` | how long a fresh quote is reused (protects the free quotas) |
| `SLAIFI_MARKET_HISTORY_CACHE_TTL_SECONDS` | `300` | same for history |
| `SLAIFI_MARKET_DATA_DELAY_MINUTES` | unset | known feed delay for Twelve Data; unset ⇒ reported as unknown, never "real time" |
| `SLAIFI_PAPER_ALLOW_CLOSED_MARKET_EXECUTION` | `false` | allow fills while the market is closed |
| `SLAIFI_PAPER_MAX_QUOTE_AGE_SECONDS` | `900` | older quotes are not executable |
| `SLAIFI_API_REQUIRE_CLIENT_HEADER` | `true` | mutating requests need `X-SLAIFI-Client` |
| `SLAIFI_SLAI_ENABLED` / `SLAIFI_SLAI_REQUIRED` | `true` / `false` | SLAI is optional; deterministic features work without it |

Real-money trading has no setting because it does not exist in the code.

Restart SLAIFI after changing a key: keys are read once at start-up.
