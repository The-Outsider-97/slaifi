# API Layer

FastAPI is a delivery boundary. It validates and serializes HTTP data, invokes pre-wired Application services and maps expected SLAIFI errors to stable HTTP responses. It does not perform financial calculations and does not import concrete infrastructure or integration adapters.

## Implemented endpoints

| Method | Path | Responsibility |
|---|---|---|
| GET | `/health` | Process liveness |
| GET | `/api/v1/market/overview` | Existing mock-provider overview slice |
| POST | `/api/v1/analysis/market` | Analyze caller-supplied normalized OHLCV observations |
| POST | `/api/v1/analysis/portfolio` | Analyze a supplied portfolio, prices, optional risk series and goal |
| POST | `/api/v1/goals/evaluate` | Evaluate goal arithmetic and optionally add separate SLAI interpretation |
| GET | `/api/v1/integrations/slai` | Report the public-safe SLAI reasoning availability state |

## Response separation

Analytical responses keep numerical output and contextual interpretation separate. For example, goal analysis returns:

```text
{
  evaluation: <authoritative deterministic goal arithmetic>,
  reasoning: <optional SLAI interpretation/provenance>
}
```

The reasoning response intentionally exposes only public-safe provenance: status, interpretation, agent identity/version, operation correlation ID, caller request ID and warnings. Raw SLAI result payloads and SharedMemory keys remain internal because they can contain implementation detail, diagnostic data or future sensitive context.

## Request IDs

Clients may provide `X-Request-ID`. SLAIFI trims and validates it, rejects blank values and limits it to 128 characters. It is trace metadata only; the SLAI adapter generates a distinct correlation identifier for each reasoning operation.

## Input controls

Pydantic request models use `extra="forbid"`. Market-bar and portfolio-trade limits are centrally configured. Domain invariants remain authoritative after HTTP validation; Pydantic does not replace Domain validation.

The API currently permits `GET` and `POST` through CORS and allows `Content-Type` plus `X-Request-ID` headers. Authentication and user authorization are intentionally deferred and must be added before exposing private persisted portfolio data.

## Error semantics

- malformed Pydantic input: FastAPI `422`;
- SLAIFI validation or financial-calculation failure: `422`;
- required SLAI reasoning unavailable: `503`;
- other expected SLAIFI failures: `400`;
- configured request collection limit exceeded: `413`.

Undefined financial quantities remain null or explicit errors according to the underlying Engine contract; the API never substitutes arbitrary zero values.
