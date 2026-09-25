# Application Layer

The Application layer orchestrates SLAIFI's financial truth without redefining it.

## Responsibilities

Application services may compose Domain objects and Engines into use cases such as market analysis, portfolio analysis, and goal evaluation. They may call application-owned ports such as `FinancialReasoner`, but they do not import concrete integrations or infrastructure.

```text
API / future launcher
        ↓
Application use case
        ├── Domain
        ├── Engines
        └── Application contract
                 ↑
          Integration adapter
```

The application layer does not fetch market data inside analytical use cases, persist portfolios, or perform SLAI-specific imports. Numerical calculations remain owned by Engines.

## Implemented use cases

- `AnalyzeMarketSeries`: composes normalized OHLCV data into features, technical measurements, drawdown, volatility, and optional contextual reasoning.
- `AnalyzePortfolio`: composes portfolio valuation, risk metrics, goal feasibility, and optional contextual reasoning.
- `EvaluateFinancialGoal`: exposes deterministic goal arithmetic independently of portfolio analysis.
- `GetMarketOverview`: retained from the architecture foundation for the mock-provider vertical slice.

## Evidence and interpretation

Application results keep these categories separate:

1. supplied observations;
2. deterministic/statistical calculations;
3. assumptions;
4. uncertainty metadata;
5. SLAI interpretation.

SLAI output is never written back into an Engine result.
