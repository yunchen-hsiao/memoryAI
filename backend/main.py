import json
import hashlib
from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import datetime
from dotenv import load_dotenv
# 初始化 Google Gemini 客戶端 (專供 Embedding 使用)
from google import genai
from google.genai import types
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

# 初始化 Cohere 客戶端 (專供文字生成)
import cohere
co = cohere.ClientV2(os.environ.get("COHERE_API_KEY"))
from supabase import create_client, Client

load_dotenv()
from security import encrypt_text, decrypt_text

# 初始化 Neo4j 圖資料庫連線
try:
    from graph_db import (sync_event_to_graph, get_full_graph, get_person_connections,
                          get_co_mentioned_keywords, get_person_relationship_graph)
    _neo4j_available = True
except Exception as _e:
    print(f"⚠️ Neo4j 模組載入失敗，圖資料庫功能將停用：{_e}")
    _neo4j_available = False

from services.entity_resolver import resolve_mentioned_entities
from services.entity_profile_service import update_entity_profiles

# Configure Supabase
supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(supabase_url, supabase_key)

# Configure Gemini
gemini_api_key = os.environ.get("GEMINI_API_KEY")
if not gemini_api_key:
    print("WARNING: GEMINI_API_KEY environment variable is missing!")
# client = genai.Client(api_key=gemini_api_key)

app = FastAPI(title="MemoryAI API")

# Configure CORS
# 瀏覽器規範不允許 allow_origins=["*"] 搭配 allow_credentials=True，
# 因此改用白名單機制。預設包含本機開發網址，正式環境網域請在 .env 的
# ALLOWED_ORIGINS 中設定（用逗號分隔多個網址，例如：
# ALLOWED_ORIGINS=https://your-app.vercel.app,https://your-domain.com）
_default_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_extra_origins = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
allowed_origins = list(dict.fromkeys(_default_origins + _extra_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str = ""
    history: list[dict] = []

# 情緒分數評分準則：統一給所有 AI 抽取事件的 prompt 使用，
# 避免 AI 僅依「事件表面敘述是否熱烈」機械式地打在 50 分附近，
# 而忽略使用者對特定人物/情境的主觀好感與期待感。
EMOTION_SCORE_GUIDE = """0到100的整數，請根據「使用者當下主觀感受到的正負向程度」評分，
        不是旁觀者對事件表面看起來熱烈與否的客觀判斷。校準參考：
          - 0-30：明顯負面（難過、生氣、失落、衝突、被忽略）
          - 40-60：平靜中性的日常瑣事，沒有明顯情緒起伏
          - 65-85：正面、開心、期待、有好感、感到被重視、享受互動
          - 85-100：非常快樂、興奮、重要的正面時刻
        ⚠️ 特別注意：如果使用者對某人有好感、喜歡、在意，即使對話內容表面平淡
        （例如只是一句閒聊訊息），只要使用者展現出期待、開心、投入或享受互動的語氣，
        都應給予偏高分數（65分以上），不要因為文字表面「看起來只是普通對話」而
        機械式地打 50 分左右。反之，若使用者明確表達失望、冷淡或不耐，也不要因為
        語氣平和就打高分。"""

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "MemoryAI Backend is running!"}

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # 透過 Supabase Auth 驗證 JWT
        user_res = supabase.auth.get_user(token)
        if not user_res or not user_res.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return user_res.user
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

@app.get("/api/dashboard/stats")
def get_dashboard_stats(current_user = Depends(get_current_user)):
    try:
        # 從 Supabase 撈出該使用者的所有記憶
        response = supabase.table("memories").select("diary_date, emotion_score, topic, keywords, summary").eq("user_id", current_user.id).execute()
        memories = response.data or []
        for m in memories:
            m['summary'] = decrypt_text(m.get('summary', ''))
            m['topic'] = decrypt_text(m.get('topic', ''))
            m['keywords'] = [decrypt_text(k) for k in (m.get('keywords') or [])]
        
        if not memories:
            return {
                "emotion_trends": [], 
                "keyword_distribution": [],
                "summary_stats": {"total_days": 0, "avg_score": 0, "top_keyword": "無"},
                "entity_analysis": []
            }

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

        # 深度分析所有出現在人物關係圖中的人物
        # 關係圖與角色看板共用 entities 表的人物白名單；不再限制為前五名。
        entities_res = supabase.table("entities").select("name").eq("user_id", current_user.id).execute()
        valid_entity_names = {
            e["name"] for e in (entities_res.data or []) if e.get("name")
        }

        # 只保留在目前記憶的 keywords 中確實出現過的人物，並依互動次數排序，
        # 讓角色看板的順序與人物關係圖的主要節點一致。
        entity_mention_counts = {
            name: sum(
                1 for m in memories
                if name in (m.get("keywords") or [])
            )
            for name in valid_entity_names
        }
        top_keywords = [
            name for name, count in sorted(
                entity_mention_counts.items(),
                key=lambda item: (-item[1], item[0])
            )
            if count > 0
        ]

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

CHAT_SOURCE_LIMIT = 8
CHAT_SOURCE_CONTEXT_LIMIT = 700
CHAT_CONTEXT_CHAR_BUDGET = 5_600


def get_embedding(text: str) -> list[float]:
    """呼叫 Gemini 產生文字的向量 (Embedding)。"""
    response = client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
    )
    return response.embeddings[0].values


def _compact_chat_text(text: str, limit: int) -> str:
    """Keep source excerpts readable while enforcing a deterministic context budget."""
    normalized = " ".join((text or "").replace("\r", "\n").split())
    return normalized if len(normalized) <= limit else f"{normalized[:limit].rstrip()}…"


def _fetch_chat_memories(user_id: str, memory_ids: set[str]) -> dict[str, dict]:
    """Fetch the encrypted source text only for already-selected retrieval candidates."""
    if not memory_ids:
        return {}
    response = supabase.table("memories").select(
        "id, diary_date, diary_time, topic, summary, content, emotion_score, importance_weight"
    ).eq("user_id", user_id).in_("id", list(memory_ids)).execute()
    return {str(memory["id"]): memory for memory in (response.data or [])}


