# MemoryAI (心靈伴侶 / 專屬大腦)

這是一個結合了 **RAG (檢索增強生成)** 與 **情感分析** 的全端 AI 專屬助理應用。
有別於市面上聊完就忘的 AI 聊天機器人，MemoryAI 能夠將你的對話、日記與情感波動「固化」為長期記憶，並透過向量資料庫隨時回想。它不僅是你的傾聽者，更是最了解你的人際關係與歷史軌跡的「高階專屬幕僚」。

---

## 核心功能介紹

### 1. 亦師亦友的 AI 幕僚 

搭載 Google Gemini 2.5 Flash 模型，AI 會在每次對話前，自動去大腦（資料庫）裡檢索與你對話相關的歷史記憶與人物設定。它記得你的朋友、你的煩惱，並且會用幽默、自然的人情味與你對話。

### 2. 記憶歸檔系統

RAG 系統的最強殺手鐧。當你跟 AI 聊完天、抱怨完之後，只需點擊「歸檔對話」，AI 就會自動將落落長的對話切分為多個「獨立事件」，自動提取摘要、下標籤、給予情緒分數，並在你確認後永久存入向量資料庫。

### 3. 情感紀錄儀表板

透過精美的視覺化圖表，讓你一眼看穿自己的內心狀態：

- **情緒波動折線圖**：追蹤你近期的情緒起伏。
- **主題頻率長條圖**：分析你最常思考或煩惱的事情。

### 4. 核心人物網

系統會自動在背景分析你的日記與對話，抓取出常出現的「人物」，建立專屬的角色看板。系統懂得過濾掉無關的地名或專案，只把真正重要的人際關係實體化，讓 AI 更懂你的人際網絡。

### 5. 記憶時光機

完整的 CRUD 介面，讓你隨時搜尋、回顧、手動新增或編輯過去的記憶碎片。所有的記憶都會被轉化為高維度向量，成為 AI 思考的養分。

---

## 技術架構

這個專案採用了現代化的前後端分離架構，結合了 Serverless 資料庫與最強大的開源套件：

### 前端 (Frontend)

- **核心框架**: React 18 + Vite (TypeScript)
- **UI & 樣式**: Tailwind CSS
- **圖表視覺化**: Recharts (響應式動態圖表)
- **Markdown 渲染**: React-Markdown + Remark-GFM
- **圖示庫**: Lucide React

### 後端 (Backend)

- **核心框架**: FastAPI (Python) - 提供極速的非同步 API 介面。
- **AI 模型**: Google GenAI SDK (`gemini-2.5-flash`) - 負責聊天、情緒分析、事件萃取、實體建模。
- **向量生成**: `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`) - 負責將繁體中文記憶轉化為 768 維的 Embedding 向量。

### 資料庫 (Database)

- **Supabase (PostgreSQL)**
  - 利用 `pgvector` 擴充套件，進行餘弦相似度 (Cosine Similarity) 語意搜尋。
  - 儲存關聯式資料（事件、日期、情緒分數）與非結構化文字。

---

## 如何運行

### 1. 環境變數設定

請在 `backend` 資料夾下建立 `.env` 檔案，填入以下金鑰：

```env
GEMINI_API_KEY=your_gemini_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_anon_key
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

---

## 系統架構亮點

1. **Human-in-the-Loop (人機協作)**：記憶歸檔時，AI 只做草稿，最終由人類確認修改後再寫入資料庫，確保資料污染率降到最低。
2. **自動錯誤重試 (Retry Mechanism)**：針對免費版 Gemini API 常見的 503 過載錯誤，後端已實作自動退避與重試機制，確保系統高可用性。
3. **RWD 響應式設計**：完美支援手機與電腦瀏覽，無論是通勤時快速歸檔對話，或是坐在電腦前查看深度儀表板，都能獲得最佳體驗。
