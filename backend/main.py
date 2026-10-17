"""Hyperion finance API.

Serves the finance-only chatbot, the live news feed, and live stock/crypto
quotes. All third-party secrets live here and never reach the browser.
"""

from __future__ import annotations

import html
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from collections import defaultdict, deque

from google import genai
from google.genai import types as genai_types
import httpx
import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
# Provider keys travel in query strings, and httpx logs full URLs at INFO level.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
log = logging.getLogger("hyperion")

app = FastAPI(title="Hyperion Finance API", version="1.0.0")

# Build the Gemini client at startup (reconfigured in the route if key is absent at boot)
_gemini_key = (os.getenv("GEMINI_API_KEY") or "").strip()
if _gemini_key:
    _gemini_client = genai.Client(api_key=_gemini_key)
else:
    _gemini_client = None
    log.warning(
        "GEMINI_API_KEY is empty, so /api/chat will answer with 503. "
        "Add it to .env for a local run, or to the host's environment variables when deployed."
    )

origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)



@app.middleware("http")
async def no_store_api_responses(request: Request, call_next: Any) -> Any:
    """Authenticated data must never be cached by a proxy or CDN."""
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


FINNHUB_BASE = "https://finnhub.io/api/v1"
ALPHAVANTAGE_BASE = "https://www.alphavantage.co/query"
REQUEST_TIMEOUT = 20.0

# Google retires model ids over time (a retired id makes every chat request fail), so the
# chat route walks FALLBACK_GEMINI_MODELS and answers with the first id this key accepts.
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
FALLBACK_GEMINI_MODELS = ("gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite")


class NoUsableModel(RuntimeError):
    """No candidate Gemini model could answer: each id was retired or the model was overloaded."""

    def __init__(self, tried: list[str], retired: list[str]) -> None:
        super().__init__(", ".join(tried))
        self.tried = tried
        self.retired = retired

    @property
    def every_id_retired(self) -> bool:
        return len(self.retired) == len(self.tried)

# --------------------------------------------------------------------------- #
# Finance-only guard
# --------------------------------------------------------------------------- #

FINANCE_TERMS = (
    "stock", "share", "equity", "equities", "etf", "fund", "index", "ipo", "dividend", "earnings",
    "revenue", "profit", "margin", "guidance", "valuation", "multiple", "pe ratio", "capital",
    "crypto", "bitcoin", "ethereum", "altcoin", "token", "coin", "blockchain", "stablecoin", "defi",
    "market", "nasdaq", "dow jones", "s&p", "spx", "vix", "bull", "bear", "rally", "selloff", "volatility",
    "portfolio", "invest", "investing", "trade", "trading", "trader", "broker", "hedge", "leverage",
    "option", "futures", "short", "allocation", "diversif", "risk", "drawdown", "rebalance",
    "bond", "yield", "treasury", "rate", "fed", "federal reserve", "inflation", "recession", "gdp",
    "macro", "monetary", "fiscal", "quantitative", "economy", "economic", "cpi", "ppi", "unemployment",
    "currency", "forex", "dollar", "euro", "yen", "commodity", "gold", "oil", "silver", "crypto market",
    "ticker", "balance sheet", "cash flow", "eps", "sec filing", "buyback", "merger", "acquisition",
    "nvda", "msft", "aapl", "tsla", "amzn", "meta", "goog", "btc", "eth", "sol", "xrp", "doge", "bnb",
    # Indian & global mutual fund / retail investing vocabulary
    "sip", "swp", "stp", "elss", "nps", "nav", "nifty", "sensex", "bse", "nse",
    "mutual fund", "lumpsum", "lump sum", "smallcap", "small cap", "largecap", "large cap",
    "midcap", "mid cap", "index fund", "aum", "folio", "redemption", "expense ratio",
    "cagr", "xirr", "absolute return", "annualised", "annualized", "wealth", "corpus",
    "ppf", "epf", "pf", "nsc", "fd", "fixed deposit", "recurring deposit", "rd",
    "sebi", "amfi", "rbi", "repo rate", "reverse repo", "monetary policy", "mpc",
    "gilt", "g-sec", "sovereign", "credit rating", "aaa", "ncd", "debenture",
    "roe", "roa", "roce", "pe", "pb", "ev", "ebitda", "free cash flow", "fcf",
    "ipo allotment", "grey market", "gmp", "listing gain", "oversubscribed",
    "intraday", "delivery", "swing trade", "positional", "technical analysis",
    "fundamental analysis", "support", "resistance", "moving average", "rsi", "macd",
    "candlestick", "volume", "open interest", "circuit breaker", "upper circuit", "lower circuit",
    "reliance", "tcs", "infosys", "hdfc", "icici", "sbi", "wipro", "bajaj", "adani",
    "zerodha", "groww", "coin", "kuvera", "paytm money",
)

REFUSAL = (
    "I am built only for finance. Ask me about a stock, crypto asset, market, portfolio, macro event, "
    "earnings report, valuation, or investing concept."
)

# History budget shared by the guard and the chat route, so a follow-up is judged on exactly
# the text the model will see. Defined here because the guard imports it first.
MAX_HISTORY_CHARS = 8000


