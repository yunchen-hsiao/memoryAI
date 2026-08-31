"""Process durable Neo4j synchronization jobs.

Usage: python scripts/process_graph_outbox.py [limit]
Run this from a scheduler/worker, not from the web request process.
"""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.graph_outbox import process_graph_sync_jobs


def main() -> None:
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_KEY"],
    )
    result = process_graph_sync_jobs(supabase, limit=limit)
    print(
        f"Graph outbox: claimed={result['claimed']} "
        f"completed={result['completed']} failed={result['failed']}"
    )


if __name__ == "__main__":
    main()
