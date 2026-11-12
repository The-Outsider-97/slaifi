# Finance API (`/api/v1`)

Mutating routes require `X-SLAIFI-Client`. Money is serialised as strings. Every market response
carries `provenance`:

| Field | Meaning |
| --- | --- |
| `mode` | `live` · `delayed` · `live_delay_unknown` (quotes) · `retrieved` (history, search) · `last_known` · `unavailable` |
| `available` | `false` when there is nothing to show — clients must display **NOT AVAILABLE** |
| `source` | the provider that supplied the data (also for `last_known`) |
| `last_known`, `saved_at` | `true` when no source answered and this is the last real observation SLAIFI saved; `saved_at` is when it was stored |
| `delayed` | `true`/`false` only when the provider documents it, otherwise `null` (never assumed "real time") |
| `observed_at`, `retrieved_at`, `age_seconds` | when the market data was observed, when SLAIFI asked, and the age |
| `attempts` | every source tried and what it answered (`ok`, `empty`, `rate_limited`, `unavailable`, `unauthorized`, `not_found`, `unsupported`, `cooling_down`); never contains a key |

No response ever contains generated, sample or placeholder prices. A quote with no data returns
`available: false` and `price: null`; `market/overview` lists such symbols in `unavailable` and
reports `data_mode` `live`, `delayed`, `live_delay_unknown`, `last_known` or `unavailable`.
Last-known quotes are never executable: paper orders on them are refused (`QUOTE_LAST_KNOWN`),
and last-known history yields "insufficient evidence" instead of a recommendation.
`portfolio/current` adds `price_basis` (`live`, `last_known` or `none`, the sources, the symbols
priced from saved quotes and the oldest observation) and answers 503 `NOT AVAILABLE` when a
holding cannot be priced at all.

**Market** — `GET market/search?q=` · `market/meta` · `market/quote/{symbol}` ·
`market/series/{symbol}?interval=&range=&overlays=` · `market/stats/{symbol}` ·
`market/compare?symbols=` · `market/history/{symbol}` · `market/overview` ·
`POST market/screen` · `GET|POST market/watchlist` · `DELETE market/watchlist/{symbol}`

**Recommendations** — `GET recommendations/{symbol}?strategy_id=&portfolio_id=&explain=` ·
`GET recommendations/{symbol}/backtest`

**Paper trading** — `GET|POST paper/portfolios` · `GET paper/portfolios/{id}` ·
`POST …/orders/preview` · `POST …/orders` · `POST …/deposit` · `POST …/withdraw` ·
`GET …/history` · `GET …/performance` · `GET …/reconcile` · `GET …/guidance` ·
`PUT …/strategy` · `POST …/reset` (needs `confirm`)

**Strategies / goals** — `GET|POST strategies` · `GET|PATCH|DELETE strategies/{id}` ·
`POST strategies/{id}/activate` · `GET|POST goal-tracker` · `DELETE goal-tracker/{id}` ·
`POST goal-tracker/{id}/analyze`

**Advisor** — `POST advisor/interpret` · `POST advisor/proposals/{id}/confirm|reject`

**System** — `GET system/status` · `GET system/providers` (configured sources, state, calls used, last success/problem — no keys) · `POST system/providers/check` (one real request per configured source) · `GET system/audit` · `GET|POST system/reconcile|backup` ·
`GET integrations/slai` · `GET /health`

Pre-existing stateless endpoints (`analysis/market`, `analysis/portfolio`, `goals/evaluate`,
`portfolio/current`) are unchanged; see `financial-analysis.md`. Interactive docs: `/docs`.
Errors: `{ "error": code, "detail": message }` with 400/403/404/409/422/429/502/503 as appropriate.
