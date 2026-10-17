import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  ChevronDown,
  CircleHelp,
  Cloud,
  Coins,
  ExternalLink,
  FileText,
  Globe2,
  HardDrive,
  History,
  Loader2,
  LogOut,
  Menu,
  MessageSquare,
  Newspaper,
  Plus,
  RefreshCw,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Trash2,
  TrendingUp,
  X,
  Zap,
} from 'lucide-react'
import {
  fetchHealth,
  fetchMarket,
  fetchNews,
  sendChat,
  type ChatContext,
  type ChatTurn,
  type MarketQuote,
  type MarketSnapshot,
  type NewsItem,
} from './lib/api'
import { getSession, hasSupabaseConfig, supabase } from './lib/supabase'
import {
  appendMessage,
  createConversation,
  deleteConversation as removeStoredConversation,
  listConversations,
  loadMessages,
  newId,
  storageMode,
  titleFrom,
  type Conversation,
  type StorageMode,
} from './lib/conversations'

type Page = 'chat' | 'news' | 'stocks' | 'crypto'
type Message = { id: string; role: 'user' | 'assistant'; text: string; time: string }

const seedStocks: MarketQuote[] = [
  { ticker: 'NVDA', name: 'NVIDIA', price: 143.59, change: 3.8, high: null, low: null, prevClose: null, marketCap: '3.5T', volume: '312.4M', source: 'seed' },
  { ticker: 'MSFT', name: 'MICROSOFT', price: 497.21, change: 1.2, high: null, low: null, prevClose: null, marketCap: '3.7T', volume: '18.6M', source: 'seed' },
  { ticker: 'AAPL', name: 'APPLE', price: 245.05, change: 0.64, high: null, low: null, prevClose: null, marketCap: '3.6T', volume: '28.2M', source: 'seed' },
  { ticker: 'TSLA', name: 'TESLA', price: 358.17, change: -1.9, high: null, low: null, prevClose: null, marketCap: '1.1T', volume: '94.1M', source: 'seed' },
  { ticker: 'AMZN', name: 'AMAZON', price: 227.92, change: 1.76, high: null, low: null, prevClose: null, marketCap: '2.4T', volume: '29.5M', source: 'seed' },
  { ticker: 'META', name: 'META PLATFORMS', price: 606.8, change: -0.42, high: null, low: null, prevClose: null, marketCap: '1.5T', volume: '12.8M', source: 'seed' },
]

const seedCrypto: MarketQuote[] = [
  { ticker: 'BTC', name: 'Bitcoin', price: 67240.5, change: -2.1, high: null, low: null, prevClose: null, marketCap: '', volume: '', source: 'seed' },
  { ticker: 'ETH', name: 'Ethereum', price: 2614.33, change: 1.45, high: null, low: null, prevClose: null, marketCap: '', volume: '', source: 'seed' },
  { ticker: 'SOL', name: 'Solana', price: 151.84, change: 4.82, high: null, low: null, prevClose: null, marketCap: '', volume: '', source: 'seed' },
  { ticker: 'XRP', name: 'XRP', price: 0.534, change: -0.88, high: null, low: null, prevClose: null, marketCap: '', volume: '', source: 'seed' },
  { ticker: 'BNB', name: 'BNB', price: 583.12, change: 0.39, high: null, low: null, prevClose: null, marketCap: '', volume: '', source: 'seed' },
  { ticker: 'DOGE', name: 'Dogecoin', price: 0.142, change: 2.12, high: null, low: null, prevClose: null, marketCap: '', volume: '', source: 'seed' },
]

const fallbackNews: NewsItem[] = [
  { source: 'MARKETWIRE', title: 'AI infrastructure spend keeps the tape tilted toward semiconductors', summary: 'Investors are weighing hyperscaler capex against stretched multiples as the next earnings cycle approaches.', time: '12 min ago', tag: 'TECH', tone: 'yellow', url: '' },
  { source: 'GLOBAL DESK', title: 'Dollar steadies as markets parse the next rate path', summary: 'Treasury yields and the dollar index remain the macro variables most likely to move risk assets today.', time: '28 min ago', tag: 'MACRO', tone: 'blue', url: '' },
  { source: 'CRYPTO BLOCK', title: 'Bitcoin trades heavy while liquidity waits for a catalyst', summary: 'Spot flows are mixed and volatility is compressing. The key question is whether support holds.', time: '41 min ago', tag: 'CRYPTO', tone: 'red', url: '' },
  { source: 'EARNINGS DESK', title: 'Mega-cap results are turning into a test of narrative durability', summary: 'The market is demanding revenue quality, not just ambitious guidance, from the largest names.', time: '1 hr ago', tag: 'EARNINGS', tone: 'yellow', url: '' },
]

const starters = ['Why is NVDA moving?', 'Explain the current crypto setup.', 'How should I think about portfolio concentration?']

