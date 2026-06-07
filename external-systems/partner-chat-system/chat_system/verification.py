"""Live-video verification submissions and reviews."""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from her_time_utils import as_text as _as_text, current_time as _current_time

from partner_moderation import (
    ACTION_FREEZE,
    build_subject_key,
    get_active_moderation_state,
    list_active_moderation_states_by_subject_keys,
)
from profile_service import apply_profile_updates, list_profile_photo_sources, resolve_profile_source

from .storage import inflate_json_columns, json_dumps, json_loads, row_to_dict
from .verification_live_challenge import (
    CHALLENGE_CAPTURE_MODE_REALTIME,
    LIVE_CHALLENGE_ACTION_LIBRARY,
    build_live_video_verification_challenge,
    challenge_phrase,
    decode_live_challenge_token,
)
from .verification_photo_review import (
    NOTIFICATION_TYPE_APPROVED,
    NOTIFICATION_TYPE_CLOSED,
    NOTIFICATION_TYPE_FROZEN,
    NOTIFICATION_TYPE_REJECTED,
    NOTIFICATION_TYPE_REQUESTED,
    NOTIFICATION_TYPE_RESUBMISSION_REQUIRED,
    PHOTO_REVIEW_METADATA_KEY,
    WORKFLOW_HISTORY_METADATA_KEY,
    append_workflow_history,
    build_photo_review_task_metadata,
    is_photo_review_signal_list,
    merge_photo_review_task_metadata,
    photo_review_notification_copy,
)
from .verification_assets import (
    decode_video_bytes as _decode_video_bytes,
    remove_stored_asset as _remove_stored_asset,
    sanitize_file_name as _sanitize_file_name,
    storage_root as _storage_root,
    validate_video_metadata as _validate_video_metadata,
    write_video_asset as _write_video_asset,
)
from .verification_speech import (
    normalize_percent_score as _normalize_percent_score,
    normalize_speech_challenge_result as _normalize_speech_challenge_result,
    transcript_excerpt as _transcript_excerpt,
)
from .verification_notifications import (
    create_verification_notification as _create_verification_notification,
    list_verification_notifications,
    list_verification_notifications_for_submissions,
    notification_already_recorded as _notification_already_recorded,
    parse_statuses as _parse_statuses,
)
from .verification_scoring import (
    apply_speech_review_to_machine_scores as _apply_speech_review_to_machine_scores,
    derive_action_challenge_score as _derive_action_challenge_score,
    normalize_machine_score as _normalize_machine_score,
    score_result as _score_result,
)

VERIFICATION_TYPE_LIVE_VIDEO = "live_video"
VERIFICATION_PROVIDER_LOCAL_OSS = "local_oss"

SUBMISSION_STATUS_AWAITING_SUBMISSION = "awaiting_submission"
SUBMISSION_STATUS_SUBMITTED = "submitted"
SUBMISSION_STATUS_UNDER_REVIEW = "under_review"
SUBMISSION_STATUS_APPROVED = "approved"
SUBMISSION_STATUS_REJECTED = "rejected"
SUBMISSION_STATUS_RESUBMISSION_REQUIRED = "resubmission_required"
SUBMISSION_STATUS_FROZEN = "frozen"
SUBMISSION_STATUS_CLOSED = "closed"

REVIEW_DECISION_APPROVE = "approve"
REVIEW_DECISION_REJECT = "reject"
REVIEW_DECISION_REQUEST_RESUBMISSION = "request_resubmission"
REVIEW_DECISION_MANUAL_REVIEW = "manual_review"

REVIEW_DECISIONS = {
    REVIEW_DECISION_APPROVE,
    REVIEW_DECISION_REJECT,
    REVIEW_DECISION_REQUEST_RESUBMISSION,
}
ACTIVE_REVIEWABLE_STATUSES = {SUBMISSION_STATUS_SUBMITTED, SUBMISSION_STATUS_UNDER_REVIEW}
RESUBMITTABLE_STATUSES = {SUBMISSION_STATUS_RESUBMISSION_REQUIRED, SUBMISSION_STATUS_REJECTED}
OPEN_SUBMISSION_STATUSES = {
    SUBMISSION_STATUS_AWAITING_SUBMISSION,
    SUBMISSION_STATUS_SUBMITTED,
    SUBMISSION_STATUS_UNDER_REVIEW,
    SUBMISSION_STATUS_RESUBMISSION_REQUIRED,
}
SYSTEM_AUTO_REVIEWER_ID = "system:auto_verification"
MACHINE_NEXT_STEP_COMPLETE = "complete"
MACHINE_NEXT_STEP_MANUAL_REVIEW = "manual_review"
MACHINE_NEXT_STEP_RETRY_LIVE_VIDEO = "retry_live_video"
MACHINE_NEXT_STEP_STRONG_IDENTITY = "strong_identity"
MACHINE_RUNTIME_METADATA_KEY = "verification_runtime"
MIN_SPOKEN_PROMPT_DISPLAY_MS = 1200
DEFAULT_REFERENCE_FACE_CANDIDATE_LIMIT = 6
SEVERE_MACHINE_RISK_FLAGS = {
    "deepfake_risk",
    "face_mismatch",
    "identity_swap_risk",
    "multiple_faces",
    "replay_attack",
    "spoofing_risk",
    "stolen_media_risk",
}
DELIVERY_CHANNEL_IN_APP = "in_app"
DELIVERY_STATUS_RECORDED = "recorded"


def _normalize_metadata(metadata: Any) -> dict[str, Any]:
    if isinstance(metadata, dict):
        return dict(metadata)
    return {}
def _normalize_flag_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        slug = re.sub(r"[^a-z0-9_]+", "_", str(item or "").strip().lower()).strip("_")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        out.append(slug)
    return out


