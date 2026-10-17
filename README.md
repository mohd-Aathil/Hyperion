# Hyperion — Finance-Only Chatbot + Market Desk

Hyperion is a finance-only web app with four areas:

1. **Finance Chat** — a chatbot that answers questions about stocks, crypto, markets, macro, earnings, valuation, portfolio construction, risk and financial news. Off-topic questions are refused, twice: in the browser before the request, and again in the backend before any model call.
2. **Live News** — a finance news feed with relative timestamps, topic tags and a link to each source story.
3. **Stocks** — live quotes across a major-equity watchlist with price, day move, day range, market cap and average volume.
4. **Crypto Market** — live digital-asset quotes with 24h move, 24h low and 24h high.

- **Frontend:** React 19 + Vite + TypeScript (`src/`)
- **Backend:** FastAPI (Python 3.12+) (`backend/main.py`)
- **Auth:** Supabase Auth (the backend verifies the Supabase access token on every API call)
- **Model:** Google Gemini, called **only** from the backend so the key never reaches the browser
- **Market + news data:** Finnhub (quotes and news) and Alpha Vantage (news), also backend-only

---

## 0. What is already done

| Piece | State |
|---|---|
| Supabase URL + publishable key | ✅ already filled in `[.env](.env)` |
| Finnhub key (stocks, crypto, news) | ✅ already filled in `.env` |
| Alpha Vantage key (news) | ✅ already filled in `.env` |
| **Gemini API key** (`GEMINI_API_KEY`) | ✅ already filled in `.env` (verified against the live API) |
| Frontend build (`npm run build`) | ✅ passes |
| Backend endpoints | ✅ verified against the live providers |
| Supabase token verification | ✅ verified (`python backend/check_auth.py`) |
| Brand assets (logo, favicon) | ✅ generated into `public/` from the source artwork |
| Saved conversations | ⚠️ working, but history is per browser until you run one SQL file — see section 6.1 |

**All four providers are configured, so the chatbot, news, stocks and crypto pages are all live.**
Section 1 is kept because a fresh clone or a rotated key needs it — but on this machine there is
nothing to paste.

The only outstanding setup step is section 6.1, which turns per-browser history into per-account
history.

> ### If chat ever says "Gemini is not configured"
>
> The backend reads `.env` **once, at startup**. If you change or add the key while it is running,
> the old empty value stays in memory until you restart it, and `/health` keeps reporting
> `"gemini": false`. That is the single most common cause of this message. After editing
> `.env`, stop the backend (`Ctrl+C` in its terminal) and start it again — no code change needed.
>
> Check it in one command:
>
> ```bash
> curl -s http://127.0.0.1:8000/health
> ```
>
> `"gemini": true` means chat is ready. `false` means the running process has not seen your
> key yet — restart it.

## 1. Paste your Gemini key (already set here; needed for a fresh clone)

1. Open <https://aistudio.google.com/app/apikey> and sign in.
2. Click **Create API key**, then copy the **entire** value.

**Edit the file by hand** — there is no setup script for the Gemini key.
After editing `.env`, restart the backend and check `curl -s http://127.0.0.1:8000/health`:
`"gemini": true` means chat is ready.

3. Open the environment file in this project (Windows: right-click → Open with Notepad):

   ```text
   .env          (project root — the file next to package.json)
   ```

