# Installation inside SLAI

SLAIFI's canonical filesystem location is:

```text
SLAI/
├── run_slaifi.py
├── logs/
├── src/
└── applications/
    └── slaifi/
```

Clone SLAIFI into `applications`:

```powershell
cd <SLAI_ROOT>\applications
git clone https://github.com/The-Outsider-97/slaifi.git
cd slaifi
python -m pip install -e ".[dev]"
```

The standalone Python package remains `slaifi` under `applications/slaifi/backend/slaifi`. The repository root is also a valid `applications.slaifi` package and exposes that backend implementation without changing global `sys.path` or depending on the process working directory.

The repository-delivered `run_slaifi.py` is written for its final location at `SLAI/run_slaifi.py`. Place that file at the SLAI root without changing its imports. It imports `applications.slaifi` first, then starts the backend application and configures process logging through `SLAI/logs/logger.py`.

Core, Domain, and Engines remain independent of SLAI runtime modules. Operational upper layers use the shared SLAI logger. Concrete agent integration remains isolated under `integrations/slai`, where AgentFactory/SharedMemory ownership is explicit and deterministic finance remains independently testable.
