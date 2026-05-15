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
    return {
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
        "profile": runtime.strip_internal_fields(record),
        "source_file": record.get("source_file"),
        "verified_rank": verified_rank,
        "activity_sort_ts": activity_sort_ts,
        "profile_status_rank": profile_status_rank,
        "reject_reason": reject_reason,
    }


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
    profile = result.get("profile") or {}
    return (
        diversity_job_cluster(runtime, profile.get("job")),
        runtime.as_text(profile.get("career_intensity")),
        runtime.as_text(profile.get("communication_style")),
        runtime.as_text(profile.get("life_routine")),
        runtime.as_text(profile.get("commitment_clarity")),
    )


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
        if overlap >= 4:
            max_penalty = max(max_penalty, 6)
        elif overlap >= 3:
            max_penalty = max(max_penalty, 4)
        elif overlap >= 2:
            max_penalty = max(max_penalty, 2)
    return max_penalty


def trim_low_quality_tail(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(results) <= 1:
        return results

    leader = results[0]
    trimmed = [leader]
    for item in results[1:]:
        score_gap = leader.get("score", 0) - item.get("score", 0)
        severe_concession = "多项条件需要放宽后才成立" in (item.get("risk_flags") or [])
        high_risk_tail = item.get("risk_score", 0) >= 35
        if severe_concession and score_gap >= 20:
            continue
        if high_risk_tail and score_gap >= 25:
            continue
        trimmed.append(item)
    return trimmed


def select_diverse_results(
    runtime: SearchRankingRuntime,
    results: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    results = trim_low_quality_tail(results)
    if len(results) <= limit:
        return results[:limit]

    remaining = list(results)
    selected: list[dict[str, Any]] = []
    while remaining and len(selected) < limit:
        best = None
        best_key = None
        for item in remaining:
            penalty = diversity_penalty(runtime, item, selected)
            key = (
                item["score"] - penalty,
                item["score"],
                item["verified_rank"],
                item["activity_sort_ts"],
                item["profile_status_rank"],
            )
            if best is None or key > best_key:
                best = item
                best_key = key
        selected.append(best)
        remaining.remove(best)
    return selected


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
