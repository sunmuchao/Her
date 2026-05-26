#!/usr/bin/env python3
"""One-shot local setup: schema migrate, proxy-intro rec→mm copy, relationship_ledger backfill."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


def _run(cmd: list[str], *, label: str) -> None:
    print(f"\n==> {label}")
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)


def _migrate_schemas() -> None:
    import outer_system_mysql_schema as schema
    from db_migrations.runner import initialize_target_database

    targets = {
        "matchmaking": os.environ["PARTNER_MATCHMAKING_DB"],
        "relationship_ledger": os.environ["HER_RELATION_LEDGER_DB"],
    }
    for target, dsn in targets.items():
        print(f"\n==> schema upgrade: {target}")
        cfg = schema.parse_mysql_dsn(dsn)
        schema.ensure_database(cfg)
        conn = schema.mysql_database_connect(cfg)
        try:
            result = initialize_target_database(
                conn,
                target=target,
                config=cfg,
                mode="migrate",
                source=dsn,
            )
            applied = [m.get("migration_id") for m in result.get("applied", [])]
            print(f"  applied={applied or '(none)'}")
        finally:
            conn.close()


def main() -> int:
    _load_dotenv()
    py = sys.executable

    _migrate_schemas()

    _run(
        [py, str(REPO_ROOT / "scripts" / "migrate_proxy_intro_to_matchmaking.py")],
        label="migrate proxy_intro cases recommendation → matchmaking",
    )

    _run(
        [py, str(REPO_ROOT / "scripts" / "backfill_relationship_ledger.py")],
        label="backfill relationship_ledger",
    )

    print(
        json.dumps(
            {
                "ok": True,
                "HER_RELATION_LEDGER_DB": os.environ.get("HER_RELATION_LEDGER_DB"),
                "HER_PROXY_INTRO_STORAGE": os.environ.get("HER_PROXY_INTRO_STORAGE"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
