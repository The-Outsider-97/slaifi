# Repository Structure

SLAIFI is an application inside the wider SLAI repository. Only directories with active responsibilities are represented below.

```text
SLAI/
├── logs/
│   └── logger.py                     # canonical logging implementation
├── src/                              # wider SLAI runtime
└── applications/
    └── slaifi/
        ├── __main__.py               # python -m applications.slaifi
        ├── package.json              # npm run build (builds the web UI into dist/)
        ├── configs/config.yaml       # typed settings, read through SLAI's ConfigRepository
        ├── pyproject.toml
        ├── backend/
        │   └── slaifi/
        │       ├── launcher.py       # start-up on the shared SLAI tools kit
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
        │       │       ├── errors.py
        │       │       └── helpers.py
        │       ├── engines/
        │       │   ├── features/
        │       │   ├── goals/
        │       │   ├── portfolio/
        │       │   ├── risk/
        │       │   ├── technical/
        │       │   └── utils/
        │       │       ├── errors.py
        │       │       └── helpers.py
        │       ├── application/
        │       ├── api/
        │       ├── infrastructure/
        │       ├── integrations/
        │       └── main.py
        ├── tests/
        └── docs/
```

There is intentionally no `backend/slaifi/core/logging` package and no `engines/_validation.py`. Their responsibilities are owned by the wider SLAI logger and `engines/utils`, respectively.
