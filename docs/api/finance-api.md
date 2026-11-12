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
`market/series/{symbol}?interval=&range=|days=&overlays=` (`days` up to 3650; the UI asks for at most 1830, five years) · `market/stats/{symbol}` ·
`market/compare?symbols=` · `market/history/{symbol}` · `market/overview` ·
`POST market/screen` · `GET|POST market/watchlist` · `DELETE market/watchlist/{symbol}`

**Recommendations** — `GET recommendations/{symbol}?strategy_id=&portfolio_id=&explain=` ·
`GET recommendations/{symbol}/backtest`

**Paper trading** — `GET|POST paper/portfolios` · `GET paper/portfolios/{id}` ·
`POST …/orders/preview` · `POST …/orders` · `POST …/deposit` · `POST …/withdraw` ·
`GET …/history` · `GET …/performance` · `GET …/reconcile` · `GET …/guidance` ·
`PUT …/strategy` · `POST …/reset` (needs `confirm`)

**Orders** — `side` is `buy`, `sell`, `short` or `cover`. A short needs an active strategy with
`max_short_exposure` > 0 (otherwise rejection `SHORT_NOT_ALLOWED`); other rejections added for shorting are
`INSUFFICIENT_MARGIN` and `WRONG_DIRECTION` (selling a short or covering a long). Positions carry
`direction` (`long`/`short`) and a signed `quantity` and `market_value`; the portfolio view adds
`short_value`, `margin_required`, `free_cash` and `short_exposure`. Strategies expose and accept
`max_short_exposure` (a fraction of the portfolio, 0 = shorting off).

**Strategies / goals** — `GET|POST strategies` · `GET|PATCH|DELETE strategies/{id}` ·
`POST strategies/{id}/activate` · `GET|POST goal-tracker` · `DELETE goal-tracker/{id}` ·
`POST goal-tracker/{id}/analyze` · `POST goal-tracker/{id}/review` (analysis + SLAI reading)

**Learning** — `GET learning/track-record` · `POST learning/track-record/refresh` ·
`GET strategies/{id}/adaptations?portfolio_id=&explain=` — see `docs/finance/learning-and-adaptation.md`

**Errors** — a rejected request body returns 422 `{"error":"validation_error","detail":"Starting capital must be a plain number such as 5000 …","fields":[{"field","label","message"}]}`: the field is named and the sentence says what to type.

**Advisor** — `POST advisor/interpret` · `POST advisor/proposals/{id}/confirm|reject`

**System** — `GET system/status` · `GET system/providers` (configured sources, state, calls used, last success/problem — no keys) · `POST system/providers/check` (one real request per configured source) · `GET system/audit` · `GET|POST system/reconcile|backup` ·
`GET integrations/slai` · `GET /health`

Pre-existing stateless endpoints (`analysis/market`, `analysis/portfolio`, `goals/evaluate`,
`portfolio/current`) are unchanged; see `financial-analysis.md`. Interactive docs: `/docs`.
**Transport** — responses over 1 KB are gzip-compressed when the client accepts it; the built UI's hashed files
(`assets/name-<hash>.ext`) are sent with `Cache-Control: private, max-age=31536000, immutable`, everything else `no-store`.
Errors: `{ "error": code, "detail": message }` with 400/403/404/409/422/429/502/503 as appropriate.
