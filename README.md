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



