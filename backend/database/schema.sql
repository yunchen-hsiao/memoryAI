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
  created_at timestamp with time zone default timezone('utc'::text, now())
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
$$;
