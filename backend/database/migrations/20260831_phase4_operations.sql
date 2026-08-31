-- Phase 4: durable background jobs and monthly summary cache.
-- Run after the Phase 3 migration and before enabling the Phase 4 worker.

create table if not exists public.monthly_summary_cache (
  user_id uuid not null references auth.users(id) on delete cascade,
  summary_year smallint not null check (summary_year between 2000 and 2100),
  summary_month smallint not null check (summary_month between 1 and 12),
  encrypted_summary text not null,
  memory_count integer not null default 0 check (memory_count >= 0),
  created_at timestamp with time zone not null default timezone('utc'::text, now()),
  updated_at timestamp with time zone not null default timezone('utc'::text, now()),
  primary key (user_id, summary_year, summary_month)
);

create index if not exists monthly_summary_cache_updated_idx
  on public.monthly_summary_cache (user_id, updated_at desc);

alter table public.monthly_summary_cache enable row level security;

create table if not exists public.background_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  job_type text not null check (job_type in ('graph', 'entities', 'entity_profile')),
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending'
    check (status in ('pending', 'processing', 'completed', 'failed')),
  progress smallint not null default 0 check (progress between 0 and 100),
  progress_message text,
  attempts integer not null default 0 check (attempts >= 0),
  available_at timestamp with time zone not null default timezone('utc'::text, now()),
  lease_until timestamp with time zone,
  lease_owner text,
  last_error text,
  created_at timestamp with time zone not null default timezone('utc'::text, now()),
  updated_at timestamp with time zone not null default timezone('utc'::text, now()),
  completed_at timestamp with time zone
);

create index if not exists background_jobs_pending_idx
  on public.background_jobs (status, available_at, created_at);

create index if not exists background_jobs_user_idx
  on public.background_jobs (user_id, job_type, created_at desc);

create unique index if not exists background_jobs_active_unique_idx
  on public.background_jobs (user_id, job_type)
  where status in ('pending', 'processing');

alter table public.background_jobs enable row level security;

create or replace function public.claim_background_jobs(
  p_worker_id text,
  p_limit integer default 5
)
returns setof public.background_jobs
language plpgsql
security definer
set search_path = public
as $$
begin
  return query
  with candidates as (
    select j.id
    from public.background_jobs j
    where (
      (j.status = 'pending' and j.available_at <= now())
      or (j.status = 'processing' and j.lease_until < now())
    )
    and j.attempts < 5
    order by j.created_at
    for update skip locked
    limit least(greatest(coalesce(p_limit, 5), 1), 25)
  )
  update public.background_jobs j
  set status = 'processing',
      attempts = j.attempts + 1,
      lease_until = now() + interval '15 minutes',
      lease_owner = left(p_worker_id, 200),
      updated_at = now(),
      last_error = null
  from candidates c
  where j.id = c.id
  returning j.*;
end;
$$;

create or replace function public.complete_background_job(
  p_job_id uuid,
  p_success boolean,
  p_error text default null,
  p_progress_message text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.background_jobs
  set status = case
        when p_success then 'completed'
        when attempts >= 5 then 'failed'
        else 'pending'
      end,
      progress = case when p_success then 100 else progress end,
      progress_message = coalesce(p_progress_message, progress_message),
      available_at = case
        when p_success then available_at
        else now() + least(power(2, attempts) * interval '30 seconds', interval '1 hour')
      end,
      lease_until = null,
      lease_owner = null,
      last_error = case when p_success then null else left(coalesce(p_error, 'unknown error'), 2000) end,
      updated_at = now(),
      completed_at = case when p_success then now() else null end
  where id = p_job_id;
end;
$$;

create or replace function public.update_background_job_progress(
  p_job_id uuid,
  p_progress smallint,
  p_message text default null
)
returns void
language sql
security definer
set search_path = public
as $$
  update public.background_jobs
  set progress = least(greatest(coalesce(p_progress, 0), 0), 100),
      progress_message = left(p_message, 500),
      updated_at = now()
  where id = p_job_id and status = 'processing';
$$;

revoke all on function public.claim_background_jobs(text, integer) from public, anon, authenticated;
revoke all on function public.complete_background_job(uuid, boolean, text, text) from public, anon, authenticated;
revoke all on function public.update_background_job_progress(uuid, smallint, text) from public, anon, authenticated;
grant execute on function public.claim_background_jobs(text, integer) to service_role;
grant execute on function public.complete_background_job(uuid, boolean, text, text) to service_role;
grant execute on function public.update_background_job_progress(uuid, smallint, text) to service_role;