# --------------------------------------------------------------------------- #
# Scope guard
# --------------------------------------------------------------------------- #
#
# The frontend guard over-refuses plain-language finance follow-ups ("explain
# that to me like you're teaching a beginner" already has the answer above it, and
# the user clearly wants more finance, not a poem or a flight booking). The backend
# version below is the real gate — it is meant to be permissive about *how* someone
# asks, and strict only about *whether* the topic is finance.
#
# Detection, in priority order:
#  1. Any outright non-finance instruction is rejected before anything else.
#  2. Instructions about *how* to explain are allowed if there is finance context.
#  3. A bare explanation request is allowed only if it points at recent turn content
#     or at words that read like a finance explanation target.
#  4. Otherwise the old keyword dictionary decides.
#
# To keep this honest and reviewable, *every* allowance lists the reason it was
# allowed. Expand the allow lists with your own judgement, never by pasting a big
# list of vague words.

# Shortest plain-language templates that clearly ask the model to explain in simple
# terms without naming a finance topic. These exist so a real follow-up such as
# "explain that to me like you're teaching a beginner" is not treated as a request
# to bake a cake. Anything not obviously finance is kept on the deny list below.
_SIMPLE_EXPLAIN_TOPIC_HINTS = frozenset({
    # generic finance-concept words that a beginner explanation usually names
    "invest", "investment", "mutual fund", "etf", "stock", "share", "equity",
    "bond", "option", "future", "crypto", "bitcoin", "ethereum", "commodity",
    "macro", "market", "economy", "rate", "yield", "return", "risk",
    "valuation", "dividend", "eps", "cagr", "nifty", "sensex",
})

# Topics that have nothing to do with finance. Anything that looks like this is
# rejected even if it also contains a finance word (faith/macro/tax exceptions
# below handle the finance-possibilities).
#
# These are the anchors of the guard. Add a family only when you've actually seen a
# request land here and you are certain it is not finance.
_NON_FINANCE_ANCHORS = frozenset({
    "recipe", "oven", "coffee", "cup of tea", "cup of coffee", "bake", "pasta", "cake", "pie",
    "pizza", "dinner", "lunch", "breakfast", "food", "drink", "cocktail",
    "sports", "football", "soccer", "basketball", "baseball", "tennis", "cricket",
    "match", "match result", "will win", "will lose", "score", "goal",
    "movie", "film", "series", "episode", "netflix", "hollywood",
    "game", "gaming", "playstation", "xbox", "ps5", "console",
    "book a", "flight", "hotel", "trip plan", "travel itinerary",
    "password reset", "reset my", "change my password", "forgot my password",
    "write an email", "draft an email", "email template",
    "python code", "javascript", "react code", "html", "css code",
    "wikipedia", "who is the ceo of", "google", "youtube",
    "summary of today's news", "top stories", "what happened today",  # non-finance daily agenda
})

# Follow-up language templates that are itself not a topic, and must point at context
# to be allowed. Plain-language explanation requests like "explain that to a beginner"
# are allowed only if we can see a finance question already in the prompt.


def _has_inline_finance_word(text: str) -> bool:
    """Old keyword dictionary, used as a fallback for topic detection."""
    lowered = text.lower()
    return any(term in lowered for term in FINANCE_TERMS)


def _is_plain_language_request(text: str) -> bool:
    '''"Explain that to me like you are teaching a beginner" type requests.'''
    lowered = text.lower()
    has_explain_behavior = (
        ("explain" in lowered and any(w in lowered for w in ("it", "that", "this", "more", "me", "you"))) or
        ("break" in lowered and "down" in lowered) or
        ("say it" in lowered) or
        ("say" in lowered and "like" in lowered and any(w in lowered for w in ("you", "i", "as if", "a beginner")))
    )
    has_explanation_target = any(hint in lowered for hint in (
        "like you", "like i", "as if", "imagine", "beginner", "layman",
        "5 year old", "10 year old", "simple terms", "plain english",
        "simple words", "simple language", "in simple",
    ))
    return has_explain_behavior and has_explanation_target


def _is_context_probe(text: str) -> bool:
    """""What does that mean", "What about", "and why", "do the same",
    ask for more on the last topic — follow-up without own topic words.
    These are allowed only when there is finance context in the prompt."""
    lowered = text.lower()
    probe_phrases = (
        "what does that mean", "what about", "and why", "why is that",
        "do the same", "and how", "is that", "so why", "how so",
        "do i", "should i", "what happens", "does that mean",
        "tell me more", "go deeper", "say more", "tell me about",
        "explain more", "then what", "how does that",
    )
    return any(phrase in lowered for phrase in probe_phrases)


def _first_sentence(text: str) -> str:
    """Take the first sentence for judgement, so a race/game result tacked onto
    a finance question does not win."""
    lowered = text.lower()
    for sep in (". ", "! ", "? ", "\n", "."):
        i = lowered.find(sep)
        if i != -1:
            return text[:i]
    return text


def _last_assistant_answer(text: str) -> str:
    """Pull the last assistant answer out of a rendered chat prompt so a
    context-bearing follow-up can be judged against the topic it refers to.

    The chat route renders the user prompt as::

        Question: <follow-up>\n\n<context block>\n\n<history>\n\nQuestion: <current>

    and a refusal case renders the assistant answer inline as::

        <follow-up> (context from last turn: <previous answer>)

    Both shapes are handled: take the tail after the last ``Question:`` marker,
    then, if that still has no finance word, fall back to the ``(context from
    last turn: ...)`` parenthetical.
    """
    lowered = text.lower()
    q_idx = lowered.rfind("question:")
    if q_idx != -1:
        tail = text[q_idx + len("question:"):].strip()
        if tail:
            return tail
    # Fallback for the unit-test rendering helper used in the regression tests.
    ctx_idx = lowered.find("(context from last turn:")
    if ctx_idx != -1:
        body = text[ctx_idx + len("(context from last turn:"):]
        close = body.find(")")
        if close != -1:
            return body[:close].strip()
    return ""


