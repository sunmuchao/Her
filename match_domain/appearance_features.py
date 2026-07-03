"""Photo-derived matching features and user appearance preferences."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from profile_service import (
    list_profile_photo_features,
    load_user_appearance_preference,
    record_appearance_feedback_event,
    upsert_user_appearance_preference,
)


DEFAULT_PROFILE_PHOTO_FEATURES_TABLE = "profile_photo_features"
DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE = "user_appearance_preferences"
DEFAULT_APPEARANCE_FEEDBACK_EVENTS_TABLE = "appearance_feedback_events"


@dataclass(frozen=True)
class PhotoBonusBreakdown:
    quality_bonus: float
    global_bonus: float
    preference_bonus: float

    @property
    def total(self) -> float:
        return round(self.quality_bonus + self.global_bonus + self.preference_bonus, 2)


def _score_to_bonus(value: Any, *, max_bonus: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    numeric = max(0.0, min(100.0, numeric))
    return round((numeric / 100.0) * max_bonus, 2)


def compute_photo_bonus_breakdown(
    candidate_photo_features: dict[str, Any] | None,
    user_appearance_preference: dict[str, Any] | None = None,
) -> PhotoBonusBreakdown:
    feature_row = dict(candidate_photo_features or {})
    preference_row = dict(user_appearance_preference or {})

    quality_bonus = round(
        _score_to_bonus(feature_row.get("photo_quality_score"), max_bonus=3.0)
        + _score_to_bonus(feature_row.get("photo_authenticity_score"), max_bonus=3.0),
        2,
    )
    global_bonus = _score_to_bonus(feature_row.get("appearance_score_global"), max_bonus=15.0)

    preference_bonus = 0.0
    dimension_pairs = (
        ("mature_score", "preferred_mature_score"),
        ("clean_score", "preferred_clean_score"),
        ("gentle_score", "preferred_gentle_score"),
        ("sunny_score", "preferred_sunny_score"),
        ("stylish_score", "preferred_stylish_score"),
    )
    matched_dimensions = 0
    total_similarity = 0.0
    for candidate_key, user_key in dimension_pairs:
        try:
            candidate_value = float(feature_row.get(candidate_key))
            user_value = float(preference_row.get(user_key))
        except (TypeError, ValueError):
            continue
        candidate_value = max(0.0, min(100.0, candidate_value))
        user_value = max(0.0, min(100.0, user_value))
        similarity = max(0.0, 1.0 - abs(candidate_value - user_value) / 100.0)
        total_similarity += similarity
        matched_dimensions += 1

    if matched_dimensions > 0:
        average_similarity = total_similarity / matched_dimensions
        preference_bonus = round((average_similarity * 30.0) - 10.0, 2)

    return PhotoBonusBreakdown(
        quality_bonus=quality_bonus,
        global_bonus=global_bonus,
        preference_bonus=preference_bonus,
    )


def load_candidate_photo_features(
    *,
    source_dsn: str | None,
    profile_ids: Iterable[int],
    table_name: str = DEFAULT_PROFILE_PHOTO_FEATURES_TABLE,
) -> dict[int, dict[str, Any]]:
    normalized_ids = [int(profile_id) for profile_id in profile_ids if int(profile_id) > 0]
    if not source_dsn or not normalized_ids:
        return {}
    return list_profile_photo_features(
        source_dsn=source_dsn,
        profile_ids=normalized_ids,
        table_name=table_name,
    )


def load_requester_appearance_preference(
    *,
    source_dsn: str | None,
    user_key: str | None,
    table_name: str = DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE,
) -> dict[str, Any] | None:
    if not source_dsn or not str(user_key or "").strip():
        return None
    return load_user_appearance_preference(
        source_dsn=source_dsn,
        user_key=str(user_key),
        table_name=table_name,
    )


def record_feedback_event(
    *,
    source_dsn: str | None,
    user_key: str,
    profile_id: int,
    candidate_profile_id: int,
    event_type: str,
    event_weight: float,
    scene: str,
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    table_name: str = DEFAULT_APPEARANCE_FEEDBACK_EVENTS_TABLE,
) -> dict[str, Any]:
    if not source_dsn:
        return {"recorded": False, "error": "source_not_configured"}
    return record_appearance_feedback_event(
        source_dsn=source_dsn,
        table_name=table_name,
        user_key=user_key,
        profile_id=profile_id,
        candidate_profile_id=candidate_profile_id,
        event_type=event_type,
        event_weight=event_weight,
        scene=scene,
        session_id=session_id,
        metadata=metadata,
    )


def rebuild_user_preference_from_events(
    *,
    source_dsn: str | None,
    user_key: str,
    profile_id: int | None,
    candidate_feature_rows: list[dict[str, Any]],
    positive_sample_count: int,
    negative_sample_count: int,
    table_name: str = DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE,
) -> dict[str, Any]:
    if not source_dsn:
        return {"saved": False, "error": "source_not_configured"}
    weighted_dimensions = {
        "preferred_mature_score": [],
        "preferred_clean_score": [],
        "preferred_gentle_score": [],
        "preferred_sunny_score": [],
        "preferred_stylish_score": [],
    }
    summary_parts: list[str] = []
    for feature_row in candidate_feature_rows:
        if not isinstance(feature_row, dict):
            continue
        for feature_key, preference_key in (
            ("mature_score", "preferred_mature_score"),
            ("clean_score", "preferred_clean_score"),
            ("gentle_score", "preferred_gentle_score"),
            ("sunny_score", "preferred_sunny_score"),
            ("stylish_score", "preferred_stylish_score"),
        ):
            value = feature_row.get(feature_key)
            try:
                weighted_dimensions[preference_key].append(float(value))
            except (TypeError, ValueError):
                continue
        summary = str(feature_row.get("appearance_summary") or "").strip()
        if summary and summary not in summary_parts:
            summary_parts.append(summary)
    patch: dict[str, Any] = {
        "positive_sample_count": int(positive_sample_count),
        "negative_sample_count": int(negative_sample_count),
        "preference_status": "done",
        "embedding_status": "pending",
    }
    for preference_key, values in weighted_dimensions.items():
        if values:
            patch[preference_key] = round(sum(values) / len(values), 2)
    if summary_parts:
        patch["appearance_preference_summary"] = "；".join(summary_parts[:5])
    return upsert_user_appearance_preference(
        source_dsn=source_dsn,
        table_name=table_name,
        user_key=user_key,
        profile_id=profile_id,
        patch=patch,
    )


__all__ = [
    "DEFAULT_APPEARANCE_FEEDBACK_EVENTS_TABLE",
    "DEFAULT_PROFILE_PHOTO_FEATURES_TABLE",
    "DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE",
    "PhotoBonusBreakdown",
    "compute_photo_bonus_breakdown",
    "load_candidate_photo_features",
    "load_requester_appearance_preference",
    "record_feedback_event",
    "rebuild_user_preference_from_events",
]
