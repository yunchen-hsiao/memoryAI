-- Run this once in the Supabase SQL Editor for an existing deployment.
-- It records the full source text for each import so same-day appends
-- can be detected without duplicating the earlier events.

create table if not exists public.memory_imports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  diary_date date not null,
  source_hash text not null,
  source_content text not null,
  created_at timestamp with time zone default timezone('utc'::text, now())
);

create index if not exists memory_imports_user_date_created_idx
  on public.memory_imports (user_id, diary_date, created_at desc);

create unique index if not exists memory_imports_user_date_hash_idx
  on public.memory_imports (user_id, diary_date, source_hash);

alter table public.memory_imports enable row level security;

-- The policies are intentionally conditional so this migration is safe to rerun.
do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'memory_imports'
      and policyname = 'memory_imports_select_own'
  ) then
    create policy "memory_imports_select_own" on public.memory_imports
      for select using (auth.uid() = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'memory_imports'
      and policyname = 'memory_imports_insert_own'
  ) then
    create policy "memory_imports_insert_own" on public.memory_imports
      for insert with check (auth.uid() = user_id);
  end if;

  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'memory_imports'
      and policyname = 'memory_imports_delete_own'
  ) then
    create policy "memory_imports_delete_own" on public.memory_imports
      for delete using (auth.uid() = user_id);
  end if;
end $$;
