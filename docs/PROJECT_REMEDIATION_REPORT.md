# MemoryAI 專案修正與完整性提升報告

> 建立日期：2026-08-31  
> 執行方式：依階段逐步修正；每階段完成後先驗證，再決定下一階段。  
> 本報告不包含任何 `.env`、API key、使用者日記或其他敏感內容。

## 1. 專案現況結論

MemoryAI 已完成 React/Vite 前端、FastAPI 後端、Supabase/PostgreSQL/pgvector、Neo4j、Gemini/Cohere 與 Supabase Auth 的主要串接，MVP 核心流程已可運作：登入、聊天 RAG、記憶 CRUD、批次日記匯入、人物分析及關係圖。

目前最需要處理的不是新增 UI，而是保護私人記憶資料、確保服務能穩定啟動、避免部分失敗被誤判為成功，以及讓 Supabase 與 Neo4j 長期保持一致。

## 2. 問題分級

### P0：部署或隱私風險

1. `backend/main.py` 在 `load_dotenv()` 前初始化 Gemini/Cohere client；無法從 `.env` 取得 key 時，後端會在 import 階段失敗。
2. `backend/security.py` 在 `ENCRYPTION_KEY` 缺失或加密失敗時回傳原文，形成 fail-open 明文保存風險。
3. `ADMIN_EMAIL` 可讓特定帳號資料完全不加密，與整體隱私目標不一致。
4. `SUPABASE_KEY`、anon key、service role key 的使用規則不一致，且 RLS 是否已套用到實際雲端環境尚未驗證。
5. 既有資料庫的 RLS 啟用與 migration 流程沒有被明確整合成正式部署 gate。

### P1：資料正確性與可靠性

1. 多數 API 在例外時仍回傳 HTTP 200 與內部錯誤字串。
2. 前端歸檔、批次匯入、刪除等 mutation 沒有一致檢查 HTTP status 與 `success`。
3. Pydantic request model 缺少長度、數量、範圍、日期與時區驗證。
4. 手動記憶 CRUD 不會可靠同步 Neo4j，可能造成圖譜與 Supabase 不一致。
5. `/api/memories`、dashboard 與人物分析仍有全量查詢和全量解密風險。
6. 背景任務使用 process memory、daemon thread 與本機 JSON cache，不適合多 worker 或多實例部署。
7. AI JSON 僅以 `json.loads()` 解析，缺少 schema 與 `exact_quote` 內容驗證。

### P2：品質、維護與產品完整性

1. 尚未建立專案測試、CI、正式 migration runner 與 staging 驗證流程。
2. `main.py` 集中路由、AI prompt、資料存取、背景任務與錯誤處理，檔案過大。
3. 前端 ESLint 目前有 29 個 errors、3 個 warnings；雖然 production build 通過，但 lint 尚未通過。
4. 前端 production bundle 約 1,189 kB，應拆分 lazy-loaded chunks。
5. embedding query/document task type 使用不一致，schema 註解仍保留舊模型資訊。
6. Dockerfile 缺少非 root user、healthcheck、設定檢查與明確的部署流程。
7. README 的 migration 說明有重複項目，且環境變數與實際腳本權限需求不完全一致。
8. 缺少資料匯出、刪除、保留期限、key rotation、AI 人格側寫 opt-out 等隱私產品能力。

## 3. 分階段執行計畫

### 第一階段：啟動設定與加密安全基礎

**目標**

- 確保 `.env` 在所有 client 初始化前載入。
- 缺少必要設定時明確停止啟動，不讓錯誤延後到 API 執行時才發生。
- 加密金鑰缺失或無效時 fail-closed。
- 新寫入資料一律加密，不再因 `ADMIN_EMAIL` 例外而保存明文。
- 保留舊有明文資料的讀取相容性，避免既有資料立即無法查看；後續再安排加密 migration。

**涉及檔案**

- `backend/main.py`
- `backend/security.py`
- `README.md`
- `docs/PROJECT_REMEDIATION_REPORT.md`

**完成條件**

- backend module import 不再因 `.env` 載入順序失敗。
- 缺少必要 key 時錯誤訊息清楚指出缺少哪些設定。
- `encrypt_text()` 沒有有效 Fernet key 時直接拋錯，不回傳原文。
- 管理員帳號的新資料也會加密。
- README 明確區分 backend-only 與 frontend-only key。

**雲端需要使用者操作**

