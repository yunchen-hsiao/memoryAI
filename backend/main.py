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
        top_5_keywords = [item["name"] for item in keyword_distribution[:5]]
        entity_analysis = []
        
        # 將 memories 照日期排序，確保 latest_events 是最新的
        sorted_memories = sorted(memories, key=lambda x: x['diary_date'], reverse=True)
        
        for kw in top_5_keywords:
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
        
        # 3. 整理記憶上下文
        memory_context = ""
        if search_results.data and len(search_results.data) > 0:
            memory_context = "【系統擷取到的相關歷史記憶】\n"
            for mem in search_results.data:
                memory_context += f"- 日期：{mem['diary_date']} (主題：{mem['topic']})\n"
                memory_context += f"  記憶細節：{mem['summary']}\n"
            memory_context += "\n請根據以上歷史記憶，如果記憶內容與使用者的問題或當前對話上下文相關，就自然地融入對話中回答，展現出「你記得這些事」的陪伴感。如果無關，則正常對話即可，不需要刻意提及記憶。\n\n"
        else:
            print("=> 沒有找到相關的記憶。")
            
        # 4. Get current time for dynamic time perception
        current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        system_instruction = f"""
        你是一個充滿同理心、溫暖且能理解人類情感的智慧伴侶。
        目前系統的絕對時間為：{current_time_str}。
        請以此時間為基準，精確理解使用者提及的「今天」、「昨天」、「明天」或「上週」等相對時間概念。
        你的回應應該自然、溫暖，像一個傾聽者，用繁體中文回答。
        
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
        response = chat_session.send_message(request.message)
        
        return {"reply": response.text}
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
    topic: Optional[str] = None
    summary: Optional[str] = None
    emotion_score: Optional[int] = None
    keywords: Optional[List[str]] = None
    original_text: Optional[str] = None

class MemoryCreate(BaseModel):
    diary_date: str
    topic: str
    summary: str
    emotion_score: int
    keywords: List[str]
    original_text: str

@app.get("/api/memories")
def get_memories():
    try:
        response = supabase.table("memories").select("*").order("diary_date", desc=True).execute()
        return {"memories": response.data}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@app.put("/api/memories/{memory_id}")
def update_memory(memory_id: str, memory: MemoryUpdate):
    try:
        update_data = {k: v for k, v in memory.model_dump().items() if v is not None}
        if not update_data:
            return {"success": True}
        
        response = supabase.table("memories").update(update_data).eq("id", memory_id).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"error": str(e)}

@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str):
    try:
        response = supabase.table("memories").delete().eq("id", memory_id).execute()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/memories")
def create_memory(memory: MemoryCreate):
    try:
        response = supabase.table("memories").insert(memory.model_dump()).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
