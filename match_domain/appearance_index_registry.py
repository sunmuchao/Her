"""Appearance index versioning, rollout, rollback, and rebuild helpers."""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping, Sequence

from .appearance_search import AppearanceStyleIndexBuilder, FaceVectorIndexBuilder


APPEARANCE_INDEX_KEYS = (
    "face_embedding_index",
    "appearance_profile_index",
)


def normalize_appearance_index_versions(payload: Mapping[str, Any] | None) -> dict[str, str]:
    raw = dict(payload or {})
    normalized: dict[str, str] = {}
    for key in APPEARANCE_INDEX_KEYS:
        value = str(raw.get(key) or "").strip()
        normalized[key] = value or "milvus_lite_v1"
    return normalized


def build_appearance_index_rollout_plan(
    *,
    current_versions: Mapping[str, Any] | None,
    candidate_versions: Mapping[str, Any] | None,
    rollout_ratio: float = 0.1,
    canary_profile_ids: Sequence[int] | Iterable[int] | None = None,
) -> dict[str, Any]:
    baseline = normalize_appearance_index_versions(current_versions)
    candidate = normalize_appearance_index_versions(candidate_versions)
    changed_keys = [
        key
        for key in APPEARANCE_INDEX_KEYS
        if baseline.get(key) != candidate.get(key)
    ]
    return {
        "baseline_versions": baseline,
        "candidate_versions": candidate,
        "changed_keys": changed_keys,
        "rollout_ratio": round(min(1.0, max(0.0, float(rollout_ratio or 0.0))), 4),
        "canary_profile_ids": [int(item) for item in list(canary_profile_ids or []) if int(item) > 0],
        "requires_rebuild": bool(changed_keys),
    }


def build_appearance_index_rollback_plan(
    *,
    current_versions: Mapping[str, Any] | None,
    rollback_target_versions: Mapping[str, Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    current = normalize_appearance_index_versions(current_versions)
    target = normalize_appearance_index_versions(rollback_target_versions or current_versions)
    changed_keys = [
        key
        for key in APPEARANCE_INDEX_KEYS
        if current.get(key) != target.get(key)
    ]
    return {
        "current_versions": current,
        "rollback_target_versions": target,
        "changed_keys": changed_keys,
        "reason": str(reason or "manual_rollback").strip() or "manual_rollback",
        "requires_rebuild": bool(changed_keys),
    }


def trigger_appearance_index_rebuild(
    *,
    source_dsn: str | None,
    profile_ids: Sequence[int] | Iterable[int],
    target_versions: Mapping[str, Any] | None,
    batch_size: int = 100,
    rebuild_face_index_fn: Callable[..., Mapping[str, Any]] = FaceVectorIndexBuilder.build_profile_index,
    rebuild_style_index_fn: Callable[..., Mapping[str, Any]] = AppearanceStyleIndexBuilder.build_profile_index,
) -> dict[str, Any]:
    normalized_ids = [int(profile_id) for profile_id in profile_ids if int(profile_id) > 0]
    chunk = max(1, int(batch_size or 100))
    processed: list[dict[str, Any]] = []
    succeeded = 0
    failed = 0
    for index in range(0, len(normalized_ids), chunk):
        batch_ids = normalized_ids[index:index + chunk]
        for profile_id in batch_ids:
            face_result = dict(
                rebuild_face_index_fn(
                    source_dsn=source_dsn,
                    profile_id=profile_id,
                )
            )
            style_result = dict(
                rebuild_style_index_fn(
                    source_dsn=source_dsn,
                    profile_id=profile_id,
                )
            )
            item = {
                "profile_id": profile_id,
                "target_versions": normalize_appearance_index_versions(target_versions),
                "face_index": face_result,
                "appearance_index": style_result,
                "saved": bool(face_result.get("saved")) or bool(style_result.get("saved")),
            }
            if item["saved"]:
                succeeded += 1
            else:
                failed += 1
            processed.append(item)
    return {
        "target_versions": normalize_appearance_index_versions(target_versions),
        "total_profiles": len(normalized_ids),
        "batch_size": chunk,
        "processed": processed,
        "succeeded": succeeded,
        "failed": failed,
    }


__all__ = [
    "APPEARANCE_INDEX_KEYS",
    "build_appearance_index_rollback_plan",
    "build_appearance_index_rollout_plan",
    "normalize_appearance_index_versions",
    "trigger_appearance_index_rebuild",
]