- 在 backend 雲端服務新增或確認 `GEMINI_API_KEY`、`COHERE_API_KEY`、`SUPABASE_URL`、`SUPABASE_SERVICE_ROLE_KEY`、`ENCRYPTION_KEY`。
- 將舊的 `SUPABASE_KEY` 逐步改名為 `SUPABASE_SERVICE_ROLE_KEY`；不要把 service role key 放進 frontend 環境變數。
- 確認 `ENCRYPTION_KEY` 與既有資料建立時使用的 key 完全相同；不可任意重新產生，否則舊資料無法解密。
- 重新部署 backend，查看啟動 log 是否正常。
- 第一階段不會自動修改雲端資料庫；RLS 的實際狀態需在下一個部署驗證步驟由使用者確認。

### 第二階段：API 錯誤契約與輸入驗證

**目標**

- 統一 HTTP status、錯誤格式與 request ID。
- 加入 request body、history、content、keywords、情緒分數、重要度與日期驗證。
- 前端統一透過 API client 處理錯誤，不再把 partial failure 顯示成成功。
- 加入基本 rate limit、AI quota 與輸入大小限制。

**預計涉及檔案**

- `backend/main.py`
- 新增 backend schemas/error handlers/middleware
- `frontend/src/App.tsx`
- `frontend/src/components/BatchImport.tsx`
- `frontend/src/components/MemoryTimeline.tsx`
- `frontend/src/components/Dashboard.tsx`

**雲端可能需要使用者操作**

- 設定 rate-limit 儲存層或平台層級限制。
- 確認反向代理或 hosting provider 的 request body limit。
- 若導入錯誤監控，提供 Sentry/監控服務的 DSN。

### 第三階段：資料分頁、聚合與 Neo4j 一致性

**目標**

- `memories` 使用 cursor pagination。
- Dashboard 改用 PostgreSQL/RPC 聚合，避免每次全量解密。
- 補齊資料庫 index 與 pgvector index。
- 以 outbox/job 機制同步 Neo4j 的 create/update/delete。
- 清理 orphan Event 與過期圖譜關係。

**預計涉及檔案**

- `backend/main.py`
- `backend/graph_db.py`
- `backend/database/migrations/*`
- `frontend/src/components/MemoryTimeline.tsx`
- 新增 job/outbox worker

**雲端可能需要使用者操作**

- 在 Supabase SQL Editor 或正式 migration runner 執行 migration。
- 在 Neo4j AuraDB 執行 index/constraint 與資料清理。
- 若採 Redis/queue，建立對應雲端服務與環境變數。

### 第四階段：背景任務、部署與可觀測性

**目標**

- 將 daemon thread、本機 JSON cache 改成持久化 job/cache。
- 增加 liveness/readiness health endpoint。
- Docker 使用非 root user 與 healthcheck。
- 加入 structured logging、request ID、錯誤監控與任務進度。
- 建立 staging 與 production 部署檢查。

**雲端可能需要使用者操作**

- 設定 queue、Redis、監控與 log retention。
- 設定 readiness probe、資源上限與 autoscaling。
- 配置 staging environment 的獨立 Supabase/Neo4j/API keys。

### 第五階段：測試、CI 與產品隱私完整性

**目標**

- 建立 unit、API integration、RLS isolation、migration 與 smoke tests。
- 修正 ESLint 全部問題。
- 建立 CI：lint、typecheck、build、Python syntax、pytest、migration check。
- 加入資料匯出/刪除、key rotation、retention policy。
- 人格側寫、MBTI 與 AI 推測加入 opt-out 與不確定性標記。

**雲端可能需要使用者操作**

- 建立 CI secrets。
- 設定 production backup、restore drill 與 key rotation 流程。
- 設定正式資料保留與刪除政策。

## 4. 已完成的基線驗證

| 項目 | 結果 |
|---|---|
| Frontend TypeScript/build | 通過 |
| Frontend ESLint | 未通過：29 errors、3 warnings |
| Python syntax check | 通過：12 個專案 Python 檔案 |
| `pip check` | 通過 |
| pytest collection | 沒有找到測試 |
| `git diff --check` | 通過 |
| backend import smoke test | 修正前失敗於 Gemini key 初始化順序 |

## 5. 每階段交付規則

每個階段完成時必須提供：

1. 修改檔案清單。
2. 實際完成的修正。
3. 本機驗證結果。
4. 尚未能在本機驗證的項目。
5. 使用者需要在雲端執行的操作。
6. 下一階段開始前可能需要的決策或確認。

## 6. 重要風險提醒

- `ENCRYPTION_KEY` 是資料可讀性的核心金鑰。若遺失或更換，既有加密記憶可能無法解密；必須先備份並保存於可靠的 secret manager。
- service role key 權限極高，只能放在 backend secret，不可放入 Vite `VITE_*` 變數或前端程式碼。
- RLS 必須在實際 Supabase project 驗證，不能只依賴 repository 內的 SQL 文件。
- 真正的 Neo4j、Supabase、Gemini、Cohere runtime 與雲端部署狀態，不能只靠本機靜態檢查推定。

