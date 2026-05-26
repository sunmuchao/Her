"""Domain ownership rules for recommendation / matchmaking / case status layering."""

from __future__ import annotations

from typing import Any, Mapping

RECOMMENDATION_STATUS_OWNER = "recommendation"
MATCHMAKING_STATUS_OWNER = "matchmaking"
CASE_STATUS_OWNER_BY_TYPE: dict[str, str] = {
    "proxy_intro": RECOMMENDATION_STATUS_OWNER,
    "matchmaking": MATCHMAKING_STATUS_OWNER,
}

RECOMMENDATION_OWNED_DELIVERY_STATUSES = frozenset(
    {
        "new",
        "review_pending",
        "pending_delivery",
        "delivered",
        "saved_by_user",
        "skipped_by_user",
        "cooled_down",
        "escalated_to_case",
        "saved",
        "skipped",
        "cooling",
        "closed",
    }
)


def case_status_owner(case_type: str | None) -> str:
    normalized = str(case_type or "").strip().lower()
    return CASE_STATUS_OWNER_BY_TYPE.get(normalized, MATCHMAKING_STATUS_OWNER)


def case_progress_owner(active_case: Mapping[str, Any] | None) -> str | None:
    if not active_case:
        return None
    owner = active_case.get("owner_service") or active_case.get("metadata", {}).get("owner_service")
    if owner:
        return str(owner)
    return case_status_owner(str(active_case.get("case_type") or ""))


def assert_recommendation_status_only(delivery_status: str | None) -> None:
    if delivery_status is None:
        return
    normalized = str(delivery_status).strip()
    if normalized and normalized not in RECOMMENDATION_OWNED_DELIVERY_STATUSES:
        raise ValueError(
            f"delivery_status {normalized!r} is not a recommendation-owned status; "
            "case lifecycle must use match_cases.case_status instead."
        )


def assert_gate_mirror_fields(row: Mapping[str, Any]) -> None:
    """Ensure gate mirror columns do not introduce new delivery_status semantics."""
    gate_outcome = row.get("gate_outcome")
    if gate_outcome is None:
        return
    normalized = str(gate_outcome).strip().lower()
    if normalized and normalized not in {"pass", "hold", "reject"}:
        raise ValueError(f"Unsupported gate_outcome: {gate_outcome!r}")
    assert_recommendation_status_only(row.get("delivery_status"))


__all__ = [
    "CASE_STATUS_OWNER_BY_TYPE",
    "MATCHMAKING_STATUS_OWNER",
    "RECOMMENDATION_OWNED_DELIVERY_STATUSES",
    "RECOMMENDATION_STATUS_OWNER",
    "assert_gate_mirror_fields",
    "assert_recommendation_status_only",
    "case_progress_owner",
    "case_status_owner",
]
