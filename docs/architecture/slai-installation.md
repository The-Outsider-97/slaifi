# Installation inside SLAI

SLAIFI's canonical filesystem location is:

```text
SLAI/
├── logs/
├── src/
└── applications/
    └── slaifi/
```

Clone SLAIFI into the singular `application` directory:

```powershell
cd <SLAI_ROOT>\applications
git clone https://github.com/The-Outsider-97/slaifi.git
cd slaifi
python -m pip install -e ".[dev]"
```

The Python package remains `slaifi` and is defined under `applications/slaifi/backend/slaifi`. Standard installation makes it importable regardless of the current working directory; SLAIFI does not use `sys.path` mutation or `os.getcwd()` assumptions.

SLAIFI starts with `python -m applications.slaifi` from the SLAI root, like the other SLAI applications. It reads its settings from `configs/config.yaml`, `<SLAI root>\.env` and the environment, and configures logging through `SLAI/logs/logger.py`.

Core, Domain, and Engines remain independent of SLAI runtime modules. Operational upper layers use the shared SLAI logger, and the concrete SLAI reasoning adapter remains isolated under `integrations/slai`.
