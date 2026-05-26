"""Helpers for CLI scripts that need a consistent actor and audit context."""

from __future__ import annotations

import argparse
from typing import Iterable

from observability import audit_event

from her_runtime_context import reset_actor_context, set_actor_context


def add_actor_cli_args(
    parser: argparse.ArgumentParser,
    *,
    default_actor_id: str,
    default_actor_roles: str | Iterable[str],
) -> None:
    parser.add_argument(
        "--actor-id",
        default=None,
        help=f"Audit actor id. Defaults to {default_actor_id}.",
    )
    parser.add_argument(
        "--actor-roles",
        default=None,
        help=(
            "Comma-separated audit roles. "
            f"Defaults to {','.join(_role_list(default_actor_roles))}."
        ),
    )
    parser.add_argument(
        "--audit-reason",
        default=None,
        help="Optional human-readable reason for this administrative action.",
    )


def activate_actor_from_args(
    args: argparse.Namespace,
    *,
    default_actor_id: str,
    default_actor_roles: str | Iterable[str],
    auth_source: str = "cli",
):
    actor_id = str(getattr(args, "actor_id", None) or default_actor_id).strip() or default_actor_id
    actor_roles = getattr(args, "actor_roles", None) or ",".join(_role_list(default_actor_roles))
    reason = getattr(args, "audit_reason", None)
    args.actor_id = actor_id
    args.actor_roles = actor_roles
    return set_actor_context(
        actor_id,
        actor_roles=actor_roles,
        auth_source=auth_source,
        reason=reason,
    )


def clear_actor(token) -> None:
    reset_actor_context(token)


def audit_cli_action(
    args: argparse.Namespace,
    *,
    action: str,
    resource_type: str,
    outcome: str,
    resource_id: str | int | None = None,
    **context,
) -> None:
    audit_event(
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        reason=getattr(args, "audit_reason", None),
        **context,
    )


def _role_list(raw: str | Iterable[str]) -> list[str]:
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    return [str(part).strip() for part in raw if str(part).strip()]


__all__ = [
    "activate_actor_from_args",
    "add_actor_cli_args",
    "audit_cli_action",
    "clear_actor",
]
