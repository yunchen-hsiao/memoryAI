# MemoryAI (心靈伴侶 / 專屬大腦)

這是一個結合了 **RAG (檢索增強生成)**、**Graph RAG (圖譜檢索)** 與 **情感分析** 的全端 AI 專屬助理應用。
有別於市面上聊完就忘的 AI 聊天機器人，MemoryAI 能夠將你的對話、日記與情感波動「固化」為長期記憶，並透過向量資料庫與圖資料庫隨時回想。它不僅是你的傾聽者，更是最了解你的人際關係與歷史軌跡的「高階專屬幕僚」。

👉 **[查看開發與更新日誌 (Changelog)](CHANGELOG.md)**

---

## 核心功能介紹

### 1. 亦師亦友的 AI 幕僚 (Graph RAG 檢索)

搭載 Cohere (Command-R) 與 Google Gemini 雙引擎。每次對話前，系統會先解析你提到的人物，並採用 **圖優先檢索**：

1. 命中核心人物時，先用 Neo4j 圖譜鎖定「與這個人真正相關」的記憶範圍，避免不同人物的相似情境互相混淆。
2. 沒有命中人物（或圖查詢失敗）時，自動 fallback 回 pgvector 全域語意搜尋。
3. 額外附上該人物的角色檔案與「圖譜共現關鍵字」，讓 AI 知道這個人通常和什麼事情一起出現。

### 2. 記憶歸檔系統

RAG 系統的最強殺手鐧。當你跟 AI 聊完天、抱怨完之後，只需點擊「歸檔對話」，AI 就會自動將落落長的對話切分為多個「獨立事件」，自動提取摘要、下標籤、給予情緒分數，並在你確認後永久存入向量資料庫，同時同步一份結構化關聯到圖資料庫。

批次匯入同一天的日記時，系統會保存來源快照與內容雜湊：完全相同的內容會跳過；如果同一天是在原內容後追加新段落，系統只分析新增尾端，避免重複建立舊事件。

### 3. 情感紀錄儀表板

透過精美的視覺化圖表，讓你一眼看穿自己的內心狀態：

- **情緒波動折線圖**：追蹤你近期的情緒起伏。
- **主題頻率長條圖**：分析你最常思考或煩惱的事情。

### 4. 人物中心關係圖 (Person Relationship Graph)

以「人」為主角的力導向關係圖，取代原本難以解讀的記憶星系圖：

- **節點大小** ＝ 該人物出現的事件數（用平方根縮放，避免主要人物把其他人壓成一個點）。
- **節點顏色** ＝ 該人物的平均情緒分數，採 **相對色階**（依當前資料的 min/max 正規化）。因為真實資料的平均分數常擠在很窄的區間（例如 58~67），絕對門檻會讓所有人看起來一樣。
- **連線粗細／亮度** ＝ 兩人共同出現的次數，選中人物的相關連線會高亮。
- **點擊節點** 會展開右側面板：人物檔案、互動次數／平均情緒／平均重要度三格統計、互動起訖期間，以及該人物的真實事件時間軸（每一項左側色條依當筆事件的情緒分數上色）。

### 5. 關係溫度計 (人物 × 月份情緒熱力圖)

表格式熱力圖：列＝人物、欄＝月份。

- 格子顏色 ＝ 該人物該月的平均情緒分數，格內數字 ＝ 該月互動次數。
- 沒有互動的月份用半透明底色表示，一眼就能看出某段關係是什麼時候開始熱起來、什麼時候冷掉。
- 右側總計欄顯示總互動次數與整體平均分數。
- 含 `sr-only` 無障礙描述與 hover tooltip，螢幕閱讀器也能取得完整數據。

### 6. 人物對比分析

人物對比卡位於關係溫度計之後，可選兩位核心人物並排比較：

- 完整互動次數、平均情緒與平均重要度。
- 使用完整人物歷史建立月度情緒趨勢，而非只取最近 30 筆事件。
- 月份沒有可用情緒分數時保持空白，不會誤當成 0 分；圖例會與兩位人物正確對應。
- 關鍵時刻會列出情緒變化較大的事件，協助比較兩段關係的差異。

### 7. 核心人物網

系統會自動在背景分析你的日記與對話，抓取出常出現的「人物」，建立專屬的角色看板。系統懂得過濾掉無關的地名或專案，只把真正重要的人際關係實體化，讓 AI 更懂你的人際網絡。