def _ordered_unique(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = str(item or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _normalize_action_keys(value: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    raw_items: list[Any]
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        return []
    for item in raw_items:
        key = re.sub(r"[^a-z0-9_]+", "_", str(item or "").strip().lower()).strip("_")
        if not key or key not in LIVE_CHALLENGE_ACTION_LIBRARY or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _machine_review_provider_name() -> str:
    raw = str(os.environ.get("HER_VERIFICATION_PROVIDER") or "").strip().lower()
    if not raw or raw == VERIFICATION_PROVIDER_LOCAL_OSS:
        return VERIFICATION_PROVIDER_LOCAL_OSS
    raise ValueError("HER_VERIFICATION_PROVIDER only supports local_oss")


def _auto_triage_enabled() -> bool:
    try:
        from match_domain.verification_triage import auto_triage_enabled

        return auto_triage_enabled()
    except Exception:  # noqa: BLE001
        raw = str(os.environ.get("HER_VERIFICATION_AUTO_TRIAGE", "1") or "1").strip().lower()
        return raw not in {"0", "false", "no", "off"}
def _machine_review_inputs(metadata: dict[str, Any]) -> dict[str, Any]:
    value = metadata.get("machine_review_inputs")
    if isinstance(value, dict):
        return dict(value)
    return {}


def _live_video_local_module():
    try:
        from . import live_video_local as module
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("local_oss provider dependencies are unavailable") from exc
    return module


def _evaluate_speech_challenge(metadata: dict[str, Any]) -> dict[str, Any]:
    action_result = _normalize_action_result(metadata)
    action_challenge = _normalize_metadata(metadata.get("action_challenge"))
    spoken_code = _as_text(action_challenge.get("spoken_code"))
    if not spoken_code:
        return {}
    speech_result = _normalize_speech_challenge_result(metadata)
    transcript_text = _as_text(speech_result.get("transcript_text"))
    recognized_digits = _as_text(speech_result.get("recognized_digits"))
    transcript_confidence = (
        _normalize_percent_score(speech_result.get("transcript_confidence"), 0)
        if speech_result.get("transcript_confidence") is not None
        else None
    )
    sync_score = (
        _normalize_percent_score(speech_result.get("audio_video_sync_score"), 0)
        if speech_result.get("audio_video_sync_score") is not None
        else None
    )
    explicit_match = speech_result.get("code_match")
    code_match = bool(explicit_match) if explicit_match is not None else bool(recognized_digits and spoken_code in recognized_digits)
    audio_recorded = bool(action_result.get("audio_recorded"))
    spoken_prompt_rendered = bool(action_result.get("spoken_prompt_rendered"))
    prompt_display_ms = int(action_result.get("spoken_prompt_display_ms") or 0)
    action_events = action_result.get("action_events") if isinstance(action_result.get("action_events"), list) else []
    last_action_ms = max((int(item.get("detected_at_ms") or 0) for item in action_events), default=0)
    speech_started_at_ms = speech_result.get("speech_started_at_ms")
    speech_after_actions = True
    if speech_started_at_ms is not None and last_action_ms:
        speech_after_actions = int(speech_started_at_ms) + 300 >= int(last_action_ms)

    risk_flags: list[str] = []
    if not audio_recorded:
        risk_flags.append("missing_audio_evidence")
    if not spoken_prompt_rendered:
        risk_flags.append("spoken_prompt_missing")
    if prompt_display_ms and prompt_display_ms < MIN_SPOKEN_PROMPT_DISPLAY_MS:
        risk_flags.append("spoken_prompt_too_short")
    if not transcript_text:
        risk_flags.append("spoken_code_unverified")
    elif not code_match:
        risk_flags.append("spoken_code_mismatch")
    elif sync_score is None:
        risk_flags.append("audio_video_sync_unverified")
    if transcript_text and not speech_after_actions:
        risk_flags.append("speech_before_actions")
    if sync_score is not None and sync_score < 60:
        risk_flags.append("low_audio_video_sync")

    score = 0
    if audio_recorded:
        score += 20
    if spoken_prompt_rendered:
        score += 15
    if prompt_display_ms >= MIN_SPOKEN_PROMPT_DISPLAY_MS:
        score += 10
    elif prompt_display_ms > 0:
        score += 4
    if transcript_text:
        score += 20
    if code_match:
        score += 25
    if transcript_text and speech_after_actions:
        score += 10
    if sync_score is not None:
        score = int(round((score * 0.65) + (sync_score * 0.35)))
    elif transcript_text:
        score = int(round(score * 0.72))
    if transcript_confidence is not None and transcript_text:
        score = int(round((score * 0.75) + (transcript_confidence * 0.25)))
    score = max(0, min(score, 100))

    result = "unclear"
    if (
        code_match
        and audio_recorded
        and spoken_prompt_rendered
        and score >= 80
        and sync_score is not None
        and "low_audio_video_sync" not in risk_flags
    ):
        result = "pass"
    elif "spoken_code_mismatch" in risk_flags or "missing_audio_evidence" in risk_flags or "spoken_prompt_missing" in risk_flags:
        result = "fail"
    elif not transcript_text:
        result = "unclear"

    return {
        "spoken_code": spoken_code,
        "provider": speech_result.get("provider"),
        "transcript_text": transcript_text or None,
        "transcript_excerpt": _transcript_excerpt(transcript_text),
        "transcript_confidence": transcript_confidence,
        "recognized_digits": recognized_digits or None,
        "code_match": code_match,
        "audio_video_sync_score": sync_score,
        "speech_started_at_ms": speech_started_at_ms,
        "speech_ended_at_ms": speech_result.get("speech_ended_at_ms"),
        "prompt_display_ms": prompt_display_ms,
        "speech_after_actions": speech_after_actions,
        "speech_score": score,
        "speech_result": result,
        "risk_flags": risk_flags,
    }


def create_live_video_verification_challenge(
    *,
    user_id: str,
    profile_id: int | None = None,
    challenge_actions: list[str] | tuple[str, ...] | str | None = None,
    challenge_action_pool: list[str] | tuple[str, ...] | str | None = None,
    action_count: int = 3,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _current_time(now)
    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise ValueError("user_id is required")
    required_actions = _normalize_action_keys(challenge_actions)
    candidate_catalog = _normalize_action_keys(challenge_action_pool)
    return build_live_video_verification_challenge(
        user_id=normalized_user_id,
        profile_id=profile_id,
        required_actions=required_actions,
        challenge_action_pool=candidate_catalog or None,
        action_count=action_count,
        now=ts,
    )


def _normalize_action_result(metadata: dict[str, Any]) -> dict[str, Any]:
    action_result = metadata.get("action_result")
    if not isinstance(action_result, dict):
        return {}
    out = dict(action_result)
    out["completed_actions"] = _normalize_action_keys(out.get("completed_actions"))
    raw_scores = out.get("action_scores")
    scores: dict[str, int] = {}
    if isinstance(raw_scores, dict):
        for key, value in raw_scores.items():
            normalized_key = _normalize_action_keys([key])
            if not normalized_key:
                continue
            scores[normalized_key[0]] = _normalize_machine_score(value, 0)
    out["action_scores"] = scores
    raw_events = out.get("action_events")
    action_events: list[dict[str, Any]] = []
    if isinstance(raw_events, list):
        for index, raw_event in enumerate(raw_events, start=1):
            if not isinstance(raw_event, dict):
                continue
            normalized_key = _normalize_action_keys([raw_event.get("action") or raw_event.get("action_key")])
            if not normalized_key:
                continue
            event: dict[str, Any] = {"action": normalized_key[0]}
            try:
                step_index = int(raw_event.get("step_index") or index)
            except (TypeError, ValueError):
                step_index = index
            event["step_index"] = max(1, step_index)
            raw_detected_at = raw_event.get("detected_at_ms")
            if raw_detected_at is not None:
                try:
                    event["detected_at_ms"] = max(0, int(raw_detected_at))
                except (TypeError, ValueError):
                    pass
            raw_score = raw_event.get("score")
            if raw_score is not None:
                event["score"] = _normalize_machine_score(raw_score, scores.get(normalized_key[0], 0))
            action_events.append(event)
    action_events.sort(key=lambda item: (int(item.get("step_index") or 0), int(item.get("detected_at_ms") or 0)))
    out["action_events"] = action_events
    try:
        out["face_count_max"] = int(out.get("face_count_max") or out.get("max_face_count") or 1)
    except (TypeError, ValueError):
        out["face_count_max"] = 1
    capture_mode = str(out.get("capture_mode") or "").strip().lower()
    if capture_mode:
        out["capture_mode"] = capture_mode
    for key in ("challenge_passed", "video_recorded", "challenge_phrase_rendered", "spoken_prompt_rendered", "audio_recorded"):
        value = out.get(key)
        if isinstance(value, str):
            out[key] = value.strip().lower() in {"1", "true", "yes", "on"}
        elif value is not None:
            out[key] = bool(value)
    for key in ("recording_started_at_ms", "recording_duration_ms", "spoken_prompt_display_ms"):
        raw_value = out.get(key)
        if raw_value is None:
            continue
        try:
            out[key] = max(0, int(raw_value))
        except (TypeError, ValueError):
            out.pop(key, None)
    return out


def _validate_live_challenge_submission(
    *,
    user_id: str,
    profile_id: int | None,
    challenge_token: str,
    metadata: dict[str, Any],
    now: datetime,
) -> tuple[dict[str, Any], str]:
    payload = decode_live_challenge_token(
        challenge_token,
        normalize_action_keys=_normalize_action_keys,
    )
    if str(payload.get("user_id") or "") != str(user_id).strip():
        raise ValueError("challenge_token user_id does not match")
    payload_profile_id = payload.get("profile_id")
    if payload_profile_id is not None and profile_id is None:
        raise ValueError("challenge_token requires profile_id")
    if payload_profile_id is not None and profile_id is not None and int(payload_profile_id) != int(profile_id):
        raise ValueError("challenge_token profile_id does not match")
    expires_at = datetime.fromisoformat(str(payload["expires_at"]))
    if now > expires_at:
        raise ValueError("challenge_token has expired")

    required_actions = _normalize_action_keys(payload.get("required_actions"))
    if not required_actions:
        raise ValueError("challenge_token required actions are missing")
    spoken_code = _as_text(payload.get("spoken_code"))
    action_result = _normalize_action_result(metadata)
    if not action_result:
        raise ValueError("metadata.action_result is required for realtime challenge verification")
    if not action_result.get("challenge_phrase_rendered"):
        raise ValueError("metadata.action_result.challenge_phrase_rendered is required for realtime challenge verification")
    action_events = action_result.get("action_events") if isinstance(action_result.get("action_events"), list) else []
    if not action_events:
        raise ValueError("metadata.action_result.action_events is required for realtime challenge verification")

    reported_completed = _ordered_unique(list(action_result.get("completed_actions") or []))
    if not reported_completed:
        for action_key in required_actions:
            passed_key = f"{action_key}_passed"
            if action_result.get(passed_key):
                reported_completed.append(action_key)
    event_order = _ordered_unique([str(event.get("action") or "").strip() for event in action_events])
    completed_actions = event_order or reported_completed
    if completed_actions[: len(required_actions)] != required_actions:
        raise ValueError("metadata.action_result does not follow challenge order")
    challenge_passed = len(completed_actions) >= len(required_actions)
    if not challenge_passed:
        raise ValueError("metadata.action_result did not complete the required challenge actions")
    if spoken_code:
        if not action_result.get("spoken_prompt_rendered"):
            raise ValueError("metadata.action_result.spoken_prompt_rendered is required for spoken challenge verification")
        if not action_result.get("audio_recorded"):
            raise ValueError("metadata.action_result.audio_recorded is required for spoken challenge verification")
    action_result["completed_actions"] = list(required_actions)
    action_result["challenge_passed"] = bool(action_result.get("challenge_passed", challenge_passed)) and challenge_passed

    enriched_metadata = _normalize_metadata(metadata)
    enriched_metadata["action_result"] = action_result
    normalized_speech_result = _normalize_speech_challenge_result(enriched_metadata)
    if normalized_speech_result:
        enriched_metadata["speech_challenge_result"] = normalized_speech_result
    enriched_metadata["action_challenge"] = {
        "challenge_id": payload.get("challenge_id"),
        "required_actions": required_actions,
        "spoken_code": spoken_code or None,
        "prompt_steps": payload.get("prompt_steps"),
        "issued_at": payload.get("issued_at"),
        "expires_at": payload.get("expires_at"),
        "capture_mode": payload.get("capture_mode") or CHALLENGE_CAPTURE_MODE_REALTIME,
    }
    return enriched_metadata, str(payload.get("challenge_phrase") or challenge_phrase(required_actions))


def _generate_submission_id() -> str:
    return f"vfy-{uuid.uuid4().hex[:16]}"


def _inflate_asset(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, metadata=("metadata_json", {}, _normalize_metadata))


def _inflate_review(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(row, metadata=("metadata_json", {}, _normalize_metadata))


def _submission_has_photo_review_task(submission: dict[str, Any] | None) -> bool:
    if not submission:
        return False
    metadata = _normalize_metadata(submission.get("metadata"))
    task = _normalize_metadata(metadata.get(PHOTO_REVIEW_METADATA_KEY))
    return task.get("task_kind") == "photo_review"


def _matching_profile_ref(
    submission: dict[str, Any] | None,
    *,
    profile_id: int | None,
    source_dsn: str | None,
    source_table_name: str | None,
) -> bool:
    if not submission:
        return False
    if profile_id is not None and submission.get("profile_id") is not None and int(submission["profile_id"]) != int(profile_id):
        return False
    if source_dsn and _as_text(submission.get("source_dsn")) and _as_text(submission.get("source_dsn")) != _as_text(source_dsn):
        return False
    if source_table_name and _as_text(submission.get("source_table_name")) and _as_text(submission.get("source_table_name")) != _as_text(source_table_name):
        return False
    return True


def _submission_subject_key(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    try:
        return build_subject_key(
            subject_user_id=row.get("user_id"),
            source_dsn=row.get("source_dsn"),
            source_table_name=row.get("source_table_name"),
            profile_id=int(row["profile_id"]) if row.get("profile_id") is not None else None,
        )
    except Exception:
        return None


def list_verification_assets_for_submissions(
    conn,
    submission_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    normalized = [str(item).strip() for item in submission_ids if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM verification_assets
        WHERE submission_id IN ({placeholders})
        ORDER BY submission_id ASC, asset_id ASC
        """,
        tuple(normalized),
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {submission_id: [] for submission_id in normalized}
    for row in rows:
        asset = _inflate_asset(row_to_dict(row))
        submission_id = str((asset or {}).get("submission_id") or "")
        if asset and submission_id:
            grouped.setdefault(submission_id, []).append(asset)
    return grouped


def list_verification_reviews_for_submissions(
    conn,
    submission_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    normalized = [str(item).strip() for item in submission_ids if str(item or "").strip()]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM verification_reviews
        WHERE submission_id IN ({placeholders})
        ORDER BY submission_id ASC, review_id ASC
        """,
        tuple(normalized),
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {submission_id: [] for submission_id in normalized}
    for row in rows:
        review = _inflate_review(row_to_dict(row))
        submission_id = str((review or {}).get("submission_id") or "")
        if review and submission_id:
            grouped.setdefault(submission_id, []).append(review)
    return grouped


def _inflate_submission(
    conn,
    row: dict[str, Any] | None,
    *,
    include_children: bool = True,
    preloaded_moderation_state: dict[str, Any] | None = None,
    preloaded_assets: list[dict[str, Any]] | None = None,
    preloaded_notifications: list[dict[str, Any]] | None = None,
    preloaded_reviews: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not row:
        return None
    out = dict(row)
    out["metadata"] = _normalize_metadata(json_loads(out.pop("metadata_json", None), {}))
    out[PHOTO_REVIEW_METADATA_KEY] = _normalize_metadata(out["metadata"].get(PHOTO_REVIEW_METADATA_KEY))
    out["workflow_history"] = list(out["metadata"].get(WORKFLOW_HISTORY_METADATA_KEY) or [])
    runtime = _normalize_metadata(out["metadata"].get(MACHINE_RUNTIME_METADATA_KEY))
    out["machine_review"] = runtime.get("machine_review")
    out["machine_review_history"] = runtime.get("machine_review_history", [])
    out["recommended_decision"] = runtime.get("recommended_decision")
    out["recommended_next_step"] = runtime.get("recommended_next_step")
    out["confidence_band"] = runtime.get("confidence_band")
    out["verification_provider"] = runtime.get("verification_provider")
    out["auto_review_applied"] = bool(runtime.get("auto_review_applied"))
    out["profile_sync"] = runtime.get("profile_sync")
    moderation_state = preloaded_moderation_state
    if moderation_state is None:
        moderation_state = get_active_moderation_state(
            conn,
            subject_user_id=out.get("user_id"),
            source_dsn=out.get("source_dsn"),
            source_table_name=out.get("source_table_name"),
            profile_id=int(out["profile_id"]) if out.get("profile_id") is not None else None,
        )
    out["moderation_state"] = moderation_state
    blocking_action = _as_text((moderation_state or {}).get("applied_action")) or None
    out["blocking_action"] = blocking_action
    out["derived_status"] = SUBMISSION_STATUS_FROZEN if blocking_action == ACTION_FREEZE and out["status"] in OPEN_SUBMISSION_STATUSES else out["status"]
    if include_children:
        out["assets"] = (
            list(preloaded_assets)
            if preloaded_assets is not None
            else list_verification_assets(conn, out["submission_id"])
        )
        out["notifications"] = (
            list(preloaded_notifications)
            if preloaded_notifications is not None
            else list_verification_notifications(conn, submission_id=out["submission_id"], limit=100)
        )
        out["reviews"] = (
            list(preloaded_reviews)
            if preloaded_reviews is not None
            else list_verification_reviews(conn, out["submission_id"])
        )
        out["latest_asset"] = out["assets"][-1] if out["assets"] else None
    return out


def _inflate_submission_rows(
    conn,
    row_dicts: list[dict[str, Any]],
    *,
    include_children: bool = True,
) -> list[dict[str, Any]]:
    if not row_dicts:
        return []
    submission_ids = [
        str(row_dict.get("submission_id") or "").strip()
        for row_dict in row_dicts
        if str(row_dict.get("submission_id") or "").strip()
    ]
    moderation_states_by_subject_key = list_active_moderation_states_by_subject_keys(
        conn,
        [key for key in (_submission_subject_key(row_dict) for row_dict in row_dicts) if key],
    )
    assets_by_submission_id: dict[str, list[dict[str, Any]]] = {}
    notifications_by_submission_id: dict[str, list[dict[str, Any]]] = {}
    reviews_by_submission_id: dict[str, list[dict[str, Any]]] = {}
    if include_children:
        assets_by_submission_id = list_verification_assets_for_submissions(conn, submission_ids)
        notifications_by_submission_id = list_verification_notifications_for_submissions(conn, submission_ids)
        reviews_by_submission_id = list_verification_reviews_for_submissions(conn, submission_ids)
    return [
        _inflate_submission(
            conn,
            row_dict,
            include_children=include_children,
            preloaded_moderation_state=moderation_states_by_subject_key.get(_submission_subject_key(row_dict) or ""),
            preloaded_assets=assets_by_submission_id.get(str(row_dict.get("submission_id") or "").strip(), []),
            preloaded_notifications=notifications_by_submission_id.get(str(row_dict.get("submission_id") or "").strip(), []),
            preloaded_reviews=reviews_by_submission_id.get(str(row_dict.get("submission_id") or "").strip(), []),
        )
        for row_dict in row_dicts
    ]


def _get_submission_row(conn, submission_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM verification_submissions WHERE submission_id = ? LIMIT 1",
        (submission_id,),
    ).fetchone()
    return row_to_dict(row)


def list_verification_assets(conn, submission_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM verification_assets
        WHERE submission_id = ?
        ORDER BY asset_id ASC
        """,
        (submission_id,),
    ).fetchall()
    return [_inflate_asset(row_to_dict(row)) for row in rows if row]


def list_verification_reviews(conn, submission_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM verification_reviews
        WHERE submission_id = ?
        ORDER BY review_id ASC
        """,
        (submission_id,),
    ).fetchall()
    return [_inflate_review(row_to_dict(row)) for row in rows if row]


def get_verification_submission(conn, submission_id: str) -> dict[str, Any] | None:
    return _inflate_submission(conn, _get_submission_row(conn, submission_id))


def list_verification_submissions(
    conn,
    *,
    user_id: str | None = None,
    statuses: list[str] | tuple[str, ...] | str | None = None,
    profile_id: int | None = None,
    limit: int = 100,
    include_children: bool = True,
) -> list[dict[str, Any]]:
    clauses = ["verification_type = ?"]
    params: list[Any] = [VERIFICATION_TYPE_LIVE_VIDEO]
    if user_id:
        clauses.append("user_id = ?")
        params.append(str(user_id))
    if profile_id is not None:
        clauses.append("profile_id = ?")
        params.append(int(profile_id))
    normalized_statuses = _parse_statuses(statuses)
    if normalized_statuses:
        placeholders = ", ".join(["?"] * len(normalized_statuses))
        clauses.append(f"status IN ({placeholders})")
        params.extend(normalized_statuses)
    params.append(max(1, min(int(limit), 200)))
    rows = conn.execute(
        f"""
        SELECT * FROM verification_submissions
        WHERE {' AND '.join(clauses)}
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    row_dicts = [row_to_dict(row) for row in rows if row]
    return _inflate_submission_rows(conn, row_dicts, include_children=include_children)


def list_photo_review_requests(
    conn,
    *,
    user_id: str | None = None,
    statuses: list[str] | tuple[str, ...] | str | None = None,
    profile_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    rows = list_verification_submissions(
        conn,
        user_id=user_id,
        statuses=statuses,
        profile_id=profile_id,
        limit=max(1, min(int(limit), 200)),
        include_children=False,
    )
    filtered_rows = [dict(row) for row in rows if _submission_has_photo_review_task(row)]
    submission_ids = [
        str(row.get("submission_id") or "").strip()
        for row in filtered_rows
        if str(row.get("submission_id") or "").strip()
    ]
    assets_by_submission_id = list_verification_assets_for_submissions(conn, submission_ids)
    notifications_by_submission_id = list_verification_notifications_for_submissions(conn, submission_ids)
    reviews_by_submission_id = list_verification_reviews_for_submissions(conn, submission_ids)
    for row in filtered_rows:
        submission_id = str(row.get("submission_id") or "").strip()
        row["assets"] = list(assets_by_submission_id.get(submission_id, []))
        row["notifications"] = list(notifications_by_submission_id.get(submission_id, []))
        row["reviews"] = list(reviews_by_submission_id.get(submission_id, []))
        row["latest_asset"] = row["assets"][-1] if row["assets"] else None
    return filtered_rows


def _find_pending_photo_review_request(
    conn,
    *,
    user_id: str,
    profile_id: int | None,
    source_dsn: str | None,
    source_table_name: str | None,
    submission_id: str | None = None,
) -> dict[str, Any] | None:
    if submission_id:
        row = get_verification_submission(conn, submission_id)
        if not row:
            raise ValueError("verification submission not found")
        if _as_text(row.get("user_id")) != _as_text(user_id):
            raise ValueError("user_id does not own this verification submission")
        if row.get("status") != SUBMISSION_STATUS_AWAITING_SUBMISSION:
            raise ValueError("verification submission is not awaiting first upload")
        if not _submission_has_photo_review_task(row):
            raise ValueError("verification submission is not a photo review task")
        return row

    candidates = list_photo_review_requests(
        conn,
        user_id=user_id,
        statuses=[SUBMISSION_STATUS_AWAITING_SUBMISSION],
        profile_id=profile_id,
        limit=20,
    )
    matched = [
        row
        for row in candidates
        if _matching_profile_ref(
            row,
            profile_id=profile_id,
            source_dsn=source_dsn,
            source_table_name=source_table_name,
        )
    ]
    if not matched:
        return None
    return matched[0]


def _maybe_record_submission_notification(
    conn,
    submission: dict[str, Any],
    *,
    notification_type: str,
    note: str | None,
    now: datetime,
) -> None:
    if not _submission_has_photo_review_task(submission):
        return
    if _notification_already_recorded(
        conn,
        submission_id=str(submission["submission_id"]),
        notification_type=notification_type,
    ):
        return
    title, body = photo_review_notification_copy(notification_type, submission, note=note)
    _create_verification_notification(
        conn,
        submission_id=str(submission["submission_id"]),
        user_id=str(submission["user_id"]),
        notification_type=notification_type,
        title=title,
        body=body,
        metadata={
            "status": submission.get("status"),
            "review_decision": submission.get("review_decision"),
            "note": note,
        },
        now=now,
    )


def request_live_video_verification(
    conn,
    *,
    user_id: str,
    profile_id: int | None = None,
    source_dsn: str | None = None,
    source_table_name: str | None = None,
    request_source: str = "risk_case_review",
    request_reason: str | None = None,
    signal_codes: list[str] | tuple[str, ...] | str | None = None,
    risk_case_id: str | None = None,
    report_ids: list[int] | tuple[int, ...] | None = None,
    requested_by: str | None = None,
    due_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _current_time(now)
    normalized_user_id = _as_text(user_id)
    if not normalized_user_id:
        raise ValueError("user_id is required")
    normalized_signal_codes = _parse_statuses(signal_codes) or []
    if not is_photo_review_signal_list(normalized_signal_codes):
        raise ValueError("signal_codes must include at least one photo review risk")

    existing = _find_pending_photo_review_request(
        conn,
        user_id=normalized_user_id,
        profile_id=profile_id,
        source_dsn=source_dsn,
        source_table_name=source_table_name,
    )
    if existing:
        merged_metadata = _normalize_metadata(existing.get("metadata"))
        merged_metadata[PHOTO_REVIEW_METADATA_KEY] = merge_photo_review_task_metadata(
            _normalize_metadata(merged_metadata.get(PHOTO_REVIEW_METADATA_KEY)),
            request_source=request_source,
            signal_codes=normalized_signal_codes,
            request_reason=request_reason,
            requested_by=requested_by,
            risk_case_ids=[risk_case_id] if risk_case_id else None,
            report_ids=list(report_ids or []),
            due_at=due_at,
            now=ts,
        )
        merged_metadata.update(_normalize_metadata(metadata))
        merged_metadata = append_workflow_history(
            merged_metadata,
            event_type="photo_review_request_refreshed",
            occurred_at=ts,
            payload={
                "request_source": request_source,
                "risk_case_id": risk_case_id,
                "signal_codes": normalized_signal_codes,
            },
        )
        conn.execute(
            """
            UPDATE verification_submissions
            SET metadata_json = ?, updated_at = ?
            WHERE submission_id = ?
            """,
            (json_dumps(merged_metadata), ts, existing["submission_id"]),
        )
        conn.commit()
        refreshed = get_verification_submission(conn, existing["submission_id"])
        assert refreshed is not None
        return refreshed

    submission_id = _generate_submission_id()
    task_metadata = build_photo_review_task_metadata(
        request_source=request_source,
        signal_codes=normalized_signal_codes,
        request_reason=request_reason,
        requested_by=requested_by,
        risk_case_ids=[risk_case_id] if risk_case_id else None,
        report_ids=list(report_ids or []),
        due_at=due_at,
        now=ts,
    )
    submission_metadata = _normalize_metadata(metadata)
    submission_metadata[PHOTO_REVIEW_METADATA_KEY] = task_metadata
    submission_metadata = append_workflow_history(
        submission_metadata,
        event_type="photo_review_requested",
        occurred_at=ts,
        payload={
            "request_source": request_source,
            "risk_case_id": risk_case_id,
            "signal_codes": normalized_signal_codes,
        },
    )
    conn.execute(
        """
        INSERT INTO verification_submissions (
          submission_id, verification_type, user_id, profile_id, source_dsn, source_table_name,
          status, resubmission_count, challenge_phrase, review_decision, review_note, reviewer_id,
          latest_asset_id, latest_sync_status, latest_sync_error, submitted_at, reviewed_at,
          approved_at, rejected_at, metadata_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL, ?, NULL, NULL, NULL, ?, ?, ?)
        """,
        (
            submission_id,
            VERIFICATION_TYPE_LIVE_VIDEO,
            normalized_user_id,
            int(profile_id) if profile_id is not None else None,
            _as_text(source_dsn) or None,
            _as_text(source_table_name) or None,
            SUBMISSION_STATUS_AWAITING_SUBMISSION,
            0,
            ts,
            json_dumps(submission_metadata),
            ts,
            ts,
        ),
    )
    created = get_verification_submission(conn, submission_id)
    assert created is not None
    _maybe_record_submission_notification(
        conn,
        created,
        notification_type=NOTIFICATION_TYPE_REQUESTED,
        note=task_metadata.get("request_reason"),
        now=ts,
    )
    conn.commit()
    refreshed = get_verification_submission(conn, submission_id)
    assert refreshed is not None
    return refreshed


def _update_photo_review_request_status(
    conn,
    *,
    user_id: str,
    profile_id: int | None,
    source_dsn: str | None,
    source_table_name: str | None,
    risk_case_id: str | None,
    next_status: str,
    note: str | None,
    actor_id: str | None,
    now: datetime,
) -> list[dict[str, Any]]:
    candidates = list_photo_review_requests(
        conn,
        user_id=user_id,
        statuses=list(OPEN_SUBMISSION_STATUSES),
        profile_id=profile_id,
        limit=50,
    )
    updated_rows: list[dict[str, Any]] = []
    for row in candidates:
        if not _matching_profile_ref(
            row,
            profile_id=profile_id,
            source_dsn=source_dsn,
            source_table_name=source_table_name,
        ):
            continue
        task = _normalize_metadata(row.get(PHOTO_REVIEW_METADATA_KEY))
        linked_risk_case_ids = set(task.get("linked_risk_case_ids") or [])
        if risk_case_id and linked_risk_case_ids and risk_case_id not in linked_risk_case_ids:
            continue
        merged_metadata = _normalize_metadata(row.get("metadata"))
        task["last_resolution_note"] = _as_text(note) or None
        task["last_resolved_by"] = _as_text(actor_id) or None
        task["last_resolved_at"] = now.isoformat(sep=" ")
        merged_metadata[PHOTO_REVIEW_METADATA_KEY] = task
        merged_metadata = append_workflow_history(
            merged_metadata,
            event_type=f"photo_review_{next_status}",
            occurred_at=now,
            payload={"note": note, "actor_id": actor_id},
        )
        conn.execute(
            """
            UPDATE verification_submissions
            SET status = ?, metadata_json = ?, updated_at = ?
            WHERE submission_id = ?
            """,
            (next_status, json_dumps(merged_metadata), now, row["submission_id"]),
        )
        refreshed = get_verification_submission(conn, row["submission_id"])
        assert refreshed is not None
        if next_status == SUBMISSION_STATUS_FROZEN:
            _maybe_record_submission_notification(
                conn,
                refreshed,
                notification_type=NOTIFICATION_TYPE_FROZEN,
                note=note,
                now=now,
            )
        elif next_status == SUBMISSION_STATUS_CLOSED:
            _maybe_record_submission_notification(
                conn,
                refreshed,
                notification_type=NOTIFICATION_TYPE_CLOSED,
                note=note,
                now=now,
            )
        updated_rows.append(refreshed)
    return updated_rows


def sync_photo_review_request_from_risk_case(
    conn,
    *,
    subject_user_id: str,
    profile_id: int | None = None,
    source_dsn: str | None = None,
    source_table_name: str | None = None,
    signal_codes: list[str] | tuple[str, ...] | str | None = None,
    risk_case_id: str | None = None,
    applied_action: str | None = None,
    status: str | None = None,
    resolution_note: str | None = None,
    resolver_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _current_time(now)
    normalized_signal_codes = _parse_statuses(signal_codes) or []
    if not is_photo_review_signal_list(normalized_signal_codes):
        return {"request": None, "updated": []}

    normalized_action = _as_text(applied_action)
    normalized_status = _as_text(status)
    if normalized_action == "require_verification":
        request = request_live_video_verification(
            conn,
            user_id=subject_user_id,
            profile_id=profile_id,
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            request_source="risk_case_review",
            request_reason=resolution_note,
            signal_codes=normalized_signal_codes,
            risk_case_id=risk_case_id,
            requested_by=resolver_id,
            now=ts,
        )
        return {"request": request, "updated": []}
    if normalized_action == ACTION_FREEZE:
        return {
            "request": None,
            "updated": _update_photo_review_request_status(
                conn,
                user_id=subject_user_id,
                profile_id=profile_id,
                source_dsn=source_dsn,
                source_table_name=source_table_name,
                risk_case_id=risk_case_id,
                next_status=SUBMISSION_STATUS_FROZEN,
                note=resolution_note,
                actor_id=resolver_id,
                now=ts,
            ),
        }
    if normalized_status in {"dismissed", "resolved"}:
        return {
            "request": None,
            "updated": _update_photo_review_request_status(
                conn,
                user_id=subject_user_id,
                profile_id=profile_id,
                source_dsn=source_dsn,
                source_table_name=source_table_name,
                risk_case_id=risk_case_id,
                next_status=SUBMISSION_STATUS_CLOSED,
                note=resolution_note,
                actor_id=resolver_id,
                now=ts,
            ),
        }
    return {"request": None, "updated": []}


def _insert_asset_row(conn, submission_id: str, asset_payload: dict[str, Any], *, attempt: int, now: datetime, metadata: dict[str, Any] | None = None) -> int:
    conn.execute(
        """
        INSERT INTO verification_assets (
          submission_id, asset_kind, storage_key, original_file_name, content_type,
          file_size_bytes, sha256_hex, upload_attempt, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            submission_id,
            VERIFICATION_TYPE_LIVE_VIDEO,
            asset_payload["storage_key"],
            asset_payload["original_file_name"],
            asset_payload["content_type"],
            int(asset_payload["file_size_bytes"]),
            asset_payload["sha256_hex"],
            int(attempt),
            json_dumps(metadata or {}),
            now,
        ),
    )
    return int(conn.lastrowid)


def _resolve_machine_review_outcome(
    *,
    liveness_score: int,
    face_match_score: int,
    challenge_score: int,
    risk_flags: list[str],
    spoken_code_required: bool,
    speech_review: dict[str, Any],
    success_summary: str,
    retry_summary: str,
) -> tuple[str | None, str, str, str]:
    recommended_decision: str | None = REVIEW_DECISION_MANUAL_REVIEW
    recommended_next_step = MACHINE_NEXT_STEP_MANUAL_REVIEW
    confidence_band = "medium"
    summary = "机器结果没有明显高风险，但还不够稳，转人工复核"
    severe_flags = [flag for flag in risk_flags if flag in SEVERE_MACHINE_RISK_FLAGS]
    speech_result = _as_text(speech_review.get("speech_result"))
    if severe_flags or face_match_score < 40:
        recommended_next_step = MACHINE_NEXT_STEP_STRONG_IDENTITY
        confidence_band = "high"
        summary = "同人比对过低或命中高风险标记，先转人工复核，并建议升级强实名"
    elif speech_result == "fail" or liveness_score < 60 or challenge_score < 60:
        recommended_decision = REVIEW_DECISION_REQUEST_RESUBMISSION
        recommended_next_step = MACHINE_NEXT_STEP_RETRY_LIVE_VIDEO
        confidence_band = "high"
        summary = retry_summary
    elif (
        liveness_score >= 85
        and face_match_score >= 85
        and challenge_score >= 80
        and not risk_flags
        and (not spoken_code_required or speech_result == "pass")
    ):
        recommended_decision = REVIEW_DECISION_APPROVE
        recommended_next_step = MACHINE_NEXT_STEP_COMPLETE
        confidence_band = "high"
        summary = success_summary
    return recommended_decision, recommended_next_step, confidence_band, summary


def _local_oss_machine_review(
    *,
    attempt: int,
    file_name: str,
    content_type: str,
    file_size_bytes: int,
    challenge_phrase: str | None,
    profile_id: int | None,
    source_dsn: str | None,
    source_table_name: str | None,
    video_path: Path | None,
    metadata: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    if video_path is None:
        raise ValueError("video_path is required when HER_VERIFICATION_PROVIDER=local_oss")

    inputs = _machine_review_inputs(metadata)
    action_result = _normalize_action_result(metadata)
    action_challenge = _normalize_metadata(metadata.get("action_challenge"))
    required_actions = _normalize_action_keys(action_challenge.get("required_actions"))
    spoken_code = _as_text(action_challenge.get("spoken_code")) or None
    spoken_code_required = bool(spoken_code)
    reference_face_sources = _load_profile_reference_face_sources(
        profile_id=profile_id,
        source_dsn=source_dsn,
        source_table_name=source_table_name,
    )
    completed_actions = set(action_result.get("completed_actions") or [])
    action_scores = action_result.get("action_scores") if isinstance(action_result.get("action_scores"), dict) else {}
    action_completion_ratio = 0.0
    if required_actions:
        completed_required = [action for action in required_actions if action in completed_actions]
        action_completion_ratio = len(completed_required) / len(required_actions)

    raw_override_result = metadata.get("local_provider_result") or metadata.get("local_oss_provider_result")
    provider_result: dict[str, Any]
    if isinstance(raw_override_result, dict) or inputs:
        provider_result = dict(raw_override_result) if isinstance(raw_override_result, dict) else {}
        provider_result["provider"] = _as_text(provider_result.get("provider")) or VERIFICATION_PROVIDER_LOCAL_OSS
        provider_result["provider_version"] = (
            _as_text(provider_result.get("provider_version")) or "local-oss-test-override"
        )
        for key in (
            "liveness_score",
            "face_match_score",
            "same_person_score",
            "replay_attack_score",
            "screen_risk_score",
            "spoofing_risk_score",
            "deepfake_risk_score",
            "deepfake_temporal_score",
            "deepfake_artifact_score",
            "photo_edit_risk_score",
            "skin_smoothing_risk_score",
            "beauty_filter_risk_score",
            "face_shape_delta_score",
            "motion_score",
            "face_presence_score",
            "average_detection_confidence",
        ):
            if key in provider_result and provider_result.get(key) is not None:
                provider_result[key] = _normalize_percent_score(provider_result.get(key), 0)
        for key in (
            "sampled_frame_count",
            "valid_face_frame_count",
            "detected_face_count_max",
            "deepfake_sampled_frame_count",
            "deepfake_face_frame_count",
            "photo_edit_reference_face_count",
            "photo_edit_live_face_frame_count",
            "photo_edit_reference_source_count",
            "photo_edit_edited_reference_count",
        ):
            if key in provider_result and provider_result.get(key) is not None:
                try:
                    provider_result[key] = max(0, int(provider_result.get(key)))
                except (TypeError, ValueError):
                    provider_result.pop(key, None)
        if "deepfake_analysis_status" in provider_result:
            provider_result["deepfake_analysis_status"] = _as_text(provider_result.get("deepfake_analysis_status")) or None
        if "photo_edit_analysis_status" in provider_result:
            provider_result["photo_edit_analysis_status"] = _as_text(provider_result.get("photo_edit_analysis_status")) or None
        provider_result["risk_flags"] = _normalize_flag_list(provider_result.get("risk_flags") or inputs.get("risk_flags"))
        if provider_result.get("speech_challenge_result") and isinstance(provider_result.get("speech_challenge_result"), dict):
            provider_result["speech_challenge_result"] = _normalize_speech_challenge_result(
                {"speech_challenge_result": provider_result.get("speech_challenge_result")}
            )

        if provider_result.get("liveness_score") is None:
            provider_result["liveness_score"] = _normalize_machine_score(inputs.get("liveness_score"), 76 + (8 if challenge_phrase else -6))
        if provider_result.get("face_match_score") is None:
            provider_result["face_match_score"] = _normalize_machine_score(inputs.get("face_match_score"), 78)
        if provider_result.get("same_person_score") is None:
            provider_result["same_person_score"] = provider_result.get("face_match_score")
        if provider_result.get("replay_attack_score") is None:
            provider_result["replay_attack_score"] = _normalize_machine_score(inputs.get("replay_attack_score"), 0)
        if provider_result.get("screen_risk_score") is None:
            provider_result["screen_risk_score"] = _normalize_machine_score(inputs.get("screen_risk_score"), 0)
        if provider_result.get("spoofing_risk_score") is None:
            provider_result["spoofing_risk_score"] = _normalize_machine_score(inputs.get("spoofing_risk_score"), 0)
        if provider_result.get("deepfake_risk_score") is None:
            provider_result["deepfake_risk_score"] = _normalize_machine_score(inputs.get("deepfake_risk_score"), 0)
        if provider_result.get("detected_face_count_max") is None:
            provider_result["detected_face_count_max"] = max(1, int(action_result.get("face_count_max") or 1))
        if provider_result.get("has_audio_track") is None:
            provider_result["has_audio_track"] = bool(action_result.get("audio_recorded")) or not spoken_code_required
    elif file_size_bytes <= 1024:
        provider_result = {
            "provider": VERIFICATION_PROVIDER_LOCAL_OSS,
            "provider_version": "local-oss-tiny-file-fallback",
            "liveness_score": 68,
            "face_match_score": 78,
            "same_person_score": 78,
            "replay_attack_score": 0,
            "screen_risk_score": 0,
            "spoofing_risk_score": 0,
            "deepfake_risk_score": 0,
            "risk_flags": ["analysis_unavailable"],
            "detected_face_count_max": max(1, int(action_result.get("face_count_max") or 1)),
            "has_audio_track": bool(action_result.get("audio_recorded")) or not spoken_code_required,
        }
    else:
        local_module = _live_video_local_module()
        try:
            provider_result = local_module.analyze_local_live_video(
                video_path,
                spoken_code=spoken_code,
                face_match_score_hint=inputs.get("face_match_score"),
                reference_image_sources=reference_face_sources,
            )
        except ValueError:
            provider_result = {
                "provider": VERIFICATION_PROVIDER_LOCAL_OSS,
                "provider_version": "local-oss-analysis-fallback",
                "liveness_score": 68,
                "face_match_score": 78,
                "same_person_score": 78,
                "replay_attack_score": 0,
                "screen_risk_score": 0,
                "spoofing_risk_score": 0,
                "deepfake_risk_score": 0,
                "risk_flags": ["analysis_unavailable"],
                "detected_face_count_max": max(1, int(action_result.get("face_count_max") or 1)),
                "has_audio_track": bool(action_result.get("audio_recorded")) or not spoken_code_required,
            }
    existing_speech_result = _normalize_speech_challenge_result(metadata)
    speech_result = provider_result.get("speech_challenge_result")
    if isinstance(speech_result, dict) and speech_result:
        normalized_provider_speech = _normalize_speech_challenge_result({"speech_challenge_result": speech_result})
        provider_result["speech_challenge_result"] = normalized_provider_speech
        provider_speech_unavailable = _as_text(normalized_provider_speech.get("analysis_status")) == "unavailable"
        if provider_speech_unavailable and existing_speech_result:
            provider_result["speech_challenge_backend_result"] = normalized_provider_speech
            metadata["speech_challenge_result"] = existing_speech_result
        else:
            metadata["speech_challenge_result"] = normalized_provider_speech

    face_count_max = max(
        int(action_result.get("face_count_max") or 1),
        int(provider_result.get("detected_face_count_max") or 0),
    )
    liveness_score = _normalize_machine_score(provider_result.get("liveness_score"), 0)
    face_match_score = _normalize_machine_score(
        provider_result.get("face_match_score") or provider_result.get("same_person_score"),
        0,
    )
    challenge_score = _derive_action_challenge_score(
        action_result=action_result,
        required_actions=required_actions,
        completed_actions=completed_actions,
        action_scores=action_scores,
        action_completion_ratio=action_completion_ratio,
        face_count_max=face_count_max,
        challenge_hint="",
        default_score=84 if challenge_phrase else 55,
    )
    if inputs.get("challenge_score") is not None:
        challenge_score = _normalize_machine_score(inputs.get("challenge_score"), challenge_score)
    if provider_result.get("motion_score") is not None:
        motion_score = _normalize_machine_score(provider_result.get("motion_score"), challenge_score)
        challenge_score = max(0, min(int(round((challenge_score * 0.75) + (motion_score * 0.25))), 100))

    risk_flags = _normalize_flag_list(provider_result.get("risk_flags"))
    if required_actions and action_completion_ratio < 1 and "challenge_incomplete" not in risk_flags:
        risk_flags.append("challenge_incomplete")
    if face_count_max > 1 and "multiple_faces" not in risk_flags:
        risk_flags.append("multiple_faces")
    if provider_result.get("replay_attack_score", 0) >= 85 and "replay_attack" not in risk_flags:
        risk_flags.append("replay_attack")
    elif provider_result.get("replay_attack_score", 0) >= 60 and "suspected_replay_attack" not in risk_flags:
        risk_flags.append("suspected_replay_attack")
    if provider_result.get("screen_risk_score", 0) >= 75 and "screen_replay_risk" not in risk_flags:
        risk_flags.append("screen_replay_risk")
    if provider_result.get("spoofing_risk_score", 0) >= 85 and "spoofing_risk" not in risk_flags:
        risk_flags.append("spoofing_risk")
    elif provider_result.get("spoofing_risk_score", 0) >= 60 and "anti_spoof_uncertain" not in risk_flags:
        risk_flags.append("anti_spoof_uncertain")
    if provider_result.get("deepfake_risk_score", 0) >= 85 and "deepfake_risk" not in risk_flags:
        risk_flags.append("deepfake_risk")
    elif provider_result.get("deepfake_risk_score", 0) >= 60 and "deepfake_uncertain" not in risk_flags:
        risk_flags.append("deepfake_uncertain")
    if provider_result.get("photo_edit_risk_score", 0) >= 85 and "photo_heavily_edited" not in risk_flags:
        risk_flags.append("photo_heavily_edited")
    elif provider_result.get("photo_edit_risk_score", 0) >= 60 and "photo_edit_uncertain" not in risk_flags:
        risk_flags.append("photo_edit_uncertain")
    if face_match_score < 40 and "face_mismatch" not in risk_flags:
        risk_flags.append("face_mismatch")
    if liveness_score < 60 and "low_liveness" not in risk_flags:
        risk_flags.append("low_liveness")
    if spoken_code_required and not bool(provider_result.get("has_audio_track")) and "missing_audio_track" not in risk_flags:
        risk_flags.append("missing_audio_track")

    speech_review = _evaluate_speech_challenge(metadata)
    if spoken_code_required and not bool(provider_result.get("has_audio_track")):
        speech_review = dict(speech_review)
        speech_flags = list(speech_review.get("risk_flags") or [])
        for flag in ("missing_audio_track", "missing_audio_evidence"):
            if flag not in speech_flags:
                speech_flags.append(flag)
        speech_review["risk_flags"] = speech_flags
        speech_review["speech_result"] = "fail"
        speech_review["speech_score"] = 0
    challenge_score = _apply_speech_review_to_machine_scores(
        challenge_score=challenge_score,
        risk_flags=risk_flags,
        speech_review=speech_review,
    )
    if challenge_score < 60 and "challenge_failed" not in risk_flags:
        risk_flags.append("challenge_failed")
    if spoken_code_required and speech_review.get("speech_result") == "pass":
        liveness_score = min(100, max(liveness_score, 88))
    elif spoken_code_required and speech_review.get("speech_result") == "unclear":
        liveness_score = max(0, min(liveness_score, 82))
    elif spoken_code_required and speech_review.get("speech_result") == "fail":
        liveness_score = max(0, min(liveness_score, 58))

    recommended_decision, recommended_next_step, confidence_band, summary = _resolve_machine_review_outcome(
        liveness_score=liveness_score,
        face_match_score=face_match_score,
        challenge_score=challenge_score,
        risk_flags=risk_flags,
        spoken_code_required=spoken_code_required,
        speech_review=speech_review,
        success_summary="动作挑战、Silent-Face 防翻拍和 faster-whisper 语音口令都通过，系统已自动通过",
        retry_summary="动作挑战、Silent-Face 防翻拍或语音口令未过，建议重新补录一段完整视频",
    )

    return {
        "provider": provider_result.get("provider") or VERIFICATION_PROVIDER_LOCAL_OSS,
        "provider_version": provider_result.get("provider_version") or "local-oss-v1",
        "evaluated_at": now.isoformat(sep=" "),
        "attempt": int(attempt),
        "file_name": file_name,
        "content_type": content_type,
        "file_size_bytes": int(file_size_bytes),
        "challenge_phrase": challenge_phrase,
        "liveness_score": liveness_score,
        "face_match_score": face_match_score,
        "challenge_score": challenge_score,
        "replay_attack_score": provider_result.get("replay_attack_score"),
        "screen_risk_score": provider_result.get("screen_risk_score"),
        "spoofing_risk_score": provider_result.get("spoofing_risk_score"),
        "deepfake_risk_score": provider_result.get("deepfake_risk_score"),
        "deepfake_analysis_status": provider_result.get("deepfake_analysis_status"),
        "deepfake_temporal_score": provider_result.get("deepfake_temporal_score"),
        "deepfake_artifact_score": provider_result.get("deepfake_artifact_score"),
        "deepfake_sampled_frame_count": provider_result.get("deepfake_sampled_frame_count"),
        "deepfake_face_frame_count": provider_result.get("deepfake_face_frame_count"),
        "photo_edit_risk_score": provider_result.get("photo_edit_risk_score"),
        "photo_edit_analysis_status": provider_result.get("photo_edit_analysis_status"),
        "skin_smoothing_risk_score": provider_result.get("skin_smoothing_risk_score"),
        "beauty_filter_risk_score": provider_result.get("beauty_filter_risk_score"),
        "face_shape_delta_score": provider_result.get("face_shape_delta_score"),
        "photo_edit_reference_face_count": provider_result.get("photo_edit_reference_face_count"),
        "photo_edit_live_face_frame_count": provider_result.get("photo_edit_live_face_frame_count"),
        "photo_edit_reference_source_count": provider_result.get("photo_edit_reference_source_count"),
        "photo_edit_edited_reference_count": provider_result.get("photo_edit_edited_reference_count"),
        "motion_score": provider_result.get("motion_score"),
        "face_presence_score": provider_result.get("face_presence_score"),
        "sampled_frame_count": provider_result.get("sampled_frame_count"),
        "valid_face_frame_count": provider_result.get("valid_face_frame_count"),
        "reference_face_source_count": provider_result.get("reference_face_source_count"),
        "reference_face_count": provider_result.get("reference_face_count"),
        "matched_face_frame_count": provider_result.get("matched_face_frame_count"),
        "best_face_similarity": provider_result.get("best_face_similarity"),
        "face_match_analysis_status": provider_result.get("face_match_analysis_status"),
        "has_audio_track": provider_result.get("has_audio_track"),
        "liveness_result": _score_result(liveness_score),
        "face_match_result": _score_result(face_match_score),
        "challenge_result": _score_result(challenge_score, pass_threshold=80, fail_threshold=60),
        "required_actions": required_actions,
        "completed_actions": sorted(completed_actions),
        "capture_mode": action_result.get("capture_mode") or action_challenge.get("capture_mode") or None,
        "spoken_code": spoken_code,
        "speech_provider": speech_review.get("provider"),
        "speech_score": speech_review.get("speech_score"),
        "speech_result": speech_review.get("speech_result"),
        "spoken_code_match": speech_review.get("code_match"),
        "transcript_excerpt": speech_review.get("transcript_excerpt"),
        "audio_video_sync_score": speech_review.get("audio_video_sync_score"),
        "risk_flags": risk_flags,
        "recommended_decision": recommended_decision,
        "recommended_next_step": recommended_next_step,
        "confidence_band": confidence_band,
        "summary": summary,
    }


def _run_machine_review(
    *,
    attempt: int,
    file_name: str,
    content_type: str,
    file_size_bytes: int,
    challenge_phrase: str | None,
    profile_id: int | None,
    source_dsn: str | None,
    source_table_name: str | None,
    video_path: Path | None = None,
    metadata: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    _machine_review_provider_name()
    return _local_oss_machine_review(
        attempt=attempt,
        file_name=file_name,
        content_type=content_type,
        file_size_bytes=file_size_bytes,
        challenge_phrase=challenge_phrase,
        profile_id=profile_id,
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        video_path=video_path,
        metadata=metadata,
        now=now,
    )


def _merge_machine_review_metadata(metadata: dict[str, Any], machine_review: dict[str, Any]) -> dict[str, Any]:
    merged = _normalize_metadata(metadata)
    runtime = _normalize_metadata(merged.get(MACHINE_RUNTIME_METADATA_KEY))
    history = list(runtime.get("machine_review_history") or [])
    history.append(machine_review)
    runtime.update(
        {
            "machine_review": machine_review,
            "machine_review_history": history[-10:],
            "recommended_decision": machine_review.get("recommended_decision"),
            "recommended_next_step": machine_review.get("recommended_next_step"),
            "confidence_band": machine_review.get("confidence_band"),
            "verification_provider": machine_review.get("provider"),
            "auto_review_applied": machine_review.get("recommended_decision") in REVIEW_DECISIONS,
        }
    )
    merged[MACHINE_RUNTIME_METADATA_KEY] = runtime
    return merged


def _apply_machine_triage(
    conn,
    *,
    submission_id: str,
    submission_snapshot: dict[str, Any],
    metadata: dict[str, Any],
    machine_review: dict[str, Any],
    now: datetime,
) -> None:
    merged_metadata = _merge_machine_review_metadata(metadata, machine_review)
    recommended_decision = str(machine_review.get("recommended_decision") or "").strip().lower()
    sync_result: dict[str, Any] | None = None
    latest_sync_status: str | None = None
    latest_sync_error: str | None = None
    review_note: str | None = None
    reviewer_id: str | None = None
    reviewed_at: datetime | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    next_status = SUBMISSION_STATUS_UNDER_REVIEW
    review_decision: str | None = None

    if recommended_decision == REVIEW_DECISION_APPROVE:
        reviewer_id = SYSTEM_AUTO_REVIEWER_ID
        review_decision = REVIEW_DECISION_APPROVE
        review_note = str(machine_review.get("summary") or "").strip() or None
        reviewed_at = now
        approved_at = now
        next_status = SUBMISSION_STATUS_APPROVED
        merged_metadata = append_workflow_history(
            merged_metadata,
            event_type="photo_review_approved",
            occurred_at=now,
            payload={"decision": REVIEW_DECISION_APPROVE, "auto_review": True},
        )
        sync_result = _sync_live_video_status_to_profile(submission_snapshot, reviewed_at=now)
        latest_sync_status = sync_result.get("status")
        if sync_result.get("status") != "synced":
            latest_sync_error = str(sync_result.get("reason") or "").strip() or None
    elif recommended_decision == REVIEW_DECISION_REQUEST_RESUBMISSION:
        reviewer_id = SYSTEM_AUTO_REVIEWER_ID
        review_decision = REVIEW_DECISION_REQUEST_RESUBMISSION
        review_note = str(machine_review.get("summary") or "").strip() or None
        reviewed_at = now
        next_status = SUBMISSION_STATUS_RESUBMISSION_REQUIRED
        merged_metadata = append_workflow_history(
            merged_metadata,
            event_type="photo_review_resubmission_required",
            occurred_at=now,
            payload={"decision": REVIEW_DECISION_REQUEST_RESUBMISSION, "auto_review": True},
        )
    elif _submission_has_photo_review_task(submission_snapshot):
        merged_metadata = append_workflow_history(
            merged_metadata,
            event_type="photo_review_under_review",
            occurred_at=now,
            payload={"decision": REVIEW_DECISION_MANUAL_REVIEW, "auto_review": False},
        )

    runtime = _normalize_metadata(merged_metadata.get(MACHINE_RUNTIME_METADATA_KEY))
    runtime["profile_sync"] = sync_result
    merged_metadata[MACHINE_RUNTIME_METADATA_KEY] = runtime

    if review_decision:
        review_metadata = {
            "auto_review": True,
            "machine_review": machine_review,
        }
        if sync_result:
            review_metadata["profile_sync"] = sync_result
        conn.execute(
            """
            INSERT INTO verification_reviews (
              submission_id, reviewer_id, decision, review_note,
              liveness_result, face_match_result, profile_consistency_result,
              metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                submission_id,
                reviewer_id,
                review_decision,
                review_note,
                machine_review.get("liveness_result"),
                machine_review.get("face_match_result"),
                None,
                json_dumps(review_metadata),
                now,
            ),
        )

    conn.execute(
        """
        UPDATE verification_submissions
        SET status = ?,
            review_decision = ?,
            review_note = ?,
            reviewer_id = ?,
            latest_sync_status = ?,
            latest_sync_error = ?,
            reviewed_at = ?,
            approved_at = ?,
            rejected_at = ?,
            metadata_json = ?,
            updated_at = ?
        WHERE submission_id = ?
        """,
        (
            next_status,
            review_decision,
            review_note,
            reviewer_id,
            latest_sync_status,
            latest_sync_error,
            reviewed_at,
            approved_at,
            rejected_at,
            json_dumps(merged_metadata),
            now,
            submission_id,
        ),
    )
    updated = get_verification_submission(conn, submission_id)
    if updated and review_decision == REVIEW_DECISION_REQUEST_RESUBMISSION:
        _maybe_record_submission_notification(
            conn,
            updated,
            notification_type=NOTIFICATION_TYPE_RESUBMISSION_REQUIRED,
            note=review_note,
            now=now,
        )
    elif updated and review_decision == REVIEW_DECISION_APPROVE:
        _maybe_record_submission_notification(
            conn,
            updated,
            notification_type=NOTIFICATION_TYPE_APPROVED,
            note=review_note,
            now=now,
        )


def _submit_into_existing_request(
    conn,
    current: dict[str, Any],
    *,
    user_id: str,
    video_base64: str,
    file_name: str,
    content_type: str | None,
    challenge_token: str | None,
    challenge_phrase: str | None,
    metadata: dict[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    if _as_text(current.get("user_id")) != _as_text(user_id):
        raise ValueError("user_id does not own this verification submission")
    if _as_text(current.get("status")) != SUBMISSION_STATUS_AWAITING_SUBMISSION:
        raise ValueError("verification submission is not awaiting first upload")

    merged_metadata = _normalize_metadata(current.get("metadata"))
    merged_metadata.update(_normalize_metadata(metadata))
    next_challenge_phrase = str(challenge_phrase).strip() if challenge_phrase else current.get("challenge_phrase")
    if challenge_token:
        merged_metadata, next_challenge_phrase = _validate_live_challenge_submission(
            user_id=str(user_id).strip(),
            profile_id=int(current.get("profile_id")) if current.get("profile_id") is not None else None,
            challenge_token=str(challenge_token),
            metadata=merged_metadata,
            now=now,
        )
    merged_metadata = append_workflow_history(
        merged_metadata,
        event_type="photo_review_submission_received",
        occurred_at=now,
        payload={"attempt": 1},
    )

    video_bytes, inferred_content_type = _decode_video_bytes(video_base64)
    safe_file_name = _sanitize_file_name(file_name)
    normalized_content_type = _validate_video_metadata(safe_file_name, content_type or inferred_content_type)
    stored_asset = _write_video_asset(
        str(current["submission_id"]),
        attempt=1,
        file_name=safe_file_name,
        content_type=normalized_content_type,
        video_bytes=video_bytes,
        now=now,
    )
    try:
        asset_id = _insert_asset_row(
            conn,
            str(current["submission_id"]),
            stored_asset,
            attempt=1,
            now=now,
            metadata=_normalize_metadata(metadata),
        )
        conn.execute(
            """
            UPDATE verification_submissions
            SET status = ?,
                challenge_phrase = ?,
                latest_asset_id = ?,
                latest_sync_status = NULL,
                latest_sync_error = NULL,
                submitted_at = ?,
                metadata_json = ?,
                updated_at = ?
            WHERE submission_id = ?
            """,
            (
                SUBMISSION_STATUS_SUBMITTED,
                next_challenge_phrase,
                asset_id,
                now,
                json_dumps(merged_metadata),
                now,
                str(current["submission_id"]),
            ),
        )
        if _auto_triage_enabled():
            submission_snapshot = {
                "submission_id": str(current["submission_id"]),
                "user_id": str(current["user_id"]),
                "profile_id": current.get("profile_id"),
                "source_dsn": current.get("source_dsn"),
                "source_table_name": current.get("source_table_name"),
                "metadata": merged_metadata,
                PHOTO_REVIEW_METADATA_KEY: merged_metadata.get(PHOTO_REVIEW_METADATA_KEY),
            }
            machine_review = _run_machine_review(
                attempt=1,
                file_name=safe_file_name,
                content_type=normalized_content_type,
                file_size_bytes=len(video_bytes),
                challenge_phrase=next_challenge_phrase,
                profile_id=int(current.get("profile_id")) if current.get("profile_id") is not None else None,
                source_dsn=current.get("source_dsn"),
                source_table_name=current.get("source_table_name"),
                video_path=_storage_root() / str(stored_asset["storage_key"]),
                metadata=merged_metadata,
                now=now,
            )
            _apply_machine_triage(
                conn,
                submission_id=str(current["submission_id"]),
                submission_snapshot=submission_snapshot,
                metadata=merged_metadata,
                machine_review=machine_review,
                now=now,
            )
        conn.commit()
    except Exception:  # noqa: BLE001
        conn.rollback()
        _remove_stored_asset(stored_asset.get("storage_key"))
        raise
    updated = get_verification_submission(conn, str(current["submission_id"]))
    assert updated is not None
    return updated


def submit_live_video_verification(
    conn,
    *,
    user_id: str,
    video_base64: str,
    file_name: str,
    submission_id: str | None = None,
    content_type: str | None = None,
    profile_id: int | None = None,
    source_dsn: str | None = None,
    source_table_name: str | None = None,
    challenge_token: str | None = None,
    challenge_phrase: str | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _current_time(now)
    if not str(user_id).strip():
        raise ValueError("user_id is required")
    attachable = _find_pending_photo_review_request(
        conn,
        user_id=str(user_id).strip(),
        profile_id=int(profile_id) if profile_id is not None else None,
        source_dsn=str(source_dsn).strip() if source_dsn else None,
        source_table_name=str(source_table_name).strip() if source_table_name else None,
        submission_id=str(submission_id).strip() if submission_id else None,
    )
    if attachable:
        return _submit_into_existing_request(
            conn,
            attachable,
            user_id=str(user_id).strip(),
            video_base64=video_base64,
            file_name=file_name,
            content_type=content_type,
            challenge_token=challenge_token,
            challenge_phrase=challenge_phrase,
            metadata=metadata,
            now=ts,
        )
    normalized_metadata = _normalize_metadata(metadata)
    resolved_challenge_phrase = str(challenge_phrase).strip() if challenge_phrase else None
    if challenge_token:
        normalized_metadata, resolved_challenge_phrase = _validate_live_challenge_submission(
            user_id=str(user_id).strip(),
            profile_id=int(profile_id) if profile_id is not None else None,
            challenge_token=str(challenge_token),
            metadata=normalized_metadata,
            now=ts,
        )
    video_bytes, inferred_content_type = _decode_video_bytes(video_base64)
    safe_file_name = _sanitize_file_name(file_name)
    normalized_content_type = _validate_video_metadata(safe_file_name, content_type or inferred_content_type)
    submission_id = _generate_submission_id()
    stored_asset = _write_video_asset(
        submission_id,
        attempt=1,
        file_name=safe_file_name,
        content_type=normalized_content_type,
        video_bytes=video_bytes,
        now=ts,
    )
    try:
        conn.execute(
            """
            INSERT INTO verification_submissions (
              submission_id, verification_type, user_id, profile_id, source_dsn, source_table_name,
              status, resubmission_count, challenge_phrase, review_decision, review_note, reviewer_id,
              latest_asset_id, latest_sync_status, latest_sync_error, submitted_at, reviewed_at,
              approved_at, rejected_at, metadata_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, ?, NULL, NULL, NULL, ?, ?, ?)
            """,
            (
                submission_id,
                VERIFICATION_TYPE_LIVE_VIDEO,
                str(user_id).strip(),
                int(profile_id) if profile_id is not None else None,
                str(source_dsn).strip() if source_dsn else None,
                str(source_table_name).strip() if source_table_name else None,
                SUBMISSION_STATUS_SUBMITTED,
                0,
                resolved_challenge_phrase,
                ts,
                json_dumps(normalized_metadata),
                ts,
                ts,
            ),
        )
        asset_id = _insert_asset_row(conn, submission_id, stored_asset, attempt=1, now=ts, metadata=normalized_metadata)
        conn.execute(
            """
            UPDATE verification_submissions
            SET latest_asset_id = ?
            WHERE submission_id = ?
            """,
            (asset_id, submission_id),
        )
        if _auto_triage_enabled():
            submission_snapshot = {
                "submission_id": submission_id,
                "user_id": str(user_id).strip(),
                "profile_id": int(profile_id) if profile_id is not None else None,
                "source_dsn": str(source_dsn).strip() if source_dsn else None,
                "source_table_name": str(source_table_name).strip() if source_table_name else None,
                "metadata": normalized_metadata,
            }
            machine_review = _run_machine_review(
                attempt=1,
                file_name=safe_file_name,
                content_type=normalized_content_type,
                file_size_bytes=len(video_bytes),
                challenge_phrase=resolved_challenge_phrase,
                profile_id=int(profile_id) if profile_id is not None else None,
                source_dsn=str(source_dsn).strip() if source_dsn else None,
                source_table_name=str(source_table_name).strip() if source_table_name else None,
                video_path=_storage_root() / str(stored_asset["storage_key"]),
                metadata=normalized_metadata,
                now=ts,
            )
            _apply_machine_triage(
                conn,
                submission_id=submission_id,
                submission_snapshot=submission_snapshot,
                metadata=normalized_metadata,
                machine_review=machine_review,
                now=ts,
            )
        conn.commit()
    except Exception:  # noqa: BLE001
        conn.rollback()
        _remove_stored_asset(stored_asset.get("storage_key"))
        raise
    created = get_verification_submission(conn, submission_id)
    assert created is not None
    return created


def resubmit_live_video_verification(
    conn,
    submission_id: str,
    *,
    user_id: str,
    video_base64: str,
    file_name: str,
    content_type: str | None = None,
    challenge_token: str | None = None,
    challenge_phrase: str | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _get_submission_row(conn, submission_id)
    if not current:
        raise ValueError("verification submission not found")
    if str(current.get("user_id") or "") != str(user_id):
        raise ValueError("user_id does not own this verification submission")
    if str(current.get("status") or "") not in RESUBMITTABLE_STATUSES:
        raise ValueError("verification submission is not waiting for resubmission")

    ts = _current_time(now)
    video_bytes, inferred_content_type = _decode_video_bytes(video_base64)
    safe_file_name = _sanitize_file_name(file_name)
    normalized_content_type = _validate_video_metadata(safe_file_name, content_type or inferred_content_type)
    attempt = int(current.get("resubmission_count") or 0) + 2
    stored_asset = _write_video_asset(
        submission_id,
        attempt=attempt,
        file_name=safe_file_name,
        content_type=normalized_content_type,
        video_bytes=video_bytes,
        now=ts,
    )
    merged_metadata = _normalize_metadata(json_loads(current.get("metadata_json"), {}))
    merged_metadata.update(_normalize_metadata(metadata))
    next_challenge_phrase = str(challenge_phrase).strip() if challenge_phrase else current.get("challenge_phrase")
    if challenge_token:
        merged_metadata, next_challenge_phrase = _validate_live_challenge_submission(
            user_id=str(user_id).strip(),
            profile_id=int(current.get("profile_id")) if current.get("profile_id") is not None else None,
            challenge_token=str(challenge_token),
            metadata=merged_metadata,
            now=ts,
        )
    if _normalize_metadata(merged_metadata.get(PHOTO_REVIEW_METADATA_KEY)).get("task_kind") == "photo_review":
        merged_metadata = append_workflow_history(
            merged_metadata,
            event_type="photo_review_resubmitted",
            occurred_at=ts,
            payload={"attempt": attempt},
        )
    try:
        asset_id = _insert_asset_row(conn, submission_id, stored_asset, attempt=attempt, now=ts, metadata=_normalize_metadata(metadata))
        conn.execute(
            """
            UPDATE verification_submissions
            SET status = ?,
                resubmission_count = ?,
                challenge_phrase = ?,
                review_decision = NULL,
                review_note = NULL,
                reviewer_id = NULL,
                latest_asset_id = ?,
                latest_sync_status = NULL,
                latest_sync_error = NULL,
                submitted_at = ?,
                reviewed_at = NULL,
                approved_at = NULL,
                rejected_at = NULL,
                metadata_json = ?,
                updated_at = ?
            WHERE submission_id = ?
            """,
            (
                SUBMISSION_STATUS_SUBMITTED,
                int(current.get("resubmission_count") or 0) + 1,
                next_challenge_phrase,
                asset_id,
                ts,
                json_dumps(merged_metadata),
                ts,
                submission_id,
            ),
        )
        if _auto_triage_enabled():
            submission_snapshot = {
                "submission_id": submission_id,
                "user_id": current.get("user_id"),
                "profile_id": current.get("profile_id"),
                "source_dsn": current.get("source_dsn"),
                "source_table_name": current.get("source_table_name"),
                "metadata": merged_metadata,
            }
            machine_review = _run_machine_review(
                attempt=attempt,
                file_name=safe_file_name,
                content_type=normalized_content_type,
                file_size_bytes=len(video_bytes),
                challenge_phrase=next_challenge_phrase,
                profile_id=int(current.get("profile_id")) if current.get("profile_id") is not None else None,
                source_dsn=current.get("source_dsn"),
                source_table_name=current.get("source_table_name"),
                video_path=_storage_root() / str(stored_asset["storage_key"]),
                metadata=merged_metadata,
                now=ts,
            )
            _apply_machine_triage(
                conn,
                submission_id=submission_id,
                submission_snapshot=submission_snapshot,
                metadata=merged_metadata,
                machine_review=machine_review,
                now=ts,
            )
        conn.commit()
    except Exception:  # noqa: BLE001
        conn.rollback()
        _remove_stored_asset(stored_asset.get("storage_key"))
        raise
    updated = get_verification_submission(conn, submission_id)
    assert updated is not None
    return updated


def _reference_face_candidate_limit() -> int:
    try:
        value = int(os.environ.get("HER_VERIFICATION_REFERENCE_FACE_CANDIDATE_LIMIT", DEFAULT_REFERENCE_FACE_CANDIDATE_LIMIT))
    except (TypeError, ValueError):
        value = DEFAULT_REFERENCE_FACE_CANDIDATE_LIMIT
    return max(1, min(value, 12))


def _load_profile_reference_face_sources(
    *,
    profile_id: int | None,
    source_dsn: str | None,
    source_table_name: str | None,
) -> list[str]:
    normalized_profile_id = int(profile_id) if profile_id is not None else None
    normalized_source_dsn, profile_table = resolve_profile_source(source_dsn, source_table_name)
    if normalized_profile_id is None or not normalized_source_dsn or not profile_table:
        return []
    return list_profile_photo_sources(
        source_dsn=normalized_source_dsn,
        source_table_name=profile_table,
        profile_id=normalized_profile_id,
        limit=_reference_face_candidate_limit(),
    )


def _sync_live_video_status_to_profile(submission: dict[str, Any], *, reviewed_at: datetime) -> dict[str, Any]:
    profile_id = submission.get("profile_id")
    source_dsn, table_name = resolve_profile_source(submission.get("source_dsn"), submission.get("source_table_name"))
    if profile_id is None or not source_dsn or not table_name:
        return {"status": "skipped", "reason": "profile source is not configured"}
    sync_result = apply_profile_updates(
        source_dsn=source_dsn,
        source_table_name=table_name,
        profile_id=int(profile_id),
        updates={
            "photo_verification_level": "live_video_verified",
            "live_video_verified": 1,
            "updated_at": reviewed_at,
        },
    )
    if sync_result.get("status") == "skipped":
        raise ValueError(f"profile table {table_name} has no live-video verification fields")
    return sync_result


def review_live_video_verification(
    conn,
    submission_id: str,
    reviewer_id: str,
    *,
    decision: str,
    review_note: str | None = None,
    liveness_result: str | None = None,
    face_match_result: str | None = None,
    profile_consistency_result: str | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = _get_submission_row(conn, submission_id)
    if not current:
        raise ValueError("verification submission not found")
    if str(current.get("status") or "") not in ACTIVE_REVIEWABLE_STATUSES:
        raise ValueError("verification submission is not awaiting review")
    normalized_decision = str(decision or "").strip().lower()
    if normalized_decision not in REVIEW_DECISIONS:
        raise ValueError("decision must be approve, reject, or request_resubmission")
    if not str(reviewer_id or "").strip():
        raise ValueError("reviewer_id is required")

    ts = _current_time(now)
    sync_result: dict[str, Any] | None = None
    next_status = SUBMISSION_STATUS_REJECTED
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    if normalized_decision == REVIEW_DECISION_APPROVE:
        sync_result = _sync_live_video_status_to_profile(current, reviewed_at=ts)
        next_status = SUBMISSION_STATUS_APPROVED
        approved_at = ts
    elif normalized_decision == REVIEW_DECISION_REQUEST_RESUBMISSION:
        next_status = SUBMISSION_STATUS_RESUBMISSION_REQUIRED
    else:
        next_status = SUBMISSION_STATUS_REJECTED
        rejected_at = ts

    review_metadata = _normalize_metadata(metadata)
    if sync_result:
        review_metadata["profile_sync"] = sync_result
    merged_submission_metadata = _normalize_metadata(json_loads(current.get("metadata_json"), {}))
    if _normalize_metadata(merged_submission_metadata.get(PHOTO_REVIEW_METADATA_KEY)).get("task_kind") == "photo_review":
        event_type = "photo_review_under_review"
        if normalized_decision == REVIEW_DECISION_APPROVE:
            event_type = "photo_review_approved"
        elif normalized_decision == REVIEW_DECISION_REQUEST_RESUBMISSION:
            event_type = "photo_review_resubmission_required"
        elif normalized_decision == REVIEW_DECISION_REJECT:
            event_type = "photo_review_rejected"
        merged_submission_metadata = append_workflow_history(
            merged_submission_metadata,
            event_type=event_type,
            occurred_at=ts,
            payload={"decision": normalized_decision, "reviewer_id": str(reviewer_id).strip()},
        )

    conn.execute(
        """
        INSERT INTO verification_reviews (
          submission_id, reviewer_id, decision, review_note,
          liveness_result, face_match_result, profile_consistency_result,
          metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            submission_id,
            str(reviewer_id).strip(),
            normalized_decision,
            review_note,
            liveness_result,
            face_match_result,
            profile_consistency_result,
            json_dumps(review_metadata),
            ts,
        ),
    )
    conn.execute(
        """
        UPDATE verification_submissions
        SET status = ?,
            review_decision = ?,
            review_note = ?,
            reviewer_id = ?,
            latest_sync_status = ?,
            latest_sync_error = ?,
            reviewed_at = ?,
            approved_at = ?,
            rejected_at = ?,
            metadata_json = ?,
            updated_at = ?
        WHERE submission_id = ?
        """,
        (
            next_status,
            normalized_decision,
            review_note,
            str(reviewer_id).strip(),
            sync_result.get("status") if sync_result else None,
            sync_result.get("reason") if sync_result and sync_result.get("status") != "synced" else None,
            ts,
            approved_at,
            rejected_at,
            json_dumps(merged_submission_metadata),
            ts,
            submission_id,
        ),
    )
    conn.commit()
    updated = get_verification_submission(conn, submission_id)
    assert updated is not None
    if normalized_decision == REVIEW_DECISION_REQUEST_RESUBMISSION:
        _maybe_record_submission_notification(
            conn,
            updated,
            notification_type=NOTIFICATION_TYPE_RESUBMISSION_REQUIRED,
            note=review_note,
            now=ts,
        )
    elif normalized_decision == REVIEW_DECISION_APPROVE:
        _maybe_record_submission_notification(
            conn,
            updated,
            notification_type=NOTIFICATION_TYPE_APPROVED,
            note=review_note,
            now=ts,
        )
    elif normalized_decision == REVIEW_DECISION_REJECT:
        _maybe_record_submission_notification(
            conn,
            updated,
            notification_type=NOTIFICATION_TYPE_REJECTED,
            note=review_note,
            now=ts,
        )
    conn.commit()
    updated = get_verification_submission(conn, submission_id)
    assert updated is not None
    if sync_result:
        updated["profile_sync"] = sync_result
    return updated


__all__ = [
    "REVIEW_DECISION_APPROVE",
    "REVIEW_DECISION_REJECT",
    "REVIEW_DECISION_REQUEST_RESUBMISSION",
    "SUBMISSION_STATUS_AWAITING_SUBMISSION",
    "SUBMISSION_STATUS_APPROVED",
    "SUBMISSION_STATUS_CLOSED",
    "SUBMISSION_STATUS_FROZEN",
    "SUBMISSION_STATUS_REJECTED",
    "SUBMISSION_STATUS_RESUBMISSION_REQUIRED",
    "SUBMISSION_STATUS_SUBMITTED",
    "SUBMISSION_STATUS_UNDER_REVIEW",
    "VERIFICATION_TYPE_LIVE_VIDEO",
    "create_live_video_verification_challenge",
    "get_verification_submission",
    "list_photo_review_requests",
    "list_verification_assets",
    "list_verification_notifications",
    "list_verification_reviews",
    "list_verification_submissions",
    "request_live_video_verification",
    "resubmit_live_video_verification",
    "review_live_video_verification",
    "submit_live_video_verification",
    "sync_photo_review_request_from_risk_case",
]
