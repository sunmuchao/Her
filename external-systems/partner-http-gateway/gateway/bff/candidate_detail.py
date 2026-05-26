"""GET /v1/candidates/{id} — BFF aggregate read for candidate detail (§13.4)."""

from __future__ import annotations

import re
from typing import Any, Protocol

from match_domain.collected_profile import extract_profile_facts
from match_domain.criteria_snapshots import get_criteria_snapshot_store, snapshot_to_dict
from match_domain.trust_summary import build_trust_summary
from profile_service import get_profile

from ..http_helpers import _json_safe, _query_dict
from ..profile_source_defaults import default_profile_source


class CandidateDetailGateway(Protocol):
    _discovery: Any


def _explain_for_recommendation(recommendation_id: int) -> dict[str, Any] | None:
    store = get_criteria_snapshot_store()
    snapshot = store.get_latest_for_recommendation(int(recommendation_id))
    if snapshot is None:
        return None
    payload = snapshot_to_dict(snapshot)
    return {
        "recommendation_id": int(recommendation_id),
        "source_map": payload.get("source_map") or {},
        "runtime_explanation": payload.get("runtime_explanation"),
        "snapshot_id": payload.get("snapshot_id"),
    }


def rest_candidate_detail(
    gateway: CandidateDetailGateway,
    environ: dict[str, Any],
    candidate_id: str,
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    try:
        profile_id = int(candidate_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("candidate_id must be an integer profile id") from exc

    session_id = (q.get("session_id") or "").strip() or None
    recommendation_id_raw = q.get("recommendation_id")
    recommendation_id: int | None = None
    if recommendation_id_raw not in (None, ""):
        recommendation_id = int(recommendation_id_raw)

    source_dsn, table_name = default_profile_source()
    row = get_profile(
        source_dsn=source_dsn,
        source_table_name=table_name,
        profile_id=profile_id,
    )
    if not row:
        return 404, {"error": {"code": "not_found", "message": "candidate profile not found"}}

    trust = build_trust_summary(row)
    detail_view: dict[str, Any] | None = None
    detail_source = "profile"

    if session_id is not None:
        try:
            discovery_out = gateway._discovery.get_profile_detail(profile_id, session_id=session_id)
            if isinstance(discovery_out, dict):
                detail_view = discovery_out.get("detail_view") or discovery_out
                detail_source = "discovery"
        except Exception:  # noqa: BLE001 — fall back to profile facts
            detail_view = None

    explain = _explain_for_recommendation(recommendation_id) if recommendation_id is not None else None

    return 200, _json_safe(
        {
            "candidate_id": profile_id,
            "profile_id": profile_id,
            "detail_source": detail_source,
            "detail_view": detail_view,
            "profile_facts": extract_profile_facts(row),
            "trust_summary": trust.to_dict(),
            "explain": explain,
        }
    )


def dispatch_candidate_bff(
    gateway: CandidateDetailGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    match = re.fullmatch(r"/v1/candidates/([^/]+)", path.rstrip("/") or "/")
    if match and method == "GET":
        return rest_candidate_detail(gateway, environ, match.group(1))
    return None


__all__ = ["dispatch_candidate_bff", "rest_candidate_detail"]