### 8. 記憶時光機

完整的 CRUD 介面，讓你隨時搜尋、回顧、手動新增或編輯過去的記憶碎片。所有的記憶都會被轉化為高維度向量，成為 AI 思考的養分。

### 9. 端到端隱私加密防護

內建應用層對稱式加密，所有使用者的對話與事件摘要在寫入資料庫前都會轉換成亂碼，**即使是資料庫管理員也無法窺探其他使用者的隱私**，並提供專屬的「管理員豁免權」方便擁有者自行管理。
圖資料庫同樣遵守這條原則：**Neo4j 只存結構化欄位**（人物名稱、日期、情緒分數、重要度、memory_id），不存 topic / summary / 日記原文，需要內容時一律回 Supabase 解密取得。

---

## 技術架構

這個專案採用了現代化的前後端分離架構，結合了 Serverless 資料庫與最強大的開源套件：

### 前端 (Frontend)

- **核心框架**: React 18 + Vite (TypeScript)
- **UI & 樣式**: Tailwind CSS
- **圖表視覺化**: Recharts (響應式動態圖表)
- **關係圖**: react-force-graph-2d (Canvas 力導向圖)
- **Markdown 渲染**: React-Markdown + Remark-GFM
- **圖示庫**: Lucide React + 自製 SVG 漸層圖示

### 後端 (Backend)

- **核心框架**: FastAPI (Python) - 提供極速的非同步 API 介面。
- **文字生成模型**: Cohere SDK (`command-r-08-2024`) - 負責聊天、情緒分析、事件萃取、實體建模。
- **向量生成模型**: Google GenAI SDK (`gemini-embedding-001`) - 負責將繁體中文記憶轉化為 3072 維的 Embedding 向量。

### 資料庫 (Database)

- **Supabase (PostgreSQL)** — 真實來源 (Source of Truth)
  - 利用 `pgvector` 擴充套件，進行餘弦相似度 (Cosine Similarity) 語意搜尋。
  - 儲存關聯式資料（事件、日期、情緒分數）與加密後的非結構化文字。
- **Neo4j AuraDB** — 關係索引層
  - Schema：`(:User)-[:EXPERIENCED]->(:Event)-[:OCCURRED_ON]->(:Date)`、`(:Event)-[:MENTIONS]->(:Keyword)`。
  - 只作為「誰跟什麼事有關」的索引，不存任何內容明文。
  - 連線失效（AuraDB 路由表過期、SessionExpired）時會自動重建 driver 並重試。

---

## 如何運行

### 1. 環境變數設定

請在 `backend` 資料夾下建立 `.env` 檔案，填入以下金鑰：

```env
# backend-only secrets
APP_ENV=development
GEMINI_API_KEY=your_gemini_api_key
COHERE_API_KEY=your_cohere_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
ENCRYPTION_KEY=your_fernet_encryption_key   # 必須保留；更換會使既有加密資料無法解密

# Neo4j AuraDB（圖資料庫功能；未設定時圖相關 API 會自動停用，不影響其他功能）
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password

# 部署用（本機開發可省略）
ALLOWED_ORIGINS=https://your-frontend.vercel.app
```

> `SUPABASE_SERVICE_ROLE_KEY` 只能放在 backend 的 secret/environment variables，絕對不可放入前端或任何 `VITE_*` 變數。既有本機環境若仍使用 `SUPABASE_KEY`，目前保留相容讀取；`APP_ENV=staging` 或 `APP_ENV=production` 時則必須改用 `SUPABASE_SERVICE_ROLE_KEY`。前端另使用 `VITE_SUPABASE_URL` 與 `VITE_SUPABASE_ANON_KEY`，anon key 可公開但安全性必須依賴 Supabase RLS。
>
> `ENCRYPTION_KEY` 不可任意重新產生。若遺失或更換，既有加密記憶可能無法解密；請將它保存於雲端 secret manager，並建立備份與 key rotation 流程。新寫入資料一律加密，舊有明文資料目前僅保留讀取相容性，後續需另行執行加密 migration。


### 2. 啟動後端 (Backend)

```bash
cd backend
# 啟動虛擬環境
.\venv\Scripts\activate
# 安裝依賴 (初次運行)
pip install -r requirements.txt
# 啟動 FastAPI 伺服器
uvicorn main:app --reload --port 8000
```

### 3. 啟動前端 (Frontend)

