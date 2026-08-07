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
GEMINI_API_KEY=your_gemini_api_key
COHERE_API_KEY=your_cohere_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
ENCRYPTION_KEY=your_fernet_encryption_key   # 負責將使用者日記加密成亂碼的專屬金鑰
ADMIN_EMAIL=your_admin_email@example.com    # 管理員豁免信箱（此信箱存入的資料將不會被加密）

# Neo4j AuraDB（圖資料庫功能；未設定時圖相關 API 會自動停用，不影響其他功能）
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_neo4j_password

# 部署用（本機開發可省略）
ALLOWED_ORIGINS=https://your-frontend.vercel.app
```


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
| `migration` SQL | 既有 Supabase 部署需在 SQL Editor 執行 `backend/database/migrations/` 下的三個 migration：`20260804_add_memory_imports.sql`、`20260804_add_entities_updated_at.sql`、`20260804_add_chat_response_feedback.sql` |
| `migration` SQL | 既有 Supabase 部署需在 SQL Editor 執行 `backend/database/migrations/` 下的三個 migration：`20260804_add_memory_imports.sql`、`20260804_add_entities_updated_at.sql`、`20260804_add_chat_response_feedback.sql` |
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
