import json
import base64
import binascii
import hashlib
import json
import logging
import re
import time
import uuid
from datetime import date as Date, time as Time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pytz
from fastapi import FastAPI, Depends, HTTPException, Query, Request, status, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
import os
import datetime
from dotenv import load_dotenv
from observability import configure_logging, new_request_id, request_id_context

# 必須在任何第三方 client 初始化前載入 .env，否則本機設定可能尚未進入 os.environ。
load_dotenv()
configure_logging()
logger = logging.getLogger("memoryai")

_APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
_REQUIRED_ENV_VARS = (
    "GEMINI_API_KEY",
    "COHERE_API_KEY",
    "SUPABASE_URL",
    "ENCRYPTION_KEY",
)
_missing_env_vars = [name for name in _REQUIRED_ENV_VARS if not os.environ.get(name)]
if _missing_env_vars:
    raise RuntimeError(
        "Missing required environment variables: "
        + ", ".join(_missing_env_vars)
    )

# 後端需要 service role key；保留 SUPABASE_KEY 僅供既有本機環境暫時相容。
# staging/production 必須改用明確命名的 SUPABASE_SERVICE_ROLE_KEY。
supabase_service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
legacy_supabase_key = os.environ.get("SUPABASE_KEY")
if not supabase_service_role_key and _APP_ENV in {"staging", "production"}:
    raise RuntimeError(
        "SUPABASE_SERVICE_ROLE_KEY is required when APP_ENV is staging or production"
    )
if not supabase_service_role_key and not legacy_supabase_key:
    raise RuntimeError(
        "Missing SUPABASE_SERVICE_ROLE_KEY (or legacy SUPABASE_KEY for local development)"
    )

# 初始化 Google Gemini 客戶端 (專供 Embedding 使用)
from google import genai
from google.genai import types
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# 初始化 Cohere 客戶端 (專供文字生成)
import cohere
co = cohere.ClientV2(os.environ["COHERE_API_KEY"])
from supabase import create_client, Client

from security import encrypt_text, decrypt_text

# 初始化 Neo4j 圖資料庫連線
try:
    from graph_db import (sync_event_to_graph, upsert_event_to_graph,
                          delete_event_from_graph, get_full_graph, get_person_connections,
                          get_co_mentioned_keywords, get_person_relationship_graph)
    _neo4j_available = True
except Exception as _e:
    logger.warning("neo4j_module_unavailable", extra={"error_type": type(_e).__name__})
    _neo4j_available = False

from services.graph_outbox import enqueue_graph_sync_job
from services.background_jobs import (
    JobConflict,
    JobStoreUnavailable,
    enqueue_background_job,
)
from services.entity_resolver import resolve_mentioned_entities
from services.person_analytics_service import (
    compute_trend_direction, trend_label, build_monthly_series,
    detect_key_moments, summarize_person_state,
)

# Configure Supabase
supabase_url = os.environ["SUPABASE_URL"]
supabase_key = supabase_service_role_key or legacy_supabase_key
supabase: Client = create_client(supabase_url, supabase_key)


def _encode_memory_cursor(memory: dict) -> str:
    payload = {
        "date": memory.get("diary_date") or "0001-01-01",
        "time": memory.get("diary_time"),
        "id": str(memory.get("id")),
    }
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _decode_memory_cursor(cursor: str | None) -> dict[str, object] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        cursor_date = Date.fromisoformat(str(payload["date"]))
        cursor_time = payload.get("time")
        if cursor_time:
            cursor_time = Time.fromisoformat(str(cursor_time))
        else:
            cursor_time = None
        cursor_id = uuid.UUID(str(payload["id"]))
        return {"date": cursor_date.isoformat(), "time": cursor_time.isoformat() if cursor_time else None, "id": str(cursor_id)}
    except (binascii.Error, KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cursor 格式無效，請重新載入記憶時間軸。",
        ) from error


def _queue_graph_sync(
    user_id: str,
    memory_id: str,
    operation: str,
    payload: dict | None,
    background_tasks: BackgroundTasks | None,
) -> bool:
    """Prefer durable outbox; use request-local fallback only before migration."""
    queued = enqueue_graph_sync_job(supabase, user_id, memory_id, operation, payload)
    if queued:
        return True
    if not _neo4j_available or background_tasks is None:
        return False
    if operation == "delete":
        background_tasks.add_task(delete_event_from_graph, user_id, memory_id)
    else:
        graph_payload = payload or {}
        background_tasks.add_task(
            upsert_event_to_graph,
            user_id,
            memory_id,
            str(graph_payload.get("date_str") or ""),
            list(graph_payload.get("keywords") or []),
            int(graph_payload.get("emotion_score", 50)),
            int(graph_payload.get("importance_weight", 3)),
        )
    return False

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


@app.middleware("http")
async def request_observability_middleware(request: Request, call_next):
    request_id = new_request_id(request.headers.get("X-Request-ID"))
    context_token = request_id_context.set(request_id)
    started_at = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    except Exception:
        logger.exception(
            "http_request_failed",
            extra={"method": request.method, "path": request.url.path},
        )
        raise
    finally:
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code if response else 500,
                "duration_ms": round((time.perf_counter() - started_at) * 1000, 2),
            },
        )
        if response is not None:
            response.headers["X-Request-ID"] = request_id
        request_id_context.reset(context_token)


