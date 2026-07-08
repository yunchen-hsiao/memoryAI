"""
Shared FastAPI dependencies for MemoryAI API routes.

Provides:
- A module-level Supabase client shared across all route modules
- get_supabase() FastAPI dependency for injecting the client
- get_user_context() / update_user_context() helpers for the
  rolling life-context narrative used by chat and import routes
"""

import datetime
import os

from dotenv import load_dotenv
from supabase import Client, create_client

load_dotenv()

# ---------------------------------------------------------------------------
# Supabase client (module-level singleton)
# ---------------------------------------------------------------------------

supabase_url: str = os.environ.get("SUPABASE_URL", "")
supabase_key: str = os.environ.get("SUPABASE_KEY", "")

supabase: Client = create_client(supabase_url, supabase_key)


def get_supabase() -> Client:
    """
    FastAPI dependency that returns the shared Supabase client.

    Usage::

        @router.get("/example")
        def example(db: Client = Depends(get_supabase)):
            ...
    """
    return supabase


# ---------------------------------------------------------------------------
# Rolling life-context helpers
# ---------------------------------------------------------------------------


def get_user_context(user_id: str) -> str:
    """
    Retrieve the user's rolling life-context narrative from the database.

    Returns a default message when no context row exists yet.
    """
    try:
        res = (
            supabase.table("user_contexts")
            .select("life_context")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0].get(
                "life_context",
                "這是一段全新的人生故事紀錄，目前還沒有任何前情提要。",
            )
    except Exception:
        pass
    return "這是一段全新的人生故事紀錄，目前還沒有任何前情提要。"


def update_user_context(user_id: str, new_context: str) -> None:
    """
    Upsert the user's rolling life-context narrative in the database.

    Failures are logged but do not propagate — a context update failure
    must never cause the parent request to fail.
    """
    try:
        supabase.table("user_contexts").upsert(
            {
                "user_id": user_id,
                "life_context": new_context,
                "updated_at": datetime.datetime.utcnow().isoformat(),
            }
        ).execute()
    except Exception as e:
        print(f"⚠️ 更新 user_context 失敗: {e}")
