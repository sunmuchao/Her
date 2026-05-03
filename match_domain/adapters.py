"""Adapters that map current system records onto canonical match-domain concepts."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Mapping

from .model import (
    CaseStatus,
    CaseType,
    MatchEvent,
    PairStatus,
    ProfileRef,
    RelationStatus,
    pair_key,
    relation_key,
)


def profile_ref_to_dict(profile_ref: ProfileRef) -> dict[str, Any]:
    return {
        "source": profile_ref.source,
        "profile_id": profile_ref.profile_id,
        "user_key": profile_ref.user_key,
        "stable_key": profile_ref.stable_key,
    }


def recommendation_owner_ref(subscription: Mapping[str, Any]) -> ProfileRef:
    source = str(subscription.get("source") or f"saved-search://{subscription['requester_id']}")
    self_id = subscription.get("self_id")
    requester_id = subscription.get("requester_id")
    return ProfileRef(
        source=source,
        profile_id=int(self_id) if self_id is not None else None,
        user_key=f"requester:{requester_id}",
    )


def recommendation_target_ref(subscription: Mapping[str, Any], candidate_id: int) -> ProfileRef:
    return ProfileRef(
        source=str(subscription["source"]),
        profile_id=int(candidate_id),
    )


def recommendation_relation_refs(
    subscription: Mapping[str, Any],
    candidate_id: int,
) -> tuple[ProfileRef, ProfileRef]:
    return (
        recommendation_owner_ref(subscription),
        recommendation_target_ref(subscription, candidate_id),
    )


def recommendation_relation_status(
    *,
    delivery_status: str | None,
    last_action_type: str | None = None,
    active_match_case_id: str | None = None,
) -> RelationStatus:
    if active_match_case_id:
        return RelationStatus.PROXY_INTRO_ACTIVE
    if delivery_status in {"proxy_intro_in_progress", "proxy_intro_accepted"}:
        return RelationStatus.PROXY_INTRO_ACTIVE
    if delivery_status == "proxy_intro_handed_off":
        return RelationStatus.CLOSED
    if delivery_status in {"cooled_down", "proxy_intro_declined", "proxy_intro_timed_out"}:
        return RelationStatus.COOLING
    if delivery_status in {"saved_by_user", "save_only"}:
        return RelationStatus.SAVED
    if delivery_status == "direct_greeted":
        return RelationStatus.DIRECT_GREETED
    if delivery_status == "review_skipped":
        return RelationStatus.SKIPPED
    if last_action_type == "skip":
        return RelationStatus.SKIPPED
    if delivery_status:
        return RelationStatus.RECOMMENDED
    return RelationStatus.NEW


def proxy_intro_case_status(case_status: str | None) -> CaseStatus:
    mapping = {
        "pending_outreach": CaseStatus.PENDING_CONTACT,
        "awaiting_reply": CaseStatus.AWAITING_REPLY,
        "accepted": CaseStatus.ACCEPTED,
        "declined": CaseStatus.DECLINED,
        "timed_out": CaseStatus.TIMED_OUT,
        "closed": CaseStatus.CLOSED,
    }
    return mapping.get(str(case_status), CaseStatus.CLOSED)


def matchmaking_case_status(case_status: str | None) -> CaseStatus:
    mapping = {
        "pending_first_contact": CaseStatus.PENDING_CONTACT,
        "pending_second_contact": CaseStatus.PENDING_CONTACT,
        "awaiting_first_reply": CaseStatus.AWAITING_REPLY,
        "awaiting_second_reply": CaseStatus.AWAITING_REPLY,
        "mutual_accept": CaseStatus.ACCEPTED,
        "declined": CaseStatus.DECLINED,
        "timed_out": CaseStatus.TIMED_OUT,
        "closed": CaseStatus.CLOSED,
    }
    return mapping.get(str(case_status), CaseStatus.CLOSED)


def canonical_pair_status(pair_status: str | None) -> PairStatus:
    mapping = {
        "eligible": PairStatus.ELIGIBLE,
        "below_threshold": PairStatus.BELOW_THRESHOLD,
        "blocked": PairStatus.BLOCKED,
        "cooling": PairStatus.COOLING,
        "case_opened": PairStatus.CASE_OPENED,
        "mutual_accept": PairStatus.MUTUAL_ACCEPT,
        "needs_revalidation": PairStatus.NEEDS_REVALIDATION,
        "stale": PairStatus.STALE,
    }
    return mapping.get(str(pair_status), PairStatus.STALE)


def pool_member_profile_ref(member: Mapping[str, Any]) -> ProfileRef:
    self_id = member.get("self_id")
    return ProfileRef(
        source=str(member["source"]),
        profile_id=int(self_id) if self_id is not None else None,
        user_key=str(member["user_key"]),
    )


def build_canonical_event(
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    actor_type: str,
    actor_id: str,
    source_service: str,
    correlation_id: str,
    occurred_at: datetime,
    payload: Mapping[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> MatchEvent:
    return MatchEvent(
        event_id=f"evt-{uuid.uuid4().hex[:16]}",
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_type=actor_type,
        actor_id=actor_id,
        source_service=source_service,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        occurred_at=occurred_at,
        payload=dict(payload or {}),
    )


def recommendation_relation_key(subscription: Mapping[str, Any], candidate_id: int) -> str:
    owner_ref, target_ref = recommendation_relation_refs(subscription, candidate_id)
    return relation_key(owner_ref, target_ref)


def canonical_pair_key_for_members(
    member_a: Mapping[str, Any],
    member_b: Mapping[str, Any],
) -> str:
    return pair_key(pool_member_profile_ref(member_a), pool_member_profile_ref(member_b))


def merge_payload_with_event(
    payload: Mapping[str, Any] | None,
    event: MatchEvent,
) -> dict[str, Any]:
    merged = dict(payload or {})
    merged["canonical_event"] = event.to_dict()
    return merged


__all__ = [
    "CaseStatus",
    "CaseType",
    "PairStatus",
    "RelationStatus",
    "build_canonical_event",
    "canonical_pair_key_for_members",
    "canonical_pair_status",
    "matchmaking_case_status",
    "merge_payload_with_event",
    "pool_member_profile_ref",
    "profile_ref_to_dict",
    "proxy_intro_case_status",
    "recommendation_owner_ref",
    "recommendation_relation_key",
    "recommendation_relation_refs",
    "recommendation_relation_status",
    "recommendation_target_ref",
]
