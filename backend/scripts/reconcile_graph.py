"""Reconcile Neo4j Event relationships with Supabase memories.

Usage: python scripts/reconcile_graph.py <user_id>
This is an operator-run backfill; it does not print secrets or diary content.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph_db import delete_event_from_graph, get_driver, upsert_event_to_graph
from security import decrypt_text


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("使用方式：python scripts/reconcile_graph.py <user_id>")

    user_id = sys.argv[1]
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"],
    )
    memories = supabase.table("memories").select(
        "id, diary_date, keywords, emotion_score, importance_weight"
    ).eq("user_id", user_id).execute().data or []
    memory_by_id = {str(memory["id"]): memory for memory in memories}

    driver = get_driver()
    with driver.session() as session:
        event_ids = {
            str(record["id"])
            for record in session.run(
                "MATCH (e:Event {user_id: $user_id}) RETURN e.id AS id",
                user_id=user_id,
            )
        }

    orphan_ids = sorted(event_ids - set(memory_by_id))
    for memory_id in orphan_ids:
        delete_event_from_graph(user_id, memory_id)

    synced = 0
    for memory in memories:
        upsert_event_to_graph(
            user_id=user_id,
            memory_id=str(memory["id"]),
            date_str=str(memory.get("diary_date") or ""),
            keywords=[
                decrypt_text(keyword) for keyword in (memory.get("keywords") or [])
            ],
            emotion_score=int(memory.get("emotion_score") or 50),
            importance_weight=int(memory.get("importance_weight") or 3),
        )
        synced += 1

    print(f"Graph reconciliation complete: synced={synced}, removed_orphans={len(orphan_ids)}")


if __name__ == "__main__":
    main()
