# Financial Analysis API Contracts

All rates are fractional internally: `0.10` means 10%. Monetary values are serialized from `Decimal` values. Timestamps must be timezone-aware.

## Market analysis

`POST /api/v1/analysis/market` accepts one asset identity plus chronological OHLCV bars. The caller supplies `periods_per_year`; SLAIFI does not silently assume 252.

The response separates:

- latest observation;
- feature series;
- technical measurements;
- volatility/drawdown calculations;
- optional SLAI reasoning.

Insufficient warm-up for an individual indicator is represented as `null`; it does not invalidate other measurable outputs.

## Portfolio analysis

`POST /api/v1/analysis/portfolio` accepts a portfolio ledger, point-in-time asset prices, and optional risk/goal context.

Risk inputs `returns`, `equity_values`, and `periods_per_year` must be supplied together. Cross-currency conversion remains unsupported at this stage and is rejected by the Portfolio Engine rather than inferred by the API.

## Goal evaluation

`POST /api/v1/goals/evaluate` performs target arithmetic only. Status values such as `feasible_under_assumptions` mean exactly that: feasibility under supplied assumptions, not a forecast or guarantee.

## Contextual reasoning

Providing `reasoning_objective` asks the configured `FinancialReasoner` to interpret the already-calculated result. The API returns this under a distinct `reasoning` field containing runtime status, interpretation, raw structured output, agent metadata, SharedMemory trace key, and warnings.
