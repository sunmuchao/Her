#!/usr/bin/env python3
"""Audit profile_recommendations for rule_provenance effective_params (§13.5)."""

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


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


def audit_conn(conn, *, limit: int = 100) -> dict[str, int]:
    from match_domain.rulesets import provenance_has_effective_params

    rows = conn.execute(
        """
        SELECT recommendation_id, rule_provenance_json
        FROM profile_recommendations
        ORDER BY recommendation_id DESC
        LIMIT ?
        """,
        (int(limit),),
    ).fetchall()
    stats = {"checked": 0, "missing_provenance": 0, "missing_effective_params": 0, "ok": 0}
    for row in rows or []:
        stats["checked"] += 1
        raw = row["rule_provenance_json"] if hasattr(row, "keys") else row[1]
        if not raw:
            stats["missing_provenance"] += 1
            continue
        provenance = json.loads(raw)
        if not provenance_has_effective_params(provenance):
            stats["missing_effective_params"] += 1
        else:
            stats["ok"] += 1
    return stats


def main() -> int:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    source = os.environ.get("PARTNER_RECOMMENDATION_DB", "").strip()
    if not source:
        raise SystemExit("PARTNER_RECOMMENDATION_DB is required")

    import outer_system_mysql_schema as schema

    cfg = schema.parse_mysql_dsn(source)
    conn = schema.mysql_database_connect(cfg)
    try:
        stats = audit_conn(conn, limit=args.limit)
    finally:
        conn.close()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 1 if stats["missing_effective_params"] or stats["missing_provenance"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
