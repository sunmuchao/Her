#!/usr/bin/env python3
"""Run §10.3 cutover: proxy-intro migration + ledger backfill + verification."""

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


def _run(cmd: list[str], *, label: str) -> None:
    print(f"\n==> {label}")
    subprocess.run(cmd, cwd=str(REPO_ROOT), check=True)


def _count_table(conn, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
    return int(row["c"] if hasattr(row, "__getitem__") else row[0])


def verify_cutover() -> dict[str, object]:
    from match_domain.proxy_intro_storage import table_names, use_matchmaking_storage

    from recommendation_system import connect_db as connect_rec
    from matchmaking_system import connect_db as connect_mm
    from relationship_ledger import connect_db as connect_ledger

    rec_dsn = os.environ["PARTNER_RECOMMENDATION_DB"]
    mm_dsn = os.environ["PARTNER_MATCHMAKING_DB"]
    ledger_dsn = os.environ["HER_RELATION_LEDGER_DB"]

    rec = connect_rec(rec_dsn)
    mm = connect_mm(mm_dsn)
    ledger = connect_ledger(ledger_dsn)
    try:
        tn = table_names()
        mm_cases = _count_table(mm, tn.cases)
        rec_legacy_cases = 0
        try:
            rec_legacy_cases = _count_table(rec, "match_cases")
        except Exception:
            rec_legacy_cases = -1
        ledger_events = _count_table(ledger, "match_relation_events")
        return {
            "HER_PROXY_INTRO_STORAGE": os.environ.get("HER_PROXY_INTRO_STORAGE", "matchmaking"),
            "use_matchmaking_storage": use_matchmaking_storage(),
            "matchmaking_proxy_intro_cases": mm_cases,
            "recommendation_legacy_match_cases": rec_legacy_cases,
            "relationship_ledger_events": ledger_events,
        }
    finally:
        rec.close()
        mm.close()
        ledger.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Skip migration/backfill; report counts only")
    parser.add_argument("--skip-validate-env", action="store_true")
    args = parser.parse_args()

    _load_dotenv()
    py = sys.executable

    os.environ.setdefault("HER_PROXY_INTRO_STORAGE", "matchmaking")
    os.environ.setdefault("HER_RELATION_LEDGER_READ_MODE", "ledger_primary")

    if not args.skip_validate_env:
        _run(
            [py, str(REPO_ROOT / "scripts" / "validate_tech_optimization_env.py")],
            label="validate §10.3 environment",
        )

    if not args.verify_only:
        _run(
            [py, str(REPO_ROOT / "scripts" / "setup_ledger_and_proxy_intro_storage.py")],
            label="schema migrate + proxy intro copy + ledger backfill",
        )

    report = verify_cutover()
    print(json.dumps({"ok": True, "cutover": report}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
