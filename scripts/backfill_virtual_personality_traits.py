#!/usr/bin/env python3
"""Backfill synthetic self_personality_traits_json for seeded virtual personas."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from _repo_bootstrap import bootstrap_repo  # noqa: E402

REPO_ROOT = bootstrap_repo()

from persona_memory_sync.persona_memory_lib import (  # noqa: E402
    DEFAULT_PERSONA_TABLE,
    DEFAULT_PROFILE_TABLE,
    mysql_connect,
    quote_mysql_ident,
)
from persona_memory_sync.synthetic_personality_traits import (  # noqa: E402
    build_synthetic_personality_traits,
)


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


def backfill(
    *,
    source: str,
    dry_run: bool,
    overwrite: bool,
    profile_id_min: int,
    profile_id_max: int,
    limit: int | None,
) -> dict[str, int]:
    conn = mysql_connect(source)
    stats = {"selected": 0, "updated": 0, "skipped_existing": 0}
    try:
        with conn.cursor() as cursor:
            existing_clause = "" if overwrite else "AND (up.self_personality_traits_json IS NULL OR TRIM(up.self_personality_traits_json) = '')"
            cursor.execute(
                f"""
                SELECT
                  up.user_key,
                  up.profile_id,
                  up.display_name,
                  up.self_age,
                  up.self_job,
                  up.self_city,
                  up.self_relationship_goal,
                  up.self_marital_status,
                  up.preferred_traits,
                  up.target_want_children,
                  up.created_at AS persona_created_at,
                  up.updated_at AS persona_updated_at,
                  up.self_personality_traits_json,
                  p.age,
                  p.job,
                  p.city,
                  p.relationship_goal,
                  p.marital_status,
                  p.life_routine,
                  p.values,
                  p.notes,
                  p.public_personality,
                  p.public_values
                FROM {quote_mysql_ident(DEFAULT_PERSONA_TABLE)} up
                LEFT JOIN {quote_mysql_ident(DEFAULT_PROFILE_TABLE)} p ON p.id = up.profile_id
                WHERE up.profile_id IS NOT NULL
                  AND up.profile_id BETWEEN %s AND %s
                  {existing_clause}
                ORDER BY up.profile_id ASC
                """,
                (profile_id_min, profile_id_max),
            )
            rows = cursor.fetchall() or []
            if limit is not None:
                rows = rows[:limit]
            stats["selected"] = len(rows)

            for row in rows:
                current = str(row.get("self_personality_traits_json") or "").strip()
                if current and not overwrite:
                    stats["skipped_existing"] += 1
                    continue
                payload = build_synthetic_personality_traits(
                    row,
                    identity=str(row.get("user_key") or row.get("profile_id") or ""),
                )
                if dry_run:
                    stats["updated"] += 1
                    continue
                cursor.execute(
                    f"""
                    UPDATE {quote_mysql_ident(DEFAULT_PERSONA_TABLE)}
                    SET self_personality_traits_json = %s,
                        updated_at = NOW()
                    WHERE user_key = %s
                    """,
                    (
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        str(row.get("user_key") or ""),
                    ),
                )
                stats["updated"] += 1

        if not dry_run:
            conn.commit()
    finally:
        conn.close()
    return stats


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE")
        or os.environ.get("PARTNER_SEARCH_MYSQL_SOURCE")
        or "",
        help="MySQL DSN for persona/profile tables",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing self_personality_traits_json values")
    parser.add_argument("--profile-id-min", type=int, default=1)
    parser.add_argument("--profile-id-max", type=int, default=10000)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    if not args.source:
        print("Provide --source or set PERSONA_MEMORY_MYSQL_SOURCE", file=sys.stderr)
        return 2

    stats = backfill(
        source=args.source,
        dry_run=args.dry_run,
        overwrite=args.overwrite,
        profile_id_min=args.profile_id_min,
        profile_id_max=args.profile_id_max,
        limit=args.limit,
    )
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