def _rank_chat_candidates(
    vector_results: list[dict], graph_candidates: dict[str, dict]
) -> list[str]:
    """
    Merge semantic and graph evidence instead of letting either retrieval mode erase the other.
    Ranking uses source-local rank (robust across different score distributions), graph event
    importance, and a small graph-only bonus so an entity's timeline remains available.
    """
    vector_rank = {
        str(item["id"]): index
        for index, item in enumerate(vector_results)
        if item.get("id")
    }
    candidate_ids = set(vector_rank) | set(graph_candidates)
    vector_count = max(len(vector_rank), 1)
    graph_count = max(len(graph_candidates), 1)

    scored: list[tuple[float, str]] = []
    for memory_id in candidate_ids:
        score = 0.0
        if memory_id in vector_rank:
            semantic_rank_score = 1 - (vector_rank[memory_id] / vector_count)
            score += 0.75 * semantic_rank_score
        if memory_id in graph_candidates:
            graph = graph_candidates[memory_id]
            graph_rank_score = 1 - (graph["rank"] / graph_count)
            importance = max(0, min(float(graph.get("importance") or 3), 5)) / 5
            score += 0.25 * graph_rank_score + 0.10 * importance
        scored.append((score, memory_id))

    return [memory_id for _, memory_id in sorted(scored, reverse=True)[:CHAT_SOURCE_LIMIT]]


def _build_evidence_sources(memories_by_id: dict[str, dict], ranked_ids: list[str]) -> list[dict]:
    """Decrypt selected memory cards and build separate model/UI-safe evidence excerpts."""
    sources: list[dict] = []
    used_chars = 0
    for memory_id in ranked_ids:
        memory = memories_by_id.get(memory_id)
        if not memory or used_chars >= CHAT_CONTEXT_CHAR_BUDGET:
            continue

        topic = decrypt_text(memory.get("topic", "")) or "未分類事件"
        summary = decrypt_text(memory.get("summary", ""))
        source_text = decrypt_text(memory.get("content", "")) or summary
        remaining = CHAT_CONTEXT_CHAR_BUDGET - used_chars
        context_excerpt = _compact_chat_text(
            source_text, min(CHAT_SOURCE_CONTEXT_LIMIT, remaining)
        )
        if not context_excerpt:
            continue

        source_number = len(sources) + 1
        used_chars += len(context_excerpt)
        sources.append({
            "citation": f"S{source_number}",
            "memory_id": memory_id,
            "date": memory.get("diary_date"),
            "diary_time": memory.get("diary_time"),
            "topic": topic,
            "summary": _compact_chat_text(summary, 240),
            "excerpt": _compact_chat_text(source_text, 360),
            "context_excerpt": context_excerpt,
        })
    return sources


def _build_entity_context(user_id: str, mentioned_entities: list[dict]) -> str:
    """Person profiles are useful background, but never replace dated event evidence."""
    if not mentioned_entities:
        return ""

    lines = ["【人物背景（輔助脈絡，不是事件證據）】"]
    for entity in mentioned_entities:
        name = entity.get("name", "未命名人物")
        relationship = _compact_chat_text(entity.get("relationship", ""), 100)
        description = _compact_chat_text(entity.get("description", ""), 280)
        lines.append(f"- {name}｜關係：{relationship or '未編譯'}")
        if description:
            lines.append(f"  人物檔案：{description}")

        if _neo4j_available:
            try:
                co_keywords = get_co_mentioned_keywords(user_id, name, limit=3)
                names = [item.get("name") for item in co_keywords if item.get("name")]
                if names:
                    lines.append(f"  常見共現：{', '.join(names)}")
            except Exception as graph_error:
                print(f"⚠️ 讀取 {name} 的圖譜共現關係失敗：{graph_error}")
    return "\n".join(lines)


def _build_memory_context(sources: list[dict]) -> str:
    if not sources:
        return "【歷史記憶證據】\n本次沒有找到足以支持特定歷史判斷的記憶。"

    lines = ["【歷史記憶證據】"]
    for source in sources:
        time_text = f" {source['diary_time']}" if source.get("diary_time") else ""
        lines.extend([
            f"[{source['citation']}] {source['date']}{time_text}｜{source['topic']}",
            f"摘要：{source['summary'] or '（無摘要）'}",
            f"原文片段：{source['context_excerpt']}",
        ])
    return "\n".join(lines)


