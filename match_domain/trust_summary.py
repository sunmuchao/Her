"""TrustSummary read model for profile / candidate presentation (§13.1.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from .support_contracts import TrustSummary

_VERIFIED_LEVEL_LABELS = {
    "basic": "基础认证",
    "photo": "照片认证",
    "id": "实名认证",
    "offline": "线下核验",
}

_PHOTO_LEVEL_LABELS = {
    "uploaded": "普通上传照片",
    "human_verified": "真人照片认证",
    "live_video_verified": "活体自拍视频认证",
    "offline_verified": "线下核验照片",
}

_FIELD_VERIFICATION_COLUMNS = {
    "education": "education_verification_status",
    "job": "job_verification_status",
    "income": "income_verification_status",
}


def build_trust_summary(
    profile: Mapping[str, Any],
    *,
    payload: Mapping[str, Any] | None = None,
    updated_at: datetime | None = None,
) -> TrustSummary:
    profile_id = int(profile.get("id") or profile.get("profile_id") or 0)
    payload = payload or {}
    existing = payload.get("trust_summary") if isinstance(payload.get("trust_summary"), Mapping) else {}

    verified_level = str(
        profile.get("verified_level")
        or existing.get("verified_level")
        or ""
    ).strip().lower() or None

    photo_level = str(
        payload.get("photo_verification_level")
        or existing.get("photo_verification_level")
        or profile.get("photo_verification_level")
        or ""
    ).strip().lower() or None

    labels: list[str] = []
    for key in ("verified_label", "photo_verification_label"):
        value = payload.get(key) or existing.get(key)
        if value:
            labels.append(str(value))

    verified_label = (
        str(payload.get("verified_label") or existing.get("verified_label") or "")
        or _VERIFIED_LEVEL_LABELS.get(verified_level or "", "")
        or None
    )
    photo_label = (
        str(payload.get("photo_verification_label") or existing.get("photo_verification_label") or "")
        or _PHOTO_LEVEL_LABELS.get(photo_level or "", "")
        or None
    )
    if verified_label and verified_label not in labels:
        labels.append(verified_label)
    if photo_label and photo_label not in labels:
        labels.append(photo_label)

    field_verifications: dict[str, str] = {}
    for field_name, column in _FIELD_VERIFICATION_COLUMNS.items():
        value = profile.get(column) or payload.get(column) or existing.get("field_verifications", {}).get(field_name)
        if value not in {None, ""}:
            field_verifications[field_name] = str(value)

    headline = (
        str(payload.get("trust_headline") or existing.get("headline") or "")
        or verified_label
        or photo_label
        or None
    )

    if profile.get("live_video_verified"):
        if "活体自拍视频认证" not in labels:
            labels.append("活体自拍视频认证")

    return TrustSummary(
        profile_id=profile_id,
        verified_level=verified_level,
        labels=labels,
        field_verifications=field_verifications,
        verified_label=verified_label,
        photo_verification_label=photo_label,
        headline=headline,
        updated_at=updated_at,
    )


__all__ = ["build_trust_summary"]
