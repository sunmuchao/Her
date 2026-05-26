"""Load fraud_graph rules from external YAML (HER_FRAUD_GRAPH_RULES_PATH)."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "fraud_graph_rules.yaml"
)

_BUILTIN_ENTITY_WEIGHTS: dict[str, int] = {
    "device_fingerprint": 50,
    "external_contact": 45,
    "payment_handle": 45,
    "avatar_fingerprint": 35,
    "image_fingerprint": 30,
    "ip_address": 25,
    "session_fingerprint": 22,
    "ip_segment": 18,
    "message_pattern": 15,
    "registration_path": 12,
    "user_agent": 10,
    "login_city": 8,
}

_BUILTIN_THRESHOLDS: dict[str, int] = {
    "freeze": 160,
    "limit_chat": 100,
    "require_verification": 60,
    "warn": 30,
}


def _rules_path() -> Path:
    configured = str(os.environ.get("HER_FRAUD_GRAPH_RULES_PATH") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _DEFAULT_RULES_PATH.resolve()


@lru_cache(maxsize=1)
def load_rules() -> dict[str, Any]:
    path = _rules_path()
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def entity_type_weights() -> dict[str, int]:
    raw = load_rules().get("entity_type_weights") or {}
    if not isinstance(raw, dict) or not raw:
        return dict(_BUILTIN_ENTITY_WEIGHTS)
    out: dict[str, int] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out or dict(_BUILTIN_ENTITY_WEIGHTS)


def action_threshold(name: str, *, default: int) -> int:
    raw = load_rules().get("action_thresholds") or {}
    if isinstance(raw, dict) and name in raw:
        try:
            return int(raw[name])
        except (TypeError, ValueError):
            pass
    return int(_BUILTIN_THRESHOLDS.get(name, default))


def retention_days(name: str, *, default: int) -> int:
    raw = load_rules().get("retention") or {}
    if isinstance(raw, dict) and name in raw:
        try:
            return int(raw[name])
        except (TypeError, ValueError):
            pass
    return default


def limit_value(name: str, *, default: int) -> int:
    raw = load_rules().get("limits") or {}
    if isinstance(raw, dict) and name in raw:
        try:
            return int(raw[name])
        except (TypeError, ValueError):
            pass
    return default


def contact_marker_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    raw = load_rules().get("contact_marker_patterns") or []
    if not isinstance(raw, list) or not raw:
        return _builtin_contact_patterns()
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        pattern = str(item.get("pattern") or "").strip()
        if not name or not pattern:
            continue
        flags_raw = str(item.get("flags") or "").upper()
        flags = re.IGNORECASE if "IGNORECASE" in flags_raw else 0
        compiled.append((name, re.compile(pattern, flags)))
    return tuple(compiled) if compiled else _builtin_contact_patterns()


def _builtin_contact_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return (
        (
            "wechat",
            re.compile(
                r"(?:微信|vx|v信|wechat)[号是为:：\s\-]*([a-zA-Z][a-zA-Z0-9_\-]{4,31})",
                re.IGNORECASE,
            ),
        ),
        (
            "telegram",
            re.compile(
                r"(?:telegram|tg)[号是为:：\s\-]*([a-zA-Z0-9_]{3,32})",
                re.IGNORECASE,
            ),
        ),
        (
            "whatsapp",
            re.compile(
                r"(?:whatsapp|wa)[号是为:：\s\-]*([a-zA-Z0-9_]{3,32})",
                re.IGNORECASE,
            ),
        ),
        (
            "line",
            re.compile(r"(?:line)[号是为:：\s\-]*([a-zA-Z0-9_]{3,32})", re.IGNORECASE),
        ),
    )


__all__ = [
    "action_threshold",
    "contact_marker_patterns",
    "entity_type_weights",
    "limit_value",
    "load_rules",
    "retention_days",
]
