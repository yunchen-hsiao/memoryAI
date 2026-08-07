-- Run once in the Supabase SQL Editor for an existing deployment.
-- This table intentionally stores preference signals only; it does not retain
-- chat messages, model responses, source snippets, or decrypted diary content.

create table if not exists public.chat_response_feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  feedback_type text not null check (
    feedback_type in ('liked', 'too_neutral', 'too_speculative', 'wrong_memory')
  ),
  response_mode text not null check (
    response_mode in ('companion', 'analysis', 'strategy', 'memory')
  ),
  created_at timestamp with time zone default timezone('utc'::text, now())
);

create index if not exists chat_response_feedback_user_created_idx
  on public.chat_response_feedback (user_id, created_at desc);

alter table public.chat_response_feedback enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'chat_response_feedback'
      and policyname = 'chat_response_feedback_select_own'
  ) then
    create policy "chat_response_feedback_select_own" on public.chat_response_feedback
      for select using (auth.uid() = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'chat_response_feedback'
      and policyname = 'chat_response_feedback_insert_own'
  ) then
    create policy "chat_response_feedback_insert_own" on public.chat_response_feedback
      for insert with check (auth.uid() = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'chat_response_feedback'
      and policyname = 'chat_response_feedback_delete_own'
  ) then
    create policy "chat_response_feedback_delete_own" on public.chat_response_feedback
      for delete using (auth.uid() = user_id);
  end if;
end $$;
