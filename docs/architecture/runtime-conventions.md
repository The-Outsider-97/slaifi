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

## Root launcher

The delivered `run_slaifi.py` must end at `SLAI/run_slaifi.py`. It:

1. loads SLAIFI Settings;
2. maps the configured log level to SLAI `LoggingSettings`;
3. configures SLAI logging once;
4. imports the composed FastAPI app after logging is ready;
5. starts Uvicorn using SLAIFI host/port settings and `log_config=None` so Uvicorn does not replace SLAI logging;
6. returns explicit failure exit codes and shuts down launcher-owned logging.

It contains no path discovery or machine-specific paths.
