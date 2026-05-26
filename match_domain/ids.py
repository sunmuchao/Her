"""Canonical entity identifiers and trace/correlation helpers for match-domain events.

All cross-service object references use the ``her:<kind>:<body>`` namespace so logs,
payloads, and correlation strings stay unambiguous (profile vs persona vs recommendation
vs pair vs case).
"""

from __future__ import annotations

from typing import Any, Mapping

from .adapters import recommendation_owner_ref, recommendation_target_ref
from .model import ProfileRef
from her_runtime_context import (
    TRACE_ID_HEX_LEN,
    get_trace_id,
    new_trace_id,
    reset_trace_id,
    set_trace_id,
)

HER_NS = "her"


def entity_id_profile(ref: ProfileRef) -> str:
    return f"{HER_NS}:prf:{ref.stable_key}"


def entity_id_persona(
    *,
    source: str,
    requester_id: str,
    self_id: int | None = None,
) -> str:
    """Subscription-side identity (searcher / saved-search owner), distinct from candidate profile rows."""

    if self_id is not None:
        return f"{HER_NS}:per:{source}#profile:{int(self_id)}"
    return f"{HER_NS}:per:{source}#req:{requester_id}"


def entity_id_recommendation(recommendation_id: int) -> str:
    return f"{HER_NS}:rec:{int(recommendation_id)}"


def entity_id_relation(relation_key: str) -> str:
    return f"{HER_NS}:rel:{relation_key}"


def entity_id_pair(pair_key_str: str) -> str:
    return f"{HER_NS}:pair:{pair_key_str}"


def entity_id_case(case_id: str) -> str:
    return f"{HER_NS}:case:{case_id}"


def entity_id_pool_member(member_id: str) -> str:
    return f"{HER_NS}:mmb:{member_id}"


def entity_id_feedback(feedback_id: str) -> str:
    return f"{HER_NS}:fdb:{feedback_id}"


def format_correlation_id(*segments: str | None) -> str:
    """Stable, pipe-separated correlation string; omit empty segments."""

    return "|".join(str(s) for s in segments if s is not None and str(s) != "")


def correlation_relation_action(
    recommendation_id: int,
    action_type: str,
    *,
    trace_id: str | None = None,
) -> str:
    tid = trace_id if trace_id is not None else get_trace_id()
    return format_correlation_id(tid, entity_id_recommendation(recommendation_id), action_type)


def correlation_case_event(
    case_id: str,
    subsystem: str,
    event_type: str,
    *,
    trace_id: str | None = None,
) -> str:
    """``subsystem`` is the case stream tag, aligned with :class:`~match_domain.model.CaseType` values."""

    tid = trace_id if trace_id is not None else get_trace_id()
    return format_correlation_id(tid, entity_id_case(case_id), subsystem, event_type)


def correlation_member_feedback(
    feedback_id: str,
    *,
    trace_id: str | None = None,
) -> str:
    tid = trace_id if trace_id is not None else get_trace_id()
    return format_correlation_id(tid, entity_id_feedback(feedback_id), "feedback")


def idempotency_relation_action(recommendation_id: int, action_type: str, time_bucket: str) -> str:
    return f"{HER_NS}:idem:{entity_id_recommendation(recommendation_id)}:{action_type}:{time_bucket}"


def idempotency_client_relation_action(recommendation_id: int, client_key: str) -> str:
    """Stable idempotency key when the client supplies ``Idempotency-Key`` / ``idempotency_key``."""

    safe = str(client_key).strip()
    if not safe:
        raise ValueError("client idempotency key must be non-empty")
    return f"{HER_NS}:idem:client:{entity_id_recommendation(recommendation_id)}:{safe}"


def idempotency_case_event(case_id: str, subsystem: str, event_type: str, time_bucket: str) -> str:
    return f"{HER_NS}:idem:{entity_id_case(case_id)}:{subsystem}:{event_type}:{time_bucket}"


def idempotency_feedback(feedback_id: str) -> str:
    return f"{HER_NS}:idem:{entity_id_feedback(feedback_id)}"


def bundle_recommendation_action_entities(
    *,
    subscription: Mapping[str, Any],
    relation_key: str,
    recommendation_id: int,
    candidate_id: int,
) -> dict[str, str]:
    owner = recommendation_owner_ref(subscription)
    target = recommendation_target_ref(subscription, int(candidate_id))
    sub_source = str(subscription.get("source") or f"saved-search://{subscription['requester_id']}")
    return {
        "persona": entity_id_persona(
            source=sub_source,
            requester_id=str(subscription["requester_id"]),
            self_id=int(subscription["self_id"]) if subscription.get("self_id") is not None else None,
        ),
        "profile_owner": entity_id_profile(owner),
        "profile_candidate": entity_id_profile(target),
        "relation": entity_id_relation(relation_key),
        "recommendation": entity_id_recommendation(int(recommendation_id)),
    }


def bundle_proxy_intro_case_entities(case: Mapping[str, Any], *, pair_key: str | None = None) -> dict[str, str]:
    out = {
        "case": entity_id_case(str(case["case_id"])),
        "recommendation": entity_id_recommendation(int(case["recommendation_id"])),
    }
    sub = case.get("subscription_id")
    if sub is not None:
        out["subscription"] = f"{HER_NS}:sub:{sub}"
    cid = case.get("candidate_id")
    rid = case.get("requester_id")
    src = case.get("source")
    if cid is not None and src is not None:
        out["profile_candidate"] = entity_id_profile(ProfileRef(source=str(src), profile_id=int(cid)))
    if rid is not None and src is not None:
        out["persona"] = entity_id_persona(
            source=str(src),
            requester_id=str(rid),
            self_id=int(case["self_id"]) if case.get("self_id") is not None else None,
        )
    if pair_key:
        out["pair"] = entity_id_pair(str(pair_key))
    return out


def bundle_matchmaking_case_entities(
    *,
    case_id: str,
    pair_key: str,
    first_contact_member_id: str | None = None,
    second_contact_member_id: str | None = None,
) -> dict[str, str]:
    out: dict[str, str] = {
        "case": entity_id_case(case_id),
        "pair": entity_id_pair(pair_key),
    }
    if first_contact_member_id:
        out["member_first_contact"] = entity_id_pool_member(str(first_contact_member_id))
    if second_contact_member_id:
        out["member_second_contact"] = entity_id_pool_member(str(second_contact_member_id))
    return out


__all__ = [
    "HER_NS",
    "TRACE_ID_HEX_LEN",
    "bundle_matchmaking_case_entities",
    "bundle_proxy_intro_case_entities",
    "bundle_recommendation_action_entities",
    "correlation_case_event",
    "correlation_member_feedback",
    "correlation_relation_action",
    "entity_id_case",
    "entity_id_feedback",
    "entity_id_pair",
    "entity_id_persona",
    "entity_id_pool_member",
    "entity_id_profile",
    "entity_id_recommendation",
    "entity_id_relation",
    "format_correlation_id",
    "get_trace_id",
    "idempotency_case_event",
    "idempotency_client_relation_action",
    "idempotency_feedback",
    "idempotency_relation_action",
    "new_trace_id",
    "reset_trace_id",
    "set_trace_id",
]
