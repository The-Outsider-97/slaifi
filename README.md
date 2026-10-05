# SLAIFI — Production Frontend Data Integration, Market Overview Reconstruction, and “My Portfolio” Implementation Mandate

## Project

**SLAIFI — SLAI Financial Intelligence**

Primary visual reference:

**Use the supplied Market Overview screenshot as the principal design reference for this frontend development phase.**

The objective is not to create a loose interpretation of the screenshot.

The actual running SLAIFI application should reproduce its:

- visual hierarchy;
- layout proportions;
- information density;
- spacing system;
- typography hierarchy;
- navigation structure;
- dashboard composition;
- card system;
- border treatment;
- dark-mode appearance;
- restrained financial-dashboard aesthetic;
- yellow/gold SLAIFI branding;
- chart presentation;
- table styling;
- status treatments;
- contextual SLAI intelligence panels;
- interaction patterns;
- and overall UX language.

However, visual similarity alone is insufficient.

The frontend must become a genuine presentation layer for the existing:

- SLAIFI backend;
- financial domain layer;
- portfolio engine;
- market-data services;
- risk services;
- analytics services;
- application/API layer;
- and SLAI integration.

The production interface must display information obtained from the actual application architecture.

It must **not** merely imitate a financial dashboard with hard-coded values.

---

# 1. ROLE

Act as the principal:

- frontend architect;
- full-stack integration engineer;
- financial-dashboard UX engineer;
- quantitative-finance UI engineer;
- SLAI integration engineer;
- API-contract reviewer;
- state-management architect;
- accessibility engineer;
- testing engineer;
- performance engineer;
- and critical code reviewer

for this SLAIFI development phase.

This is a repository implementation task.

Do not treat it as:

- a Figma exercise;
- a static HTML mockup;
- a screenshot recreation only;
- a disconnected frontend prototype;
- or a demo populated with invented financial information.

Inspect the existing repository before changing the architecture.

Do not assume technologies or data contracts that have not been verified in the repository.

---

# 2. PRIMARY OBJECTIVE

Implement the SLAIFI frontend so that the supplied **Market Overview** design becomes representative of the actual running application.

The completed frontend must:

1. closely reproduce the supplied Market Overview design;
2. obtain financial information through the SLAIFI backend;
3. consume existing SLAI-derived intelligence where available;
4. clearly distinguish unavailable data from available data;
5. eliminate fabricated frontend financial information;
6. provide robust loading, empty, stale, partial, and error states;
7. use reusable components rather than page-specific duplication;
8. preserve existing functioning architecture where justified;
9. remain maintainable as SLAIFI expands;
10. and introduce a fully integrated **My Portfolio** page using the same design system.

The Market Overview and My Portfolio pages must look and behave as parts of the same application.

---

# 3. REPOSITORY-FIRST REQUIREMENT

Before implementing major changes, inspect the current codebase and establish the actual architecture.

Determine at minimum:

## Frontend

- framework;
- framework version;
- routing system;
- page structure;
- component hierarchy;
- styling approach;
- theme implementation;
- typography setup;
- state-management approach;
- query/data-fetching approach;
- existing charting libraries;
- icon system;
- reusable UI components;
- authentication handling;
- workspace handling;
- environment configuration;
- frontend testing infrastructure.

## Backend

Identify:

- application entry points;
- API framework;
- API routers;
- endpoints;
- request models;
- response models;
- serialization strategy;
- financial-domain services;
- market-data providers;
- quote services;
- historical-price services;
- portfolio services;
- holdings models;
- transaction models;
- risk services;
- analytics engines;
- asset metadata services;
- persistence mechanisms;
- caches;
- authentication/workspace boundaries;
- health/status endpoints;
- existing WebSocket/SSE mechanisms if present.

## SLAI Integration

Determine exactly how SLAIFI currently communicates with SLAI.

Inspect:

- SLAI adapters;
- SLAI client interfaces;
- agent orchestration;
- shared-memory integration;
- reasoning services;
- analysis services;
- risk-analysis integration;
- recommendation/signal generation;
- explanation generation;
- confidence data;
- provenance data;
- error propagation;
- timeout behaviour;
- and fallback behaviour.

Do not invent another integration layer if a suitable one already exists.

---

# 4. PRESERVE THE EXISTING ARCHITECTURE

Prefer extension over replacement.

Do not rewrite functioning:

- backend services;
- domain models;
- portfolio engines;
- market-data adapters;
- SLAI adapters;
- API clients;
- configuration systems;
- shared components;
- or state-management infrastructure

merely because a different architecture would be easier to implement.

Refactor only where a concrete architectural problem exists.

For every significant refactor, there should be a technical reason such as:

- duplication;
- broken abstraction boundaries;
- inconsistent API contracts;
- impossible state handling;
- circular dependencies;
- unmaintainable component coupling;
- security problems;
- or measurable performance issues.

---

# 5. NON-NEGOTIABLE — NO FABRICATED FINANCIAL DATA

The frontend must not substitute unavailable backend information with realistic-looking fabricated financial values.

Unacceptable examples include:

```ts
const portfolioValue = 125430.18;
const sp500 = 5782.76;
const dayChange = 0.82;
const vix = 16.52;
