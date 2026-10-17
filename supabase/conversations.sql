-- Hyperion — per-user conversation history
--
-- Run this ONCE in the Supabase dashboard:
--   SQL Editor -> New query -> paste this whole file -> Run.
--
-- It creates two tables and locks them down with row level security, so a
-- signed-in user can only ever read or write their own rows. The client never
-- sends a user id: `user_id` defaults to auth.uid() and the policy enforces it.
--
-- Until this has been run, the app keeps conversations in the browser instead
-- and tells you so on the chat page. Reload after running it.

-- ------------------------------------------------------------------ tables --

create table if not exists public.conversations (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null default auth.uid() references auth.users (id) on delete cascade,
  title      text not null default 'New conversation',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.messages (
  id              uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversations (id) on delete cascade,
  user_id         uuid not null default auth.uid() references auth.users (id) on delete cascade,
  role            text not null check (role in ('user', 'assistant')),
  content         text not null,
  created_at      timestamptz not null default now()
);

-- ----------------------------------------------------------------- indexes --

-- The sidebar lists a user's conversations, newest activity first.
create index if not exists conversations_user_updated_idx
  on public.conversations (user_id, updated_at desc);

-- Opening a conversation replays its messages in order.
create index if not exists messages_conversation_created_idx
  on public.messages (conversation_id, created_at);

-- -------------------------------------------------------------------- rls --

alter table public.conversations enable row level security;
alter table public.messages enable row level security;

-- RLS decides which rows are visible; grants decide whether the role may touch
-- the table at all. Both are required.
grant select, insert, update, delete on public.conversations to authenticated;
grant select, insert, update, delete on public.messages to authenticated;

drop policy if exists "own conversations" on public.conversations;
create policy "own conversations" on public.conversations
  for all
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

drop policy if exists "own messages" on public.messages;
create policy "own messages" on public.messages
  for all
  to authenticated
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);