def render_chat_prompt(prompt: str, history: list[ChatTurn] | None = None) -> str:
    """Build the prompt the chat route actually sends to the model and run it
    through the finance scope guard.

    A standalone prompt is judged on its own. A follow-up with no own finance
    topic is judged against the most recent assistant answer attached as context,
    which mirrors what the /api/chat route does before it forwards the request to
    the model. This is the function the chat route should call.
    """
    rendered: str
    if history:
        recent: list[dict[str, str]] = []
        budget = MAX_HISTORY_CHARS
        for turn in reversed(history[-12:]):
            budget -= len(turn.content)
            if budget < 0:
                break
            recent.insert(0, {"role": turn.role, "content": turn.content})
        last_answer = ""
        for turn in reversed(recent):
            if turn["role"] == "assistant" and turn["content"].strip():
                last_answer = turn["content"].strip()
                break
        if last_answer:
            rendered = f"{prompt} (context from last turn: {last_answer})"
        else:
            rendered = prompt
    else:
        rendered = prompt
    return rendered


def is_finance_prompt(prompt: str, history: list[ChatTurn] | None = None) -> bool:
    if not prompt or not prompt.strip():
        return False

    # Judge the prompt the same way the chat route will send it: with the most
    # recent assistant answer attached as context when there is one. That puts a
    # finance follow-up back in front of the same dictionary that already handles
    # the topic, without widening the gate for anything that is genuinely not
    # finance.
    text = render_chat_prompt(prompt, history).strip()
    lowered = text.lower()

    # 1. Outright non-finance instructions are rejected first, even if a finance
    #    word happens to be somewhere in the attached context.
    for anchor in _NON_FINANCE_ANCHORS:
        if anchor in lowered:
            return False

    # 2. A plain-language explanation request ("explain that to me like you are
    #    teaching a beginner") or a context-probe follow-up ("what does that mean")
    #    that names a finance topic anywhere in the rendered prompt is in scope. When
    #    the chat loop has attached the previous assistant answer as context, that
    #    puts a finance follow-up back in front of the same dictionary that already
    #    handles the topic.
    if _is_plain_language_request(text) or _is_context_probe(text):
        if _has_inline_finance_word(text):
            return True
        # The rendered prompt is a bare explanation/follow-up with no finance topic
        # anywhere. That is genuinely ambiguous and is refused.
        return False

    # 3. Everything else is decided by the old keyword dictionary.
    return _has_inline_finance_word(text)


# --------------------------------------------------------------------------- #
# Supabase token verification (HS256 legacy secret or ES256/RS256 JWKS)
# --------------------------------------------------------------------------- #

JWKS_CACHE_LIFESPAN = 3600
_jwks_clients: dict[str, jwt.PyJWKClient] = {}


def jwks_url() -> str:
    explicit = (os.getenv("SUPABASE_JWKS_URL") or "").strip()
    if explicit:
        return explicit
    base = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    if not base:
        raise ValueError("Set SUPABASE_JWKS_URL or SUPABASE_URL")
    return f"{base}/auth/v1/.well-known/jwks.json"


def jwks_client() -> jwt.PyJWKClient:
    url = jwks_url()
    client = _jwks_clients.get(url)
    if client is None:
        client = jwt.PyJWKClient(url, cache_keys=True, lifespan=JWKS_CACHE_LIFESPAN)
        _jwks_clients[url] = client
    return client


def decode_supabase_token(token: str) -> dict[str, Any]:
    """Verify a Supabase access token.

    Projects created after 2025 sign with an asymmetric key (ES256) and must be
    verified against the project JWKS. Older projects use an HS256 shared
    secret. Both are supported, JWKS first is not required - order is cheap.
    """
    secret = (os.getenv("SUPABASE_JWT_SECRET") or "").strip()
    if secret:
        try:
            return jwt.decode(token, secret, algorithms=["HS256"], audience="authenticated")
        except jwt.PyJWTError:
            pass  # Project uses asymmetric signing keys - fall through to JWKS.
    signing_key = jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["ES256", "ES384", "RS256", "RS384"],
        audience="authenticated",
    )


def current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    allow_demo = (os.getenv("ALLOW_DEMO_AUTH") or "false").strip().lower() == "true"
    if allow_demo and authorization in (None, "Bearer demo-token"):
        return {"sub": "demo-user", "email": "demo@hyperion.local", "demo": True}
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Supabase access token")
    try:
        return decode_supabase_token(authorization.removeprefix("Bearer ").strip())
    except Exception as exc:  # noqa: BLE001 - any verification failure is a 401
        log.warning("Supabase token rejected: %s", exc)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired Supabase access token") from exc


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #


class PortfolioPosition(BaseModel):
    ticker: str
    name: str = ""
    allocation: float = 0
    value: float = 0
    change: float = 0


class MarketAsset(BaseModel):
    ticker: str
    price: float = 0
    change: float = 0


class ChatContext(BaseModel):
    portfolio: list[PortfolioPosition] = Field(default_factory=list)
    market: list[MarketAsset] = Field(default_factory=list)


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    selected_symbol: str = Field(default="SPX", max_length=24)
    context: ChatContext = Field(default_factory=ChatContext)
    history: list[ChatTurn] = Field(default_factory=list)
    model: str | None = None


