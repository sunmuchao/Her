"""Photo-derived matching features and user appearance preferences."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

from profile_service import (
    get_profile,
    iter_profile_batches,
    list_appearance_feedback_events,
    list_profile_photos,
    list_profile_photo_features,
    load_user_appearance_preference,
    record_appearance_feedback_event,
    resolve_profile_source,
    upsert_profile_photo_features,
    upsert_user_appearance_preference,
)


DEFAULT_PROFILE_PHOTO_FEATURES_TABLE = "profile_photo_features"
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


def resolve_preference_weight_multiplier(user_appearance_preference: dict[str, Any] | None) -> float:
    preference_row = dict(user_appearance_preference or {})
    positive_count = max(0, int(_safe_float(preference_row.get("positive_sample_count"), default=0.0)))
    negative_count = max(0, int(_safe_float(preference_row.get("negative_sample_count"), default=0.0)))
    total_count = positive_count + negative_count
    if total_count <= 0:
        return 1.0
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
    global_bonus = _score_to_bonus(
        GlobalAppearanceScorer.score(feature_row),
        max_bonus=15.0,
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


class GlobalAppearanceScorer:
    @staticmethod
    def score(candidate_photo_features: dict[str, Any] | None) -> float:
        feature_row = dict(candidate_photo_features or {})
        if feature_row.get("appearance_score_global") not in (None, ""):
            return round(_clamp_score(feature_row.get("appearance_score_global"), default=0.0), 2)
        quality_score = _clamp_score(feature_row.get("photo_quality_score"), default=50.0)
        authenticity_score = _clamp_score(feature_row.get("photo_authenticity_score"), default=50.0)
        face_score = _clamp_score(feature_row.get("face_score_global"), default=50.0)
        return round((quality_score * 0.22) + (authenticity_score * 0.18) + (face_score * 0.60), 2)


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
    primary_entry = normalized_entries[0]
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
    quality_score = min(100.0, 48.0 + photo_count * 6.0 + verification_bonus * 0.7 + _stable_bucket(source_seed, salt="quality", lower=0, upper=16))
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
    appearance_summary = f"照片整体给人{top_labels[0]}的感觉，第一眼偏{top_labels[1]}，整体风格接近{top_labels[2]}。"
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
    profile_source = str(profile_source_dsn or source_dsn or "").strip()
    resolved_profile_source, resolved_table = resolve_profile_source(profile_source, source_table_name)
    if not resolved_profile_source or not resolved_table:
        return {"saved": False, "error": "profile_source_unresolved"}
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
    existing_feature_row = load_candidate_photo_features(
        source_dsn=source_dsn,
        profile_ids=[normalized_profile_id],
        table_name=table_name,
    ).get(normalized_profile_id)
    patch = build_photo_feature_patch(
        profile_row=profile_row,
        photo_entries=photo_entries,
        existing_feature_row=existing_feature_row,
    )
    saved = upsert_profile_photo_features(
        source_dsn=source_dsn,
        profile_id=normalized_profile_id,
        patch=patch,
        table_name=table_name,
    )
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
    photo_entries: list[dict[str, Any]] = []
    for value in list(normalized_record.get("photo_preview") or []):
        photo_url = str(value or "").strip()
        if photo_url:
            photo_entries.append({"photo_source": photo_url})
    avatar_url = str(normalized_record.get("avatar_url") or "").strip()
    if avatar_url and avatar_url not in {item["photo_source"] for item in photo_entries}:
        photo_entries.insert(0, {"photo_source": avatar_url})
    existing_feature_row = load_candidate_photo_features(
        source_dsn=source_dsn,
        profile_ids=[normalized_profile_id],
        table_name=table_name,
    ).get(normalized_profile_id)
    patch = build_photo_feature_patch(
        profile_row=normalized_record,
        photo_entries=photo_entries,
        existing_feature_row=existing_feature_row,
    )
    saved = upsert_profile_photo_features(
        source_dsn=source_dsn,
        profile_id=normalized_profile_id,
        patch=patch,
        table_name=table_name,
    )
    if sync_embedding and str(saved.get("analysis_status") or "").lower() == "done":
        try:
            embedding_out = _save_text_embedding(
                subject_id=normalized_profile_id,
                vector_type=APPEARANCE_PROFILE_VECTOR_TYPE,
                text=str(saved.get("appearance_summary") or "").strip(),
            )
        except Exception as exc:
            return upsert_profile_photo_features(
                source_dsn=source_dsn,
                profile_id=normalized_profile_id,
                table_name=table_name,
                patch={
                    "embedding_status": "failed",
                    "embedding_model": "text-embedding-v3",
                    "last_error": f"appearance_profile_embedding_failed:{str(exc)[:180]}",
                },
            )
        return upsert_profile_photo_features(
            source_dsn=source_dsn,
            profile_id=normalized_profile_id,
            table_name=table_name,
            patch={
                "embedding_status": "done" if embedding_out.get("saved") else "failed",
                "embedding_model": "text-embedding-v3",
                "last_error": None if embedding_out.get("saved") else "appearance_profile_embedding_failed",
            },
        )
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
    "GlobalAppearanceScorer",
    "PhotoBonusBreakdown",
    "RiskPenaltyBreakdown",
    "RiskPenaltyCalculator",
    "TrustBonusBreakdown",
    "TrustBonusCalculator",
    "backfill_profile_photo_features",
    "build_appearance_explanation",
    "build_photo_feature_patch",
    "compute_appearance_interest_signal",
    "compute_photo_bonus_breakdown",
    "compute_risk_penalty_breakdown",
    "compute_trust_bonus_breakdown",
    "load_candidate_photo_features",
    "load_requester_appearance_preference",
    "backfill_user_appearance_preferences",
    "record_feedback_event",
    "rebuild_user_preference_from_events",
    "rebuild_user_preference_from_history",
    "refresh_profile_photo_features",
    "refresh_profile_photo_features_from_record",
    "resolve_preference_weight_multiplier",
    "sync_user_appearance_preference_embedding",
]
