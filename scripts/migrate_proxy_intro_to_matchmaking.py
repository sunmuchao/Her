#!/usr/bin/env python3
"""Copy legacy recommendation ``match_cases`` rows into matchmaking ``proxy_intro_*`` tables."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from match_domain.proxy_intro_storage import table_names  # noqa: E402

REC_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"
MM_ROOT = REPO_ROOT / "external-systems" / "partner-matchmaking-system"
for root in (REC_ROOT, MM_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from recommendation_system import connect_db as connect_rec  # noqa: E402
from recommendation_system.storage import DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN  # noqa: E402
from matchmaking_system import connect_db as connect_mm  # noqa: E402
from matchmaking_system.storage import DEFAULT_MATCHMAKING_TEST_MYSQL_DSN  # noqa: E402


def _copy_table(rec_conn, mm_conn, *, source: str, target: str, key_col: str) -> int:
    rows = rec_conn.execute(f"SELECT * FROM {source}").fetchall()
    if not rows:
        return 0
    columns = [desc[0] for desc in rec_conn.execute(f"SELECT * FROM {source} LIMIT 1").description]
    placeholders = ", ".join(["?"] * len(columns))
    col_list = ", ".join(columns)
    copied = 0
    for row in rows:
        payload = tuple(row[col] if hasattr(row, "__getitem__") else getattr(row, col) for col in columns)
        existing = mm_conn.execute(
            f"SELECT 1 FROM {target} WHERE {key_col} = ? LIMIT 1",
            (payload[columns.index(key_col)],),
        ).fetchone()
        if existing:
            continue
        mm_conn.execute(
            f"INSERT INTO {target} ({col_list}) VALUES ({placeholders})",
            payload,
        )
        copied += 1
    return copied


def migrate(*, rec_dsn: str, mm_dsn: str, dry_run: bool) -> dict[str, int]:
    os.environ["HER_PROXY_INTRO_STORAGE"] = "matchmaking"
    tn = table_names()
    rec = connect_rec(rec_dsn)
    mm = connect_mm(mm_dsn)
    try:
        counts = {
            "cases": _copy_table(rec, mm, source="match_cases", target=tn.cases, key_col="case_id"),
            "events": _copy_table(
                rec,
                mm,
                source="match_case_events",
                target=tn.events,
                key_col="event_id",
            ),
            "attempts": _copy_table(
                rec,
                mm,
                source="match_case_outreach_attempts",
                target=tn.attempts,
                key_col="attempt_id",
            ),
        }
        if dry_run:
            rec.rollback()
            mm.rollback()
        else:
            rec.commit()
            mm.commit()
        return counts
    except Exception:
        rec.rollback()
        mm.rollback()
        raise
    finally:
        rec.close()
        mm.close()


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


def main() -> None:
    _load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rec-dsn", default=os.environ.get("PARTNER_RECOMMENDATION_DB", DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN))
    parser.add_argument("--mm-dsn", default=os.environ.get("PARTNER_MATCHMAKING_DB", DEFAULT_MATCHMAKING_TEST_MYSQL_DSN))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    counts = migrate(rec_dsn=args.rec_dsn, mm_dsn=args.mm_dsn, dry_run=args.dry_run)
    print(counts)


if __name__ == "__main__":
    main()
