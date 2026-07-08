"""
Memory CRUD routes for MemoryAI API.

Routes:
    GET    /api/memories               — list all memories for the current user
    POST   /api/memories               — create a new memory
    PUT    /api/memories/{memory_id}   — update an existing memory
    DELETE /api/memories/{memory_id}   — hard-delete a memory (soft delete added in task 8.1)
"""

from fastapi import APIRouter, Depends

from api.dependencies import supabase
from api.middleware.auth import get_current_user
from models.schemas import MemoryCreate, MemoryUpdate
from services.embedding_service import get_embedding
from services.encryption_service import decrypt_text, encrypt_text

router = APIRouter(prefix="/api", tags=["memories"])


@router.get("/memories")
def get_memories(current_user=Depends(get_current_user)):
    try:
        response = (
            supabase.table("memories")
            .select("*")
            .eq("user_id", current_user.id)
            .order("diary_date", desc=True)
            .execute()
        )
        for m in response.data:
            m["summary"] = decrypt_text(m.get("summary", ""))
            m["content"] = decrypt_text(m.get("content", ""))
            m["topic"] = decrypt_text(m.get("topic", ""))
            m["keywords"] = [decrypt_text(k) for k in (m.get("keywords") or [])]
            m["timezone"] = m.get("timezone") or "Asia/Taipei"
        return {"memories": response.data}
    except Exception as e:
        import traceback

        traceback.print_exc()
        return {"error": str(e)}


@router.post("/memories")
def create_memory(memory: MemoryCreate, current_user=Depends(get_current_user)):
    try:
        data = memory.model_dump()

        # Attach user identity
        data["user_id"] = current_user.id

        # Map original_text → content
        if data.get("original_text"):
            data["content"] = data["original_text"]
        if "original_text" in data:
            del data["original_text"]

        # Compute embedding
        embedding_text = (
            f"[{data.get('diary_date', '')}] "
            f"標籤:{data.get('topic', '')} - {data.get('summary', '')}。"
            f"相關細節：{', '.join(data.get('keywords', []))}。"
            f"原文：{data.get('content', '')}"
        )
        data["embedding"] = get_embedding(embedding_text)

        # Encrypt sensitive fields
        data["summary"] = encrypt_text(data.get("summary", ""), current_user.email)
        data["content"] = encrypt_text(data.get("content", ""), current_user.email)
        data["topic"] = encrypt_text(data.get("topic", ""), current_user.email)
        data["keywords"] = [
            encrypt_text(k, current_user.email) for k in data.get("keywords", [])
        ]

        response = supabase.table("memories").insert(data).execute()
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"error": str(e)}


@router.put("/memories/{memory_id}")
def update_memory(
    memory_id: str, memory: MemoryUpdate, current_user=Depends(get_current_user)
):
    try:
        # Verify ownership and fetch current values for embedding recalculation
        old_data_res = (
            supabase.table("memories")
            .select("user_id, diary_date, topic, summary, keywords, content")
            .eq("id", memory_id)
            .execute()
        )
        if (
            not old_data_res.data
            or old_data_res.data[0].get("user_id") != current_user.id
        ):
            return {"error": "Unauthorized or memory not found"}

        old_data = old_data_res.data[0]
        # Decrypt stored values so they can be merged with new values
        old_data["summary"] = decrypt_text(old_data.get("summary", ""))
        old_data["content"] = decrypt_text(old_data.get("content", ""))
        old_data["topic"] = decrypt_text(old_data.get("topic", ""))
        old_data["keywords"] = [
            decrypt_text(k) for k in (old_data.get("keywords") or [])
        ]

        update_data = {k: v for k, v in memory.model_dump().items() if v is not None}
        if not update_data:
            return {"success": True}

        if update_data.get("original_text"):
            update_data["content"] = update_data["original_text"]
        if "original_text" in update_data:
            del update_data["original_text"]

        # Re-compute embedding if any content field changed
        if any(
            k in update_data
            for k in ["summary", "topic", "keywords", "content", "diary_date"]
        ):
            date = update_data.get("diary_date", old_data.get("diary_date", ""))
            topic = update_data.get("topic", old_data.get("topic", ""))
            summary = update_data.get("summary", old_data.get("summary", ""))
            keywords = update_data.get("keywords", old_data.get("keywords", []))
            content = update_data.get("content", old_data.get("content", ""))

            embedding_text = (
                f"[{date}] 標籤:{topic} - {summary}。"
                f"相關細節：{', '.join(keywords)}。原文：{content}"
            )
            update_data["embedding"] = get_embedding(embedding_text)

        # Encrypt fields before writing
        if "summary" in update_data:
            update_data["summary"] = encrypt_text(
                update_data["summary"], current_user.email
            )
        if "content" in update_data:
            update_data["content"] = encrypt_text(
                update_data["content"], current_user.email
            )
        if "topic" in update_data:
            update_data["topic"] = encrypt_text(
                update_data["topic"], current_user.email
            )
        if "keywords" in update_data:
            update_data["keywords"] = [
                encrypt_text(k, current_user.email) for k in update_data["keywords"]
            ]

        response = (
            supabase.table("memories")
            .update(update_data)
            .eq("id", memory_id)
            .eq("user_id", current_user.id)
            .execute()
        )
        return {"success": True, "data": response.data}
    except Exception as e:
        return {"error": str(e)}


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str, current_user=Depends(get_current_user)):
    try:
        supabase.table("memories").delete().eq("id", memory_id).eq(
            "user_id", current_user.id
        ).execute()
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}
