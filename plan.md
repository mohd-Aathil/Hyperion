# Hyperion — Refocused Product Plan

## Product scope

Hyperion is a finance-only chatbot and market information desk. The product has four top-level areas: Finance Chat, Live News, Stocks, and Crypto Market. The chatbot answers only questions about stocks, crypto, markets, macroeconomics, earnings, valuation, portfolio construction, risk, investing concepts, and financial news. The frontend and FastAPI backend both guard against off-topic prompts.

## Architecture

The React/Vite frontend provides protected Supabase Auth, navigation between the four product areas, finance-only prompt screening, the responsive neo-brutalist UI, conversation memory, and a seeded snapshot that keeps the pages readable only when a provider is unreachable. FastAPI validates Supabase access tokens (JWKS for ES256 projects, shared secret for older ones), refuses off-topic chat before model calls, forwards approved finance prompts and recent conversation turns to OpenRouter, and exposes `/api/news` and `/api/market` adapters. News is served by Alpha Vantage `NEWS_SENTIMENT` with an automatic Finnhub fallback and a curated fallback last. Stocks and crypto are live Finnhub quotes, cached server-side to stay within free-tier rate limits.

## Design direction

Neo-brutalist editorial fintech: warm paper cream, ink-black borders, electric-yellow highlights, cobalt data surfaces, and red warning states. The layout is a strong product navigation rail plus a dominant content canvas. Cards use hard offset shadows and no blur. Typography pairs Space Grotesk with IBM Plex Mono for market numbers and metadata. Controls are tactile, direct, and fast. Copy is explicit about the finance-only boundary and the difference between analysis and advice.

## Project structure

- `src/App.tsx`: auth gate, product navigation, chat behavior, news/stocks/crypto pages, fallback market data.
- `src/lib/api.ts`: authenticated chat request client and context types.
- `src/lib/supabase.ts`: browser client and session restoration.
- `src/styles.css`: shared neo-brutalist design system, page-specific layouts, and responsive breakpoints.
- `backend/main.py`: FastAPI app, token validation, finance-only guard, OpenRouter adapter, news and market adapters, health endpoint, response caching.
- `backend/check_auth.py`: runnable self-test for Supabase token verification.
- `README.md` and `.env.example`: deployment, secrets, API links, and setup instructions.
