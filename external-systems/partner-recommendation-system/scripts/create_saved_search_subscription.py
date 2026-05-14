#!/usr/bin/env python3

"""Create a saved-search subscription for the Phase 3 recommendation system."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


_partner_rec_root = Path(__file__).resolve().parents[1]
_repo_root = Path(__file__).resolve().parents[3]
for root in (_partner_rec_root, _repo_root):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from recommendation_system import connect_db, create_subscription, initialize_database  # noqa: E402
from match_domain.script_actor import (  # noqa: E402
    activate_actor_from_args,
    add_actor_cli_args,
    audit_cli_action,
    clear_actor,
)
from recommendation_system.storage import DEFAULT_RECOMMENDATION_MYSQL_DSN  # noqa: E402


def load_json_arg(value: str | None, default):
    if not value:
        return default
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a Phase 3 saved-search subscription.")
    parser.add_argument(
        "--db",
        default=DEFAULT_RECOMMENDATION_MYSQL_DSN,
        help="MySQL DSN for recommendation state (env PARTNER_RECOMMENDATION_DB).",
    )
    parser.add_argument("--requester-id", required=True, type=int, help="Stable requester id in the outer product system.")
    parser.add_argument("--source", required=True, help="Partner-search MySQL DSN.")
    parser.add_argument("--title", default=None, help="Human-readable subscription title.")
    parser.add_argument("--table-name", default=None, help="Optional MySQL table override.")
    parser.add_argument("--photos-table-name", default=None, help="Optional MySQL photos table override.")
    parser.add_argument("--criteria-json", required=True, help="JSON string or @file for the saved search criteria.")
    parser.add_argument(
        "--subscription-overrides-json",
        default=None,
        help="Optional JSON string or @file for subscription-level criteria overrides.",
    )
    parser.add_argument("--self-profile-json", default=None, help="JSON string or @file for the requester profile.")
    parser.add_argument("--self-id", type=int, default=None, help="Optional requester profile id already stored in the partner-search source.")
    parser.add_argument("--limit-count", type=int, default=10, help="How many candidates to ask partner-search for each refresh.")
    parser.add_argument("--top-k", type=int, default=5, help="How many top candidates to track for reminders.")
    parser.add_argument("--min-notify-score", type=int, default=40, help="Minimum score required before the outer system will queue a reminder.")
    parser.add_argument(
        "--recommendation-mode",
        choices=["match_based", "direct_greet_only"],
        default="direct_greet_only",
        help="Whether any high-match candidate can be pushed, or only direct-greet-ready candidates.",
    )
    parser.add_argument(
        "--direct-greet-profile-json",
        default=None,
        help="Optional JSON string or @file describing the extra bar for proactive direct-greet recommendations.",
    )
    parser.add_argument(
        "--max-review-candidates-per-refresh",
        type=int,
        default=3,
        help="How many top candidates can enter the proactive direct-greet review pool per refresh.",
    )
    parser.add_argument(
        "--min-direct-greet-score",
        type=int,
        default=60,
        help="Minimum direct-greet review score required before a candidate can be proactively pushed.",
    )
    parser.add_argument(
        "--allow-follow-up-questions",
        action="store_true",
        help="Allow proactive pushes even when the candidate still has follow-up questions.",
    )
    parser.add_argument(
        "--allow-risk-flags",
        action="store_true",
        help="Allow proactive pushes even when the candidate still has risk flags.",
    )
    parser.add_argument("--daily-notification-cap", type=int, default=2, help="How many recommendation cards the requester can receive per day.")
    parser.add_argument("--quiet-hours-start", type=int, default=22, help="Quiet-hour start in local 24h time.")
    parser.add_argument("--quiet-hours-end", type=int, default=9, help="Quiet-hour end in local 24h time.")
    parser.add_argument("--refresh-interval-hours", type=int, default=24, help="How often this subscription becomes due again.")
    parser.add_argument("--skip-cooldown-days", type=int, default=30, help="Cooldown after a user presses skip.")
    add_actor_cli_args(
        parser,
        default_actor_id="system:recommendation-admin",
        default_actor_roles="service_worker",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(_repo_root / ".env", override=True)
    args = parse_args()
    actor_token = activate_actor_from_args(
        args,
        default_actor_id="system:recommendation-admin",
        default_actor_roles="service_worker",
    )
    conn = connect_db(args.db)
    try:
        initialize_database(conn)
        subscription = create_subscription(
            conn,
            requester_id=args.requester_id,
            source=args.source,
            criteria=load_json_arg(args.criteria_json, {}),
            subscription_overrides=load_json_arg(args.subscription_overrides_json, {}),
            self_profile=load_json_arg(args.self_profile_json, None),
            self_id=args.self_id,
            title=args.title,
            table_name=args.table_name,
            photos_table_name=args.photos_table_name,
            limit_count=args.limit_count,
            top_k=args.top_k,
            min_notify_score=args.min_notify_score,
            recommendation_mode=args.recommendation_mode,
            direct_greet_profile=load_json_arg(args.direct_greet_profile_json, {}),
            max_review_candidates_per_refresh=args.max_review_candidates_per_refresh,
            min_direct_greet_score=args.min_direct_greet_score,
            auto_reject_on_follow_up_questions=not args.allow_follow_up_questions,
            auto_reject_on_risk_flags=not args.allow_risk_flags,
            daily_notification_cap=args.daily_notification_cap,
            quiet_hours_start=args.quiet_hours_start,
            quiet_hours_end=args.quiet_hours_end,
            refresh_interval_hours=args.refresh_interval_hours,
            skip_cooldown_days=args.skip_cooldown_days,
        )
        audit_cli_action(
            args,
            action="recommendation.create_subscription",
            resource_type="recommendation_subscription",
            resource_id=subscription["subscription_id"],
            outcome="succeeded",
            requester_id=args.requester_id,
        )
    except Exception as exc:
        audit_cli_action(
            args,
            action="recommendation.create_subscription",
            resource_type="recommendation_subscription",
            resource_id=str(args.requester_id),
            outcome="failed",
            error_message=str(exc),
        )
        raise
    finally:
        conn.close()
        clear_actor(actor_token)
    print(json.dumps(subscription, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
