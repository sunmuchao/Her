#!/usr/bin/env python3
"""把历史 conversation_summaries 标准化为更适合召回的表达，并重置向量状态。"""

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

from match_domain.retrieval_text_normalizer import normalize_summary_text
from match_domain.session_end_processor import SUMMARY_FIELD_KEYS, validate_summary_text
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


def load_rows(dsn: str, limit: int, requester_id: int | None = None) -> list[dict]:
    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            where_sql = ""
            params: list[object] = []
            if requester_id is not None:
                where_sql = "WHERE requester_id = %s"
                params.append(int(requester_id))

            cursor.execute(
                f"""
                SELECT summary_id, conversation_id, requester_id, summary_key, summary_text, vector_status
                FROM {quote_mysql_ident("conversation_summaries")}
                {where_sql}
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                tuple(params + [int(limit)]),
            )
            return list(cursor.fetchall() or [])
    finally:
        release_persona_connection(dsn, conn)


def plan_changes(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    rewrites: list[dict] = []
    invalid_after_normalization: list[dict] = []

    for row in rows:
        key = str(row.get("summary_key") or "").strip()
        text = str(row.get("summary_text") or "").strip()
        if key not in SUMMARY_FIELD_KEYS:
            continue

        normalized = normalize_summary_text(key, text)
        normalized_text = normalized.normalized_text
        retrieval_text = normalized.retrieval_text
        quality = validate_summary_text(key, normalized_text)

        if quality != "valid":
            invalid_after_normalization.append(
                {
                    **row,
                    "normalized_text": normalized_text,
                    "quality": quality,
                    "applied_rules": normalized.applied_rules,
                }
            )
            continue

        if retrieval_text != text:
            rewrites.append(
                {
                    **row,
                    "normalized_text": normalized_text,
                    "retrieval_text": retrieval_text,
                    "applied_rules": normalized.applied_rules,
                }
            )

    return rewrites, invalid_after_normalization


def apply_changes(dsn: str, rewrites: list[dict]) -> int:
    if not rewrites:
        return 0

    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            for row in rewrites:
                cursor.execute(
                    f"""
                    UPDATE {quote_mysql_ident("conversation_summaries")}
                    SET summary_text = %s, vector_status = 'pending', updated_at = NOW()
                    WHERE summary_id = %s
                    """,
                    (row["retrieval_text"], row["summary_id"]),
                )
        conn.commit()
        return len(rewrites)
    finally:
        release_persona_connection(dsn, conn)


def main() -> int:
    parser = argparse.ArgumentParser(description="标准化历史 conversation_summaries，提高召回一致性")
    parser.add_argument("--persona-dsn", default=None)
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--requester-id", type=int, default=None)
    parser.add_argument("--apply", action="store_true", help="实际更新数据库；默认仅 dry-run")
    args = parser.parse_args()

    dsn = resolve_persona_dsn(args.persona_dsn)
    if not dsn:
        print("缺少 persona DSN。请传 --persona-dsn 或设置 PERSONA_MEMORY_MYSQL_SOURCE。", file=sys.stderr)
        return 2

    rows = load_rows(dsn, limit=args.limit, requester_id=args.requester_id)
    rewrites, invalid_after_normalization = plan_changes(rows)

    print(
        f"scanned={len(rows)} rewrites={len(rewrites)} "
        f"invalid_after_normalization={len(invalid_after_normalization)} apply={args.apply}"
    )

    for row in rewrites[:20]:
        print(
            f"rewrite summary_id={row['summary_id']} requester_id={row['requester_id']} "
            f"key={row['summary_key']} old={row['summary_text'][:80]} "
            f"new={row['retrieval_text'][:80]} rules={row['applied_rules']}"
        )

    for row in invalid_after_normalization[:10]:
        print(
            f"invalid summary_id={row['summary_id']} requester_id={row['requester_id']} "
            f"key={row['summary_key']} old={row['summary_text'][:80]} "
            f"normalized={row['normalized_text'][:80]} quality={row['quality']}"
        )

    if not args.apply:
        return 0

    updated = apply_changes(dsn, rewrites)
    print(f"updated={updated}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
