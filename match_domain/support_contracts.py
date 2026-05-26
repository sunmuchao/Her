"""Support-domain contracts consumed by main-chain services (§13.1.3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Mapping

GATE_OUTCOME_PASS = "pass"
GATE_OUTCOME_HOLD = "hold"
GATE_OUTCOME_REJECT = "reject"

GATE_OUTCOMES = frozenset({GATE_OUTCOME_PASS, GATE_OUTCOME_HOLD, GATE_OUTCOME_REJECT})

SUBJECT_RECOMMENDATION = "recommendation"
SUBJECT_PROFILE = "profile"
SUBJECT_SEARCH_CANDIDATE = "search_candidate"

OWNER_MODERATION = "moderation"
OWNER_VERIFICATION = "verification"
OWNER_RECOMMENDATION_GATE = "recommendation_gate"
OWNER_OPS = "ops"


@dataclass(frozen=True)
class Principal:
    user_id: str | None
    profile_id: int | None
    roles: frozenset[str]
    auth_source: str
    user_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        from match_domain.principal import user_key_from_profile_id

        profile_id = self.profile_id
        resolved_user_key = self.user_key or user_key_from_profile_id(profile_id)
        return {
            "user_id": self.user_id,
            "profile_id": profile_id,
            "requester_id": profile_id,
            "user_key": resolved_user_key,
            "roles": sorted(self.roles),
            "auth_source": self.auth_source,
        }


@dataclass
class TrustSummary:
    profile_id: int
    verified_level: str | None = None
    labels: list[str] = field(default_factory=list)
    field_verifications: dict[str, str] = field(default_factory=dict)
    verified_label: str | None = None
    photo_verification_label: str | None = None
    headline: str | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.updated_at is not None:
            payload["updated_at"] = self.updated_at.isoformat()
        return payload


@dataclass
class GateDecision:
    subject_type: str
    subject_id: str
    outcome: str
    reason_codes: list[str] = field(default_factory=list)
    owner_service: str = OWNER_RECOMMENDATION_GATE
    evaluated_at: datetime | None = None
    details_ref: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.evaluated_at is not None:
            payload["evaluated_at"] = self.evaluated_at.isoformat()
        return payload


@dataclass
class OpsOverride:
    target_owner: str
    target_id: str
    action: str
    operator_id: str
    reason: str | None = None
    expires_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.expires_at is not None:
            payload["expires_at"] = self.expires_at.isoformat()
        return payload


def principal_from_actor(actor: Any, *, profile_id: int | None = None) -> Principal:
    from match_domain.principal import user_key_from_profile_id

    user_id = str(getattr(actor, "actor_id", "") or "") or None
    roles = getattr(actor, "roles", frozenset()) or frozenset()
    if not isinstance(roles, frozenset):
        roles = frozenset(roles)
    return Principal(
        user_id=user_id,
        profile_id=profile_id,
        roles=roles,
        auth_source=str(getattr(actor, "auth_source", "") or "unknown"),
        user_key=user_key_from_profile_id(profile_id),
    )


def gate_decision_from_mapping(raw: Mapping[str, Any] | None) -> GateDecision | None:
    if not raw:
        return None
    outcome = str(raw.get("outcome") or raw.get("gate_outcome") or "").strip()
    if outcome not in GATE_OUTCOMES:
        return None
    reason_codes = raw.get("reason_codes") or raw.get("gate_reason_codes") or []
    if isinstance(reason_codes, str):
        reason_codes = [part.strip() for part in reason_codes.split(",") if part.strip()]
    return GateDecision(
        subject_type=str(raw.get("subject_type") or SUBJECT_RECOMMENDATION),
        subject_id=str(raw.get("subject_id") or ""),
        outcome=outcome,
        reason_codes=[str(code) for code in reason_codes if code],
        owner_service=str(raw.get("owner_service") or OWNER_RECOMMENDATION_GATE),
        details_ref=(str(raw["details_ref"]) if raw.get("details_ref") else None),
    )


__all__ = [
    "GATE_OUTCOME_HOLD",
    "GATE_OUTCOME_PASS",
    "GATE_OUTCOME_REJECT",
    "GATE_OUTCOMES",
    "GateDecision",
    "OpsOverride",
    "OWNER_MODERATION",
    "OWNER_OPS",
    "OWNER_RECOMMENDATION_GATE",
    "OWNER_VERIFICATION",
    "Principal",
    "SUBJECT_PROFILE",
    "SUBJECT_RECOMMENDATION",
    "SUBJECT_SEARCH_CANDIDATE",
    "TrustSummary",
    "gate_decision_from_mapping",
    "principal_from_actor",
]
