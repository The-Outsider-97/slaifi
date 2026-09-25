# Domain Layer

Domain represents provider-neutral financial concepts and invariants. It may import Core only.

Implemented foundations:

- `AssetId`: symbol plus optional exchange, asset class, currency, and provider-independent instrument identifier;
- normalized `PriceQuote`, `OHLCVBar`, and `MarketSnapshot`;
- portfolio ledger concepts (`Trade`, `CashFlow`, `Portfolio`) distinct from calculated `Position` and `PortfolioSnapshot`;
- return/income targets, hard risk constraints, and soft goal preferences;
- risk result contracts;
- prediction and recommendation records without model/recommendation logic.

`AssetRef` remains an alias of `AssetId` solely to preserve the architecture-foundation vertical slice while callers migrate.

Money and executable trade values use `Decimal`. Statistical outputs and return/risk rates use `float` under the documented numerical conventions.
