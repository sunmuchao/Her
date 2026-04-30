#!/usr/bin/env python3

"""Refresh due saved-search subscriptions and queue new recommendations."""

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

from recommendation_system import connect_db, initialize_database, refresh_due_subscriptions  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Refresh due Phase 3 saved-search subscriptions.")
    parser.add_argument("--db", required=True, help="SQLite database path for the external recommendation system.")
    parser.add_argument(
        "--subscription-id",
        action="append",
        help="Refresh only these subscriptions. Repeatable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = connect_db(args.db)
    initialize_database(conn)
    summaries = refresh_due_subscriptions(conn, subscription_ids=args.subscription_id)
    print(
        json.dumps(
            {
                "refreshed_count": len(summaries),
                "subscriptions": summaries,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
