# Recommendation Model

> The original design contract for this document listed actions such as STRONG_BUY, SHORT and COVER and
> fields such as confidence and expected return. The implemented model deliberately does **not** produce
> them. See [methodology.md](methodology.md) for the implemented contract.

Implemented actions: `BUY`, `HOLD`, `SELL`, `WATCH`, `AVOID`, `REDUCE`, `DCA`, or an explicit
**insufficient evidence** result. A record carries the rule score (an aggregate in [-1, 1], not a probability),
risk level, horizon, supporting and conflicting signals, constraint findings, invalidation conditions,
model versions and data provenance. A prediction interval is attached only when walk-forward validation
of its coverage passed. Confidence scores, expected returns and accuracy figures are never fabricated.
