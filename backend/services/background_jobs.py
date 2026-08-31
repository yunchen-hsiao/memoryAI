"""Durable application jobs backed by Supabase."""

from __future__ import annotations

import json
import logging
import os
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[1]


class JobConflict(Exception):
    """The same user/job type already has an active job."""


class JobStoreUnavailable(Exception):
    """The Phase 4 background_jobs table is unavailable."""


def enqueue_background_job(
    supabase_client: Any,
    user_id: str,
    job_type: str,
    payload: dict[str, Any] | None = None,
) -> str:
    try:
        result = supabase_client.table("background_jobs").insert({
            "user_id": user_id,
            "job_type": job_type,
            "payload": payload or {},
        }).execute()
    except Exception as error:
        message = str(error).lower()
        if "duplicate" in message or "unique" in message:
            raise JobConflict("此類背景任務已在執行中") from error
        raise JobStoreUnavailable("background job store is unavailable") from error

    if not result.data or not result.data[0].get("id"):
        raise JobStoreUnavailable("background job was not created")
    return str(result.data[0]["id"])


def _run_subprocess_job(job_type: str, user_id: str) -> None:
    script = {
        "graph": "build_graph.py",
        "entities": "build_entities.py",
    }[job_type]
    subprocess.run(
        [sys.executable, str(BACKEND_DIR / "scripts" / script), user_id],
        cwd=str(BACKEND_DIR),
        check=True,
    )


def _run_job(job: dict[str, Any]) -> None:
    job_type = job["job_type"]
    user_id = str(job["user_id"])
    payload = job.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)

    if job_type in {"graph", "entities"}:
        _run_subprocess_job(job_type, user_id)
        return
    if job_type == "entity_profile":
        from services.entity_profile_service import update_entity_profiles

        names = [str(name) for name in payload.get("mentioned_names", [])]
        update_entity_profiles(user_id, names)
        return
    raise ValueError(f"unsupported background job type: {job_type}")


def process_background_jobs(
    supabase_client: Any,
    limit: int = 5,
    worker_id: str | None = None,
) -> dict[str, int]:
    worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
    claimed = supabase_client.rpc(
        "claim_background_jobs",
        {"p_worker_id": worker_id, "p_limit": limit},
    ).execute().data or []
    completed = 0
    failed = 0

    for job in claimed:
        job_id = str(job["id"])
        try:
            _run_job(job)
            supabase_client.rpc(
                "complete_background_job",
                {
                    "p_job_id": job_id,
                    "p_success": True,
                    "p_error": None,
                    "p_progress_message": "completed",
                },
            ).execute()
            completed += 1
        except Exception as error:
            failed += 1
            logger.exception("background_job_failed", extra={"job_id": job_id})
            try:
                supabase_client.rpc(
                    "complete_background_job",
                    {
                        "p_job_id": job_id,
                        "p_success": False,
                        "p_error": str(error),
                        "p_progress_message": "failed; scheduled for retry",
                    },
                ).execute()
            except Exception:
                logger.exception("background_job_status_update_failed", extra={"job_id": job_id})

    return {"claimed": len(claimed), "completed": completed, "failed": failed}
