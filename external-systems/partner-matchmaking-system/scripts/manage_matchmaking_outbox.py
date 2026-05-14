#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime

from dotenv import load_dotenv

SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

for root in (SYSTEM_ROOT, REPO_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from matchmaking_system import (  # noqa: E402
    list_failed_outbox,
    list_pending_outbox,
    list_processing_outbox,
    list_retry_pending_outbox,
    requeue_outbox_rows,
    run_matchmaking_outbox_worker,
    serve_matchmaking_outbox_worker,
    summarize_outbox,
)
from matchmaking_system.outbox import recover_stale_outbox_claims  # noqa: E402
from matchmaking_system.storage import (  # noqa: E402
    DEFAULT_MATCHMAKING_MYSQL_DSN,
    connect_db,
    initialize_database,
)
from match_domain.script_actor import (  # noqa: E402
    activate_actor_from_args,
    add_actor_cli_args,
    audit_cli_action,
    clear_actor,
)


def _parse_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage matchmaking outbox consumption and retry queues.")
    parser.add_argument(
        "command",
        choices=(
            "summary",
            "consume",
            "serve",
            "list-pending",
            "list-failed",
            "list-retry",
            "list-processing",
            "recover-stale",
            "requeue",
        ),
    )
    parser.add_argument("--dsn", default=DEFAULT_MATCHMAKING_MYSQL_DSN)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-batches", type=int, default=1)
    parser.add_argument("--retry-delay-seconds", type=int, default=None)
    parser.add_argument("--retry-backoff-multiplier", type=int, default=None)
    parser.add_argument("--retry-max-delay-seconds", type=int, default=None)
    parser.add_argument("--max-attempts", type=int, default=None)
    parser.add_argument("--claim-timeout-seconds", type=int, default=None)
    parser.add_argument("--poll-interval-seconds", type=int, default=None)
    parser.add_argument("--max-idle-polls", type=int, default=None)
    parser.add_argument("--max-runtime-seconds", type=int, default=None)
    parser.add_argument("--worker-name", default=None)
    parser.add_argument("--due-only", action="store_true")
    parser.add_argument("--stale-only", action="store_true")
    parser.add_argument("--outbox-id", action="append", dest="outbox_ids", type=int)
    parser.add_argument("--reset-attempts", action="store_true")
    parser.add_argument("--keep-last-error", action="store_true")
    parser.add_argument("--now", default=None, help="Optional current time in YYYY-MM-DD HH:MM:SS.")
    add_actor_cli_args(
        parser,
        default_actor_id="system:matchmaking-outbox",
        default_actor_roles="service_worker",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=True)
    args = _parse_args()
    now = _parse_datetime(args.now)
    claim_timeout_seconds = args.claim_timeout_seconds or 300
    actor_token = activate_actor_from_args(
        args,
        default_actor_id="system:matchmaking-outbox",
        default_actor_roles="service_worker",
    )
    conn = connect_db(args.dsn)
    try:
        initialize_database(conn)
        if args.command == "summary":
            payload = summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds)
        elif args.command == "consume":
            payload = run_matchmaking_outbox_worker(
                conn,
                limit=args.limit,
                max_batches=args.max_batches,
                retry_delay_seconds=args.retry_delay_seconds,
                retry_backoff_multiplier=args.retry_backoff_multiplier,
                retry_max_delay_seconds=args.retry_max_delay_seconds,
                max_attempts=args.max_attempts,
                claim_timeout_seconds=args.claim_timeout_seconds,
                worker_name=args.worker_name,
                now=now,
            )
        elif args.command == "serve":
            payload = serve_matchmaking_outbox_worker(
                conn,
                limit=args.limit,
                max_batches_per_cycle=args.max_batches,
                retry_delay_seconds=args.retry_delay_seconds,
                retry_backoff_multiplier=args.retry_backoff_multiplier,
                retry_max_delay_seconds=args.retry_max_delay_seconds,
                max_attempts=args.max_attempts,
                claim_timeout_seconds=args.claim_timeout_seconds,
                poll_interval_seconds=args.poll_interval_seconds,
                max_idle_polls=args.max_idle_polls,
                max_runtime_seconds=args.max_runtime_seconds,
                worker_name=args.worker_name,
            )
        elif args.command == "list-pending":
            payload = {
                "rows": list_pending_outbox(conn, limit=args.limit, now=now),
                "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
            }
        elif args.command == "list-failed":
            payload = {
                "rows": list_failed_outbox(conn, limit=args.limit),
                "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
            }
        elif args.command == "list-retry":
            payload = {
                "rows": list_retry_pending_outbox(conn, limit=args.limit, now=now, due_only=bool(args.due_only)),
                "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
            }
        elif args.command == "list-processing":
            payload = {
                "rows": list_processing_outbox(
                    conn,
                    limit=args.limit,
                    now=now,
                    stale_only=bool(args.stale_only),
                    claim_timeout_seconds=claim_timeout_seconds,
                ),
                "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
            }
        elif args.command == "recover-stale":
            recovered = recover_stale_outbox_claims(
                conn,
                now=now,
                claim_timeout_seconds=claim_timeout_seconds,
                retry_delay_seconds=args.retry_delay_seconds or 60,
                max_attempts=args.max_attempts or 3,
                error_message="matchmaking outbox processing timed out",
            )
            conn.commit()
            payload = {
                "recovered": recovered,
                "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
            }
        else:
            changed = requeue_outbox_rows(
                conn,
                list(args.outbox_ids or []),
                reset_attempts=bool(args.reset_attempts),
                clear_error=not bool(args.keep_last_error),
            )
            conn.commit()
            payload = {
                "requeued": changed,
                "outbox_ids": list(args.outbox_ids or []),
                "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
            }
        audit_cli_action(
            args,
            action=f"matchmaking_outbox.{args.command}",
            resource_type="matchmaking_outbox",
            resource_id=args.command,
            outcome="succeeded",
            limit=args.limit,
            outbox_ids=list(args.outbox_ids or []),
        )
    except Exception as exc:
        audit_cli_action(
            args,
            action=f"matchmaking_outbox.{args.command}",
            resource_type="matchmaking_outbox",
            resource_id=args.command,
            outcome="failed",
            error_message=str(exc),
        )
        raise
    finally:
        conn.close()
        clear_actor(actor_token)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