@app.post("/api/chat")
def chat(request: ChatRequest, current_user = Depends(get_current_user)):
    try:
        user_id = str(current_user.id)

        # 1. 人物精確比對：保留既有的全名/手動別名設計，不擅自猜測新別名。
        entities_res = supabase.table("entities").select("*").eq("user_id", current_user.id).execute()
        all_entities = entities_res.data or []
        for entity in all_entities:
            entity["relationship"] = decrypt_text(entity.get("relationship", ""))
            entity["description"] = decrypt_text(entity.get("description", ""))
        mentioned_entities = resolve_mentioned_entities(request.message, all_entities)

        # 2. Graph retrieval：命中人物時取得其事件時間線；仍會與向量結果合併。
        graph_candidates: dict[str, dict] = {}
        if mentioned_entities and _neo4j_available:
            try:
                for entity in mentioned_entities:
                    connections = get_person_connections(user_id, entity["name"], limit=30)
                    for rank, connection in enumerate(connections):
                        memory_id = str(connection.get("memory_id") or "")
                        if not memory_id:
                            continue
                        candidate = {
                            "rank": rank,
                            "importance": connection.get("importance_weight"),
                        }
                        existing = graph_candidates.get(memory_id)
                        if not existing or candidate["rank"] < existing["rank"]:
                            graph_candidates[memory_id] = candidate
            except Exception as graph_error:
                print(f"⚠️ Graph retrieval 失敗，將只使用向量檢索：{graph_error}")

        # 3. Vector retrieval：即使有圖譜命中仍照常執行，補到情境上相似的舊事件。
        vector_results: list[dict] = []
        try:
            query_embedding = get_embedding(request.message)
            vector_response = supabase.rpc(
                "search_memories",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": 0.4,
                    "match_count": 12,
                    "p_user_id": current_user.id,
                    "time_weight_factor": 0.2,
                }
            ).execute()
            vector_results = vector_response.data or []
        except Exception as vector_error:
            # Graph evidence can still support the answer when embeddings are temporarily unavailable.
            print(f"⚠️ Vector retrieval 失敗，將只使用圖譜證據：{vector_error}")

        ranked_ids = _rank_chat_candidates(vector_results, graph_candidates)
        memories_by_id = _fetch_chat_memories(user_id, set(ranked_ids))
        evidence_sources = _build_evidence_sources(memories_by_id, ranked_ids)
        memory_context = _build_memory_context(evidence_sources)
        entity_context = _build_entity_context(user_id, mentioned_entities)

        # 4. Long-term context is explicitly secondary to dated event evidence.
        life_context = _compact_chat_text(get_user_context(user_id), 650)
        current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        system_instruction = f"""
你是使用者的 MemoryAI：一個記得她故事、能一起拆解情境的聰明好友與幕僚。
你的首要責任不是提供萬用諮商建議，而是先聽懂使用者現在是在分享、吐槽、求判讀，還是明確要下一步策略。

【證據與誠實規則】
1. 「歷史記憶證據」是唯一可當作過去具體事實的資料。凡是根據它提出的具體主張，請在句末附上對應的 [S1]、[S2] 等引用；不要捏造引用。
2. 請清楚區分：使用者已說／記憶已記錄的事實、你的合理推論、以及無法確認的部分。不能把他人的內心動機說成已知事實。
3. 人物背景與長期脈絡僅供理解，不能取代有日期的事件證據；若它和事件證據衝突，以事件證據為準。
4. 若沒有相關歷史證據，直接坦白「我目前沒有找到能支持這個過去判斷的記憶」，不要用空泛心理學填滿答案。

【回應方式】
1. 配合使用者此刻的情緒與語氣：她在吐槽或分享時，先接住荒謬點與核心感受；沒有被要求時，不要自動變成教她溝通、叫她冷靜或要求她理解對方的說教機器。
2. 可以自然、幽默、帶有人情味，也可少量使用系統比喻；不要為了風格硬塞術語或誇大成戰報。
3. 若需要分析，先從具體行為與時間線下手，再提出「可能」的解讀。若使用者要求建議，再給少量、符合她已設下邊界的可執行選項。
4. 回答可用短段落或條列，但避免例行公事般的「猜測心理／建議對策」模板。
5. 一律使用繁體中文。

目前系統時間：{current_time_str}

{entity_context}

【長期脈絡（可能過時，僅作輔助）】
{life_context}

{memory_context}
"""

        # 只保留近期對話，並只轉送模型真正需要的 role/content 欄位。
        formatted_history = []
        for message in request.history[-15:]:
            content = message.get("content", "")
            if not content:
                continue
            role = "user" if message.get("role") == "user" else "assistant"
            formatted_history.append({"role": role, "content": content})

        messages = (
            [{"role": "system", "content": system_instruction}]
            + formatted_history
            + [{"role": "user", "content": request.message}]
        )
        response = co.chat(model="command-r-08-2024", messages=messages, max_tokens=4000)

        # context_excerpt is solely for the model; never return the longer version to the browser.
        public_sources = [
            {
                key: source[key]
                for key in ("citation", "memory_id", "date", "diary_time", "topic", "summary", "excerpt")
            }
            for source in evidence_sources
        ]
        retrieval_modes = []
        if graph_candidates:
            retrieval_modes.append("graph")
        if vector_results:
            retrieval_modes.append("vector")

        return {
            "reply": response.message.content[0].text,
            "sources": public_sources,
            "retrieval": {
                "mode": "+".join(retrieval_modes) or "none",
                "source_count": len(public_sources),
                "mentioned_entities": [entity["name"] for entity in mentioned_entities],
            },
        }

    except Exception as error:
        import traceback
        traceback.print_exc()
        return {"error": str(error)}

@app.get("/api/dashboard/graph")
def get_dashboard_graph(current_user = Depends(get_current_user)):
    try:
        # 從 Supabase 撈出該使用者的所有人物關係與記憶
        response = supabase.table("memories").select("id, diary_date, emotion_score, topic, keywords, summary").eq("user_id", current_user.id).execute()
        memories = response.data or []
        for m in memories:
            m['summary'] = decrypt_text(m.get('summary', ''))
            m['topic'] = decrypt_text(m.get('topic', ''))
            m['keywords'] = [decrypt_text(k) for k in (m.get('keywords') or [])]

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
    timezone: Optional[str] = None
    topic: Optional[str] = None
    summary: Optional[str] = None
    emotion_score: Optional[int] = None
    keywords: Optional[List[str]] = None
    original_text: Optional[str] = None
    content: Optional[str] = None
    importance_weight: Optional[int] = None

class MemoryCreate(BaseModel):
    diary_date: str
    diary_time: Optional[str] = None
    timezone: Optional[str] = None
    topic: str
    summary: str
    emotion_score: int
    keywords: List[str]
    original_text: Optional[str] = ""
    content: Optional[str] = ""
    importance_weight: Optional[int] = 3

class ImportSingleRequest(BaseModel):
    date_str: str
    content: str


def _normalize_import_content(content: str) -> str:
    """Normalize line endings/outer whitespace for stable import comparisons."""
    return content.replace("\r\n", "\n").replace("\r", "\n").strip()


def _import_content_hash(content: str) -> str:
    return hashlib.sha256(_normalize_import_content(content).encode("utf-8")).hexdigest()


def _get_latest_import_snapshot(user_id: str, date_str: str) -> dict | None:
    """Return the latest raw diary snapshot, if the tracking table is installed."""
    try:
        response = supabase.table("memory_imports").select(
            "source_hash, source_content"
        ).eq("user_id", user_id).eq("diary_date", date_str) \
            .order("created_at", desc=True).limit(1).execute()
        return response.data[0] if response.data else None
    except Exception as error:
        # Keep imports compatible with databases that have not run the migration yet.
        if "memory_imports" not in str(error):
            print(f"⚠️ 讀取匯入快照失敗：{error}")
        return None


def _save_import_snapshot(user_id: str, date_str: str, content: str, user_email: str) -> None:
    """Save a full encrypted source snapshot after all events are inserted."""
    normalized = _normalize_import_content(content)
    try:
        supabase.table("memory_imports").insert({
            "user_id": user_id,
            "diary_date": date_str,
            "source_hash": _import_content_hash(normalized),
            "source_content": encrypt_text(normalized, user_email),
        }).execute()
    except Exception as error:
        # The event import itself succeeded; surface migration instructions in logs.
        print(f"⚠️ 無法保存匯入快照（請先執行 memory_imports migration）：{error}")


