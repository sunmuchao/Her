"""Photo-derived matching features and user appearance preferences."""

from __future__ import annotations

import asyncio
import hashlib
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from profile_service import (
    get_face_consistency_score,
    get_profile,
    insert_reference_face_search_job,
    insert_profile_photo_feature_version,
    iter_profile_batches,
    list_appearance_feedback_events,
    list_profile_face_attributes,
    list_profile_face_embeddings,
    list_profile_photo_feature_rows,
    list_profile_photo_feature_versions,
    list_profile_photos,
    list_profile_photo_features,
    list_verified_face_anchors,
    load_user_appearance_preference,
    record_appearance_feedback_event,
    resolve_profile_source,
    upsert_face_consistency_score,
    upsert_profile_face_attributes,
    upsert_profile_face_embedding,
    upsert_profile_photo_features,
    upsert_verified_face_anchor,
    upsert_user_appearance_preference,
)


DEFAULT_PROFILE_PHOTO_FEATURES_TABLE = "profile_photo_features"
DEFAULT_PROFILE_PHOTO_FEATURE_VERSIONS_TABLE = "profile_photo_feature_versions"
DEFAULT_PROFILE_FACE_ATTRIBUTES_TABLE = "profile_face_attributes"
DEFAULT_PROFILE_FACE_EMBEDDINGS_TABLE = "profile_face_embeddings"
DEFAULT_VERIFIED_FACE_ANCHORS_TABLE = "verified_face_anchors"
DEFAULT_FACE_CONSISTENCY_SCORES_TABLE = "face_consistency_scores"
DEFAULT_REFERENCE_FACE_SEARCH_JOBS_TABLE = "reference_face_search_jobs"
DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE = "user_appearance_preferences"
DEFAULT_APPEARANCE_FEEDBACK_EVENTS_TABLE = "appearance_feedback_events"
APPEARANCE_PROFILE_VECTOR_TYPE = "appearance_profile"
APPEARANCE_PREFERENCE_VECTOR_TYPE = "appearance_preference"

_PREFERENCE_DIMENSIONS = (
    ("mature_score", "preferred_mature_score"),
    ("clean_score", "preferred_clean_score"),
    ("gentle_score", "preferred_gentle_score"),
    ("sunny_score", "preferred_sunny_score"),
    ("stylish_score", "preferred_stylish_score"),
)
_POSITIVE_EVENT_TYPES = {
    "express_interest",
    "save",
    "review_save",
    "direct_greet",
    "review_direct_greet",
    "chat_started",
    "chat_replied",
    "chat_continued",
    "detail_view",
}
_NEGATIVE_EVENT_TYPES = {
    "skip",
    "review_skip",
    "quick_pass",
    "explicit_dislike",
}
_DEFAULT_EVENT_WEIGHTS = {
    "express_interest": 3.0,
    "save": 2.5,
    "review_save": 2.5,
    "direct_greet": 4.0,
    "review_direct_greet": 4.0,
    "chat_started": 4.5,
    "chat_replied": 5.0,
    "chat_continued": 5.5,
    "detail_view": 1.2,
    "skip": -2.0,
    "review_skip": -2.5,
    "quick_pass": -3.0,
    "explicit_dislike": -4.0,
}
_PREFERENCE_EVENT_HALF_LIFE_DAYS = 45.0
EXPLANATION_TEMPLATE_LIBRARY = {
    "base_only": "{base_summary}",
    "appearance_only": "{appearance_summary}",
    "base_plus_appearance": "{base_summary}，再加上{appearance_summary}",
    "base_plus_trust": "{base_summary}，而且{trust_summary}",
}


@dataclass(frozen=True)
class PhotoBonusBreakdown:
    quality_bonus: float
    global_bonus: float
    preference_bonus: float

    @property
    def total(self) -> float:
        return round(self.quality_bonus + self.global_bonus + self.preference_bonus, 2)


@dataclass(frozen=True)
class TrustBonusBreakdown:
    verified_bonus: float
    photo_verification_bonus: float
    authenticity_bonus: float
    quality_bonus: float

    @property
    def total(self) -> float:
        return round(
            self.verified_bonus
            + self.photo_verification_bonus
            + self.authenticity_bonus
            + self.quality_bonus,
            2,
        )


@dataclass(frozen=True)
class RiskPenaltyBreakdown:
    authenticity_penalty: float
    quality_penalty: float
    explicit_flag_penalty: float
    style_mismatch_penalty: float
    reasons: list[str]

    @property
    def total(self) -> float:
        return round(
            self.authenticity_penalty
            + self.quality_penalty
            + self.explicit_flag_penalty
            + self.style_mismatch_penalty,
            2,
        )


@dataclass(frozen=True)
class AppearanceWeightStrategy:
    scene: str
    base_weight: float
    preference_weight: float
    trust_weight: float
    risk_weight: float
    user_stage: str


@dataclass(frozen=True)
class ProfilePhotoTrustScore:
    score: float
    confidence_weight: float
    risk_level: str
    badges: list[str]


@dataclass(frozen=True)
class VerifiedPhotoQualityScore:
    score: float
    confidence: float
    blur_penalty: float
    lighting_penalty: float
    occlusion_penalty: float
    reasons: list[str]


@dataclass(frozen=True)
class EnvironmentGapAssessment:
    gap_score: float
    compensation_factor: float
    notes: list[str]


@dataclass(frozen=True)
class FaceConsistencyResult:
    score: float
    threshold: float
    confidence_weight: float
    environment_gap_score: float
    risk_level: str
    risk_flags: list[str]
    matched: bool


class PhotoAnalysisStateMachine:
    _ALLOWED_TRANSITIONS = {
        "pending": {"processing", "failed"},
        "processing": {"done", "failed", "retrying"},
        "retrying": {"processing", "failed"},
        "failed": {"retrying", "processing"},
        "done": {"processing"},
    }

    @classmethod
    def can_transition(cls, current_status: str | None, next_status: str) -> bool:
        current = str(current_status or "pending").strip().lower() or "pending"
        target = str(next_status or "").strip().lower()
        if not target:
            return False
        if current == target:
            return True
        return target in cls._ALLOWED_TRANSITIONS.get(current, set())

    @classmethod
    def build_transition_patch(
        cls,
        existing_row: dict[str, Any] | None,
        *,
        next_status: str,
        error_message: str | None = None,
        retry_count: int | None = None,
        embedding_status: str | None = None,
    ) -> dict[str, Any]:
        current_status = str((existing_row or {}).get("analysis_status") or "pending").strip().lower()
        target_status = str(next_status or "").strip().lower() or current_status or "pending"
        if not cls.can_transition(current_status, target_status):
            raise ValueError(f"invalid_photo_analysis_transition:{current_status}->{target_status}")
        patch: dict[str, Any] = {
            "analysis_status": target_status,
            "last_transition_at": datetime.now(),
        }
        if embedding_status is not None:
            patch["embedding_status"] = embedding_status
        if retry_count is not None:
            patch["retry_count"] = max(0, int(retry_count))
        if target_status in {"processing", "done"}:
            patch["last_error"] = None
        elif error_message:
            patch["last_error"] = str(error_message)[:255]
        return patch


class PhotoAnalysisRetryQueue:
    @staticmethod
    def current_retry_count(feature_row: dict[str, Any] | None) -> int:
        return max(0, int(_safe_float((feature_row or {}).get("retry_count"), default=0.0)))

    @classmethod
    def should_retry(cls, feature_row: dict[str, Any] | None, *, max_retry_count: int = 3) -> bool:
        return cls.current_retry_count(feature_row) < max(1, int(max_retry_count))

    @classmethod
    def build_retry_patch(
        cls,
        feature_row: dict[str, Any] | None,
        *,
        max_retry_count: int = 3,
    ) -> dict[str, Any]:
        current_retry_count = cls.current_retry_count(feature_row)
        if current_retry_count >= max(1, int(max_retry_count)):
            return PhotoAnalysisStateMachine.build_transition_patch(
                feature_row,
                next_status="failed",
                error_message=(feature_row or {}).get("last_error") or "photo_analysis_retry_exhausted",
                retry_count=current_retry_count,
            )
        return PhotoAnalysisStateMachine.build_transition_patch(
            feature_row,
            next_status="retrying",
            error_message=(feature_row or {}).get("last_error"),
            retry_count=current_retry_count + 1,
            embedding_status="pending",
        )


class PhotoFeatureVersionManager:
    SNAPSHOT_FIELDS = (
        "profile_id",
        "photo_set_version",
        "analysis_status",
        "embedding_status",
        "retry_count",
        "primary_photo_id",
        "face_score_global",
        "appearance_score_global",
        "photo_quality_score",
        "photo_authenticity_score",
        "mature_score",
        "clean_score",
        "gentle_score",
        "sunny_score",
        "stylish_score",
        "appearance_summary",
        "appearance_tags_json",
        "analysis_model",
        "embedding_model",
        "last_error",
        "last_transition_at",
        "updated_at",
    )

    @classmethod
    def build_snapshot(
        cls,
        feature_row: dict[str, Any] | None,
        *,
        trigger_reason: str,
    ) -> dict[str, Any]:
        normalized = dict(feature_row or {})
        snapshot = {
            field_name: normalized.get(field_name)
            for field_name in cls.SNAPSHOT_FIELDS
            if field_name in normalized
        }
        snapshot["trigger_reason"] = str(trigger_reason or "").strip() or "unknown"
        return snapshot


class VerifiedPhotoQualityScorer:
    @staticmethod
    def score(
        profile_row: dict[str, Any] | None,
        photo_entries: list[dict[str, Any]] | None,
    ) -> VerifiedPhotoQualityScore:
        normalized_profile = dict(profile_row or {})
        sources = _normalize_photo_sources(list(photo_entries or []))
        if not sources:
            return VerifiedPhotoQualityScore(
                score=0.0,
                confidence=0.35,
                blur_penalty=18.0,
                lighting_penalty=16.0,
                occlusion_penalty=20.0,
                reasons=["缺少认证照来源"],
            )
        primary_source = sources[0].lower()
        verification_level = str(
            normalized_profile.get("photo_verification_level")
            or normalized_profile.get("verified_level")
            or ""
        ).strip().lower()
        base_score = {
            "offline": 88.0,
            "id": 84.0,
            "photo": 76.0,
            "uploaded": 68.0,
            "basic": 60.0,
        }.get(verification_level, 58.0)
        blur_penalty = 12.0 if any(token in primary_source for token in ("blur", "lowres", "small")) else 0.0
        lighting_penalty = 10.0 if any(token in primary_source for token in ("dark", "night", "backlight")) else 0.0
        occlusion_penalty = 14.0 if any(token in primary_source for token in ("mask", "sunglass", "cover")) else 0.0
        bonus = min(8.0, max(0, len(sources) - 1) * 2.5)
        score = max(0.0, min(100.0, base_score - blur_penalty - lighting_penalty - occlusion_penalty + bonus))
        confidence = max(0.35, min(1.0, score / 100.0))
        reasons: list[str] = []
        if blur_penalty:
            reasons.append("认证照清晰度偏弱")
        if lighting_penalty:
            reasons.append("认证照光线条件一般")
        if occlusion_penalty:
            reasons.append("认证照有人脸遮挡风险")
        if not reasons:
            reasons.append("认证照质量整体稳定")
        return VerifiedPhotoQualityScore(
            score=round(score, 2),
            confidence=round(confidence, 2),
            blur_penalty=round(blur_penalty, 2),
            lighting_penalty=round(lighting_penalty, 2),
            occlusion_penalty=round(occlusion_penalty, 2),
            reasons=reasons,
        )


class EnvironmentGapCompensator:
    @staticmethod
    def assess(
        verified_anchor_row: dict[str, Any] | None,
        candidate_photo_features: dict[str, Any] | None,
    ) -> EnvironmentGapAssessment:
        anchor_row = dict(verified_anchor_row or {})
        feature_row = dict(candidate_photo_features or {})
        anchor_quality = _clamp_score(anchor_row.get("quality_score"), default=60.0)
        feature_quality = _clamp_score(feature_row.get("photo_quality_score"), default=60.0)
        authenticity = _clamp_score(feature_row.get("photo_authenticity_score"), default=60.0)
        gap_score = max(0.0, min(100.0, abs(anchor_quality - feature_quality) * 0.9 + abs(anchor_quality - authenticity) * 0.4))
        compensation_factor = max(0.72, min(1.08, 1.0 - (gap_score / 250.0)))
        notes: list[str] = []
        if gap_score >= 24:
            notes.append("认证照和资料照拍摄环境差异较大")
        if feature_quality + 8 < anchor_quality:
            notes.append("资料照质量明显弱于认证照")
        if not notes:
            notes.append("认证照与资料照环境差异可控")
        return EnvironmentGapAssessment(
            gap_score=round(gap_score, 2),
            compensation_factor=round(compensation_factor, 2),
            notes=notes,
        )


