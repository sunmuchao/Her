#!/usr/bin/env python3
"""检查候选池关键摘要覆盖率。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    from dotenv import load_dotenv

    load_dotenv(repo_root / ".env")
except ImportError:
    pass

from outer_system_mysql_schema import quote_mysql_ident
from persona_memory_sync.persona_memory_lib import mysql_connect, release_persona_connection

SUMMARY_KEYS = (
    "personality_traits",
    "values",
    "emotional_needs",
    "life_attitude",
)


def _source() -> str:
    return (
        os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE")
        or os.environ.get("HER_DISCOVERY_PROFILE_SOURCE")
        or os.environ.get("PARTNER_SEARCH_MYSQL_SOURCE")
        or ""
    ).strip()


def main() -> int:
    source = _source()
    if not source:
        print("Missing MySQL source. Set PERSONA_MEMORY_MYSQL_SOURCE or HER_DISCOVERY_PROFILE_SOURCE.")
        return 1

    conn = mysql_connect(source, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            placeholders = ", ".join(["%s"] * len(SUMMARY_KEYS))
            cursor.execute(
                f"""
                SELECT
                    COUNT(DISTINCT p.id) AS total_candidates,
                    COUNT(DISTINCT CASE WHEN cs.profile_id IS NOT NULL THEN p.id END) AS covered_candidates
                FROM {quote_mysql_ident("profiles")} p
                LEFT JOIN {quote_mysql_ident("conversation_summaries")} cs
                  ON cs.profile_id = p.id
                 AND cs.summary_key IN ({placeholders})
                WHERE p.profile_status = 'active'
                """,
                SUMMARY_KEYS,
            )
            row = cursor.fetchone() or {}
            total_candidates = int(row.get("total_candidates") or 0)
            covered_candidates = int(row.get("covered_candidates") or 0)
            coverage = round((covered_candidates / total_candidates) * 100, 2) if total_candidates else 0.0

            print("candidate_summary_coverage")
            print(f"summary_keys={','.join(SUMMARY_KEYS)}")
            print(f"total_candidates={total_candidates}")
            print(f"covered_candidates={covered_candidates}")
            print(f"coverage_percent={coverage}")
        return 0
    finally:
        release_persona_connection(source, conn)


if __name__ == "__main__":
    raise SystemExit(main())
