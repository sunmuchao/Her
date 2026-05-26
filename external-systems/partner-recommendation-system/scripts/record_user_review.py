#!/usr/bin/env python3

"""Record a pre-delivery user review decision for a recommendation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from _cli_common import bootstrap_script_paths, load_json_arg

bootstrap_script_paths()

_REPO_ROOT = Path(__file__).resolve().parents[3]

from recommendation_system import connect_db, initialize_database, record_user_review  # noqa: E402
from match_domain.script_actor import (  # noqa: E402
    activate_actor_from_args,
    add_actor_cli_args,
    audit_cli_action,
    clear_actor,
)
from recommendation_system.storage import DEFAULT_RECOMMENDATION_MYSQL_DSN  # noqa: E402


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
    add_actor_cli_args(
        parser,
        default_actor_id="system:recommendation-admin",
        default_actor_roles="service_worker",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(_REPO_ROOT / ".env", override=True)
    args = parse_args()
    actor_token = activate_actor_from_args(
        args,
        default_actor_id="system:recommendation-admin",
        default_actor_roles="service_worker",
    )
    conn = connect_db(args.db)
    try:
        initialize_database(conn)
        recommendation = record_user_review(
            conn,
            subscription_id=args.subscription_id,
            candidate_id=args.candidate_id,
            review_type=args.review,
            actor_id=args.actor_id,
            review_payload=load_json_arg(args.payload_json),
        )
        audit_cli_action(
            args,
            action="recommendation.record_review",
            resource_type="recommendation_subscription",
            resource_id=args.subscription_id,
            outcome="succeeded",
            candidate_id=args.candidate_id,
            review_type=args.review,
        )
    except Exception as exc:
        audit_cli_action(
            args,
            action="recommendation.record_review",
            resource_type="recommendation_subscription",
            resource_id=args.subscription_id,
            outcome="failed",
            candidate_id=args.candidate_id,
            review_type=args.review,
            error_message=str(exc),
        )
        raise
    finally:
        conn.close()
        clear_actor(actor_token)
    print(json.dumps(recommendation, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
