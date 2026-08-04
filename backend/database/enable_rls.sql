-- ============================================================================
-- 啟用 Row Level Security (RLS)
-- ============================================================================
-- 背景：目前 memories / entities / user_contexts / profiles 四張表都沒有啟用
-- RLS。由於前端使用的 Supabase anon key 會被打包進瀏覽器 JS bundle（公開資訊），
-- 任何人只要取得這組 anon key，就能在瀏覽器 console 用 supabase-js 直接呼叫
-- supabase.from('memories').select('*') 或 supabase.rpc('search_memories', ...)，
-- 完全繞過 FastAPI 後端與其 JWT 驗證，讀取到其他使用者的記憶資料。
--
-- 修法：啟用 RLS 並加上「只能存取自己資料」的 policy。
-- 後端使用的是 Supabase service role key，service role 預設會繞過 RLS，
-- 因此這個修改不影響現有後端功能，只會擋掉「跳過後端直接打 Supabase」的路徑。
--
-- 使用方式：在 Supabase Dashboard > SQL Editor 貼上並執行整份檔案即可，
-- 這份腳本可重複執行（使用 DROP POLICY IF EXISTS 確保不會因 policy 已存在而報錯）。
-- ============================================================================

-- ── profiles ────────────────────────────────────────────────────────────────
alter table public.profiles enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles
  for select using (auth.uid() = id);

drop policy if exists "profiles_insert_own" on public.profiles;
create policy "profiles_insert_own" on public.profiles
  for insert with check (auth.uid() = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles
  for update using (auth.uid() = id) with check (auth.uid() = id);

drop policy if exists "profiles_delete_own" on public.profiles;
create policy "profiles_delete_own" on public.profiles
  for delete using (auth.uid() = id);

-- ── user_contexts ───────────────────────────────────────────────────────────
alter table public.user_contexts enable row level security;

drop policy if exists "user_contexts_select_own" on public.user_contexts;
create policy "user_contexts_select_own" on public.user_contexts
  for select using (auth.uid() = user_id);

drop policy if exists "user_contexts_insert_own" on public.user_contexts;
create policy "user_contexts_insert_own" on public.user_contexts
  for insert with check (auth.uid() = user_id);

drop policy if exists "user_contexts_update_own" on public.user_contexts;
create policy "user_contexts_update_own" on public.user_contexts
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "user_contexts_delete_own" on public.user_contexts;
create policy "user_contexts_delete_own" on public.user_contexts
  for delete using (auth.uid() = user_id);

-- ── memories ─────────────────────────────────────────────────────────────────
alter table public.memories enable row level security;

drop policy if exists "memories_select_own" on public.memories;
create policy "memories_select_own" on public.memories
  for select using (auth.uid() = user_id);

drop policy if exists "memories_insert_own" on public.memories;
create policy "memories_insert_own" on public.memories
  for insert with check (auth.uid() = user_id);

drop policy if exists "memories_update_own" on public.memories;
create policy "memories_update_own" on public.memories
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "memories_delete_own" on public.memories;
create policy "memories_delete_own" on public.memories
  for delete using (auth.uid() = user_id);

-- ── entities ─────────────────────────────────────────────────────────────────
alter table public.entities enable row level security;

drop policy if exists "entities_select_own" on public.entities;
create policy "entities_select_own" on public.entities
  for select using (auth.uid() = user_id);

drop policy if exists "entities_insert_own" on public.entities;
create policy "entities_insert_own" on public.entities
  for insert with check (auth.uid() = user_id);

drop policy if exists "entities_update_own" on public.entities;
create policy "entities_update_own" on public.entities
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "entities_delete_own" on public.entities;
create policy "entities_delete_own" on public.entities
  for delete using (auth.uid() = user_id);

-- ── search_memories 函式 ──────────────────────────────────────────────────────
-- 明確標示為 SECURITY INVOKER（Postgres 預設值，這裡明確寫出以避免未來誤改成
-- SECURITY DEFINER）。SECURITY INVOKER 代表這個函式會以「呼叫者」的權限執行，
-- 因此當任何人透過 anon key 呼叫這個 RPC 時，函式內部對 memories 表的查詢
-- 仍會受到上面剛啟用的 RLS policy 限制，即使呼叫者在 p_user_id 參數中
-- 故意填入別人的 UUID 也無法讀到其他使用者的資料。
alter function search_memories(vector, float, int, uuid, float) security invoker;
