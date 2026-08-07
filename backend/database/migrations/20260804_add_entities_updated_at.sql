-- Run once in the Supabase SQL Editor for an existing deployment.
-- Adds updated_at to entities so the person status card (現況簡報卡) can show
-- profile freshness (e.g. "3 天前更新"). Existing rows will have updated_at = NULL
-- until their profile is next rebuilt/incrementally updated.

alter table public.entities
  add column if not exists updated_at timestamp with time zone default timezone('utc'::text, now());
