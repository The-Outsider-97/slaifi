# Repository Structure

This document separates the **current Architecture Foundation** from the **planned production structure**. Directories are created only when they acquire executable responsibility; the planned tree is not a mandate to create empty packages.

Legend:
- `[now]` implemented in the Architecture Foundation.
- `[next]` expected in the next concrete milestone.
- `[later]` deliberately deferred until required.

```text
slaifi/
├── .github/
│   └── workflows/
│       └── ci.yml                         [now]
├── .env.example                           [now]
├── .gitignore                             [now]
├── LICENSE                                [now]
├── README.md                              [now]
├── pyproject.toml                         [now]
│
├── docs/
│   ├── architecture/
│   │   ├── overview.md                    [now]
│   │   ├── dependency-rules.md            [now]
│   │   ├── data-flow.md                   [now]
│   │   ├── repository-structure.md        [now]
│   │   └── slai-integration.md            [now]
│   ├── finance/
│   │   ├── recommendation-model.md        [now]
│   │   ├── risk-model.md                  [now]
│   │   └── goal-model.md                  [now]
│   ├── api/                               [next]
│   ├── models/                            [later]
│   └── decisions/
│       ├── 0001-modular-monolith.md       [now]
│       ├── 0002-fastapi-react-vite.md     [now]
│       └── 0003-provider-contracts.md     [now]
│
├── backend/
│   └── slaifi/
│       ├── __init__.py                    [now]
│       ├── main.py                        [now] composition root
│       ├── core/
│       │   ├── config/                    [now]
│       │   ├── exceptions/                [now]
│       │   ├── logging/                   [now]
│       │   ├── types/                     [next]
│       │   └── protocols/                 [later; only non-domain contracts]
│       ├── domain/
│       │   ├── market/                    [now]
│       │   ├── assets/                    [next]
│       │   ├── portfolio/                 [next]
│       │   ├── goals/                     [next]
│       │   ├── risk/                      [next]
│       │   ├── predictions/               [later]
│       │   ├── recommendations/           [later]
│       │   └── education/                 [later]
│       ├── application/
│       │   ├── market/                    [now]
│       │   ├── portfolio/                 [next]
│       │   ├── goals/                     [next]
│       │   ├── analysis/                  [later]
│       │   └── recommendations/           [later]
│       ├── engines/
│       │   ├── features/                  [next]
│       │   ├── technical/                 [next]
│       │   ├── fundamental/               [later]
│       │   ├── sentiment/                 [later]
│       │   ├── regime/                    [later]
│       │   ├── prediction/                [later]
│       │   ├── risk/                      [next]
│       │   ├── portfolio/                 [next]
│       │   ├── goals/                     [next]
│       │   ├── strategy/                  [later]
│       │   └── recommendation/            [later]
│       ├── models/
│       │   ├── forecasting/               [later]
│       │   ├── classification/            [later]
│       │   ├── ensembles/                 [later]
│       │   └── registry/                  [later]
│       ├── infrastructure/
│       │   ├── market_data/               [now]
│       │   ├── database/                  [next]
│       │   ├── repositories/              [next]
│       │   ├── cache/                     [later]
│       │   └── persistence/               [next]
│       ├── integrations/
│       │   ├── slai/                      [later]
│       │   └── external/                  [later]
│       └── api/
│           ├── routes/                    [now]
│           ├── schemas/                   [now]
│           ├── dependencies.py            [now]
│           └── middleware/                [next]
│
├── frontend/
│   ├── index.html                         [now]
│   ├── package.json                       [now]
│   ├── tsconfig.json                      [now]
│   ├── tsconfig.app.json                  [now]
│   ├── vite.config.ts                     [now]
│   └── src/
│       ├── App.tsx                        [now]
│       ├── main.tsx                       [now]
│       ├── pages/                         [now: Home only]
│       ├── components/                    [now]
│       ├── hooks/                         [now]
│       ├── services/                      [now]
│       ├── styles/                        [now]
│       ├── types/                         [now]
│       ├── layouts/                       [next]
│       ├── features/                      [next]
│       ├── state/                         [later]
│       ├── charts/                        [next]
│       └── utils/                         [only when a concrete shared utility exists]
│
├── tests/
│   ├── unit/                              [now]
│   ├── integration/                       [now]
│   ├── financial/                         [now]
│   ├── architecture/                      [now]
│   ├── api/                               [now]
│   ├── models/                            [later]
│   ├── regression/                        [later]
│   └── frontend/                          [next]
│
├── scripts/
│   ├── data/                              [next]
│   ├── models/                            [later]
│   └── maintenance/                       [later]
│
├── config/                                [later]
│   ├── market/                            [when declarative universes/provider rules appear]
│   ├── models/                            [when model configuration exists]
│   ├── risk/                              [when reviewed policy parameters exist]
│   └── strategies/                        [when strategy policies exist]
│
├── data/                                  [local/deployment storage; not a source-of-truth code package]
│   ├── raw/                               [later]
│   ├── normalized/                        [later]
│   ├── processed/                         [later]
│   ├── features/                          [later]
│   └── cache/                             [later]
│
├── migrations/                            [next, with relational persistence]
├── docker-compose.yml                     [next, when PostgreSQL is introduced]
└── tools/                                 [later; only project-specific developer tools]
```

## Why several baseline directories are deferred

Creating empty `engines`, `models`, `integrations`, `config`, `scripts`, and `data` hierarchies would create implied ownership without executable contracts. SLAIFI instead documents their intended placement now and creates each package with its first reviewed use case.

## Database boundary

The initial relational design will begin with the smallest set needed for portfolio and auditability: users (or an external-user reference if authentication remains out of process), portfolios, accounts, transactions, goals, holdings/materialized positions where justified, and snapshots. Prediction, recommendation, model-run, alert, watchlist, and Academy-progress tables are introduced with the features that own them rather than pre-created speculatively.
