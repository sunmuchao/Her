#!/usr/bin/env python3
"""Backfill relationship_ledger from recommendation, matchmaking, and chat domain events."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for extra in (
    REPO_ROOT,
    REPO_ROOT / "external-systems" / "partner-recommendation-system",
    REPO_ROOT / "external-systems" / "partner-matchmaking-system",
    REPO_ROOT / "external-systems" / "partner-chat-system",
):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from match_domain import (  # noqa: E402
    match_event_from_mapping,
    match_events_from_action_rows,
    match_events_from_case_event_rows,
    matchmaking_relation_key,
    recommendation_relation_key,
)
from recommendation_system import connect_db as connect_recommendation_db  # noqa: E402
from recommendation_system.service import get_subscription  # noqa: E402
from recommendation_system.storage import json_loads  # noqa: E402
from matchmaking_system import connect_db as connect_matchmaking_db  # noqa: E402
from matchmaking_system.service import get_pool_member, list_match_case_events  # noqa: E402
from chat_system import connect_db as connect_chat_db  # noqa: E402
from relationship_ledger import append_event, connect_db as connect_ledger_db  # noqa: E402
from relationship_ledger.storage import DEFAULT_RELATION_LEDGER_MYSQL_DSN  # noqa: E402
from recommendation_system.storage import DEFAULT_RECOMMENDATION_MYSQL_DSN  # noqa: E402
from matchmaking_system.storage import DEFAULT_MATCHMAKING_MYSQL_DSN  # noqa: E402
from chat_system.storage import DEFAULT_CHAT_MYSQL_DSN  # noqa: E402


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


def _replay_recommendation_actions(rec_conn, ledger_conn, *, dry_run: bool) -> int:
    rows = rec_conn.execute(
        """
        SELECT ra.*, pr.subscription_id, pr.candidate_id
        FROM recommendation_actions ra
        JOIN profile_recommendations pr ON pr.recommendation_id = ra.recommendation_id
        ORDER BY ra.occurred_at ASC, ra.action_id ASC
        """
    ).fetchall()
    count = 0
    for row in rows:
        item = dict(row)
        subscription = get_subscription(rec_conn, str(item["subscription_id"]))
        relation_key = recommendation_relation_key(subscription, int(item["candidate_id"]))
        events = match_events_from_action_rows([item])
        for event in events:
            if dry_run:
                count += 1
                continue
            append_event(
                ledger_conn,
                event=event,
                relation_key=relation_key,
                owner_profile_ref=json_loads(subscription.get("owner_profile_ref_json"), None),
                target_profile_ref={
                    "source": subscription["source"],
                    "profile_id": int(item["candidate_id"]),
                },
            )
            count += 1
    return count


def _replay_proxy_intro_cases(
    rec_conn,
    ledger_conn,
    *,
    mm_conn=None,
    dry_run: bool,
) -> int:
    from match_domain.proxy_intro_storage import table_names, use_matchmaking_storage

    case_conn = mm_conn if use_matchmaking_storage() and mm_conn is not None else rec_conn
    cases_table = table_names().cases
    rows = case_conn.execute(
        f"SELECT case_id FROM {cases_table} ORDER BY created_at ASC, case_id ASC"
    ).fetchall()
    count = 0
    for row in rows:
        case_id = str(row["case_id"])
        events = match_events_from_case_event_rows(list_match_case_events(case_conn, case_id))
        case = case_conn.execute(
            f"SELECT * FROM {cases_table} WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        if not case:
            continue
        subscription = get_subscription(rec_conn, str(case["subscription_id"]))
        relation_key = recommendation_relation_key(subscription, int(case["candidate_id"]))
        for event in events:
            if dry_run:
                count += 1
                continue
            append_event(
                ledger_conn,
                event=event,
                relation_key=relation_key,
                owner_profile_ref=json_loads(subscription.get("owner_profile_ref_json"), None),
                target_profile_ref={
                    "source": subscription["source"],
                    "profile_id": int(case["candidate_id"]),
                },
                case_id=case_id,
                case_type="proxy_intro",
            )
            count += 1
    return count


def _replay_matchmaking_cases(mm_conn, ledger_conn, *, dry_run: bool) -> int:
    rows = mm_conn.execute(
        "SELECT case_id, pair_key, first_contact_member_id, second_contact_member_id FROM match_cases ORDER BY created_at ASC"
    ).fetchall()
    count = 0
    for row in rows:
        case_id = str(row["case_id"])
        events = match_events_from_case_event_rows(list_match_case_events(mm_conn, case_id))
        member_low = get_pool_member(mm_conn, str(row["first_contact_member_id"]))
        member_high = get_pool_member(mm_conn, str(row["second_contact_member_id"]))
        relation_key = matchmaking_relation_key(member_low, member_high)
        for event in events:
            if dry_run:
                count += 1
                continue
            append_event(
                ledger_conn,
                event=event,
                relation_key=relation_key,
                owner_profile_ref=member_low.get("profile_ref"),
                target_profile_ref=member_high.get("profile_ref"),
                case_id=case_id,
                case_type="matchmaking",
            )
            count += 1
    return count


def _replay_chat_threads(chat_conn, ledger_conn, *, dry_run: bool) -> int:
    rows = chat_conn.execute(
        "SELECT thread_id, case_id, relation_key, metadata_json FROM chat_threads ORDER BY created_at ASC"
    ).fetchall()
    count = 0
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        relation_key = (
            metadata.get("ledger_relation_key")
            or row.get("relation_key")
            or f"chat-case:{row['case_id']}"
        )
        event_rows = chat_conn.execute(
            """
            SELECT canonical_event_json, occurred_at
            FROM chat_messages
            WHERE thread_id = ?
            ORDER BY occurred_at ASC, message_id ASC
            """,
            (row["thread_id"],),
        ).fetchall()
        for event_row in event_rows:
            canon = json.loads(event_row["canonical_event_json"] or "{}")
            if not isinstance(canon, dict) or not canon.get("event_type"):
                continue
            event = match_event_from_mapping(canon)
            if dry_run:
                count += 1
                continue
            append_event(
                ledger_conn,
                event=event,
                relation_key=str(relation_key),
            )
            count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill relationship_ledger mirror data")
    parser.add_argument("--dry-run", action="store_true", help="Count events without writing")
    args = parser.parse_args()

    _load_dotenv()
    import os

    rec_dsn = os.environ.get("PARTNER_RECOMMENDATION_DB", DEFAULT_RECOMMENDATION_MYSQL_DSN)
    mm_dsn = os.environ.get("PARTNER_MATCHMAKING_DB", DEFAULT_MATCHMAKING_MYSQL_DSN)
    chat_dsn = os.environ.get("PARTNER_CHAT_DB", DEFAULT_CHAT_MYSQL_DSN)
    ledger_dsn = os.environ.get("HER_RELATION_LEDGER_DB", DEFAULT_RELATION_LEDGER_MYSQL_DSN)

    rec_conn = connect_recommendation_db(rec_dsn)
    mm_conn = connect_matchmaking_db(mm_dsn)
    chat_conn = connect_chat_db(chat_dsn)
    ledger_conn = connect_ledger_db(ledger_dsn)
    try:
        totals = {
            "recommendation_actions": _replay_recommendation_actions(rec_conn, ledger_conn, dry_run=args.dry_run),
            "proxy_intro_cases": _replay_proxy_intro_cases(
                rec_conn,
                ledger_conn,
                mm_conn=mm_conn,
                dry_run=args.dry_run,
            ),
            "matchmaking_cases": _replay_matchmaking_cases(mm_conn, ledger_conn, dry_run=args.dry_run),
            "chat_events": _replay_chat_threads(chat_conn, ledger_conn, dry_run=args.dry_run),
        }
    finally:
        rec_conn.close()
        mm_conn.close()
        chat_conn.close()
        ledger_conn.close()

    print(json.dumps({"dry_run": args.dry_run, "totals": totals}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
