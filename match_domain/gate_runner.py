"""Unified gate evaluation and recommendation mirror application (§13.1.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from her_time_utils import current_time

from .boundary import assert_recommendation_status_only
from .support_contracts import (
    GATE_OUTCOME_HOLD,
    GATE_OUTCOME_PASS,
    GATE_OUTCOME_REJECT,
    OWNER_MODERATION,
    OWNER_RECOMMENDATION_GATE,
    SUBJECT_RECOMMENDATION,
    SUBJECT_SEARCH_CANDIDATE,
    GateDecision,
)

from .reason_codes import normalize_reason_codes, reason_codes_from_final_review

_FINAL_REVIEW_TO_OUTCOME = {
    "rejected": GATE_OUTCOME_REJECT,
    "review_deferred": GATE_OUTCOME_HOLD,
    "save_only": GATE_OUTCOME_HOLD,
    "direct_greet_ready": GATE_OUTCOME_PASS,
    "match_ready": GATE_OUTCOME_PASS,
}


def _unique_reason_codes(*groups: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for group in groups:
        for code in group:
            normalized = str(code or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def evaluate_candidate_search_gate(
    candidate: Mapping[str, Any],
    *,
    moderation_dsn: str | None = None,
) -> GateDecision:
    """Post-search moderation gate for a single candidate record."""
    profile_id = candidate.get("id")
    subject_id = str(profile_id if profile_id is not None else candidate.get("name") or "unknown")
    reason_codes: list[str] = []
    outcome = GATE_OUTCOME_PASS
    owner = OWNER_RECOMMENDATION_GATE

    action = str(candidate.get("account_moderation_action") or "").strip()
    if action in {"limited_exposure", "freeze"}:
        outcome = GATE_OUTCOME_REJECT
        reason_codes.append(f"moderation:{action}")
        owner = OWNER_MODERATION
    elif action in {"require_verification", "limit_chat", "warn"}:
        outcome = GATE_OUTCOME_HOLD
        reason_codes.append(f"moderation:{action}")
        owner = OWNER_MODERATION

    risk_flags = candidate.get("risk_flags") or []
    if isinstance(risk_flags, str):
        risk_flags = [risk_flags]
    for flag in risk_flags:
        normalized = str(flag or "").strip()
        if normalized:
            reason_codes.append(f"risk:{normalized}")

    if moderation_dsn and not action and candidate.get("profile_review_status") == "needs_review":
        outcome = GATE_OUTCOME_HOLD
        reason_codes.append("moderation:needs_review")
        owner = OWNER_MODERATION

    return GateDecision(
        subject_type=SUBJECT_SEARCH_CANDIDATE,
        subject_id=subject_id,
        outcome=outcome,
        reason_codes=_unique_reason_codes(reason_codes),
        owner_service=owner,
        evaluated_at=current_time(),
        details_ref=f"search_candidate:{subject_id}" if reason_codes else None,
    )


def evaluate_recommendation_gate(
    *,
    candidate_id: int,
    final_review: Mapping[str, Any],
    risk_flags: list[Any] | None = None,
) -> GateDecision:
    status = str(final_review.get("status") or "").strip()
    outcome = _FINAL_REVIEW_TO_OUTCOME.get(status, GATE_OUTCOME_HOLD)
    reason_codes = reason_codes_from_final_review(final_review)
    for flag in risk_flags or []:
        normalized = str(flag or "").strip()
        if normalized:
            reason_codes.append(f"risk:{normalized}")

    return GateDecision(
        subject_type=SUBJECT_RECOMMENDATION,
        subject_id=str(candidate_id),
        outcome=outcome,
        reason_codes=normalize_reason_codes(reason_codes),
        owner_service=OWNER_RECOMMENDATION_GATE,
        evaluated_at=current_time(),
        details_ref=f"recommendation_gate:final_review:{status}",
    )


def apply_gate_decision(
    decision: GateDecision,
    *,
    delivery_status: str,
    delivery_reason: str | None,
) -> dict[str, Any]:
    """Return mirror columns for profile_recommendations; validate delivery_status ownership."""
    assert_recommendation_status_only(delivery_status)
    mirror = {
        "gate_outcome": decision.outcome,
        "gate_reason_codes": list(decision.reason_codes),
        "gate_owner_service": decision.owner_service,
        "gate_details_ref": decision.details_ref,
        "gate_evaluated_at": decision.evaluated_at,
    }
    if decision.outcome == GATE_OUTCOME_REJECT and delivery_status not in {"suppressed", "cooled_down", "skipped_by_user"}:
        mirror["delivery_status_hint"] = "suppressed"
        mirror["delivery_reason_hint"] = delivery_reason or "gate_reject"
    elif decision.outcome == GATE_OUTCOME_HOLD and delivery_status == "pending_delivery":
        mirror["delivery_status_hint"] = "review_pending"
        mirror["delivery_reason_hint"] = delivery_reason or "gate_hold"
    return mirror


def recommendation_row_gate_fields(decision: GateDecision) -> dict[str, Any]:
    import json

    evaluated_at = decision.evaluated_at or current_time()
    return {
        "gate_outcome": decision.outcome,
        "gate_reason_codes_json": json.dumps(decision.reason_codes, ensure_ascii=False),
        "gate_owner_service": decision.owner_service,
        "gate_details_ref": decision.details_ref,
        "gate_evaluated_at": evaluated_at,
    }


__all__ = [
    "apply_gate_decision",
    "evaluate_candidate_search_gate",
    "evaluate_recommendation_gate",
    "recommendation_row_gate_fields",
]
