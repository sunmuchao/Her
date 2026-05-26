#!/usr/bin/env python3
"""Audit report for §13.1.2 collected profile layer (explicit vs inference separation)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from match_domain.collected_metadata import TAG_FIELDS_REQUIRING_EXPLICIT_OBS  # noqa: E402
from match_domain.collected_profile import INFERENCE_ONLY_PERSONA_FIELDS  # noqa: E402
from match_domain.deprecated_profile_columns import DEPRECATED_PROFILE_COLUMNS  # noqa: E402
from persona_memory_sync.persona_memory_lib import (  # noqa: E402
    DEFAULT_OBSERVATION_TABLE,
    DEFAULT_PERSONA_TABLE,
    DEFAULT_PROFILE_TABLE,
    mysql_connect,
    quote_mysql_ident,
)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
          AND COLUMN_NAME = %s
        LIMIT 1
        """,
        (table, column),
    )
    return cursor.fetchone() is not None


def _non_null_count(cursor, table: str, column: str) -> int:
    if not _column_exists(cursor, table, column):
        return 0
    cursor.execute(
        f"""
        SELECT COUNT(*) AS cnt
        FROM {quote_mysql_ident(table)}
        WHERE {quote_mysql_ident(column)} IS NOT NULL
          AND {quote_mysql_ident(column)} <> ''
        """
    )
    row = cursor.fetchone()
    return int((row["cnt"] if isinstance(row, dict) else row[0]) or 0)


def audit(*, source: str) -> dict[str, Any]:
    conn = mysql_connect(source)
    report: dict[str, Any] = {
        "source": source,
        "profiles": {},
        "personas": {},
        "observations": {},
        "checks": [],
    }
    try:
        with conn.cursor() as cursor:
            deprecated_profile_usage: dict[str, int] = {}
            for column in DEPRECATED_PROFILE_COLUMNS:
                count = _non_null_count(cursor, DEFAULT_PROFILE_TABLE, column)
                if count:
                    deprecated_profile_usage[column] = count
            report["profiles"]["deprecated_columns_with_data"] = deprecated_profile_usage
            report["profiles"]["deprecated_columns_remaining"] = [
                column
                for column in DEPRECATED_PROFILE_COLUMNS
                if _column_exists(cursor, DEFAULT_PROFILE_TABLE, column)
            ]

            inference_hits: dict[str, int] = {}
            for field in INFERENCE_ONLY_PERSONA_FIELDS:
                count = _non_null_count(cursor, DEFAULT_PERSONA_TABLE, field)
                if count:
                    inference_hits[field] = count
            report["personas"]["inference_fields_with_data"] = inference_hits

            tag_without_explicit: dict[str, int] = {}
            for field in TAG_FIELDS_REQUIRING_EXPLICIT_OBS:
                count = _non_null_count(cursor, DEFAULT_PERSONA_TABLE, field)
                if not count:
                    continue
                cursor.execute(
                    f"""
                    SELECT COUNT(DISTINCT user_key) AS cnt
                    FROM {quote_mysql_ident(DEFAULT_OBSERVATION_TABLE)}
                    WHERE field_name = %s
                      AND source_type IN ('explicit', 'profile_form', 'explicit_confirmation')
                    """,
                    (field,),
                )
                row = cursor.fetchone()
                explicit_users = int((row["cnt"] if isinstance(row, dict) else row[0]) or 0)
                if explicit_users == 0:
                    tag_without_explicit[field] = count
            report["personas"]["tag_fields_without_explicit_observation"] = tag_without_explicit

            cursor.execute(
                f"""
                SELECT source_type, COUNT(*) AS cnt
                FROM {quote_mysql_ident(DEFAULT_OBSERVATION_TABLE)}
                GROUP BY source_type
                ORDER BY cnt DESC
                """
            )
            report["observations"]["by_source_type"] = {
                str(row["source_type"] if isinstance(row, dict) else row[0]): int(
                    row["cnt"] if isinstance(row, dict) else row[1]
                )
                for row in (cursor.fetchall() or [])
            }

            cursor.execute(
                f"""
                SELECT COUNT(*) AS cnt
                FROM {quote_mysql_ident(DEFAULT_OBSERVATION_TABLE)}
                WHERE source_channel IS NOT NULL AND source_channel <> ''
                """
            )
            row = cursor.fetchone()
            report["observations"]["with_source_channel"] = int(
                (row["cnt"] if isinstance(row, dict) else row[0]) or 0
            )

            checks: list[dict[str, Any]] = []
            checks.append(
                {
                    "name": "profiles_deprecated_columns_empty",
                    "ok": not deprecated_profile_usage,
                    "detail": deprecated_profile_usage or "all deprecated profile columns empty or dropped",
                }
            )
            checks.append(
                {
                    "name": "persona_inference_fields_empty",
                    "ok": not inference_hits,
                    "detail": inference_hits or "no inference-only persona fields populated",
                }
            )
            checks.append(
                {
                    "name": "tag_fields_have_explicit_observations",
                    "ok": not tag_without_explicit,
                    "detail": tag_without_explicit or "tag fields backed by explicit observations",
                }
            )
            report["checks"] = checks
            report["ok"] = all(item["ok"] for item in checks)
    finally:
        conn.close()
    return report


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", ""),
        help="MySQL DSN for profiles/persona database",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    args = parser.parse_args()
    if not args.source.strip():
        print("PERSONA_MEMORY_MYSQL_SOURCE or --source is required", file=sys.stderr)
        return 1
    report = audit(source=args.source.strip())
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
