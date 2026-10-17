export type ChatContext = {
  portfolio: Array<{ ticker: string; name: string; allocation: number; value: number; change: number }>
  market: Array<{ ticker: string; price: number; change: number }>
}

export type ChatTurn = { role: 'user' | 'assistant'; content: string }

export type ChatRequest = {
  prompt: string
  selected_symbol: string
  context: ChatContext
  history: ChatTurn[]
  model?: string
}

export type NewsItem = {
  source: string
  title: string
  summary: string
  time: string
  tag: string
  tone: 'yellow' | 'blue' | 'red'
  url: string
}

export type MarketQuote = {
  ticker: string
  name: string
  price: number
  change: number
  high: number | null
  low: number | null
  prevClose: number | null
  marketCap: string
  volume: string
  source: string
}

export type MarketSnapshot = {
  asOf: string
  source: string
  live: boolean
  stocks: MarketQuote[]
  crypto: MarketQuote[]
}

/**
 * Empty string means "same origin": Vite proxies /api in development and the
 * FastAPI container serves the built frontend in production. Set VITE_API_URL
 * only when the frontend and backend live on different domains.
 */
function apiBaseUrl(): string {
  const configured = (import.meta.env.VITE_API_URL as string | undefined)?.trim()
  return configured ? configured.replace(/\/+$/, '') : ''
}

async function request<T>(path: string, init: RequestInit = {}, accessToken?: string): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${apiBaseUrl()}${path}`, {
      ...init,
      headers: {
        ...(init.headers || {}),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      },
      // Generous timeout: free-tier hosts cold-start in about a minute.
      signal: AbortSignal.timeout(90_000),
    })
  } catch (error) {
    throw new Error(
      error instanceof DOMException && error.name === 'TimeoutError'
        ? 'The finance API timed out. Check that the backend is running.'
        : 'The finance API is unreachable. Start the backend and check the API URL.',
    )
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body && typeof body.detail === 'string' ? body.detail : `Request failed with status ${response.status}`
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

export async function sendChat(requestBody: ChatRequest, accessToken?: string): Promise<string> {
  const data = await request<{ response?: string }>(
    '/api/chat',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(requestBody) },
    accessToken,
  )
  return data.response?.trim() || 'The analyst returned an empty response. Try the question again.'
}

export type NewsFeed = { items: NewsItem[]; source: string; live: boolean; asOf: string }

export async function fetchNews(accessToken?: string): Promise<NewsFeed> {
  const data = await request<Partial<NewsFeed>>('/api/news', {}, accessToken)
  return { items: data.items || [], source: data.source || 'curated', live: Boolean(data.live), asOf: data.asOf || '' }
}

export async function fetchMarket(accessToken?: string): Promise<MarketSnapshot> {
  return request<MarketSnapshot>('/api/market', {}, accessToken)
}

export type ProviderStatus = {
  gemini: boolean
  gemini_model: string
  finnhub: boolean
  alphavantage: boolean
  supabase_url: boolean
}

const EMPTY_STATUS: ProviderStatus = {
  gemini: false,
  gemini_model: '',
  finnhub: false,
  alphavantage: false,
  supabase_url: false,
}

/**
 * Public endpoint (no token needed) that reports which providers are configured,
 * so the chat page can warn about a missing model key before you type.
 */
export async function fetchHealth(): Promise<ProviderStatus | null> {
  try {
    const response = await fetch(`${apiBaseUrl()}/health`, { signal: AbortSignal.timeout(15_000) })
    if (!response.ok) return null
    const data = (await response.json()) as { providers?: Partial<ProviderStatus> }
    return { ...EMPTY_STATUS, ...(data.providers || {}) }
  } catch {
    return null
  }
}
