"""Result payload and ranking helpers for partner search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Sequence


@dataclass(frozen=True)
class SearchRankingRuntime:
    as_int: Callable[[Any], int | None]
    as_text: Callable[[Any], str]
    strip_internal_fields: Callable[[dict[str, Any]], dict[str, Any]]
    diversity_job_patterns: Sequence[tuple[Any, str]]
    result_sort_key: Callable[[dict[str, Any]], Any]
    diversity_penalty_tiers: Sequence[int] = (6, 4, 2)
    score_gap_severe_concession: int = 20
    score_gap_high_risk_tail: int = 25


def build_match_result(
    runtime: SearchRankingRuntime,
    *,
    record: dict[str, Any],
    score: int,
    fit_score: int,
    confidence_score: int,
    risk_score: int,
    matched_on: list[str],
    reciprocal_on: list[str],
    missing_fields: list[str],
    self_profile_gaps: list[str],
    risk_flags: list[str],
    match_evidence: list[str],
    follow_up_questions: list[str],
    verified_rank: int,
    activity_sort_ts: int,
    profile_status_rank: int,
    matched: bool = True,
    reject_reason: str | None = None,
) -> dict[str, Any]:
    profile = runtime.strip_internal_fields(record) if (diagnostics := (matched is False or reject_reason is not None)) else None
    result = {
        "matched": matched,
        "id": record.get("id"),
        "name": record.get("name") or "未命名",
        "score": score,
        "fit_score": fit_score,
        "confidence_score": confidence_score,
        "risk_score": risk_score,
        "matched_on": matched_on,
        "reciprocal_on": reciprocal_on,
        "missing_fields": missing_fields,
        "self_profile_gaps": self_profile_gaps,
        "risk_flags": risk_flags,
        "match_evidence": match_evidence,
        "follow_up_questions": follow_up_questions,
        "profile": profile,
        "source_file": record.get("source_file"),
        "verified_rank": verified_rank,
        "activity_sort_ts": activity_sort_ts,
        "profile_status_rank": profile_status_rank,
        "reject_reason": reject_reason,
    }
    if not diagnostics:
        result["_profile_record"] = record
    return result


def record_ref(runtime: SearchRankingRuntime, record: dict[str, Any] | None) -> tuple[int | None, str]:
    if record is None:
        return (None, "")
    return (runtime.as_int(record.get("id")), record.get("source_file") or "")


def result_sort_key(result: dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        result["score"],
        result["verified_rank"],
        result["activity_sort_ts"],
        result["profile_status_rank"],
    )


def diversity_job_cluster(runtime: SearchRankingRuntime, job: Any) -> str:
    text = runtime.as_text(job)
    if not text:
        return ""
    for pattern, label in runtime.diversity_job_patterns:
        if pattern.search(text):
            return label
    return text[:12]


def diversity_signature(runtime: SearchRankingRuntime, result: dict[str, Any]) -> tuple[str, str, str, str, str]:
    cached = result.get("_diversity_signature")
    if isinstance(cached, tuple) and len(cached) == 5:
        return cached
    profile = result.get("profile")
    if not isinstance(profile, dict):
        profile = result.get("_profile_record") or {}
    signature = (
        diversity_job_cluster(runtime, profile.get("job")),
        runtime.as_text(profile.get("career_intensity")),
        runtime.as_text(profile.get("communication_style")),
        runtime.as_text(profile.get("life_routine")),
        runtime.as_text(profile.get("commitment_clarity")),
    )
    result["_diversity_signature"] = signature
    return signature


def materialize_result_profile(runtime: SearchRankingRuntime, result: dict[str, Any]) -> dict[str, Any]:
    profile = result.get("profile")
    if isinstance(profile, dict):
        result.pop("_profile_record", None)
        result.pop("_diversity_signature", None)
        return result
    raw_record = result.pop("_profile_record", None)
    if isinstance(raw_record, dict):
        result["profile"] = runtime.strip_internal_fields(raw_record)
    else:
        result["profile"] = {}
    result.pop("_diversity_signature", None)
    return result


def diversity_penalty(
    runtime: SearchRankingRuntime,
    candidate: dict[str, Any],
    selected: list[dict[str, Any]],
) -> int:
    candidate_signature = diversity_signature(runtime, candidate)
    max_penalty = 0
    for existing in selected:
        overlap = sum(
            1
            for left, right in zip(candidate_signature, diversity_signature(runtime, existing))
            if left and right and left == right
        )
        tiers = list(runtime.diversity_penalty_tiers) or [6, 4, 2]
        if overlap >= 4:
            max_penalty = max(max_penalty, int(tiers[0]))
        elif overlap >= 3:
            max_penalty = max(max_penalty, int(tiers[1] if len(tiers) > 1 else tiers[0]))
        elif overlap >= 2:
            max_penalty = max(max_penalty, int(tiers[2] if len(tiers) > 2 else tiers[-1]))
    return max_penalty


def _diversity_penalty_from_overlap(runtime: SearchRankingRuntime, max_overlap: int) -> int:
    tiers = tuple(runtime.diversity_penalty_tiers) or (6, 4, 2)
    if max_overlap >= 4:
        return int(tiers[0])
    if max_overlap >= 3:
        return int(tiers[1] if len(tiers) > 1 else tiers[0])
    if max_overlap >= 2:
        return int(tiers[2] if len(tiers) > 2 else tiers[-1])
    return 0


def _signature_overlap(left: tuple[str, str, str, str, str], right: tuple[str, str, str, str, str]) -> int:
    return sum(1 for left_item, right_item in zip(left, right) if left_item and right_item and left_item == right_item)


def trim_low_quality_tail(
    runtime: SearchRankingRuntime,
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if len(results) <= 1:
        return results

    leader = results[0]
    trimmed = [leader]
    for item in results[1:]:
        score_gap = leader.get("score", 0) - item.get("score", 0)
        severe_concession = "多项条件需要放宽后才成立" in (item.get("risk_flags") or [])
        high_risk_tail = item.get("risk_score", 0) >= 35
        if severe_concession and score_gap >= runtime.score_gap_severe_concession:
            continue
        if high_risk_tail and score_gap >= runtime.score_gap_high_risk_tail:
            continue
        trimmed.append(item)
    return trimmed


def select_diverse_results(
    runtime: SearchRankingRuntime,
    results: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """选择推荐结果（删除多样性筛选，只保留质量保护）。

    改为直接按分数排序，取前limit个结果。
    """
    # 裁剪低质量尾部（质量保护）
    results = trim_low_quality_tail(runtime, results)
    # 直接按分数排序，取前limit个（删除多样性筛选）
    results.sort(key=result_sort_key, reverse=True)
    # Materialize profile 并返回
    return [materialize_result_profile(runtime, item) for item in results[:limit]]


__all__ = [
    "SearchRankingRuntime",
    "build_match_result",
    "diversity_job_cluster",
    "diversity_penalty",
    "diversity_signature",
    "record_ref",
    "result_sort_key",
    "select_diverse_results",
    "trim_low_quality_tail",
]
