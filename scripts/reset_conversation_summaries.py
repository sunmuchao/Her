#!/usr/bin/env python3
"""清空 conversation_summaries 表。"""

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


def count_rows(dsn: str) -> int:
    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) AS count FROM {quote_mysql_ident('conversation_summaries')}"
            )
            row = cursor.fetchone() or {}
            return int(row.get("count") or 0)
    finally:
        release_persona_connection(dsn, conn)


def clear_rows(dsn: str) -> int:
    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"DELETE FROM {quote_mysql_ident('conversation_summaries')}")
            deleted = int(cursor.rowcount or 0)
        conn.commit()
        return deleted
    finally:
        release_persona_connection(dsn, conn)


def main() -> int:
    parser = argparse.ArgumentParser(description="清空 conversation_summaries 表")
    parser.add_argument("--persona-dsn", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    dsn = resolve_persona_dsn(args.persona_dsn)
    if not dsn:
        print("缺少 persona DSN。", file=sys.stderr)
        return 2

    before = count_rows(dsn)
    print(f"before={before} apply={args.apply}")
    if not args.apply:
        return 0

    deleted = clear_rows(dsn)
    after = count_rows(dsn)
    print(f"deleted={deleted} after={after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