CHAT_RESPONSE_MODES = {"companion", "analysis", "strategy", "memory"}
CHAT_FEEDBACK_TYPES = {"liked", "too_neutral", "too_speculative", "wrong_memory"}


def _raise_internal_error(message: str, error: Exception):
    """Log internal details while returning a safe public API error."""
    logger.exception("internal_api_error", extra={"error_type": type(error).__name__})
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message) from error


def _normalize_date_value(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a valid ISO date")
    raw_parts = value.strip().replace("/", "-").split("-")
    if len(raw_parts) != 3:
        raise ValueError(f"{field_name} must use YYYY-MM-DD format")
    try:
        parsed = Date(int(raw_parts[0]), int(raw_parts[1]), int(raw_parts[2]))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a valid calendar date") from error
    return parsed.isoformat()


def _validate_time_value(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        Time.fromisoformat(value)
    except ValueError as error:
        raise ValueError("diary_time must use HH:MM or HH:MM:SS format") from error
    return value


def _validate_timezone_value(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as error:
        # Windows 可能沒有 system tzdata；pytz 提供相同 IANA timezone 的 fallback。
        try:
            pytz.timezone(value)
        except pytz.UnknownTimeZoneError as fallback_error:
            raise ValueError("timezone must be a valid IANA timezone") from fallback_error
    return value


def _validate_keywords_value(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if len(value) > 30:
        raise ValueError("keywords cannot contain more than 30 items")
    for keyword in value:
        if not isinstance(keyword, str) or not keyword.strip():
            raise ValueError("keywords must contain non-empty strings")
        if len(keyword.strip()) > 100:
            raise ValueError("each keyword must be at most 100 characters")
    return [keyword.strip() for keyword in value]


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=12_000)
    history: list[dict] = Field(default_factory=list, max_length=30)
    response_mode: Literal["companion", "analysis", "strategy", "memory"] = "analysis"

    @field_validator("history")
    @classmethod
    def validate_history(cls, value: list[dict]) -> list[dict]:
        for item in value:
            if not isinstance(item, dict) or not isinstance(item.get("content"), str):
                raise ValueError("history items must contain string content")
            if len(item["content"]) > 12_000:
                raise ValueError("each history message must be at most 12000 characters")
        return value


class ChatFeedbackRequest(BaseModel):
    feedback_type: Literal["liked", "too_neutral", "too_speculative", "wrong_memory"]
    response_mode: Literal["companion", "analysis", "strategy", "memory"] = "analysis"

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

@app.get("/health/live")
def liveness_check():
    """Cheap process check for container liveness probes."""
    return {"status": "ok", "service": "memoryai-backend"}


@app.get("/health/ready")
def readiness_check():
    """Dependency check for traffic readiness; never calls AI providers."""
    checks = {"supabase": "ok", "graph_outbox": "ok", "background_jobs": "ok"}
    try:
        # Service-role access is intentionally used only by the backend.
        supabase.table("profiles").select("id").limit(1).execute()
        supabase.table("graph_sync_outbox").select("id").limit(1).execute()
        supabase.table("background_jobs").select("id").limit(1).execute()
    except Exception as error:
        logger.warning("readiness_check_failed", extra={"path": "/health/ready"})
        checks["supabase"] = "unavailable"
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "checks": checks},
        ) from error

    checks["neo4j"] = "available" if _neo4j_available else "degraded"
    return {"status": "ready", "checks": checks}


@app.get("/api/health")
def health_check():
    # Backward-compatible alias; new deployments should probe /health/live or /health/ready.
    return liveness_check()

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # 透過 Supabase Auth 驗證 JWT
        user_res = supabase.auth.get_user(token)
        if not user_res or not user_res.user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return user_res.user
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("authentication_validation_failed", extra={"error_type": type(error).__name__})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from error

@app.get("/api/jobs/{job_id}")
def get_background_job(job_id: str, current_user=Depends(get_current_user)):
    try:
        uuid.UUID(job_id)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="job_id 格式無效") from error
    try:
        result = supabase.table("background_jobs").select(
            "id, job_type, status, progress, progress_message, attempts, "
            "last_error, created_at, updated_at, completed_at"
        ).eq("id", job_id).eq("user_id", str(current_user.id)).limit(1).execute()
        if not result.data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
        return {"success": True, "job": result.data[0]}
    except HTTPException:
        raise
    except Exception as error:
        _raise_internal_error("無法讀取背景任務狀態", error)


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
        
        # Numeric dashboard values are aggregated in PostgreSQL so encrypted scores
        # do not need to be loaded and averaged in Python on every request.
        aggregate_rows = []
        try:
            aggregate_rows = supabase.rpc(
                "get_dashboard_aggregates",
                {"p_user_id": str(current_user.id)},
            ).execute().data or []
        except Exception as aggregate_error:
            # Keep compatibility until the Phase 3 migration has been applied.
            print(f"⚠️ Dashboard aggregate RPC unavailable, using fallback: {aggregate_error}")

        if not memories:
            return {
                "emotion_trends": [],
                "keyword_distribution": [],
                "summary_stats": {"total_days": 0, "avg_score": 0, "top_keyword": "無"},
                "entity_analysis": []
            }

        # PostgreSQL provides date averages/counts; encrypted topics are only used
        # to retain the existing display label for each day.
        if aggregate_rows:
            emotion_trends = []
            for row in aggregate_rows:
                date_value = str(row.get("diary_date"))
                topics_today = [m["topic"] for m in memories if m.get("diary_date") == date_value]
                main_topic = max(set(topics_today), key=topics_today.count) if topics_today else ""
                emotion_trends.append({
                    "date": date_value,
                    "score": round(float(row.get("avg_score") or 0), 1),
                    "main_topic": main_topic,
                })
            total_days = int(aggregate_rows[0].get("total_days") or 0)
            avg_overall_score = float(aggregate_rows[0].get("overall_avg_score") or 0)
        else:
            # Fallback for a deployment that has not applied the migration yet.
            date_scores = {}
            for m in memories:
                date = m["diary_date"]
                score = m["emotion_score"]
                if score is None:
                    continue
                date_scores.setdefault(date, []).append(score)
            emotion_trends = []
            for date in sorted(date_scores.keys()):
                avg_score = sum(date_scores[date]) / len(date_scores[date])
                topics_today = [m["topic"] for m in memories if m["diary_date"] == date]
                main_topic = max(set(topics_today), key=topics_today.count) if topics_today else ""
                emotion_trends.append({
                    "date": date,
                    "score": round(avg_score, 1),
                    "main_topic": main_topic,
                })
            total_days = len(date_scores)
            avg_overall_score = (
                sum(sum(scores) / len(scores) for scores in date_scores.values()) / total_days
                if total_days else 0
            )

        # Keyword/entity analysis still uses decrypted fields because existing
        # keywords and summaries are encrypted; it is intentionally isolated from
        # the numeric aggregate path above.
        keyword_counts = {}
        stop_words = {"聊天", "訊息", "回覆", "朋友"}
        for m in memories:
            for kw in m.get("keywords") or []:
                if not kw or len(kw) > 10 or kw in stop_words:
                    continue
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1

        keyword_distribution = [
            {"name": k, "value": v}
            for k, v in sorted(keyword_counts.items(), key=lambda item: item[1], reverse=True)
        ][:10]

        top_keyword = keyword_distribution[0]["name"] if keyword_distribution else "無"
        summary_stats = {
            "total_days": total_days,
            "avg_score": round(avg_overall_score, 1),
            "top_keyword": top_keyword,
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
    except Exception as error:
        _raise_internal_error("無法載入儀表板資料", error)

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
        "id, diary_date, diary_time, topic, summary, content, keywords, emotion_score, importance_weight"
    ).eq("user_id", user_id).in_("id", list(memory_ids)).execute()
    memories = {}
    for memory in (response.data or []):
        # Cross-person filtering needs plaintext keywords; decrypt once and keep alongside the record.
        memory["decrypted_keywords"] = [
            decrypt_text(keyword) for keyword in (memory.get("keywords") or [])
        ]
        memories[str(memory["id"])] = memory
    return memories


