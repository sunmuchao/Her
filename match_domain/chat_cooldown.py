"""Configurable assistant cooldown by reason_code (§13.5 phase 4)."""

from __future__ import annotations

import os
from typing import Any, Sequence

from .reason_codes import normalize_reason_codes
from .rule_config import resolve_effective_rules
from .rule_config_schema import SLICE_CHAT_ASSISTANT_COOLDOWN, code_defaults_for_slice


def _optional_recommendation_conn():
    dsn = os.environ.get("PARTNER_RECOMMENDATION_DB", "").strip()
    if not dsn:
        return None
    try:
        import outer_system_mysql_schema as schema

        cfg = schema.parse_mysql_dsn(dsn)
        return schema.mysql_database_connect(cfg)
    except Exception:  # noqa: BLE001
        return None


def resolve_assistant_cooldown_seconds(
    reason_codes: Sequence[Any] | None,
    *,
    conn=None,
    experiment_bucket: str | None = None,
    profile_id: int | None = None,
) -> int:
    owns_conn = False
    if conn is None:
        conn = _optional_recommendation_conn()
        owns_conn = conn is not None
    try:
        from .rule_config import RuleResolutionContext

        bundle = resolve_effective_rules(
            SLICE_CHAT_ASSISTANT_COOLDOWN,
            RuleResolutionContext(experiment_bucket=experiment_bucket, profile_id=profile_id),
            conn=conn,
        )
    finally:
        if owns_conn and conn is not None:
            conn.close()

    defaults = code_defaults_for_slice(SLICE_CHAT_ASSISTANT_COOLDOWN)
    mapping = dict(defaults.get("reason_code_seconds") or {})
    mapping.update(bundle.params.get("reason_code_seconds") or {})
    default_seconds = int(bundle.params.get("default_seconds", defaults.get("default_seconds", 60)))

    for raw in normalize_reason_codes(list(reason_codes or [])):
        key = raw.removeprefix("chat:") if raw.startswith("chat:") else raw
        if key in mapping:
            return int(mapping[key])
        if raw in mapping:
            return int(mapping[raw])
    return default_seconds


def apply_configured_cooldown(decision: dict[str, Any], *, conn=None) -> dict[str, Any]:
    codes = list(decision.get("reason_codes") or [])
    configured = resolve_assistant_cooldown_seconds(codes, conn=conn)
    current = int(decision.get("cooldown_seconds") or 0)
    # Policy floors (post_chat, opening_probe) may require higher cooldowns.
    decision["cooldown_seconds"] = max(current, configured)
    return decision


__all__ = [
    "apply_configured_cooldown",
    "resolve_assistant_cooldown_seconds",
]
