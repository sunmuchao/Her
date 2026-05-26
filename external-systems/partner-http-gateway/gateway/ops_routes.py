"""Ops-only REST routes under /v1/ops/* (§13.4)."""

from __future__ import annotations

from typing import Any, Protocol

from match_domain import get_trace_id

from .http_helpers import _query_dict
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


def dispatch_ops_rest(
    gateway: OpsGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    normalized = path.rstrip("/") or "/"
    if normalized == "/v1/ops/async-jobs/dashboard" and method == "GET":
        return rest_ops_async_job_dashboard(gateway, environ)
    return None


__all__ = ["dispatch_ops_rest", "rest_ops_async_job_dashboard"]
