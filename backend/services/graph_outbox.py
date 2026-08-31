"""Durable Neo4j synchronization queue backed by Supabase."""

from __future__ import annotations

import json
import socket
from typing import Any

from graph_db import delete_event_from_graph, upsert_event_to_graph


def enqueue_graph_sync_job(
    supabase_client: Any,
    user_id: str,
    memory_id: str,
    operation: str,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Persist a graph operation; return False only for pre-migration compatibility."""
    if operation not in {"upsert", "delete"}:
        raise ValueError("unsupported graph sync operation")

    try:
        result = supabase_client.table("graph_sync_outbox").insert({
            "user_id": user_id,
            "memory_id": memory_id,
            "operation": operation,
            "payload": payload or {},
        }).execute()
        return bool(result.data)
    except Exception as error:
        # Deployments must run the migration before relying on the queue. Keeping a
        # false return lets an old database use the request-local fallback instead
        # of claiming that a durable job was created when the table is absent.
        print(f"⚠️ graph_sync_outbox enqueue failed: {error}")
        return False


def process_graph_sync_jobs(
    supabase_client: Any,
    limit: int = 10,
    worker_id: str | None = None,
) -> dict[str, int]:
    """Claim and process a bounded batch of idempotent Neo4j operations."""
    worker_id = worker_id or f"{socket.gethostname()}-{id(supabase_client)}"
    claimed = supabase_client.rpc(
        "claim_graph_sync_jobs",
        {"p_worker_id": worker_id, "p_limit": limit},
    ).execute().data or []
    completed = 0
    failed = 0

    for job in claimed:
        job_id = str(job["id"])
        try:
            payload = job.get("payload") or {}
            if isinstance(payload, str):
                payload = json.loads(payload)
            if job["operation"] == "delete":
                delete_event_from_graph(str(job["user_id"]), str(job["memory_id"]))
            else:
                upsert_event_to_graph(
                    user_id=str(job["user_id"]),
                    memory_id=str(job["memory_id"]),
                    date_str=str(payload.get("date_str") or ""),
                    keywords=[str(keyword) for keyword in payload.get("keywords", [])],
                    emotion_score=int(payload.get("emotion_score", 50)),
                    importance_weight=int(payload.get("importance_weight", 3)),
                )
            supabase_client.rpc(
                "complete_graph_sync_job",
                {"p_job_id": job_id, "p_success": True, "p_error": None},
            ).execute()
            completed += 1
        except Exception as error:
            failed += 1
            try:
                supabase_client.rpc(
                    "complete_graph_sync_job",
                    {
                        "p_job_id": job_id,
                        "p_success": False,
                        "p_error": str(error),
                    },
                ).execute()
            except Exception as mark_error:
                print(f"⚠️ 無法更新 graph job 狀態 {job_id}: {mark_error}")
            print(f"⚠️ graph job {job_id} failed: {error}")

    return {"claimed": len(claimed), "completed": completed, "failed": failed}
