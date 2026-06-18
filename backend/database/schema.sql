-- Enable the pgvector extension to work with embedding vectors
create extension if not exists vector;

-- Create memories table
create table memories (
  id uuid primary key default gen_random_uuid(),
  content text not null, -- The original text
  summary text not null, -- AI generated summary
  topic text,
  keywords text[],
  emotion_score integer, -- e.g., 0-100 (0 is very negative, 100 is very positive)
  importance_weight integer default 3, -- 1-5 scale
  embedding vector(3072), -- Gemini text-embedding-004 has 768 dimensions
  diary_date date, -- The actual date the event happened
  diary_time time NULL, -- The actual time the event happened
  created_at timestamp with time zone default timezone('utc'::text, now())
);

-- Create entities table for coreference resolution (Who is "he/she/it")
create table entities (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  description text,
  relationship text,
  created_at timestamp with time zone default timezone('utc'::text, now())
);

-- Create a function to search memories based on vector similarity and time decay
create or replace function search_memories(
  query_embedding vector(768),
  match_threshold float,
  match_count int,
  time_weight_factor float default 0.3 -- How much time decay affects the score (0 to 1)
)
returns table (
  id uuid,
  summary text,
  topic text,
  diary_date date,
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
  where 1 - (memories.embedding <=> query_embedding) > match_threshold
  order by final_score desc
  limit match_count;
end;
$$;
