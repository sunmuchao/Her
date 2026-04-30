#!/usr/bin/env python3

"""Create a saved-search subscription for the Phase 3 recommendation system."""

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

from recommendation_system import connect_db, create_subscription, initialize_database  # noqa: E402


def load_json_arg(value: str | None, default):
    if not value:
        return default
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Phase 3 saved-search subscription.")
    parser.add_argument("--db", required=True, help="SQLite database path for the external recommendation system.")
    parser.add_argument("--requester-id", required=True, type=int, help="Stable requester id in the outer product system.")
    parser.add_argument("--source", required=True, help="Partner-search MySQL DSN.")
    parser.add_argument("--title", default=None, help="Human-readable subscription title.")
    parser.add_argument("--table-name", default=None, help="Optional MySQL table override.")
    parser.add_argument("--photos-table-name", default=None, help="Optional MySQL photos table override.")
    parser.add_argument("--criteria-json", required=True, help="JSON string or @file for the saved search criteria.")
    parser.add_argument("--self-profile-json", default=None, help="JSON string or @file for the requester profile.")
    parser.add_argument("--limit-count", type=int, default=10, help="How many candidates to ask partner-search for each refresh.")
    parser.add_argument("--top-k", type=int, default=5, help="How many top candidates to track for reminders.")
    parser.add_argument("--min-notify-score", type=int, default=40, help="Minimum score required before the outer system will queue a reminder.")
    parser.add_argument("--daily-notification-cap", type=int, default=2, help="How many recommendation cards the requester can receive per day.")
    parser.add_argument("--quiet-hours-start", type=int, default=22, help="Quiet-hour start in local 24h time.")
    parser.add_argument("--quiet-hours-end", type=int, default=9, help="Quiet-hour end in local 24h time.")
    parser.add_argument("--refresh-interval-hours", type=int, default=24, help="How often this subscription becomes due again.")
    parser.add_argument("--skip-cooldown-days", type=int, default=30, help="Cooldown after a user presses skip.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    conn = connect_db(args.db)
    initialize_database(conn)
    subscription = create_subscription(
        conn,
        requester_id=args.requester_id,
        source=args.source,
        criteria=load_json_arg(args.criteria_json, {}),
        self_profile=load_json_arg(args.self_profile_json, None),
        title=args.title,
        table_name=args.table_name,
        photos_table_name=args.photos_table_name,
        limit_count=args.limit_count,
        top_k=args.top_k,
        min_notify_score=args.min_notify_score,
        daily_notification_cap=args.daily_notification_cap,
        quiet_hours_start=args.quiet_hours_start,
        quiet_hours_end=args.quiet_hours_end,
        refresh_interval_hours=args.refresh_interval_hours,
        skip_cooldown_days=args.skip_cooldown_days,
    )
    print(json.dumps(subscription, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
