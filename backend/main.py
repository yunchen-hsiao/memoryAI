import json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from supabase import create_client, Client

load_dotenv()

# Configure Supabase
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# Configure Gemini
client = genai.Client()

app = FastAPI(title="MemoryAI API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "MemoryAI Backend is running!"}

@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    try:
        # 從 Supabase 撈出所有記憶
        response = supabase.table("memories").select("diary_date, emotion_score, topic, keywords, summary").execute()
        memories = response.data

        if not memories:
            return {"emotion_trends": [], "topic_distribution": []}

        # 整理情緒趨勢 (按日期平均)
        date_scores = {}
        for m in memories:
            date = m['diary_date']
            score = m['emotion_score']
            if score is None: continue
            if date not in date_scores:
                date_scores[date] = []
            date_scores[date].append(score)
            
        emotion_trends = []
        for date in sorted(date_scores.keys()):
            avg_score = sum(date_scores[date]) / len(date_scores[date])
            # 找出當天最常出現的 topic
            topics_today = [m['topic'] for m in memories if m['diary_date'] == date]
            main_topic = max(set(topics_today), key=topics_today.count) if topics_today else ""
            
            emotion_trends.append({
                "date": date,
                "score": round(avg_score, 1),
                "main_topic": main_topic
            })
            
        # 整理關鍵字分佈
        keyword_counts = {}
        stop_words = {"聊天", "訊息", "回覆", "朋友" }
        
        for m in memories:
            keywords = m.get('keywords') or []
            for kw in keywords:
                # 過濾掉太長的句子或是無意義的常見字詞
                if not kw or len(kw) > 10 or kw in stop_words: continue 
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
            
        keyword_distribution = [
            {"name": k, "value": v} 
            for k, v in sorted(keyword_counts.items(), key=lambda item: item[1], reverse=True)
        ][:10] # 只取前 10 大關鍵字，並直接捨棄「其他」長尾數據
        
        # 準備大腦總覽數據
        total_days = len(date_scores)
        avg_overall_score = 0
        if total_days > 0:
            avg_overall_score = sum([sum(scores)/len(scores) for scores in date_scores.values()]) / total_days
        top_keyword = keyword_distribution[0]["name"] if keyword_distribution else "無"
        
        summary_stats = {
            "total_days": total_days,
            "avg_score": round(avg_overall_score, 1),
            "top_keyword": top_keyword
        }

        # 深度分析前五大核心實體
        # 只過濾出已經被 AI 認定為「人類/實體」並編譯進 entities 資料表的關鍵字
        entities_res = supabase.table("entities").select("name").execute()
        valid_entity_names = {e["name"] for e in entities_res.data} if entities_res.data else set()
        
        top_keywords = [item["name"] for item in keyword_distribution if item["name"] in valid_entity_names][:5]
        
        entity_analysis = []
        
        # 將 memories 照日期排序，確保 latest_events 是最新的
        sorted_memories = sorted(memories, key=lambda x: x['diary_date'], reverse=True)
        
        for kw in top_keywords:
            # 找出包含此關鍵字的記憶（放寬標準：不只看 keywords，連同 summary 也找，解決 AI 沒有標到 keyword 的遺漏問題）
            entity_events = []
            for m in sorted_memories:
                kws = m.get('keywords') or []
                summary = m.get('summary') or ''
                if kw in kws or kw in summary:
                    entity_events.append(m)
            
            # 計算平均分數
            scores = [m['emotion_score'] for m in entity_events if m.get('emotion_score') is not None]
            avg_score = sum(scores) / len(scores) if scores else 0
            
            # 計算共現詞
            co_occurrences = {}
            for m in entity_events:
                for other_kw in (m.get('keywords') or []):
                    if other_kw != kw and len(other_kw) <= 10:
                        co_occurrences[other_kw] = co_occurrences.get(other_kw, 0) + 1
            
            top_co_keywords = [k[0] for k in sorted(co_occurrences.items(), key=lambda x: x[1], reverse=True)[:5]]
            
            # 擷取最近三次互動摘要
            latest_events = [
                {"date": e['diary_date'], "summary": e.get('summary', '無摘要')}
                for e in entity_events[:3]
            ]
            
            entity_analysis.append({
                "name": kw,
                "mentions": len(entity_events),
                "avg_score": round(avg_score, 1),
                "co_keywords": top_co_keywords,
                "latest_events": latest_events
            })

        return {
            "emotion_trends": emotion_trends,
            "keyword_distribution": keyword_distribution,
            "summary_stats": summary_stats,
            "entity_analysis": entity_analysis
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error fetching dashboard stats: {e}")
        return {"error": str(e)}

def get_embedding(text: str) -> list[float]:
    """呼叫 Gemini 產生文字的向量 (Embedding)"""
    response = client.models.embed_content(
        model="gemini-embedding-2",
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY" # 搜尋用的 Task Type
        )
    )
    return response.embeddings[0].values

@app.post("/api/chat")
def chat(request: ChatRequest):
    try:
        # 1. 將使用者的問題轉成向量
        query_embedding = get_embedding(request.message)
        
        # 2. 向 Supabase 進行時間衰減相似度搜尋
        search_results = supabase.rpc(
            'search_memories', 
            {
                'query_embedding': query_embedding,
                'match_threshold': 0.4, # 相似度門檻
                'match_count': 5,      # 最多取 5 筆最相關的
                'time_weight_factor': 0.2 # 時間衰減權重 (0.2 表示輕微偏好近期的記憶)
            }
        ).execute()
        
        # 2.5 實體 (Entity) 雙重檢索
        # 抓取目前資料庫中所有的核心實體檔案
        entities_res = supabase.table("entities").select("*").execute()
        entity_context = ""
        if entities_res.data:
            mentioned_entities = [e for e in entities_res.data if e['name'] in request.message]
            if mentioned_entities:
                entity_context = "\n【核心人物檔案 (Entity Profiles)】\n系統偵測到使用者提及了以下核心人物，請嚴格參考這些人設檔案來進行行為分析：\n"
                for e in mentioned_entities:
                    entity_context += f"👤 {e['name']} (關係：{e['relationship']})\n"
                    entity_context += f"   行為分析：{e['description']}\n"
        
        # 3. 整理記憶上下文
        memory_context = ""
        if search_results.data and len(search_results.data) > 0:
            memory_context = "【系統擷取到的相關歷史記憶】\n"
            for mem in search_results.data:
                time_str = f" {mem.get('diary_time', '')}" if mem.get('diary_time') else ""
                memory_context += f"- 日期：{mem['diary_date']}{time_str} (主題：{mem['topic']})\n"
                memory_context += f"  記憶細節：{mem['summary']}\n"
            memory_context += "\n請根據以上歷史記憶，如果記憶內容與使用者的問題或當前對話上下文相關，就自然地融入對話中回答，展現出「你記得這些事」的陪伴感。如果無關，則正常對話即可，不需要刻意提及記憶。\n\n"
        else:
            print("=> 沒有找到相關的記憶。")
            
        # 4. Get current time for dynamic time perception
        current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        system_instruction = f"""
        你是一個敏銳、重視邏輯，但說話風格像是一個「亦師亦友的高階幕僚」或「專屬架構師」。
        你的任務是幫使用者（蕭蕭）分析她與他人的互動，拆解對方的行為模式與潛在邏輯。
        
        【回應風格準則】：
        1. 保持理性與客觀的分析，不需要過度煽情的安慰，但語氣請保持「自然、幽默、帶有人情味」，像一個聰明的朋友在跟你討論，絕對不要聽起來像冷冰冰的報告機器人。
        2. 善用條列式、結構化的方式拆解分析（例如：推測對方心理、行為動機、情境推測）。
        3. 可以適度穿插一些資訊/系統術語來比喻人類行為（例如：批次處理、休眠模式、Ping），作為一種有趣的幽默感，但不要滿口生硬的醫學或電腦專有名詞。
        4. 根據使用者提供的互動細節，給出具體且實用的「處置建議」或「下一步對策」。
        
        目前系統的絕對時間為：{current_time_str}。請以此時間為基準來理解「今天」、「昨天」等時間差。
        請用繁體中文回答。
        
        {entity_context}
        {memory_context}
        """
        
        # Format history
        formatted_history = []
        for msg in request.history:
            role = "user" if msg["role"] == "user" else "model"
            formatted_history.append({"role": role, "parts": [{"text": msg["content"]}]})
            
        chat_session = client.chats.create(
            model='gemini-2.5-flash',
            config=genai.types.GenerateContentConfig(
                system_instruction=system_instruction
            ),
            history=formatted_history
        )
        
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = chat_session.send_message(request.message)
                return {"reply": response.text}
            except Exception as e:
                if "503" in str(e) and attempt < max_retries - 1:
                    print(f"Chat API 503 Error. Retrying in 3 seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(3)
                else:
                    raise e
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error: {e}")
        return {"reply": f"抱歉，大腦暫時連線失敗，請稍後再試。錯誤原因: {str(e)}"}

@app.get("/api/dashboard/graph")
def get_dashboard_graph():
    try:
        response = supabase.table("memories").select("id, diary_date, emotion_score, topic, keywords, summary").execute()
        memories = response.data

        if not memories:
            return {"nodes": [], "links": []}

        nodes = []
        links = []
        
        # 1. 計算所有實體的出現次數
        stop_words = {"聊天", "訊息", "回覆", "晚餐", "午餐", "朋友", "我", "自己", "今天", "明天", "昨天", "感覺", "覺得", "事情", "時候", "最近", "有點", "一起", "一下", "一個"}
        keyword_counts = {}
        for m in memories:
            keywords = m.get('keywords') or []
            for kw in keywords:
                if not kw or len(kw) > 10 or kw in stop_words: continue 
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        
        # 只取前 8 大實體作為節點（避免圖表太過混亂）
        top_entities = [k for k, v in sorted(keyword_counts.items(), key=lambda item: item[1], reverse=True)[:8]]
        
        # 建立 Entity 節點
        entity_node_ids = set()
        for entity in top_entities:
            nodes.append({
                "id": f"entity_{entity}",
                "name": entity,
                "group": "entity",
                "val": keyword_counts[entity] * 2
            })
            entity_node_ids.add(f"entity_{entity}")

        # 建立 Memory 節點與連線
        memory_node_ids = set()
        
        for m in memories:
            m_id = f"mem_{m['id']}"
            m_kws = m.get('keywords') or []
            m_summary = m.get('summary') or ''
            
            # 檢查這個記憶是否包含了 top_entities 中的任何人事物
            matched_entities = []
            for entity in top_entities:
                if entity in m_kws or entity in m_summary:
                    matched_entities.append(entity)
                    
            if not matched_entities:
                continue 
                
            if m_id not in memory_node_ids:
                nodes.append({
                    "id": m_id,
                    "name": f"{m['diary_date']} {m.get('topic', '')}",
                    "group": "memory",
                    "val": 3,
                    "score": m.get('emotion_score', 50),
                    "summary": m_summary
                })
                memory_node_ids.add(m_id)
                
            # 建立記憶與實體之間的連線
            for entity in matched_entities:
                links.append({
                    "source": m_id,
                    "target": f"entity_{entity}",
                    "value": 1
                })

        return {
            "nodes": nodes,
            "links": links
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

# --- 記憶時光機 API (Phase 5.4) ---
from typing import Optional, List

class MemoryUpdate(BaseModel):
    diary_date: Optional[str] = None
    diary_time: Optional[str] = None
    topic: Optional[str] = None
    summary: Optional[str] = None
    emotion_score: Optional[int] = None
    keywords: Optional[List[str]] = None
    original_text: Optional[str] = None

class MemoryCreate(BaseModel):
    diary_date: str
    diary_time: Optional[str] = None
    topic: str
    summary: str
    emotion_score: int
    keywords: List[str]
    original_text: Optional[str] = ""
    content: Optional[str] = ""
    importance_weight: Optional[int] = 3

@app.get("/api/memories")
def get_memories():
    try:
        response = supabase.table("memories").select("*").order("diary_date", desc=True).execute()
        return {"memories": response.data}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@app.post("/api/memories")
def create_memory(memory: MemoryCreate):
    try:
        data = memory.model_dump()
        
        # 處理欄位對應：將 original_text 轉入 content
        if data.get('original_text'):
            data['content'] = data['original_text']
            
        if 'original_text' in data:
            del data['original_text']
            
        # 自動計算 embedding
        embedding_text = f"[{data.get('diary_date', '')}] 標籤:{data.get('topic', '')} - {data.get('summary', '')}。相關細節：{', '.join(data.get('keywords', []))}。原文：{data.get('content', '')}"
        data['embedding'] = get_embedding(embedding_text)
        
        response = supabase.table("memories").insert(data).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"error": str(e)}

@app.put("/api/memories/{memory_id}")
def update_memory(memory_id: str, memory: MemoryUpdate):
    try:
        update_data = {k: v for k, v in memory.model_dump().items() if v is not None}
        if not update_data:
            return {"success": True}
            
        if update_data.get('original_text'):
            update_data['content'] = update_data['original_text']
        if 'original_text' in update_data:
            del update_data['original_text']
            
        # 如果有更新到內容相關的欄位，重新計算 embedding
        if any(k in update_data for k in ['summary', 'topic', 'keywords', 'content', 'diary_date']):
            # 先取得原本的資料來補全
            old_data = supabase.table("memories").select("diary_date, topic, summary, keywords, content").eq("id", memory_id).execute().data[0]
            date = update_data.get('diary_date', old_data.get('diary_date', ''))
            topic = update_data.get('topic', old_data.get('topic', ''))
            summary = update_data.get('summary', old_data.get('summary', ''))
            keywords = update_data.get('keywords', old_data.get('keywords', []))
            content = update_data.get('content', old_data.get('content', ''))
            
            embedding_text = f"[{date}] 標籤:{topic} - {summary}。相關細節：{', '.join(keywords)}。原文：{content}"
            update_data['embedding'] = get_embedding(embedding_text)
        
        response = supabase.table("memories").update(update_data).eq("id", memory_id).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/chat/summarize")
def summarize_chat(request: ChatRequest):
    try:
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.datetime.now().strftime("%H:%M")
        
        chat_text = ""
        for msg in request.history:
            role = "AI" if msg['role'] == 'ai' or msg['role'] == 'model' else "我"
            chat_text += f"{role}: {msg['content']}\n"
            
        # 加上最後一句話
        chat_text += f"我: {request.message}\n"

        prompt = f"""
        你是一個記憶萃取專家。以下是我（蕭蕭）與 AI 的最新一段對話紀錄。
        這段對話可能包含了今天發生的事情、我的抱怨、或是新資訊。
        請判斷這段對話包含了「幾個獨立的事件或主題」。
        
        請將每個獨立事件切割出來，提取豐富細節，並輸出為純 JSON 陣列 (Array) 格式（不要包含 ```json 等 Markdown 標記，直接回傳 [ 開始的字串）：
        [
            {{
                "summary": "一段約50字的精要總結（請統一使用第一人稱「我」來代表蕭蕭）",
                "topic": "這個事件的主要標籤（簡短名詞），例如：感情、專題討論、閒聊",
                "keywords": ["關鍵字1", "關鍵字2", "具體人事物"],
                "emotion_score": 0到100的整數 (0是最負面悲傷，100是最快樂正面，50是平靜),
                "importance_weight": 1到5的整數 (1是最不重要，5是對人生影響重大),
                "content_chunk": "與這個事件相關的對話重點或原汁原味的金句紀錄",
                "diary_date": "{current_date}",
                "diary_time": "{current_time}"
            }}
        ]
        
        對話紀錄：
        {chat_text}
        """

        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    )
                )
                
                events = json.loads(response.text)
                return {"success": True, "events": events}
            except Exception as e:
                if "503" in str(e) and attempt < max_retries - 1:
                    print(f"Summarize API 503 Error. Retrying in 3 seconds... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(3)
                else:
                    raise e
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str):
    try:
        response = supabase.table("memories").delete().eq("id", memory_id).execute()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}



@app.post("/api/entities/build")
def trigger_build_entities():
    import subprocess
    import sys
    try:
        # 使用 sys.executable 確保背景執行時是使用當前 venv 的 python，而不是系統的 python
        subprocess.Popen([sys.executable, "scripts/build_entities.py"])
        return {"success": True, "message": "已成功觸發核心人物檔案編譯！系統正在背景努力更新大腦中。"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
