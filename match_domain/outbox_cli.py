"""Shared CLI for subsystem outbox administration."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pathlib import Path

from dotenv import load_dotenv
from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path
from match_domain.script_actor import (
    activate_actor_from_args,
    add_actor_cli_args,
    audit_cli_action,
    clear_actor,
)


@dataclass(frozen=True)
class OutboxSubsystemSpec:
    name: str
    package: str
    default_dsn_attr: str
    default_actor_id: str
    audit_prefix: str
    include_list_pending: bool
    recover_error_message: str | None


SUBSYSTEM_SPECS: dict[str, OutboxSubsystemSpec] = {
    "recommendation": OutboxSubsystemSpec(
        name="recommendation",
        package="recommendation_system",
        default_dsn_attr="DEFAULT_RECOMMENDATION_MYSQL_DSN",
        default_actor_id="system:recommendation-outbox",
        audit_prefix="recommendation_outbox",
        include_list_pending=True,
        recover_error_message="recommendation outbox processing timed out",
    ),
    "matchmaking": OutboxSubsystemSpec(
        name="matchmaking",
        package="matchmaking_system",
        default_dsn_attr="DEFAULT_MATCHMAKING_MYSQL_DSN",
        default_actor_id="system:matchmaking-outbox",
        audit_prefix="matchmaking_outbox",
        include_list_pending=True,
        recover_error_message="matchmaking outbox processing timed out",
    ),
    "chat": OutboxSubsystemSpec(
        name="chat",
        package="chat_system",
        default_dsn_attr="DEFAULT_CHAT_MYSQL_DSN",
        default_actor_id="system:chat-outbox",
        audit_prefix="chat_outbox",
        include_list_pending=False,
        recover_error_message=None,
    ),
}


def _parse_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")


WORKER_EXPORTS: dict[str, tuple[str, str]] = {
    "recommendation": ("run_recommendation_outbox_worker", "serve_recommendation_outbox_worker"),
    "matchmaking": ("run_matchmaking_outbox_worker", "serve_matchmaking_outbox_worker"),
    "chat": ("run_chat_outbox_worker", "serve_chat_outbox_worker"),
}


def _load_subsystem(spec: OutboxSubsystemSpec) -> dict[str, Any]:
    package = importlib.import_module(spec.package)
    storage = importlib.import_module(f"{spec.package}.storage")
    outbox_module = importlib.import_module(f"{spec.package}.outbox")
    run_name, serve_name = WORKER_EXPORTS[spec.name]
    return {
        "package": package,
        "default_dsn": getattr(storage, spec.default_dsn_attr),
        "connect_db": storage.connect_db,
        "initialize_database": storage.initialize_database,
        "recover_stale_outbox_claims": outbox_module.recover_stale_outbox_claims,
        "list_failed_outbox": package.list_failed_outbox,
        "list_pending_outbox": getattr(package, "list_pending_outbox", None),
        "list_processing_outbox": package.list_processing_outbox,
        "list_retry_pending_outbox": package.list_retry_pending_outbox,
        "requeue_outbox_rows": package.requeue_outbox_rows,
        "summarize_outbox": package.summarize_outbox,
        "run_worker": getattr(package, run_name),
        "serve_worker": getattr(package, serve_name),
    }


def _command_choices(spec: OutboxSubsystemSpec) -> tuple[str, ...]:
    commands = [
        "summary",
        "consume",
        "serve",
    ]
    if spec.include_list_pending:
        commands.append("list-pending")
    commands.extend(
        [
            "list-failed",
            "list-retry",
            "list-processing",
            "recover-stale",
            "requeue",
        ]
    )
    return tuple(commands)


def _parse_args(spec: OutboxSubsystemSpec) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Manage {spec.name} outbox consumption and retry queues.")
    parser.add_argument("command", choices=_command_choices(spec))
    parser.add_argument("--dsn", default=None)
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
        default_actor_id=spec.default_actor_id,
        default_actor_roles="service_worker",
    )
    return parser.parse_args()


def _dispatch_command(
    *,
    spec: OutboxSubsystemSpec,
    loaded: dict[str, Any],
    args: argparse.Namespace,
    conn,
    now: datetime | None,
    claim_timeout_seconds: int,
) -> dict[str, Any]:
    summarize_outbox: Callable[..., dict[str, Any]] = loaded["summarize_outbox"]
    if args.command == "summary":
        return summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds)
    if args.command == "consume":
        return loaded["run_worker"](
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
    if args.command == "serve":
        return loaded["serve_worker"](
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
    if args.command == "list-pending":
        return {
            "rows": loaded["list_pending_outbox"](conn, limit=args.limit, now=now),
            "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
        }
    if args.command == "list-failed":
        return {
            "rows": loaded["list_failed_outbox"](conn, limit=args.limit),
            "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
        }
    if args.command == "list-retry":
        return {
            "rows": loaded["list_retry_pending_outbox"](
                conn,
                limit=args.limit,
                now=now,
                due_only=bool(args.due_only),
            ),
            "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
        }
    if args.command == "list-processing":
        return {
            "rows": loaded["list_processing_outbox"](
                conn,
                limit=args.limit,
                now=now,
                stale_only=bool(args.stale_only),
                claim_timeout_seconds=claim_timeout_seconds,
            ),
            "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
        }
    if args.command == "recover-stale":
        recover_kwargs: dict[str, Any] = {
            "now": now,
            "claim_timeout_seconds": claim_timeout_seconds,
            "retry_delay_seconds": args.retry_delay_seconds or 60,
            "max_attempts": args.max_attempts or 3,
        }
        if spec.recover_error_message:
            recover_kwargs["error_message"] = spec.recover_error_message
        recovered = loaded["recover_stale_outbox_claims"](conn, **recover_kwargs)
        conn.commit()
        return {
            "recovered": recovered,
            "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
        }
    changed = loaded["requeue_outbox_rows"](
        conn,
        list(args.outbox_ids or []),
        reset_attempts=bool(args.reset_attempts),
        clear_error=not bool(args.keep_last_error),
    )
    conn.commit()
    return {
        "requeued": changed,
        "outbox_ids": list(args.outbox_ids or []),
        "summary": summarize_outbox(conn, now=now, claim_timeout_seconds=claim_timeout_seconds),
    }


def main(subsystem: str) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    ensure_partner_system_roots_on_sys_path(repo_root)
    load_dotenv(repo_root / ".env", override=True)
    spec = SUBSYSTEM_SPECS[subsystem]
    loaded = _load_subsystem(spec)
    args = _parse_args(spec)
    now = _parse_datetime(args.now)
    claim_timeout_seconds = args.claim_timeout_seconds or 300
    actor_token = activate_actor_from_args(
        args,
        default_actor_id=spec.default_actor_id,
        default_actor_roles="service_worker",
    )
    conn = loaded["connect_db"](args.dsn or loaded["default_dsn"])
    try:
        loaded["initialize_database"](conn)
        payload = _dispatch_command(
            spec=spec,
            loaded=loaded,
            args=args,
            conn=conn,
            now=now,
            claim_timeout_seconds=claim_timeout_seconds,
        )
        audit_cli_action(
            args,
            action=f"{spec.audit_prefix}.{args.command}",
            resource_type=spec.audit_prefix,
            resource_id=args.command,
            outcome="succeeded",
            limit=args.limit,
            outbox_ids=list(args.outbox_ids or []),
        )
    except Exception as exc:
        audit_cli_action(
            args,
            action=f"{spec.audit_prefix}.{args.command}",
            resource_type=spec.audit_prefix,
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


__all__ = ["SUBSYSTEM_SPECS", "main"]
