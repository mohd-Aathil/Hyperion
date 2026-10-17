# Hyperion — build status

## Delivered and verified locally

- Finance-only chatbot: finance guard in the browser **and** in FastAPI, Gemini called only from
  the backend, model conversation memory, typing indicator, auto-scroll, formatted answers.
- Live News page: Alpha Vantage `NEWS_SENTIMENT` adapter, automatic Finnhub fallback, curated
  fallback, relative timestamps, topic tags, source links, 5-minute auto refresh.
- Stocks page: live Finnhub quotes — price, day move, day range, market cap, average volume.
- Crypto Market page: live Finnhub quotes — price, 24h move, 24h low, 24h high.
- Supabase Auth: ES256 tokens verified against the project JWKS (and HS256 secrets still supported).
- Backend caching, provider status in `/health`, `Cache-Control: no-store` on API responses.
- `backend/check_auth.py` self-test for token verification.
- README with step-by-step local setup, frontend deployment, backend deployment and Docker.

## Verified by running it

- `npm run build` (tsc + vite) passes.
- `/health`, `/api/market`, `/api/news` return live provider data.
- Garbage and expired Supabase tokens return 401; a token signed by the wrong key is rejected.
- Off-topic prompt is refused; a finance prompt reaches the model call path.
- Gemini model fallback: a retired `GEMINI_MODEL` id no longer breaks chat
  (`pytest backend/tests/test_model_fallback.py`).
- Browser check of all four pages with live data.

## Blocked on you

- Nothing. `GEMINI_API_KEY` is set in `.env` and chat answers come back.
- Optional cleanup: `scripts/set_openrouter_key.py` is a leftover from the OpenRouter build and sets
  a variable chat no longer reads.