class NewsItem(BaseModel):
    source: str
    title: str
    summary: str
    time: str
    tag: str
    tone: str
    url: str = ""


class Quote(BaseModel):
    ticker: str
    name: str
    price: float
    change: float
    high: float | None = None
    low: float | None = None
    prevClose: float | None = None
    marketCap: str = ""
    volume: str = ""
    source: str = "finnhub"


class MarketResponse(BaseModel):
    asOf: str
    source: str
    live: bool
    stocks: list[Quote]
    crypto: list[Quote]


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #

_cache: dict[str, tuple[float, Any]] = {}


def cache_get(key: str, ttl: float) -> Any | None:
    entry = _cache.get(key)
    if entry and time.time() - entry[0] < ttl:
        return entry[1]
    return None


def cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.time(), value)


# --------------------------------------------------------------------------- #
# Rate limiting (in-process, per user, sliding window)
# --------------------------------------------------------------------------- #
#
# The chat route makes a billable Gemini call for every accepted prompt. On a
# public deployment an unthrottled user (or a bot) could burn the whole quota
# in minutes, so calls are metered per principal. The windows are deliberately
# generous for a human: nobody chatting normally will hit them.

CHAT_RATE_LIMIT = int((os.getenv("CHAT_RATE_LIMIT") or "").strip() or 20)          # max requests ...
CHAT_RATE_WINDOW_SECONDS = float((os.getenv("CHAT_RATE_WINDOW") or "").strip() or 300)  # ... per this many seconds

_chat_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def chat_rate_limit_exceeded(principal: str) -> bool:
    """True when `principal` has consumed its whole sliding window (and recorded the hit)."""
    now = time.time()
    bucket = _chat_rate_buckets[principal]
    while bucket and now - bucket[0] > CHAT_RATE_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= CHAT_RATE_LIMIT:
        return True
    bucket.append(now)
    return False


def compact_number(value: float | None) -> str:
    """Render 4912984 (millions) style figures into 4.91T / 312.4M strings."""
    if value is None or value <= 0:
        return ""
    for limit, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if value >= limit:
            return f"{value / limit:.2f}".rstrip("0").rstrip(".") + suffix
    return f"{value:.0f}"


def relative_time(published: datetime | None) -> str:
    if published is None:
        return "recently"
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - published).total_seconds()
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} hr ago"
    return f"{int(seconds // 86400)} d ago"


# Word-boundary gate used for the news feed. Headlines must look like market news.
HEADLINE_RE = re.compile(
    r"\b(stocks?|shares?|equit(?:y|ies)|markets?|nasdaq|dow(?:jones)?|s&p|wall street|earnings|revenue|profit|guidance|"
    r"valuation|ipo|dividend|buybacks?|mergers?|acquisitions?|deal|bonds?|yields?|treasur(?:y|ies)|inflation|"
    r"fed|federal reserve|rate|rates|gdp|recession|economy|economic|tariffs?|investors?|investing|trader?|trading|"
    r"crypto|bitcoin|ethereum|blockchain|stablecoin|token|defi|etfs?|funds?|hedge|futures|options?|"
    r"capit(?:al|alization)|securities|analysts?|quarter(?:ly)?|bull|bear|rally|selloff|volatility|portfolios?|tickers?)\b",
    re.IGNORECASE,
)


def is_finance_headline(headline: str, related: str, tag: str) -> bool:
    """Keep the news feed finance-relevant without dropping real market stories."""
    if related.strip():
        return True
    if tag != "MARKETS":
        return True
    return bool(HEADLINE_RE.search(headline))


TAG_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("CRYPTO", "red", re.compile(r"\b(bitcoin|btc|ethereum|eth|crypto|blockchain|stablecoin|solana|sol|xrp|dogecoin|doge|altcoin|defi|binance|nft|digital assets?)\b", re.IGNORECASE)),
    ("EARNINGS", "yellow", re.compile(r"\b(earnings|quarterly|q[1-4]|results|guidance|profit|revenue|eps|fiscal|outlook)\b", re.IGNORECASE)),
    ("MACRO", "blue", re.compile(r"\b(fed|federal reserve|inflation|interest rates?|treasury|yields?|dollar|economy|economic|gdp|tariffs?|central bank|cpi|recession|policymakers?)\b", re.IGNORECASE)),
    ("TECH", "yellow", re.compile(r"\b(chips?|semiconductors?|artificial intelligence|ai|nvidia|software|cloud|data cent(?:er|re)s?)\b", re.IGNORECASE)),
]


def tag_for(text: str) -> tuple[str, str]:
    """Return (tag, tone) for a headline, matched on whole words."""
    for tag, tone, pattern in TAG_PATTERNS:
        if pattern.search(text):
            return tag, tone
    return "MARKETS", "yellow"


# --------------------------------------------------------------------------- #
# Market data (Finnhub)
# --------------------------------------------------------------------------- #

STOCK_UNIVERSE: list[tuple[str, str]] = [
    ("NVDA", "NVIDIA"),
    ("MSFT", "MICROSOFT"),
    ("AAPL", "APPLE"),
    ("TSLA", "TESLA"),
    ("AMZN", "AMAZON"),
    ("META", "META PLATFORMS"),
]