const FINANCE_PATTERN =
  /(stock|share|equit|etf|fund|index|ipo|dividend|earnings|revenue|profit|margin|valuation|capital|crypto|bitcoin|btc|ethereum|eth\b|token|coin|blockchain|stablecoin|defi|market|nasdaq|dow jones|s&p|spx|vix|bull|bear|rally|selloff|volatil|portfolio|invest|trade|trading|broker|hedge|leverage|option|futures|allocat|diversif|risk|drawdown|bond|yield|treasury|interest rate|\bfed\b|inflation|recession|gdp|macro|monetary|fiscal|quantitative|econom|currency|forex|dollar|commodit|gold|oil|ticker|eps|merger|acquisition|buyback|nvda|msft|aapl|tsla|amzn|meta|goog|sol\b|xrp|doge|bnb|\bsip\b|\bswp\b|\bstp\b|elss|\bnps\b|\bnav\b|nifty|sensex|\bbse\b|\bnse\b|mutual fund|lumpsum|lump sum|smallcap|small cap|largecap|large cap|midcap|mid cap|index fund|\baum\b|folio|redemption|expense ratio|\bcagr\b|\bxirr\b|annuali[sz]|\bppf\b|\bepf\b|\bnsc\b|fixed deposit|recurring deposit|\bsebi\b|\bamfi\b|\brbi\b|repo rate|reverse repo|\bgilt\b|g-sec|debenture|\broe\b|\broa\b|\broce\b|\bebitda\b|\bfcf\b|grey market|intraday|swing trade|technical analysis|fundamental analysis|moving average|\brsi\b|\bmacd\b|candlestick|open interest|circuit breaker|reliance|\btcs\b|infosys|\bhdfc\b|\bicici\b|\bsbi\b|wipro|bajaj|adani|zerodha|groww)/i

const REFUSAL =
  'I am built only for finance. Ask me about a stock, crypto asset, market, portfolio, macro event, earnings report, valuation, or investing concept.'

