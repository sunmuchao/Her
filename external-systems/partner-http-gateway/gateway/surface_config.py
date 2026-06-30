"""Gateway route surface configuration (§13.4)."""

from __future__ import annotations

import os

SURFACE_ALL = "all"
SURFACE_PUBLIC = "public"
SURFACE_OPS = "ops"
SURFACE_INTERNAL = "internal"

_VALID_SURFACES = frozenset({SURFACE_ALL, SURFACE_PUBLIC, SURFACE_OPS, SURFACE_INTERNAL})


def gateway_surface() -> str:
    raw = (os.environ.get("PARTNER_GATEWAY_SURFACE") or SURFACE_ALL).strip().lower()
    return raw if raw in _VALID_SURFACES else SURFACE_ALL


def jsonrpc_enabled() -> bool:
    raw = (os.environ.get("PARTNER_GATEWAY_ENABLE_JSONRPC") or "1").strip().lower()
    return raw in ("1", "true", "yes")


def _normalize_path(path: str) -> str:
    return (path or "/").rstrip("/") or "/"


def classify_rest_path(path: str) -> str:
    normalized = _normalize_path(path)
    if normalized == "/health":
        return "health"
    if normalized.startswith("/v1/ops/"):
        return "ops"
    if normalized.startswith("/v1/") or normalized.startswith("/v2/"):
        return "public"
    return "other"


def is_rest_path_allowed(path: str, _method: str) -> bool:
    surface = gateway_surface()
    kind = classify_rest_path(path)
    if surface == SURFACE_ALL:
        return True
    if surface == SURFACE_PUBLIC:
        return kind in {"health", "public"}
    if surface == SURFACE_OPS:
        return kind in {"health", "ops"}
    if surface == SURFACE_INTERNAL:
        return kind == "health"
    return True


def is_jsonrpc_allowed() -> bool:
    if not jsonrpc_enabled():
        return False
    surface = gateway_surface()
    return surface in {SURFACE_ALL, SURFACE_INTERNAL}


__all__ = [
    "SURFACE_ALL",
    "SURFACE_INTERNAL",
    "SURFACE_OPS",
    "SURFACE_PUBLIC",
    "classify_rest_path",
    "gateway_surface",
    "is_jsonrpc_allowed",
    "is_rest_path_allowed",
    "jsonrpc_enabled",
]
