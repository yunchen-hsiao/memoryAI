-- Phase 3: bounded memory reads, dashboard aggregates, and durable Neo4j sync jobs.
-- Run this migration in Supabase before deploying the Phase 3 backend.

create index if not exists memories_user_timeline_idx
  on public.memories (
    user_id,
    diary_date desc nulls last,
    diary_time desc nulls last,
    id desc
  );

-- Supabase's current pgvector build rejects HNSW/IVFFlat indexes on vector(3072)
-- because ANN vector indexes are limited to 2000 dimensions. Keep a partial
-- B-tree filter index so user-scoped exact vector scans avoid rows without embeddings.
-- Do not replace this with HNSW unless the embedding column is migrated to a
-- supported indexed representation and search_memories is updated accordingly.
create index if not exists memories_embedding_user_present_idx
  on public.memories (user_id)
  where embedding is not null;

create or replace function public.get_memory_page(
  p_user_id uuid,
  p_limit integer default 31,
  p_cursor_date date default null,
  p_cursor_time time default null,
  p_cursor_id uuid default null
)
returns table (
  id uuid,
  diary_date date,
  diary_time time,
  timezone text,
  topic text,
  summary text,
  emotion_score integer,
  importance_weight integer,
  keywords text[],
  content text
)
language sql
security invoker
stable
as $$
  select
    m.id, m.diary_date, m.diary_time, m.timezone, m.topic, m.summary,
    m.emotion_score, m.importance_weight, m.keywords, m.content
  from public.memories m
  where m.user_id = p_user_id
    and (
      p_cursor_id is null
      or (
        coalesce(m.diary_date, '0001-01-01'::date),
        coalesce(m.diary_time, '00:00:00'::time),
        m.id
      ) < (
        coalesce(p_cursor_date, '0001-01-01'::date),
        coalesce(p_cursor_time, '00:00:00'::time),
        p_cursor_id
      )
    )
  order by m.diary_date desc nulls last, m.diary_time desc nulls last, m.id desc
  limit least(greatest(coalesce(p_limit, 31), 1), 101);
$$;

create or replace function public.get_dashboard_aggregates(p_user_id uuid)
returns table (
  diary_date date,
  memory_count bigint,
  avg_score numeric,
  total_days bigint,
  overall_avg_score numeric
)
language sql
security invoker
stable
as $$
  with daily as (
    select
      m.diary_date,
      count(*)::bigint as memory_count,
      avg(m.emotion_score)::numeric as avg_score
    from public.memories m
    where m.user_id = p_user_id
      and m.diary_date is not null
    group by m.diary_date
  ), summary as (
    select
      count(*)::bigint as total_days,
      coalesce(avg(d.avg_score), 0)::numeric as overall_avg_score
    from daily d
  )
  select
    d.diary_date,
    d.memory_count,
    round(d.avg_score, 1),
    s.total_days,
    round(s.overall_avg_score, 1)
  from daily d
  cross join summary s
  order by d.diary_date;
$$;

create table if not exists public.graph_sync_outbox (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  memory_id uuid not null,
  operation text not null check (operation in ('upsert', 'delete')),
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'completed', 'failed')),
  attempts integer not null default 0 check (attempts >= 0),
  available_at timestamp with time zone not null default timezone('utc'::text, now()),
  lease_until timestamp with time zone,
  last_error text,
  created_at timestamp with time zone not null default timezone('utc'::text, now()),
  processed_at timestamp with time zone
);

create index if not exists graph_sync_outbox_pending_idx
  on public.graph_sync_outbox (status, available_at, created_at);

create index if not exists graph_sync_outbox_memory_idx
  on public.graph_sync_outbox (user_id, memory_id, created_at desc);

alter table public.graph_sync_outbox enable row level security;

create or replace function public.claim_graph_sync_jobs(
  p_worker_id text,
  p_limit integer default 10
)
returns setof public.graph_sync_outbox
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with candidates as (
    select o.id
    from public.graph_sync_outbox o
    where (
      (o.status = 'pending' and o.available_at <= now())
      or (o.status = 'processing' and o.lease_until < now())
    )
    and o.attempts < 5
    order by o.created_at
    for update skip locked
    limit least(greatest(coalesce(p_limit, 10), 1), 100)
  )
  update public.graph_sync_outbox o
  set status = 'processing',
      attempts = o.attempts + 1,
      lease_until = now() + interval '5 minutes',
      last_error = null
  from candidates c
  where o.id = c.id
  returning o.*;
end;
$$;

create or replace function public.complete_graph_sync_job(
  p_job_id uuid,
  p_success boolean,
  p_error text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.graph_sync_outbox
  set status = case
        when p_success then 'completed'
        when attempts >= 5 then 'failed'
        else 'pending'
      end,
      available_at = case
        when p_success then available_at
        else now() + least(power(2, attempts) * interval '10 seconds', interval '1 hour')
      end,
      lease_until = null,
      last_error = case when p_success then null else left(coalesce(p_error, 'unknown error'), 2000) end,
      processed_at = case when p_success then now() else null end
  where id = p_job_id;
end;
$$;

revoke all on function public.get_memory_page(uuid, integer, date, time, uuid) from public, anon, authenticated;
revoke all on function public.get_dashboard_aggregates(uuid) from public, anon, authenticated;
revoke all on function public.claim_graph_sync_jobs(text, integer) from public, anon, authenticated;
revoke all on function public.complete_graph_sync_job(uuid, boolean, text) from public, anon, authenticated;
grant execute on function public.get_memory_page(uuid, integer, date, time, uuid) to service_role;
grant execute on function public.get_dashboard_aggregates(uuid) to service_role;
grant execute on function public.claim_graph_sync_jobs(text, integer) to service_role;
grant execute on function public.complete_graph_sync_job(uuid, boolean, text) to service_role;