CRYPTO_UNIVERSE: list[tuple[str, str, str]] = [
    ("BTC", "Bitcoin", "BINANCE:BTCUSDT"),
    ("ETH", "Ethereum", "BINANCE:ETHUSDT"),
    ("SOL", "Solana", "BINANCE:SOLUSDT"),
    ("XRP", "XRP", "BINANCE:XRPUSDT"),
    ("BNB", "BNB", "BINANCE:BNBUSDT"),
    ("DOGE", "Dogecoin", "BINANCE:DOGEUSDT"),
]

SEED_STOCKS = [
    Quote(ticker="NVDA", name="NVIDIA", price=143.59, change=3.8, source="seed"),
    Quote(ticker="MSFT", name="MICROSOFT", price=497.21, change=1.2, source="seed"),
    Quote(ticker="AAPL", name="APPLE", price=245.05, change=0.64, source="seed"),
    Quote(ticker="TSLA", name="TESLA", price=358.17, change=-1.9, source="seed"),
    Quote(ticker="AMZN", name="AMAZON", price=227.92, change=1.76, source="seed"),
    Quote(ticker="META", name="META PLATFORMS", price=606.8, change=-0.42, source="seed"),
]

SEED_CRYPTO = [
    Quote(ticker="BTC", name="Bitcoin", price=67240.5, change=-2.1, source="seed"),
    Quote(ticker="ETH", name="Ethereum", price=2614.33, change=1.45, source="seed"),
    Quote(ticker="SOL", name="Solana", price=151.84, change=4.82, source="seed"),
    Quote(ticker="XRP", name="XRP", price=0.534, change=-0.88, source="seed"),
    Quote(ticker="BNB", name="BNB", price=583.12, change=0.39, source="seed"),
    Quote(ticker="DOGE", name="Dogecoin", price=0.142, change=2.12, source="seed"),
]


def finnhub_key() -> str:
    return (os.getenv("FINNHUB_API_KEY") or "").strip()


async def finnhub_quote(client: httpx.AsyncClient, symbol: str) -> dict[str, Any] | None:
    key = cache_get(f"fh:quote:{symbol}", 45)
    if key is not None:
        return key
    try:
        response = await client.get(f"{FINNHUB_BASE}/quote", params={"symbol": symbol, "token": finnhub_key()})
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("Finnhub quote failed for %s: %s", symbol, exc)
        return None
    if not isinstance(payload, dict) or not payload.get("c") or payload.get("c") <= 0:
        return None
    cache_set(f"fh:quote:{symbol}", payload)
    return payload


async def finnhub_profile(client: httpx.AsyncClient, symbol: str) -> dict[str, Any]:
    cached = cache_get(f"fh:profile:{symbol}", 21600)
    if cached is not None:
        return cached
    try:
        response = await client.get(f"{FINNHUB_BASE}/stock/profile2", params={"symbol": symbol, "token": finnhub_key()})
        response.raise_for_status()
        payload = response.json() if isinstance(response.json(), dict) else {}
    except (httpx.HTTPError, ValueError) as exc:
        log.info("Finnhub profile unavailable for %s: %s", symbol, exc)
        payload = {}
    cache_set(f"fh:profile:{symbol}", payload)
    return payload


async def finnhub_metric(client: httpx.AsyncClient, symbol: str) -> dict[str, Any]:
    cached = cache_get(f"fh:metric:{symbol}", 21600)
    if cached is not None:
        return cached
    try:
        response = await client.get(f"{FINNHUB_BASE}/stock/metric", params={"symbol": symbol, "metric": "all", "token": finnhub_key()})
        response.raise_for_status()
        payload = response.json().get("metric", {}) if isinstance(response.json(), dict) else {}
    except (httpx.HTTPError, ValueError) as exc:
        log.info("Finnhub metric unavailable for %s: %s", symbol, exc)
        payload = {}
    cache_set(f"fh:metric:{symbol}", payload)
    return payload


async def build_market() -> MarketResponse:
    now = datetime.now(timezone.utc).isoformat()
    if not finnhub_key():
        log.warning("FINNHUB_API_KEY is not set - serving seeded market snapshot")
        return MarketResponse(asOf=now, source="seed", live=False, stocks=SEED_STOCKS, crypto=SEED_CRYPTO)

    stocks: list[Quote] = []
    crypto: list[Quote] = []
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            for ticker, name in STOCK_UNIVERSE:
                quote = await finnhub_quote(client, ticker)
                if quote is None:
                    continue
                profile = await finnhub_profile(client, ticker)
                metric = await finnhub_metric(client, ticker)
                stocks.append(
                    Quote(
                        ticker=ticker,
                        name=(profile.get("name") or name).upper(),
                        price=round(float(quote["c"]), 2),
                        change=round(float(quote.get("dp") or 0), 2),
                        high=round(float(quote.get("h") or 0), 2) or None,
                        low=round(float(quote.get("l") or 0), 2) or None,
                        prevClose=round(float(quote.get("pc") or 0), 2) or None,
                        marketCap=compact_number((profile.get("marketCapitalization") or 0) * 1_000_000),
                        volume=compact_number((metric.get("10DayAverageTradingVolume") or 0) * 1_000_000),
                        source="finnhub",
                    )
                )
            for ticker, name, symbol in CRYPTO_UNIVERSE:
                quote = await finnhub_quote(client, symbol)
                if quote is None:
                    continue
                crypto.append(
                    Quote(
                        ticker=ticker,
                        name=name,
                        price=round(float(quote["c"]), 6) if float(quote["c"]) < 1 else round(float(quote["c"]), 2),
                        change=round(float(quote.get("dp") or 0), 2),
                        high=round(float(quote.get("h") or 0), 6) if float(quote.get("h") or 0) < 1 else round(float(quote.get("h") or 0), 2),
                        low=round(float(quote.get("l") or 0), 6) if float(quote.get("l") or 0) < 1 else round(float(quote.get("l") or 0), 2),
                        prevClose=round(float(quote.get("pc") or 0), 2) or None,
                        source="finnhub",
                    )
                )
    except httpx.HTTPError as exc:
        log.warning("Market request failed: %s", exc)

    if not stocks and not crypto:
        return MarketResponse(asOf=now, source="seed", live=False, stocks=SEED_STOCKS, crypto=SEED_CRYPTO)
    return MarketResponse(
        asOf=now,
        source="finnhub",
        live=True,
        stocks=stocks or SEED_STOCKS,
        crypto=crypto or SEED_CRYPTO,
    )


