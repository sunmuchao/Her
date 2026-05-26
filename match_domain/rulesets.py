"""Named rule sets and version pins for recommendation/search provenance."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .rule_config import bundles_to_effective_params, resolve_subscription_rule_bundles

RULE_PROVENANCE_SCHEMA_V1 = "her.rule_provenance/v1"
RULE_PROVENANCE_SCHEMA = "her.rule_provenance/v2"

# Logical slices — bump the version string when that slice's behavior changes.
RULE_SET_PARTNER_SEARCH_SCORING = "partner_search.scoring"
RULE_SET_PARTNER_SEARCH_RECIPROCAL = "partner_search.reciprocal"
RULE_SET_RECOMMENDATION_CRITERIA = "recommendation.criteria_compiler"
RULE_SET_RECOMMENDATION_DELIVERY_GATE = "recommendation.direct_greet_gate"

CURRENT_RULE_SET_VERSIONS: dict[str, str] = {
    RULE_SET_PARTNER_SEARCH_SCORING: "1.0.0",
    RULE_SET_PARTNER_SEARCH_RECIPROCAL: "1.0.0",
    RULE_SET_RECOMMENDATION_CRITERIA: "1.0.0",
    RULE_SET_RECOMMENDATION_DELIVERY_GATE: "1.1.0",
}


def stable_content_fingerprint(value: Any) -> str:
    """Deterministic SHA-256 over canonical JSON (for persona / search-request snapshots)."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_subscription_refresh_provenance(
    *,
    subscription_id: str,
    persona_profile: Mapping[str, Any] | None,
    search_request: Mapping[str, Any],
    subscription: Mapping[str, Any] | None = None,
    conn=None,
    experiment_bucket: str | None = None,
) -> dict[str, Any]:
    """
    Bundle pinned rule-set versions plus content fingerprints for one saved-search refresh.

    Stored on ``saved_search_runs`` and ``profile_recommendations`` so deliveries and
    ledger actions can be traced back to the rule slice versions, effective params, and inputs used.
    """

    provenance: dict[str, Any] = {
        "schema": RULE_PROVENANCE_SCHEMA,
        "rule_sets": dict(CURRENT_RULE_SET_VERSIONS),
        "fingerprints": {
            "subscription_id": subscription_id,
            "persona_profile": stable_content_fingerprint(dict(persona_profile or {})),
            "search_request": stable_content_fingerprint(dict(search_request or {})),
        },
    }
    if subscription is not None:
        bundles = resolve_subscription_rule_bundles(
            subscription,
            conn=conn,
            experiment_bucket=experiment_bucket,
        )
        provenance["effective_params"] = bundles_to_effective_params(bundles)
    return provenance


def provenance_has_effective_params(provenance: Mapping[str, Any] | None) -> bool:
    if not provenance:
        return False
    effective = provenance.get("effective_params")
    return isinstance(effective, dict) and bool(effective)


__all__ = [
    "CURRENT_RULE_SET_VERSIONS",
    "RULE_PROVENANCE_SCHEMA",
    "RULE_PROVENANCE_SCHEMA_V1",
    "RULE_SET_PARTNER_SEARCH_RECIPROCAL",
    "RULE_SET_PARTNER_SEARCH_SCORING",
    "RULE_SET_RECOMMENDATION_CRITERIA",
    "RULE_SET_RECOMMENDATION_DELIVERY_GATE",
    "build_subscription_refresh_provenance",
    "provenance_has_effective_params",
    "stable_content_fingerprint",
]
