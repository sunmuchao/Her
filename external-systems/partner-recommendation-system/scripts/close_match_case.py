#!/usr/bin/env python3

"""Close an active proxy-intro case."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_partner_rec_root = Path(__file__).resolve().parents[1]
if str(_partner_rec_root) not in sys.path:
    sys.path.insert(0, str(_partner_rec_root))

from recommendation_system import close_match_case, connect_db, initialize_database  # noqa: E402
from recommendation_system.storage import DEFAULT_RECOMMENDATION_MYSQL_DSN  # noqa: E402


def load_json_arg(value: str | None) -> dict:
    if not value:
        return {}
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Close an active proxy-intro case.")
    parser.add_argument(
        "--db",
        default=DEFAULT_RECOMMENDATION_MYSQL_DSN,
        help="MySQL DSN for recommendation state (env PARTNER_RECOMMENDATION_DB).",
    )
    parser.add_argument("--case-id", required=True, help="Match case id.")
    parser.add_argument(
        "--close-reason",
        default="handoff_completed",
        help="Why the case is being closed.",
    )
    parser.add_argument("--actor-type", default="system", help="Actor recorded on the close event.")
    parser.add_argument("--payload-json", default=None, help="Optional JSON string or @file with close context.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = connect_db(args.db)
    initialize_database(conn)
    case = close_match_case(
        conn,
        case_id=args.case_id,
        close_reason=args.close_reason,
        actor_type=args.actor_type,
        close_payload=load_json_arg(args.payload_json),
    )
    print(json.dumps(case, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
