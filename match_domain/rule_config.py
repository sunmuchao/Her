"""Resolve effective rule parameters with auditable resolution chains (§13.5)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from her_time_utils import current_time

from .review_config import review_policy_from_env
from .experiment_bucket import resolve_experiment_bucket_for_subscription
from .rule_config_schema import (
    DEFAULT_RECOMMENDATION_MODE,
    SLICE_CHAT_ASSISTANT_COOLDOWN,
    SLICE_PARTNER_SEARCH_RANKING,
    SLICE_PARTNER_SEARCH_SCORING,
    SLICE_RECOMMENDATION_DELIVERY,
    SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
    SLICE_RECOMMENDATION_REVIEW_POLICY,
    SLICE_VERIFICATION_AUTO_TRIAGE,
    code_defaults_for_slice,
)
from .rule_config_store import (
    SCOPE_EXPERIMENT_BUCKET,
    SCOPE_GLOBAL,
    SCOPE_PROFILE,
    SCOPE_SUBSCRIPTION,
    get_active_assignment,
)


@dataclass
class RuleResolutionContext:
    subscription: Mapping[str, Any] | None = None
    subscription_id: str | None = None
    profile_id: int | None = None
    experiment_bucket: str | None = None


@dataclass
class EffectiveRuleBundle:
    slice_id: str
    version_id: str
    params: dict[str, Any]
    resolution_chain: list[str] = field(default_factory=list)
    resolved_at: datetime = field(default_factory=current_time)

    def to_provenance_entry(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "resolution_chain": list(self.resolution_chain),
            **self.params,
        }


def _normalize_int(value: Any, default: int) -> int:
    if value in {None, ""}:
        return default
    return int(value)


def _normalize_bool(value: Any, default: bool) -> bool:
    if value in {None, ""}:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _json_loads(raw: Any, default: Any) -> Any:
    if raw in {None, ""}:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    if isinstance(raw, str):
        return json.loads(raw)
    return default


def _load_review_policy_overrides(subscription: Mapping[str, Any]) -> dict[str, Any]:
    overrides = _json_loads(subscription.get("subscription_overrides_json"), {})
    if not isinstance(overrides, Mapping):
        return {}
    review_policy = overrides.get("review_policy")
    if not isinstance(review_policy, Mapping):
        return {}
    return dict(review_policy)


def _load_delivery_overrides(subscription: Mapping[str, Any]) -> dict[str, Any]:
    overrides = _json_loads(subscription.get("subscription_overrides_json"), {})
    if not isinstance(overrides, Mapping):
        return {}
    delivery = overrides.get("delivery")
    if not isinstance(delivery, Mapping):
        return {}
    return dict(delivery)


def _merge_params(
    base: dict[str, Any],
    overlay: Mapping[str, Any],
    chain_label: str,
    chain: list[str],
) -> dict[str, Any]:
    if not overlay:
        return base
    merged = dict(base)
    merged.update({k: v for k, v in overlay.items() if v is not None})
    chain.append(chain_label)
    return merged


def _resolve_from_db(conn, slice_id: str, context: RuleResolutionContext, chain: list[str]) -> dict[str, Any] | None:
    if conn is None:
        return None
    scopes: list[tuple[str, str, str]] = []
    if context.experiment_bucket:
        scopes.append((SCOPE_EXPERIMENT_BUCKET, context.experiment_bucket, f"experiment:{context.experiment_bucket}"))
    subscription_id = context.subscription_id
    if subscription_id is None and context.subscription is not None:
        subscription_id = str(context.subscription.get("subscription_id") or "") or None
    if subscription_id:
        scopes.append((SCOPE_SUBSCRIPTION, subscription_id, f"subscription:{subscription_id}"))
    if context.profile_id is not None:
        scopes.append((SCOPE_PROFILE, str(context.profile_id), f"profile:{context.profile_id}"))
    scopes.append((SCOPE_GLOBAL, "*", "global"))

    for scope_type, scope_key, label in scopes:
        assignment = get_active_assignment(conn, slice_id=slice_id, scope_type=scope_type, scope_key=scope_key)
        if assignment is None:
            continue
        params = dict(assignment.get("params") or {})
        chain.append(f"{label}:{assignment.get('version_id')}")
        return params
    return None


def resolve_effective_rules(
    slice_id: str,
    context: RuleResolutionContext | None = None,
    *,
    conn=None,
) -> EffectiveRuleBundle:
    context = context or RuleResolutionContext()
    chain: list[str] = []
    params = dict(code_defaults_for_slice(slice_id))
    chain.append("code_defaults")

    db_params = _resolve_from_db(conn, slice_id, context, chain)
    if db_params is not None:
        params.update(db_params)

    subscription = context.subscription
    if subscription is not None:
        if slice_id == SLICE_RECOMMENDATION_DIRECT_GREET_GATE:
            review_overrides = _load_review_policy_overrides(subscription)
            column_overlay = {
                "recommendation_mode": subscription.get("recommendation_mode"),
                "max_review_candidates_per_refresh": subscription.get("max_review_candidates_per_refresh"),
                "min_direct_greet_score": subscription.get("min_direct_greet_score"),
                "auto_reject_on_follow_up_questions": subscription.get("auto_reject_on_follow_up_questions"),
                "auto_reject_on_risk_flags": subscription.get("auto_reject_on_risk_flags"),
            }
            params = _merge_params(
                params,
                {k: v for k, v in column_overlay.items() if v not in {None, ""}},
                "subscription_columns",
                chain,
            )
            params = _merge_params(params, review_overrides, "subscription_overrides.review_policy", chain)
            if review_overrides:
                params["direct_greet_profile"] = review_overrides.get(
                    "direct_greet_profile",
                    subscription.get("direct_greet_profile_json"),
                )
            else:
                params["direct_greet_profile"] = subscription.get("direct_greet_profile_json")
        elif slice_id == SLICE_RECOMMENDATION_DELIVERY:
            delivery_overrides = _load_delivery_overrides(subscription)
            params = _merge_params(params, delivery_overrides, "subscription_overrides.delivery", chain)
            column_overlay = {
                "min_notify_score": subscription.get("min_notify_score"),
                "daily_notification_cap": subscription.get("daily_notification_cap"),
                "quiet_hours_start": subscription.get("quiet_hours_start"),
                "quiet_hours_end": subscription.get("quiet_hours_end"),
                "skip_cooldown_days": subscription.get("skip_cooldown_days"),
            }
            params = _merge_params(
                params,
                {k: v for k, v in column_overlay.items() if v not in {None, ""}},
                "subscription_columns",
                chain,
            )
        elif slice_id == SLICE_RECOMMENDATION_REVIEW_POLICY:
            params.update(review_policy_from_env())
            chain.append("environment_review_policy")

    if slice_id == SLICE_RECOMMENDATION_DIRECT_GREET_GATE:
        defaults = code_defaults_for_slice(slice_id)
        params["recommendation_mode"] = str(params.get("recommendation_mode") or DEFAULT_RECOMMENDATION_MODE)
        params["max_review_candidates_per_refresh"] = _normalize_int(
            params.get("max_review_candidates_per_refresh"),
            int(defaults["max_review_candidates_per_refresh"]),
        )
        params["min_direct_greet_score"] = _normalize_int(
            params.get("min_direct_greet_score"),
            int(defaults["min_direct_greet_score"]),
        )
        params["auto_reject_on_follow_up_questions"] = _normalize_bool(
            params.get("auto_reject_on_follow_up_questions"),
            bool(defaults["auto_reject_on_follow_up_questions"]),
        )
        params["auto_reject_on_risk_flags"] = _normalize_bool(
            params.get("auto_reject_on_risk_flags"),
            bool(defaults["auto_reject_on_risk_flags"]),
        )
        raw_profile = params.get("direct_greet_profile")
        if isinstance(raw_profile, str) and raw_profile.strip():
            params["direct_greet_profile"] = _json_loads(raw_profile, {})
        elif not isinstance(raw_profile, Mapping):
            params["direct_greet_profile"] = {}

    version_id = "code_default"
    for item in reversed(chain):
        if ":" in item and item.split(":", 1)[0] in {
            "global",
            "subscription",
            "experiment",
            "profile",
        }:
            version_id = item.split(":", 1)[1]
            break

    return EffectiveRuleBundle(
        slice_id=slice_id,
        version_id=version_id,
        params=params,
        resolution_chain=chain,
        resolved_at=current_time(),
    )


def resolve_subscription_rule_bundles(
    subscription: Mapping[str, Any],
    *,
    conn=None,
    experiment_bucket: str | None = None,
) -> dict[str, EffectiveRuleBundle]:
    if experiment_bucket is None and subscription is not None:
        experiment_bucket = resolve_experiment_bucket_for_subscription(subscription, conn=conn)
    from .experiment_bucket import profile_id_from_subscription

    profile_id = profile_id_from_subscription(subscription) if subscription is not None else None
    context = RuleResolutionContext(
        subscription=subscription,
        subscription_id=str(subscription.get("subscription_id") or "") or None,
        profile_id=profile_id if profile_id and profile_id > 0 else None,
        experiment_bucket=experiment_bucket,
    )
    slices = (
        SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
        SLICE_RECOMMENDATION_DELIVERY,
        SLICE_RECOMMENDATION_REVIEW_POLICY,
        SLICE_PARTNER_SEARCH_SCORING,
        SLICE_PARTNER_SEARCH_RANKING,
        SLICE_CHAT_ASSISTANT_COOLDOWN,
        SLICE_VERIFICATION_AUTO_TRIAGE,
    )
    return {slice_id: resolve_effective_rules(slice_id, context, conn=conn) for slice_id in slices}


def bundles_to_effective_params(bundles: Mapping[str, EffectiveRuleBundle]) -> dict[str, Any]:
    return {slice_id: bundle.to_provenance_entry() for slice_id, bundle in bundles.items()}


__all__ = [
    "EffectiveRuleBundle",
    "RuleResolutionContext",
    "bundles_to_effective_params",
    "resolve_effective_rules",
    "resolve_subscription_rule_bundles",
]