function price(value: number) {
  const digits = Math.abs(value) < 1 ? 4 : 2
  return new Intl.NumberFormat('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits }).format(value)
}
function signed(value: number) {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}
function clockLabel(iso: string) {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const PLAIN_LANGUAGE_REQUEST =
  /(explain|break|say)\b.*(like\s+you|like\s+i|as\s+if|imagine|beginner|l layman|5\s*year\s*old|10\s*year\s*old|simple\s+terms|plain\s+english|simple\s+words|simple\s+language|in\s+simple)/i

function isFinancePrompt(userPrompt: string, recentMessages: readonly { role: string; text: string }[]): boolean {
  if (FINANCE_PATTERN.test(userPrompt)) return true

  // A plain-language explanation request ("explain that to me like you are teaching
  // a beginner") without own finance topic is allowed when the last answer in the
  // conversation already names a finance topic — that mirrors the backend guard, which
  // attaches the previous assistant answer as context before deciding.
  if (PLAIN_LANGUAGE_REQUEST.test(userPrompt)) {
    for (let i = recentMessages.length - 1; i >= 0; i--) {
      if (recentMessages[i].role === 'assistant' && FINANCE_PATTERN.test(recentMessages[i].text)) {
        return true
      }
      if (recentMessages[i].role !== 'user') continue
    }
    return false
  }

  return false
}
function nowTime() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
/** Compact age label for the conversation list. */
function relativeTime(iso: string) {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return ''
  const minutes = Math.round((Date.now() - then) / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return days < 7 ? `${days}d ago` : new Date(iso).toLocaleDateString()
}

/** Minimal inline formatter: handles **bold** so model output is not shown raw. */
function inline(text: string, keyPrefix: string): ReactNode[] {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .filter(Boolean)
    .map((chunk, index) =>
      chunk.startsWith('**') && chunk.endsWith('**')
        ? <strong key={`${keyPrefix}-${index}`}>{chunk.slice(2, -2)}</strong>
        : <span key={`${keyPrefix}-${index}`}>{chunk}</span>,
    )
}

function FormattedText({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/).map((block) => block.trim()).filter(Boolean)
  return (
    <>
      {blocks.map((block, blockIndex) => {
        const lines = block.split('\n').map((line) => line.trim()).filter(Boolean)
        const isList = lines.length > 0 && lines.every((line) => /^([-*•]|\d+\.)\s/.test(line))
        if (isList) {
          return (
            <ul className="answer-list" key={blockIndex}>
              {lines.map((line, lineIndex) => (
                <li key={lineIndex}>{inline(line.replace(/^([-*•]|\d+\.)\s+/, ''), `${blockIndex}-${lineIndex}`)}</li>
              ))}
            </ul>
          )
        }
        return (
          <p key={blockIndex}>
            {lines.map((line, lineIndex) => (
              <span key={lineIndex}>
                {inline(line, `${blockIndex}-${lineIndex}`)}
                {lineIndex < lines.length - 1 && <br />}
              </span>
            ))}
          </p>
        )
      })}
    </>
  )
}

function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(!hasSupabaseConfig)
  const [demoMode, setDemoMode] = useState(!hasSupabaseConfig)
  const [authMode, setAuthMode] = useState<'signin' | 'signup'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [authError, setAuthError] = useState('')
  const [authNotice, setAuthNotice] = useState('')
  const [page, setPage] = useState<Page>('chat')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [news, setNews] = useState(fallbackNews)
  const [newsSource, setNewsSource] = useState('curated')
  const [snapshot, setSnapshot] = useState<MarketSnapshot | null>(null)
  const [selectedSymbol, setSelectedSymbol] = useState('SPX')
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [chatReady, setChatReady] = useState<boolean | null>(null)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [isLoadingConversation, setIsLoadingConversation] = useState(false)
  const [storage, setStorage] = useState<StorageMode>('unknown')
  const [mobileNav, setMobileNav] = useState(false)
  const [showDisclaimer, setShowDisclaimer] = useState(false)
  const chatScrollRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!supabase) return
    getSession().then((current) => {
      setSession(current)
      setReady(true)
    })
    const { data } = supabase.auth.onAuthStateChange((_event, current) => setSession(current))
    return () => data.subscription.unsubscribe()
  }, [])

  useEffect(() => {
    let active = true
    fetchMarket(session?.access_token)
      .then((data) => {
        if (active) setSnapshot(data)
      })
      .catch(() => {
        /* keep the seeded snapshot so the pages stay readable offline */
      })
    return () => {
      active = false
    }
  }, [session])

  useEffect(() => {
    let active = true
    fetchHealth().then((health) => {
      if (!active || !health) return
      setChatReady(health.gemini)
    })
    return () => {
      active = false
    }
  }, [session])

  useEffect(() => {
    chatScrollRef.current?.scrollTo({ top: chatScrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, isSending])

  // Start a fresh, empty conversation whenever the identity changes, including
  // on sign-out, so one account never inherits another account's questions, and
  // load the history that belongs to the new identity.
  const userId = session?.user.id ?? null
  const identityKey = userId ?? (demoMode ? 'demo' : 'signed-out')
  useEffect(() => {
    let active = true
    setMessages([])
    setInput('')
    setPage('chat')
    setSelectedSymbol('SPX')
    setShowDisclaimer(false)
    setActiveConversationId(null)
    setConversations([])
    void (async () => {
      const rows = await listConversations()
      if (!active) return
      setConversations(rows)
      setStorage(storageMode())
    })()
    return () => {
      active = false
    }
  }, [identityKey])

  const stocks = snapshot?.stocks?.length ? snapshot.stocks : seedStocks
  const crypto = snapshot?.crypto?.length ? snapshot.crypto : seedCrypto
  const marketLive = Boolean(snapshot?.live)
  const marketStamp = snapshot ? clockLabel(snapshot.asOf) : '—'

  const displayName = session?.user.email?.split('@')[0] || 'Demo desk'
  const initials = (session?.user.email || 'demo').slice(0, 2).toUpperCase()

  const marketContext = useMemo<ChatContext['market']>(
    () =>
      [...stocks.slice(0, 5), ...crypto.slice(0, 3)].map((quote) => ({
        ticker: quote.ticker,
        price: quote.price,
        change: quote.change,
      })),
    [stocks, crypto],
  )

  function pushMessage(message: Omit<Message, 'id' | 'time'> & { id?: string; time?: string }) {
    setMessages((current) => [
      ...current,
      { id: message.id ?? newId(), time: message.time ?? nowTime(), role: message.role, text: message.text },
    ])
  }

  async function auth(event: FormEvent) {
    event.preventDefault()
    setAuthError('')
    setAuthNotice('')
    if (!supabase) return
    const result =
      authMode === 'signin'
        ? await supabase.auth.signInWithPassword({ email, password })
        : await supabase.auth.signUp({ email, password })
    if (result.error) {
      setAuthError(result.error.message)
      return
    }
    if (authMode === 'signup' && !result.data.session) {
      setAuthNotice('Account created. Confirm the email address we just sent you, then sign in.')
    }
  }

  async function signOut() {
    if (supabase) await supabase.auth.signOut()
    setSession(null)
    // Leave demo mode on the way out, otherwise the app keeps rendering the
    // workspace instead of the sign-in screen the user asked for.
    setDemoMode(false)
    setMobileNav(false)
    setInput('')
    setMessages([])
    setConversations([])
    setActiveConversationId(null)
  }

  async function refreshNews() {
    setIsRefreshing(true)
    try {
      const payload = await fetchNews(session?.access_token)
      if (payload.items.length) {
        setNews(payload.items)
        setNewsSource(payload.source)
      }
    } catch {
      /* keep the curated fallback feed */
    } finally {
      setIsRefreshing(false)
    }
  }

  useEffect(() => {
    void refreshNews()
    const timer = window.setInterval(() => void refreshNews(), 300_000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session])

  async function refreshMarket() {
    setIsRefreshing(true)
    try {
      setSnapshot(await fetchMarket(session?.access_token))
    } catch {
      /* keep showing the last snapshot */
    } finally {
      setIsRefreshing(false)
    }
  }

  function sendMessage(event?: FormEvent, suggested?: string) {
    event?.preventDefault()
    void deliver(suggested)
  }

  /** Move a conversation to the top of the list and refresh its age. */
  function touchConversation(conversationId: string) {
    const now = new Date().toISOString()
    setConversations((current) =>
      current
        .map((item) => (item.id === conversationId ? { ...item, updatedAt: now } : item))
        .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
    )
  }

  /**
   * Create the conversation the first time the user actually says something, so
   * opening the page and never typing does not leave empty rows in the history.
   */
  async function ensureConversation(prompt: string): Promise<string | null> {
    if (activeConversationId) return activeConversationId
    try {
      const created = await createConversation(titleFrom(prompt))
      setActiveConversationId(created.id)
      setConversations((current) => [created, ...current])
      setStorage(storageMode())
      return created.id
    } catch {
      return null
    }
  }

  function startNewConversation() {
    setActiveConversationId(null)
    setMessages([])
    setInput('')
    setPage('chat')
    setMobileNav(false)
  }

  async function openConversation(conversationId: string) {
    setPage('chat')
    setMobileNav(false)
    setIsLoadingConversation(true)
    try {
      const rows = await loadMessages(conversationId)
      setMessages(rows.map((row) => ({ id: row.id, role: row.role, text: row.content, time: clockLabel(row.createdAt) })))
      setActiveConversationId(conversationId)
    } finally {
      setIsLoadingConversation(false)
    }
  }

  async function removeConversation(conversationId: string) {
    await removeStoredConversation(conversationId)
    setConversations((current) => current.filter((item) => item.id !== conversationId))
    if (conversationId === activeConversationId) startNewConversation()
  }

  async function deliver(suggested?: string) {
    const prompt = (suggested ?? input).trim()
    if (!prompt || isSending) return
    const history: ChatTurn[] = messages.slice(-10).map((message) => ({ role: message.role, content: message.text }))

    pushMessage({ role: 'user', text: prompt })
    setInput('')
    setIsSending(true)

    const conversationId = await ensureConversation(prompt)
    if (conversationId) {
      void appendMessage(conversationId, 'user', prompt)
      touchConversation(conversationId)
    }

    if (!isFinancePrompt(prompt, messages)) {
      pushMessage({ role: 'assistant', text: REFUSAL })
      if (conversationId) void appendMessage(conversationId, 'assistant', REFUSAL)
      setIsSending(false)
      return
    }

    try {
      const response = await sendChat(
        // Only real, live market data is sent as context; nothing fabricated.
        { prompt, selected_symbol: selectedSymbol, context: { portfolio: [], market: marketContext }, history },
        session?.access_token,
      )
      pushMessage({ role: 'assistant', text: response })
      if (conversationId) {
        void appendMessage(conversationId, 'assistant', response)
        touchConversation(conversationId)
      }
    } catch (error) {
      const detail = error instanceof Error ? error.message : 'Unknown error'
      const failure =
        `I could not reach the finance model.\n\n- Reason: ${detail}\n` +
        `- Check: the backend is running, GEMINI_API_KEY is set, and ${demoMode ? 'ALLOW_DEMO_AUTH is true or you are signed in' : 'your session is still valid'}.\n` +
        `- Meanwhile: the Stocks, Crypto and Live News pages keep working with live provider data.`
      pushMessage({ role: 'assistant', text: failure })
      if (conversationId) void appendMessage(conversationId, 'assistant', failure)
    } finally {
      setIsSending(false)
    }
  }

  function askAbout(symbol: string, template: (symbol: string) => string) {
    setSelectedSymbol(symbol)
    setPage('chat')
    void deliver(template(symbol))
  }

  if (!ready) {
    return (
      <div className="loading-screen">
        <Loader2 className="spin" size={28} />
        <span>RESTORING SESSION...</span>
      </div>
    )
  }

  if (hasSupabaseConfig && !session && !demoMode) {
    return (
      <AuthScreen
        email={email}
        password={password}
        setEmail={setEmail}
        setPassword={setPassword}
        authMode={authMode}
        setAuthMode={(mode) => {
          setAuthMode(mode)
          setAuthError('')
          setAuthNotice('')
        }}
        authError={authError}
        authNotice={authNotice}
        onSubmit={auth}
        onDemo={() => setDemoMode(true)}
      />
    )
  }

  const nav = [
    { id: 'chat' as Page, label: 'Finance Chat', icon: MessageSquare },
    { id: 'news' as Page, label: 'Live News', icon: Newspaper },
    { id: 'stocks' as Page, label: 'Stocks', icon: TrendingUp },
    { id: 'crypto' as Page, label: 'Crypto Market', icon: Coins },
  ]

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
        <div className="brand-lockup">
          <img className="brand-logo" src="/hyperion-logo.png" alt="Hyperion" width={1928} height={514} />
          <div className="wordmark-sub">FINANCE ONLY / 01</div>
        </div>
        <div className="sidebar-status">
          <span className={marketLive ? 'status-dot' : 'status-dot offline'} />
          {marketLive ? 'LIVE MARKET FEED' : 'SEEDED SNAPSHOT'} <span className="mono">{marketStamp}</span>
        </div>
        <div className="nav-label">PRODUCT</div>
        <nav className="primary-nav">
          {nav.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              className={`nav-item ${page === id ? 'active' : ''}`}
              onClick={() => {
                setPage(id)
                setMobileNav(false)
              }}
            >
              <Icon size={17} strokeWidth={2.5} />
              <span>{label}</span>
              {id === 'news' && <span className="nav-count">LIVE</span>}
            </button>
          ))}
        </nav>
        <div className="nav-label">LATEST HEADLINE</div>
        {news[0] ? (
          <div className="headline-card">
            <div className="headline-meta">
              <span className={newsSource !== 'curated' ? 'status-dot' : 'status-dot offline'} />
              <span>{news[0].source}</span>
              <b className="dot-sep">·</b>
              <span>{news[0].time}</span>
            </div>
            <h4>{news[0].title}</h4>
            <p>{news[0].summary}</p>
            <button
              className="headline-ask"
              onClick={() =>
                askAbout(selectedSymbol, () => `Explain the finance implications of this headline: ${news[0].title}`)
              }
            >
              ASK HYPERION <ArrowUpRight size={13} />
            </button>
          </div>
        ) : (
          <div className="headline-card headline-empty">
            <p>No headline available yet. Refresh the Live News page to pull the feed.</p>
          </div>
        )}
        <div className="sidebar-bottom">
          <button className="nav-item" onClick={() => setShowDisclaimer(true)}>
            <CircleHelp size={17} />
            <span>Finance scope</span>
          </button>
          <button className="nav-item" onClick={() => void signOut()}>
            <LogOut size={17} />
            <span>Sign out</span>
          </button>
          <div className="user-block">
            <div className="avatar">{initials}</div>
            <div>
              <strong>{displayName}</strong>
              <span>{demoMode ? 'demo session' : 'authenticated'}</span>
            </div>
            <ChevronDown size={16} />
          </div>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setMobileNav(!mobileNav)} aria-label="Toggle navigation">
            <Menu size={21} />
          </button>
          <div className="breadcrumbs">
            <span>HYPERION</span>
            <b>/</b>
            <strong>{nav.find((item) => item.id === page)?.label.toUpperCase()}</strong>
          </div>
          <div className="topbar-actions">
            <div className="global-search">
              <Search size={16} />
              <span>Ask Hyperion about any symbol...</span>
              <kbd>
                <CommandIcon /> K
              </kbd>
            </div>
            <button className="top-avatar" onClick={() => setPage('chat')}>
              {initials}
            </button>
          </div>
        </header>

        <div className="content-wrap">
          {page === 'chat' && (
            <ChatPage
              messages={messages}
              input={input}
              setInput={setInput}
              isSending={isSending}
              isLoadingConversation={isLoadingConversation}
              onSend={sendMessage}
              scrollRef={chatScrollRef}
              selectedSymbol={selectedSymbol}
              marketLive={marketLive}
              marketStamp={marketStamp}
              chatReady={chatReady}
              conversations={conversations}
              activeConversationId={activeConversationId}
              storage={storage}
              onNewConversation={startNewConversation}
              onOpenConversation={(id) => void openConversation(id)}
              onDeleteConversation={(id) => void removeConversation(id)}
            />
          )}
          {page === 'news' && (
            <NewsPage
              news={news}
              source={newsSource}
              isRefreshing={isRefreshing}
              onRefresh={() => void refreshNews()}
              onAsk={(title) => askAbout(selectedSymbol, () => `Explain the finance implications of this headline: ${title}`)}
            />
          )}
          {page === 'stocks' && (
            <StocksPage
              rows={stocks}
              live={marketLive}
              stamp={marketStamp}
              isRefreshing={isRefreshing}
              onRefresh={() => void refreshMarket()}
              onAsk={(ticker) => askAbout(ticker, (symbol) => `Give me a balanced finance brief on ${symbol}.`)}
            />
          )}
          {page === 'crypto' && (
            <CryptoPage
              rows={crypto}
              live={marketLive}
              stamp={marketStamp}
              isRefreshing={isRefreshing}
              onRefresh={() => void refreshMarket()}
              onAsk={(ticker) => askAbout(ticker, (symbol) => `Explain the current setup and risks for ${symbol}.`)}
            />
          )}
        </div>

        <footer className="app-footer">
          <span>HYPERION / FINANCE-ONLY WORKSPACE</span>
          <span className="footer-center">
            {marketLive ? 'LIVE PROVIDER DATA' : 'DELAYED SNAPSHOT'} <i className={marketLive ? 'status-dot' : 'status-dot offline'} />
          </span>
          <span>
            <button onClick={() => setShowDisclaimer(true)}>RISK &amp; DATA NOTE</button> <span className="footer-separator">/</span> v1.0.0
          </span>
        </footer>
      </main>

      {showDisclaimer && (
        <div className="modal-backdrop" onClick={() => setShowDisclaimer(false)}>
          <div className="disclaimer-modal" onClick={(event) => event.stopPropagation()}>
            <button className="modal-close" onClick={() => setShowDisclaimer(false)}>
              <X size={18} />
            </button>
            <div className="card-kicker">
              <ShieldCheck size={16} /> HYPERION SCOPE
            </div>
            <h2>
              Finance in.
              <br />
              <mark>Everything else out.</mark>
            </h2>
            <p>
              Hyperion answers finance-related questions only. Market data comes from third-party providers and AI analysis can be wrong. This
              is educational information, not investment advice. Verify sources before acting.
            </p>
            <button className="dark-button" onClick={() => setShowDisclaimer(false)}>
              GOT IT <ArrowUpRight size={15} />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function CommandIcon() {
  return <span className="command-icon">⌘</span>
}

function PageIntro({ eyebrow, title, description, action }: { eyebrow: string; title: ReactNode; description: string; action?: ReactNode }) {
  return (
    <div className="page-intro">
      <div>
        <div className="eyebrow">
          <span className="live-pip" /> {eyebrow}
        </div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  )
}

function DataBadge({ live, stamp, suffix }: { live: boolean; stamp: string; suffix?: string }) {
  return (
    <span className="data-badge">
      <span className={live ? 'status-dot' : 'status-dot offline'} /> {live ? 'LIVE' : 'SEEDED'} · AS OF {stamp}
      {suffix ? ` · ${suffix}` : ''}
    </span>
  )
}

function ChatPage({
  messages,
  input,
  setInput,
  isSending,
  isLoadingConversation,
  onSend,
  scrollRef,
  selectedSymbol,
  marketLive,
  marketStamp,
  chatReady,
  conversations,
  activeConversationId,
  storage,
  onNewConversation,
  onOpenConversation,
  onDeleteConversation,
}: {
  messages: Message[]
  input: string
  setInput: (value: string) => void
  isSending: boolean
  isLoadingConversation: boolean
  onSend: (event?: FormEvent, suggested?: string) => void
  scrollRef: React.RefObject<HTMLDivElement | null>
  selectedSymbol: string
  marketLive: boolean
  marketStamp: string
  chatReady: boolean | null
  conversations: Conversation[]
  activeConversationId: string | null
  storage: StorageMode
  onNewConversation: () => void
  onOpenConversation: (id: string) => void
  onDeleteConversation: (id: string) => void
}) {
  return (
    <>
      <PageIntro
        eyebrow="01 / FINANCE-ONLY ASSISTANT"
        title={
          <>
            Ask the <mark>market.</mark>
          </>
        }
        description="A focused chatbot for stocks, crypto, macro, earnings, valuation, and portfolio risk. No generic life advice. No off-topic drift."
      />
      <div className="chat-layout">
        <aside className="conversation-rail">
          <button className="new-chat-button" onClick={onNewConversation}>
            <Plus size={15} /> NEW CHAT
          </button>
          <div className="rail-heading">
            <History size={13} /> HISTORY
          </div>
          <div className={`storage-note ${storage === 'cloud' ? 'cloud' : 'local'}`}>
            {storage === 'cloud' ? <Cloud size={11} /> : <HardDrive size={11} />}
            {storage === 'cloud' ? 'SYNCED TO YOUR ACCOUNT' : 'SAVED IN THIS BROWSER'}
          </div>
          <div className="conversation-list">
            {conversations.length === 0 ? (
              <p className="rail-empty">No saved conversations yet. Ask a question and it will appear here.</p>
            ) : (
              conversations.map((item) => (
                <div key={item.id} className={`conversation-item ${item.id === activeConversationId ? 'active' : ''}`}>
                  <button className="conversation-open" onClick={() => onOpenConversation(item.id)}>
                    <strong>{item.title}</strong>
                    <span>{relativeTime(item.updatedAt)}</span>
                  </button>
                  <button
                    className="conversation-delete"
                    onClick={() => onDeleteConversation(item.id)}
                    aria-label={`Delete conversation: ${item.title}`}
                    title="Delete conversation"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>
        <section className="chat-panel standalone-chat">
          <div className="chat-header">
            <div>
              <div className="eyebrow">
                <span className="live-pip" /> HYPERION CO-PILOT
              </div>
              <h2>Finance, clearly.</h2>
            </div>
          </div>
          <div className="scope-strip">
            <ShieldCheck size={15} />
            <strong>Finance scope:</strong>
            <span>stocks · crypto · markets · macro · portfolio · investing concepts</span>
          </div>
          {chatReady === false && (
            <div className="config-warning">
              <AlertTriangle size={16} />
              <div>
                <strong>CHAT NEEDS A GEMINI KEY</strong>
                The backend is running and answering, but <code>GEMINI_API_KEY</code> is empty, so questions cannot be
                completed yet. Paste your key onto the <code>GEMINI_API_KEY</code> line of <code>.env</code> for a local
                run, or add it as a Render environment variable when deployed, then restart the backend. Live News, Stocks and
                Crypto already work.
              </div>
            </div>
          )}
          <div className="message-scroll" ref={scrollRef}>
            {isLoadingConversation && (
              <div className="chat-empty">
                <span className="empty-mark">
                  <Loader2 className="spin" size={18} />
                </span>
                <h3>Opening conversation...</h3>
              </div>
            )}
            {messages.length === 0 && !isLoadingConversation && (
              <div className="chat-empty">
                <span className="empty-mark">
                  <Sparkles size={18} />
                </span>
                <h3>New conversation.</h3>
                <p>
                  Ask about a ticker, a macro print, an earnings report, a valuation, or a position. Hyperion stays inside
                  finance and labels its assumptions.
                </p>
              </div>
            )}
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            {isSending && (
              <div className="message assistant">
                <div className="message-avatar bot-avatar">
                  <Sparkles size={15} />
                </div>
                <div className="message-body">
                  <div className="message-meta">
                    <strong>HYPERION</strong>
                    <span>THINKING...</span>
                  </div>
                  <div className="typing">
                    <i />
                    <i />
                    <i />
                  </div>
                </div>
              </div>
            )}
          </div>
          {messages.length === 0 && (
            <div className="starter-prompts">
              {starters.map((prompt) => (
                <button key={prompt} onClick={() => onSend(undefined, prompt)}>
                  {prompt}
                  <ArrowUpRight size={13} />
                </button>
              ))}
            </div>
          )}
          <form className="composer" onSubmit={onSend}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="Ask a finance question..."
              rows={1}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  onSend()
                }
              }}
            />
            <span className="composer-hint">
              SHIFT + ENTER
              <br />
              NEW LINE
            </span>
            <button className="send-button" type="submit" disabled={!input.trim() || isSending}>
              <Send size={18} />
            </button>
          </form>
          <div className="risk-note">
            <ShieldCheck size={13} /> EDUCATIONAL ONLY — NOT INVESTMENT ADVICE. VERIFY DATA BEFORE YOU ACT.
          </div>
        </section>

        <aside className="chat-side-stack">
          <div className="rail-card yellow-card">
            <div className="card-kicker">
              <Zap size={15} /> HOW TO USE HYPERION
            </div>
            <h3>
              BRING A<br />
              TICKER.
            </h3>
            <p>Ask “why”, “what changed”, “what can break”, or “compare” to get a structured finance read.</p>
          </div>
          <div className="rail-card watch-card">
            <div className="card-kicker">
              <Activity size={15} /> CONTEXT SENT
            </div>
            <div className="pulse-number">
              {selectedSymbol}
              <span>{marketLive ? '' : '?'}</span>
            </div>
            <p>
              Focus symbol for your next question. Live market context as of {marketStamp} from {marketLive ? 'your provider feed' : 'the built-in snapshot'}.
            </p>
            <div className="chip-row">
              <span className="context-chip">{marketLive ? 'LIVE DATA' : 'SEEDED DATA'}</span>
              <span className="context-chip">MARKET-ONLY CONTEXT</span>
            </div>
          </div>
        </aside>
      </div>
    </>
  )
}

function NewsPage({
  news,
  source,
  isRefreshing,
  onRefresh,
  onAsk,
}: {
  news: NewsItem[]
  source: string
  isRefreshing: boolean
  onRefresh: () => void
  onAsk: (title: string) => void
}) {
  const live = source !== 'curated'
  return (
    <>
      <PageIntro
        eyebrow="02 / LIVE FINANCE NEWS"
        title={
          <>
            The tape,
            <br />
            <mark>in context.</mark>
          </>
        }
        description="Market-moving headlines across equities, macro, earnings and digital assets. Refreshed automatically every five minutes."
        action={
          <button className="dark-button page-action" onClick={onRefresh}>
            <RefreshCw size={15} className={isRefreshing ? 'spin' : ''} /> REFRESH FEED
          </button>
        }
      />
      <div className="news-layout">
        <section className="news-feed">
          <div className="feed-toolbar">
            <span>
              <span className={live ? 'status-dot' : 'status-dot offline'} /> {live ? 'LIVE FEED' : 'CURATED FALLBACK'}
            </span>
            <span>{source === 'alphavantage' ? 'Alpha Vantage' : source === 'finnhub' ? 'Finnhub' : 'Built-in'} · newest first</span>
          </div>
          {news.map((item) => (
            <article className="news-card" key={`${item.title}-${item.time}`}>
              <div className={`news-tag ${item.tone}`}>{item.tag}</div>
              <div className="news-main">
                <div className="news-meta">
                  <span>{item.source}</span>
                  <b>·</b>
                  <span>{item.time}</span>
                </div>
                <h2>{item.title}</h2>
                <p>{item.summary}</p>
                <div className="news-actions">
                  <button className="text-action" onClick={() => onAsk(item.title)}>
                    ASK HYPERION <ArrowUpRight size={14} />
                  </button>
                  {item.url && (
                    <a className="text-action news-link" href={item.url} target="_blank" rel="noreferrer noopener">
                      SOURCE <ExternalLink size={13} />
                    </a>
                  )}
                </div>
              </div>
            </article>
          ))}
        </section>
        <aside className="news-aside">
          <div className="rail-card blue-card">
            <div className="card-kicker">
              <Globe2 size={15} /> NEWS NOTE
            </div>
            <h3>
              HEADLINES
              <br />
              ARE NOT
              <br />
              THESIS.
            </h3>
            <p>Use the feed to find a question. Then ask Hyperion to separate signal from narrative.</p>
          </div>
          <div className="rail-card checklist-card">
            <div className="card-kicker">
              <FileText size={15} /> FEED COVERAGE
            </div>
            <Check text="Market moving" active />
            <Check text="Macro" active />
            <Check text="Earnings" active />
            <Check text="Crypto" active />
            <p className="feed-foot">
              Filtering happens on the server: generic lifestyle items are dropped before they reach this feed.
            </p>
          </div>
        </aside>
      </div>
    </>
  )
}

function StocksPage({
  rows,
  live,
  stamp,
  isRefreshing,
  onRefresh,
  onAsk,
}: {
  rows: MarketQuote[]
  live: boolean
  stamp: string
  isRefreshing: boolean
  onRefresh: () => void
  onAsk: (ticker: string) => void
}) {
  return (
    <>
      <PageIntro
        eyebrow="03 / EQUITIES"
        title={
          <>
            Stocks,
            <br />
            <mark>without noise.</mark>
          </>
        }
        description="Live quotes for major names. Spot the daily move, then jump straight into a finance-only analysis."
        action={
          <div className="intro-actions">
            <DataBadge live={live} stamp={stamp} />
            <button className="dark-button page-action" onClick={onRefresh}>
              <RefreshCw size={15} className={isRefreshing ? 'spin' : ''} /> REFRESH
            </button>
          </div>
        }
      />
      <MarketSummary rows={rows} label="TOTAL MARKET" />
      <div className="asset-table-wrap">
        <div className="asset-table-head">
          <span>NAME</span>
          <span>PRICE</span>
          <span>DAY</span>
          <span>MARKET CAP</span>
          <span>AVG VOLUME</span>
          <span>RANGE (DAY)</span>
          <span />
        </div>
        {rows.map((item) => (
          <div className="asset-row" key={item.ticker}>
            <div className="asset-name">
              <span className="asset-logo">{item.ticker.slice(0, 1)}</span>
              <div>
                <strong>{item.ticker}</strong>
                <span>{item.name}</span>
              </div>
            </div>
            <strong className="mono">${price(item.price)}</strong>
            <span className={`change ${item.change < 0 ? 'negative' : ''}`}>{signed(item.change)}</span>
            <span className="mono table-muted">{item.marketCap || '—'}</span>
            <span className="mono table-muted">{item.volume || '—'}</span>
            <span className="mono table-muted">
              {item.low && item.high ? `${price(item.low)} – ${price(item.high)}` : '—'}
            </span>
            <button className="ask-button" onClick={() => onAsk(item.ticker)}>
              ASK <ArrowUpRight size={13} />
            </button>
          </div>
        ))}
      </div>
    </>
  )
}

function CryptoPage({
  rows,
  live,
  stamp,
  isRefreshing,
  onRefresh,
  onAsk,
}: {
  rows: MarketQuote[]
  live: boolean
  stamp: string
  isRefreshing: boolean
  onRefresh: () => void
  onAsk: (ticker: string) => void
}) {
  return (
    <>
      <PageIntro
        eyebrow="04 / DIGITAL ASSETS"
        title={
          <>
            Crypto,
            <br />
            <mark>with guardrails.</mark>
          </>
        }
        description="Live digital-asset quotes with volatility visible, not hidden behind soft language."
        action={
          <div className="intro-actions">
            <DataBadge live={live} stamp={stamp} suffix="24/7" />
            <button className="dark-button page-action" onClick={onRefresh}>
              <RefreshCw size={15} className={isRefreshing ? 'spin' : ''} /> REFRESH
            </button>
          </div>
        }
      />
      <MarketSummary rows={rows} label="DIGITAL ASSETS" />
      <div className="crypto-grid">
        {rows.map((coin) => (
          <article className="crypto-card" key={coin.ticker}>
            <div className="crypto-top">
              <span className="asset-logo blue-logo">{coin.ticker.slice(0, 1)}</span>
              <div>
                <strong>{coin.ticker}</strong>
                <span>{coin.name}</span>
              </div>
              <button onClick={() => onAsk(coin.ticker)} aria-label={`Ask Hyperion about ${coin.ticker}`}>
                <ArrowUpRight size={15} />
              </button>
            </div>
            <div className="crypto-price">${price(coin.price)}</div>
            <div className="crypto-change">
              <span className={coin.change < 0 ? 'negative' : 'positive'}>{signed(coin.change)}</span>
              <span>24H</span>
            </div>
            <div className="crypto-line">
              <span style={{ width: `${Math.min(90, Math.max(14, 50 + coin.change * 7))}%` }} />
            </div>
            <div className="crypto-foot">
              <span>24H LOW {coin.low ? price(coin.low) : '—'}</span>
              <span>24H HIGH {coin.high ? price(coin.high) : '—'}</span>
            </div>
          </article>
        ))}
      </div>
    </>
  )
}

function MarketSummary({ rows, label }: { rows: MarketQuote[]; label: string }) {
  const advancing = rows.filter((row) => row.change > 0).length
  const average = rows.length ? rows.reduce((sum, row) => sum + row.change, 0) / rows.length : 0
  const top = rows.reduce<MarketQuote | null>((best, row) => (!best || Math.abs(row.change) > Math.abs(best.change) ? row : best), null)
  return (
    <div className="market-summary">
      <SummaryMetric label={label} value={`${rows.length} tracked`} change={`${advancing} advancing`} />
      <SummaryMetric label="TOP MOVER" value={top ? top.ticker : '—'} change={top ? signed(top.change) : '—'} />
      <SummaryMetric label="AVERAGE MOVE" value={signed(average)} change={average < 0 ? 'RISK OFF' : average > 0.5 ? 'RISK ON' : 'FLAT'} />
    </div>
  )
}

function SummaryMetric({ label, value, change }: { label: string; value: string; change: string }) {
  return (
    <div className="summary-metric">
      <span>{label}</span>
      <strong>{value}</strong>
      <small className={change.startsWith('-') ? 'negative' : 'positive'}>{change}</small>
    </div>
  )
}

function Check({ text, active }: { text: string; active?: boolean }) {
  return (
    <div className={`check-item ${active ? 'done' : ''}`}>
      <span>{active ? '✓' : ''}</span>
      {text}
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  return (
    <div className={`message ${message.role}`}>
      <div className={`message-avatar ${message.role === 'assistant' ? 'bot-avatar' : 'user-avatar'}`}>
        {message.role === 'assistant' ? <Sparkles size={15} /> : 'YOU'}
      </div>
      <div className="message-body">
        <div className="message-meta">
          <strong>{message.role === 'assistant' ? 'HYPERION' : 'YOU'}</strong>
          <span>{message.time}</span>
        </div>
        <div className="message-text">
          {message.role === 'assistant' ? <FormattedText text={message.text} /> : message.text}
        </div>
      </div>
    </div>
  )
}

function AuthScreen({
  email,
  password,
  setEmail,
  setPassword,
  authMode,
  setAuthMode,
  authError,
  authNotice,
  onSubmit,
  onDemo,
}: {
  email: string
  password: string
  setEmail: (value: string) => void
  setPassword: (value: string) => void
  authMode: 'signin' | 'signup'
  setAuthMode: (mode: 'signin' | 'signup') => void
  authError: string
  authNotice: string
  onSubmit: (event: FormEvent) => void
  onDemo: () => void
}) {
  return (
    <div className="auth-screen">
      <div className="auth-side">
        <div className="brand-lockup">
          <img className="brand-logo" src="/hyperion-logo-light.png" alt="Hyperion" width={1928} height={514} />
          <div className="wordmark-sub">FINANCE ONLY / 01</div>
        </div>
        <div className="auth-manifesto">
          <span>
            THE
            <br />
            MARKET
            <br />
            <mark>IS LOUD.</mark>
          </span>
          <strong>
            YOUR READ
            <br />
            DOESN'T HAVE
            <br />
            TO BE.
          </strong>
        </div>
      </div>
      <div className="auth-card-wrap">
        <div className="auth-card">
          <div className="eyebrow">
            <span className="live-pip" /> SECURE FINANCE ACCESS
          </div>
          <h1>{authMode === 'signin' ? 'Back to the desk.' : 'Open your desk.'}</h1>
          <p>One focused space for finance questions, news, and market context.</p>
          <form onSubmit={onSubmit}>
            <label>
              EMAIL
              <input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@domain.com" required />
            </label>
            <label>
              PASSWORD
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="••••••••"
                minLength={6}
                required
              />
            </label>
            {authError && <div className="form-error">{authError}</div>}
            {authNotice && <div className="form-notice">{authNotice}</div>}
            <button className="dark-button auth-button" type="submit">
              {authMode === 'signin' ? 'SIGN IN' : 'CREATE ACCOUNT'} <ArrowUpRight size={16} />
            </button>
          </form>
          <div className="auth-switch">
            <span>{authMode === 'signin' ? 'New here?' : 'Already have access?'}</span>
            <button onClick={() => setAuthMode(authMode === 'signin' ? 'signup' : 'signin')}>
              {authMode === 'signin' ? 'Create an account' : 'Sign in instead'}
            </button>
          </div>
          <div className="or-divider">
            <span>OR</span>
          </div>
          <button className="demo-button" onClick={onDemo}>
            ENTER DEMO MODE <Zap size={15} />
          </button>
          <div className="auth-footnote">
            <AlertTriangle size={13} /> Demo mode needs ALLOW_DEMO_AUTH=true on the backend.
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
