# Learning, adaptation and SLAI review

SLAIFI does not train a model and does not claim to "learn" in the machine-learning sense. What it
does is **measure itself, suggest cautious changes from measured results, and give SLAI the context
to explain them**. Everything below is deterministic, advisory and checked by tests.

## 1. Track record (`domain/learning`, `engines/learning/track_record.py`, `application/learning`)

* Every real, current recommendation that makes a price call (BUY, STRONG_BUY, DCA, SELL, PARTIAL_SELL,
  REDUCE, SHORT, AVOID) is written to `recommendation_log` with the symbol, action, strategy and the last
  real close. HOLD/WATCH make no price call and are never scored. Recommendations built on last-known data,
  and "insufficient evidence" reports, are **never logged**.
* One row per symbol, strategy and day, so refreshing a page cannot inflate the sample. (Daily rows for the
  same symbol are still correlated; the sample is smaller in effect than its count.)
* **Check results** (`POST learning/track-record/refresh`, or the button on *Strategies & goals*) judges each
  recommendation older than 28 calendar days (20 trading days) by the real price change to the first close on
  or after that date. It makes one real data request per symbol, at most 8 symbols per press (free-tier limits);
  last-known prices never settle a recommendation. Moves under 0.5 % count as flat, not as a hit or a miss.
* The summary reports counts, hit rate and a 95 % Wilson interval. **Below 20 decisive results there is no
  verdict** ("too early to say"). Above that the verdict is "better than a coin flip" only if the whole
  interval is above 50 %, "worse" only if the whole interval is below, otherwise "no clear edge".
  A past hit rate is not a forecast.

## 2. Strategy suggestions (`engines/learning/adaptation.py`)

`GET strategies/{id}/adaptations?portfolio_id=&explain=` applies simple rules to measured evidence:

| Rule | Evidence | Suggestion |
|---|---|---|
| worst fall ≥ 80 % of the drawdown limit | paper-portfolio valuation history (≥ 10 points) | smaller position cap (×0.75) and +5 % cash reserve |
| largest holding above its cap | current weights | observation only (trim the holding) |
| cash below the reserve | current weights | observation only |
| track record "worse than chance" (≥ 20 results) | track record | trade one step less often |
| income goal but low income weight | goals | set income focus to 50 % |
| goal needs ≥ 15 %/yr but strategy is conservative | goal arithmetic | **observation only**: lower the target, save more or allow more time |
| goal behind its straight-line pace | goal progress | observation: re-analyse with a portfolio attached |

**The rules never suggest taking more risk or loosening a limit.** Nothing is applied automatically: each
suggestion with a change has an *Apply* button that uses the normal strategy-update path (hard-limit
loosening would still demand acknowledgement).

## 3. Re-planning goals

A *Reach a balance* goal analysed with a portfolio attached is **re-planned from today**: it uses the
portfolio's current value and the time left (`horizon − elapsed`), and the report says so. Measured progress
compares the portfolio value to a straight line from the starting value to the target. The straight line is
a comparison, not a prediction.

## 4. SLAI integration

All SLAI calls go through the same guarded runner (`RecommendationService.run_reasoner`): interpretation
guard (no guarantees/probabilities), the SLAI safety review, and a labelled, optional result. The
deterministic figures are authoritative and never replaced.

| Operation | Where | Evidence sent |
|---|---|---|
| `recommendation_explanation` (existing) | recommendations | report evidence **plus the track-record context** (verdict, decisive results, hit rate) as uncertainty |
| `goal_plan_review` (new) | `POST goal-tracker/{id}/review` | goal figures, findings, plan, progress |
| `strategy_adaptation_review` (new) | `GET strategies/{id}/adaptations?explain=true` | strategy limits, suggestions with evidence, track record; constraint `never_suggest_more_risk` |

If SLAI is disabled or unavailable the endpoints still return every figure; only the interpretation is absent.
