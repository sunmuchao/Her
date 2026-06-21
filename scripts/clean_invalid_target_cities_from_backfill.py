#!/usr/bin/env python3
"""清理本次回填中误写的 target_cities 历史值。"""

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

BAD_VALUES = {
    "在无锡,无锡": "无锡",
    "无锡工作定居": "无锡",
}


def resolve_persona_dsn(cli_value: str | None) -> str:
    return str(
        cli_value
        or os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE")
        or os.environ.get("HER_PERSONA_DB")
        or ""
    ).strip()


def load_candidates(dsn: str) -> list[dict]:
    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(BAD_VALUES))
            cursor.execute(
                f"""
                SELECT user_key, target_cities
                FROM {quote_mysql_ident("user_personas")}
                WHERE target_cities IN ({placeholders})
                ORDER BY user_key ASC
                """,
                tuple(BAD_VALUES.keys()),
            )
            return list(cursor.fetchall() or [])
    finally:
        release_persona_connection(dsn, conn)


def apply_cleanup(dsn: str, rows: list[dict]) -> int:
    if not rows:
        return 0

    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            for row in rows:
                user_key = str(row.get("user_key") or "")
                bad_value = str(row.get("target_cities") or "")
                fixed_value = BAD_VALUES[bad_value]
                cursor.execute(
                    f"""
                    UPDATE {quote_mysql_ident("user_personas")}
                    SET target_cities = %s
                    WHERE user_key = %s
                    """,
                    (fixed_value, user_key),
                )
                cursor.execute(
                    f"""
                    DELETE FROM {quote_mysql_ident("user_persona_observations")}
                    WHERE user_key = %s
                      AND field_name = 'target_cities'
                      AND field_value = %s
                    """,
                    (user_key, bad_value),
                )
        conn.commit()
        return len(rows)
    finally:
        release_persona_connection(dsn, conn)


def main() -> int:
    parser = argparse.ArgumentParser(description="清理误写的 target_cities")
    parser.add_argument("--persona-dsn", default=None)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    dsn = resolve_persona_dsn(args.persona_dsn)
    if not dsn:
        print("缺少 persona DSN。", file=sys.stderr)
        return 2

    rows = load_candidates(dsn)
    print(f"candidates={len(rows)} apply={args.apply}")
    for row in rows:
        print(f"user_key={row.get('user_key')} bad_target_cities={row.get('target_cities')}")

    if not args.apply:
        return 0

    fixed = apply_cleanup(dsn, rows)
    print(f"fixed={fixed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
