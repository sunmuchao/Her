#!/usr/bin/env python3

"""Record a pre-delivery user review decision for a recommendation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_partner_rec_root = Path(__file__).resolve().parents[1]
if str(_partner_rec_root) not in sys.path:
    sys.path.insert(0, str(_partner_rec_root))

from recommendation_system import connect_db, initialize_database, record_user_review  # noqa: E402
from recommendation_system.storage import DEFAULT_RECOMMENDATION_MYSQL_DSN  # noqa: E402


def load_json_arg(value: str | None) -> dict:
    if not value:
        return {}
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Record a user review decision before delivery.")
    parser.add_argument(
        "--db",
        default=DEFAULT_RECOMMENDATION_MYSQL_DSN,
        help="MySQL DSN for recommendation state (env PARTNER_RECOMMENDATION_DB).",
    )
    parser.add_argument("--subscription-id", required=True, help="Saved-search subscription id.")
    parser.add_argument("--candidate-id", required=True, type=int, help="Candidate id from partner-search.")
    parser.add_argument(
        "--review",
        required=True,
        choices=["skip", "save", "direct_greet"],
        help="The user's pre-delivery review decision.",
    )
    parser.add_argument("--payload-json", default=None, help="Optional JSON string or @file with extra review context.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = connect_db(args.db)
    initialize_database(conn)
    recommendation = record_user_review(
        conn,
        subscription_id=args.subscription_id,
        candidate_id=args.candidate_id,
        review_type=args.review,
        review_payload=load_json_arg(args.payload_json),
    )
    print(json.dumps(recommendation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
