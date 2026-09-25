# Dependency Rules

The rules are executable in `tests/architecture/`.

| Package | May depend on SLAIFI packages |
| --- | --- |
| `core` | none |
| `domain` | `core` |
| `engines` | `core`, `domain` |
| `application` | `core`, `domain`, `engines` |
| `infrastructure` | `core`, `domain` |
| `integrations` | `core`, `domain`, **Application contracts only** |
| `api` | `core`, `domain`, `application` |
| `main` | composition-root dependencies as required |

Additional rules:

- Core never imports higher SLAIFI layers.
- Domain never imports Engines/Application/API/Infrastructure/Integrations.
- Engines remain deterministic calculation code and do not perform delivery or integration work.
- Application owns integration ports and does not import concrete adapters.
- API does not import Infrastructure or concrete Integrations.
- Integrations may implement Application-owned contracts but may not import Application use cases.
- No package cycle is permitted.
- No backend module may use `os.getcwd()`, `Path.cwd()` or `sys.path` mutation for runtime discovery.

The cleanup utility packages follow the same direction: `core/utils` is lowest-level, `domain/utils` may depend on Core, and `engines/utils` may depend on Core/Domain.
