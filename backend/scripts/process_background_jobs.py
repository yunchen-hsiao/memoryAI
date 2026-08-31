"""Process durable graph/entity background jobs.

Usage: python scripts/process_background_jobs.py [limit]
Run this from a scheduler or a dedicated worker, never from the web request process.
"""

from __future__ import annotations

import json
import logging
import os
import sys

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.background_jobs import process_background_jobs

logging.basicConfig(level=logging.INFO, format="%(message)s")


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"],
    )
    result = process_background_jobs(supabase, limit=limit)
    print(json.dumps({"event": "background_jobs_batch", **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