def _filter_cross_person_contamination(
    ranked_ids: list[str],
    memories_by_id: dict[str, dict],
    graph_candidates: dict[str, dict],
    mentioned_entities: list[dict],
    all_entities: list[dict],
) -> list[str]:
    """
    Vector search is global and has no notion of "whose event this is", so a semantically
    similar memory about a different named person can otherwise leak into evidence for the
    person the user actually asked about (this is exactly the cross-person mixing Graph RAG
    was introduced to prevent). Graph candidates are already scoped correctly by
    get_person_connections(); this only needs to guard vector-only candidates.
    """
    if not mentioned_entities:
        return ranked_ids

    mentioned_names = {entity["name"] for entity in mentioned_entities}
    other_known_names = {
        entity["name"] for entity in all_entities if entity["name"] not in mentioned_names
    }
    if not other_known_names:
        return ranked_ids

    filtered = []
    for memory_id in ranked_ids:
        if memory_id in graph_candidates:
            filtered.append(memory_id)
            continue
        memory = memories_by_id.get(memory_id)
        if not memory:
            continue
        memory_names = set(memory.get("decrypted_keywords") or [])
        belongs_to_other_person_only = bool(memory_names & other_known_names) and not (
            memory_names & mentioned_names
        )
        if belongs_to_other_person_only:
            continue
        filtered.append(memory_id)
    return filtered


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


def _get_response_feedback_context(user_id: str) -> str:
    """Turn stored preference signals into concise, non-sensitive system guidance."""
    try:
        response = supabase.table("chat_response_feedback").select("feedback_type") \
            .eq("user_id", user_id).order("created_at", desc=True).limit(40).execute()
    except Exception as error:
        # Deployment remains usable until the optional preference migration is installed.
        if "chat_response_feedback" not in str(error):
            print(f"⚠️ 讀取聊天回饋偏好失敗：{error}")
        return ""

    counts: dict[str, int] = {}
    for row in (response.data or []):
        feedback_type = row.get("feedback_type")
        if feedback_type in CHAT_FEEDBACK_TYPES:
            counts[feedback_type] = counts.get(feedback_type, 0) + 1

    notes = []
    if counts.get("too_neutral", 0) > 0:
        notes.append("使用者不喜歡為了中立而替他人合理化；先回應她明確描述的情境與邊界。")
    if counts.get("too_speculative", 0) > 0:
        notes.append("使用者不喜歡腦補；推論要保留條件，並和已知事實分開。")
    if counts.get("wrong_memory", 0) > 0:
        notes.append("使用者很在意記憶正確性；只引用真正支持說法的 [S#]，不確定就明講。")
    if counts.get("liked", 0) > 0:
        notes.append("使用者喜歡有具體脈絡、自然直接且不說教的回覆。")

    return f"【使用者過往回饋偏好】\n- " + "\n- ".join(notes) if notes else ""


