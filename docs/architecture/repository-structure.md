# Repository Structure

SLAIFI is an application inside the wider SLAI repository. Only directories with active responsibilities are represented below.

```text
SLAI/
├── run_slaifi.py                     # root process launcher
├── logs/
│   └── logger.py                     # canonical logging implementation
├── src/                              # wider SLAI runtime
└── applications/
    └── slaifi/
        ├── __init__.py               # applications.slaifi package bridge
        ├── run_slaifi.py             # delivery/reference copy; move to SLAI root
        ├── pyproject.toml
        ├── backend/
        │   └── slaifi/
        │       ├── core/
        │       │   ├── config/
        │       │   ├── exceptions/   # Core-only compatibility re-export
        │       │   ├── types/
        │       │   └── utils/
        │       │       ├── errors.py
        │       │       └── helpers.py
        │       ├── domain/
        │       │   ├── assets/
        │       │   ├── goals/
        │       │   ├── market/
        │       │   ├── portfolio/
        │       │   ├── predictions/
        │       │   ├── recommendations/
        │       │   ├── risk/
        │       │   └── utils/
        │       ├── engines/
        │       │   ├── features/
        │       │   ├── goals/
        │       │   ├── portfolio/
        │       │   ├── risk/
        │       │   ├── technical/
        │       │   └── utils/
        │       ├── application/
        │       ├── api/
        │       ├── infrastructure/
        │       ├── integrations/
        │       └── main.py
        ├── frontend/
        ├── tests/
        └── docs/
```

There is intentionally no duplicate `backend/slaifi/core/logging` package and no `engines/_validation.py`. Their responsibilities are owned by the wider SLAI logger and `engines/utils`, respectively.

The application root `__init__.py` extends only the `applications.slaifi` package search path to the backend implementation. It does not modify global `sys.path` or depend on the process working directory.