4. Find this line and paste your key after the `=` with no quotes and no spaces:

   ```text
   GEMINI_API_KEY=
   ```

   It must end up looking like:

   ```text
   GEMINI_API_KEY=AIzaSyxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

5. Save the file and restart the backend (stop it with `Ctrl+C` in its terminal, then run the
   backend command from section 4.2 again). The Gemini free tier covers this app, so no billing
   setup is required.

> `GEMINI_MODEL` in the same file chooses the model. It is set to `gemini-3.6-flash`, which is
> current, fast and inexpensive; any current id from
> <https://ai.google.dev/gemini-api/docs/models> works.
>
> Google retires model ids over time. **A retired id no longer breaks chat:** the backend tries
> `GEMINI_MODEL` first, then falls back through `gemini-3.6-flash`, `gemini-3.5-flash` and
> `gemini-3.1-flash-lite`, logging which one answered. Set the variable anyway so the model you
> intend is the one doing the work.

---

## 2. Project structure

```text
hyperion/
├── .env                       # YOUR credentials (gitignored — never commit)
├── .env.example               # copy of the template, safe to commit
├── README.md                  # this guide
├── Dockerfile                 # single image: builds the frontend AND runs FastAPI
├── Dockerfile.api             # backend-only image for split deployments (Render etc.)
├── render.yaml                # Render blueprint: pre-fills the backend service
├── package.json               # frontend scripts + dependencies
├── vite.config.ts             # dev server on :3000, proxies /api and /health -> :8000
├── index.html                 # HTML shell + icon links
├── assets/brand/
│   └── hyperion-logo.png      # source logo artwork (the single source of truth)
├── public/
│   ├── favicon.svg            # emblem favicon (SVG with the PNG embedded)
│   ├── hyperion-logo.png      # lockup for light surfaces
│   ├── hyperion-logo-light.png# lockup for dark surfaces
│   ├── hyperion-mark.png      # emblem only
│   ├── hyperion-favicon.png   # 512px icon tile
│   └── apple-touch-icon.png
├── supabase/
│   └── conversations.sql      # per-user chat history + row level security (section 6.1)
├── scripts/
│   ├── build_brand_assets.py  # regenerates public/ from the source logo
│   └── build_brand_assets.py  # regenerates public/ from the source logo
├── src/
│   ├── App.tsx                # auth gate, 4 pages, chat logic, live data wiring
│   ├── main.tsx               # React entry point
│   ├── styles.css             # neo-brutalist design system + responsive layout
│   └── lib/
│       ├── api.ts             # typed client for /api/chat, /api/news, /api/market, /health
│       ├── conversations.ts   # chat history: Supabase when signed in, browser fallback
│       └── supabase.ts        # browser Supabase client + session restore
└── backend/
    ├── main.py                # FastAPI app: auth, finance guard, chat, news, market
    ├── requirements.txt       # Python dependencies
    └── check_auth.py          # runnable self-test for token verification
