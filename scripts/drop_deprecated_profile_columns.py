#!/usr/bin/env python3
"""Drop deprecated profiles preference/matcher columns after data migration."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from match_domain.deprecated_profile_columns import DEPRECATED_PROFILE_COLUMNS  # noqa: E402
from persona_memory_sync.persona_memory_lib import (  # noqa: E402
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


def drop_columns(*, source: str, dry_run: bool) -> dict[str, int | list[str]]:
    conn = mysql_connect(source)
    dropped: list[str] = []
    skipped: list[str] = []
    try:
        with conn.cursor() as cursor:
            for column in DEPRECATED_PROFILE_COLUMNS:
                cursor.execute(
                    """
                    SELECT 1
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = %s
                      AND COLUMN_NAME = %s
                    LIMIT 1
                    """,
                    (DEFAULT_PROFILE_TABLE, column),
                )
                if cursor.fetchone() is None:
                    skipped.append(column)
                    continue
                if dry_run:
                    dropped.append(column)
                    continue
                cursor.execute(
                    f"ALTER TABLE {quote_mysql_ident(DEFAULT_PROFILE_TABLE)} "
                    f"DROP COLUMN {quote_mysql_ident(column)}"
                )
                dropped.append(column)
        if dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()
    return {"dropped": dropped, "skipped": skipped, "dry_run": dry_run}


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", ""),
        help="MySQL DSN for profiles/persona database",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.source.strip():
        print("PERSONA_MEMORY_MYSQL_SOURCE or --source is required", file=sys.stderr)
        return 1
    result = drop_columns(source=args.source.strip(), dry_run=bool(args.dry_run))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