## 7. 第二階段執行結果：API 錯誤契約與輸入驗證

### 已完成

- `ChatRequest`：限制 message 12,000 字、history 30 筆，並驗證 history content。
- `MemoryCreate` / `MemoryUpdate`：限制 topic、summary、content、keywords、original_text 長度與數量。
- `emotion_score` 限制為 0～100。
- `importance_weight` 限制為 1～5。
- `diary_date` / `date_str` 驗證為合法日期並正規化為 `YYYY-MM-DD`。
- `diary_time` 驗證為合法 `HH:MM` 或 `HH:MM:SS`。
- `timezone` 使用 IANA timezone 驗證，例如 `Asia/Taipei`、`Pacific/Auckland`。
- 批次匯入單筆 content 限制為 100,000 字，避免單次 request 無限制消耗 AI/API 資源。
- 主要 backend endpoint 改用安全的 HTTP error status，不再把內部例外字串直接回傳給使用者。
- 未找到記憶回傳 404；背景任務重複啟動回傳 409；Neo4j 不可用回傳 503；AI 事件解析失敗回傳 502。
- 新增 `frontend/src/lib/api.ts`，統一處理 HTTP status、`success: false`、`error` 與 FastAPI `detail`。
- 聊天、回饋、摘要、記憶 CRUD、人物編譯與 dashboard API 改用統一 client。
- 歸檔遇到部分失敗時，不再顯示全數成功；已成功事件會從預覽移除，失敗事件保留供重試，降低重複寫入風險。
- 批次匯入遇到部分失敗時顯示成功、略過、失敗數量，且不清空原始輸入。
- 記憶刪除與儲存只有 API 確認成功後才更新畫面。

### 尚未包含

- Redis/資料庫 rate limit 與每日 AI quota。
- 全域 request body size middleware。
- 正式 request ID、structured logging 與外部錯誤監控。
- Neo4j outbox 一致性同步。
- memories cursor pagination 與 dashboard SQL 聚合。

### 第二階段雲端操作

本階段不需要執行 Supabase SQL migration，也不需要修改 Neo4j schema。部署時只需：

1. 將目前程式部署到 backend 與 frontend。
2. 確認 backend 仍使用第一階段要求的 `APP_ENV=production` 與 `SUPABASE_SERVICE_ROLE_KEY`。
3. 重新測試登入、聊天、記憶新增/修改/刪除與批次匯入。
4. 確認 API 錯誤時 frontend 顯示失敗，不會清空尚未完成的內容。

若下一階段導入 rate limit、queue 或 SQL index，才會需要額外的雲端服務或 migration。

### 最終本機驗證結果

- Backend Python AST syntax check：通過，檢查 12 個專案 Python 檔案，0 syntax errors。
- Backend module import：通過。
- Pydantic targeted validation smoke：通過；確認 `Asia/Taipei` 在 Windows 環境可通過 `pytz` fallback、日期可正規化為 `YYYY-MM-DD`，非法 timezone、超出範圍的 emotion score 與空白 import content 會被拒絕。
- Frontend `npm run build`：通過；Vite 仍提示 JavaScript bundle 約 1,189.66 kB、超過 500 kB 的既有優化警告。
- Frontend `npm run lint`：仍未全數通過，剩餘 24 errors、2 warnings，集中在既有 `any` 型別、React effect state update、missing dependency 與常數條件；本階段新增的 `frontend/src/lib/api.ts` lint error 已修正。
- `git diff --check`：通過。

第二階段的程式、文件與本機驗證已完成；不自動進入第三階段。

## 8. 第三階段執行結果：分頁、聚合與 Neo4j 一致性

### 已完成的本機程式修改

- 新增 `backend/database/migrations/20260831_phase3_data_consistency.sql`：
  - `memories(user_id, diary_date, diary_time, id)` 時間軸複合 index。
  - 3072 維 embedding 的 user-scoped filter index；Supabase 目前的 pgvector 不接受對 `vector(3072)` 建立 HNSW/IVFFlat ANN index，因此不在 migration 建立 HNSW。
  - `get_memory_page` cursor pagination RPC，固定排序為 date/time/id，最多回傳 101 筆供 backend 判斷 `has_more`。
  - `get_dashboard_aggregates` RPC，聚合每日記憶數、每日平均情緒、總天數與每日平均的整體平均。
  - `graph_sync_outbox` table、pending index、claim/lease/retry/complete RPC。