```

### Brand assets

`assets/brand/hyperion-logo.png` is the only file you replace to rebrand — everything else is
derived from it. After swapping it, regenerate the files the app actually serves:

```bash
.venv/Scripts/python scripts/build_brand_assets.py    # Windows
.venv/bin/python scripts/build_brand_assets.py        # macOS / Linux
```

That writes the light and dark lockups, the emblem mark, the favicon and the Apple touch icon into
`public/`. It needs Pillow (`pip install Pillow`), a build-time tool only — the running app never
imports it.

---

## 3. Every variable, where it goes, and where to get it

There are **two** places a variable can live:

- **Local development:** the single file `.env` in the project root. The frontend (Vite) and the
  backend (python-dotenv) both read it. Nothing else needs editing.
- **Production:** type the same names into your hosting provider's environment/secrets settings.
  Do **not** upload `.env`.

Only variables starting with `VITE_` are visible to the browser. Everything else stays on the server.

| Variable | Used by | Secret? | Where to get it |
|---|---|---:|---|
| `VITE_SUPABASE_URL` | Browser | No | Supabase → Project Settings → API |
| `VITE_SUPABASE_ANON_KEY` | Browser | No | Supabase → Project Settings → API Keys (publishable key) |
| `VITE_API_URL` | Browser | No | Only for split deployments. Leave unset for local dev and Docker |
| `SUPABASE_URL` | Backend | No | Same Supabase URL as above |
| `SUPABASE_JWKS_URL` | Backend | No | `<SUPABASE_URL>/auth/v1/.well-known/jwks.json` |
| `SUPABASE_JWT_SECRET` | Backend | **Yes** | Leave **empty** for this project (see note below) |
| `GEMINI_API_KEY` | Backend | **Yes** | <https://aistudio.google.com/app/apikey> |
| `GEMINI_MODEL` | Backend | No | Any current id from <https://ai.google.dev/gemini-api/docs/models> |
| `ALPHAVANTAGE_API_KEY` | Backend | **Yes** | <https://www.alphavantage.co/support/#api-key> |
| `ALPHAVANTAGE_NEWS_TOPICS` | Backend | No | News topic filter, default `financial_markets` |
| `FINNHUB_API_KEY` | Backend | **Yes** | <https://finnhub.io/dashboard> |
| `ALLOW_DEMO_AUTH` | Backend | No | `true` locally, **`false` in production** |
| `CHAT_RATE_LIMIT` | Backend | No | Max chat requests per user per window (default `20`) |
| `CHAT_RATE_WINDOW` | Backend | No | Rate-limit window in seconds (default `300`) |
| `CORS_ORIGINS` | Backend | No | Comma-separated list of allowed frontend origins |

### This project's own values

Your Supabase project (safe to publish — these two ship to the browser anyway):

```text
VITE_SUPABASE_URL=https://ndsymoyjcaihptacuytk.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_fzEhVv7gKs5H9iM0uzQbbQ_EtIGyd1Y
SUPABASE_URL=https://ndsymoyjcaihptacuytk.supabase.co
SUPABASE_JWKS_URL=https://ndsymoyjcaihptacuytk.supabase.co/auth/v1/.well-known/jwks.json
```

The three provider keys (`GEMINI_API_KEY`, `FINNHUB_API_KEY`, `ALPHAVANTAGE_API_KEY`) have real
values in your local `.env` and are **deliberately not repeated in this file**, because README gets
committed and those keys are billable. Copy them out of `.env` when you configure hosting. If you
ever lose them, regenerate them at the links in the table above.

> **Why `SUPABASE_JWT_SECRET` is empty:** this Supabase project signs access tokens with an
> asymmetric **ES256** key, so the backend verifies tokens against the project **JWKS** URL instead
> of a shared secret. That is the modern, safer setup. Only fill in `SUPABASE_JWT_SECRET` if you
> have an older project that still signs with an HS256 secret.

---

## 4. Run it locally

You need **Node.js 20+** and **Python 3.11+**. The steps below are written for Windows (the paths in
the original build); macOS/Linux equivalents are noted in parentheses.

### 4.1 Frontend

From the project root:

```bash
npm install
npm run dev
```

(Vite dev server: <http://localhost:3000> — it proxies `/api/*` to `http://127.0.0.1:8000`, which is
why `VITE_API_URL` can stay unset locally.)

### 4.2 Backend — open a **second** terminal, in the same folder

Windows:

```bash
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
./.venv/Scripts/python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Backend base URL: `http://127.0.0.1:8000` · health: `http://127.0.0.1:8000/health`

### 4.3 Open the app

Go to <http://localhost:3000> and either sign in with a Supabase email/password account, or click
**ENTER DEMO MODE** (works while `ALLOW_DEMO_AUTH=true`).

---

## 5. Verify it works

```bash
# 1. Health + which providers the backend can see
curl http://127.0.0.1:8000/health

# 2. Live stock + crypto quotes (demo token only works while ALLOW_DEMO_AUTH=true)
curl -H "Authorization: Bearer demo-token" http://127.0.0.1:8000/api/market

# 3. Live finance news
curl -H "Authorization: Bearer demo-token" http://127.0.0.1:8000/api/news

# 4. The finance-only guard (expect the refusal text, no model call)
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Authorization: Bearer demo-token" -H "Content-Type: application/json" \
  -d '{"prompt":"write me a poem about my cat"}'

# 5. Supabase token verification self-test (no real account needed)
./.venv/Scripts/python.exe backend/check_auth.py
```

`/health` reports `"gemini": false` until you complete step 1.

In the browser, check that: the sidebar says **LIVE MARKET FEED**, the Stocks and Crypto pages show
real prices with an as-of timestamp, Live News shows tagged headlines with source links, an
off-topic chat message is refused, and a finance question returns a model answer.

---

## 6. Supabase setup checklist

Your project already has email/password sign-in enabled. Two things to do before going live:

1. **Site URL and redirects.** Supabase dashboard → **Authentication → URL Configuration**:
   - *Site URL*: your deployed frontend domain, e.g. `https://hyperion.example.com`
   - *Redirect URLs*: add the same domain (and `http://localhost:3000` while developing)
2. **Email confirmation.** By default Supabase requires a user to confirm their email before they get
   a session. Either:
   - leave it on and configure **Authentication → Emails** (custom SMTP) so real users receive the
     confirmation mail, or
   - turn **Confirm email** off (Authentication → Providers → Email) for instant sign-up while testing.

The backend does not need a service-role key: it only *verifies* tokens. It supports both signing
schemes — HS256 legacy secrets and ES256/RS256 keys via JWKS.

### 6.1 Saved conversations (one-time SQL — required for per-user chat history)

Out of the box the app works, but each browser keeps its own chats: the history rail on the chat page
reads **SAVED IN THIS BROWSER**. To give every user their own conversations across devices, run one
file:

1. Supabase dashboard → **SQL Editor** → **New query**.
2. Paste the entire contents of [`supabase/conversations.sql`](supabase/conversations.sql).
3. Click **Run**. Expect “Success. No rows returned”.
4. Reload the app. The rail badge becomes **SYNCED TO YOUR ACCOUNT**.

That script creates two tables and locks them down with row level security, so a signed-in user can
only ever read or write their own rows:

| Table | Holds |
|---|---|
| `public.conversations` | one row per chat: `title`, `created_at`, `updated_at` |
| `public.messages` | every turn: `conversation_id`, `role`, `content`, `created_at` |

Ownership is enforced through `user_id`, which **defaults to `auth.uid()`** — the browser never sends
an owner id, and the policy rejects any row that is not the caller's. Deleting a conversation
cascades to its messages. Every statement is idempotent, so it is safe to re-run.

> No redeploy is needed. The app probes for the tables when it loads and switches to the cloud as
> soon as they exist. Until then — and always in demo mode, which has no account — history lives in
> `localStorage`.

---

## 7. Deploy the backend

The backend is a standard Python container. **Recommended: Render** (free tier, Docker support, no
credit card required). Any of the alternatives below works with the same repo.

For a split deployment (API on Render, UI on Vercel) use **`Dockerfile.api`** — it builds in seconds
and exposes only the API. Use the root `Dockerfile` only if you want one container serving both.

### 7.1 Render (recommended)

**Fastest route:** Render dashboard → **New → Blueprint** → pick this repo. Render reads
`render.yaml`, creates the service with the Docker runtime, the `/health` check and every variable
name already in place, and prompts you for the three secrets. Then edit the two `your-frontend-domain`
placeholders in `render.yaml` (or in the dashboard) once you know your Vercel URL.

**Manual route:**

1. Create a free account at <https://render.com> and connect your GitHub repository.
2. **New → Web Service**, pick the repo.
3. Settings:
   - **Language/Runtime:** `Docker`
   - **Dockerfile path:** `./Dockerfile.api`
   - **Instance type:** `Free`
   - **Health check path:** `/health`
4. Add environment variables (Render → your service → **Environment**):

   ```text
   SUPABASE_URL=https://ndsymoyjcaihptacuytk.supabase.co
   SUPABASE_JWKS_URL=https://ndsymoyjcaihptacuytk.supabase.co/auth/v1/.well-known/jwks.json
   SUPABASE_JWT_SECRET=
   GEMINI_API_KEY=<paste from .env>
   GEMINI_MODEL=gemini-3.6-flash
   ALPHAVANTAGE_API_KEY=<paste from .env>
   ALPHAVANTAGE_NEWS_TOPICS=financial_markets
   FINNHUB_API_KEY=<paste from .env>
   ALLOW_DEMO_AUTH=false
   CORS_ORIGINS=https://<your-frontend-domain>
   ```

5. **Create Web Service** and wait for the first build. Render gives you a URL such as
   `https://hyperion-api.onrender.com`.
6. Confirm it is live: open `https://hyperion-api.onrender.com/health`. In the JSON you should see
   `"finnhub": true`, `"alphavantage": true`, `"gemini": true`. Visiting the bare URL returns a
   small JSON banner confirming this is the API — the UI lives on Vercel.
7. Copy that URL: it is your `VITE_API_URL` in the next section, and put your Vercel domain into
   `CORS_ORIGINS` here. Changing either means a redeploy of the side you changed.

Notes specific to Render's free tier: it binds on `$PORT` with a default of `10000` (the container
already respects `$PORT`), the service **sleeps after 15 minutes** of no traffic and wakes on the
next request in roughly a minute — so the first chat message after a quiet period can take that long
(the frontend waits up to 90 seconds for this reason).

### 7.2 Other hosts

- **Railway** — `New Project → Deploy from GitHub`; it detects the root `Dockerfile` automatically.
  The trial gives $5 of credit for 30 days, after which the free plan gives $1/month. Set the same
  variables, add `ALLOW_DEMO_AUTH=false`, and point your domain's health check at `/health`.
- **Koyeb** — free Web Service instance (512 MB, scales to zero after an hour idle, requires a card
  for account validation). Choose Dockerfile builds from Git, then add the same variables.
- **Fly.io** — no free tier for new organizations; the smallest machine is about $2.19 per 30 days.
  ```bash
  fly auth login
  fly launch --no-deploy     # creates fly.toml; keep the internal port aligned with $PORT
  fly secrets set GEMINI_API_KEY=... FINNHUB_API_KEY=... ALPHAVANTAGE_API_KEY=... \
                   SUPABASE_URL=... SUPABASE_JWKS_URL=... ALLOW_DEMO_AUTH=false CORS_ORIGINS=...
  fly deploy
  ```
- **Any VPS / Docker host** — `docker build` + `docker run --env-file` (section 9).

Whatever you pick, the backend must be reachable over **HTTPS** with a stable domain, and
`CORS_ORIGINS` must contain your frontend origin exactly (scheme + host, no trailing slash).

---

## 8. Deploy the frontend

The frontend is a static Vite build. **Important:** Vite bakes `VITE_*` values into the JavaScript at
**build time**, so set them in the build environment and rebuild after changing them.

Build settings on every platform:

| Setting | Value |
|---|---|
| Install command | `npm ci` |
| Build command | `npm run build` |
| Output/publish directory | `dist` |
| Environment variables | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, and (only for split deploys) `VITE_API_URL` |

You then need the browser to reach the backend. Pick **one** approach:

**Option A — point the frontend straight at the backend (use this one on Vercel).**
Set `VITE_API_URL=https://hyperion-api.onrender.com` in Vercel's environment variables and redeploy,
and make sure the backend's `CORS_ORIGINS` lists your Vercel domain. Direct calls avoid any proxy
timeout, which matters because a chat answer can take up to 90 seconds when the free Render instance
is cold-starting. Rebuild/redeploy whenever the backend URL changes.

**Option B — proxy `/api/*` from the frontend host to the backend.**
Leave `VITE_API_URL` unset so the browser calls `/api/...` on its own origin. Fine for the fast
data endpoints; check your platform's proxy timeout before routing the chat through it.

- *Vercel* — add `vercel.json` in the repo root:
  ```json
  {
    "rewrites": [
      { "source": "/api/:path*", "destination": "https://hyperion-api.onrender.com/api/:path*" }
    ]
  }
  ```
  (Projects created from April 2026 honour upstream cache headers on external rewrites; the backend
  already sends `Cache-Control: no-store` on `/api/*`, so nothing gets cached.)
- *Netlify* — put `public/_redirects` in the repo (Vite copies it into `dist`):
  ```text
  /api/*  https://hyperion-api.onrender.com/api/:splat  200
  ```
  Put that line **before** any `/*  /index.html  200` SPA rule. Proxy rewrites time out after 26 s.
- *Cloudflare Pages* — `_redirects` cannot proxy to an external domain, so use a Pages Function
  (`functions/api/[[path]].js`) that forwards to `env.API_ORIGIN`, and add a `_routes.json` so only
  `/api/*` runs the Function.

Free-tier hosting facts worth knowing (checked against vendor docs): Vercel Hobby is free but
non-commercial only; Netlify's current free plan for new accounts is credit-based (production deploys
and bandwidth consume credits); Cloudflare Pages includes 500 builds/month and unlimited static
requests.

Finally, go back to Supabase → **Authentication → URL Configuration** and set the frontend domain as
the Site URL plus a redirect URL.

---

## 9. Run everything in one Docker container

This is the simplest way to have one URL. The image builds the frontend, then FastAPI serves both the
API and the built static files.

```bash
docker build \
  --build-arg VITE_SUPABASE_URL=https://ndsymoyjcaihptacuytk.supabase.co \
  --build-arg VITE_SUPABASE_ANON_KEY=sb_publishable_fzEhVv7gKs5H9iM0uzQbbQ_EtIGyd1Y \
  -t hyperion .

docker run --rm -p 3000:3000 --env-file .env hyperion
```

Open <http://localhost:3000>. Before shipping this image anywhere, edit `.env` and set
`ALLOW_DEMO_AUTH=false`, then start it with `-e ALLOW_DEMO_AUTH=false` or via your platform's
variables. The image exposes a `HEALTHCHECK` against `/health` and honours `$PORT`.

---

## 10. Going-live checklist

- [ ] `GEMINI_API_KEY` is set on the backend and `/health` shows `"gemini": true`.
- [ ] `ALLOW_DEMO_AUTH=false` in production (demo mode bypasses Supabase auth verification).
- [ ] `CORS_ORIGINS` lists your frontend domain, and only that.
- [ ] Supabase **Site URL** + **Redirect URLs** contain the production frontend domain.
- [ ] Frontend build environment has `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`.
- [ ] The frontend can reach the backend (proxy rewrite or `VITE_API_URL`), verified from the
      deployed site — not just locally.
- [ ] Signed-out users get **401** from `/api/market`, `/api/news` and `/api/chat`.
- [ ] Two different accounts see their own data and cannot break each other's session.
- [ ] An off-topic chat message is refused; a finance question returns a model answer.
- [ ] No secret appears in the browser bundle: search the built `dist/` output for the Gemini key,
      the Finnhub key and the Alpha Vantage key. None should appear.

---

## 11. The Render + Vercel runbook, in order

1. Paste the Gemini key into `.env` and confirm chat works locally (README section 1).
2. Push the repo to GitHub (`.env` stays ignored — verify with `git status`).
3. Render → **New → Blueprint** → pick the repo → paste the three secrets when prompted.
4. Wait for the build. Open `https://<your-api>.onrender.com/health` and check all three providers
   report `true`.
5. Vercel → **Add New → Project** → pick the repo. Framework `Vite`, build `npm run build`, output
   `dist`. Add `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` and
   `VITE_API_URL=https://<your-api>.onrender.com`, then deploy.
6. Back in Render, set `CORS_ORIGINS` to your Vercel domain and let it redeploy.
7. Supabase → **Authentication → URL Configuration** → set the Site URL and add the Vercel domain to
   Redirect URLs.
8. Open the Vercel URL, sign in, and run the section 10 checklist against the live site.

---

## 12. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| Chat says *"Gemini is not configured"*, or the chat header shows **NO MODEL KEY** with a pink banner | `GEMINI_API_KEY` is empty on the **backend**. Complete step 1 and restart. The banner clears after you reload the page. |
| Chat says *"Gemini rejected the API key"* | Key is truncated or wrong. Copy the whole value from <https://aistudio.google.com/app/apikey>. |
| Chat says *"Gemini model '...' not found"* | The model id is retired. Chat falls back to a working id automatically, so this only shows if *every* candidate is unavailable — set `GEMINI_MODEL` in `.env` to a current id and restart. |
| Chat says *"Gemini rate limit reached"* | Free-tier quota exhausted, or too many chats at once. Wait a moment and send again. |
| Signing out keeps you in the app | Fixed. **Sign out** now clears the session and returns to the sign-in screen. |
| Chat says *"Missing Supabase access token"* (401) | In production `ALLOW_DEMO_AUTH` is `false` and you are not signed in. Sign in, or use the demo flag locally. |
| Chat says *"Invalid or expired Supabase access token"* | Wrong `SUPABASE_URL`/`SUPABASE_JWKS_URL`, or a stale session. Sign out and in again. |
| Chat says *"I could not reach the finance model"* with a network reason | Backend not running, wrong `VITE_API_URL`, or CORS blocked. Check `/health` and the browser console. |
| First message after idling takes ~1 minute on Render free | Expected cold start. The next requests are fast. |
| Stocks/Crypto pages show **SEEDED** instead of **LIVE** | The backend has no reachable Finnhub key, or you are rate-limited. Check `/health` → `"finnhub"`. |
| News says **CURATED FALLBACK** | Alpha Vantage NEWS_SENTIMENT is premium-only on a free key and Finnhub returned nothing. See section 13. |
| Empty crypto market cap / volume | Finnhub's free tier does not expose crypto market cap, candles or volume. The page shows 24h low/high instead. |
| The history rail says **SAVED IN THIS BROWSER** | You have not run `supabase/conversations.sql` yet, or you are in demo mode (no account). See section 6.1. |
| History is empty after signing in elsewhere | Expected until section 6.1 is done — before that, history belongs to one browser. |
| Sign-up does nothing | Supabase "Confirm email" is on and no SMTP is configured. See section 6. |

---

## 13. Data providers, limits and caching

**Finnhub** (`FINNHUB_API_KEY`) supplies stock quotes via `/quote`, company names and market caps
via `/stock/profile2`, average volume via `/stock/metric`, and the news feed via `/company-news`,
`/news?category=general|crypto|forex|merger`. Crypto prices come from the same `/quote` endpoint
using Binance pairs such as `BINANCE:BTCUSDT`. Finnhub's free tier does **not** include
`/crypto/candle`, so no OHLC history or crypto market cap is available — the Crypto page shows
24h low/high instead of a fabricated market cap.

**Alpha Vantage** (`ALPHAVANTAGE_API_KEY`) is tried **first** for news via `NEWS_SENTIMENT`. On a free
key Alpha Vantage currently reports that endpoint as premium-only, so the backend automatically falls
back to Finnhub's news. Both paths pass the same filter, which drops generic lifestyle stories. If you
upgrade Alpha Vantage, the feed switches over with no code change.

**Backend caching** (keeps you inside free-tier rate limits): quotes 45 s, news 5 minutes, company
profiles and metrics 6 hours. The live news page also refreshes itself every 5 minutes.

**Off-topic filtering:** a keyword guard in both the browser and the backend, plus a system prompt
that instructs the model to refuse non-finance topics. Because the guard is keyword-based, a finance
question with no finance vocabulary can be refused — rephrase with a ticker, sector or market term.

---

## 14. Security rules

- Keys live only in `.env` (gitignored) or your platform's secret settings. Never in `src/`, never in
  a `VITE_*` variable, never in a commit.
- `VITE_*` values are public by definition. Only Supabase's URL and publishable/anon key belong there.
- The backend validates a Supabase access token on every `/api/*` route; the model and market keys
  are never proxied to the browser.
- API responses are sent with `Cache-Control: no-store`.
- `ALLOW_DEMO_AUTH=true` bypasses token verification. It exists for local development only.
- Verified locally: the browser and backend both refuse off-topic prompts, a forged or expired token
  is rejected (401), and a token signed with the wrong key is rejected.

## 15. Honest limits

Market data is third-party and may be delayed; free tiers rate-limit; AI output can be wrong.
Hyperion collects and stores **no portfolio data at all**: only live market quotes are sent to the
model as context, and there is no brokerage connection of any kind. Conversations are saved only
after section 6.1 has been run, and then only for the signed-in account. Hyperion is educational
tooling, **not investment advice**.
