#!/usr/bin/env python3
"""One-shot local setup: schema migrate, proxy-intro rec→mm copy, relationship_ledger backfill."""

from __future__ import annotations

import json
import os
import subprocess
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


def ensure_snapshot_table() -> None:
    from partner_search.search_snapshot_store import ensure_search_snapshot_table

    print("\n==> ensure partner_search_snapshots table")
    ensure_search_snapshot_table()


def main() -> int:
    _load_dotenv()
    py = sys.executable

    _migrate_schemas()
    ensure_snapshot_table()

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