@app.get("/api/memories")
def get_memories(current_user = Depends(get_current_user)):
    try:
        # 明確列出欄位，絕對不要用 select("*")。
        # embedding 是 3072 維向量，每筆記憶約 39KB，902 筆會產生約 35MB 的 JSON，
        # 解析成 Python 物件後記憶體用量會遠超 Render 免費層的 512MB 而被 OOM 中止。
        # 前端時間軸完全不需要向量，排除後 payload 從 35MB 降到約 1MB。
        response = supabase.table("memories").select(
            "id, diary_date, diary_time, timezone, topic, summary, "
            "emotion_score, importance_weight, keywords, content"
        ).eq("user_id", current_user.id).order("diary_date", desc=True).execute()
        for m in response.data:
            m['summary'] = decrypt_text(m.get('summary', ''))
            m['content'] = decrypt_text(m.get('content', ''))
            m['topic'] = decrypt_text(m.get('topic', ''))
            m['keywords'] = [decrypt_text(k) for k in (m.get('keywords') or [])]
            m['timezone'] = m.get('timezone') or 'Asia/Taipei'
        return {"memories": response.data}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@app.post("/api/memories")
def create_memory(memory: MemoryCreate, current_user = Depends(get_current_user)):
    try:
        data = memory.model_dump()
        
        # 加入 user_id
        data['user_id'] = current_user.id
        
        # 處理欄位對應：將 original_text 轉入 content
        if data.get('original_text'):
            data['content'] = data['original_text']
            
        if 'original_text' in data:
            del data['original_text']
            
        # 自動計算 embedding
        embedding_text = f"[{data.get('diary_date', '')}] 標籤:{data.get('topic', '')} - {data.get('summary', '')}。相關細節：{', '.join(data.get('keywords', []))}。原文：{data.get('content', '')}"
        data['embedding'] = get_embedding(embedding_text)
        
        # 加密
        data['summary'] = encrypt_text(data.get('summary', ''), current_user.email)
        data['content'] = encrypt_text(data.get('content', ''), current_user.email)
        data['topic'] = encrypt_text(data.get('topic', ''), current_user.email)
        data['keywords'] = [encrypt_text(k, current_user.email) for k in data.get('keywords', [])]
        
        response = supabase.table("memories").insert(data).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"error": str(e)}

@app.put("/api/memories/{memory_id}")
def update_memory(memory_id: str, memory: MemoryUpdate, current_user = Depends(get_current_user)):
    try:
        # 首先驗證這筆記憶是否屬於該使用者
        old_data_res = supabase.table("memories").select("user_id, diary_date, topic, summary, keywords, content").eq("id", memory_id).execute()
        if not old_data_res.data or old_data_res.data[0].get('user_id') != current_user.id:
            return {"error": "Unauthorized or memory not found"}
            
        old_data = old_data_res.data[0]
        # 解密 old_data
        old_data['summary'] = decrypt_text(old_data.get('summary', ''))
        old_data['content'] = decrypt_text(old_data.get('content', ''))
        old_data['topic'] = decrypt_text(old_data.get('topic', ''))
        old_data['keywords'] = [decrypt_text(k) for k in (old_data.get('keywords') or [])]
        
        update_data = {k: v for k, v in memory.model_dump().items() if v is not None}
        if not update_data:
            return {"success": True}
            
        if update_data.get('original_text'):
            update_data['content'] = update_data['original_text']
        if 'original_text' in update_data:
            del update_data['original_text']
            
        # 如果有更新到內容相關的欄位，重新計算 embedding
        if any(k in update_data for k in ['summary', 'topic', 'keywords', 'content', 'diary_date']):
            date = update_data.get('diary_date', old_data.get('diary_date', ''))
            topic = update_data.get('topic', old_data.get('topic', ''))
            summary = update_data.get('summary', old_data.get('summary', ''))
            keywords = update_data.get('keywords', old_data.get('keywords', []))
            content = update_data.get('content', old_data.get('content', ''))
            
            embedding_text = f"[{date}] 標籤:{topic} - {summary}。相關細節：{', '.join(keywords)}。原文：{content}"
            update_data['embedding'] = get_embedding(embedding_text)
            
        # 在寫入資料庫前，將要更新的字串加密
        if 'summary' in update_data:
            update_data['summary'] = encrypt_text(update_data['summary'], current_user.email)
        if 'content' in update_data:
            update_data['content'] = encrypt_text(update_data['content'], current_user.email)
        if 'topic' in update_data:
            update_data['topic'] = encrypt_text(update_data['topic'], current_user.email)
        if 'keywords' in update_data:
            update_data['keywords'] = [encrypt_text(k, current_user.email) for k in update_data['keywords']]
        
        response = supabase.table("memories").update(update_data).eq("id", memory_id).eq("user_id", current_user.id).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/chat/summarize")