```bash
cd frontend
# 安裝依賴 (初次運行)
npm install
# 啟動 Vite 開發伺服器
npm run dev
```

### 4. 維運腳本 (backend/scripts)

| 腳本 | 用途 |
| --- | --- |
| `import_history_v2.py` | 從日記文字檔批次匯入歷史記憶（含 AI 事件切割、前情提要串接、429 自動退避） |
| `build_graph.py` | 把 Supabase 既有記憶補建／重建到 Neo4j 圖譜 |
| `build_entities.py` | 掃描記憶，重新萃取核心人物實體檔案 |
| `migration` SQL | 既有 Supabase 部署需依序執行 `backend/database/migrations/` 下的 migration：`20260804_add_memory_imports.sql`、`20260804_add_entities_updated_at.sql`、`20260804_add_chat_response_feedback.sql`、`20260831_phase3_data_consistency.sql`、`20260831_phase4_operations.sql`。Phase 3 的 migration 不可使用舊版 HNSW SQL；目前 `vector(3072)` 只建立 user-scoped filter index。 |
| `migrate_graph_strip_content.py` | 一次性遷移：清掉圖資料庫早期版本殘留的內容明文欄位 |
| `reembed_memories.py` | 換 embedding 模型／維度後，重算全部記憶向量 |
| `model_search.py` | 列出目前 API Key 可用的模型清單 |

---

## 系統架構亮點

1. **Human-in-the-Loop (人機協作)**：記憶歸檔時，AI 只做草稿，最終由人類確認修改後再寫入資料庫，確保資料污染率降到最低。
2. **自動錯誤重試 (Retry Mechanism)**：針對免費版 API 常見的 429 (Rate Limit) 或 503 暫時不可用錯誤，後端已實作自動退避與重試機制；Neo4j 連線中斷也會自動重建連線重試，確保系統高可用性。
3. **RWD 響應式設計**：完美支援手機與電腦瀏覽，無論是通勤時快速歸檔對話，或是坐在電腦前查看深度儀表板，都能獲得最佳體驗。
4. **絕對的隱私防護**：結合 Supabase Auth JWT 身分驗證與 Python 後端應用層加密，確保使用者資料只為自己所用；圖資料庫刻意只存結構化關聯，把明文風險集中在單一個加密資料源。
5. **結構化防幻覺與精確擷取 (Verbatim Snippet)**：在處理萬字級超長日記時，透過導入 `involved_people` 強制人物隔離，並要求 AI 原文裁切 `exact_quote` 取代總結，徹底根除 RAG 場景中常見的「實體混淆幻覺」。
6. **雙資料庫分工 (Vector + Graph)**：向量庫負責「語意上像不像」，圖資料庫負責「事實上有沒有關聯」。人物明確時走圖譜精準命中，語意模糊時走向量廣泛召回，兩者互補。
7. **降級不中斷 (Graceful Degradation)**：Neo4j 模組載入失敗或環境變數缺失時，只有圖相關 API 會回報不可用，聊天、歸檔、時光機等核心流程完全不受影響。

---

## 已知限制與待辦

- **`GET /api/memories` 尚未分頁**：目前一次回傳該使用者全部記憶。已排除 3072 維 embedding 欄位（payload 從約 35MB 降到約 1MB），但筆數會隨時間線性成長，在 Render 免費層 512MB 記憶體下長期仍有 OOM (exit 137) 風險。下一步規劃改為 `?limit=&offset=` 分頁 + 前端無限捲動。
- **人物判定仍依賴關鍵字長度啟發式**（2~6 字），少數地名或專案名可能被誤判為人物。
- **手動記憶 CRUD 與圖譜同步仍非即時**：透過記憶時光機手動新增、編輯或刪除記憶後，人物對比／人物關係圖可能暫時與 Supabase 不一致；新增或編輯後可執行 `python scripts/build_graph.py <user_id>` 補同步，刪除資料則需另外清理或重建對應 Neo4j 圖譜。
- **月度故事回顧**功能已實作但暫時隱藏，等 API 額度策略確定後再開放。

## API 錯誤與輸入驗證

Backend API 會在 server-side 驗證輸入資料，包括聊天長度與歷史筆數、記憶內容長度、關鍵字數量、情緒分數（0-100）、重要度（1-5）、日期、時間與 IANA 時區。前端不可取代這些驗證。

