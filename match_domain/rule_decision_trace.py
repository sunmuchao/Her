"""Build human-readable recommendation decision traces (§13.5)."""

from __future__ import annotations

from typing import Any, Mapping

from .reason_codes import describe_reason_code, normalize_reason_codes
from .rulesets import provenance_has_effective_params


def build_recommendation_decision_trace(recommendation: Mapping[str, Any]) -> dict[str, Any]:
    provenance = dict(recommendation.get("rule_provenance") or {})
    gate_codes = normalize_reason_codes(list(recommendation.get("gate_reason_codes") or []))
    return {
        "recommendation_id": recommendation.get("recommendation_id"),
        "subscription_id": recommendation.get("subscription_id"),
        "candidate_id": recommendation.get("candidate_id"),
        "delivery_status": recommendation.get("delivery_status"),
        "final_review_status": recommendation.get("final_review_status"),
        "final_review_reason": recommendation.get("final_review_reason"),
        "gate_outcome": recommendation.get("gate_outcome"),
        "gate_owner_service": recommendation.get("gate_owner_service"),
        "gate_details_ref": recommendation.get("gate_details_ref"),
        "reason_codes": gate_codes,
        "reason_code_labels": [describe_reason_code(code) for code in gate_codes],
        "rule_provenance_schema": provenance.get("schema"),
        "effective_params": dict(provenance.get("effective_params") or {}),
        "has_effective_params": provenance_has_effective_params(provenance),
        "rule_sets": dict(provenance.get("rule_sets") or {}),
    }


__all__ = ["build_recommendation_decision_trace"]
