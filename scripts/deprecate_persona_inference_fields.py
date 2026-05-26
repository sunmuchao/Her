#!/usr/bin/env python3
"""Clear persona inference fields without explicit observations (§13.1.2 cleanup)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from _repo_bootstrap import bootstrap_repo  # noqa: E402

REPO_ROOT = bootstrap_repo()

from match_domain.collected_metadata import TAG_FIELDS_REQUIRING_EXPLICIT_OBS  # noqa: E402
from match_domain.collected_profile import INFERENCE_ONLY_PERSONA_FIELDS  # noqa: E402
from persona_memory_sync.persona_memory_lib import (  # noqa: E402
    DEFAULT_OBSERVATION_TABLE,
    DEFAULT_PERSONA_TABLE,
    mysql_connect,
    quote_mysql_ident,
)

CLEAR_ALWAYS = set(INFERENCE_ONLY_PERSONA_FIELDS) | {
    "public_profile_summary_draft",
    "public_preference_summary_draft",
}


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


def _explicit_fields_for_user(cursor, user_key: str) -> set[str]:
    cursor.execute(
        f"""
        SELECT DISTINCT field_name
        FROM {quote_mysql_ident(DEFAULT_OBSERVATION_TABLE)}
        WHERE user_key = %s AND source_type = 'explicit'
        """,
        (user_key,),
    )
    return {str(row["field_name"]) for row in (cursor.fetchall() or [])}


def cleanup(*, source: str, dry_run: bool, limit: int | None) -> dict[str, int]:
    conn = mysql_connect(source)
    stats = {"personas_scanned": 0, "personas_updated": 0, "fields_cleared": 0}
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {quote_mysql_ident(DEFAULT_PERSONA_TABLE)} ORDER BY id ASC")
            rows = cursor.fetchall() or []
            if limit is not None:
                rows = rows[:limit]

            for row in rows:
                stats["personas_scanned"] += 1
                user_key = str(row["user_key"])
                explicit_fields = _explicit_fields_for_user(cursor, user_key)
                updates: dict[str, None] = {}

                for field in CLEAR_ALWAYS:
                    if row.get(field) not in (None, ""):
                        updates[field] = None

                for field in TAG_FIELDS_REQUIRING_EXPLICIT_OBS:
                    if row.get(field) in (None, ""):
                        continue
                    if field not in explicit_fields:
                        updates[field] = None

                if not updates:
                    continue

                stats["personas_updated"] += 1
                stats["fields_cleared"] += len(updates)
                if dry_run:
                    continue

                set_clause = ", ".join(
                    f"{quote_mysql_ident(col)} = NULL" for col in updates
                )
                cursor.execute(
                    f"""
                    UPDATE {quote_mysql_ident(DEFAULT_PERSONA_TABLE)}
                    SET {set_clause}, updated_at = NOW()
                    WHERE user_key = %s
                    """,
                    (user_key,),
                )

        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return stats


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Deprecate persona inference fields without explicit evidence")
    parser.add_argument(
        "--source",
        default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE")
        or os.environ.get("PARTNER_SEARCH_MYSQL_SOURCE")
        or "",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if not args.source:
        print("Provide --source or set PERSONA_MEMORY_MYSQL_SOURCE", file=sys.stderr)
        return 2
    print(cleanup(source=args.source, dry_run=args.dry_run, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
