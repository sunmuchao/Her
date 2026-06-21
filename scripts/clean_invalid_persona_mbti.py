#!/usr/bin/env python3
"""清理 user_personas / user_persona_observations 中无效 MBTI 历史数据。"""

from __future__ import annotations

import argparse
import json
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

from match_domain.session_end_processor import VALID_MBTI_TYPES
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


def load_persona_rows(dsn: str, limit: int) -> list[dict]:
    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, user_key, self_personality_traits_json
                FROM {quote_mysql_ident("user_personas")}
                WHERE self_personality_traits_json IS NOT NULL
                  AND self_personality_traits_json != ''
                ORDER BY id ASC
                LIMIT %s
                """,
                (int(limit),),
            )
            return list(cursor.fetchall() or [])
    finally:
        release_persona_connection(dsn, conn)


def build_cleaned_traits(raw_value: str) -> tuple[bool, str | None, str | None]:
    text = str(raw_value or "").strip()
    if not text:
        return False, None, None

    try:
        payload = json.loads(text)
    except Exception:
        return False, None, None

    if not isinstance(payload, dict):
        return False, None, None

    mbti = payload.get("mbti")
    if not isinstance(mbti, dict):
        return False, None, None

    type_code = str(mbti.get("type_code") or "").strip().upper()
    if type_code in VALID_MBTI_TYPES:
        return False, None, None

    cleaned = dict(payload)
    cleaned.pop("mbti", None)
    if not cleaned:
        return True, text, None
    return True, text, json.dumps(cleaned, ensure_ascii=False, sort_keys=True)


def apply_cleanup(dsn: str, updates: list[dict]) -> tuple[int, int]:
    if not updates:
        return 0, 0

    conn = mysql_connect(dsn, use_pool=True, timeout=10.0)
    try:
        with conn.cursor() as cursor:
            for item in updates:
                if item["new_value"] is None:
                    cursor.execute(
                        f"""
                        UPDATE {quote_mysql_ident("user_personas")}
                        SET self_personality_traits_json = NULL
                        WHERE id = %s
                        """,
                        (item["id"],),
                    )
                else:
                    cursor.execute(
                        f"""
                        UPDATE {quote_mysql_ident("user_personas")}
                        SET self_personality_traits_json = %s
                        WHERE id = %s
                        """,
                        (item["new_value"], item["id"]),
                    )

                cursor.execute(
                    f"""
                    DELETE FROM {quote_mysql_ident("user_persona_observations")}
                    WHERE user_key = %s
                      AND field_name = 'self_personality_traits_json'
                      AND field_value LIKE %s
                    """,
                    (item["user_key"], '%"type_code": "未测过"%'),
                )
        conn.commit()
        return len(updates), len(updates)
    finally:
        release_persona_connection(dsn, conn)


def main() -> int:
    parser = argparse.ArgumentParser(description="清理无效 MBTI 历史数据")
    parser.add_argument("--persona-dsn", default=None, help="默认读取 PERSONA_MEMORY_MYSQL_SOURCE / HER_PERSONA_DB")
    parser.add_argument("--limit", type=int, default=5000, help="最多扫描多少条 persona 记录")
    parser.add_argument("--apply", action="store_true", help="实际执行清理；默认仅 dry-run")
    args = parser.parse_args()

    dsn = resolve_persona_dsn(args.persona_dsn)
    if not dsn:
        print("缺少 persona DSN。请传 --persona-dsn 或设置 PERSONA_MEMORY_MYSQL_SOURCE。", file=sys.stderr)
        return 2

    rows = load_persona_rows(dsn, args.limit)
    updates: list[dict] = []
    for row in rows:
        changed, old_value, new_value = build_cleaned_traits(row.get("self_personality_traits_json"))
        if changed:
            updates.append({
                "id": row.get("id"),
                "user_key": str(row.get("user_key") or ""),
                "old_value": old_value,
                "new_value": new_value,
            })

    print(f"scanned={len(rows)} invalid_mbti={len(updates)} apply={args.apply}")
    for item in updates[:20]:
        print(
            f"user_key={item['user_key']} persona_id={item['id']} "
            f"old={str(item['old_value'])[:120]} new={str(item['new_value'])[:120]}"
        )

    if not args.apply:
        return 0

    updated, cleaned_obs = apply_cleanup(dsn, updates)
    print(f"updated_personas={updated} cleaned_observations={cleaned_obs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