class FaceConsistencyScorer:
    @staticmethod
    def _cosine_similarity(anchor_embedding: list[float], candidate_embedding: list[float]) -> float:
        if not anchor_embedding or not candidate_embedding or len(anchor_embedding) != len(candidate_embedding):
            return 0.0
        numerator = sum(left * right for left, right in zip(anchor_embedding, candidate_embedding))
        left_norm = math.sqrt(sum(value * value for value in anchor_embedding))
        right_norm = math.sqrt(sum(value * value for value in candidate_embedding))
        if left_norm <= 0 or right_norm <= 0:
            return 0.0
        return max(-1.0, min(1.0, numerator / (left_norm * right_norm)))

    @classmethod
    def score(
        cls,
        verified_anchor_row: dict[str, Any] | None,
        candidate_photo_features: dict[str, Any] | None,
        *,
        face_embedding_row: dict[str, Any] | None = None,
    ) -> FaceConsistencyResult:
        anchor_row = dict(verified_anchor_row or {})
        feature_row = dict(candidate_photo_features or {})
        embedding_row = dict(face_embedding_row or {})
        quality_confidence = max(
            0.35,
            min(
                1.0,
                _safe_float(anchor_row.get("confidence_score"), default=65.0) / 100.0,
            ),
        )
        environment = EnvironmentGapCompensator.assess(anchor_row, feature_row)
        anchor_embedding = list(anchor_row.get("embedding_json") or [])
        candidate_embedding = list(embedding_row.get("embedding_json") or [])
        if anchor_embedding and candidate_embedding:
            similarity = ((cls._cosine_similarity(anchor_embedding, candidate_embedding) + 1.0) / 2.0) * 100.0
        else:
            authenticity = _clamp_score(feature_row.get("photo_authenticity_score"), default=55.0)
            quality = _clamp_score(feature_row.get("photo_quality_score"), default=55.0)
            appearance = _clamp_score(feature_row.get("appearance_score_global"), default=55.0)
            similarity = (authenticity * 0.42) + (quality * 0.28) + (appearance * 0.30)
        compensated_score = similarity * environment.compensation_factor
        threshold = max(48.0, min(78.0, 70.0 - ((_safe_float(anchor_row.get("quality_score"), default=70.0) - 70.0) * 0.22)))
        weighted_score = max(0.0, min(100.0, compensated_score * (0.72 + quality_confidence * 0.28)))
        risk_flags = generate_photo_risk_flags(
            candidate_photo_features=feature_row,
            consistency_score=weighted_score,
            environment_gap_score=environment.gap_score,
        )
        if weighted_score >= threshold + 8:
            risk_level = "low"
        elif weighted_score >= threshold - 4:
            risk_level = "medium"
        else:
            risk_level = "high"
        return FaceConsistencyResult(
            score=round(weighted_score, 2),
            threshold=round(threshold, 2),
            confidence_weight=round(quality_confidence, 2),
            environment_gap_score=environment.gap_score,
            risk_level=risk_level,
            risk_flags=risk_flags,
            matched=weighted_score >= threshold,
        )


class VerifiedFaceAnchorWriter:
    @staticmethod
    def write(
        *,
        source_dsn: str | None,
        profile_id: int,
        profile_row: dict[str, Any] | None,
        photo_entries: list[dict[str, Any]] | None,
        face_embedding_row: dict[str, Any] | None = None,
        table_name: str = DEFAULT_VERIFIED_FACE_ANCHORS_TABLE,
    ) -> dict[str, Any]:
        normalized_profile_id = int(profile_id or 0)
        if not source_dsn or normalized_profile_id <= 0:
            return {}
        quality = VerifiedPhotoQualityScorer.score(profile_row, photo_entries)
        sources = _normalize_photo_sources(list(photo_entries or []))
        primary_source = sources[0] if sources else ""
        anchor_version = f"verified-anchor-v1:{normalized_profile_id}"
        embedding_json = list((face_embedding_row or {}).get("embedding_json") or []) or _deterministic_face_embedding(
            normalized_profile_id,
            sources,
            salt="verified_anchor",
        )
        return upsert_verified_face_anchor(
            source_dsn=source_dsn,
            profile_id=normalized_profile_id,
            anchor_version=anchor_version,
            patch={
                "verification_asset_type": "photo",
                "anchor_source": primary_source or None,
                "quality_score": quality.score,
                "confidence_score": round(quality.confidence * 100.0, 2),
                "environment_bias_score": round((quality.lighting_penalty + quality.occlusion_penalty) / 2.0, 2),
                "embedding_json": embedding_json,
                "metadata_json": {
                    "reasons": quality.reasons,
                    "blur_penalty": quality.blur_penalty,
                    "lighting_penalty": quality.lighting_penalty,
                    "occlusion_penalty": quality.occlusion_penalty,
                },
                "is_active": 1,
            },
            table_name=table_name,
        )

def _clamp_score(value: Any, *, default: float = 50.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(100.0, numeric))


def _stable_bucket(text: str, *, salt: str = "", lower: int = 0, upper: int = 100) -> float:
    normalized = f"{salt}|{text}".encode("utf-8")
    digest = hashlib.sha256(normalized).hexdigest()
    span = max(1, upper - lower)
    return float(lower + (int(digest[:8], 16) % (span + 1)))


def _deterministic_face_embedding(
    profile_id: int,
    photo_sources: list[str],
    *,
    salt: str,
    dims: int = 16,
) -> list[float]:
    seed = f"{profile_id}|{'|'.join(photo_sources)}|{salt}"
    vector: list[float] = []
    for index in range(max(4, dims)):
        bucket = _stable_bucket(seed, salt=f"{salt}:{index}", lower=0, upper=1000)
        vector.append(round((bucket / 500.0) - 1.0, 6))
    return vector


def _top_dimension_labels(feature_row: dict[str, Any], limit: int = 3) -> list[str]:
    label_pairs = [
        ("成熟感", _clamp_score(feature_row.get("mature_score"))),
        ("干净清爽", _clamp_score(feature_row.get("clean_score"))),
        ("温柔感", _clamp_score(feature_row.get("gentle_score"))),
        ("阳光感", _clamp_score(feature_row.get("sunny_score"))),
        ("利落精致", _clamp_score(feature_row.get("stylish_score"))),
    ]
    label_pairs.sort(key=lambda item: item[1], reverse=True)
    return [label for label, _score in label_pairs[: max(1, limit)]]


def _normalize_photo_sources(photo_entries: list[dict[str, Any]]) -> list[str]:
    return [
        str(item.get("photo_source") or "").strip()
        for item in photo_entries or []
        if isinstance(item, dict) and str(item.get("photo_source") or "").strip()
    ]


def generate_photo_risk_flags(
    *,
    candidate_photo_features: dict[str, Any] | None,
    consistency_score: float,
    environment_gap_score: float,
) -> list[str]:
    feature_row = dict(candidate_photo_features or {})
    flags: list[str] = []
    authenticity = _clamp_score(feature_row.get("photo_authenticity_score"), default=60.0)
    quality = _clamp_score(feature_row.get("photo_quality_score"), default=60.0)
    if consistency_score < 52:
        flags.append("mixed_identity_photos")
    if authenticity < 45:
        flags.append("heavy_beautification")
    if quality < 40:
        flags.append("low_quality_profile_photos")
    if environment_gap_score >= 24:
        flags.append("environment_gap_high")
    return flags


def compute_cover_authenticity_score(
    *,
    profile_row: dict[str, Any] | None,
    photo_entries: list[dict[str, Any]],
) -> float:
    normalized_profile = dict(profile_row or {})
    photo_sources = _normalize_photo_sources(photo_entries)
    if not photo_sources:
        return 0.0
    primary_source = photo_sources[0]
    avatar_url = str(normalized_profile.get("avatar_url") or "").strip()
    verified_level = str(
        normalized_profile.get("photo_verification_level")
        or normalized_profile.get("verified_level")
        or ""
    ).strip().lower()
    verification_bonus = {
        "offline": 18.0,
        "id": 16.0,
        "photo": 10.0,
        "uploaded": 6.0,
        "basic": 3.0,
    }.get(verified_level, 0.0)
    same_as_avatar_bonus = 8.0 if avatar_url and avatar_url == primary_source else 0.0
    photo_count_bonus = min(12.0, max(0, len(photo_sources) - 1) * 3.0)
    source_penalty = 0.0
    if any("filter" in source.lower() or "beauty" in source.lower() for source in photo_sources[:1]):
        source_penalty += 8.0
    score_seed = f"{normalized_profile.get('id') or ''}|{primary_source}|cover_auth"
    score = 46.0 + verification_bonus + same_as_avatar_bonus + photo_count_bonus - source_penalty
    score += _stable_bucket(score_seed, salt="cover_auth", lower=0, upper=16)
    return round(max(0.0, min(100.0, score)), 2)


def compute_cover_detail_consistency_score(photo_entries: list[dict[str, Any]]) -> float:
    photo_sources = _normalize_photo_sources(photo_entries)
    if not photo_sources:
        return 0.0
    if len(photo_sources) == 1:
        return 58.0
    primary_source = photo_sources[0]
    primary_tokens = {
        token
        for token in primary_source.lower().replace("://", "/").replace("?", "/").replace("&", "/").split("/")
        if token and len(token) >= 3
    }
    overlap_scores: list[float] = []
    for source in photo_sources[1:]:
        tokens = {
            token
            for token in source.lower().replace("://", "/").replace("?", "/").replace("&", "/").split("/")
            if token and len(token) >= 3
        }
        if not tokens or not primary_tokens:
            overlap_scores.append(0.45)
            continue
        union_size = len(primary_tokens | tokens)
        overlap_scores.append(len(primary_tokens & tokens) / union_size if union_size else 0.45)
    average_overlap = sum(overlap_scores) / max(1, len(overlap_scores))
    score = 42.0 + (average_overlap * 42.0) + min(12.0, len(photo_sources[1:]) * 4.0)
    return round(max(0.0, min(100.0, score)), 2)


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("appearance embedding sync cannot run inside an existing event loop")


