-- Enable the pgvector extension to work with embedding vectors
create extension if not exists vector;

-- Create a table for public profiles (optional, stores username/settings)
create table public.profiles (
  id uuid references auth.users on delete cascade not null primary key,
  username text unique,
  created_at timestamp with time zone default timezone('utc'::text, now())
);

-- Create user_contexts table for rolling narrative
create table user_contexts (
  user_id uuid primary key references auth.users(id) on delete cascade,
  life_context text default '這是一段全新的人生故事紀錄，目前還沒有任何前情提要。',
  updated_at timestamp with time zone default timezone('utc'::text, now())
);

-- Create memories table
create table memories (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade, -- Link to Supabase Auth User
  content text not null, -- The original text
  summary text not null, -- AI generated summary
  topic text,
  keywords text[],
  emotion_score integer, -- e.g., 0-100 (0 is very negative, 100 is very positive)
  importance_weight integer default 3, -- 1-5 scale
  embedding vector(3072), -- Gemini text-embedding-004 has 768 dimensions
  diary_date date, -- The actual date the event happened
  diary_time time NULL, -- The actual time the event happened
  timezone text NULL, -- e.g., 'Asia/Taipei', 'Pacific/Auckland'
  created_at timestamp with time zone default timezone('utc'::text, now())
);

-- Create entities table for coreference resolution (Who is "he/she/it")
create table entities (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade, -- Link to Supabase Auth User
  name text not null,
  description text,
  relationship text,
  created_at timestamp with time zone default timezone('utc'::text, now()),
  updated_at timestamp with time zone default timezone('utc'::text, now()) -- 側寫最後更新時間，供人物簡報卡顯示新鮮度
);

-- Create a function to search memories based on vector similarity and time decay
create or replace function search_memories(
  query_embedding vector(3072),
  match_threshold float,
  match_count int,
  p_user_id uuid, -- User ID parameter
  time_weight_factor float default 0.3 -- How much time decay affects the score (0 to 1)
)
returns table (
  id uuid,
  summary text,
  topic text,
  diary_date date,
  diary_time time,
  timezone text,
  similarity float,
  final_score float
)
language plpgsql
as $$
begin
  return query
  select
    memories.id,
    memories.summary,
    memories.topic,
    memories.diary_date,
    memories.diary_time,
    memories.timezone,
    (1 - (memories.embedding <=> query_embedding)) as similarity,
    -- Hybrid score calculation:
    -- Base similarity + time decay factor
    -- (Time diff in days + 1) to avoid div by zero
    -- We assume recent memories are more relevant.
    (
      (1 - (memories.embedding <=> query_embedding)) * (1 - time_weight_factor) +
      (1.0 / (extract(epoch from (now() - memories.diary_date::timestamp))/86400 + 1)) * time_weight_factor
    ) as final_score
  from memories
  where 
    memories.user_id = p_user_id -- Filter by user
    and 1 - (memories.embedding <=> query_embedding) > match_threshold
  order by final_score desc
  limit match_count;
end;
$$
security invoker; -- 明確使用呼叫者權限執行，確保 RLS policy 對此函式生效

-- ============================================================================
-- Row Level Security (RLS)
-- ============================================================================
-- 前端使用的 Supabase anon key 會被打包進瀏覽器 JS bundle，屬於公開資訊。
-- 若不啟用 RLS，任何人取得 anon key 後即可直接用 supabase-js 讀取／竄改
-- 任意使用者的資料，完全繞過 FastAPI 後端的 JWT 驗證。
-- 後端使用 service role key 呼叫 Supabase，service role 預設會繞過 RLS，
-- 因此以下設定不影響後端現有功能。

alter table public.profiles enable row level security;
create policy "profiles_select_own" on public.profiles
  for select using (auth.uid() = id);
create policy "profiles_insert_own" on public.profiles
  for insert with check (auth.uid() = id);
create policy "profiles_update_own" on public.profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);
create policy "profiles_delete_own" on public.profiles
  for delete using (auth.uid() = id);

alter table public.user_contexts enable row level security;
create policy "user_contexts_select_own" on public.user_contexts
  for select using (auth.uid() = user_id);
create policy "user_contexts_insert_own" on public.user_contexts
  for insert with check (auth.uid() = user_id);
create policy "user_contexts_update_own" on public.user_contexts
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "user_contexts_delete_own" on public.user_contexts
  for delete using (auth.uid() = user_id);

alter table public.memories enable row level security;
create policy "memories_select_own" on public.memories
  for select using (auth.uid() = user_id);
create policy "memories_insert_own" on public.memories
  for insert with check (auth.uid() = user_id);
create policy "memories_update_own" on public.memories
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "memories_delete_own" on public.memories
  for delete using (auth.uid() = user_id);

alter table public.entities enable row level security;
create policy "entities_select_own" on public.entities
  for select using (auth.uid() = user_id);
create policy "entities_insert_own" on public.entities
  for insert with check (auth.uid() = user_id);
create policy "entities_update_own" on public.entities
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "entities_delete_own" on public.entities
  for delete using (auth.uid() = user_id);

-- Track raw import snapshots so re-importing an existing date can detect
-- exact duplicates and process only newly appended diary text.
create table if not exists memory_imports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  diary_date date not null,
  source_hash text not null,
  source_content text not null,
  created_at timestamp with time zone default timezone('utc'::text, now())
);

create index if not exists memory_imports_user_date_created_idx
  on memory_imports (user_id, diary_date, created_at desc);

create unique index if not exists memory_imports_user_date_hash_idx
  on memory_imports (user_id, diary_date, source_hash);

alter table public.memory_imports enable row level security;
create policy "memory_imports_select_own" on public.memory_imports
  for select using (auth.uid() = user_id);
create policy "memory_imports_insert_own" on public.memory_imports
  for insert with check (auth.uid() = user_id);
create policy "memory_imports_delete_own" on public.memory_imports
  for delete using (auth.uid() = user_id);

-- Store coarse chat-response preferences without retaining chat text or memory excerpts.
create table chat_response_feedback (
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

create index chat_response_feedback_user_created_idx
  on chat_response_feedback (user_id, created_at desc);

alter table public.chat_response_feedback enable row level security;
create policy "chat_response_feedback_select_own" on public.chat_response_feedback
  for select using (auth.uid() = user_id);
create policy "chat_response_feedback_insert_own" on public.chat_response_feedback
  for insert with check (auth.uid() = user_id);
create policy "chat_response_feedback_delete_own" on public.chat_response_feedback
  for delete using (auth.uid() = user_id);
