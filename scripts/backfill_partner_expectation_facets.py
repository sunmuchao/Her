#!/usr/bin/env python3
"""从已有 partner_expectation 里回填更细的检索槽位。"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    from dotenv import load_dotenv

    load_dotenv(repo_root / ".env")
except ImportError:
    pass

from match_domain.session_end_processor import split_partner_expectation_facets
from persona_memory_sync.persona_memory_lib import (
    mysql_connect,
    quote_mysql_ident,
    release_persona_connection,
)


def resolve_persona_dsn(cli_value: str | None) -> str:
    return str(
        cli_value
        or os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE")
        or os.environ.get("HER_PERSONA_DB")
        or ""
    ).strip()


def load_rows(dsn: str, limit: int) -> list[dict]:
    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT summary_id, conversation_id, conversation_type, requester_id, profile_id, summary_text
                FROM {quote_mysql_ident("conversation_summaries")}
                WHERE summary_key = 'partner_expectation'
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (int(limit),),
            )
            return list(cursor.fetchall() or [])
    finally:
        release_persona_connection(dsn, conn)


def plan_rows(rows: list[dict]) -> list[dict]:
    plans: list[dict] = []
    for row in rows:
        split = split_partner_expectation_facets({"partner_expectation": str(row.get("summary_text") or "").strip()})
        extras = {k: v for k, v in split.items() if k != "partner_expectation" and str(v or "").strip()}
        if extras:
            plans.append({**row, "extras": extras})
    return plans


def apply_plans(dsn: str, plans: list[dict]) -> int:
    if not plans:
        return 0

    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            for row in plans:
                for summary_key, summary_text in row["extras"].items():
                    cursor.execute(
                        f"""
                        DELETE FROM {quote_mysql_ident("conversation_summaries")}
                        WHERE conversation_id = %s AND summary_key = %s
                        """,
                        (row["conversation_id"], summary_key),
                    )
                    cursor.execute(
                        f"""
                        INSERT INTO {quote_mysql_ident("conversation_summaries")}
                        (conversation_id, conversation_type, requester_id, profile_id, summary_key, summary_text, vector_status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, 'pending', NOW())
                        """,
                        (
                            row["conversation_id"],
                            row["conversation_type"],
                            row["requester_id"],
                            row["profile_id"],
                            summary_key,
                            summary_text,
                        ),
                    )
        conn.commit()
        return sum(len(row["extras"]) for row in plans)
    finally:
        release_persona_connection(dsn, conn)


def main() -> int:
    parser = argparse.ArgumentParser(description="回填 partner_expectation 的细分槽位")
    parser.add_argument("--persona-dsn", default=None)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    dsn = resolve_persona_dsn(args.persona_dsn)
    if not dsn:
        print("缺少 persona DSN。", file=sys.stderr)
        return 2

    rows = load_rows(dsn, limit=args.limit)
    plans = plan_rows(rows)
    print(f"scanned={len(rows)} rows_with_facets={len(plans)} apply={args.apply}")
    for row in plans[:20]:
        print(
            f"conversation_id={row['conversation_id']} requester_id={row['requester_id']} "
            f"extras={row['extras']}"
        )

    if not args.apply:
        return 0

    inserted = apply_plans(dsn, plans)
    print(f"inserted={inserted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
