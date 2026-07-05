"""Photo model versioning, rollout evaluation, and recompute helpers."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence

from .appearance_features import refresh_profile_photo_features

PHOTO_MODEL_KEYS = (
    "face_embedding_model",
    "style_model",
    "attribute_model",
    "summary_model",
)


def normalize_photo_model_versions(payload: Mapping[str, Any] | None) -> dict[str, str]:
    raw = dict(payload or {})
    normalized: dict[str, str] = {}
    for key in PHOTO_MODEL_KEYS:
        value = str(raw.get(key) or "").strip()
        normalized[key] = value or "deterministic_v1"
    return normalized


def evaluate_photo_model_candidate(
    *,
    baseline_metrics: Mapping[str, Any] | None,
    candidate_metrics: Mapping[str, Any] | None,
    min_success_rate_lift: float = 0.0,
    max_latency_regression_ms: float = 30.0,
    min_result_count_lift: float = -0.2,
) -> dict[str, Any]:
    baseline = dict(baseline_metrics or {})
    candidate = dict(candidate_metrics or {})
    baseline_success = float(baseline.get("success_rate") or 0.0)
    candidate_success = float(candidate.get("success_rate") or 0.0)
    baseline_latency = float(baseline.get("avg_latency_ms") or 0.0)
    candidate_latency = float(candidate.get("avg_latency_ms") or 0.0)
    baseline_results = float(baseline.get("avg_result_count") or 0.0)
    candidate_results = float(candidate.get("avg_result_count") or 0.0)

    success_lift = round(candidate_success - baseline_success, 4)
    latency_regression = round(candidate_latency - baseline_latency, 2)
    result_count_lift = round(candidate_results - baseline_results, 2)

    reasons: list[str] = []
    approved = True
    if success_lift < min_success_rate_lift:
        approved = False
        reasons.append("success_rate_not_improved_enough")
    if latency_regression > max_latency_regression_ms:
        approved = False
        reasons.append("latency_regression_too_high")
    if result_count_lift < min_result_count_lift:
        approved = False
        reasons.append("result_count_dropped_too_much")
    if approved:
        reasons.append("candidate_model_meets_guardrails")

    return {
        "approved": approved,
        "reasons": reasons,
        "deltas": {
            "success_rate_lift": success_lift,
            "latency_regression_ms": latency_regression,
            "avg_result_count_lift": result_count_lift,
        },
    }


def build_photo_model_rollout_plan(
    *,
    current_versions: Mapping[str, Any] | None,
    candidate_versions: Mapping[str, Any] | None,
    rollout_ratio: float = 0.1,
    experiment_bucket: str = "photo_model_candidate",
) -> dict[str, Any]:
    baseline = normalize_photo_model_versions(current_versions)
    candidate = normalize_photo_model_versions(candidate_versions)
    changed_keys = [
        key
        for key in PHOTO_MODEL_KEYS
        if baseline.get(key) != candidate.get(key)
    ]
    ratio = min(1.0, max(0.0, float(rollout_ratio or 0.0)))
    return {
        "baseline_versions": baseline,
        "candidate_versions": candidate,
        "changed_keys": changed_keys,
        "rollout_ratio": round(ratio, 4),
        "experiment_bucket": str(experiment_bucket or "photo_model_candidate").strip() or "photo_model_candidate",
        "requires_recompute": bool(changed_keys),
    }


def build_photo_feature_recompute_plan(
    *,
    profile_ids: Sequence[int] | Iterable[int],
    target_versions: Mapping[str, Any] | None,
    batch_size: int = 100,
) -> dict[str, Any]:
    normalized_ids = [int(profile_id) for profile_id in profile_ids if int(profile_id) > 0]
    chunk = max(1, int(batch_size or 100))
    batches = [
        normalized_ids[index:index + chunk]
        for index in range(0, len(normalized_ids), chunk)
    ]
    return {
        "target_versions": normalize_photo_model_versions(target_versions),
        "total_profiles": len(normalized_ids),
        "batch_size": chunk,
        "batches": batches,
    }


def trigger_photo_feature_recompute(
    *,
    source_dsn: str | None,
    profile_ids: Sequence[int] | Iterable[int],
    target_versions: Mapping[str, Any] | None,
    profile_source_dsn: str | None = None,
    source_table_name: str | None = None,
    batch_size: int = 100,
    refresh_fn: Callable[..., Mapping[str, Any]] = refresh_profile_photo_features,
) -> dict[str, Any]:
    plan = build_photo_feature_recompute_plan(
        profile_ids=profile_ids,
        target_versions=target_versions,
        batch_size=batch_size,
    )
    processed: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0
    for batch in plan["batches"]:
        for profile_id in batch:
            result = dict(
                refresh_fn(
                    source_dsn=source_dsn,
                    profile_id=int(profile_id),
                    profile_source_dsn=profile_source_dsn,
                    source_table_name=source_table_name,
                )
            )
            saved = bool(result.get("saved", True))
            if saved:
                succeeded += 1
            else:
                failed += 1
            processed.append(
                {
                    "profile_id": int(profile_id),
                    "saved": saved,
                    "target_versions": plan["target_versions"],
                    "result": result,
                }
            )
    return {
        **plan,
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
    }


__all__ = [
    "PHOTO_MODEL_KEYS",
    "build_photo_feature_recompute_plan",
    "build_photo_model_rollout_plan",
    "evaluate_photo_model_candidate",
    "normalize_photo_model_versions",
    "trigger_photo_feature_recompute",
]