API 錯誤會使用適當的 HTTP status，例如 400（輸入錯誤）、404（資料不存在）、409（背景任務重複）、502（AI 回應無法解析）、503（Neo4j 暫時不可用）與 500（伺服器錯誤）。前端透過統一 API client 檢查 HTTP status 與錯誤 payload；批次匯入或對話歸檔部分失敗時，不會再誤顯示全數成功，也不會清除尚未完成的內容。

目前第二階段尚未加入 Redis/資料庫 rate limit、每日 AI quota、cursor pagination 或 Neo4j outbox；這些項目列在 `docs/PROJECT_REMEDIATION_REPORT.md` 的後續階段。

## 第三階段：分頁、聚合與 Neo4j 一致性

第三階段新增：

- `GET /api/memories` 使用 bounded cursor pagination，預設每頁 30 筆、上限 100 筆，回傳 `next_cursor` 與 `has_more`。
- MemoryTimeline 改為分頁載入與「載入更多」，不再初次載入全部記憶。
- Dashboard 的日期情緒趨勢、紀錄天數與平均分數可使用 PostgreSQL aggregate RPC；加密的 keywords、summary 相關人物分析仍保留有限制的相容路徑。
- `backend/database/migrations/20260831_phase3_data_consistency.sql` 新增時間軸複合 index、3072 維 embedding 的 user-scoped filter index、dashboard aggregate RPC 與 Neo4j graph sync outbox。Supabase 目前不支援對 `vector(3072)` 建立 HNSW/IVFFlat ANN index，因此 migration 不會建立 HNSW。
- Memory create/update/delete 與日記匯入會先建立 durable graph outbox job；`backend/scripts/process_graph_outbox.py` 負責 claim、retry 與處理 Neo4j upsert/delete。
- `backend/scripts/reconcile_graph.py` 可依使用者比對 Supabase memories 與 Neo4j Event，清除 orphan Event 並重建結構化關係。

部署第三階段 backend 前，必須先在 Supabase 執行該 migration。部署後需配置排程或 worker 定期執行：

```text
python scripts/process_graph_outbox.py 25
```

既有資料切換新流程後，需由維運人員依使用者執行一次 graph reconciliation。Worker 只需要既有 backend 的 Supabase service-role、Neo4j 與加密設定，不需要把任何 service-role key 放進 frontend，也不強制新增 Redis。

## 第四階段：背景任務、部署與可觀測性

第四階段新增：

- `GET /health/live`：只檢查 API process 是否存活，供容器 liveness probe 使用。
- `GET /health/ready`：檢查 Supabase、Phase 3 graph outbox 與 Phase 4 background jobs table；Neo4j 目前以 degraded 狀態回報，不阻擋核心 API readiness。
- API middleware 會產生或傳遞 `X-Request-ID`，並在 response header 回傳相同 ID。
- Backend 使用標準 library 輸出 JSON structured logs，包含 timestamp、level、method、path、status、duration 與 request ID；不記錄 token、secret、prompt 或日記內容。
- `background_jobs` 與 `monthly_summary_cache` 改由 Supabase 持久化，不再依賴 web process 的 daemon thread 或本機 JSON cache。
- `backend/scripts/process_background_jobs.py` 負責執行 graph、entities、entity profile jobs；`backend/scripts/process_graph_outbox.py` 仍負責 Phase 3 Neo4j sync jobs。
- `GET /api/jobs/{job_id}` 提供使用者查詢自己背景任務的狀態與進度。
- Backend Dockerfile 改為固定 Python base image、非 root `app` user、`HEALTHCHECK` 與 unbuffered logging。

### 第四階段 migration 與 worker

Phase 4 migration：

```text
backend/database/migrations/20260831_phase4_operations.sql
```

必須先執行 Phase 3 修正版 migration，再執行 Phase 4 migration。部署後至少設定兩個獨立 scheduler/worker command：

```text
python scripts/process_graph_outbox.py 25
python scripts/process_background_jobs.py 5
```

兩個 worker 都不可在 web request process 內以 daemon thread 執行。Production/staging 必須使用各自獨立的 Supabase、Neo4j、Gemini、Cohere、`ENCRYPTION_KEY` 與 service-role secrets；service-role key 只放 backend/worker，不可放進 frontend。

### Health probe

```text
Liveness:  GET /health/live
Readiness: GET /health/ready
```

若 readiness 回傳 `503`，通常表示 Phase 3/Phase 4 migration 尚未執行，或 Supabase 無法連線；此時平台不應將該 instance 導入流量。
