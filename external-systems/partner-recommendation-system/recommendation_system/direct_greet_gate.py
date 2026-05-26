"""Rule-based proactive recommendation gate for direct-greet quality."""

from __future__ import annotations

import json
import os
from typing import Any, Mapping

from match_domain.experiment_bucket import (
    profile_id_from_subscription,
    resolve_experiment_bucket_for_subscription,
)
from match_domain.rule_config import RuleResolutionContext, resolve_effective_rules
from match_domain.rule_config_schema import (
    DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH,
    DEFAULT_MIN_DIRECT_GREET_SCORE,
    DEFAULT_RECOMMENDATION_MODE,
    SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
)

from .storage import json_loads


RECOMMENDATION_MODES = {"match_based", "direct_greet_only"}


def normalize_recommendation_mode(value: Any) -> str:
    if not value:
        return DEFAULT_RECOMMENDATION_MODE
    mode = str(value).strip().lower()
    if mode not in RECOMMENDATION_MODES:
        raise ValueError(f"Unsupported recommendation_mode: {value}")
    return mode


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


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _load_direct_greet_profile(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        return json.loads(raw)
    raise ValueError("direct_greet_profile_json must be a JSON object when present.")


def _load_review_policy_overrides(subscription: Mapping[str, Any]) -> dict[str, Any]:
    overrides = json_loads(subscription.get("subscription_overrides_json"), {})
    if not isinstance(overrides, Mapping):
        return {}
    review_policy = overrides.get("review_policy")
    if not isinstance(review_policy, Mapping):
        return {}
    return dict(review_policy)


def resolve_review_policy(subscription: Mapping[str, Any], *, conn=None) -> dict[str, Any]:
    experiment_bucket = resolve_experiment_bucket_for_subscription(subscription, conn=conn)
    bundle = resolve_effective_rules(
        SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
        RuleResolutionContext(
            subscription=subscription,
            subscription_id=str(subscription.get("subscription_id") or "") or None,
            profile_id=profile_id_from_subscription(subscription),
            experiment_bucket=experiment_bucket,
        ),
        conn=conn,
    )
    params = dict(bundle.params)
    policy_source = "code_defaults"
    if any(label.startswith("global:") for label in bundle.resolution_chain):
        policy_source = "global_rule_config"
    elif _load_review_policy_overrides(subscription):
        policy_source = "subscription_overrides.review_policy"
    elif any(label == "subscription_columns" for label in bundle.resolution_chain):
        policy_source = "subscription_columns"
    elif any(
        os.environ.get(key)
        for key in (
            "HER_RECOMMENDATION_MODE",
            "HER_RECOMMENDATION_MAX_REVIEW_CANDIDATES_PER_REFRESH",
            "HER_RECOMMENDATION_MIN_DIRECT_GREET_SCORE",
            "HER_RECOMMENDATION_AUTO_REJECT_ON_FOLLOW_UP_QUESTIONS",
            "HER_RECOMMENDATION_AUTO_REJECT_ON_RISK_FLAGS",
        )
    ):
        policy_source = "environment_defaults"
    direct_greet_profile = params.get("direct_greet_profile") or {}
    if isinstance(direct_greet_profile, str):
        direct_greet_profile = json.loads(direct_greet_profile) if direct_greet_profile.strip() else {}
    return {
        "recommendation_mode": normalize_recommendation_mode(params.get("recommendation_mode")),
        "max_review_candidates_per_refresh": int(params.get("max_review_candidates_per_refresh")),
        "min_direct_greet_score": int(params.get("min_direct_greet_score")),
        "auto_reject_on_follow_up_questions": bool(params.get("auto_reject_on_follow_up_questions")),
        "auto_reject_on_risk_flags": bool(params.get("auto_reject_on_risk_flags")),
        "direct_greet_profile": dict(direct_greet_profile),
        "policy_source": policy_source,
        "resolution_chain": list(bundle.resolution_chain),
        "version_id": bundle.version_id,
    }


def _value_matches_requirement(actual: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return actual in expected
    return actual == expected


def review_candidate_for_proactive_delivery(
    subscription: Mapping[str, Any],
    result: Mapping[str, Any],
    *,
    review_rank: int,
    conn=None,
) -> dict[str, Any]:
    review_policy = resolve_review_policy(subscription, conn=conn)
    mode = review_policy["recommendation_mode"]
    base_score = int(result.get("score") or 0)
    matched_on = [str(item) for item in _as_list(result.get("matched_on")) if item]
    reciprocal_on = [str(item) for item in _as_list(result.get("reciprocal_on")) if item]
    risk_flags = [str(item) for item in _as_list(result.get("risk_flags")) if item]
    follow_up_questions = [str(item) for item in _as_list(result.get("follow_up_questions")) if item]
    missing_fields = [str(item) for item in _as_list(result.get("missing_fields")) if item]
    self_profile_gaps = [str(item) for item in _as_list(result.get("self_profile_gaps")) if item]
    profile = dict(result.get("profile") or {})

    max_review_candidates = int(review_policy["max_review_candidates_per_refresh"])
    min_direct_greet_score = int(review_policy["min_direct_greet_score"])
    auto_reject_on_follow_up_questions = bool(review_policy["auto_reject_on_follow_up_questions"])
    auto_reject_on_risk_flags = bool(review_policy["auto_reject_on_risk_flags"])
    direct_greet_profile = dict(review_policy["direct_greet_profile"])

    review_score = base_score
    review_score += min(9, len(reciprocal_on) * 3)
    review_score -= len(risk_flags) * 6
    review_score -= len(follow_up_questions) * 4
    review_score -= len(missing_fields) * 4
    review_score -= len(self_profile_gaps) * 4
    review_score = max(review_score, 0)

    payload = {
        "mode": mode,
        "review_rank": review_rank,
        "max_review_candidates_per_refresh": max_review_candidates,
        "base_score": base_score,
        "review_score": review_score,
        "risk_flags_count": len(risk_flags),
        "follow_up_questions_count": len(follow_up_questions),
        "missing_fields_count": len(missing_fields),
        "self_profile_gaps_count": len(self_profile_gaps),
        "reciprocal_signal_count": len(reciprocal_on),
        "matched_on_count": len(matched_on),
        "review_policy": {
            "recommendation_mode": review_policy["recommendation_mode"],
            "max_review_candidates_per_refresh": max_review_candidates,
            "min_direct_greet_score": min_direct_greet_score,
            "auto_reject_on_follow_up_questions": auto_reject_on_follow_up_questions,
            "auto_reject_on_risk_flags": auto_reject_on_risk_flags,
            "direct_greet_profile": direct_greet_profile,
            "policy_source": review_policy["policy_source"],
        },
    }

    if mode == "match_based":
        return {
            "status": "match_ready",
            "reason": "match_based_mode",
            "score": review_score,
            "payload": payload,
        }

    if review_rank > max_review_candidates:
        payload["outside_review_pool"] = True
        return {
            "status": "review_deferred",
            "reason": "outside_review_pool",
            "score": review_score,
            "payload": payload,
        }

    requirement_failures: list[str] = []
    required_profile_fields = [
        str(field)
        for field in _as_list(direct_greet_profile.get("required_profile_fields"))
        if field
    ]
    for field in required_profile_fields:
        if profile.get(field) in {None, "", []}:
            requirement_failures.append(f"missing_profile_field:{field}")

    required_profile_values = direct_greet_profile.get("required_profile_values") or {}
    if not isinstance(required_profile_values, Mapping):
        raise ValueError("direct_greet_profile_json.required_profile_values must be an object.")
    for field, expected in required_profile_values.items():
        if not _value_matches_requirement(profile.get(field), expected):
            requirement_failures.append(f"unexpected_profile_value:{field}")

    required_signal_keywords = [
        str(keyword).strip()
        for keyword in _as_list(direct_greet_profile.get("required_signal_keywords"))
        if str(keyword).strip()
    ]
    all_signals = " ".join(matched_on + reciprocal_on).lower()
    for keyword in required_signal_keywords:
        if keyword.lower() not in all_signals:
            requirement_failures.append(f"missing_signal_keyword:{keyword}")

    min_reciprocal_signals = _normalize_int(direct_greet_profile.get("min_reciprocal_signals"), 0)
    if len(reciprocal_on) < min_reciprocal_signals:
        requirement_failures.append(f"reciprocal_signals_lt:{min_reciprocal_signals}")

    if requirement_failures:
        payload["requirement_failures"] = requirement_failures
        return {
            "status": "rejected",
            "reason": "direct_greet_preferences_not_met",
            "score": review_score,
            "payload": payload,
        }

    if auto_reject_on_risk_flags and risk_flags:
        payload["blocked_by"] = "risk_flags"
        return {
            "status": "save_only",
            "reason": "risk_flags_require_manual_review",
            "score": review_score,
            "payload": payload,
        }

    if auto_reject_on_follow_up_questions and follow_up_questions:
        payload["blocked_by"] = "follow_up_questions"
        return {
            "status": "save_only",
            "reason": "follow_up_questions_require_manual_review",
            "score": review_score,
            "payload": payload,
        }

    if missing_fields or self_profile_gaps:
        payload["blocked_by"] = "missing_information"
        return {
            "status": "save_only",
            "reason": "missing_information_requires_manual_review",
            "score": review_score,
            "payload": payload,
        }

    if review_score < min_direct_greet_score:
        payload["blocked_by"] = "score_threshold"
        payload["min_direct_greet_score"] = min_direct_greet_score
        return {
            "status": "save_only",
            "reason": "not_compelling_enough_for_direct_greet",
            "score": review_score,
            "payload": payload,
        }

    payload["min_direct_greet_score"] = min_direct_greet_score
    return {
        "status": "direct_greet_ready",
        "reason": "direct_greet_gate_passed",
        "score": review_score,
        "payload": payload,
    }


__all__ = [
    "DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH",
    "DEFAULT_MIN_DIRECT_GREET_SCORE",
    "DEFAULT_RECOMMENDATION_MODE",
    "RECOMMENDATION_MODES",
    "normalize_recommendation_mode",
    "resolve_review_policy",
    "review_candidate_for_proactive_delivery",
]
