#!/usr/bin/env python3

"""Record a proxy-intro reply for a case."""

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

from recommendation_system import connect_db, initialize_database, record_match_case_reply  # noqa: E402


def load_json_arg(value: str | None) -> dict:
    if not value:
        return {}
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a proxy-intro reply.")
    parser.add_argument("--db", required=True, help="SQLite database path for the external recommendation system.")
    parser.add_argument("--case-id", required=True, help="Match case id.")
    parser.add_argument(
        "--reply",
        required=True,
        choices=["accepted", "declined"],
        help="The reply to record.",
    )
    parser.add_argument("--payload-json", default=None, help="Optional JSON string or @file with reply context.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = connect_db(args.db)
    initialize_database(conn)
    case = record_match_case_reply(
        conn,
        case_id=args.case_id,
        reply_type=args.reply,
        reply_payload=load_json_arg(args.payload_json),
    )
    print(json.dumps(case, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