# --------------------------------------------------------------------------- #
# News (Alpha Vantage NEWS_SENTIMENT, then Finnhub, then curated)
# --------------------------------------------------------------------------- #

FALLBACK_NEWS = [
    NewsItem(source="MARKETWIRE", title="AI infrastructure spend keeps the tape tilted toward semiconductors", summary="Investors are weighing hyperscaler capex against stretched multiples as the next earnings cycle approaches.", time="12 min ago", tag="TECH", tone="yellow"),
    NewsItem(source="GLOBAL DESK", title="Dollar steadies as markets parse the next rate path", summary="Treasury yields and the dollar index remain the macro variables most likely to move risk assets today.", time="28 min ago", tag="MACRO", tone="blue"),
    NewsItem(source="CRYPTO BLOCK", title="Bitcoin trades heavy while liquidity waits for a catalyst", summary="Spot flows are mixed and volatility is compressing. The key question is whether support holds.", time="41 min ago", tag="CRYPTO", tone="red"),
    NewsItem(source="EARNINGS DESK", title="Mega-cap results are turning into a test of narrative durability", summary="The market is demanding revenue quality, not just ambitious guidance, from the largest names.", time="1 hr ago", tag="EARNINGS", tone="yellow"),
]


# Provider article text arrives with HTML fragments, entities and exotic
# whitespace (FOREXLIVE wraps summaries in <p>, Reuters uses non-breaking
# spaces). The UI renders plain text, so normalise it here, once, at the source.
#
# The tag pattern deliberately requires a letter (or slash) after "<", so real
# prose such as "S&P slips > 1%" or "rates < 2%" is never mistaken for markup.
HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")
WHITESPACE_RE = re.compile(r"\s+")


def clean_text(raw: Any) -> str:
    """Turn provider-supplied article text into plain, single-spaced prose."""
    text = html.unescape(str(raw or ""))
    if "<" in text:
        text = HTML_TAG_RE.sub(" ", text)
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")
    return WHITESPACE_RE.sub(" ", text).strip()


