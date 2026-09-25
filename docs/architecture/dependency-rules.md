# Dependency Rules

The dependency rules are executable in `tests/architecture/test_dependency_rules.py`.

## Allowed package dependencies

| Package | May depend on SLAIFI packages |
| --- | --- |
| `core` | none |
| `domain` | `core` |
| `engines` | `core`, `domain` |
| `application` | `core`, `domain`, `engines` |
| `infrastructure` | `core`, `domain` |
| `integrations` | `core`, `domain` |
| `api` | `core`, `domain`, `application` |
| `main` | all packages required for composition |

`main.py` is deliberately excluded from the layered graph because a composition root must know both abstractions and concrete implementations.

## Explicit prohibitions

- `core` must not import any other SLAIFI package.
- `domain` must not import `application`, `engines`, `api`, `infrastructure`, or `integrations`.
- `engines` must not perform delivery/infrastructure work.
- `application` must not import concrete infrastructure or SLAI adapters.
- `api` must not import provider or database adapters.
- `infrastructure` and `integrations` must not import `application` or `api`.
- No package cycle is permitted.

## Why this shape

The interfaces required by business workflows are owned by the stable side of the dependency. For example, the market domain owns `MarketDataProvider`; a vendor adapter implements it. This follows dependency inversion and prevents vendor payloads from leaking into financial logic.

## Enforcement

The architecture test parses Python AST imports under `backend/slaifi`, converts imports to package-level edges, validates them against the allow-list, and then performs cycle detection. CI runs this test with the rest of the backend suite.

This is intentionally repository-local rather than relying on a linter plugin: the rules are visible, versioned, testable, and can evolve with explicit review.
