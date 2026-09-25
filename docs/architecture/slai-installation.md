# Installation inside SLAI

SLAIFI's canonical filesystem location is:

```text
SLAI/
├── run_slaifi.py
├── logs/
├── src/
└── application/
    └── slaifi/
```

Clone SLAIFI into the singular `application` directory:

```powershell
cd <SLAI_ROOT>\application
git clone https://github.com/The-Outsider-97/slaifi.git
cd slaifi
python -m pip install -e ".[dev]"
```

The Python package remains `slaifi` and is defined under `application/slaifi/backend/slaifi`. Standard installation makes it importable regardless of the current working directory; SLAIFI does not use `sys.path` mutation or `os.getcwd()` assumptions.

The repository-delivered `run_slaifi.py` is written for its final location at `SLAI/run_slaifi.py`. Move that file to the SLAI root without changing its imports. It reads host/port and environment from SLAIFI's Settings layer and configures logging through `SLAI/logs/logger.py`.

Core, Domain, and Engines remain independent of SLAI runtime modules. Operational upper layers use the shared SLAI logger, and the concrete SLAI reasoning adapter remains isolated under `integrations/slai`.
