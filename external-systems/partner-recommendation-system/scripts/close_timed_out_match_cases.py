#!/usr/bin/env python3

"""Close proxy-intro cases that missed the reply deadline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def ensure_package_root() -> Path:
    package_root = Path(__file__).resolve().parents[1]
    if str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    return package_root


ensure_package_root()

from recommendation_system import close_timed_out_match_cases, connect_db, initialize_database  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Close timed-out proxy-intro cases.")
    parser.add_argument("--db", required=True, help="SQLite database path for the external recommendation system.")
    parser.add_argument("--case-id", action="append", default=None, help="Optional case id to check. Repeatable.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = connect_db(args.db)
    initialize_database(conn)
    summary = close_timed_out_match_cases(conn, case_ids=args.case_id)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