@app.post("/api/chat")
def chat(request: ChatRequest, current_user = Depends(get_current_user)):
    if not request.message.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message cannot be empty",
        )
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
        ranked_ids = _filter_cross_person_contamination(
            ranked_ids, memories_by_id, graph_candidates, mentioned_entities, all_entities
        )
        evidence_sources = _build_evidence_sources(memories_by_id, ranked_ids)
        memory_context = _build_memory_context(evidence_sources)
        entity_context = _build_entity_context(user_id, mentioned_entities)

        # 4. Long-term context is explicitly secondary to dated event evidence.
        life_context = _compact_chat_text(get_user_context(user_id), 650)
        current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode_instructions = {
            "companion": "陪我吐槽：先自然接住情緒與荒謬點，像懂脈絡的好友聊天；除非使用者主動要求，不要展開長篇分析或給策略。",
            "analysis": "冷靜分析：先提出有證據支持的行為／互動模式，再分開說明合理推論與未知處；不要只重述使用者的話或退回泛用安慰。",
            "strategy": "幫我想下一步：先用簡短證據說明判斷前提，再給 2～3 個可選且尊重使用者既有邊界的行動方案。",
            "memory": "查記憶：以日期、人物、事件時間線回答；只陳述能被證據支持的內容，不做人格分析、讀心或建議。",
        }
        response_mode = request.response_mode if request.response_mode in CHAT_RESPONSE_MODES else "analysis"
        mode_instruction = mode_instructions[response_mode]
        feedback_context = _get_response_feedback_context(user_id)
        system_instruction = f"""
你是使用者的 MemoryAI：一個記得她故事、能一起拆解情境的聰明好友與幕僚。
你的首要責任不是提供萬用諮商建議，而是先聽懂使用者現在是在分享、吐槽、求判讀，還是明確要下一步策略。

【本輪回應模式】
{mode_instruction}

【證據與誠實規則】(強制遵守，不是建議)
1. 每當你描述「歷史記憶證據」中某一則具體事件、對話或行為時，該句結尾必須加上對應的 [S1]、[S2] 等引用標記。例如：「他跟你討論健康狀況時回應得較含糊 [S2]。」沒有引用標記的句子，代表你正在做推論或一般陪聊，不能包含只有記憶才會知道的具體細節。
2. 絕對禁止把 A 的事件、發言或行為，誤植到 B 身上。每則歷史記憶證據開頭的人名／情境即為該事件的真正主角；只能用來描述使用者本次詢問的對象。若某則證據看起來與本次對象無關，直接忽略它，不要硬套用。
3. 請清楚區分：使用者已說／記憶已記錄的事實（需引用）、你的合理推論（不需引用，但要標明「可能」「或許」等字眼）、以及無法確認的部分。不能把他人的內心動機說成已知事實。
4. 人物背景與長期脈絡僅供理解，不能取代有日期的事件證據；若它和事件證據衝突，以事件證據為準。
5. 若沒有相關歷史證據，直接坦白「我目前沒有找到能支持這個過去判斷的記憶」，不要用空泛心理學填滿答案，也不要編造引用。

【回應方式】
1. 配合使用者此刻的情緒與語氣：她在吐槽或分享時，先接住荒謬點與核心感受；沒有被要求時，不要自動變成教她溝通、叫她冷靜或要求她理解對方的說教機器。
2. 可以自然、幽默、帶有人情味，也可少量使用系統比喻；不要為了風格硬塞術語或誇大成戰報。
3. 若需要分析，先從具體行為與時間線下手，再提出「可能」的解讀。若使用者要求建議，再給少量、符合她已設下邊界的可執行選項。
4. 回答可用短段落或條列，但避免例行公事般的「猜測心理／建議對策」模板。
5. 一律使用繁體中文。

目前系統時間：{current_time_str}

{feedback_context}

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
        reply_text = response.message.content[0].text

        # Display only sources the model actually cited. Retrieval candidates are not evidence
        # until the reply makes a claim tied to their [S#] marker.
        cited_sources = set(re.findall(r"\[(S\d+)\]", reply_text))
        public_sources = [
            {
                key: source[key]
                for key in ("citation", "memory_id", "date", "diary_time", "topic", "summary", "excerpt")
            }
            for source in evidence_sources
            if source["citation"] in cited_sources
        ]
        retrieval_modes = []
        if graph_candidates:
            retrieval_modes.append("graph")
        if vector_results:
            retrieval_modes.append("vector")

        return {
            "reply": reply_text,
            "sources": public_sources,
            "response_mode": response_mode,
            "retrieval": {
                "mode": "+".join(retrieval_modes) or "none",
                "source_count": len(public_sources),
                "mentioned_entities": [entity["name"] for entity in mentioned_entities],
            },
        }

    except HTTPException:
        raise
    except Exception as error:
        _raise_internal_error("聊天服務暫時無法使用", error)


@app.post("/api/chat/feedback")
def record_chat_feedback(feedback: ChatFeedbackRequest, current_user = Depends(get_current_user)):
    """Persist only a coarse preference signal; never store chat text or source excerpts here."""
    try:
        supabase.table("chat_response_feedback").insert({
            "user_id": current_user.id,
            "feedback_type": feedback.feedback_type,
            "response_mode": feedback.response_mode,
        }).execute()
        return {"success": True}
    except Exception as error:
        _raise_internal_error("無法記錄聊天回饋", error)

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
    except Exception as error:
        _raise_internal_error("無法載入記憶關係圖", error)

# --- 記憶時光機 API (Phase 5.4) ---
from typing import Optional


class MemoryUpdate(BaseModel):
    diary_date: Optional[str] = Field(default=None, max_length=10)
    diary_time: Optional[str] = Field(default=None, max_length=8)
    timezone: Optional[str] = Field(default=None, max_length=64)
    topic: Optional[str] = Field(default=None, max_length=200)
    summary: Optional[str] = Field(default=None, max_length=3_000)
    emotion_score: Optional[int] = Field(default=None, ge=0, le=100)
    keywords: Optional[list[str]] = Field(default=None, max_length=30)
    original_text: Optional[str] = Field(default=None, max_length=20_000)
    content: Optional[str] = Field(default=None, max_length=20_000)
    importance_weight: Optional[int] = Field(default=None, ge=1, le=5)

    @field_validator("diary_date")
    @classmethod
    def validate_diary_date(cls, value: str | None) -> str | None:
        return _normalize_date_value(value, "diary_date") if value is not None else None

    @field_validator("diary_time")
    @classmethod
    def validate_diary_time(cls, value: str | None) -> str | None:
        return _validate_time_value(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return _validate_timezone_value(value)

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: list[str] | None) -> list[str] | None:
        return _validate_keywords_value(value)


class MemoryCreate(BaseModel):
    diary_date: str = Field(..., max_length=10)
    diary_time: Optional[str] = Field(default=None, max_length=8)
    timezone: Optional[str] = Field(default=None, max_length=64)
    topic: str = Field(..., min_length=1, max_length=200)
    summary: str = Field(..., min_length=1, max_length=3_000)
    emotion_score: int = Field(..., ge=0, le=100)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    original_text: Optional[str] = Field(default="", max_length=20_000)
    content: Optional[str] = Field(default="", max_length=20_000)
    importance_weight: Optional[int] = Field(default=3, ge=1, le=5)

    @field_validator("diary_date")
    @classmethod
    def validate_diary_date(cls, value: str) -> str:
        return _normalize_date_value(value, "diary_date")

    @field_validator("diary_time")
    @classmethod
    def validate_diary_time(cls, value: str | None) -> str | None:
        return _validate_time_value(value)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        return _validate_timezone_value(value)

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: list[str]) -> list[str]:
        return _validate_keywords_value(value) or []


class ImportSingleRequest(BaseModel):
    date_str: str = Field(..., max_length=10)
    content: str = Field(..., min_length=1, max_length=100_000)

    @field_validator("date_str")
    @classmethod
    def validate_date_str(cls, value: str) -> str:
        return _normalize_date_value(value, "date_str")


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
def get_memories(
    current_user=Depends(get_current_user),
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None),
):
    try:
        decoded_cursor = _decode_memory_cursor(cursor)
        cursor_params = decoded_cursor or {}
        response = supabase.rpc(
            "get_memory_page",
            {
                "p_user_id": str(current_user.id),
                "p_limit": limit + 1,
                "p_cursor_date": cursor_params.get("date"),
                "p_cursor_time": cursor_params.get("time"),
                "p_cursor_id": cursor_params.get("id"),
            },
        ).execute()
        rows = response.data or []
        has_more = len(rows) > limit
        page = rows[:limit]
        for memory in page:
            memory["summary"] = decrypt_text(memory.get("summary", ""))
            memory["content"] = decrypt_text(memory.get("content", ""))
            memory["topic"] = decrypt_text(memory.get("topic", ""))
            memory["keywords"] = [
                decrypt_text(keyword) for keyword in (memory.get("keywords") or [])
            ]
            memory["timezone"] = memory.get("timezone") or "Asia/Taipei"
        next_cursor = _encode_memory_cursor(page[-1]) if has_more and page else None
        return {
            "memories": page,
            "next_cursor": next_cursor,
            "has_more": has_more,
        }
    except HTTPException:
        raise
    except Exception as error:
        _raise_internal_error("無法載入記憶資料", error)

@app.post("/api/memories")
def create_memory(
    memory: MemoryCreate,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
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
        graph_sync_queued = False
        if response.data and response.data[0].get("id"):
            graph_sync_queued = _queue_graph_sync(
                str(current_user.id),
                str(response.data[0]["id"]),
                "upsert",
                {
                    "date_str": data.get("diary_date", ""),
                    "keywords": memory.keywords,
                    "emotion_score": data.get("emotion_score", 50),
                    "importance_weight": data.get("importance_weight", 3),
                },
                background_tasks,
            )
        return {"success": True, "data": response.data, "graph_sync_queued": graph_sync_queued}
    except Exception as error:
        _raise_internal_error("無法建立記憶", error)

@app.put("/api/memories/{memory_id}")
def update_memory(
    memory_id: str,
    memory: MemoryUpdate,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    try:
        # 首先驗證這筆記憶是否屬於該使用者
        old_data_res = supabase.table("memories").select(
            "user_id, diary_date, topic, summary, keywords, content, "
            "emotion_score, importance_weight"
        ).eq("id", memory_id).execute()
        if not old_data_res.data or old_data_res.data[0].get('user_id') != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found",
            )
            
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

        graph_payload = {
            "date_str": update_data.get("diary_date", old_data.get("diary_date", "")),
            "keywords": update_data.get("keywords", old_data.get("keywords", [])),
            "emotion_score": update_data.get("emotion_score", old_data.get("emotion_score", 50)),
            "importance_weight": update_data.get("importance_weight", old_data.get("importance_weight", 3)),
        }

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
        graph_sync_queued = _queue_graph_sync(
            str(current_user.id),
            memory_id,
            "upsert",
            graph_payload,
            background_tasks,
        )
        return {"success": True, "data": response.data, "graph_sync_queued": graph_sync_queued}
    except HTTPException:
        raise
    except Exception as error:
        _raise_internal_error("無法更新記憶", error)

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
                #     model='gemini-3.5-flash',
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
    except HTTPException:
        raise
    except Exception as error:
        _raise_internal_error("無法摘要聊天內容", error)

@app.get("/api/memories/monthly_summary")
def monthly_summary(year: int, month: int, force_regenerate: bool = False, current_user = Depends(get_current_user)):
    """For the Dashboard: generate a narrative story summary for a given month."""
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="year/month is out of range",
        )
    user_id = str(current_user.id)
    if not force_regenerate:
        try:
            cached_res = supabase.table("monthly_summary_cache").select(
                "encrypted_summary, memory_count"
            ).eq("user_id", user_id).eq("summary_year", year).eq(
                "summary_month", month
            ).limit(1).execute()
            cached = cached_res.data[0] if cached_res.data else None
        except Exception as error:
            logger.warning("monthly_summary_cache_read_failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="月度摘要快取服務目前不可用，請先完成 Phase 4 migration。",
            ) from error
        if cached:
            return {
                "success": True,
                "summary": decrypt_text(cached["encrypted_summary"]),
                "memory_count": cached.get("memory_count", 0),
                "cached": True,
            }

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
        
        # 儲存到 Supabase durable cache（內容仍以使用者 email 加密）。
        try:
            supabase.table("monthly_summary_cache").upsert({
                "user_id": user_id,
                "summary_year": year,
                "summary_month": month,
                "encrypted_summary": encrypt_text(summary_text, current_user.email),
                "memory_count": len(res.data),
                "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }).execute()
        except Exception:
            # 摘要已成功產生；cache 寫入失敗不應丟失本次結果，但要留下結構化 log。
            logger.exception("monthly_summary_cache_write_failed")

        return {"success": True, "summary": summary_text, "memory_count": len(res.data), "cached": False}
    except Exception as error:
        _raise_internal_error("無法產生月度摘要", error)

@app.delete("/api/memories/{memory_id}")
def delete_memory(
    memory_id: str,
    background_tasks: BackgroundTasks,
    current_user=Depends(get_current_user),
):
    try:
        response = supabase.table("memories").delete().eq("id", memory_id).eq("user_id", current_user.id).execute()
        if not response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Memory not found",
            )
        graph_sync_queued = _queue_graph_sync(
            str(current_user.id),
            memory_id,
            "delete",
            None,
            background_tasks,
        )
        return {"success": True, "graph_sync_queued": graph_sync_queued}
    except HTTPException:
        raise
    except Exception as error:
        _raise_internal_error("無法刪除記憶", error)


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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="日記內容不能是空白",
            )

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
                # model='gemini-3.5-flash',
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
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="AI 未產生可用的事件資料",
            )

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
            
            # Supabase 是 source of truth；Neo4j 同步先寫入 durable outbox。
            # 只同步結構化資訊，不寫入 topic/summary 等內容明文。
            if res.data:
                memory_id = res.data[0].get("id")
                _queue_graph_sync(
                    str(current_user.id),
                    str(memory_id),
                    "upsert",
                    {
                        "date_str": request.date_str,
                        "keywords": [
                            k for k in event.get("keywords", [])
                            if k not in ["蕭筠蓁", "我", "自己"]
                        ],
                        "emotion_score": event.get("emotion_score", 50),
                        "importance_weight": event.get("importance_weight", 3),
                    },
                    background_tasks,
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
        entity_profile_job_id = None
        if mentioned_names:
            try:
                entity_profile_job_id = enqueue_background_job(
                    supabase,
                    str(current_user.id),
                    "entity_profile",
                    {"mentioned_names": sorted(mentioned_names)},
                )
            except JobConflict:
                logger.info("entity_profile_job_already_active")
            except JobStoreUnavailable:
                logger.exception("entity_profile_job_store_unavailable")

        return {
            "success": True,
            "inserted_count": inserted_count,
            "skipped_event_count": skipped_event_count,
            "appended": analysis_content != normalized_content,
            "entity_profile_job_id": entity_profile_job_id,
        }
    except HTTPException:
        raise
    except Exception as error:
        _raise_internal_error("無法匯入日記", error)


# ── 圖資料庫 API (Neo4j) ─────────────────────────────────────────────────

@app.get("/api/graph")
def get_graph_data(current_user = Depends(get_current_user)):
    """Takes the full graph data from Neo4j for visualization."""
    if not _neo4j_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j 圖資料庫目前不可用",
        )
    try:
        data = get_full_graph(str(current_user.id))
        return {"success": True, **data}
    except Exception as error:
        _raise_internal_error("無法載入記憶關係圖", error)

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
    except Exception as error:
        _raise_internal_error("無法載入關係熱力圖", error)

@app.get("/api/dashboard/person_overview")
def get_person_overview(current_user = Depends(get_current_user)):
    """
    人物總覽：一次回傳「象限圖」與「總覽表」共用的資料。

    與 relationship_heatmap 一樣，直接用 Supabase 的 keywords/summary 比對人物，
    不依賴 Neo4j（Neo4j 目前不可用時，這頁分析仍可正常運作）。

    每位人物回傳：
      - total_count: 總互動次數（象限圖 X 軸）
      - avg_score: 平均情緒分數（象限圖 Y 軸）
      - first_date / last_date: 互動起訖日期
      - trend_direction / trend_label: 情緒趨勢方向（供總覽表的 ↑/↓/→ 欄位）
    """
    try:
        entities_res = supabase.table("entities").select("name") \
            .eq("user_id", current_user.id).execute()
        person_names = [e["name"] for e in (entities_res.data or []) if e.get("name")]
        if not person_names:
            return {
                "success": True, "persons": [],
                "message": "尚未編譯核心人物檔案，請先執行「編譯核心人物檔案」。"
            }

        mem_res = supabase.table("memories").select("diary_date, emotion_score, keywords, summary") \
            .eq("user_id", current_user.id).execute()
        memories = mem_res.data or []
        if not memories:
            return {"success": True, "persons": []}

        for m in memories:
            m["keywords"] = [decrypt_text(k) for k in (m.get("keywords") or [])]
            m["summary"] = decrypt_text(m.get("summary", ""))

        persons = []
        for name in person_names:
            # 與 relationship_heatmap / dashboard stats 一致的比對方式：keywords 或 summary 命中
            related = [
                m for m in memories
                if name in (m.get("keywords") or []) or name in (m.get("summary") or "")
            ]
            if not related:
                continue

            # 依日期由舊到新排序，才能正確判斷「趨勢方向」（前半段 vs 後半段）
            related.sort(key=lambda m: m.get("diary_date") or "")
            chronological_scores = [m.get("emotion_score") for m in related]
            scored = [s for s in chronological_scores if s is not None]

            direction = compute_trend_direction(chronological_scores)
            # 與趨勢方向採用同一套「前半段 vs 後半段」基準，額外回傳幅度，
            # 讓總覽可以找出最明顯的升溫／降溫關係，而不是只顯示箭頭。
            trend_delta = None
            if len(scored) >= 2:
                midpoint = len(scored) // 2
                first_average = sum(scored[:midpoint]) / midpoint
                second_average = sum(scored[midpoint:]) / len(scored[midpoint:])
                trend_delta = round(second_average - first_average, 1)
            dates = [m["diary_date"] for m in related if m.get("diary_date")]

            persons.append({
                "name": name,
                "total_count": len(related),
                "avg_score": round(sum(scored) / len(scored), 1) if scored else None,
                "first_date": min(dates) if dates else None,
                "last_date": max(dates) if dates else None,
                "trend_direction": direction,
                "trend_label": trend_label(direction),
                "trend_delta": trend_delta,
            })

        # 互動次數多的人物排在前面，與其他人物分析頁的排序邏輯一致
        persons.sort(key=lambda p: p["total_count"], reverse=True)

        return {"success": True, "persons": persons}
    except Exception as error:
        _raise_internal_error("無法載入人物總覽", error)

@app.get("/api/graph/persons")
def get_persons_graph(current_user = Depends(get_current_user)):
    """
    人物中心的關係圖：只保留 entities 表中已被判定為人物的節點，
    並附上每個人物的平均情緒分數、互動次數與人物檔案，供前端做顏色/大小編碼。
    """
    if not _neo4j_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j 圖資料庫目前不可用",
        )
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
    except Exception as error:
        _raise_internal_error("無法載入人物關係圖", error)

def _get_person_analytics_bundle(user_id: str, person_name: str) -> dict:
    """
    共用邏輯：抓取某人物的完整事件時間軸並算出衍生分析。
    供 /api/graph/person/{name} 與 /api/graph/compare 共用，避免重複實作
    Neo4j 事件查詢、Supabase 解密、月度聚合／關鍵時刻／現況摘要的組裝。

    回傳的 events 已依時間先後排序（舊→新）。
    """
    # Neo4j 只回傳結構化資訊（memory_id, date, emotion_score, importance_weight），
    # 不含事件內容明文，需回 Supabase 依 memory_id 查詢並解密取得實際內容。
    # 分析／對比需要完整人物歷史；聊天 RAG 仍會在呼叫端明確傳入 limit=30。
    connections = get_person_connections(user_id, person_name, limit=None)
    memory_ids = [c["memory_id"] for c in connections if c.get("memory_id")]

    events = []
    if memory_ids:
        # 人物歷史可能很長；分批查詢避免把數百／數千個 UUID
        # 一次放進 PostgREST .in()，造成 URL 過長或請求逾時。
        memories_by_id = {}
        batch_size = 100
        for start in range(0, len(memory_ids), batch_size):
            batch_ids = memory_ids[start:start + batch_size]
            res = supabase.table("memories").select("id, diary_date, diary_time, topic, summary, emotion_score, importance_weight") \
                .eq("user_id", user_id) \
                .in_("id", batch_ids) \
                .execute()
            memories_by_id.update({str(m["id"]): m for m in (res.data or [])})

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

    # 依時間先後排序（舊→新），供月度聚合／趨勢／關鍵時刻計算使用。
    # get_person_connections 原本回傳新→舊，這裡明確反轉，避免順序假設出錯。
    events.sort(key=lambda e: e.get("date") or "")

    # 新版資料庫會用 updated_at 顯示人物側寫的新鮮度；既有部署若尚未
    # 執行 migration，PostgREST 會在欄位不存在時拋錯。這個附加資訊不能讓
    # 人物詳情或對比功能整頁失敗，因此依序降級至 created_at，再回傳 None。
    profile_updated_at = None
    try:
        entity_res = supabase.table("entities").select("updated_at") \
            .eq("user_id", user_id).eq("name", person_name).limit(1).execute()
        profile_updated_at = (entity_res.data or [{}])[0].get("updated_at") if entity_res.data else None
    except Exception as updated_at_error:
        print(
            "⚠️ entities.updated_at 無法讀取，人物側寫新鮮度將改用 created_at 或略過："
            f" {updated_at_error}"
        )
        try:
            entity_res = supabase.table("entities").select("created_at") \
                .eq("user_id", user_id).eq("name", person_name).limit(1).execute()
            profile_updated_at = (entity_res.data or [{}])[0].get("created_at") if entity_res.data else None
        except Exception as created_at_error:
            print(f"⚠️ entities.created_at 也無法讀取，略過人物側寫新鮮度： {created_at_error}")

    co_mentions = get_co_mentioned_keywords(user_id, person_name)
    scores = [e["emotion_score"] for e in events if e.get("emotion_score") is not None]
    importances = [e["importance_weight"] for e in events if e.get("importance_weight") is not None]

    return {
        "events": events,
        "co_mentioned": co_mentions,
        "monthly_series": build_monthly_series(events),
        "key_moments": detect_key_moments(events),
        "status": summarize_person_state(events, profile_updated_at),
        "event_count": len(events),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "avg_importance": round(sum(importances) / len(importances), 1) if importances else None,
    }


@app.get("/api/graph/person/{person_name}")
def get_person_graph(person_name: str, current_user = Depends(get_current_user)):
    """
    Query all events related to a specific person, plus derived analytics for the
    strengthened person detail panel:
      - monthly_series: 生命週期線圖用的月度聚合（事件數 + 平均情緒）
      - key_moments: 情緒轉折點（與前一筆事件的分數差最大的幾個事件）
      - status: 現況簡報卡（最新事件、趨勢方向、人物側寫最後更新時間）
    """
    if not _neo4j_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j 圖資料庫目前不可用",
        )
    try:
        bundle = _get_person_analytics_bundle(str(current_user.id), person_name)
        return {"success": True, **bundle}
    except Exception as error:
        _raise_internal_error("無法載入人物分析", error)


@app.get("/api/graph/compare")
def compare_persons(person_a: str, person_b: str, current_user = Depends(get_current_user)):
    """
    人物對比視圖：一次回傳兩位人物的分析資料（互動頻率、平均情緒、平均重要度、
    月度生命週期序列、關鍵時刻），供前端並排比較。

    直接重用 _get_person_analytics_bundle()，與單一人物詳情面板保證資料格式一致。
    """
    if not _neo4j_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neo4j 圖資料庫目前不可用",
        )
    if not person_a or not person_b:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="請提供兩位人物的名稱（person_a、person_b）。",
        )
    try:
        user_id = str(current_user.id)
        bundle_a = _get_person_analytics_bundle(user_id, person_a)
        bundle_b = _get_person_analytics_bundle(user_id, person_b)
        return {
            "success": True,
            "persons": [
                {"name": person_a, **bundle_a},
                {"name": person_b, **bundle_b},
            ],
        }
    except Exception as error:
        _raise_internal_error("無法比較人物資料", error)

# --- 持久化背景任務觸發 ---
# Web process 只建立 Supabase job，不在 request process 啟動 daemon thread。

@app.post("/api/graph/build")
def trigger_build_graph(current_user=Depends(get_current_user)):
    """建立一次性歷史資料同步 job，由獨立 worker 執行。"""
    try:
        job_id = enqueue_background_job(
            supabase,
            str(current_user.id),
            "graph",
            {},
        )
        return {"success": True, "job_id": job_id, "message": "已建立 Neo4j 圖資料庫同步任務。"}
    except JobConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Neo4j 圖資料庫同步已在進行中，請等待完成後再試一次。",
        ) from error
    except JobStoreUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="背景任務服務目前不可用，請先完成 Phase 4 migration。",
        ) from error


@app.post("/api/entities/build")
def trigger_build_entities(current_user=Depends(get_current_user)):
    """建立人物檔案編譯 job，由獨立 worker 執行。"""
    try:
        job_id = enqueue_background_job(
            supabase,
            str(current_user.id),
            "entities",
            {},
        )
        return {"success": True, "job_id": job_id, "message": "已建立核心人物檔案編譯任務。"}
    except JobConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="核心人物檔案編譯已在進行中，請等待完成後再試一次。",
        ) from error
    except JobStoreUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="背景任務服務目前不可用，請先完成 Phase 4 migration。",
        ) from error

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
