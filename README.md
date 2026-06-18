# MemoryAI - 你的專屬心靈大腦 🧠

MemoryAI 是一個結合 RAG（檢索增強生成）、情感分析與核心人物網路的智慧型日記系統。它不僅僅是一個對話機器人，更是一個能記住你喜怒哀樂、梳理人際關係、並且隨著你的傾訴而成長的「數位大腦」與「靈魂伴侶」。

## ✨ 核心功能

### 1. 溫馨治癒的對話空間 (Memory Chat)
- **自然傾訴**：就像和一個懂你的朋友聊天一樣，自由地分享你的一天。
- **智慧歸檔**：AI 會自動分析對話內容，將一段長篇對話智慧切分為多個獨立的「記憶事件」。
- **情感感知**：自動為每一段記憶打上情感分數 (0-100)，並提取核心關鍵字。

### 2. 歷史記憶流 (Memory Timeline)
- **手動記錄與編輯**：隨時手動寫下回憶，或修改過去的記憶。
- **視覺化情緒**：透過不同的色彩標籤，一眼看出每一段記憶的情緒色彩。
- **快速檢索**：支援透過關鍵字、主題快速找回塵封的記憶。

### 3. 大腦記憶儀表板 (Brain Dashboard)
- **情緒時光機**：追蹤你近期的情緒起伏曲線。
- **記憶雷達**：分析你生活中最常出現的關鍵字。
- **核心實體深度分析 (角色看板)**：
  - AI 會自動彙整出你生命中重要的人物或事物。
  - 計算他們對你帶來的情感影響力（正向或負向）。
  - 顯示共現網路與最近的互動回放。

### 4. 記憶星系網路圖 (Memory Graph)
- 將所有的記憶與核心人物視覺化為動態的星系網路。
- 點擊記憶行星，即可快速預覽該記憶的詳細內容與摘要。

---

## 🛠 技術架構

MemoryAI 採用了前後端分離的現代化架構，結合了向量資料庫與大型語言模型，打造出具備長效記憶能力的系統。

### 前端 (Frontend)
- **框架**: React (Vite)
- **樣式**: Tailwind CSS (溫暖治癒的石色/琥珀色系)
- **圖表與視覺化**: 
  - `recharts` (情緒曲線、關鍵字分佈)
  - `react-force-graph-2d` (記憶星系網路圖)
- **圖標庫**: `lucide-react`

### 後端 (Backend)
- **框架**: FastAPI (Python)
- **大語言模型 (LLM)**: Google Gemini API
  - 負責對話生成、記憶事件切分、摘要萃取與情緒分析。
  - 使用 Function Calling 確保輸出的結構化資料（如 JSON）。
- **向量資料庫**: Supabase (PostgreSQL + pgvector)
  - 儲存所有的記憶事件，並將內容透過嵌入模型轉化為 Vector 儲存。
  - 支援 RAG（Retrieval-Augmented Generation），在對話時透過向量相似度搜尋找回相關歷史記憶。

---

## 🚀 部署指南

### 前端 (Vercel)
1. 前端為標準的 Vite React 專案，已內建 `vercel.json`。
2. 直接將程式碼推送到 GitHub，登入 Vercel 點擊 "Import Project" 匯入即可。
3. **注意**: 部署前需將 `frontend/src` 中各檔案（如 `App.tsx`, `Dashboard.tsx`, `MemoryTimeline.tsx` 等）內寫死的 `http://localhost:8000` 替換為**您實際部署後的後端網址**，或使用環境變數（如 `import.meta.env.VITE_API_URL`）。

### 後端 (Render / Railway)
後端包含完整的 `Dockerfile` 與 `requirements.txt`，可無縫部署：
1. 將專案推送到 GitHub。
2. 在 Render 或 Railway 建立新的 Web Service 並選擇該 Repo，系統會自動辨識 Dockerfile 進行構建。
3. **必要環境變數 (Environment Variables) 設定**：
   - `GEMINI_API_KEY`: 您的 Google Gemini API 金鑰。
   - `SUPABASE_URL`: 您的 Supabase 專案網址。
   - `SUPABASE_KEY`: 您的 Supabase 專案匿名金鑰或 Service Role 金鑰。
4. 啟動後，後端將於 8000 port 提供服務。

---

> 「讓所有的回憶，都有一個溫暖的歸宿。」 - MemoryAI
