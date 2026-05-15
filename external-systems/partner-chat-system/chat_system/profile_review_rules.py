"""Rule builders and severity reducers for profile review workflows."""

from __future__ import annotations

import re
from typing import Any

from her_time_utils import as_text as _as_text, unique_ordered_texts as _unique_ordered

SEVERITY_LOW = "low"
SEVERITY_MEDIUM = "medium"
SEVERITY_HIGH = "high"

ACTION_LIMITED_EXPOSURE = "limited_exposure"
ACTION_REQUIRE_VERIFICATION = "require_verification"

LOW_WAGE_JOB_KEYWORDS = ("助理", "文员", "行政", "客服", "店员", "实习")
HIGH_INCOME_CITY_MISMATCH = {
    "镇江",
    "扬州",
    "湖州",
    "嘉兴",
    "南通",
    "常州",
    "无锡",
}


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_income_max_wan(value: Any) -> int | None:
    text = _as_text(value)
    if not text:
        return None
    matches = [int(item) for item in re.findall(r"(\d+)", text)]
    if not matches:
        return None
    if "+" in text:
        return matches[0]
    return max(matches)


def photo_review_signal_codes_for_hits(hits: list[dict[str, Any]]) -> list[str]:
    signal_codes: list[str] = []
    for hit in hits:
        signal_codes.extend(list(hit.get("signal_codes") or []))
    return _unique_ordered(signal_codes)


