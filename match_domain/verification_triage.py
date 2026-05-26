"""Verification auto-triage config from rule_config (§13.5 phase 4)."""

from __future__ import annotations

import os
from typing import Any

from .rule_config import resolve_effective_rules
from .rule_config_schema import SLICE_VERIFICATION_AUTO_TRIAGE, code_defaults_for_slice


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


def resolve_verification_triage_config(*, conn=None) -> dict[str, Any]:
    owns_conn = False
    if conn is None:
        conn = _optional_recommendation_conn()
        owns_conn = conn is not None
    try:
        bundle = resolve_effective_rules(SLICE_VERIFICATION_AUTO_TRIAGE, conn=conn)
        params = dict(code_defaults_for_slice(SLICE_VERIFICATION_AUTO_TRIAGE))
        params.update(bundle.params)
        return params
    finally:
        if owns_conn and conn is not None:
            conn.close()


def auto_triage_enabled(*, conn=None) -> bool:
    cfg = resolve_verification_triage_config(conn=conn)
    enabled = cfg.get("enabled")
    if enabled is None:
        raw = os.environ.get("HER_VERIFICATION_AUTO_TRIAGE", "1")
        return str(raw).strip().lower() not in {"0", "false", "no", "off"}
    if isinstance(enabled, bool):
        return enabled
    return str(enabled).strip().lower() not in {"0", "false", "no", "off"}


__all__ = [
    "auto_triage_enabled",
    "resolve_verification_triage_config",
]