def summarize_chat(request: ChatRequest, current_user = Depends(get_current_user)):
    try:
        current_date = datetime.datetime.now().strftime("%Y-%m-%d")
        current_time = datetime.datetime.now().strftime("%H:%M")
        
        chat_text = ""
        for msg in request.history:
            role = "AI" if msg['role'] == 'ai' or msg['role'] == 'model' else "我"
            chat_text += f"{role}: {msg['content']}\n"
            
        if request.message:
            chat_text += f"我: {request.message}\n"

        # 讀取前情提要
        life_context = get_user_context(current_user.id)

        prompt = f"""
        你是一個記憶萃取專家，正在閱讀一部連續的個人日記。
        
        【前情提要 — 截至目前為止的人生背景】
        {life_context}
        
        以下是使用者與 AI 的最新一段對話紀錄。
        請根據前情提要分析這段對話，判斷包含了「幾個獨立的事件或主題」。
        請將每個獨立事件切割出來，並輸出為純 JSON 陣列 (Array) 格式（不要包含 ```json 標記）：
        [
            {{
                "involved_people": ["真正參與此事件的具體人名"],
                "exact_quote": "請從原文中完全『一字不漏』地擷取出與此事件對應的段落。絕對禁止改寫、總結或腦補！",
                "summary": "一段約60字的精要總結（請統一使用第一人稱「我」，如有跨事件關聯請自然提及）",
                "topic": "這個事件的主要標籤（簡短名詞）",
                "keywords": ["具體人名", "地名", "獨特物件"],
                "emotion_score": {EMOTION_SCORE_GUIDE},
                "importance_weight": 1到5的整數,
                "diary_date": "{current_date}",
                "diary_time": "{current_time}",
                "timezone": "標準時區字串，例如 Pacific/Auckland，若未提及則填 Asia/Taipei"
            }}
        ]
        最後，請在陣列的最後加上一個特殊物件：
        {{ "__context_update__": "根據今天發生的所有事情，請用繁體中文更新並補充「前情提要」。保持在300字以內，重點保留重要人物的現況、未完結的事件進展、使用者目前的情緒狀態與重要計畫。" }}
        
        【⚠️ 嚴格防幻覺與擷取警告】
        1. 絕對禁止將不同時間、不同場合發生的人事物合併！
        2. 如果對話寫「我跟A去了某地，後來遇到B」，在事件摘要中必須明確分開，絕對不能寫成「我跟A還有B一起去了某地」。
        3. summary 裡面提到的人物，必須嚴格對應到 involved_people 陣列裡的人物。如果他沒有參與該事件，嚴禁在 summary 中將他與該事件掛鉤！
        4. 【JSON 格式嚴格要求】輸出 JSON 時，請務必正確處理特殊字元跳脫！特別是 `exact_quote` 中的內容，遇到雙引號 `"` 請替換為 `\\"`，遇到換行請替換為 `\\n`，絕對不能破壞 JSON 的合法性！
        
        對話紀錄：
        {chat_text}
        """

        import time
        max_retries = 3
        all_items = None
        for attempt in range(max_retries):
            try:
                # response = client.models.generate_content(
                #     model='gemini-2.5-flash-lite',
                #     contents=prompt,
                #     config=types.GenerateContentConfig(
                #         response_mime_type="application/json",
                #     )
                # )
                # all_items = json.loads(response.text)
                
                response = co.chat(
                    model='command-r-08-2024',
                    messages=[{"role": "user", "content": prompt}]
                )
                
                raw_text = response.message.content[0].text.strip()
                start_idx = raw_text.find('[')
                end_idx = raw_text.rfind(']')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    raw_text = raw_text[start_idx:end_idx+1]
                else:
                    start_idx = raw_text.find('{')
                    end_idx = raw_text.rfind('}')
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        raw_text = raw_text[start_idx:end_idx+1]
                
                all_items = json.loads(raw_text, strict=False)
                break
            except Exception as e:
                if "503" in str(e) and attempt < max_retries - 1:
                    time.sleep(3)
                elif attempt == max_retries - 1:
                    raise e
                    
        # 將 context_update 與實際事件分開回傳
        context_update = None
        real_events = []
        for item in all_items:
            if "__context_update__" in item:
                context_update = item["__context_update__"]
            else:
                real_events.append(item)
        if context_update:
            update_user_context(current_user.id, context_update)
        return {"success": True, "events": real_events}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/api/memories/monthly_summary")
def monthly_summary(year: int, month: int, force_regenerate: bool = False, current_user = Depends(get_current_user)):
    """For the Dashboard: generate a narrative story summary for a given month."""
    import os, json
    CACHE_FILE = "monthly_summaries_cache.json"
    
    cache_key = f"{year:04d}-{month:02d}"
    user_cache = {}
    
    # 讀取本地快取
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                user_cache = json.load(f)
        except Exception:
            user_cache = {}
            
    user_id = str(current_user.id)
    if user_id not in user_cache:
        user_cache[user_id] = {}
        
    # 如果不是強制重新生成，且快取中有資料，直接回傳
    if not force_regenerate and cache_key in user_cache[user_id]:
        encrypted_summary = user_cache[user_id][cache_key]
        summary = decrypt_text(encrypted_summary)
        return {"success": True, "summary": summary, "cached": True}

    try:
        import calendar
        # 查詢該月的所有記憶（用 calendar.monthrange 取得該月實際最後一天，避免 31 日不存在的問題）
        last_day = calendar.monthrange(year, month)[1]
        date_from = f"{year:04d}-{month:02d}-01"
        date_to = f"{year:04d}-{month:02d}-{last_day:02d}"
        res = supabase.table("memories") \
            .select("summary, topic, diary_date, diary_time, keywords, emotion_score") \
            .eq("user_id", current_user.id) \
            .gte("diary_date", date_from) \
            .lte("diary_date", date_to) \
            .order("diary_date").execute()
        
        if not res.data:
            return {"success": True, "summary": None, "message": "這個月份還沒有任何記憶。"}

        # 解密直接用於 Prompt
        memory_lines = []
        for m in res.data:
            s = decrypt_text(m.get('summary', ''))
            t = decrypt_text(m.get('topic', ''))
            memory_lines.append(f"[{m['diary_date']}] {t}: {s}")

        memories_text = "\n".join(memory_lines)
        prompt = f"""
        以下是一位使用者在 {year}年{month}月的所有記憶片段：

        {memories_text}

        請用溫暖、帶點文學性的文字，以第一人稱「我」，將這個月的所有事情織成一篇「本月發生故事小結」。
        - 請突顯重要的人物互動、情感線索、有趣的小事、或重要的亮點。
        - 如果有明顯的故事線索（如感情線、專案進展），請自然地織入。
        - 長度約 200-400 字，請用繁體中文寫作。
        - 直接回傳純文字內容，不要加標題。
        """

        response = co.chat(
            model='command-r-08-2024',
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000
        )
        summary_text = response.message.content[0].text.strip()
        
        # 存入快取（用 user_email 加密後儲存）
        user_cache[user_id][cache_key] = encrypt_text(summary_text, current_user.email)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(user_cache, f, ensure_ascii=False, indent=2)
            
        return {"success": True, "summary": summary_text, "memory_count": len(res.data), "cached": False}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: str, current_user = Depends(get_current_user)):
    try:
        response = supabase.table("memories").delete().eq("id", memory_id).eq("user_id", current_user.id).execute()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


# --- 全局脈絡 (Global Rolling Context) Helpers ---
def get_user_context(user_id: str) -> str:
    """從資料庫取得使用者目前的人生背景前情提要"""
    try:
        res = supabase.table("user_contexts").select("life_context").eq("user_id", user_id).limit(1).execute()
        if res.data:
            return res.data[0].get("life_context", "這是一段全新的人生故事紀錄，目前還沒有任何前情提要。")
    except:
        pass
    return "這是一段全新的人生故事紀錄，目前還沒有任何前情提要。"

