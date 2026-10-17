# Hyperion — Production Readiness Audit

**Date:** 2026-10-17 · **Verdict: ready to deploy**, with the checklist in §6 to complete during publication.

---

## 1. Secrets — PASS

| Item | Result |
|---|---|
| Real provider keys (`GEMINI_API_KEY`, `FINNHUB_API_KEY`, `ALPHAVANTAGE_API_KEY`) | Only in `.env`, which is git-ignored (`.gitignore:5`); never copied into any image or bundle |
| Secret scan (`sk-or-v1-`, `AIzaSy…`, `AQ.Ab8`, `sb_secret_`, raw key assignments) across all tracked source/config/docs | **No exposure.** Only placeholder values (`YOUR_*`) and the public Supabase URL + publishable key, which ship to the browser by design |
| `VITE_*` bundle | Contains only `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` (publishable). No secret ever prefixes `VITE_` |
| Backend reads keys | `os.getenv` at request time; never logged (`httpx`/`httpcore` loggers suppressed to WARNING because keys travel in query strings) |
| Turned-off OpenRouter key comment in `.env` | Left in place deliberately (your file, marked "disabled — kept for reference"). It is ignored by both frontend and backend |

## 2. Auth — PASS

- Every `/api/*` route requires a verified Supabase JWT (`current_user` dependency): ES256/RS256 via the project JWKS, HS256 shared secret supported, `aud` must be `authenticated`.
- `backend/check_auth.py` self-test: valid token accepted, expired rejected, wrong-key-forged rejected, wrong audience rejected, live JWKS reachable — **all PASS** (exit 0).
- Production mode verified on a scratch instance (`ALLOW_DEMO_AUTH=false`, :8001): `/api/market`, `/api/news`, `/api/chat` without a token → **401**; forged bearer → **401**; literal `demo-token` → **401**. `/health` stays public (200) for host health checks.
- **Before publishing, set `ALLOW_DEMO_AUTH=false` on the deployed backend.** README §10 checklist covers this.
- The frontend gate is client-side only; all data still requires a valid token from the API. Sign-out clears the session.

## 3. Rate limiting — PASS (new in this pass)

- Added a per-principal sliding-window limiter on `/api/chat` (the only billable, model-backed endpoint): default **20 requests / 300 s per user**, tunable via `CHAT_RATE_LIMIT` / `CHAT_RATE_WINDOW` (documented in `.env.example` and README §3).
- Verified live: requests 1–19 accepted, 20+ → **HTTP 429** with an actionable message; the bucket clears as the window slides.
- Finance-guard refusals do not consume the budget (they cost nothing).
- Non-model endpoints (`/api/market`, `/api/news`) stay cheap via server-side caches (45 s / 5 min TTL) so bursts do not multiply provider calls.
- Gemini calls have model-level fallback (`gemini-3.6-flash → 3.5-flash → 3.1-flash-lite`) for retired ids or 503-capacity errors; quota/key errors are never silently swapped.

## 4. Database (Supabase) — PASS

- `supabase/conversations.sql` creates `conversations` + `messages` with RLS **enabled** and deny-by-default policies (`auth.uid() = user_id` on both `using` and `with check`); grants to `authenticated` only; cascade deletes; indexes on the access paths.
- The client never sends a user id — ownership always defaults to `auth.uid()`, so there is no IDOR surface.
- The backend needs **no service-role key** (it only verifies tokens). Nothing in the repo holds one.
- **Run this SQL once in the Supabase SQL editor before publishing** if you want per-account chat history (otherwise history stays per-browser — the app still works).

## 5. Code hardening + structure (this pass)

| Fix | Why |
|---|---|
| `payload.model` from the client is now **ignored** | A caller could otherwise name a retired/absent model or probe which ids exist. Model selection is a server decision (`active_model()`) |
| Chat scope cap shared with the guard (`MAX_HISTORY_CHARS = 8000`, defined once) | Guard and model now always see the same text — single source of truth, no drift possible; no way to get content approved through one window and send a different one to Gemini |
| `app.config.ts` removed | Dead file — no import anywhere in `src/` or `index.html`; also removed from `tsconfig.node.json` and the Dockerfile `COPY` line |
| `scripts/set_openrouter_key.py` removed | Legacy OpenRouter helper; chat no longer reads that variable, and the README pointed fresh clones at it |
| `__pycache__/`, `.pytest_cache/` cleaned | Deleted from the working tree so nothing stale ships in any archive |
| README / `.env.example` / `render.yaml` updated | Correct Gemini variable names everywhere; no OpenRouter references left to break a fresh deployment |
| Repo hygiene already correct | `.env`, `.venv/`, `node_modules/`, `dist/`, `*.log`, `__pycache__/` are all git-ignored — verified with `git check-ignore -v` |

## 6. What remains manual for you (checklist)

- [ ] **Render backend** (or chosen host): set env vars from README §3 with real values, `ALLOW_DEMO_AUTH=false`, `CORS_ORIGINS=https://<your-vercel-domain>`.
- [ ] **Vercel frontend**: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, and `VITE_API_URL=https://<your-api-host>` at build time.
- [ ] **Supabase → Authentication → URL Configuration**: Site URL = production domain; keep `http://localhost:3000` as a dev redirect.
- [ ] **Run `supabase/conversations.sql`** once in the SQL editor for per-account history.
- [ ] **GitHub push**: safe — verify with `git status --short` that nothing secret-looking appears (nothing does, verified).
- [ ] **Rotate the Finnhub + Alpha Vantage keys before going fully public if the repo was ever cloned or the `.env` ever shared**: rotation is free and instant at their dashboards. The Gemini key was freshly issued and has only lived in `.env`.

## 7. Verified working (end-to-end, this pass)

- 50/50 backend tests pass (`pytest backend/tests`); auth self-test passes (exit 0).
- `npm run build` (tsc + vite) succeeds.
- Real chat round-trips: *"Why is NVDA moving?"* → model answer; *"explain the pe ratio to a beginner"* → answer; off-topic → refused (both browser and backend guard).
- Rate limiter fires at exactly the configured threshold (20).
- Production-mode 401 posture confirmed on a clean instance.
- Browser preview: sign-in gate, demo mode, all four pages, no config warning, no console errors.
- Live market/news data flows through the Vite proxy on `/api` + `/health`.

## 8. Known non-blocking papercuts

- The keyword guard refuses "P/E ratio" written with a slash ("pe ratio" without one passes). Cosmetic; any rephrase reaches the model, and the README documents the keyword nature of the guard.
- Alpha Vantage free tier rejects `NEWS_SENTIMENT` (premium-only) — the feed automatically falls back to Finnhub, which works. Expected, documented in README §13.
- `/health` keeps an `"openrouter": true` *alias* mirroring the Gemini key state for older clients; harmless, documented in code.
