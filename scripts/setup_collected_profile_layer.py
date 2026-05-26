#!/usr/bin/env python3
"""One-shot setup for §13.1.2 collected profile layer (staging/production)."""

from __future__ import annotations

import argparse
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


def _run(cmd: list[str], *, label: str, dry_run: bool) -> None:
    print(f"\n==> {label}")
    print(" ".join(cmd))
    if dry_run:
        return
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)


def _migrate_persona() -> None:
    import outer_system_mysql_schema as schema
    from db_migrations.runner import initialize_target_database

    source = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "").strip()
    if not source:
        raise SystemExit("PERSONA_MEMORY_MYSQL_SOURCE is required")
    cfg = schema.parse_mysql_dsn(source)
    schema.ensure_database(cfg)
    conn = schema.mysql_database_connect(cfg)
    try:
        result = initialize_target_database(
            conn,
            target="persona",
            config=cfg,
            mode="migrate",
            source=source,
        )
        applied = [m.get("migration_id") for m in result.get("applied", [])]
        print(f"persona migrations applied={applied or '(none)'}")
    finally:
        conn.close()


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print steps without executing")
    parser.add_argument(
        "--skip-drop-columns",
        action="store_true",
        help="Skip dropping deprecated profiles columns (after migrate+clear only)",
    )
    args = parser.parse_args()
    py = sys.executable
    dry = bool(args.dry_run)

    print("\n==> persona schema migrate (includes m0003 drop profile preference columns)")
    if not dry:
        _migrate_persona()

    steps = [
        (
            [py, str(REPO_ROOT / "scripts" / "migrate_profile_preferences_to_persona.py"), "--clear-profile-columns"],
            "migrate profiles.preferred_* -> user_personas + clear profile columns",
        ),
        (
            [py, str(REPO_ROOT / "scripts" / "deprecate_persona_inference_fields.py")],
            "deprecate persona inference fields without explicit observations",
        ),
    ]
    if not args.skip_drop_columns:
        steps.append(
            (
                [py, str(REPO_ROOT / "scripts" / "drop_deprecated_profile_columns.py")],
                "drop deprecated profiles preference/matcher columns",
            )
        )

    if os.environ.get("HER_RELATION_LEDGER_DB"):
        steps.extend(
            [
                (
                    [py, str(REPO_ROOT / "scripts" / "migrate_proxy_intro_to_matchmaking.py")],
                    "migrate proxy_intro cases recommendation -> matchmaking",
                ),
                (
                    [py, str(REPO_ROOT / "scripts" / "backfill_relationship_ledger.py")],
                    "backfill relationship_ledger",
                ),
            ]
        )

    for cmd, label in steps:
        _run(cmd, label=label, dry_run=dry)

    print(
        json.dumps(
            {
                "ok": True,
                "dry_run": dry,
                "PERSONA_MEMORY_MYSQL_SOURCE": os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE"),
                "HER_RELATION_LEDGER_DB": os.environ.get("HER_RELATION_LEDGER_DB"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
