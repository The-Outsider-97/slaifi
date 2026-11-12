# Runtime, Errors, Logging, and Utility Conventions

## Canonical logging

`SLAI/logs/logger.py` is the only logging implementation used by SLAIFI. SLAIFI does not define formatters, handlers, `basicConfig`, or root-logger configuration. The wider SLAI host configures logging; `SLAI/run_slaifi.py` performs that configuration only when it is the process launcher.

Operational boundaries may use:

```python
from logs.logger import get_logger

logger = get_logger("SLAIFI Component")
```

Domain and Engines should normally remain logging-free. Lower layers raise typed errors; operational boundaries log only when a failure requires operational visibility, avoiding repeated log-and-rethrow chains.

## Error ownership

```text
SlaifiError
├── ConfigurationError
├── ValidationError
├── CalculationError
├── IntegrationError
└── InfrastructureError

DomainError
└── DomainValidationError

EngineError
├── EngineValidationError
└── FinancialCalculationError
    └── InsufficientDataError
```

Domain and Engine errors inherit Core categories where API-level translation needs a stable lower-level category. Error instances can carry `component`, `operation`, `cause`, structured `context`, and optional `retryable` metadata. API remains the only layer that maps these failures to HTTP responses.

`core/exceptions/__init__.py` is retained only as a compatibility re-export for Core-owned error names. It contains no definitions and does not import Domain or Engines. New code must use the owning `utils.errors` module.

## Utility ownership

### `core/utils`
Only finance-independent helpers and base error categories belong here. Current cross-cutting helpers cover timezone-awareness detection and JSON-safe immutable conversion.

### `domain/utils`
Financial-domain invariant helpers belong here: timezone-aware domain timestamps, non-blank domain text, and domain identifier normalization. Domain helpers raise Domain-owned errors.

### `engines/utils`
Reusable numerical input helpers belong here: finite/positive series validation, chronological OHLCV sequence validation and positive integer parameter validation. Algorithms such as RSI, ATR, Sharpe ratio, drawdown, portfolio valuation and goal feasibility remain in their engine modules.

A helper used by only one algorithm should stay local to that algorithm rather than being moved into a generic utility file.

## Launcher

SLAIFI starts like every other SLAI application: `python -m applications.slaifi` from the SLAI root
(`applications/slaifi/__main__.py` → `backend/slaifi/launcher.py`). It:

1. parses the shared options (`add_server_arguments`: `--port`, `--data-dir`, `--config`, `--client-dir`, `--token`, `--no-browser`, `--slai-root`) and refuses non-loopback hosts;
2. loads `configs/config.yaml` through the shared `load_section`, then `<SLAI root>/.env` and the environment (they win), then the command line;
3. configures SLAI logging once (`logs/logger.py`) and shuts it down on exit;
4. binds the listening socket itself (a taken port is an error, never shared) and builds the FastAPI app with the shared Content-Security-Policy and security headers;
5. serves it with uvicorn (`log_config=None`, `access_log=False` so the token in the start-up link is never logged) through the shared `serve()` banner, browser opening and clean shutdown;
6. prints a link carrying a one-time access token; `api/local_access.py` trades it for an HttpOnly, SameSite=Strict cookie and enforces Host/Origin checks (the same rules as `applications/tools/server`).

The launcher imports the SLAI kit (`applications.tools`) and therefore only runs inside SLAI. It contains no path discovery or machine-specific paths.
