"""Build partner_search penalties from rule_config (§13.5)."""

from __future__ import annotations

from typing import Any, Mapping

from .rule_config import RuleResolutionContext, resolve_effective_rules
from .rule_config_schema import SLICE_PARTNER_SEARCH_RANKING, SLICE_PARTNER_SEARCH_SCORING
from .search_rule_context import get_search_rule_context

# Flags that use the negotiable tier when overridden (§13.5.4).
NEGOTIABLE_RISK_FLAGS = frozenset(
    {
        "对方年龄要求可能可放宽",
        "对方身高要求可能可放宽",
        "对方学历要求可能可放宽",
        "对方收入要求可能可放宽",
        "对方城市偏好未命中，异地仅可协商",
        "对方城市偏好未命中，异地接受度未知",
        "对方异地仅可协商",
        "对方异地接受度未知",
        "对方婚史接受度偏保守",
        "对方婚史接受需要先聊再判断",
        "对方对子女情况仅可协商",
        "对方对子女接受度偏保守",
        "对方对子女接受需要先接触再判断",
        "对方对抽烟仅可协商",
        "对方对喝酒仅可协商",
        "对方城市偏好未命中，但资料写了接受异地",
    }
)


def _tier_for_risk_flag(flag: str) -> str | None:
    if flag in NEGOTIABLE_RISK_FLAGS:
        return "negotiable"
    if "未知" in flag:
        return "unknown"
    if "偏保守" in flag or "需要先" in flag:
        return "conservative"
    return None


def build_effective_risk_flag_penalties(
    base_penalties: Mapping[str, int],
    *,
    conn=None,
    experiment_bucket: str | None = None,
    profile_id: int | None = None,
) -> dict[str, int]:
    ctx = get_search_rule_context()
    if ctx is not None:
        conn = conn or ctx.conn
        experiment_bucket = experiment_bucket or ctx.experiment_bucket
        profile_id = profile_id or ctx.profile_id

    bundle = resolve_effective_rules(
        SLICE_PARTNER_SEARCH_SCORING,
        RuleResolutionContext(experiment_bucket=experiment_bucket, profile_id=profile_id),
        conn=conn,
    )
    tier_values = {
        "negotiable": int(bundle.params.get("penalty_tier.negotiable", 7)),
        "unknown": int(bundle.params.get("penalty_tier.unknown", 10)),
        "conservative": int(bundle.params.get("penalty_tier.conservative", 9)),
    }
    critical = bundle.params.get("critical_missing_field_penalties")
    if not isinstance(critical, dict):
        critical = {}

    out = dict(base_penalties)
    for flag in base_penalties:
        tier = _tier_for_risk_flag(flag)
        if tier and tier in tier_values:
            out[flag] = tier_values[tier]
    return out


def build_ranking_rule_params(
    *,
    conn=None,
    experiment_bucket: str | None = None,
    profile_id: int | None = None,
) -> dict[str, Any]:
    ctx = get_search_rule_context()
    if ctx is not None:
        conn = conn or ctx.conn
        experiment_bucket = experiment_bucket or ctx.experiment_bucket
        profile_id = profile_id or ctx.profile_id

    bundle = resolve_effective_rules(
        SLICE_PARTNER_SEARCH_RANKING,
        RuleResolutionContext(experiment_bucket=experiment_bucket, profile_id=profile_id),
        conn=conn,
    )
    tiers = bundle.params.get("diversity_penalty_tiers")
    if not isinstance(tiers, list) or len(tiers) < 3:
        tiers = [6, 4, 2]
    return {
        "diversity_penalty_tiers": [int(tiers[0]), int(tiers[1]), int(tiers[2])],
        "score_gap_severe_concession": int(bundle.params.get("score_gap_severe_concession", 20)),
        "score_gap_high_risk_tail": int(bundle.params.get("score_gap_high_risk_tail", 25)),
    }


def build_matching_rule_params(
    *,
    conn=None,
    experiment_bucket: str | None = None,
    profile_id: int | None = None,
) -> dict[str, Any]:
    ctx = get_search_rule_context()
    if ctx is not None:
        conn = conn or ctx.conn
        experiment_bucket = experiment_bucket or ctx.experiment_bucket
        profile_id = profile_id or ctx.profile_id

    bundle = resolve_effective_rules(
        SLICE_PARTNER_SEARCH_SCORING,
        RuleResolutionContext(experiment_bucket=experiment_bucket, profile_id=profile_id),
        conn=conn,
    )
    params = bundle.params
    return {
        "income_curve": {
            "within_score": int(params.get("income_curve.within_score", 12)),
            "below_near_distance": int(params.get("income_curve.below_near_distance", 10)),
            "below_edge_distance": int(params.get("income_curve.below_edge_distance", 20)),
            "below_near_score": int(params.get("income_curve.below_near_score", 8)),
            "below_edge_score": int(params.get("income_curve.below_edge_score", 4)),
            "above_near_distance": int(params.get("income_curve.above_near_distance", 20)),
            "above_near_score": int(params.get("income_curve.above_near_score", 10)),
            "above_far_score": int(params.get("income_curve.above_far_score", 8)),
        },
        "city_curve": {
            "same_city_score": int(params.get("city_curve.same_city_score", 8)),
            "same_city_bonus_when_near_priority": int(
                params.get("city_curve.same_city_bonus_when_near_priority", 4)
            ),
            "settlement_same_city_score": int(params.get("city_curve.settlement_same_city_score", 5)),
            "criteria_settlement_hit_score": int(params.get("city_curve.criteria_settlement_hit_score", 8)),
        },
    }


__all__ = [
    "NEGOTIABLE_RISK_FLAGS",
    "build_effective_risk_flag_penalties",
    "build_matching_rule_params",
    "build_ranking_rule_params",
]
