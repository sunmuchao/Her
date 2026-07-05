"""Ops-only REST routes under /v1/ops/* (§13.4)."""

from __future__ import annotations

from typing import Mapping
from typing import Any, Protocol

from match_domain import get_trace_id
from observability.photo_search_metrics import build_photo_search_dashboard

from .http_helpers import _parse_json_body, _query_dict, _read_body
from .role_sets import INTERNAL_WRITE_ROLES


class OpsGateway(Protocol):
    def _require_roles(
        self,
        environ: dict[str, Any],
        roles: frozenset[str],
        *,
        message: str,
    ) -> Any: ...

    def _build_async_job_dashboard(self, *, limit: int) -> dict[str, Any]: ...


def rest_ops_async_job_dashboard(
    gateway: OpsGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot inspect the async job dashboard",
    )
    q = _query_dict(environ)
    try:
        limit = int(q.get("limit", 5))
    except ValueError:
        limit = 5
    return 200, {**gateway._build_async_job_dashboard(limit=limit), "trace_id": get_trace_id()}


def _normalize_photo_search_dashboard_events(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows = payload.get("events") if isinstance(payload, Mapping) else []
    if rows is None and isinstance(payload, Mapping):
        rows = payload.get("rows")
    normalized: list[dict[str, Any]] = []
    for item in list(rows or []):
        if isinstance(item, Mapping):
            normalized.append(dict(item))
    return normalized


def rest_ops_photo_search_dashboard(
    gateway: OpsGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot inspect the photo search dashboard",
    )
    events: list[dict[str, Any]] = []
    if (environ.get("REQUEST_METHOD") or "GET").upper() == "POST":
        payload = _parse_json_body(_read_body(environ))
        events = _normalize_photo_search_dashboard_events(payload)
    dashboard = build_photo_search_dashboard(events)
    return 200, {
        **dashboard,
        "event_count": len(events),
        "trace_id": get_trace_id(),
    }


def dispatch_ops_rest(
    gateway: OpsGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    normalized = path.rstrip("/") or "/"
    if normalized == "/v1/ops/async-jobs/dashboard" and method == "GET":
        return rest_ops_async_job_dashboard(gateway, environ)
    if normalized == "/v1/ops/photo-search/dashboard" and method in {"GET", "POST"}:
        return rest_ops_photo_search_dashboard(gateway, environ)
    return None


__all__ = [
    "dispatch_ops_rest",
    "rest_ops_async_job_dashboard",
    "rest_ops_photo_search_dashboard",
]
