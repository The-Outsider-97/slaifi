# Installation inside SLAI

SLAIFI is intended to live at:

```text
SLAI/
└── applications/
    └── slaifi/
```

Clone from PowerShell:

```powershell
cd <SLAI_ROOT>\applications
git clone https://github.com/The-Outsider-97/slaifi.git
```

The Python package is defined under `backend/slaifi` using standard packaging metadata. Install SLAIFI from its repository directory (for development, `python -m pip install -e .`) or otherwise place the installed distribution on Python's import path. Lower layers do not import `AgentFactory`, shared memory, SLAI agents, or any SLAI application module.

A future SLAI launcher/adapter may depend on SLAIFI contracts. SLAIFI Core, Domain, and Engines must not depend back on SLAI.
