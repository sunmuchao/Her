#!/usr/bin/env python3
"""Migrate profiles.preferred_* into user_personas collected fields; clear profile preference/matcher columns."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from persona_memory_sync.persona_memory_lib import (  # noqa: E402
    DEFAULT_PERSONA_TABLE,
    DEFAULT_PROFILE_TABLE,
    mysql_connect,
    quote_mysql_ident,
)
from match_domain.deprecated_profile_columns import (  # noqa: E402
    DEPRECATED_PROFILE_COLUMNS,
    PROFILE_PREFERENCE_TO_PERSONA,
)

PROFILE_PREFERENCE_TO_PERSONA = dict(PROFILE_PREFERENCE_TO_PERSONA)

PROFILE_COLUMNS_TO_CLEAR = list(DEPRECATED_PROFILE_COLUMNS)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


def migrate(
    *,
    source: str,
    dry_run: bool,
    clear_profile_columns: bool,
    limit: int | None,
) -> dict[str, int]:
    conn = mysql_connect(source)
    stats = {"personas_updated": 0, "fields_copied": 0, "profiles_cleared": 0}
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT p.id AS profile_id, up.user_key, up.id AS persona_id, p.*
                FROM {quote_mysql_ident(DEFAULT_PROFILE_TABLE)} p
                JOIN {quote_mysql_ident(DEFAULT_PERSONA_TABLE)} up ON up.profile_id = p.id
                ORDER BY p.id ASC
                """
            )
            rows = cursor.fetchall() or []
            if limit is not None:
                rows = rows[:limit]

            for row in rows:
                persona_updates: dict[str, object] = {}
                for profile_col, persona_col in PROFILE_PREFERENCE_TO_PERSONA.items():
                    value = row.get(profile_col)
                    if value in (None, ""):
                        continue
                    persona_updates[persona_col] = value

                if persona_updates:
                    if dry_run:
                        stats["personas_updated"] += 1
                        stats["fields_copied"] += len(persona_updates)
                    else:
                        set_clause = ", ".join(
                            f"{quote_mysql_ident(col)} = %s" for col in persona_updates
                        )
                        cursor.execute(
                            f"""
                            UPDATE {quote_mysql_ident(DEFAULT_PERSONA_TABLE)}
                            SET {set_clause}, updated_at = NOW()
                            WHERE user_key = %s
                            """,
                            [*persona_updates.values(), row["user_key"]],
                        )
                        stats["personas_updated"] += 1
                        stats["fields_copied"] += len(persona_updates)

                if clear_profile_columns:
                    clear_values = {col: None for col in PROFILE_COLUMNS_TO_CLEAR if col in row}
                    if not clear_values:
                        continue
                    if dry_run:
                        stats["profiles_cleared"] += 1
                    else:
                        set_clause = ", ".join(
                            f"{quote_mysql_ident(col)} = NULL" for col in clear_values
                        )
                        cursor.execute(
                            f"""
                            UPDATE {quote_mysql_ident(DEFAULT_PROFILE_TABLE)}
                            SET {set_clause}
                            WHERE id = %s
                            """,
                            (row["profile_id"],),
                        )
                        stats["profiles_cleared"] += 1

        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return stats


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description="Migrate profile preferences into user_personas")
    parser.add_argument(
        "--source",
        default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE")
        or os.environ.get("PARTNER_SEARCH_MYSQL_SOURCE")
        or "",
        help="MySQL DSN for persona/profile tables",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--clear-profile-columns", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if not args.source:
        print("Provide --source or set PERSONA_MEMORY_MYSQL_SOURCE", file=sys.stderr)
        return 2
    stats = migrate(
        source=args.source,
        dry_run=args.dry_run,
        clear_profile_columns=args.clear_profile_columns,
        limit=args.limit,
    )
    print(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
