# API Layer

The FastAPI layer is a delivery boundary. It validates and serializes HTTP data, invokes Application services, and maps expected SLAIFI exceptions to stable HTTP responses.

## Endpoints

| Method | Path | Responsibility |
|---|---|---|
| GET | `/health` | Process liveness |
| GET | `/api/v1/market/overview` | Existing mock-provider overview slice |
| POST | `/api/v1/analysis/market` | Analyze caller-supplied normalized OHLCV observations |
| POST | `/api/v1/analysis/portfolio` | Analyze a caller-supplied portfolio, prices, optional risk series, and goal |
| POST | `/api/v1/goals/evaluate` | Evaluate target arithmetic without generating a strategy |
| GET | `/api/v1/integrations/slai` | Report SLAI reasoning integration availability |

## Boundary rules

The API may depend on Application, Domain types needed for schema conversion, and Core configuration/errors. It must not import `infrastructure` or `integrations`. Concrete implementations are wired only in `slaifi.main`.

Request schemas use `extra="forbid"` to reject accidental fields. Market-bar and portfolio-trade limits are centrally configurable. Domain invariants remain authoritative after Pydantic validation; API validation does not replace them.

## Error semantics

- malformed Pydantic input: FastAPI 422;
- SLAIFI validation/calculation failure: 422;
- required contextual reasoning unavailable: 503;
- other expected SLAIFI errors: 400.

Undefined financial quantities remain null or explicit errors according to the underlying Engine contract; the API does not replace them with zero.