def build_profile_photo_rule_hits(photo_review: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(photo_review, dict) or photo_review.get("analysis_status") != "ok":
        return []

    hits: list[dict[str, Any]] = []
    same_person_score = _as_int(photo_review.get("same_person_score")) or 0
    photo_edit_risk_score = _as_int(photo_review.get("photo_edit_risk_score")) or 0
    deepfake_risk_score = _as_int(photo_review.get("deepfake_risk_score")) or 0
    stolen_media_risk_score = _as_int(photo_review.get("stolen_media_risk_score")) or 0
    risk_flags = set(photo_review.get("risk_flags") or [])

    if "mixed_identity_photos" in risk_flags or same_person_score < 45:
        hits.append(
            {
                "rule_code": "profile_photo_identity_mismatch",
                "severity": SEVERITY_HIGH,
                "evidence": {
                    "same_person_score": same_person_score,
                    "same_person_pair_count": photo_review.get("same_person_pair_count"),
                    "same_person_average_similarity": photo_review.get("same_person_average_similarity"),
                    "same_person_min_similarity": photo_review.get("same_person_min_similarity"),
                    "summary": "资料照之间像是混入了不同的人，不像同一个人整组上传。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["photo_mismatch", "identity_mismatch"],
            }
        )
    elif "same_person_uncertain" in risk_flags or same_person_score < 70:
        hits.append(
            {
                "rule_code": "profile_photo_identity_uncertain",
                "severity": SEVERITY_MEDIUM,
                "evidence": {
                    "same_person_score": same_person_score,
                    "same_person_pair_count": photo_review.get("same_person_pair_count"),
                    "summary": "资料照之间的人脸一致性不稳定，需要补录活体进一步确认。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["photo_mismatch"],
            }
        )

    if "stolen_media_risk" in risk_flags or stolen_media_risk_score >= 85:
        hits.append(
            {
                "rule_code": "profile_photo_stolen_media_risk",
                "severity": SEVERITY_HIGH,
                "evidence": {
                    "stolen_media_risk_score": stolen_media_risk_score,
                    "cross_profile_duplicate_count": photo_review.get("cross_profile_duplicate_count"),
                    "exact_cross_profile_duplicate_count": photo_review.get("exact_cross_profile_duplicate_count"),
                    "summary": "资料照和别的资料高度重复，疑似盗图或多人复用。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["suspected_fake_photo"],
            }
        )
    elif "duplicate_profile_photo" in risk_flags or stolen_media_risk_score >= 60:
        hits.append(
            {
                "rule_code": "profile_photo_duplicate_uncertain",
                "severity": SEVERITY_MEDIUM,
                "evidence": {
                    "stolen_media_risk_score": stolen_media_risk_score,
                    "duplicate_photo_count": photo_review.get("duplicate_photo_count"),
                    "cross_profile_duplicate_count": photo_review.get("cross_profile_duplicate_count"),
                    "summary": "资料照存在重复或近似重复信号，需要进一步确认来源。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["suspected_fake_photo"],
            }
        )

    if "deepfake_risk" in risk_flags or deepfake_risk_score >= 85:
        hits.append(
            {
                "rule_code": "profile_photo_deepfake_risk",
                "severity": SEVERITY_HIGH,
                "evidence": {
                    "deepfake_risk_score": deepfake_risk_score,
                    "deepfake_artifact_score": photo_review.get("deepfake_artifact_score"),
                    "deepfake_consistency_score": photo_review.get("deepfake_consistency_score"),
                    "summary": "资料照存在明显 AI 生成或换脸痕迹，不能直接放行。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["suspected_fake_photo", "identity_mismatch"],
            }
        )
    elif "deepfake_uncertain" in risk_flags or deepfake_risk_score >= 60:
        hits.append(
            {
                "rule_code": "profile_photo_deepfake_uncertain",
                "severity": SEVERITY_MEDIUM,
                "evidence": {
                    "deepfake_risk_score": deepfake_risk_score,
                    "deepfake_artifact_score": photo_review.get("deepfake_artifact_score"),
                    "summary": "资料照存在可疑的生成/换脸痕迹，需要补录真人活体验证。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["suspected_fake_photo"],
            }
        )

    if "photo_heavily_edited" in risk_flags or photo_edit_risk_score >= 85:
        hits.append(
            {
                "rule_code": "profile_photo_heavily_edited",
                "severity": SEVERITY_MEDIUM,
                "evidence": {
                    "photo_edit_risk_score": photo_edit_risk_score,
                    "skin_smoothing_risk_score": photo_review.get("skin_smoothing_risk_score"),
                    "beauty_filter_risk_score": photo_review.get("beauty_filter_risk_score"),
                    "face_shape_delta_score": photo_review.get("face_shape_delta_score"),
                    "summary": "资料照修图太重，和自然真人状态差距过大。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["photo_heavily_edited"],
            }
        )
    elif "photo_edit_uncertain" in risk_flags or photo_edit_risk_score >= 60:
        hits.append(
            {
                "rule_code": "profile_photo_edit_uncertain",
                "severity": SEVERITY_LOW,
                "evidence": {
                    "photo_edit_risk_score": photo_edit_risk_score,
                    "edited_photo_count": photo_review.get("edited_photo_count"),
                    "summary": "资料照存在明显美颜/磨皮信号，建议补录真人活体做交叉确认。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["photo_heavily_edited"],
            }
        )

    if "multiple_faces_in_profile_photos" in risk_flags:
        hits.append(
            {
                "rule_code": "profile_photo_multiple_faces",
                "severity": SEVERITY_LOW,
                "evidence": {
                    "multiple_face_photo_count": photo_review.get("multiple_face_photo_count"),
                    "summary": "资料照里出现多人脸，主体验证不够干净。",
                },
                "required_verifications": ["live_video"],
                "signal_codes": ["suspected_fake_photo"],
            }
        )

    return hits


def build_profile_rule_hits(profile: dict[str, Any]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    income_max = _parse_income_max_wan(profile.get("income_range"))
    job_text = _as_text(profile.get("job"))
    city = _as_text(profile.get("city"))
    if income_max is not None and income_max >= 80 and any(keyword in job_text for keyword in LOW_WAGE_JOB_KEYWORDS):
        hits.append(
            {
                "rule_code": "income_job_mismatch",
                "severity": SEVERITY_HIGH if income_max >= 120 else SEVERITY_MEDIUM,
                "evidence": {
                    "income_range": profile.get("income_range"),
                    "job": profile.get("job"),
                    "summary": "高收入声明与岗位类型存在明显落差",
                },
                "required_verifications": ["income", "job"],
            }
        )
    if income_max is not None and income_max >= 120 and city in HIGH_INCOME_CITY_MISMATCH:
        hits.append(
            {
                "rule_code": "income_city_mismatch",
                "severity": SEVERITY_MEDIUM,
                "evidence": {
                    "income_range": profile.get("income_range"),
                    "city": profile.get("city"),
                    "summary": "高收入声明与城市常见收入分布存在明显落差",
                },
                "required_verifications": ["income"],
            }
        )
    frequent_changes: dict[str, int] = {}
    for field_key in ("job_change_count_30d", "income_change_count_30d", "city_change_count_30d"):
        count = _as_int(profile.get(field_key))
        if count is not None and count >= 2:
            frequent_changes[field_key] = count
    if frequent_changes:
        hits.append(
            {
                "rule_code": "frequent_profile_changes",
                "severity": SEVERITY_MEDIUM if len(frequent_changes) >= 2 else SEVERITY_LOW,
                "evidence": {
                    "changes": frequent_changes,
                    "summary": "近 30 天关键信息修改频繁",
                },
                "required_verifications": ["job", "income"],
            }
        )
    return hits


def profile_review_action_for_hits(hits: list[dict[str, Any]]) -> str:
    if any(hit["severity"] == SEVERITY_HIGH for hit in hits) or len(hits) >= 2:
        return ACTION_LIMITED_EXPOSURE
    return ACTION_REQUIRE_VERIFICATION


def profile_review_severity_for_hits(hits: list[dict[str, Any]]) -> str:
    if any(hit["severity"] == SEVERITY_HIGH for hit in hits):
        return SEVERITY_HIGH
    if any(hit["severity"] == SEVERITY_MEDIUM for hit in hits):
        return SEVERITY_MEDIUM
    return SEVERITY_LOW


__all__ = [
    "build_profile_photo_rule_hits",
    "build_profile_rule_hits",
    "photo_review_signal_codes_for_hits",
    "profile_review_action_for_hits",
    "profile_review_severity_for_hits",
]