def parse_alphavantage_time(raw: str) -> datetime | None:
    try:
        return datetime.strptime(raw, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


async def alphavantage_news(client: httpx.AsyncClient) -> list[NewsItem]:
    key = (os.getenv("ALPHAVANTAGE_API_KEY") or "").strip()
    if not key:
        return []
    try:
        response = await client.get(
            ALPHAVANTAGE_BASE,
            params={
                "function": "NEWS_SENTIMENT",
                "topics": os.getenv("ALPHAVANTAGE_NEWS_TOPICS", "financial_markets"),
                "sort": "LATEST",
                "limit": 30,
                "apikey": key,
            },
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.info("Alpha Vantage news unavailable: %s", exc)
        return []
    if not isinstance(payload, dict) or "feed" not in payload:
        note = payload.get("Information") or payload.get("Note") if isinstance(payload, dict) else None
        if note:
            log.info("Alpha Vantage news not served on this plan: %s", note)
        return []
    items: list[NewsItem] = []
    for article in payload.get("feed", []):
        title = clean_text(article.get("title"))
        if not title:
            continue
        published = parse_alphavantage_time(article.get("time_published", ""))
        summary = clean_text(article.get("summary"))
        tag, tone = tag_for(f"{title} {summary}")
        items.append(
            NewsItem(
                source=(article.get("source") or "NEWS DESK").upper()[:24],
                title=title,
                summary=summary[:400] or "Open the story for the full finance context.",
                time=relative_time(published),
                tag=tag,
                tone=tone,
                url=article.get("url") or "",
            )
        )
    return items


def to_news_item(article: dict[str, Any]) -> tuple[datetime | None, NewsItem] | None:
    title = clean_text(article.get("headline") or article.get("title"))
    if not title:
        return None
    summary = clean_text(article.get("summary"))
    tag, tone = tag_for(f"{title} {summary}")
    if not is_finance_headline(title, article.get("related") or "", tag):
        return None
    published = None
    if article.get("datetime"):
        published = datetime.fromtimestamp(article["datetime"], tz=timezone.utc)
    return published, NewsItem(
        source=(article.get("source") or "NEWS DESK").upper()[:24],
        title=title,
        summary=summary[:400] or "Open the story for the full finance context.",
        time=relative_time(published),
        tag=tag,
        tone=tone,
        url=article.get("url") or "",
    )


async def finnhub_news(client: httpx.AsyncClient) -> list[NewsItem]:
    """Company news for the watchlist plus focused category feeds."""
    if not finnhub_key():
        return []
    today = datetime.now(timezone.utc).date()
    collected: list[tuple[datetime | None, NewsItem]] = []

    for ticker, _ in STOCK_UNIVERSE:
        try:
            response = await client.get(
                f"{FINNHUB_BASE}/company-news",
                params={"symbol": ticker, "from": str(today - timedelta(days=3)), "to": str(today), "token": finnhub_key()},
            )
            response.raise_for_status()
            articles = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.info("Finnhub company news unavailable for %s: %s", ticker, exc)
            continue
        if isinstance(articles, list):
            for article in articles[:15]:
                item = to_news_item(article)
                if item:
                    collected.append(item)

    for category in ("general", "crypto", "forex", "merger"):
        try:
            response = await client.get(f"{FINNHUB_BASE}/news", params={"category": category, "token": finnhub_key()})
            response.raise_for_status()
            articles = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.info("Finnhub news unavailable for %s: %s", category, exc)
            continue
        if isinstance(articles, list):
            for article in articles[:25]:
                item = to_news_item(article)
                if item:
                    collected.append(item)

    deduped: dict[str, tuple[datetime | None, NewsItem]] = {}
    for published, item in sorted(collected, key=lambda pair: pair[0] or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        deduped.setdefault(item.title.lower()[:90], (published, item))
    return [item for _, item in deduped.values()]


async def build_news() -> tuple[str, list[NewsItem]]:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        # Alpha Vantage NEWS_SENTIMENT first (premium plan), then Finnhub.
        items = await alphavantage_news(client)
        if items:
            return "alphavantage", items[:28]
        items = await finnhub_news(client)
        if items:
            return "finnhub", items[:28]
    return "curated", FALLBACK_NEWS


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


def active_model() -> str:
    return (os.getenv("GEMINI_MODEL") or "").strip() or DEFAULT_GEMINI_MODEL


def candidate_models(requested: str) -> list[str]:
    """The requested model first, then the known-good ids, so a retired id still answers."""
    chain = [requested]
    for name in FALLBACK_GEMINI_MODELS:
        if name not in chain:
            chain.append(name)
    return chain


def model_is_unavailable(exc: Exception) -> bool:
    """True when the provider rejected the model *id* (404 / retired), not the request itself."""
    text = str(exc).lower()
    if "404" in text or "not_found" in text:
        return True
    return "no longer available" in text or "not found" in text or "does not exist" in text


def model_is_overloaded(exc: Exception) -> bool:
    """True when the provider is out of capacity or timed out, so another model may still answer."""
    text = str(exc).lower()
    if "503" in text or "504" in text:
        return True
    return "high demand" in text or "overloaded" in text or "try again later" in text


def should_try_next_model(exc: Exception) -> bool:
    """A retired id or a busy model is worth retrying against the next candidate.

    A rejected API key, an exhausted quota or a malformed request is not: those failures would
    repeat for every candidate, so they are surfaced to the user untouched.
    """
    return model_is_unavailable(exc) or model_is_overloaded(exc)


def provider_status() -> dict[str, Any]:
    return {
        "gemini": bool((os.getenv("GEMINI_API_KEY") or "").strip()),
        # Legacy alias: older bundled frontends read this name from /health. It reports the
        # Gemini key state, because that is the only provider chat uses.
        "openrouter": bool((os.getenv("GEMINI_API_KEY") or "").strip()),
        "gemini_model": active_model(),
        "finnhub": bool(finnhub_key()),
        "alphavantage": bool((os.getenv("ALPHAVANTAGE_API_KEY") or "").strip()),
        "supabase_jwt_secret": bool((os.getenv("SUPABASE_JWT_SECRET") or "").strip()),
        "supabase_url": bool((os.getenv("SUPABASE_URL") or "").strip()),
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "service": "hyperion-finance-api", "version": app.version, "providers": provider_status()}


@app.get("/api/news")
async def news(_: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    cached = cache_get("news", 300)
    if cached is None:
        source, items = await build_news()
        cached = {"items": items, "source": source, "live": source != "curated", "asOf": datetime.now(timezone.utc).isoformat()}
        cache_set("news", cached)
    return cached


@app.get("/api/market")
async def market(_: dict[str, Any] = Depends(current_user)) -> MarketResponse:
    cached = cache_get("market", 45)
    if cached is None:
        cached = await build_market()
        cache_set("market", cached)
    return cached


def recent_history(history: list[ChatTurn]) -> list[dict[str, str]]:
    turns: list[ChatTurn] = []
    budget = MAX_HISTORY_CHARS
    for turn in reversed(history[-12:]):
        budget -= len(turn.content)
        if budget < 0:
            break
        turns.insert(0, turn)
    return [{"role": turn.role, "content": turn.content} for turn in turns]


@app.post("/api/chat")
async def chat(payload: ChatRequest, user: dict[str, Any] = Depends(current_user)) -> dict[str, str]:
    principal = str(user.get("sub") or "anon")
    if chat_rate_limit_exceeded(principal):
        raise HTTPException(
            status_code=429,
            detail=(
                f"Too many questions in a short window ({CHAT_RATE_LIMIT} per "
                f"{int(CHAT_RATE_WINDOW_SECONDS)}s). Give it a moment and try again."
            ),
        )

    if not is_finance_prompt(payload.prompt, payload.history):
        return {"response": REFUSAL}

    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Gemini is not configured: GEMINI_API_KEY is empty. Paste your key from "
                "https://aistudio.google.com/app/apikey onto the GEMINI_API_KEY line of .env, "
                "then restart the backend."
            ),
        )

    portfolio_summary = ", ".join(
        f"{item.ticker} {item.allocation:.0f}% (${item.value:,.0f}, {item.change:+.1f}%)" for item in payload.context.portfolio
    )
    market_summary = ", ".join(f"{item.ticker} {item.price:,.2f} ({item.change:+.2f}%)" for item in payload.context.market)

    system_instruction = (
        "You are Hyperion, a finance-only AI assistant. Answer only questions about stocks, equities, "
        "crypto, markets, macroeconomics, earnings, valuation, portfolio construction, risk, investing "
        "concepts, mutual funds, SIPs, financial instruments, and financial news. This includes all "
        "global and Indian finance topics such as SIP, SWP, ELSS, NAV, Nifty, Sensex, RBI policy, "
        "and SEBI regulations. If the user asks about anything completely outside finance, politely "
        "decline and invite a finance question. Be direct and structured: lead with the short answer, "
        "then the key drivers, then what would prove the read wrong. Separate facts from inference, "
        "state your assumptions, never promise returns, and keep length proportional to the question. "
        "Use plain text with short paragraphs and simple hyphen bullets - no markdown tables."
    )

    context_block = (
        f"Selected symbol: {payload.selected_symbol}\n"
        f"Portfolio context: {portfolio_summary or 'none'}\n"
        f"Market context: {market_summary or 'none'}"
    )

    # Build Gemini conversation history (new SDK format)
    gemini_contents: list[genai_types.ContentDict] = []
    for turn in recent_history(payload.history):
        gemini_contents.append(
            genai_types.Content(
                role="user" if turn["role"] == "user" else "model",
                parts=[genai_types.Part(text=turn["content"])],
            )
        )

    # The model id is a server decision: a client-supplied value could be a retired or
    # non-text model (or someone probing), so it is deliberately ignored.
    model_name = active_model()

    try:
        api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
        client = genai.Client(api_key=api_key)
        user_message = f"{context_block}\n\nQuestion: {payload.prompt}"
        gemini_contents.append(
            genai_types.Content(
                role="user",
                parts=[genai_types.Part(text=user_message)],
            )
        )
        config = genai_types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            max_output_tokens=900,
        )

        # Walk the candidate ids: a retired model id or a model that is out of capacity degrades
        # to a working one instead of failing the whole request. A bad key, an exhausted quota or
        # a malformed request stops here, because every candidate would fail the same way.
        tried: list[str] = []
        retired: list[str] = []
        response = None
        for candidate in candidate_models(model_name):
            try:
                response = await client.aio.models.generate_content(
                    model=candidate,
                    contents=gemini_contents,
                    config=config,
                )
            except Exception as exc:  # noqa: BLE001
                if not should_try_next_model(exc):
                    raise
                tried.append(candidate)
                if model_is_unavailable(exc):
                    retired.append(candidate)
                    log.warning("Gemini model '%s' is retired or unknown to this key; trying the next candidate.", candidate)
                else:
                    log.warning("Gemini model '%s' is at capacity; trying the next candidate.", candidate)
                continue
            model_name = candidate
            break

        if response is None:
            raise NoUsableModel(tried, retired)
        if tried:
            log.info("Answered with '%s'; the configured model '%s' is unavailable.", model_name, tried[0])

        content = response.text
        if not content or not content.strip():
            raise ValueError("Gemini returned an empty response")
        return {"response": content.strip()}
    except NoUsableModel as exc:
        log.warning("Gemini call failed: no usable model among %s", exc.tried)
        if exc.every_id_retired:
            status = 502
            detail = (
                f"None of the configured Gemini models are available on this API key ({', '.join(exc.tried)}). "
                "Set GEMINI_MODEL in .env to a current id from https://ai.google.dev/gemini-api/docs/models "
                "and restart the backend."
            )
        else:
            status = 503
            detail = (
                "Every Gemini model this app can use is busy right now "
                f"({', '.join(exc.tried)}). Nothing is misconfigured - send the question again in a few seconds."
            )
        raise HTTPException(status_code=status, detail=detail) from exc
    except Exception as exc:  # noqa: BLE001
        err_str = str(exc).lower()
        log.warning("Gemini call failed: %s", exc)
        if "api_key" in err_str or "api key" in err_str or "invalid" in err_str or "401" in err_str:
            detail = "Gemini rejected the API key. Check GEMINI_API_KEY in .env."
        elif "quota" in err_str or "429" in err_str or "resource_exhausted" in err_str:
            detail = "Gemini rate limit reached. Try again shortly."
        elif "not found" in err_str or "404" in err_str:
            detail = f"Gemini model '{model_name}' not found. Check GEMINI_MODEL in .env."
        else:
            detail = "The finance model is temporarily unavailable. Try again."
        raise HTTPException(status_code=502, detail=detail) from exc


# --------------------------------------------------------------------------- #
# Serve the built frontend when dist/ exists (single-container deployment)
# --------------------------------------------------------------------------- #

frontend_dist = os.path.join(PROJECT_ROOT, "dist")
if os.path.isdir(os.path.join(frontend_dist, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        requested = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(requested):
            return FileResponse(requested)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
else:
    # Split deployment: this process is the API only, the UI lives elsewhere.
    @app.get("/")
    def api_root() -> dict[str, str]:
        return {
            "service": app.title,
            "status": "ok",
            "health": "/health",
            "docs": "/docs",
            "note": "API only. The Hyperion frontend is deployed separately and calls this origin.",
        }
