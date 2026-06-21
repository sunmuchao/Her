#!/usr/bin/env python3
"""清理 conversation_summaries 中不再合法的历史摘要记录。

清理规则：
- 结构化字段（如 age/city/income 等）不应存在于 conversation_summaries
- 摘要字段中，未通过 validate_summary_text() 质检的记录应删除

默认先 dry-run，仅展示待清理记录数量与样例。
"""

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

from match_domain.session_end_processor import (
    STRUCTURED_QUANTIFIABLE_FIELDS,
    validate_summary_text,
)
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


def load_candidates(dsn: str, limit: int) -> list[dict]:
    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT conversation_id, requester_id, summary_key, summary_text, created_at
                FROM {quote_mysql_ident("conversation_summaries")}
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (int(limit),),
            )
            rows = cursor.fetchall()
            return list(rows or [])
    finally:
        release_persona_connection(dsn, conn)


def classify_row(row: dict) -> str | None:
    key = str(row.get("summary_key") or "").strip()
    text = str(row.get("summary_text") or "").strip()

    if key in STRUCTURED_QUANTIFIABLE_FIELDS:
        return "structured_field_in_summary"

    quality = validate_summary_text(key, text)
    if quality != "valid":
        return f"summary_quality_{quality}"

    return None


def delete_rows(dsn: str, rows: list[dict]) -> int:
    if not rows:
        return 0

    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            for row in rows:
                cursor.execute(
                    f"""
                    DELETE FROM {quote_mysql_ident("conversation_summaries")}
                    WHERE conversation_id = %s AND requester_id = %s AND summary_key = %s
                    LIMIT 1
                    """,
                    (
                        row.get("conversation_id"),
                        row.get("requester_id"),
                        row.get("summary_key"),
                    ),
                )
        conn.commit()
        return len(rows)
    finally:
        release_persona_connection(dsn, conn)


def main() -> int:
    parser = argparse.ArgumentParser(description="清理不合法的 conversation_summaries 历史记录")
    parser.add_argument("--persona-dsn", default=None, help="默认读取 PERSONA_MEMORY_MYSQL_SOURCE / HER_PERSONA_DB")
    parser.add_argument("--limit", type=int, default=2000, help="最多扫描多少条记录")
    parser.add_argument("--apply", action="store_true", help="实际执行删除；默认仅 dry-run")
    args = parser.parse_args()

    dsn = resolve_persona_dsn(args.persona_dsn)
    if not dsn:
        print("缺少 persona DSN。请传 --persona-dsn 或设置 PERSONA_MEMORY_MYSQL_SOURCE。", file=sys.stderr)
        return 2

    rows = load_candidates(dsn, args.limit)
    invalid_rows: list[dict] = []

    for row in rows:
        reason = classify_row(row)
        if reason:
            enriched = dict(row)
            enriched["reason"] = reason
            invalid_rows.append(enriched)

    print(f"scanned={len(rows)} invalid={len(invalid_rows)} apply={args.apply}")
    for row in invalid_rows[:20]:
        text = str(row.get("summary_text") or "")
        print(
            f"conversation_id={row.get('conversation_id')} requester_id={row.get('requester_id')} "
            f"key={row.get('summary_key')} reason={row.get('reason')} text={text[:80]}"
        )

    if not args.apply:
        return 0

    deleted = delete_rows(dsn, invalid_rows)
    print(f"deleted={deleted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
