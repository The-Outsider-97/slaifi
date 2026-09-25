# Core Layer

`backend/slaifi/core/` contains finance-agnostic foundations only. It may use the Python standard library and carefully selected foundational dependencies, but it must not import Domain, Engines, Application, Infrastructure, API, Integrations, or SLAI internals.

Current responsibilities:

- validated runtime settings;
- structured JSON logging;
- a small exception hierarchy;
- normalized currency/rate primitives.

## Installation-location rule

Core must behave identically whether the process starts from the SLAIFI repository, `SLAI/`, or `SLAI/applications/`. Settings therefore do not auto-load `.env` from the process working directory. Callers may pass an explicit dotenv path or use environment variables.

No lower-layer module may use `os.getcwd()`, `Path.cwd()` for package-resource discovery, or modify `sys.path`.
