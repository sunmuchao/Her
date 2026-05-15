"""Helpers for photo review verification workflow metadata and notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from her_time_utils import as_text as _as_text, unique_ordered_texts as _unique_ordered

PHOTO_REVIEW_METADATA_KEY = "photo_review_task"
WORKFLOW_HISTORY_METADATA_KEY = "workflow_history"
NOTIFICATION_TYPE_REQUESTED = "photo_review_requested"
NOTIFICATION_TYPE_RESUBMISSION_REQUIRED = "photo_review_resubmission_required"
NOTIFICATION_TYPE_APPROVED = "photo_review_approved"
NOTIFICATION_TYPE_REJECTED = "photo_review_rejected"
NOTIFICATION_TYPE_FROZEN = "photo_review_frozen"
NOTIFICATION_TYPE_CLOSED = "photo_review_closed"
PHOTO_REVIEW_SIGNAL_CODES = {
    "photo_mismatch",
    "suspected_fake_photo",
    "photo_heavily_edited",
    "identity_mismatch",
}


def _normalize_metadata(metadata: Any) -> dict[str, Any]:
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}


def is_photo_review_signal_list(signal_codes: list[str] | None) -> bool:
    return any(code in PHOTO_REVIEW_SIGNAL_CODES for code in list(signal_codes or []))


def _photo_review_reason_labels(signal_codes: list[str] | None) -> list[str]:
    codes = set(signal_codes or [])
    labels: list[str] = []
    if "suspected_fake_photo" in codes or "photo_mismatch" in codes:
        labels.append("照片与真人不符")
    if "photo_heavily_edited" in codes:
        labels.append("疑似过度修图")
    if "identity_mismatch" in codes:
        labels.append("疑似非本人")
    if not labels and codes:
        labels.append("照片真实性待复核")
    return labels


def _default_photo_review_capture_tips() -> list[str]:
    return [
        "请录制 5-10 秒无遮挡真人视频，正脸清晰可见。",
        "请在自然光或均匀光线下拍摄，避免强滤镜、美颜和过暗环境。",
        "请按提示完成眨眼、张嘴、转头等动作，确保平台能完成活体核验。",
    ]


def _iso_datetime_or_none(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat(sep=" ")
    text = _as_text(value)
    return text or None


def build_photo_review_task_metadata(
    *,
    request_source: str,
    signal_codes: list[str] | None,
    request_reason: str | None,
    requested_by: str | None,
    risk_case_ids: list[str] | None,
    report_ids: list[int] | None,
    due_at: datetime | None,
    now: datetime,
) -> dict[str, Any]:
    labels = _photo_review_reason_labels(signal_codes)
    summary = _as_text(request_reason)
    if not summary:
        if labels:
            summary = f"平台检测到你的资料存在{labels[0]}等信号，请补录真人活体视频完成复核。"
        else:
            summary = "平台检测到你的资料照片存在待复核信号，请补录真人活体视频。"
    return {
        "task_kind": "photo_review",
        "request_source": _as_text(request_source) or "risk_case_review",
        "request_title": "请补录真人活体视频",
        "request_reason": summary,
        "reason_labels": labels,
        "request_reason_codes": _unique_ordered(signal_codes),
        "linked_risk_case_ids": _unique_ordered(risk_case_ids),
        "linked_report_ids": [int(item) for item in list(report_ids or []) if str(item).strip()],
        "capture_tips": _default_photo_review_capture_tips(),
        "requested_at": now.isoformat(sep=" "),
        "requested_by": _as_text(requested_by) or None,
        "due_at": _iso_datetime_or_none(due_at),
    }


def merge_photo_review_task_metadata(
    current_task: dict[str, Any] | None,
    *,
    request_source: str,
    signal_codes: list[str] | None,
    request_reason: str | None,
    requested_by: str | None,
    risk_case_ids: list[str] | None,
    report_ids: list[int] | None,
    due_at: datetime | None,
    now: datetime,
) -> dict[str, Any]:
    base = _normalize_metadata(current_task)
    incoming = build_photo_review_task_metadata(
        request_source=request_source,
        signal_codes=signal_codes,
        request_reason=request_reason,
        requested_by=requested_by,
        risk_case_ids=risk_case_ids,
        report_ids=report_ids,
        due_at=due_at,
        now=now,
    )
    merged = {**base, **incoming}
    merged["reason_labels"] = _unique_ordered(list(base.get("reason_labels") or []) + list(incoming.get("reason_labels") or []))
    merged["request_reason_codes"] = _unique_ordered(
        list(base.get("request_reason_codes") or []) + list(incoming.get("request_reason_codes") or [])
    )
    merged["linked_risk_case_ids"] = _unique_ordered(
        list(base.get("linked_risk_case_ids") or []) + list(incoming.get("linked_risk_case_ids") or [])
    )
    merged["linked_report_ids"] = [
        int(item)
        for item in _unique_ordered(list(base.get("linked_report_ids") or []) + list(incoming.get("linked_report_ids") or []))
    ]
    if not _as_text(merged.get("request_reason")):
        merged["request_reason"] = incoming["request_reason"]
    if not _as_text(merged.get("request_title")):
        merged["request_title"] = incoming["request_title"]
    if not merged.get("capture_tips"):
        merged["capture_tips"] = incoming["capture_tips"]
    merged["last_updated_at"] = now.isoformat(sep=" ")
    return merged


def append_workflow_history(
    metadata: dict[str, Any],
    *,
    event_type: str,
    occurred_at: datetime,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    merged = _normalize_metadata(metadata)
    history = list(merged.get(WORKFLOW_HISTORY_METADATA_KEY) or [])
    history.append(
        {
            "event_type": _as_text(event_type),
            "occurred_at": occurred_at.isoformat(sep=" "),
            "payload": _normalize_metadata(payload),
        }
    )
    merged[WORKFLOW_HISTORY_METADATA_KEY] = history[-30:]
    return merged


def photo_review_notification_copy(
    notification_type: str,
    submission: dict[str, Any] | None,
    *,
    note: str | None = None,
) -> tuple[str, str]:
    task = _normalize_metadata((submission or {}).get(PHOTO_REVIEW_METADATA_KEY))
    reason = _as_text(task.get("request_reason")) or "平台检测到你的资料照片存在待复核信号。"
    if notification_type == NOTIFICATION_TYPE_REQUESTED:
        return "请补录真人活体视频", f"{reason} 请尽快补录真人活体视频，完成平台复核。"
    if notification_type == NOTIFICATION_TYPE_RESUBMISSION_REQUIRED:
        return "补录材料需要重新提交", _as_text(note) or "当前提交的活体视频暂不足以完成复核，请按提示重新补录更清晰的视频。"
    if notification_type == NOTIFICATION_TYPE_APPROVED:
        return "真人视频复核已通过", _as_text(note) or "你的真人活体视频已通过复核，相关资料状态已更新。"
    if notification_type == NOTIFICATION_TYPE_REJECTED:
        return "真人视频复核未通过", _as_text(note) or "当前提交未通过复核，请查看原因后重新准备材料。"
    if notification_type == NOTIFICATION_TYPE_FROZEN:
        return "当前补录任务已冻结", _as_text(note) or "因风险处置升级，你的当前照片补录任务已被冻结，需等待平台进一步处理。"
    if notification_type == NOTIFICATION_TYPE_CLOSED:
        return "当前补录任务已关闭", _as_text(note) or "当前照片补录任务已关闭，无需继续提交本次补录。"
    return "资料复核状态更新", _as_text(note) or "你的资料复核状态已更新。"
