# Recommendation Model — Design Contract

This document defines the boundary before recommendation logic is implemented.

A recommendation is a reproducible decision-support record, not a free-form label. Candidate actions may include `BUY`, `STRONG_BUY`, `HOLD`, `DCA`, `REDUCE`, `PARTIAL_SELL`, `SELL`, `SHORT`, `COVER`, `AVOID`, and `WATCH`.

The engine must eventually consume approved, separately identifiable evidence from prediction, technical/fundamental analysis, risk, portfolio exposure, strategy compatibility, user goals, market regime, uncertainty, and SLAI reasoning.

At minimum a recommendation record will carry action, asset, timestamp, horizon, goal context, confidence, uncertainty, expected return, expected downside, risk level, supporting signals, conflicting signals, invalidation conditions, reasoning provenance, and model versions.

No action label will be implemented until its scoring/decision policy and tests are mathematically specified.
