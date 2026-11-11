# Setup and configuration

## Requirements
* Python 3.11+ (3.12 recommended); Node.js LTS for the UI.
* The SLAI host (provides `applications.tools.*`, `logs.logger`, and optionally `src.agents.*`).
  SLAIFI imports these and does not copy them.

## Install inside SLAI
```
<SLAI_ROOT>\applications\slaifi        # this repository
<SLAI_ROOT>\run_slaifi.py              # launcher (copy of ./run_slaifi.py)
```
```
cd <SLAI_ROOT>
python -m pip install -e applications/slaifi[dev]
python run_slaifi.py
```
The launcher starts the API on `127.0.0.1:8000`. For the UI: `cd applications/slaifi/frontend && npm install && npm run build`
(or `npm run dev` for development at http://localhost:5173).

## Configuration (environment variables, prefix `SLAIFI_`)
See `.env.example` for a complete annotated file.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SLAIFI_ENVIRONMENT` | `development` | `production` refuses the mock provider |
| `SLAIFI_DATA_DIR` | SLAI per-app folder | ledger database, backups |
| `SLAIFI_MARKET_PROVIDER` | `mock` | `mock` or `twelvedata` |
| `SLAIFI_MARKET_API_KEY` | – | Twelve Data key; stored as a secret, never logged or returned |
| `SLAIFI_MARKET_DATA_DELAY_MINUTES` | unset | known feed delay; unset ⇒ reported as unknown, never "real time" |
| `SLAIFI_MOCK_ILLUSTRATIVE_HISTORY` | `true` | mock mode serves labelled synthetic history |
| `SLAIFI_PAPER_ALLOW_ILLUSTRATIVE_EXECUTION` | `true` | allow simulated fills on illustrative prices (still labelled) |
| `SLAIFI_PAPER_ALLOW_CLOSED_MARKET_EXECUTION` | `false` | allow fills while the market is closed |
| `SLAIFI_PAPER_MAX_QUOTE_AGE_SECONDS` | `900` | older quotes are not executable |
| `SLAIFI_API_REQUIRE_CLIENT_HEADER` | `true` | mutating requests need `X-SLAIFI-Client` |
| `SLAIFI_SLAI_ENABLED` / `SLAIFI_SLAI_REQUIRED` | `true` / `false` | SLAI is optional; deterministic features work without it |

Real-money trading has no setting because it does not exist in the code.