def _score_to_bonus(value: Any, *, max_bonus: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0.0
    numeric = max(0.0, min(100.0, numeric))
    return round((numeric / 100.0) * max_bonus, 2)


def _safe_float(value: Any, *, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _preference_history_count(user_appearance_preference: dict[str, Any] | None) -> int:
    preference_row = dict(user_appearance_preference or {})
    positive_count = max(0, int(_safe_float(preference_row.get("positive_sample_count"), default=0.0)))
    negative_count = max(0, int(_safe_float(preference_row.get("negative_sample_count"), default=0.0)))
    return positive_count + negative_count


def calibrate_global_appearance_score(value: Any) -> float:
    raw_score = _clamp_score(value, default=50.0)
    normalized = (raw_score - 50.0) / 50.0
    calibrated = 50.0 + (math.tanh(normalized * 1.15) * 30.0)
    return round(max(0.0, min(100.0, calibrated)), 2)


def resolve_global_bonus_multiplier(user_appearance_preference: dict[str, Any] | None) -> float:
    total_count = _preference_history_count(user_appearance_preference)
    if total_count <= 0:
        return 1.2
    if total_count < 3:
        return 1.15
    if total_count < 8:
        return 1.08
    return 1.0


def resolve_preference_weight_multiplier(user_appearance_preference: dict[str, Any] | None) -> float:
    total_count = _preference_history_count(user_appearance_preference)
    if total_count <= 0:
        return 0.3
    if total_count < 3:
        return 0.45
    if total_count < 8:
        return 0.75
    if total_count < 20:
        return 1.0
    return 1.15


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _time_decay_multiplier(
    created_at: Any,
    *,
    now: datetime | None = None,
    half_life_days: float = _PREFERENCE_EVENT_HALF_LIFE_DAYS,
) -> float:
    created_dt = _coerce_datetime(created_at)
    if created_dt is None:
        return 1.0
    current = now or datetime.now(created_dt.tzinfo)
    age_seconds = max(0.0, (current - created_dt).total_seconds())
    if half_life_days <= 0:
        return 1.0
    half_life_seconds = half_life_days * 86400.0
    return max(0.15, 0.5 ** (age_seconds / half_life_seconds))


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
    global_bonus = round(
        _score_to_bonus(
            GlobalAppearanceScorer.score(feature_row),
            max_bonus=15.0,
        )
        * resolve_global_bonus_multiplier(preference_row),
        2,
    )

    preference_bonus = 0.0
    matched_dimensions = 0
    total_similarity = 0.0
    for candidate_key, user_key in _PREFERENCE_DIMENSIONS:
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
        preference_bonus = round(
            ((average_similarity * 30.0) - 10.0)
            * resolve_preference_weight_multiplier(preference_row),
            2,
        )

    return PhotoBonusBreakdown(
        quality_bonus=quality_bonus,
        global_bonus=global_bonus,
        preference_bonus=preference_bonus,
    )


def compute_trust_bonus_breakdown(
    profile_row: dict[str, Any] | None,
    candidate_photo_features: dict[str, Any] | None,
) -> TrustBonusBreakdown:
    normalized_profile = dict(profile_row or {})
    feature_row = dict(candidate_photo_features or {})
    verified_level = str(
        normalized_profile.get("verified_level")
        or normalized_profile.get("photo_verification_level")
        or ""
    ).strip().lower()
    photo_level = str(
        normalized_profile.get("photo_verification_level")
        or feature_row.get("photo_verification_level")
        or ""
    ).strip().lower()
    verified_bonus = {
        "offline": 4.0,
        "id": 3.2,
        "photo": 2.2,
        "uploaded": 1.0,
        "basic": 0.8,
    }.get(verified_level, 0.0)
    photo_verification_bonus = {
        "offline_verified": 3.0,
        "live_video_verified": 2.8,
        "human_verified": 2.2,
        "photo": 1.6,
        "uploaded": 0.6,
    }.get(photo_level, 0.0)
    authenticity_score = _clamp_score(feature_row.get("photo_authenticity_score"), default=0.0)
    quality_score = _clamp_score(feature_row.get("photo_quality_score"), default=0.0)
    authenticity_bonus = round(max(0.0, min(3.5, (authenticity_score - 60.0) / 12.0)), 2)
    quality_bonus = round(max(0.0, min(2.5, (quality_score - 65.0) / 14.0)), 2)
    return TrustBonusBreakdown(
        verified_bonus=verified_bonus,
        photo_verification_bonus=photo_verification_bonus,
        authenticity_bonus=authenticity_bonus,
        quality_bonus=quality_bonus,
    )


def compute_risk_penalty_breakdown(
    profile_row: dict[str, Any] | None,
    candidate_photo_features: dict[str, Any] | None,
    *,
    risk_flags: Iterable[Any] | None = None,
) -> RiskPenaltyBreakdown:
    del profile_row
    feature_row = dict(candidate_photo_features or {})
    normalized_flags = [str(item or "").strip() for item in risk_flags or [] if str(item or "").strip()]
    authenticity_score = _clamp_score(feature_row.get("photo_authenticity_score"), default=0.0)
    quality_score = _clamp_score(feature_row.get("photo_quality_score"), default=0.0)

    authenticity_penalty = round(max(0.0, min(6.0, (55.0 - authenticity_score) / 7.5)), 2)
    quality_penalty = round(max(0.0, min(3.5, (45.0 - quality_score) / 8.0)), 2)
    explicit_flag_penalty = 0.0
    reasons: list[str] = []

    joined_flags = "；".join(normalized_flags)
    if any(token in joined_flags for token in ("假图", "修图", "滤镜", "AI 图", "P 图")):
        explicit_flag_penalty += 4.0
        reasons.append("照片真实性需要再确认")
    if any(token in joined_flags for token in ("多人", "合照", "看不清", "遮挡")):
        explicit_flag_penalty += 2.5
        reasons.append("主图辨识度一般，最好多看几张")

    style_mismatch_penalty = 0.0
    if any("长相类型和你的偏好有一定偏差" in flag for flag in normalized_flags):
        style_mismatch_penalty = 1.8
        reasons.append("长相风格和你常点开的类型有点偏差")

    if authenticity_penalty >= 3.0 and "照片真实性需要再确认" not in reasons:
        reasons.append("照片可信度暂时偏弱")
    if quality_penalty >= 2.0 and "主图辨识度一般，最好多看几张" not in reasons:
        reasons.append("主图信息量偏少，建议点开详情再看")

    return RiskPenaltyBreakdown(
        authenticity_penalty=authenticity_penalty,
        quality_penalty=quality_penalty,
        explicit_flag_penalty=round(explicit_flag_penalty, 2),
        style_mismatch_penalty=style_mismatch_penalty,
        reasons=reasons[:3],
    )


def build_appearance_explanation(
    candidate_photo_features: dict[str, Any] | None,
    user_appearance_preference: dict[str, Any] | None = None,
    *,
    trust_bonus: TrustBonusBreakdown | None = None,
    risk_penalty: RiskPenaltyBreakdown | None = None,
) -> dict[str, Any]:
    feature_row = dict(candidate_photo_features or {})
    preference_row = dict(user_appearance_preference or {})
    if not feature_row:
        return {"summary": "", "highlights": [], "stage": "unknown"}

    photo_bonus = compute_photo_bonus_breakdown(feature_row, preference_row)
    trust = trust_bonus or compute_trust_bonus_breakdown({}, feature_row)
    risk = risk_penalty or compute_risk_penalty_breakdown({}, feature_row)
    top_labels = _top_dimension_labels(feature_row, limit=2)
    highlights: list[str] = []

    if top_labels:
        highlights.append(f"照片整体更偏{top_labels[0]}")
    if len(top_labels) > 1:
        highlights.append(f"第一眼会觉得更{top_labels[1]}")
    if photo_bonus.global_bonus >= 8.0:
        highlights.append("第一眼眼缘会更强")
    elif photo_bonus.global_bonus >= 4.0:
        highlights.append("照片整体比较顺眼")

    if photo_bonus.preference_bonus >= 8.0:
        highlights.append("长相类型贴近你最近常点喜欢的那一挂")
    elif photo_bonus.preference_bonus >= 3.0:
        highlights.append("气质方向和你的偏好比较接近")
    elif photo_bonus.preference_bonus <= -5.0:
        highlights.append("长相风格和你平时会点开的类型有点偏差")

    if trust.total >= 5.0:
        highlights.append("资料和照片可信度都更稳")
    elif trust.total >= 2.5:
        highlights.append("照片可信度相对不错")

    summary_parts: list[str] = []
    if photo_bonus.global_bonus >= 8.0:
        summary_parts.append("第一眼眼缘会更强")
    elif photo_bonus.global_bonus >= 4.0:
        summary_parts.append("照片整体比较顺眼")
    if photo_bonus.preference_bonus >= 8.0:
        summary_parts.append("长相类型也更贴近你的偏好")
    elif photo_bonus.preference_bonus >= 3.0:
        summary_parts.append("气质方向和你的偏好比较接近")
    elif top_labels:
        summary_parts.append(f"整体偏{top_labels[0]}")
    if trust.total >= 5.0:
        summary_parts.append("资料和照片可信度也更稳")
    elif risk.total >= 5.0:
        summary_parts.append("但照片真实性最好再确认一下")

    unique_highlights: list[str] = []
    for item in highlights:
        if item and item not in unique_highlights:
            unique_highlights.append(item)

    total_samples = max(
        0,
        int(_safe_float(preference_row.get("positive_sample_count"), default=0.0))
        + int(_safe_float(preference_row.get("negative_sample_count"), default=0.0)),
    )
    stage = "new_user"
    if total_samples >= 20:
        stage = "high_preference_confidence"
    elif total_samples >= 8:
        stage = "stable_preference"
    elif total_samples >= 3:
        stage = "warming_up"

    return {
        "summary": "，".join(summary_parts[:3]) or str(feature_row.get("appearance_summary") or "").strip(),
        "highlights": unique_highlights[:4],
        "stage": stage,
        "preference_weight_multiplier": resolve_preference_weight_multiplier(preference_row),
    }


def build_match_explanation_payload(
    *,
    matched_on: Iterable[Any] | None = None,
    appearance_reasoning: dict[str, Any] | None = None,
    trust_summary: str | None = None,
) -> dict[str, Any]:
    base_highlights = [str(item or "").strip() for item in list(matched_on or []) if str(item or "").strip()]
    appearance_payload = dict(appearance_reasoning or {})
    appearance_summary = str(appearance_payload.get("summary") or "").strip()
    appearance_highlights = [
        str(item or "").strip()
        for item in list(appearance_payload.get("highlights") or [])
        if str(item or "").strip()
    ]
    trust_text = str(trust_summary or "").strip()

    base_summary = "、".join(base_highlights[:2])
    template_key = "base_only"
    if base_summary and appearance_summary:
        template_key = "base_plus_appearance"
    elif base_summary and trust_text:
        template_key = "base_plus_trust"
    elif appearance_summary:
        template_key = "appearance_only"

    summary = EXPLANATION_TEMPLATE_LIBRARY[template_key].format(
        base_summary=base_summary,
        appearance_summary=appearance_summary,
        trust_summary=trust_text,
    ).strip("， ")

    highlights: list[str] = []
    for item in base_highlights[:2] + appearance_highlights[:2]:
        if item and item not in highlights:
            highlights.append(item)
    if not highlights and summary:
        highlights.append(summary)

    return {
        "template_key": template_key,
        "summary": summary,
        "highlights": highlights[:4],
    }


class GlobalAppearanceScorer:
    @staticmethod
    def score(candidate_photo_features: dict[str, Any] | None) -> float:
        feature_row = dict(candidate_photo_features or {})
        if feature_row.get("appearance_score_global") not in (None, ""):
            return calibrate_global_appearance_score(feature_row.get("appearance_score_global"))
        quality_score = _clamp_score(feature_row.get("photo_quality_score"), default=50.0)
        authenticity_score = _clamp_score(feature_row.get("photo_authenticity_score"), default=50.0)
        face_score = _clamp_score(feature_row.get("face_score_global"), default=50.0)
        raw_score = (quality_score * 0.22) + (authenticity_score * 0.18) + (face_score * 0.60)
        return calibrate_global_appearance_score(raw_score)


def resolve_appearance_weight_strategy(
    scene: str | None,
    user_appearance_preference: dict[str, Any] | None = None,
) -> AppearanceWeightStrategy:
    normalized_scene = str(scene or "general").strip().lower() or "general"
    total_count = _preference_history_count(user_appearance_preference)
    user_stage = "new_user"
    if total_count >= 20:
        user_stage = "high_preference_confidence"
    elif total_count >= 8:
        user_stage = "stable_preference"
    elif total_count >= 3:
        user_stage = "warming_up"

    base_weight = 1.0
    preference_weight = 1.0
    trust_weight = 1.0
    risk_weight = 1.0

    if normalized_scene.startswith("discovery"):
        base_weight = 1.12
        preference_weight = 0.92
        trust_weight = 0.95
        risk_weight = 0.92
    elif normalized_scene.startswith("recommendation"):
        base_weight = 0.96
        preference_weight = 1.08
        trust_weight = 1.12
        risk_weight = 1.08

    if user_stage == "new_user":
        base_weight += 0.18
        preference_weight *= 0.45
    elif user_stage == "warming_up":
        base_weight += 0.08
        preference_weight *= 0.82
    elif user_stage == "high_preference_confidence":
        preference_weight *= 1.08

    return AppearanceWeightStrategy(
        scene=normalized_scene,
        base_weight=round(base_weight, 2),
        preference_weight=round(preference_weight, 2),
        trust_weight=round(trust_weight, 2),
        risk_weight=round(risk_weight, 2),
        user_stage=user_stage,
    )


class TrustBonusCalculator:
    @staticmethod
    def compute(
        profile_row: dict[str, Any] | None,
        candidate_photo_features: dict[str, Any] | None,
    ) -> TrustBonusBreakdown:
        return compute_trust_bonus_breakdown(profile_row, candidate_photo_features)


class RiskPenaltyCalculator:
    @staticmethod
    def compute(
        profile_row: dict[str, Any] | None,
        candidate_photo_features: dict[str, Any] | None,
        *,
        risk_flags: Iterable[Any] | None = None,
    ) -> RiskPenaltyBreakdown:
        return compute_risk_penalty_breakdown(
            profile_row,
            candidate_photo_features,
            risk_flags=risk_flags,
        )


class ProfilePhotoTrustScorer:
    @staticmethod
    def score(
        profile_row: dict[str, Any] | None,
        candidate_photo_features: dict[str, Any] | None,
        *,
        risk_flags: Iterable[Any] | None = None,
    ) -> ProfilePhotoTrustScore:
        feature_row = dict(candidate_photo_features or {})
        trust_bonus = compute_trust_bonus_breakdown(profile_row, feature_row)
        risk_penalty = compute_risk_penalty_breakdown(
            profile_row,
            feature_row,
            risk_flags=risk_flags,
        )
        authenticity_score = _clamp_score(feature_row.get("photo_authenticity_score"), default=0.0)
        quality_score = _clamp_score(feature_row.get("photo_quality_score"), default=0.0)
        confidence_weight = round(
            max(0.35, min(1.0, ((quality_score * 0.45) + (authenticity_score * 0.55)) / 100.0)),
            2,
        )
        raw_score = 48.0 + (trust_bonus.total * 6.0) - (risk_penalty.total * 4.5)
        weighted_score = round(max(0.0, min(100.0, raw_score * confidence_weight)), 2)
        if weighted_score >= 72:
            risk_level = "low"
        elif weighted_score >= 48:
            risk_level = "medium"
        else:
            risk_level = "high"

        badges: list[str] = []
        verified_level = str(
            (profile_row or {}).get("verified_level")
            or (profile_row or {}).get("photo_verification_level")
            or ""
        ).strip().lower()
        if verified_level in {"offline", "id"}:
            badges.append("认证信息较完整")
        if authenticity_score >= 75:
            badges.append("照片真人感较强")
        elif authenticity_score >= 60:
            badges.append("照片可信度尚可")
        if quality_score >= 75:
            badges.append("资料照质量较稳定")
        if risk_penalty.reasons and risk_level != "low":
            badges.append(risk_penalty.reasons[0])

        deduped_badges: list[str] = []
        for item in badges:
            if item and item not in deduped_badges:
                deduped_badges.append(item)
        return ProfilePhotoTrustScore(
            score=weighted_score,
            confidence_weight=confidence_weight,
            risk_level=risk_level,
            badges=deduped_badges[:3],
        )


def build_photo_feature_patch(
    *,
    profile_row: dict[str, Any] | None,
    photo_entries: list[dict[str, Any]],
    existing_feature_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_profile = dict(profile_row or {})
    normalized_entries = [dict(item) for item in photo_entries or [] if isinstance(item, dict)]
    photo_sources = [str(item.get("photo_source") or "").strip() for item in normalized_entries if str(item.get("photo_source") or "").strip()]
    if not photo_sources:
        return {
            "analysis_status": "failed",
            "embedding_status": "pending",
            "last_error": "no_photo_sources",
        }

    signature = "|".join(photo_sources)
    photo_set_version = int(hashlib.sha256(signature.encode("utf-8")).hexdigest()[:8], 16)
    detections = FaceDetector.detect(normalized_entries)
    primary_entry = PrimaryPhotoSelector.select(normalized_entries, detections) or normalized_entries[0]
    primary_source = str(primary_entry.get("photo_source") or photo_sources[0]).strip()
    photo_count = len(photo_sources)
    verified_level = str(
        normalized_profile.get("photo_verification_level")
        or normalized_profile.get("verified_level")
        or ""
    ).strip().lower()
    age_value = normalized_profile.get("age")
    try:
        age_bias = max(-8.0, min(8.0, (float(age_value) - 28.0) * 0.7))
    except (TypeError, ValueError):
        age_bias = 0.0

    verification_bonus = {
        "offline": 16.0,
        "id": 14.0,
        "photo": 10.0,
        "uploaded": 7.0,
        "basic": 4.0,
    }.get(verified_level, 0.0)
    source_seed = f"{normalized_profile.get('id') or ''}|{primary_source}|{signature}"
    clean_score = min(100.0, 45.0 + verification_bonus + photo_count * 5.0 + _stable_bucket(source_seed, salt="clean", lower=0, upper=20))
    cover_authenticity_score = compute_cover_authenticity_score(
        profile_row=normalized_profile,
        photo_entries=normalized_entries,
    )
    cover_detail_consistency_score = compute_cover_detail_consistency_score(normalized_entries)
    authenticity_score = min(
        100.0,
        (
            (42.0 + verification_bonus * 1.4 + photo_count * 4.0 + _stable_bucket(source_seed, salt="auth", lower=0, upper=18)) * 0.45
            + cover_authenticity_score * 0.30
            + cover_detail_consistency_score * 0.25
        ),
    )
    quality_score = PhotoQualityScorer.score(
        profile_row=normalized_profile,
        photo_entries=normalized_entries,
        detections=detections,
    )
    mature_score = min(100.0, max(0.0, 38.0 + age_bias + _stable_bucket(source_seed, salt="mature", lower=0, upper=40)))
    gentle_score = min(100.0, 32.0 + _stable_bucket(source_seed, salt="gentle", lower=0, upper=45))
    sunny_score = min(100.0, 30.0 + _stable_bucket(source_seed, salt="sunny", lower=0, upper=50))
    stylish_score = min(100.0, 28.0 + photo_count * 3.0 + _stable_bucket(source_seed, salt="stylish", lower=0, upper=42))
    face_score = round((clean_score + mature_score + gentle_score + sunny_score + stylish_score) / 5.0, 2)
    appearance_score = round((quality_score * 0.22) + (authenticity_score * 0.18) + (face_score * 0.60), 2)
    top_labels = _top_dimension_labels(
        {
            "mature_score": mature_score,
            "clean_score": clean_score,
            "gentle_score": gentle_score,
            "sunny_score": sunny_score,
            "stylish_score": stylish_score,
        }
    )
    appearance_summary = AppearanceSummaryGenerator.generate(
        style_scores={
            "mature_score": mature_score,
            "clean_score": clean_score,
            "gentle_score": gentle_score,
            "sunny_score": sunny_score,
            "stylish_score": stylish_score,
        },
        attribute_scores={
            "eye_size_score": 36.0 + gentle_score * 0.24,
            "face_roundness_score": 30.0 + sunny_score * 0.18,
            "skin_clarity_score": 30.0 + clean_score * 0.46,
            "smile_intensity_score": 24.0 + sunny_score * 0.42,
        },
    )
    appearance_tags_json = [{"label": label} for label in top_labels]
    existing_version = int(existing_feature_row.get("photo_set_version") or 0) if isinstance(existing_feature_row, dict) else 0
    embedding_status = "pending"
    if existing_version == photo_set_version and existing_feature_row:
        current_summary = str(existing_feature_row.get("appearance_summary") or "").strip()
        current_status = str(existing_feature_row.get("embedding_status") or "").strip()
        if current_summary == appearance_summary and current_status:
            embedding_status = current_status
    return {
        "primary_photo_id": None,
        "photo_set_version": photo_set_version,
        "analysis_status": "done",
        "embedding_status": embedding_status,
        "face_score_global": round(face_score, 2),
        "appearance_score_global": appearance_score,
        "photo_quality_score": round(quality_score, 2),
        "photo_authenticity_score": round(authenticity_score, 2),
        "mature_score": round(mature_score, 2),
        "clean_score": round(clean_score, 2),
        "gentle_score": round(gentle_score, 2),
        "sunny_score": round(sunny_score, 2),
        "stylish_score": round(stylish_score, 2),
        "appearance_summary": appearance_summary,
        "appearance_tags_json": appearance_tags_json,

        # 新增：AI颜值评分和AI口语化描述
        "beauty_score": None,  # 将在refresh_profile_photo_features中填充
        "beauty_score_model": None,
        "beauty_score_reasoning": None,
        "appearance_keywords_json": None,
        "appearance_style_type": None,
        "dominant_features_json": None,

        "analysis_model": "deterministic-photo-feature-v1",
        "last_error": None,
    }


def _save_text_embedding(*, subject_id: int, vector_type: str, text: str) -> dict[str, Any]:
    if subject_id <= 0 or not text.strip():
        return {"saved": False, "reason": "missing_subject_or_text"}
    from match_domain.embedding_service import EmbeddingService
    from match_domain.vector_store_lite import VectorStoreLite

    async def _generate() -> list[float]:
        service = EmbeddingService(model_name="text-embedding-v3")
        try:
            return await service.generate_embedding(text)
        finally:
            await service.aclose()

    embedding = _run_async(_generate())
    vector_store = VectorStoreLite()
    try:
        result = vector_store.save_vector_with_version(
            user_id=subject_id,
            vector_type=vector_type,
            embedding=embedding,
            raw_text=text,
            conversation_id=f"{vector_type}-{subject_id}",
        )
        return {"saved": bool(result.get("success")), "result": result}
    finally:
        vector_store.close()


def _persist_photo_feature_version_snapshot(
    *,
    source_dsn: str | None,
    feature_row: dict[str, Any] | None,
    trigger_reason: str,
    table_name: str = DEFAULT_PROFILE_PHOTO_FEATURE_VERSIONS_TABLE,
) -> dict[str, Any] | None:
    normalized_row = dict(feature_row or {})
    profile_id = int(normalized_row.get("profile_id") or 0)
    if not source_dsn or profile_id <= 0:
        return None
    snapshot = PhotoFeatureVersionManager.build_snapshot(
        normalized_row,
        trigger_reason=trigger_reason,
    )
    try:
        return insert_profile_photo_feature_version(
            source_dsn=source_dsn,
            profile_id=profile_id,
            snapshot=snapshot,
            photo_set_version=int(normalized_row.get("photo_set_version") or 1),
            analysis_status=str(normalized_row.get("analysis_status") or "pending"),
            trigger_reason=trigger_reason,
            table_name=table_name,
        )
    except Exception:
        return None


def _build_face_attribute_patch(
    *,
    profile_row: dict[str, Any] | None,
    feature_row: dict[str, Any] | None,
    photo_entries: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    normalized_profile = dict(profile_row or {})
    normalized_feature = dict(feature_row or {})
    photo_sources = _normalize_photo_sources(list(photo_entries or []))
    profile_id = int(normalized_profile.get("id") or normalized_feature.get("profile_id") or 0)
    seed = f"{profile_id}|{'|'.join(photo_sources)}|face_attributes"
    mature = _clamp_score(normalized_feature.get("mature_score"), default=50.0)
    clean = _clamp_score(normalized_feature.get("clean_score"), default=50.0)
    gentle = _clamp_score(normalized_feature.get("gentle_score"), default=50.0)
    sunny = _clamp_score(normalized_feature.get("sunny_score"), default=50.0)
    stylish = _clamp_score(normalized_feature.get("stylish_score"), default=50.0)
    eye_size = round(min(100.0, 36.0 + gentle * 0.24 + _stable_bucket(seed, salt="eye", lower=0, upper=18)), 2)
    face_roundness = round(min(100.0, 30.0 + sunny * 0.18 + _stable_bucket(seed, salt="round", lower=0, upper=22)), 2)
    jaw_definition = round(min(100.0, 32.0 + mature * 0.26 + stylish * 0.14), 2)
    smile_intensity = round(min(100.0, 24.0 + sunny * 0.42), 2)
    skin_clarity = round(min(100.0, 30.0 + clean * 0.46), 2)
    youthfulness = round(
        min(100.0, max(0.0, (eye_size * 0.28) + (face_roundness * 0.24) + (skin_clarity * 0.24) + (smile_intensity * 0.24))),
        2,
    )
    return {
        "primary_photo_id": normalized_feature.get("primary_photo_id"),
        "face_count": max(1, len(photo_sources)),
        "dominant_face_index": 0,
        "eye_size_score": eye_size,
        "face_roundness_score": face_roundness,
        "jaw_definition_score": jaw_definition,
        "smile_intensity_score": smile_intensity,
        "skin_clarity_score": skin_clarity,
        "style_clean_score": round(clean, 2),
        "style_gentle_score": round(gentle, 2),
        "style_sunny_score": round(sunny, 2),
        "style_stylish_score": round(stylish, 2),
        "youthfulness_score": youthfulness,
        "attributes_json": {
            "appearance_summary": normalized_feature.get("appearance_summary"),
            "top_labels": _top_dimension_labels(normalized_feature),
        },
        "extractor_version": "deterministic-face-attributes-v1",
    }


def _sync_profile_face_side_tables(
    *,
    source_dsn: str | None,
    profile_row: dict[str, Any] | None,
    photo_entries: list[dict[str, Any]] | None,
    feature_row: dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_feature = dict(feature_row or {})
    normalized_profile_id = int(normalized_feature.get("profile_id") or (profile_row or {}).get("id") or 0)
    if not source_dsn or normalized_profile_id <= 0:
        return {}
    photo_sources = _normalize_photo_sources(list(photo_entries or []))
    attributes_row = upsert_profile_face_attributes(
        source_dsn=source_dsn,
        profile_id=normalized_profile_id,
        patch=_build_face_attribute_patch(
            profile_row=profile_row,
            feature_row=normalized_feature,
            photo_entries=photo_entries,
        ),
    )
    embedding_row = upsert_profile_face_embedding(
        source_dsn=source_dsn,
        profile_id=normalized_profile_id,
        embedding_type="primary_face",
        patch={
            "photo_set_version": int(normalized_feature.get("photo_set_version") or 1),
            "embedding_dim": 16,
            "embedding_json": _deterministic_face_embedding(
                normalized_profile_id,
                photo_sources,
                salt="primary_face",
            ),
            "quality_score": normalized_feature.get("photo_quality_score"),
            "confidence_score": normalized_feature.get("photo_authenticity_score"),
            "extractor_version": "deterministic-face-embedding-v1",
        },
    )
    verified_level = str(
        (profile_row or {}).get("photo_verification_level")
        or (profile_row or {}).get("verified_level")
        or ""
    ).strip().lower()
    anchor_row: dict[str, Any] | None = None
    consistency_row: dict[str, Any] | None = None
    if verified_level in {"offline", "id", "photo", "uploaded"} and photo_sources:
        anchor_row = VerifiedFaceAnchorWriter.write(
            source_dsn=source_dsn,
            profile_id=normalized_profile_id,
            profile_row=profile_row,
            photo_entries=photo_entries,
            face_embedding_row=embedding_row,
        )
        consistency = FaceConsistencyScorer.score(
            anchor_row,
            normalized_feature,
            face_embedding_row=embedding_row,
        )
        consistency_row = upsert_face_consistency_score(
            source_dsn=source_dsn,
            profile_id=normalized_profile_id,
            patch={
                "anchor_id": anchor_row.get("id"),
                "consistency_score": consistency.score,
                "threshold_score": consistency.threshold,
                "confidence_weight": consistency.confidence_weight,
                "environment_gap_score": consistency.environment_gap_score,
                "risk_level": consistency.risk_level,
                "risk_flags_json": consistency.risk_flags,
                "detail_json": {
                    "matched": consistency.matched,
                    "badges": list(ProfilePhotoTrustScorer.score(profile_row, normalized_feature, risk_flags=consistency.risk_flags).badges),
                },
            },
        )
    return {
        "face_attributes": attributes_row,
        "face_embedding": embedding_row,
        "verified_anchor": anchor_row,
        "consistency": consistency_row,
    }


def _merge_analysis_patch(
    base_patch: dict[str, Any],
    transition_patch: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(base_patch)
    merged.update(transition_patch)
    return merged


def _sync_profile_vector_indexes(
    *,
    source_dsn: str | None,
    profile_id: int,
) -> dict[str, Any]:
    normalized_profile_id = int(profile_id or 0)
    if not source_dsn or normalized_profile_id <= 0:
        return {
            "triggered": False,
            "saved": False,
            "error": "source_or_profile_missing",
            "indexes": [],
        }

    from .appearance_search import AppearanceStyleIndexBuilder, FaceVectorIndexBuilder

    results: list[dict[str, Any]] = []
    saved_any = False
    for index_name, builder in (
        ("face_embedding", FaceVectorIndexBuilder),
        ("appearance_profile", AppearanceStyleIndexBuilder),
    ):
        try:
            result = dict(
                builder.build_profile_index(
                    source_dsn=source_dsn,
                    profile_id=normalized_profile_id,
                )
            )
        except Exception as exc:
            result = {
                "saved": False,
                "error": f"index_sync_failed:{str(exc)[:180]}",
            }
        result.setdefault("index_name", index_name)
        saved_any = saved_any or bool(result.get("saved"))
        results.append(result)

    failed_indexes = [
        str(item.get("index_name") or "unknown")
        for item in results
        if not bool(item.get("saved"))
    ]
    return {
        "triggered": True,
        "saved": saved_any,
        "profile_id": normalized_profile_id,
        "indexes": results,
        "failed_indexes": failed_indexes,
    }


def refresh_profile_photo_features(
    *,
    source_dsn: str | None,
    profile_id: int,
    profile_source_dsn: str | None = None,
    source_table_name: str | None = None,
    photos_table_name: str | None = None,
    table_name: str = DEFAULT_PROFILE_PHOTO_FEATURES_TABLE,
    sync_embedding: bool = True,
) -> dict[str, Any]:
    normalized_profile_id = int(profile_id or 0)
    if not source_dsn or normalized_profile_id <= 0:
        return {"saved": False, "error": "source_or_profile_missing"}
    existing_feature_row = load_candidate_photo_features(
        source_dsn=source_dsn,
        profile_ids=[normalized_profile_id],
        table_name=table_name,
    ).get(normalized_profile_id)
    processing_patch = PhotoAnalysisStateMachine.build_transition_patch(
        existing_feature_row,
        next_status="processing",
        embedding_status="pending",
        retry_count=PhotoAnalysisRetryQueue.current_retry_count(existing_feature_row),
    )
    processing_row = upsert_profile_photo_features(
        source_dsn=source_dsn,
        profile_id=normalized_profile_id,
        patch=processing_patch,
        table_name=table_name,
    )
    profile_source = str(profile_source_dsn or source_dsn or "").strip()
    resolved_profile_source, resolved_table = resolve_profile_source(profile_source, source_table_name)
    if not resolved_profile_source or not resolved_table:
        failed = upsert_profile_photo_features(
            source_dsn=source_dsn,
            profile_id=normalized_profile_id,
            patch=PhotoAnalysisStateMachine.build_transition_patch(
                processing_row,
                next_status="failed",
                error_message="profile_source_unresolved",
                retry_count=PhotoAnalysisRetryQueue.current_retry_count(processing_row),
            ),
            table_name=table_name,
        )
        _persist_photo_feature_version_snapshot(
            source_dsn=source_dsn,
            feature_row=failed,
            trigger_reason="analysis_failed",
        )
        return failed
    try:
        profile_row = get_profile(
            source_dsn=resolved_profile_source,
            source_table_name=resolved_table,
            profile_id=normalized_profile_id,
        )
        photo_entries = list_profile_photos(
            source_dsn=resolved_profile_source,
            source_table_name=resolved_table,
            profile_id=normalized_profile_id,
            photos_table_name=photos_table_name,
        )
        patch = build_photo_feature_patch(
            profile_row=profile_row,
            photo_entries=photo_entries,
            existing_feature_row=processing_row,
        )
    except Exception as exc:
        failed = upsert_profile_photo_features(
            source_dsn=source_dsn,
            profile_id=normalized_profile_id,
            patch=PhotoAnalysisStateMachine.build_transition_patch(
                processing_row,
                next_status="failed",
                error_message=f"photo_feature_refresh_failed:{str(exc)[:180]}",
                retry_count=PhotoAnalysisRetryQueue.current_retry_count(processing_row),
            ),
            table_name=table_name,
        )
        _persist_photo_feature_version_snapshot(
            source_dsn=source_dsn,
            feature_row=failed,
            trigger_reason="analysis_failed",
        )
        return failed
    transition_patch = PhotoAnalysisStateMachine.build_transition_patch(
        processing_row,
        next_status=str(patch.get("analysis_status") or "failed"),
        error_message=patch.get("last_error"),
        retry_count=PhotoAnalysisRetryQueue.current_retry_count(processing_row),
        embedding_status=patch.get("embedding_status"),
    )
    saved = upsert_profile_photo_features(
        source_dsn=source_dsn,
        profile_id=normalized_profile_id,
        patch=_merge_analysis_patch(patch, transition_patch),
        table_name=table_name,
    )
    if str(saved.get("analysis_status") or "").lower() == "done":
        try:
            # 新增：人脸向量提取
            from .face_embedding_extractor import extract_face_embedding
            from .face_similarity_search import upsert_profile_face_embedding

            face_embedding_result = None
            primary_photo_url = None

            # 找到主照片（第一张照片）
            if photo_entries and len(photo_entries) > 0:
                primary_photo_url = photo_entries[0].get("photo_url") or photo_entries[0].get("photo_source")

            # 提取人脸向量
            if primary_photo_url:
                face_embedding_result = extract_face_embedding(primary_photo_url)

                if face_embedding_result and face_embedding_result.get("success"):
                    # 保存人脸向量到数据库
                    import json
                    upsert_profile_face_embedding(
                        source_dsn=source_dsn,
                        profile_id=normalized_profile_id,
                        face_embedding_json=json.dumps(face_embedding_result["face_embedding"]),
                        face_embedding_model=face_embedding_result["face_embedding_model"],
                        face_embedding_dimension=face_embedding_result["face_embedding_dimension"],
                        face_detection_confidence=face_embedding_result.get("face_detection_confidence"),
                        face_bbox_json=json.dumps(face_embedding_result.get("face_bbox", {})),
                        photo_url=primary_photo_url,
                        photo_verification_level=profile_row.get("photo_verification_level"),
                        is_primary_face=True,
                    )
        except Exception:
            # 人脸向量提取失败不影响主流程
            pass

        # 新增：AI颜值评分和AI口语化描述
        try:
            from .beauty_score_analyzer import analyze_beauty_score, generate_appearance_description

            primary_photo_url = None
            if photo_entries and len(photo_entries) > 0:
                primary_photo_url = photo_entries[0].get("photo_url") or photo_entries[0].get("photo_source")

            if primary_photo_url:
                # AI颜值评分
                beauty_result = analyze_beauty_score(primary_photo_url)
                if beauty_result and beauty_result.get("success"):
                    beauty_score = beauty_result.get("beauty_score", 0)
                    reasoning = beauty_result.get("reasoning", "")
                    saved = upsert_profile_photo_features(
                        source_dsn=source_dsn,
                        profile_id=normalized_profile_id,
                        table_name=table_name,
                        patch={
                            "beauty_score": round(float(beauty_score), 2),
                            "beauty_score_model": "claude-3-5-sonnet-20241022",
                            "beauty_score_reasoning": str(reasoning)[:500] if reasoning else None,
                        },
                    )

                # AI外貌描述
                description_result = generate_appearance_description(primary_photo_url)
                if description_result and description_result.get("success"):
                    appearance_keywords = description_result.get("appearance_keywords", [])
                    appearance_style_type = description_result.get("appearance_style_type", "neutral")
                    dominant_features = description_result.get("dominant_features", [])

                    saved = upsert_profile_photo_features(
                        source_dsn=source_dsn,
                        profile_id=normalized_profile_id,
                        table_name=table_name,
                        patch={
                            "appearance_keywords_json": [{"keyword": kw} for kw in appearance_keywords],
                            "appearance_style_type": appearance_style_type,
                            "dominant_features_json": [{"feature": f} for f in dominant_features],
                        },
                    )
        except Exception:
            # AI评分和描述失败不影响主流程
            pass

        # 原有逻辑：同步profile_face_side_tables
        try:
            _sync_profile_face_side_tables(
                source_dsn=source_dsn,
                profile_row=profile_row,
                photo_entries=photo_entries,
                feature_row=saved,
            )
        except Exception:
            pass
    index_sync: dict[str, Any] | None = None
    if sync_embedding and str(saved.get("analysis_status") or "").lower() == "done":
        try:
            embedding_out = _save_text_embedding(
                subject_id=normalized_profile_id,
                vector_type=APPEARANCE_PROFILE_VECTOR_TYPE,
                text=str(saved.get("appearance_summary") or "").strip(),
            )
        except Exception as exc:
            saved = upsert_profile_photo_features(
                source_dsn=source_dsn,
                profile_id=normalized_profile_id,
                table_name=table_name,
                patch={
                    "embedding_status": "failed",
                    "embedding_model": "text-embedding-v3",
                    "last_error": f"appearance_profile_embedding_failed:{str(exc)[:180]}",
                },
            )
        else:
            saved = upsert_profile_photo_features(
                source_dsn=source_dsn,
                profile_id=normalized_profile_id,
                table_name=table_name,
                patch={
                    "embedding_status": "done" if embedding_out.get("saved") else "failed",
                    "embedding_model": "text-embedding-v3",
                    "last_error": None if embedding_out.get("saved") else "appearance_profile_embedding_failed",
                },
            )
    if str(saved.get("analysis_status") or "").lower() == "done":
        index_sync = _sync_profile_vector_indexes(
            source_dsn=source_dsn,
            profile_id=normalized_profile_id,
        )
    _persist_photo_feature_version_snapshot(
        source_dsn=source_dsn,
        feature_row=saved,
        trigger_reason=(
            "analysis_completed"
            if str(saved.get("analysis_status") or "").lower() == "done"
            and str(saved.get("embedding_status") or "").lower() != "failed"
            else "embedding_failed"
            if str(saved.get("embedding_status") or "").lower() == "failed"
            else "analysis_failed"
        ),
    )
    if index_sync is not None:
        saved = {
            **saved,
            "index_sync": index_sync,
        }
    return saved


def refresh_profile_photo_features_from_record(
    *,
    source_dsn: str | None,
    record: dict[str, Any] | None,
    table_name: str = DEFAULT_PROFILE_PHOTO_FEATURES_TABLE,
    sync_embedding: bool = False,
) -> dict[str, Any]:
    normalized_record = dict(record or {})
    normalized_profile_id = int(normalized_record.get("id") or 0)
    if not source_dsn or normalized_profile_id <= 0:
        return {"saved": False, "error": "source_or_profile_missing"}
    existing_feature_row = load_candidate_photo_features(
        source_dsn=source_dsn,
        profile_ids=[normalized_profile_id],
        table_name=table_name,
    ).get(normalized_profile_id)
    processing_row = upsert_profile_photo_features(
        source_dsn=source_dsn,
        profile_id=normalized_profile_id,
        patch=PhotoAnalysisStateMachine.build_transition_patch(
            existing_feature_row,
            next_status="processing",
            embedding_status="pending",
            retry_count=PhotoAnalysisRetryQueue.current_retry_count(existing_feature_row),
        ),
        table_name=table_name,
    )
    photo_entries: list[dict[str, Any]] = []
    for value in list(normalized_record.get("photo_preview") or []):
        photo_url = str(value or "").strip()
        if photo_url:
            photo_entries.append({"photo_source": photo_url})
    avatar_url = str(normalized_record.get("avatar_url") or "").strip()
    if avatar_url and avatar_url not in {item["photo_source"] for item in photo_entries}:
        photo_entries.insert(0, {"photo_source": avatar_url})
    patch = build_photo_feature_patch(
        profile_row=normalized_record,
        photo_entries=photo_entries,
        existing_feature_row=processing_row,
    )
    saved = upsert_profile_photo_features(
        source_dsn=source_dsn,
        profile_id=normalized_profile_id,
        patch=_merge_analysis_patch(
            patch,
            PhotoAnalysisStateMachine.build_transition_patch(
                processing_row,
                next_status=str(patch.get("analysis_status") or "failed"),
                error_message=patch.get("last_error"),
                retry_count=PhotoAnalysisRetryQueue.current_retry_count(processing_row),
                embedding_status=patch.get("embedding_status"),
            ),
        ),
        table_name=table_name,
    )
    if str(saved.get("analysis_status") or "").lower() == "done":
        try:
            _sync_profile_face_side_tables(
                source_dsn=source_dsn,
                profile_row=normalized_record,
                photo_entries=photo_entries,
                feature_row=saved,
            )
        except Exception:
            pass
    index_sync: dict[str, Any] | None = None
    if sync_embedding and str(saved.get("analysis_status") or "").lower() == "done":
        try:
            embedding_out = _save_text_embedding(
                subject_id=normalized_profile_id,
                vector_type=APPEARANCE_PROFILE_VECTOR_TYPE,
                text=str(saved.get("appearance_summary") or "").strip(),
            )
        except Exception as exc:
            saved = upsert_profile_photo_features(
                source_dsn=source_dsn,
                profile_id=normalized_profile_id,
                table_name=table_name,
                patch={
                    "embedding_status": "failed",
                    "embedding_model": "text-embedding-v3",
                    "last_error": f"appearance_profile_embedding_failed:{str(exc)[:180]}",
                },
            )
            _persist_photo_feature_version_snapshot(
                source_dsn=source_dsn,
                feature_row=saved,
                trigger_reason="embedding_failed",
            )
            return saved
        saved = upsert_profile_photo_features(
            source_dsn=source_dsn,
            profile_id=normalized_profile_id,
            table_name=table_name,
            patch={
                "embedding_status": "done" if embedding_out.get("saved") else "failed",
                "embedding_model": "text-embedding-v3",
                "last_error": None if embedding_out.get("saved") else "appearance_profile_embedding_failed",
            },
        )
        index_sync = _sync_profile_vector_indexes(
            source_dsn=source_dsn,
            profile_id=normalized_profile_id,
        )
        _persist_photo_feature_version_snapshot(
            source_dsn=source_dsn,
            feature_row=saved,
            trigger_reason="analysis_completed" if embedding_out.get("saved") else "embedding_failed",
        )
        return {
            **saved,
            "index_sync": index_sync,
        }
    if str(saved.get("analysis_status") or "").lower() == "done":
        index_sync = _sync_profile_vector_indexes(
            source_dsn=source_dsn,
            profile_id=normalized_profile_id,
        )
    _persist_photo_feature_version_snapshot(
        source_dsn=source_dsn,
        feature_row=saved,
        trigger_reason="analysis_completed" if str(saved.get("analysis_status") or "").lower() == "done" else "analysis_failed",
    )
    if index_sync is not None:
        saved = {
            **saved,
            "index_sync": index_sync,
        }
    return saved


def backfill_profile_photo_features(
    *,
    source_dsn: str | None,
    profile_source_dsn: str | None = None,
    source_table_name: str | None = None,
    photos_table_name: str | None = None,
    where_clause: str = "",
    params: Iterable[Any] | None = None,
    batch_size: int = 200,
    limit: int | None = None,
    sync_embedding: bool = False,
    only_missing: bool = False,
    table_name: str = DEFAULT_PROFILE_PHOTO_FEATURES_TABLE,
) -> dict[str, Any]:
    if not source_dsn:
        return {"saved": False, "error": "source_not_configured"}
    profile_source = str(profile_source_dsn or source_dsn or "").strip()
    resolved_profile_source, resolved_table = resolve_profile_source(profile_source, source_table_name)
    if not resolved_profile_source or not resolved_table:
        return {"saved": False, "error": "profile_source_unresolved"}

    normalized_batch_size = max(1, int(batch_size or 200))
    normalized_limit = max(0, int(limit or 0))
    processed = 0
    saved = 0
    skipped = 0
    failed = 0
    errors: list[dict[str, Any]] = []

    for batch in iter_profile_batches(
        source_dsn=resolved_profile_source,
        source_table_name=resolved_table,
        where_clause=where_clause,
        params=tuple(params or ()),
        batch_size=normalized_batch_size,
    ):
        candidate_rows = [dict(row) for row in batch if isinstance(row, dict)]
        if only_missing and candidate_rows:
            existing_map = load_candidate_photo_features(
                source_dsn=source_dsn,
                profile_ids=[int(row.get("id") or 0) for row in candidate_rows],
                table_name=table_name,
            )
            candidate_rows = [
                row
                for row in candidate_rows
                if int(row.get("id") or 0) > 0 and int(row.get("id") or 0) not in existing_map
            ]
        for row in candidate_rows:
            profile_id = int(row.get("id") or 0)
            if profile_id <= 0:
                skipped += 1
                continue
            if normalized_limit and processed >= normalized_limit:
                return {
                    "saved": True,
                    "processed": processed,
                    "saved_count": saved,
                    "skipped_count": skipped,
                    "failed_count": failed,
                    "errors": errors,
                    "stopped_early": True,
                }
            try:
                result = refresh_profile_photo_features(
                    source_dsn=source_dsn,
                    profile_source_dsn=resolved_profile_source,
                    source_table_name=resolved_table,
                    photos_table_name=photos_table_name,
                    profile_id=profile_id,
                    table_name=table_name,
                    sync_embedding=sync_embedding,
                )
            except Exception as exc:
                failed += 1
                errors.append({"profile_id": profile_id, "error": str(exc)[:200]})
            else:
                if str(result.get("analysis_status") or "").lower() == "done":
                    saved += 1
                else:
                    skipped += 1
            processed += 1

    return {
        "saved": True,
        "processed": processed,
        "saved_count": saved,
        "skipped_count": skipped,
        "failed_count": failed,
        "errors": errors,
        "stopped_early": False,
    }


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


class FaceDetector:
    @staticmethod
    def detect(photo_entries: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        detections: list[dict[str, Any]] = []
        for index, source in enumerate(_normalize_photo_sources(list(photo_entries or []))):
            lowered = source.lower()
            confidence = 96.0
            if any(token in lowered for token in ("group", "multi", "party")):
                confidence = 68.0
            elif any(token in lowered for token in ("tiny", "far", "lowres")):
                confidence = 74.0
            detections.append(
                {
                    "photo_source": source,
                    "face_count": 2 if "group" in lowered or "multi" in lowered else 1,
                    "dominant_face_index": 0,
                    "detection_confidence": confidence,
                    "aligned": confidence >= 70.0,
                }
            )
        return detections


class FaceQualityAssessor:
    @staticmethod
    def score(detection: dict[str, Any] | None) -> float:
        item = dict(detection or {})
        confidence = _clamp_score(item.get("detection_confidence"), default=70.0)
        face_count = max(1, int(item.get("face_count") or 1))
        multi_face_penalty = 14.0 if face_count > 1 else 0.0
        aligned_bonus = 6.0 if bool(item.get("aligned")) else 0.0
        return round(max(0.0, min(100.0, confidence - multi_face_penalty + aligned_bonus)), 2)


class FaceEmbeddingExtractor:
    @staticmethod
    def extract(
        *,
        profile_id: int,
        photo_entries: list[dict[str, Any]] | None,
        dims: int = 16,
    ) -> dict[str, Any]:
        sources = _normalize_photo_sources(list(photo_entries or []))
        embedding = _deterministic_face_embedding(profile_id, sources, salt="face_embedding", dims=dims)
        return {
            "embedding_dim": len(embedding),
            "embedding_json": embedding,
            "extractor_version": "deterministic-face-embedding-v1",
        }


class PrimaryPhotoSelector:
    @staticmethod
    def select(
        photo_entries: list[dict[str, Any]] | None,
        detections: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        normalized_entries = [dict(item) for item in list(photo_entries or []) if isinstance(item, dict)]
        if not normalized_entries:
            return None
        detection_map = {
            str(item.get("photo_source") or "").strip(): dict(item)
            for item in list(detections or [])
            if isinstance(item, dict)
        }
        ranked = sorted(
            normalized_entries,
            key=lambda item: (
                FaceQualityAssessor.score(detection_map.get(str(item.get("photo_source") or "").strip())),
                1 if "avatar" in str(item.get("photo_source") or "").lower() else 0,
            ),
            reverse=True,
        )
        return ranked[0] if ranked else None


class PhotoQualityScorer:
    @staticmethod
    def score(
        *,
        profile_row: dict[str, Any] | None,
        photo_entries: list[dict[str, Any]] | None,
        detections: list[dict[str, Any]] | None = None,
    ) -> float:
        sources = _normalize_photo_sources(list(photo_entries or []))
        if not sources:
            return 0.0
        detection_map = {
            str(item.get("photo_source") or "").strip(): dict(item)
            for item in list(detections or [])
            if isinstance(item, dict)
        }
        detection_scores = [
            FaceQualityAssessor.score(detection_map.get(source))
            for source in sources
        ] or [55.0]
        verification_level = str(
            (profile_row or {}).get("photo_verification_level")
            or (profile_row or {}).get("verified_level")
            or ""
        ).strip().lower()
        verification_bonus = {
            "offline": 8.0,
            "id": 6.0,
            "photo": 4.0,
        }.get(verification_level, 0.0)
        return round(
            max(0.0, min(100.0, (sum(detection_scores) / len(detection_scores)) * 0.82 + len(sources) * 4.5 + verification_bonus)),
            2,
        )


class FacialAttributeScorer:
    @staticmethod
    def score(
        *,
        profile_row: dict[str, Any] | None,
        photo_entries: list[dict[str, Any]] | None,
    ) -> dict[str, float]:
        feature_patch = build_photo_feature_patch(
            profile_row=profile_row,
            photo_entries=list(photo_entries or []),
        )
        attributes = _build_face_attribute_patch(
            profile_row=profile_row,
            feature_row=feature_patch,
            photo_entries=photo_entries,
        )
        return {
            "eye_size_score": float(attributes.get("eye_size_score") or 0.0),
            "face_roundness_score": float(attributes.get("face_roundness_score") or 0.0),
            "jaw_definition_score": float(attributes.get("jaw_definition_score") or 0.0),
            "smile_intensity_score": float(attributes.get("smile_intensity_score") or 0.0),
            "skin_clarity_score": float(attributes.get("skin_clarity_score") or 0.0),
        }


class AppearanceStyleScorer:
    @staticmethod
    def score(
        *,
        profile_row: dict[str, Any] | None,
        photo_entries: list[dict[str, Any]] | None,
    ) -> dict[str, float]:
        patch = build_photo_feature_patch(
            profile_row=profile_row,
            photo_entries=list(photo_entries or []),
        )
        return {
            "clean_score": float(patch.get("clean_score") or 0.0),
            "gentle_score": float(patch.get("gentle_score") or 0.0),
            "sunny_score": float(patch.get("sunny_score") or 0.0),
            "stylish_score": float(patch.get("stylish_score") or 0.0),
            "mature_score": float(patch.get("mature_score") or 0.0),
        }


class YouthfulnessScorer:
    @staticmethod
    def score(attribute_scores: dict[str, Any] | None) -> float:
        attributes = dict(attribute_scores or {})
        eye_size = _clamp_score(attributes.get("eye_size_score"), default=50.0)
        roundness = _clamp_score(attributes.get("face_roundness_score"), default=50.0)
        skin_clarity = _clamp_score(attributes.get("skin_clarity_score"), default=50.0)
        smile = _clamp_score(attributes.get("smile_intensity_score"), default=50.0)
        return round(
            max(0.0, min(100.0, eye_size * 0.28 + roundness * 0.24 + skin_clarity * 0.28 + smile * 0.20)),
            2,
        )


class AppearanceTagExtractor:
    @staticmethod
    def extract(style_scores: dict[str, Any] | None, *, limit: int = 3) -> list[str]:
        return _top_dimension_labels(dict(style_scores or {}), limit=limit)


class AppearanceSummaryGenerator:
    @staticmethod
    def generate(
        *,
        style_scores: dict[str, Any] | None,
        attribute_scores: dict[str, Any] | None = None,
    ) -> str:
        style_labels = AppearanceTagExtractor.extract(style_scores, limit=3)
        attributes = dict(attribute_scores or {})
        youthfulness = YouthfulnessScorer.score(attributes)
        youth_text = "带一点幼态感" if youthfulness >= 65 else "更偏成熟利落"
        if len(style_labels) < 3:
            style_labels = (style_labels + ["顺眼", "自然", "干净"])[:3]
        return f"照片整体给人{style_labels[0]}的感觉，第一眼偏{style_labels[1]}，整体风格接近{style_labels[2]}，{youth_text}。"

def load_profile_photo_feature_versions(
    *,
    source_dsn: str | None,
    profile_id: int,
    limit: int = 20,
    table_name: str = DEFAULT_PROFILE_PHOTO_FEATURE_VERSIONS_TABLE,
) -> list[dict[str, Any]]:
    normalized_profile_id = int(profile_id or 0)
    if not source_dsn or normalized_profile_id <= 0:
        return []
    return list_profile_photo_feature_versions(
        source_dsn=source_dsn,
        profile_id=normalized_profile_id,
        limit=limit,
        table_name=table_name,
    )


def load_profile_face_attributes(
    *,
    source_dsn: str | None,
    profile_ids: Iterable[int],
    table_name: str = DEFAULT_PROFILE_FACE_ATTRIBUTES_TABLE,
) -> dict[int, dict[str, Any]]:
    normalized_ids = [int(profile_id) for profile_id in profile_ids if int(profile_id) > 0]
    if not source_dsn or not normalized_ids:
        return {}
    return list_profile_face_attributes(
        source_dsn=source_dsn,
        profile_ids=normalized_ids,
        table_name=table_name,
    )


def load_profile_face_embeddings(
    *,
    source_dsn: str | None,
    profile_ids: Iterable[int] | None = None,
    embedding_type: str | None = None,
    limit: int = 200,
    table_name: str = DEFAULT_PROFILE_FACE_EMBEDDINGS_TABLE,
) -> list[dict[str, Any]]:
    if not source_dsn:
        return []
    return list_profile_face_embeddings(
        source_dsn=source_dsn,
        profile_ids=list(profile_ids or []),
        embedding_type=embedding_type,
        limit=limit,
        table_name=table_name,
    )


def load_verified_face_anchors(
    *,
    source_dsn: str | None,
    profile_id: int,
    active_only: bool = True,
    limit: int = 5,
    table_name: str = DEFAULT_VERIFIED_FACE_ANCHORS_TABLE,
) -> list[dict[str, Any]]:
    normalized_profile_id = int(profile_id or 0)
    if not source_dsn or normalized_profile_id <= 0:
        return []
    return list_verified_face_anchors(
        source_dsn=source_dsn,
        profile_id=normalized_profile_id,
        active_only=active_only,
        limit=limit,
        table_name=table_name,
    )


def load_face_consistency_score(
    *,
    source_dsn: str | None,
    profile_id: int,
    table_name: str = DEFAULT_FACE_CONSISTENCY_SCORES_TABLE,
) -> dict[str, Any] | None:
    normalized_profile_id = int(profile_id or 0)
    if not source_dsn or normalized_profile_id <= 0:
        return None
    return get_face_consistency_score(
        source_dsn=source_dsn,
        profile_id=normalized_profile_id,
        table_name=table_name,
    )


def create_reference_face_search_job(
    *,
    source_dsn: str | None,
    requester_user_key: str,
    requester_profile_id: int | None = None,
    job_type: str = "face_similarity",
    input_source: str | None = None,
    filters: dict[str, Any] | None = None,
    result_profile_ids: Iterable[int] | None = None,
    status: str = "pending",
    table_name: str = DEFAULT_REFERENCE_FACE_SEARCH_JOBS_TABLE,
) -> dict[str, Any]:
    normalized_user_key = str(requester_user_key or "").strip()
    if not source_dsn or not normalized_user_key:
        return {"saved": False, "error": "source_or_user_missing"}
    normalized_results = [int(profile_id) for profile_id in list(result_profile_ids or []) if int(profile_id) > 0]
    embedding_json = _deterministic_face_embedding(
        int(requester_profile_id or 0),
        [str(input_source or "").strip()],
        salt="reference_search",
    )
    return insert_reference_face_search_job(
        source_dsn=source_dsn,
        requester_user_key=normalized_user_key,
        requester_profile_id=requester_profile_id,
        job_type=job_type,
        input_source=input_source,
        input_face_embedding_json=embedding_json,
        status=status,
        filters_json=filters,
        result_profile_ids_json=normalized_results,
        result_count=len(normalized_results),
        table_name=table_name,
    )


def retry_failed_profile_photo_features(
    *,
    source_dsn: str | None,
    profile_ids: Iterable[int] | None = None,
    profile_source_dsn: str | None = None,
    source_table_name: str | None = None,
    photos_table_name: str | None = None,
    limit: int = 100,
    max_retry_count: int = 3,
    sync_embedding: bool = False,
    table_name: str = DEFAULT_PROFILE_PHOTO_FEATURES_TABLE,
) -> dict[str, Any]:
    if not source_dsn:
        return {"saved": False, "error": "source_not_configured"}
    normalized_ids = [int(item) for item in list(profile_ids or []) if int(item) > 0]
    if normalized_ids:
        feature_rows = list(load_candidate_photo_features(
            source_dsn=source_dsn,
            profile_ids=normalized_ids,
            table_name=table_name,
        ).values())
    else:
        feature_rows = list_profile_photo_feature_rows(
            source_dsn=source_dsn,
            analysis_statuses=["failed"],
            limit=limit,
            table_name=table_name,
        )
    retried = 0
    exhausted = 0
    failed = 0
    results: list[dict[str, Any]] = []
    for feature_row in feature_rows[: max(1, int(limit or 100))]:
        profile_id = int(feature_row.get("profile_id") or 0)
        if profile_id <= 0:
            continue
        retry_patch = PhotoAnalysisRetryQueue.build_retry_patch(
            feature_row,
            max_retry_count=max_retry_count,
        )
        queued = upsert_profile_photo_features(
            source_dsn=source_dsn,
            profile_id=profile_id,
            patch=retry_patch,
            table_name=table_name,
        )
        if str(queued.get("analysis_status") or "").lower() != "retrying":
            exhausted += 1
            _persist_photo_feature_version_snapshot(
                source_dsn=source_dsn,
                feature_row=queued,
                trigger_reason="retry_exhausted",
            )
            results.append({"profile_id": profile_id, "status": "exhausted", "row": queued})
            continue
        refreshed = refresh_profile_photo_features(
            source_dsn=source_dsn,
            profile_id=profile_id,
            profile_source_dsn=profile_source_dsn,
            source_table_name=source_table_name,
            photos_table_name=photos_table_name,
            table_name=table_name,
            sync_embedding=sync_embedding,
        )
        if str(refreshed.get("analysis_status") or "").lower() == "done":
            retried += 1
        else:
            failed += 1
        results.append({"profile_id": profile_id, "status": str(refreshed.get("analysis_status") or ""), "row": refreshed})
    return {
        "saved": True,
        "processed": len(results),
        "retried_count": retried,
        "failed_count": failed,
        "exhausted_count": exhausted,
        "results": results,
    }


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
        event_weight=event_weight if event_weight is not None else _DEFAULT_EVENT_WEIGHTS.get(str(event_type or "").strip(), 0.0),
        scene=scene,
        session_id=session_id,
        metadata=metadata,
    )


def _build_preference_patch_from_weighted_rows(
    *,
    source_dsn: str,
    feature_rows: list[dict[str, Any]],
    user_key: str,
    profile_id: int | None,
    positive_sample_count: int,
    negative_sample_count: int,
    table_name: str,
) -> dict[str, Any]:
    numerator: dict[str, float] = {preference_key: 0.0 for _feature_key, preference_key in _PREFERENCE_DIMENSIONS}
    denominator: dict[str, float] = {preference_key: 0.0 for _feature_key, preference_key in _PREFERENCE_DIMENSIONS}
    positive_summaries: list[str] = []
    negative_summaries: list[str] = []
    for feature_row in feature_rows:
        signed_weight = float(feature_row.get("_event_weight") or 0.0)
        if signed_weight == 0:
            continue
        for feature_key, preference_key in _PREFERENCE_DIMENSIONS:
            raw_value = feature_row.get(feature_key)
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            numerator[preference_key] += (value - 50.0) * signed_weight
            denominator[preference_key] += abs(signed_weight)
        summary = str(feature_row.get("appearance_summary") or "").strip()
        if not summary:
            continue
        if signed_weight > 0 and summary not in positive_summaries:
            positive_summaries.append(summary)
        elif signed_weight < 0 and summary not in negative_summaries:
            negative_summaries.append(summary)
    patch: dict[str, Any] = {
        "positive_sample_count": int(positive_sample_count),
        "negative_sample_count": int(negative_sample_count),
        "preference_status": "done",
        "embedding_status": "pending",
        "last_feedback_at": None,
    }
    for _feature_key, preference_key in _PREFERENCE_DIMENSIONS:
        if denominator[preference_key] <= 0:
            continue
        patch[preference_key] = round(max(0.0, min(100.0, 50.0 + numerator[preference_key] / denominator[preference_key])), 2)
    summary_parts: list[str] = []
    if positive_summaries:
        summary_parts.append(f"更容易被这类风格吸引：{'；'.join(positive_summaries[:3])}")
    if negative_summaries:
        summary_parts.append(f"相对不偏好这类风格：{'；'.join(negative_summaries[:2])}")
    if summary_parts:
        patch["appearance_preference_summary"] = "。".join(summary_parts)
    return upsert_user_appearance_preference(
        source_dsn=source_dsn,
        table_name=table_name,
        user_key=user_key,
        profile_id=profile_id,
        patch=patch,
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
    weighted_rows: list[dict[str, Any]] = []
    for feature_row in candidate_feature_rows:
        if not isinstance(feature_row, dict):
            continue
        cloned = dict(feature_row)
        cloned["_event_weight"] = max(0.0, float(cloned.get("_event_weight") or 1.0))
        weighted_rows.append(cloned)
    saved = _build_preference_patch_from_weighted_rows(
        source_dsn=source_dsn,
        feature_rows=weighted_rows,
        user_key=user_key,
        profile_id=profile_id,
        positive_sample_count=positive_sample_count,
        negative_sample_count=negative_sample_count,
        table_name=table_name,
    )
    try:
        sync_user_appearance_preference_embedding(
            source_dsn=source_dsn,
            user_key=user_key,
            profile_id=profile_id,
            table_name=table_name,
        )
    except Exception:
        return saved
    return load_requester_appearance_preference(source_dsn=source_dsn, user_key=user_key) or saved


def rebuild_user_preference_from_history(
    *,
    source_dsn: str | None,
    user_key: str,
    profile_id: int | None,
    scene: str | None = None,
    event_limit: int = 200,
    now: datetime | None = None,
    table_name: str = DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE,
) -> dict[str, Any]:
    if not source_dsn:
        return {"saved": False, "error": "source_not_configured"}
    events = list_appearance_feedback_events(
        source_dsn=source_dsn,
        user_key=user_key,
        profile_id=profile_id,
        scene=scene,
        limit=event_limit,
    )
    if not events:
        return {"saved": False, "error": "no_feedback_events"}
    candidate_ids = sorted(
        {
            int(event.get("candidate_profile_id") or 0)
            for event in events
            if int(event.get("candidate_profile_id") or 0) > 0
        }
    )
    feature_map = load_candidate_photo_features(
        source_dsn=source_dsn,
        profile_ids=candidate_ids,
        table_name=DEFAULT_PROFILE_PHOTO_FEATURES_TABLE,
    )
    weighted_rows: list[dict[str, Any]] = []
    positive_sample_count = 0
    negative_sample_count = 0
    for event in events:
        candidate_id = int(event.get("candidate_profile_id") or 0)
        feature_row = feature_map.get(candidate_id)
        if not feature_row:
            continue
        event_type = str(event.get("event_type") or "").strip()
        signed_weight = _derive_event_weight(event)
        signed_weight *= _time_decay_multiplier(event.get("created_at"), now=now)
        if signed_weight == 0:
            continue
        cloned = dict(feature_row)
        cloned["_event_weight"] = signed_weight
        weighted_rows.append(cloned)
        if signed_weight > 0 or event_type in _POSITIVE_EVENT_TYPES:
            positive_sample_count += 1
        elif signed_weight < 0 or event_type in _NEGATIVE_EVENT_TYPES:
            negative_sample_count += 1
    if not weighted_rows:
        return {"saved": False, "error": "no_feature_rows_for_feedback"}
    saved = _build_preference_patch_from_weighted_rows(
        source_dsn=source_dsn,
        feature_rows=weighted_rows,
        user_key=user_key,
        profile_id=profile_id,
        positive_sample_count=positive_sample_count,
        negative_sample_count=negative_sample_count,
        table_name=table_name,
    )
    try:
        sync_user_appearance_preference_embedding(
            source_dsn=source_dsn,
            user_key=user_key,
            profile_id=profile_id,
            table_name=table_name,
        )
    except Exception:
        return saved
    return load_requester_appearance_preference(source_dsn=source_dsn, user_key=user_key) or saved


def backfill_user_appearance_preferences(
    *,
    source_dsn: str | None,
    user_keys: Iterable[str],
    scene: str | None = None,
    event_limit: int = 200,
) -> dict[str, Any]:
    if not source_dsn:
        return {"saved": False, "error": "source_not_configured"}
    normalized_user_keys = []
    seen_keys: set[str] = set()
    for value in user_keys:
        key = str(value or "").strip()
        if not key or key in seen_keys:
            continue
        normalized_user_keys.append(key)
        seen_keys.add(key)
    if not normalized_user_keys:
        return {"saved": False, "error": "no_user_keys"}

    processed = 0
    saved = 0
    failed = 0
    results: list[dict[str, Any]] = []
    for user_key in normalized_user_keys:
        try:
            result = rebuild_user_preference_from_history(
                source_dsn=source_dsn,
                user_key=user_key,
                profile_id=None,
                scene=scene,
                event_limit=event_limit,
            )
        except Exception as exc:
            failed += 1
            results.append({"user_key": user_key, "saved": False, "error": str(exc)[:200]})
        else:
            if result.get("saved") is False and result.get("error"):
                failed += 1
            else:
                saved += 1
            results.append({"user_key": user_key, **dict(result or {})})
        processed += 1
    return {
        "saved": True,
        "processed": processed,
        "saved_count": saved,
        "failed_count": failed,
        "results": results,
    }


def sync_user_appearance_preference_embedding(
    *,
    source_dsn: str | None,
    user_key: str,
    profile_id: int | None,
    table_name: str = DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE,
) -> dict[str, Any]:
    if not source_dsn:
        return {"saved": False, "error": "source_not_configured"}
    current = load_requester_appearance_preference(source_dsn=source_dsn, user_key=user_key)
    if not current:
        return {"saved": False, "error": "preference_missing"}
    subject_id = int(profile_id or current.get("profile_id") or 0)
    summary_text = str(current.get("appearance_preference_summary") or "").strip()
    if subject_id <= 0 or not summary_text:
        updated = upsert_user_appearance_preference(
            source_dsn=source_dsn,
            table_name=table_name,
            user_key=user_key,
            profile_id=profile_id,
            patch={"embedding_status": "failed", "last_error": "missing_profile_id_or_summary"},
        )
        return {"saved": False, "preference": updated}
    try:
        embedding_out = _save_text_embedding(
            subject_id=subject_id,
            vector_type=APPEARANCE_PREFERENCE_VECTOR_TYPE,
            text=summary_text,
        )
    except Exception as exc:
        updated = upsert_user_appearance_preference(
            source_dsn=source_dsn,
            table_name=table_name,
            user_key=user_key,
            profile_id=profile_id,
            patch={"embedding_status": "failed", "last_error": f"appearance_preference_embedding_failed:{str(exc)[:180]}"},
        )
        return {"saved": False, "preference": updated}
    updated = upsert_user_appearance_preference(
        source_dsn=source_dsn,
        table_name=table_name,
        user_key=user_key,
        profile_id=profile_id,
        patch={
            "embedding_status": "done" if embedding_out.get("saved") else "failed",
            "last_error": None if embedding_out.get("saved") else "appearance_preference_embedding_failed",
        },
    )
    return {"saved": bool(embedding_out.get("saved")), "preference": updated}


@dataclass(frozen=True)
class AppearanceInterestSignal:
    positive_signal: float
    negative_signal: float
    net_signal: float
    is_quick_bounce: bool
    detail_quality: str
    telemetry_weight: float


def compute_detail_duration_strength(detail_view_duration_ms: int | float | None) -> float:
    detail_ms = max(0.0, float(detail_view_duration_ms or 0.0))
    if 0.0 < detail_ms < 2000.0:
        return -2.0
    if detail_ms >= 10000.0:
        return 2.5
    if detail_ms >= 6000.0:
        return 1.8
    if detail_ms >= 3000.0:
        return 1.0
    if detail_ms >= 2000.0:
        return 0.4
    return 0.0


def classify_click_quality(
    *,
    detail_view_duration_ms: int | float | None = None,
    card_visible_duration_ms: int | float | None = None,
    photo_swipe_count: int | float | None = None,
    return_view_count: int | float | None = None,
    quick_bounce: bool | None = None,
) -> str:
    detail_ms = max(0.0, float(detail_view_duration_ms or 0.0))
    visible_ms = max(0.0, float(card_visible_duration_ms or 0.0))
    swipe_count = max(0.0, float(photo_swipe_count or 0.0))
    revisit_count = max(0.0, float(return_view_count or 0.0))
    if bool(quick_bounce) or (0.0 < detail_ms < 2000.0):
        return "low"
    if detail_ms >= 8000.0 or revisit_count > 0 or swipe_count >= 3:
        return "high"
    if detail_ms >= 3000.0 or visible_ms >= 1500.0 or swipe_count >= 1:
        return "medium"
    return "low"


def apply_click_quality_correction(
    *,
    base_event_weight: float,
    detail_view_duration_ms: int | float | None = None,
    card_visible_duration_ms: int | float | None = None,
    photo_swipe_count: int | float | None = None,
    return_view_count: int | float | None = None,
    quick_bounce: bool | None = None,
) -> float:
    quality = classify_click_quality(
        detail_view_duration_ms=detail_view_duration_ms,
        card_visible_duration_ms=card_visible_duration_ms,
        photo_swipe_count=photo_swipe_count,
        return_view_count=return_view_count,
        quick_bounce=quick_bounce,
    )
    duration_strength = compute_detail_duration_strength(detail_view_duration_ms)
    corrected = float(base_event_weight) + duration_strength
    if quality == "high":
        corrected += 1.5
    elif quality == "medium":
        corrected += 0.5
    else:
        corrected -= 1.0
    return round(corrected, 4)


def compute_appearance_interest_signal(
    *,
    event_weight: float = 0.0,
    detail_view_duration_ms: int | float | None = None,
    card_visible_duration_ms: int | float | None = None,
    photo_swipe_count: int | float | None = None,
    return_view_count: int | float | None = None,
    quick_bounce: bool | None = None,
) -> AppearanceInterestSignal:
    detail_ms = max(0.0, float(detail_view_duration_ms or 0.0))
    visible_ms = max(0.0, float(card_visible_duration_ms or 0.0))
    swipe_count = max(0.0, float(photo_swipe_count or 0.0))
    revisit_count = max(0.0, float(return_view_count or 0.0))
    resolved_quick_bounce = bool(quick_bounce) or (0.0 < detail_ms < 2000.0)

    telemetry_weight = compute_detail_duration_strength(detail_ms)
    if visible_ms >= 1200.0:
        telemetry_weight += min(1.5, visible_ms / 4000.0)
    if swipe_count > 0:
        telemetry_weight += min(1.2, swipe_count * 0.35)
    if revisit_count > 0:
        telemetry_weight += min(1.5, revisit_count * 0.75)
    detail_quality = classify_click_quality(
        detail_view_duration_ms=detail_ms,
        card_visible_duration_ms=visible_ms,
        photo_swipe_count=swipe_count,
        return_view_count=revisit_count,
        quick_bounce=resolved_quick_bounce,
    )
    total = apply_click_quality_correction(
        base_event_weight=float(event_weight) + telemetry_weight,
        detail_view_duration_ms=detail_ms,
        card_visible_duration_ms=visible_ms,
        photo_swipe_count=swipe_count,
        return_view_count=revisit_count,
        quick_bounce=resolved_quick_bounce,
    )
    telemetry_weight = round(total - float(event_weight), 4)

    return AppearanceInterestSignal(
        positive_signal=max(0.0, round(total, 4)),
        negative_signal=max(0.0, round(-total, 4)),
        net_signal=round(total, 4),
        is_quick_bounce=resolved_quick_bounce,
        detail_quality=detail_quality,
        telemetry_weight=round(telemetry_weight, 4),
    )


def _derive_event_weight(event: dict[str, Any]) -> float:
    event_type = str(event.get("event_type") or "").strip()
    metadata = dict(event.get("metadata") or {})
    base_weight = float(event.get("event_weight") or _DEFAULT_EVENT_WEIGHTS.get(event_type, 0.0))
    if event_type == "engagement_metrics":
        signal = compute_appearance_interest_signal(
            event_weight=0.0,
            detail_view_duration_ms=metadata.get("detail_view_duration_ms"),
            card_visible_duration_ms=metadata.get("card_visible_duration_ms"),
            photo_swipe_count=metadata.get("photo_swipe_count"),
            return_view_count=metadata.get("return_view_count"),
            quick_bounce=metadata.get("quick_bounce"),
        )
        return signal.net_signal
    if event_type == "detail_view":
        return apply_click_quality_correction(
            base_event_weight=base_weight,
            detail_view_duration_ms=metadata.get("detail_view_duration_ms"),
            card_visible_duration_ms=metadata.get("card_visible_duration_ms"),
            photo_swipe_count=metadata.get("photo_swipe_count"),
            return_view_count=metadata.get("return_view_count"),
            quick_bounce=metadata.get("quick_bounce"),
        )
    return base_weight


__all__ = [
    "APPEARANCE_PREFERENCE_VECTOR_TYPE",
    "APPEARANCE_PROFILE_VECTOR_TYPE",
    "DEFAULT_APPEARANCE_FEEDBACK_EVENTS_TABLE",
    "DEFAULT_PROFILE_PHOTO_FEATURES_TABLE",
    "DEFAULT_USER_APPEARANCE_PREFERENCES_TABLE",
    "AppearanceInterestSignal",
    "AppearanceStyleScorer",
    "AppearanceSummaryGenerator",
    "AppearanceTagExtractor",
    "AppearanceWeightStrategy",
    "EnvironmentGapAssessment",
    "EnvironmentGapCompensator",
    "FaceDetector",
    "FaceEmbeddingExtractor",
    "FaceConsistencyResult",
    "FaceConsistencyScorer",
    "FaceQualityAssessor",
    "FacialAttributeScorer",
    "GlobalAppearanceScorer",
    "PhotoBonusBreakdown",
    "PhotoAnalysisRetryQueue",
    "PhotoAnalysisStateMachine",
    "PhotoFeatureVersionManager",
    "PhotoQualityScorer",
    "PrimaryPhotoSelector",
    "ProfilePhotoTrustScore",
    "ProfilePhotoTrustScorer",
    "RiskPenaltyBreakdown",
    "RiskPenaltyCalculator",
    "TrustBonusBreakdown",
    "TrustBonusCalculator",
    "YouthfulnessScorer",
    "VerifiedFaceAnchorWriter",
    "VerifiedPhotoQualityScore",
    "VerifiedPhotoQualityScorer",
    "backfill_profile_photo_features",
    "build_appearance_explanation",
    "build_match_explanation_payload",
    "build_photo_feature_patch",
    "calibrate_global_appearance_score",
    "create_reference_face_search_job",
    "compute_appearance_interest_signal",
    "compute_photo_bonus_breakdown",
    "compute_risk_penalty_breakdown",
    "compute_trust_bonus_breakdown",
    "generate_photo_risk_flags",
    "load_candidate_photo_features",
    "load_face_consistency_score",
    "load_profile_face_attributes",
    "load_profile_face_embeddings",
    "load_profile_photo_feature_versions",
    "load_requester_appearance_preference",
    "load_verified_face_anchors",
    "backfill_user_appearance_preferences",
    "record_feedback_event",
    "rebuild_user_preference_from_events",
    "rebuild_user_preference_from_history",
    "refresh_profile_photo_features",
    "refresh_profile_photo_features_from_record",
    "retry_failed_profile_photo_features",
    "resolve_appearance_weight_strategy",
    "resolve_global_bonus_multiplier",
    "resolve_preference_weight_multiplier",
    "sync_user_appearance_preference_embedding",
]
