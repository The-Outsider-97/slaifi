# ADR 0002 — FastAPI Backend and React/Vite Frontend

**Status:** Accepted

## Backend

FastAPI is selected because SLAIFI benefits from typed request/response contracts, asynchronous I/O support for market-provider calls, automatic OpenAPI output, and a small delivery layer around Python-native quantitative code. Pydantic is used for boundary validation and settings.

## Frontend

React with TypeScript and Vite is selected for the application dashboard. SLAIFI currently does not require server-side rendering or a frontend server runtime; using Vite keeps the browser application a clear API client and avoids duplicating backend domain responsibilities.

BIMAP uses React/Next.js and a CSS-variable theme system. SLAIFI retains the React/TypeScript family and the token/theming philosophy while selecting a simpler client build for this product's current requirements.

## Revisit when

Choose a server-rendered framework only if public SEO-heavy content, server components, edge rendering, or frontend-owned server workflows become concrete requirements.
