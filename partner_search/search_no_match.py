"""No-match diagnostics and fallback helpers for partner search."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class SearchNoMatchRuntime:
    field_display_name: Callable[[str], str]
    unique_ordered: Callable[[Any], list[Any]]
    evaluate_candidate: Callable[..., dict[str, Any] | None]
    result_sort_key: Callable[[dict[str, Any]], Any]
    select_diverse_results: Callable[[list[dict[str, Any]], int], list[dict[str, Any]]]
    format_text: Callable[[list[dict[str, Any]]], str]


def build_rejection_reason(code: Any, detail: Any = None) -> str:
    if detail is None or detail == "":
        return str(code)
    return f"{code}:{detail}"


def parse_rejection_reason(reason: Any) -> tuple[str, str]:
    code, _, detail = str(reason or "").partition(":")
    return code, detail


def format_rejection_reason(runtime: SearchNoMatchRuntime, reason: Any) -> str:
    code, detail = parse_rejection_reason(reason)
    labels = {
        "profile_status_mismatch": "资料状态不在要求范围",
        "active_time_missing": "缺少最近活跃时间",
        "active_too_old": "最近活跃时间太久",
        "verified_below_min": "认证等级低于最低要求",
        "verified_level_mismatch": "认证等级不在允许范围",
        "photo_verification_below_min": "照片核验等级低于最低要求",
        "photo_verification_level_mismatch": "照片核验等级不在允许范围",
        "age_below_min": "年龄低于下限",
        "age_above_max": "年龄高于上限",
        "height_below_min": "身高低于下限",
        "height_above_max": "身高高于上限",
        "gender_mismatch": "性别不匹配",
        "city_mismatch": "城市不在要求范围",
        "district_mismatch": "区域不在要求范围",
        "settlement_city_mismatch": "定居城市不在要求范围",
        "relationship_goal_mismatch": "关系目标不一致",
        "smoking_mismatch": "抽烟条件不匹配",
        "drinking_mismatch": "喝酒条件不匹配",
        "long_distance_mismatch": "异地态度不匹配",
        "housing_status_mismatch": "住房条件不匹配",
        "car_status_mismatch": "车辆条件不匹配",
        "marital_status_mismatch": "婚况不匹配",
        "has_children_mismatch": "子女情况不匹配",
        "want_children_mismatch": "生育计划不匹配",
        "accept_partner_children_mismatch": "对子女接受度不匹配",
        "accept_marital_status_strength_mismatch": "婚史接受真实度不匹配",
        "accept_partner_children_strength_mismatch": "对子女接受真实度不匹配",
        "marriage_timeline_mismatch": "结婚节奏不匹配",
        "photo_count_too_low": "照片数量低于要求",
        "education_below_self_preference": "低于你的学历底线",
        "reciprocal_age_preference": "不符合对方年龄偏好",
        "reciprocal_city_preference": "不符合对方城市偏好",
        "reciprocal_height_preference": "不符合对方身高偏好",
        "reciprocal_education_preference": "不符合对方学历偏好",
        "reciprocal_income_preference": "不符合对方收入偏好",
        "reciprocal_sexual_orientation": "不符合对方性取向偏好",  # ✅ 新增：性取向反向匹配
        "reciprocal_marital_status_preference": "不符合对方婚况接受范围",
        "reciprocal_children_acceptance": "对方不能接受你的子女情况",
        "reciprocal_marital_status_acceptance_not_strong": "对方对你的婚史不是明确接受",
        "reciprocal_children_acceptance_not_strong": "对方对你的孩子不是明确接受",
        "reciprocal_marital_status_acceptance_unknown": "对方没明确写是否真接受你的婚史",
        "reciprocal_children_acceptance_unknown": "对方没明确写是否真接受你的孩子",
        "reciprocal_smoking_acceptance": "对方不能接受你的抽烟情况",
        "reciprocal_drinking_acceptance": "对方不能接受你的喝酒情况",
        "reciprocal_long_distance_acceptance": "对方不能接受异地",
        "candidate_pool_empty_after_exclusions": "筛选后没有其他可用候选",
        "exclude_source_channel": "来自排除的来源渠道",
    }
    if code == "must_have_missing":
        return f"缺少必需关键词「{detail}」"
    if code == "must_not_have_hit":
        return f"命中排除关键词「{detail}」"
    if code == "required_known_missing":
        return f"资料里没明确写{runtime.field_display_name(detail)}"
    return labels.get(code, code or "未知淘汰原因")


def suggestion_for_rejection(runtime: SearchNoMatchRuntime, reason: Any) -> str | None:
    code, detail = parse_rejection_reason(reason)
    if code in {"city_mismatch", "district_mismatch", "settlement_city_mismatch"}:
        return "放宽地域条件，先别把同区/同定居地卡得太死。"
    if code == "must_have_missing":
        return f"把“{detail}”从硬条件改成加分项，先保留可聊对象。"
    if code == "must_not_have_hit":
        return f"确认“{detail}”是不是真硬雷点，不然先改成追问题。"
    if code in {"verified_below_min", "verified_level_mismatch"}:
        return "先放宽认证要求，再靠追问确认真实性。"
    if code == "photo_count_too_low":
        return "先放宽照片门槛，用资料内容和风险提示做二筛。"
    if code == "education_below_self_preference":
        return "先确认学历底线是不是硬条件，不然别把明显低于预期的人往前放。"
    if code in {"active_too_old", "active_time_missing"}:
        return "放宽活跃时间要求，先确认对方现在还找不找。"
    if code == "relationship_goal_mismatch":
        return "关系目标别卡太死，结婚导向和认真恋爱可以先一起放进池子。"
    if code in {"smoking_mismatch", "drinking_mismatch", "long_distance_mismatch"}:
        return "把生活习惯类条件分成硬雷点和可追问项，别一刀切。"
    if code in {
        "marital_status_mismatch",
        "accept_marital_status_strength_mismatch",
        "reciprocal_marital_status_preference",
        "reciprocal_marital_status_acceptance_not_strong",
        "reciprocal_marital_status_acceptance_unknown",
    }:
        return "婚况会明显压缩池子，先看对方是否明确接受再婚/复杂婚史。"
    if code in {
        "has_children_mismatch",
        "want_children_mismatch",
        "accept_partner_children_mismatch",
        "accept_partner_children_strength_mismatch",
        "reciprocal_children_acceptance",
        "reciprocal_children_acceptance_not_strong",
        "reciprocal_children_acceptance_unknown",
    }:
        return "孩子相关条件会明显压缩池子，先确认对方是明确接受、谨慎接受还是完全不接受。"
    if code == "candidate_pool_empty_after_exclusions":
        return "这轮不是排序问题，是当前城市/年龄段没有其他可用候选，先补数据池。"
    if code == "required_known_missing":
        return f"先别强制要求写明{runtime.field_display_name(detail)}，保留结果后再追问。"
    if code.startswith("reciprocal_"):
        return "这次是卡在对方反向要求上，优先检查城市、年龄、婚况、孩子、异地。"
    return None


def build_no_match_diagnostics_payload(
    scanned_count: int,
    passed_count: int,
    usable_count: int,
    top_reasons: list[dict[str, Any]],
    relax_suggestions: list[str],
) -> dict[str, Any]:
    return {
        "scanned_count": scanned_count,
        "passed_count": passed_count,
        "usable_count": usable_count,
        "top_reasons": top_reasons,
        "relax_suggestions": relax_suggestions,
    }


def _strict_diagnostic_cache(criteria: dict[str, Any]) -> dict[int, dict[str, Any] | None]:
    cache = criteria.get("__strict_diagnostic_cache")
    if isinstance(cache, dict):
        return cache
    created: dict[int, dict[str, Any] | None] = {}
    criteria["__strict_diagnostic_cache"] = created
    return created


def _evaluate_strict_candidate(
    runtime: SearchNoMatchRuntime,
    record: dict[str, Any],
    criteria: dict[str, Any],
) -> dict[str, Any] | None:
    cache = _strict_diagnostic_cache(criteria)
    record_key = id(record)
    if record_key in cache:
        return cache[record_key]
    diagnostic = runtime.evaluate_candidate(record, criteria, diagnostics=True)
    cache[record_key] = diagnostic
    return diagnostic


def build_no_match_diagnostics(
    runtime: SearchNoMatchRuntime,
    records: list[dict[str, Any]],
    criteria: dict[str, Any],
) -> dict[str, Any]:
    if not records:
        return {
            "scanned_count": 0,
            "passed_count": 0,
            "usable_count": 0,
            "top_reasons": [],
            "relax_suggestions": [
                "数据源预筛后已经没候选了，先检查城市、年龄、资料状态、最近活跃、认证等级这些硬条件。"
            ],
        }

    rejection_counts: Counter[str] = Counter()
    passed_count = 0
    excluded_count = 0
    for record in records:
        diagnostic = _evaluate_strict_candidate(runtime, record, criteria)
        if diagnostic and diagnostic.get("matched"):
            passed_count += 1
            continue
        reason = "unknown"
        if diagnostic:
            reason = diagnostic.get("reject_reason") or "unknown"
        if reason == "exclude_record_ref":
            excluded_count += 1
            continue
        rejection_counts[reason] += 1

    usable_count = max(len(records) - excluded_count, 0)

    if rejection_counts:
        top_reasons = [
            {
                "reason": reason,
                "label": format_rejection_reason(runtime, reason),
                "count": count,
            }
            for reason, count in rejection_counts.most_common(4)
        ]
    elif excluded_count:
        top_reasons = [
            {
                "reason": "candidate_pool_empty_after_exclusions",
                "label": "筛选后没有其他可用候选",
                "count": excluded_count,
            }
        ]
    else:
        top_reasons = []
    relax_suggestions = list(
        runtime.unique_ordered(
            suggestion_for_rejection(runtime, item["reason"]) for item in top_reasons
        )
    )

    return build_no_match_diagnostics_payload(
        scanned_count=len(records),
        passed_count=passed_count,
        usable_count=usable_count,
        top_reasons=top_reasons,
        relax_suggestions=relax_suggestions[:3],
    )


def build_fallback_candidates(
    runtime: SearchNoMatchRuntime,
    records: list[dict[str, Any]],
    criteria: dict[str, Any],
    limit: int = 3,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for record in records:
        strict_diagnostic = _evaluate_strict_candidate(runtime, record, criteria)
        if strict_diagnostic and strict_diagnostic.get("matched"):
            continue

        fallback_result = runtime.evaluate_candidate(
            record,
            criteria,
            reciprocal_mode="fallback",
        )
        if not fallback_result:
            continue

        if strict_diagnostic and strict_diagnostic.get("reject_reason"):
            fallback_result["fallback_reason"] = format_rejection_reason(
                runtime,
                strict_diagnostic["reject_reason"],
            )
        candidates.append(fallback_result)

    candidates.sort(key=runtime.result_sort_key, reverse=True)
    return runtime.select_diverse_results(candidates, limit)


def format_no_match_text(
    runtime: SearchNoMatchRuntime,
    diagnostics: dict[str, Any] | None,
    fallback_results: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        "No strict matches found."
        if fallback_results
        else "No matches found."
    ]
    if not diagnostics:
        return "\n".join(lines)

    pool_parts = [
        f"scanned={diagnostics.get('scanned_count', 0)}",
        f"passed={diagnostics.get('passed_count', 0)}",
    ]
    if diagnostics.get("usable_count") is not None and diagnostics.get("usable_count") != diagnostics.get("scanned_count"):
        pool_parts.append(f"usable_after_exclusions={diagnostics.get('usable_count', 0)}")
    lines.append("pool_summary: " + " | ".join(pool_parts))
    top_reasons = diagnostics.get("top_reasons") or []
    if top_reasons:
        lines.append(
            "why_no_match: "
            + " | ".join(f"{item['label']} x{item['count']}" for item in top_reasons)
        )
    suggestions = diagnostics.get("relax_suggestions") or []
    if suggestions:
        lines.append("relax_suggestions: " + " | ".join(suggestions))
    if fallback_results:
        lines.append("fallback_matches: 当前没有严格匹配，但下面这些属于有偏差、仍可聊的兼容对象。")
        lines.append(runtime.format_text(fallback_results))
    return "\n".join(lines)


__all__ = [
    "SearchNoMatchRuntime",
    "build_fallback_candidates",
    "build_no_match_diagnostics",
    "build_no_match_diagnostics_payload",
    "build_rejection_reason",
    "format_no_match_text",
    "format_rejection_reason",
    "parse_rejection_reason",
    "suggestion_for_rejection",
]