- `backend/main.py`：
  - `/api/memories` 改為 bounded cursor pagination，cursor 使用 base64url opaque payload，回傳 `memories`、`next_cursor`、`has_more`。
  - create/update/delete memory 與 diary import 會寫入 graph outbox；migration 尚未套用時才使用 request-local background fallback，避免假稱已建立 durable job。
  - Dashboard 的數值趨勢與 summary stats 優先使用 PostgreSQL aggregate RPC，RPC 尚未存在時保留舊 Python fallback。
- `frontend/src/components/MemoryTimeline.tsx`：
  - 首次只載入 30 筆。
  - 以 cursor append 後續頁面，加入「載入更多記憶」按鈕。
  - 新增、修改成功後重新載入第一頁，不再把整個 memory table 載入前端。
- `backend/graph_db.py`：
  - 新增 idempotent Event upsert，更新 date、emotion、importance 並替換舊 `OCCURRED_ON` / `MENTIONS` 關係。
  - 新增 Event delete 與 orphan Keyword/Date cleanup。
- 新增 `backend/services/graph_outbox.py`、`backend/scripts/process_graph_outbox.py` 與 `backend/scripts/reconcile_graph.py`。
  - Worker 使用 database claim/lease，失敗會退避重試，五次失敗後標記 `failed`。
  - reconciliation 會比對 Supabase memory IDs 與 Neo4j Event IDs，清除孤兒並重新同步結構化資料。

### 明確限制

- 本階段只把日期與情緒等不需解密的 Dashboard 數值移到 SQL aggregate；既有加密 keywords/summary 的 keyword distribution、人物比對與最近摘要仍走相容解密路徑。若要完全 SQL 化，後續需要明確設計可接受隱私風險的 normalized keyword/entity relation table。
- Repository 只建立 migration 草稿，尚未對實際 Supabase project 執行 SQL；也尚未執行 Neo4j reconciliation。這些需要部署維運人員在雲端執行。
- 未新增 Redis；worker 可由平台 cron、獨立 worker 或 scheduler 執行，但不可依賴 web process 的 daemon thread 來保證 outbox 處理。

### 第三階段雲端操作清單

1. 在 Supabase SQL Editor 或正式 migration runner 執行：
   `backend/database/migrations/20260831_phase3_data_consistency.sql`
2. 確認 migration 成功建立：
   - `memories_user_timeline_idx`
   - `memories_embedding_user_present_idx`
   - `get_memory_page`
   - `get_dashboard_aggregates`
   - `graph_sync_outbox`
   - 四個 outbox function
3. 使用 `EXPLAIN` 或 Supabase Query Performance 檢查時間軸查詢與 user-scoped embedding filter 是否使用新 index。由於目前 `memories.embedding` 是 `vector(3072)`，Supabase pgvector 的 HNSW/IVFFlat ANN index 不可直接建立；若未來要使用 ANN，需先設計相容的降維或 `halfvec` schema migration，並同步修改 embedding 產生與搜尋 RPC，不在本次 migration 直接變更既有資料。
4. 確認 Neo4j AuraDB 已存在既有 User/Event/Date/Keyword uniqueness constraints；若尚未建立，先執行 `build_graph.py` 的 constraint 語句或由維運人員建立。
5. 部署 backend/frontend，並設定 scheduler/worker 定期執行：
   `python scripts/process_graph_outbox.py 25`
   worker 使用既有 backend secrets，不可把 service-role key 放進 frontend。
6. 先在 staging 或單一測試使用者執行一次：
   `python scripts/reconcile_graph.py <user_id>`
   確認 `synced` 與 `removed_orphans` 數量，再擴大到其他使用者。
7. 驗證新增、修改 keywords/date/score、刪除記憶後，outbox 最終變成 `completed`，Neo4j 不再保留舊 MENTIONS 或已刪除 Event。

本階段未執行任何雲端 SQL、Neo4j 指令或部署操作；在使用者完成 migration 與 worker 設定前，不宣稱第三階段雲端完成。

### 第三階段本機驗證結果

- Backend Python AST syntax check：通過，15 個專案 Python 檔案、0 syntax errors。
- Backend module、outbox service、outbox worker imports：通過。
- Cursor smoke：通過；合法 cursor 可 round-trip 還原 date/time/id，非法 cursor 回傳 HTTP 400。
- Frontend `npm run build`：通過；TypeScript 與 Vite build 均通過，仍有約 1,190 kB bundle size warning。
- Frontend `npm run lint`：24 errors、2 warnings，與第三階段前既有基線相同；本階段新增的 `MemoryTimeline` lint 問題已移除。剩餘問題集中於既有 `any`、React effect state update、missing dependency 與常數條件。
- `git diff --check`：通過。

本機第三階段程式交付完成；雲端 migration、outbox scheduler、Neo4j constraints 確認與 reconciliation 尚未執行，不能視為雲端部署完成。