def update_user_context(user_id: str, new_context: str):
    """更新使用者的人生背景前情提要"""
    try:
        supabase.table("user_contexts").upsert({
            "user_id": user_id,
            "life_context": new_context,
            "updated_at": datetime.datetime.utcnow().isoformat()
        }).execute()
    except Exception as e:
        print(f"⚠️ 更新 user_context 失敗: {e}")

@app.post("/api/import/single")
def import_single_day(request: ImportSingleRequest, background_tasks: BackgroundTasks, current_user = Depends(get_current_user)):
    try:
        normalized_content = _normalize_import_content(request.content)
        if not normalized_content:
            return {"success": False, "error": "日記內容不能是空白。"}

        # 以內容快照判斷重複，而不是只看日期。
        # 同一天若是舊內容加上新段落，只分析新增的尾端。
        source_hash = _import_content_hash(normalized_content)
        snapshot = _get_latest_import_snapshot(str(current_user.id), request.date_str)
        if snapshot and snapshot.get("source_hash") == source_hash:
            return {"success": True, "skipped": True, "message": "Content already imported"}

        existing_res = supabase.table('memories').select('id, content') \
            .eq('diary_date', request.date_str).eq('user_id', current_user.id).execute()
        existing_event_contents = {
            _normalize_import_content(decrypt_text(row.get("content", "")))
            for row in (existing_res.data or [])
            if row.get("content")
        }

        analysis_content = normalized_content
        if snapshot and snapshot.get("source_content"):
            previous_content = _normalize_import_content(
                decrypt_text(snapshot["source_content"])
            )
            if previous_content and normalized_content.startswith(previous_content):
                analysis_content = normalized_content[len(previous_content):].strip()
                if not analysis_content:
                    return {"success": True, "skipped": True, "message": "Content already imported"}

        # 讀取目前的人生脈絡前情提要
        life_context = get_user_context(current_user.id)

        # 3. 呼叫分析工具 (帶入前情提要)
        prompt = f"""
        你現在是一個專業的心理分析師與記憶萃取專家，正在閱讀一部連續的個人生活日記。

        【前情提要 — 截至目前為止的人生背景】
        {life_context}

        請根據以上前情提要，閱讀以下 {request.date_str} 的日記內容，並判斷這篇日記包含了「幾個獨立的事件或主題」。
        如果今天的事件與前情提要中的人物或事件有所關聯，請在 summary 中自然地點出前後因果。
        請將每個獨立事件切割出來，提取豐富細節，並輸出為一個純 JSON 陣列 (Array) 格式（不要包含 ```json 等 Markdown 標記）：
        [
            {{
                "involved_people": ["真正參與此事件的具體人名"],
                "exact_quote": "請從原文中完全『一字不漏』地擷取出與此事件對應的段落。絕對禁止改寫、總結或腦補！",
                "summary": "一段約60字的精要總結（請統一使用第一人稱「我」，如有跨事件關聯請自然提及）",
                "topic": "這個事件的主要標籤（簡短名詞），例如：感情、專題討論、鋼琴社",
                "keywords": ["具體人名", "地名", "獨特物件"], // 排除「聊天、訊息、朋友、我」等無意義通稱
                "emotion_score": {EMOTION_SCORE_GUIDE},
                "importance_weight": 1到5的整數 (1是最不重要，5是對人生影響重大),
                "diary_time": "HH:MM 格式，若無則填 null",
                "timezone": "標準時區字串，例如 Pacific/Auckland，若無則填 Asia/Taipei"
            }}
        ]
        最後，請在 JSON 陣列的最後加上一個特殊物件（作為最後一個元素）：
        {{ "__context_update__": "根據今天發生的所有事情，請用繁體中文更新並補充「前情提要」，請整合舊的前情提要內容，加入今天的新進展。請使用第一人稱「我」的視角來撰寫。保持在300字以內，重點保留重要人物的現況、未完結的事件進展、使用者目前的情緒狀態與重要計畫。\n【嚴重警告】絕對不可以竄改或替換任何人名！請完全照抄原文出現的名字，不要用同音字替換！" }}

        【⚠️ 嚴格防幻覺與擷取警告】
        1. 絕對禁止將不同時間、不同場合發生的人事物合併！
        2. 如果日記寫「我跟A去了某地，後來遇到B」，在事件摘要中必須明確分開，絕對不能寫成「我跟A還有B一起去了某地」。
        3. summary 裡面提到的人物，必須嚴格對應到 involved_people 陣列裡的人物。如果他沒有參與該事件，嚴禁在 summary 中將他與該事件掛鉤！
        4. 【JSON 格式嚴格要求】輸出 JSON 時，請務必正確處理特殊字元跳脫！特別是 `exact_quote` 中的內容，遇到雙引號 `"` 請替換為 `\\"`，遇到換行請替換為 `\\n`，絕對不能破壞 JSON 的合法性！

        如果整篇日記只有一個主題，就回傳兩個元素的陣列（一個事件 + 一個 __context_update__）。
        日記內容：
        {analysis_content}
        """

        import time
        max_retries = 3
        events = None
        for attempt in range(max_retries):
            try:
                # response = client.models.generate_content(
                # model='gemini-2.5-flash-lite',
                #     contents=prompt,
                #     config=types.GenerateContentConfig(response_mime_type="application/json")
                # )
                # events = json.loads(response.text)
                
                response = co.chat(
                    model='command-r-08-2024',
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=4000
                )
                
                raw_text = response.message.content[0].text.strip()
                start_idx = raw_text.find('[')
                end_idx = raw_text.rfind(']')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    raw_text = raw_text[start_idx:end_idx+1]
                else:
                    start_idx = raw_text.find('{')
                    end_idx = raw_text.rfind('}')
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        raw_text = raw_text[start_idx:end_idx+1]
                
                events = json.loads(raw_text, strict=False)
                break
            except Exception as e:
                if "503" in str(e) and attempt < max_retries - 1:
                    time.sleep(3)
                elif attempt == max_retries - 1:
                    raise e
                    
        if not events:
            return {"success": False, "error": "Failed to parse events"}

        # 4. 抽取 context_update 並分開正式事件
        context_update = None
        real_events = []
        for ev in events:
            if "__context_update__" in ev:
                context_update = ev["__context_update__"]
            else:
                real_events.append(ev)

        inserted_count = 0
        skipped_event_count = 0
        for event in real_events:
            event_quote = _normalize_import_content(
                str(event.get("exact_quote") or analysis_content)
            )
            # 舊版本沒有 source snapshot 時，仍以事件原文做第二層去重。
            if event_quote and event_quote in existing_event_contents:
                skipped_event_count += 1
                continue

            embedding_text = f"[{request.date_str}] 標籤:{event.get('topic','')} - {event.get('summary','')}。相關細節：{', '.join(event.get('keywords',[]))}。原文：{analysis_content}"
            embedding = get_embedding(embedding_text)
            
            import re
            diary_time = event.get("diary_time")
            if diary_time == "null" or diary_time == "" or diary_time is None:
                diary_time = None
            else:
                time_match = re.search(r"(\d{2}:\d{2})", str(diary_time))
                diary_time = time_match.group(1) if time_match else None
                
            timezone = event.get("timezone")
            if timezone == "null" or timezone == "":
                timezone = None

            data = {
                "user_id": current_user.id,
                "diary_date": request.date_str,
                "diary_time": diary_time,
                "timezone": timezone,
                "topic": encrypt_text(event.get("topic", ""), current_user.email),
                "summary": encrypt_text(event.get("summary", ""), current_user.email),
                "keywords": [encrypt_text(k, current_user.email) for k in event.get("keywords", []) if k not in ["蕭筠蓁", "我", "自己"]],
                "emotion_score": event.get("emotion_score", 50),
                "importance_weight": event.get("importance_weight", 3),
                "content": encrypt_text(event_quote, current_user.email),  # 擷取單一事件的原文片段，不儲存一整天的全文
                "embedding": embedding
            }
            res = supabase.table("memories").insert(data).execute()
            inserted_count += 1
            if event_quote:
                existing_event_contents.add(event_quote)
            
            # 將事件同步至圖資料庫（放在背景執行，不卡住前端體驗）
            # 注意：只同步結構化資訊（人物關聯、日期、分數），不寫入 topic/summary 內容明文
            if _neo4j_available and res.data:
                memory_id = res.data[0].get("id")
                background_tasks.add_task(
                    sync_event_to_graph,
                    str(current_user.id),
                    str(memory_id),
                    request.date_str,
                    [k for k in event.get("keywords", []) if k not in ["蕭筠蓁", "我", "自己"]],
                    event.get("emotion_score", 50),
                    event.get("importance_weight", 3)
                )

        # 所有事件完成後才保存完整來源；下次同日追加時可只分析新增尾端。
        _save_import_snapshot(
            str(current_user.id), request.date_str, normalized_content, current_user.email
        )

        # 5. 更新使用者的全局脈絡
        if context_update:
            update_user_context(current_user.id, context_update)

        # 6. 背景局部更新本次匯入事件中提到的人物檔案（不重跑全庫，只處理本次提到的人）
        mentioned_names = set()
        for event in real_events:
            mentioned_names.update(
                k for k in event.get("keywords", []) if k not in ["蕭筠蓁", "我", "自己"]
            )
        if mentioned_names:
            started = _start_background_function_job(
                str(current_user.id),
                "entity_profile",
                update_entity_profiles,
                str(current_user.id),
                list(mentioned_names)
            )
            if not started:
                print(f"⏭️ 使用者 {current_user.id} 的人物檔案更新任務已在執行中，本次跳過。")

        return {
            "success": True,
            "inserted_count": inserted_count,
            "skipped_event_count": skipped_event_count,
            "appended": analysis_content != normalized_content,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# ── 圖資料庫 API (Neo4j) ─────────────────────────────────────────────────

@app.get("/api/graph")
def get_graph_data(current_user = Depends(get_current_user)):
    """Takes the full graph data from Neo4j for visualization."""
    if not _neo4j_available:
        return {"error": "Neo4j 圖資料庫目前不可用"}
    try:
        data = get_full_graph(str(current_user.id))
        return {"success": True, **data}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/dashboard/relationship_heatmap")
def get_relationship_heatmap(current_user = Depends(get_current_user)):
    """
    人物 × 月份的情緒熱力圖資料。
    對 entities 表中的每個人物，逐月聚合互動次數與平均情緒分數，
    用來觀察「每段關係隨時間的情緒變化」。
    資料全部來自 Supabase（需解密 keywords/summary 做人物比對），不依賴 Neo4j。
    """
    try:
        entities_res = supabase.table("entities").select("name") \
            .eq("user_id", current_user.id).execute()
        person_names = [e["name"] for e in (entities_res.data or []) if e.get("name")]
        if not person_names:
            return {
                "success": True, "months": [], "persons": [],
                "message": "尚未編譯核心人物檔案，請先執行「編譯核心人物檔案」。"
            }

        mem_res = supabase.table("memories").select("diary_date, emotion_score, keywords, summary") \
            .eq("user_id", current_user.id).execute()
        memories = mem_res.data or []
        if not memories:
            return {"success": True, "months": [], "persons": []}

        for m in memories:
            m["keywords"] = [decrypt_text(k) for k in (m.get("keywords") or [])]
            m["summary"] = decrypt_text(m.get("summary", ""))

        # 收集所有出現過的月份（YYYY-MM），依時間排序
        all_months = sorted({
            (m.get("diary_date") or "")[:7]
            for m in memories if m.get("diary_date")
        })

        persons = []
        for name in person_names:
            # 與 dashboard entity_analysis 一致的比對方式：keywords 或 summary 命中
            related = [
                m for m in memories
                if name in (m.get("keywords") or []) or name in (m.get("summary") or "")
            ]
            if not related:
                continue

            by_month: dict[str, list[int]] = {}
            for m in related:
                month = (m.get("diary_date") or "")[:7]
                score = m.get("emotion_score")
                if not month or score is None:
                    continue
                by_month.setdefault(month, []).append(score)

            cells = [
                {
                    "month": month,
                    "count": len(scores),
                    "avg_score": round(sum(scores) / len(scores), 1),
                }
                for month, scores in sorted(by_month.items())
            ]
            all_scores = [s for scores in by_month.values() for s in scores]

            persons.append({
                "name": name,
                "total_count": len(related),
                "avg_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
                "cells": cells,
            })

        # 互動次數多的人物排在前面
        persons.sort(key=lambda p: p["total_count"], reverse=True)

        return {"success": True, "months": all_months, "persons": persons}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.get("/api/graph/persons")
def get_persons_graph(current_user = Depends(get_current_user)):
    """
    人物中心的關係圖：只保留 entities 表中已被判定為人物的節點，
    並附上每個人物的平均情緒分數、互動次數與人物檔案，供前端做顏色/大小編碼。
    """
    if not _neo4j_available:
        return {"error": "Neo4j 圖資料庫目前不可用"}
    try:
        entities_res = supabase.table("entities").select("name, description, relationship") \
            .eq("user_id", current_user.id).execute()
        entities = entities_res.data or []
        if not entities:
            return {
                "success": True, "nodes": [], "links": [],
                "message": "尚未編譯核心人物檔案，請先執行「編譯核心人物檔案」。"
            }

        person_names = [e["name"] for e in entities if e.get("name")]
        graph = get_person_relationship_graph(str(current_user.id), person_names)

        # 把人物檔案（需解密）併入節點資料，讓前端點擊時可直接顯示
        profile_by_name = {
            e["name"]: {
                "description": decrypt_text(e.get("description", "")),
                "relationship": decrypt_text(e.get("relationship", "")),
            }
            for e in entities if e.get("name")
        }
        for node in graph["nodes"]:
            profile = profile_by_name.get(node["id"], {})
            node["description"] = profile.get("description", "")
            node["relationship"] = profile.get("relationship", "")

        return {"success": True, **graph}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/api/graph/person/{person_name}")
def get_person_graph(person_name: str, current_user = Depends(get_current_user)):
    """Query all events related to a specific person."""
    if not _neo4j_available:
        return {"error": "Neo4j 圖資料庫目前不可用"}
    try:
        # Neo4j 只回傳結構化資訊（memory_id, date, emotion_score, importance_weight），
        # 不含事件內容明文，需回 Supabase 依 memory_id 查詢並解密取得實際內容。
        connections = get_person_connections(str(current_user.id), person_name)
        memory_ids = [c["memory_id"] for c in connections if c.get("memory_id")]

        events = []
        if memory_ids:
            res = supabase.table("memories").select("id, diary_date, diary_time, topic, summary, emotion_score, importance_weight") \
                .eq("user_id", current_user.id) \
                .in_("id", memory_ids) \
                .execute()
            memories_by_id = {str(m["id"]): m for m in (res.data or [])}
            for c in connections:
                m = memories_by_id.get(str(c.get("memory_id")))
                if not m:
                    continue
                events.append({
                    "date": m.get("diary_date"),
                    "topic": decrypt_text(m.get("topic", "")),
                    "summary": decrypt_text(m.get("summary", "")),
                    "emotion_score": m.get("emotion_score"),
                    "importance_weight": m.get("importance_weight"),
                })

        co_mentions = get_co_mentioned_keywords(str(current_user.id), person_name)
        return {"success": True, "events": events, "co_mentioned": co_mentions}
    except Exception as e:
        return {"error": str(e)}

# --- 背景腳本併發保護 ---
# 避免同一個使用者對同一種背景任務（圖譜同步 / 實體編譯）連續觸發多個行程同時執行，
# 造成 Neo4j / Supabase / Gemini API 的資源競爭。
# 注意：此鎖僅存在於單一 Python 行程的記憶體中，若後端以多個 worker 行程部署
# （例如 uvicorn --workers > 1 或多台伺服器），無法跨行程互相保護，屆時需改用
# Redis 或資料庫作為共享鎖。
import subprocess
import threading

_running_jobs: set[tuple[str, str]] = set()
_jobs_lock = threading.Lock()

def _start_background_job(user_id: str, job_type: str, cmd: list[str], cwd: str | None = None) -> bool:
    """嘗試啟動一個背景任務（獨立子行程）。若該使用者的同類任務已在執行中，回傳 False 並不會啟動新行程。"""
    key = (user_id, job_type)
    with _jobs_lock:
        if key in _running_jobs:
            return False
        _running_jobs.add(key)

    def _run():
        try:
            proc = subprocess.Popen(cmd, cwd=cwd)
            proc.wait()
        except Exception as e:
            print(f"⚠️ 背景任務執行失敗 ({job_type}, user={user_id}): {e}")
        finally:
            with _jobs_lock:
                _running_jobs.discard(key)

    threading.Thread(target=_run, daemon=True).start()
    return True


def _start_background_function_job(user_id: str, job_type: str, func, *args, **kwargs) -> bool:
    """
    嘗試啟動一個背景任務（同行程內直接呼叫 Python 函式，而非 subprocess）。
    沿用與 _start_background_job 相同的 (_jobs_lock, _running_jobs) 併發保護語意，
    適合輕量、不需要獨立子行程隔離的任務（例如局部更新人物檔案）。
    若該使用者的同類任務已在執行中，回傳 False 並不會啟動新任務。
    """
    key = (user_id, job_type)
    with _jobs_lock:
        if key in _running_jobs:
            return False
        _running_jobs.add(key)

    def _run():
        try:
            func(*args, **kwargs)
        except Exception as e:
            print(f"⚠️ 背景任務執行失敗 ({job_type}, user={user_id}): {e}")
        finally:
            with _jobs_lock:
                _running_jobs.discard(key)

    threading.Thread(target=_run, daemon=True).start()
    return True


@app.post("/api/graph/build")
def trigger_build_graph(current_user = Depends(get_current_user)):
    """觸發一次性歷史資料同步到 Neo4j"""
    import sys
    try:
        started = _start_background_job(
            str(current_user.id),
            "graph",
            [sys.executable, "scripts/build_graph.py", str(current_user.id)],
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        if not started:
            return {"success": False, "message": "Neo4j 圖資料庫同步已在進行中，請等待完成後再試一次。"}
        return {"success": True, "message": "已觸發 Neo4j 圖資料庫同步！系統正在背景建立圖譜中，這可能需要幾分鐘。"}
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/entities/build")
def trigger_build_entities(current_user = Depends(get_current_user)):
    import sys
    try:
        # 使用 sys.executable 確保背景執行時是使用當前 venv 的 python
        started = _start_background_job(
            str(current_user.id),
            "entities",
            [sys.executable, "scripts/build_entities.py", str(current_user.id)]
        )
        if not started:
            return {"success": False, "message": "核心人物檔案編譯已在進行中，請等待完成後再試一次。"}
        return {"success": True, "message": "已成功觸發核心人物檔案編譯！系統正在背景努力更新大腦中。"}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
