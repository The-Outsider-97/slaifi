# Finance API (`/api/v1`)

Mutating routes require `X-SLAIFI-Client`. Money is serialised as strings. Every market response
carries `provenance` (provider, mode: live/delayed/mock, illustrative flag, observed_at, delay).

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

**System** — `GET system/status` · `GET system/audit` · `GET|POST system/reconcile|backup` ·
`GET integrations/slai` · `GET /health`

Pre-existing stateless endpoints (`analysis/market`, `analysis/portfolio`, `goals/evaluate`,
`portfolio/current`) are unchanged; see `financial-analysis.md`. Interactive docs: `/docs`.
Errors: `{ "error": code, "detail": message }` with 400/403/404/409/422/429/502/503 as appropriate.
