#!/usr/bin/env python3
"""Seed global rule_config versions from code/env defaults (§13.5 phase 2)."""

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


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from db_migrations.runner import initialize_target_database
    from match_domain.rule_config_store import seed_global_defaults_from_code

    source = os.environ.get("PARTNER_RECOMMENDATION_DB", "").strip()
    if not source:
        raise SystemExit("PARTNER_RECOMMENDATION_DB is required")

    if args.dry_run:
        print(f"would migrate recommendation + seed rule config at {source}")
        return 0

    import outer_system_mysql_schema as schema

    cfg = schema.parse_mysql_dsn(source)
    schema.ensure_database(cfg)
    conn = schema.mysql_database_connect(cfg)
    try:
        result = initialize_target_database(
            conn,
            target="recommendation",
            config=cfg,
            mode="migrate",
            source=source,
        )
        applied = [m.get("migration_id") for m in result.get("applied", [])]
        print(f"migrations applied={applied or '(none)'}")
        created = seed_global_defaults_from_code(conn)
        print(f"seeded rule config versions={created or '(none)'}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
