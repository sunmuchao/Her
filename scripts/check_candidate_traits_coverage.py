#!/usr/bin/env python3
"""检查候选池 personality traits 覆盖率。"""

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
            cursor.execute(
                f"""
                SELECT
                    COUNT(*) AS total_count,
                    SUM(
                        CASE
                            WHEN up.self_personality_traits_json IS NOT NULL
                             AND TRIM(up.self_personality_traits_json) <> ''
                            THEN 1 ELSE 0
                        END
                    ) AS covered_count
                FROM {quote_mysql_ident("profiles")} p
                LEFT JOIN {quote_mysql_ident("user_personas")} up
                  ON up.profile_id = p.id
                WHERE p.profile_status = 'active'
                """
            )
            row = cursor.fetchone() or {}

            total_count = int(row.get("total_count") or 0)
            covered_count = int(row.get("covered_count") or 0)
            coverage = round((covered_count / total_count) * 100, 2) if total_count else 0.0

            print("candidate_traits_coverage")
            print(f"total_count={total_count}")
            print(f"covered_count={covered_count}")
            print(f"coverage_percent={coverage}")
        return 0
    finally:
        release_persona_connection(source, conn)


if __name__ == "__main__":
    raise SystemExit(main())
