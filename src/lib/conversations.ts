import { supabase } from './supabase'

/**
 * Conversation persistence.
 *
 * Conversations belong to the signed-in account and live in Supabase
 * (`supabase/conversations.sql`), so they follow the user to any device. RLS
 * scopes every row to `auth.uid()`, and the `user_id` column defaults to the
 * caller, so the client never sends an owner.
 *
 * Demo mode has no account, and a project that has not run the SQL yet has no
 * tables, so both cases fall back to this browser's localStorage. The app works
 * either way; only the reach of the history changes.
 */

export type ChatRole = 'user' | 'assistant'

export type Conversation = {
  id: string
  title: string
  updatedAt: string
}

export type StoredMessage = {
  id: string
  role: ChatRole
  content: string
  createdAt: string
}

const LOCAL_KEY = 'hyperion.conversations.v1'

type LocalConversation = Conversation & { messages: StoredMessage[] }

/** 'cloud' once the tables are confirmed reachable, 'local' otherwise. */
export type StorageMode = 'cloud' | 'local' | 'unknown'
let mode: StorageMode = 'unknown'

export function storageMode(): StorageMode {
  return mode
}

export function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `id-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

/** A short, human title taken from the first thing the user asked. */
export function titleFrom(prompt: string): string {
  const clean = prompt.replace(/\s+/g, ' ').trim()
  if (!clean) return 'New conversation'
  return clean.length > 52 ? `${clean.slice(0, 49).trimEnd()}...` : clean
}

/* ------------------------------------------------------------------ local --- */

function readLocal(): LocalConversation[] {
  try {
    const raw = window.localStorage.getItem(LOCAL_KEY)
    const parsed = raw ? (JSON.parse(raw) as unknown) : []
    return Array.isArray(parsed) ? (parsed as LocalConversation[]) : []
  } catch {
    return []
  }
}

function writeLocal(rows: LocalConversation[]): void {
  try {
    window.localStorage.setItem(LOCAL_KEY, JSON.stringify(rows))
  } catch {
    /* storage full or blocked: history is a convenience, not a requirement */
  }
}

/* ------------------------------------------------------------------ cloud --- */

/**
 * Is the cloud schema actually deployed? A missing table is the expected state
 * before the SQL is run, so it is cached; anything else is treated as
 * transient and not cached, leaving room for a later call to succeed.
 */
async function cloudAvailable(): Promise<boolean> {
  if (!supabase) return false
  if (mode === 'local') return false
  if (mode === 'cloud') return true
  const { error } = await supabase.from('conversations').select('id').limit(1)
  if (!error) {
    mode = 'cloud'
    return true
  }
  const text = `${error.code ?? ''} ${error.message ?? ''}`.toLowerCase()
  if (text.includes('does not exist') || text.includes('schema cache') || text.includes('pgrst205')) {
    mode = 'local'
  }
  return false
}

/* ------------------------------------------------------------------- api --- */

export async function listConversations(): Promise<Conversation[]> {
  if (await cloudAvailable()) {
    const { data, error } = await supabase!
      .from('conversations')
      .select('id, title, updated_at')
      .order('updated_at', { ascending: false })
      .limit(60)
    if (!error) {
      return (data ?? []).map((row) => ({
        id: row.id as string,
        title: (row.title as string) || 'Untitled',
        updatedAt: row.updated_at as string,
      }))
    }
  }
  return readLocal()
    .map(({ id, title, updatedAt }) => ({ id, title, updatedAt }))
    .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
}

export async function createConversation(title: string): Promise<Conversation> {
  const now = new Date().toISOString()
  if (await cloudAvailable()) {
    const { data, error } = await supabase!.from('conversations').insert({ title }).select('id, title, updated_at').single()
    if (!error && data) {
      return { id: data.id as string, title: data.title as string, updatedAt: data.updated_at as string }
    }
    // The write reached the database and was refused (RLS, quota, network).
    // Stay on one store for this conversation rather than writing its first
    // message to the cloud and the next to this browser, which would show the
    // user a half-empty thread.
    mode = 'local'
  }
  const local: LocalConversation = { id: newId(), title, updatedAt: now, messages: [] }
  writeLocal([local, ...readLocal()])
  return { id: local.id, title: local.title, updatedAt: local.updatedAt }
}

export async function loadMessages(conversationId: string): Promise<StoredMessage[]> {
  if (await cloudAvailable()) {
    const { data, error } = await supabase!
      .from('messages')
      .select('id, role, content, created_at')
      .eq('conversation_id', conversationId)
      .order('created_at', { ascending: true })
      .limit(400)
    if (!error) {
      return (data ?? []).map((row) => ({
        id: row.id as string,
        role: row.role as ChatRole,
        content: row.content as string,
        createdAt: row.created_at as string,
      }))
    }
  }
  return readLocal().find((row) => row.id === conversationId)?.messages ?? []
}

export async function appendMessage(conversationId: string, role: ChatRole, content: string): Promise<void> {
  const now = new Date().toISOString()
  if (await cloudAvailable()) {
    const { error } = await supabase!.from('messages').insert({ conversation_id: conversationId, role, content })
    if (!error) {
      // Keep the list ordered by activity. Failure here only affects ordering.
      await supabase!.from('conversations').update({ updated_at: now }).eq('id', conversationId)
    }
    return
  }
  const rows = readLocal()
  const target = rows.find((row) => row.id === conversationId)
  if (!target) return
  target.messages.push({ id: newId(), role, content, createdAt: now })
  target.updatedAt = now
  writeLocal(rows)
}

export async function deleteConversation(conversationId: string): Promise<void> {
  if (await cloudAvailable()) {
    // Messages cascade with the conversation.
    await supabase!.from('conversations').delete().eq('id', conversationId)
    return
  }
  writeLocal(readLocal().filter((row) => row.id !== conversationId))
}

/** Wipe history for the current browser (local mode only). */
export function clearLocalConversations(): void {
  writeLocal([])
}
