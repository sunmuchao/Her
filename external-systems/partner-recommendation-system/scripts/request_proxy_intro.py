#!/usr/bin/env python3

"""Create a proxy-intro case from a recommendation."""

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

from recommendation_system import connect_db, create_match_case, initialize_database  # noqa: E402
from match_domain.script_actor import (  # noqa: E402
    activate_actor_from_args,
    add_actor_cli_args,
    audit_cli_action,
    clear_actor,
)
from recommendation_system.storage import DEFAULT_RECOMMENDATION_MYSQL_DSN  # noqa: E402


def load_json_arg(value: str | None) -> dict:
    if not value:
        return {}
    if value.startswith("@"):
        return json.loads(Path(value[1:]).read_text(encoding="utf-8"))
    return json.loads(value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a proxy-intro case.")
    parser.add_argument(
        "--db",
        default=DEFAULT_RECOMMENDATION_MYSQL_DSN,
        help="MySQL DSN for recommendation state (env PARTNER_RECOMMENDATION_DB).",
    )
    parser.add_argument("--subscription-id", required=True, help="Saved-search subscription id.")
    parser.add_argument("--candidate-id", required=True, type=int, help="Candidate id from partner-search.")
    parser.add_argument("--initiated-by", default="requester", help="Actor creating the case.")
    parser.add_argument("--channel", default="in_app_proxy_intro", help="Outreach channel to store on the case.")
    parser.add_argument("--reply-window-hours", type=int, default=72, help="Reply deadline window in hours.")
    parser.add_argument("--payload-json", default=None, help="Optional JSON string or @file with request context.")
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
        match_case = create_match_case(
            conn,
            subscription_id=args.subscription_id,
            candidate_id=args.candidate_id,
            initiated_by=args.initiated_by,
            outreach_channel=args.channel,
            reply_window_hours=args.reply_window_hours,
            request_payload=load_json_arg(args.payload_json),
        )
        audit_cli_action(
            args,
            action="recommendation.request_proxy_intro",
            resource_type="recommendation_subscription",
            resource_id=args.subscription_id,
            outcome="succeeded",
            candidate_id=args.candidate_id,
            initiated_by=args.initiated_by,
        )
    except Exception as exc:
        audit_cli_action(
            args,
            action="recommendation.request_proxy_intro",
            resource_type="recommendation_subscription",
            resource_id=args.subscription_id,
            outcome="failed",
            candidate_id=args.candidate_id,
            initiated_by=args.initiated_by,
            error_message=str(exc),
        )
        raise
    finally:
        conn.close()
        clear_actor(actor_token)
    print(json.dumps(match_case, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
