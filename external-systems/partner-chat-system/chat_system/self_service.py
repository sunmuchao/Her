"""Unified self-service center payloads for verification, appeals, and risk history."""

from __future__ import annotations

from typing import Any

from her_time_utils import as_text as _as_text, unique_ordered_texts as _unique_ordered

from partner_moderation import ACTION_FREEZE, ACTION_LIMIT_CHAT, ACTION_LIMITED_EXPOSURE

from .moderation_ops import list_risk_appeals
from .profile_reviews import (
    FIELD_DISPUTE_STATUS_NONE,
    FIELD_DISPUTE_STATUS_OPEN,
    FIELD_POLICIES,
    FIELD_SUBMISSION_STATUS_APPROVED,
    FIELD_SUBMISSION_STATUS_EXPIRED,
    FIELD_SUBMISSION_STATUS_REJECTED,
    FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED,
    FIELD_SUBMISSION_STATUS_SUBMITTED,
    FIELD_SUBMISSION_STATUS_UNDER_REVIEW,
    PROFILE_REVIEW_APPEAL_STATUS_REJECTED,
    PROFILE_REVIEW_APPEAL_STATUS_SUBMITTED,
    PROFILE_REVIEW_APPEAL_STATUS_UNDER_REVIEW,
    PROFILE_REVIEW_APPEAL_STATUS_UPHELD,
    PROFILE_REVIEW_STATUS_ACTION_APPLIED,
    PROFILE_REVIEW_STATUS_DISMISSED,
    PROFILE_REVIEW_STATUS_OPEN,
    PROFILE_REVIEW_STATUS_RESOLVED,
    PROFILE_REVIEW_STATUS_UNDER_REVIEW,
    list_profile_field_verification_submissions,
    list_profile_review_case_appeals,
    list_profile_review_cases,
)
from .risk import list_risk_cases
from .verification import (
    list_photo_review_requests,
    list_verification_notifications,
    SUBMISSION_STATUS_APPROVED,
    SUBMISSION_STATUS_AWAITING_SUBMISSION,
    SUBMISSION_STATUS_CLOSED,
    SUBMISSION_STATUS_FROZEN,
    SUBMISSION_STATUS_REJECTED,
    SUBMISSION_STATUS_RESUBMISSION_REQUIRED,
    SUBMISSION_STATUS_SUBMITTED,
    SUBMISSION_STATUS_UNDER_REVIEW,
)

PHOTO_REVIEW_TITLE = "照片真实性补录"
FIELD_REVIEW_TITLE_SUFFIX = "核验"
FIELD_APPEAL_TITLE_SUFFIX = "申诉"
CHAT_RISK_APPEAL_TITLE = "聊天风控申诉"
PROFILE_REVIEW_APPEAL_TITLE = "资料一致性申诉"
FIELD_DISPUTE_TITLE = "字段核验申诉"

STATE_PENDING = "pending"
STATE_ACTION_REQUIRED = "action_required"
STATE_IN_PROGRESS = "in_progress"
STATE_COMPLETE = "complete"

FIELD_REQUEST_STATES = {
    FIELD_DISPUTE_STATUS_NONE,
    FIELD_SUBMISSION_STATUS_SUBMITTED,
    FIELD_SUBMISSION_STATUS_UNDER_REVIEW,
    FIELD_SUBMISSION_STATUS_REJECTED,
    FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED,
    FIELD_SUBMISSION_STATUS_EXPIRED,
    FIELD_SUBMISSION_STATUS_APPROVED,
}


def _item_time(item: dict[str, Any]) -> str:
    return _as_text(item.get("updated_at") or item.get("created_at") or item.get("resolved_at"))


def _status_label(status: str) -> str:
    labels = {
        SUBMISSION_STATUS_AWAITING_SUBMISSION: "待补件",
        SUBMISSION_STATUS_SUBMITTED: "审核中",
        SUBMISSION_STATUS_UNDER_REVIEW: "审核中",
        SUBMISSION_STATUS_RESUBMISSION_REQUIRED: "需补材料",
        SUBMISSION_STATUS_REJECTED: "已驳回",
        SUBMISSION_STATUS_APPROVED: "已通过",
        SUBMISSION_STATUS_FROZEN: "已冻结",
        SUBMISSION_STATUS_CLOSED: "已关闭",
        FIELD_SUBMISSION_STATUS_SUBMITTED: "待补件",
        FIELD_SUBMISSION_STATUS_UNDER_REVIEW: "审核中",
        FIELD_SUBMISSION_STATUS_APPROVED: "已核验",
        FIELD_SUBMISSION_STATUS_REJECTED: "已驳回",
        FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED: "需补材料",
        FIELD_SUBMISSION_STATUS_EXPIRED: "已过期",
        "disputed": "申诉复核中",
        PROFILE_REVIEW_STATUS_OPEN: "待处理",
        PROFILE_REVIEW_STATUS_UNDER_REVIEW: "复核中",
        PROFILE_REVIEW_STATUS_ACTION_APPLIED: "已处置",
        PROFILE_REVIEW_STATUS_DISMISSED: "已驳回",
        PROFILE_REVIEW_STATUS_RESOLVED: "已结案",
        PROFILE_REVIEW_APPEAL_STATUS_SUBMITTED: "已受理",
        PROFILE_REVIEW_APPEAL_STATUS_UNDER_REVIEW: "复核中",
        PROFILE_REVIEW_APPEAL_STATUS_UPHELD: "申诉成立",
        PROFILE_REVIEW_APPEAL_STATUS_REJECTED: "申诉驳回",
        "available": "可申诉",
        "open": "进行中",
        "under_review": "复核中",
        "upheld": "申诉成立",
        "rejected": "已驳回",
        "resolved": "已结案",
        # 新增标准认证状态标签
        "unverified": "未认证",
        "verified": "已认证",
        "pending": "审核中",
        "action_required": "待处理",
    }
    return labels.get(status, status)


def _policy(field_key: str) -> dict[str, Any]:
    return dict(FIELD_POLICIES.get(field_key, {}))


def _verification_work_state(status: str) -> str:
    if status in {SUBMISSION_STATUS_AWAITING_SUBMISSION, SUBMISSION_STATUS_RESUBMISSION_REQUIRED, SUBMISSION_STATUS_REJECTED, FIELD_SUBMISSION_STATUS_REJECTED, FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED, FIELD_SUBMISSION_STATUS_EXPIRED, "awaiting_submission"}:
        return STATE_ACTION_REQUIRED
    if status in {SUBMISSION_STATUS_SUBMITTED, SUBMISSION_STATUS_UNDER_REVIEW, FIELD_SUBMISSION_STATUS_SUBMITTED, FIELD_SUBMISSION_STATUS_UNDER_REVIEW, "disputed"}:
        return STATE_IN_PROGRESS
    if status in {SUBMISSION_STATUS_FROZEN}:
        return STATE_PENDING
    return STATE_COMPLETE


def _appeal_work_state(status: str) -> str:
    if status == "available":
        return STATE_ACTION_REQUIRED
    if status in {PROFILE_REVIEW_APPEAL_STATUS_SUBMITTED, PROFILE_REVIEW_APPEAL_STATUS_UNDER_REVIEW, "submitted", "under_review"}:
        return STATE_IN_PROGRESS
    return STATE_COMPLETE


def _review_eta_text(kind: str) -> str:
    if kind == "photo_review":
        return "通常 24 小时内"
    if kind == "field_verification":
        return "通常 1-3 个工作日"
    if kind == "appeal":
        return "通常 1-3 个工作日"
    return "视人工处理进度而定"


def _build_support_actions(*, kind: str, detail: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    primary_action = detail.get("primary_action")
    if isinstance(primary_action, dict):
        actions.append(primary_action)
    actions.append(
        {
            "kind": "contact_support",
            "label": "联系客服",
            "channel": "manual_review_queue",
            "hint": "如认为处理有误，可补充材料后申请人工复核。",
        }
    )
    if kind == "appeal":
        actions.append(
            {
                "kind": "add_evidence",
                "label": "补充材料",
                "hint": "先把说明和证明材料补全，再提交申诉。",
            }
        )
    return actions


def _photo_review_item(request: dict[str, Any]) -> dict[str, Any]:
    task = request.get("photo_review_task") or {}
    notifications = request.get("notifications") or []
    latest_review = (request.get("reviews") or [{}])[-1] if request.get("reviews") else {}
    status = _as_text(request.get("derived_status") or request.get("status"))
    trigger_reasons = _unique_ordered(task.get("reason_labels") or [request.get("request_reason")])
    required_materials = ["5-10 秒身份认证视频"]
    example_materials = list(task.get("capture_tips") or [])
    out = {
        "item_id": request.get("submission_id"),
        "item_type": "photo_review_request",
        "title": PHOTO_REVIEW_TITLE,
        "status": status,
        "status_label": _status_label(status),
        "work_state": _verification_work_state(status),
        "trigger_reasons": trigger_reasons,
        "required_materials": required_materials,
        "example_materials": example_materials,
        "review_eta": _review_eta_text("photo_review"),
        "failure_reason": _as_text((latest_review or {}).get("review_note")),
        "support_hint": "补录时尽量用自然光、正脸、无遮挡的视频。",
        "detail_ref": {
            "kind": "verification_submission",
            "submission_id": request.get("submission_id"),
        },
        "primary_action": {
            "kind": "resubmit_live_video" if status in {SUBMISSION_STATUS_RESUBMISSION_REQUIRED, SUBMISSION_STATUS_REJECTED} else "submit_live_video",
            "method": "POST",
            "path": (
                f"/v1/verifications/live-video-submissions/{request['submission_id']}/resubmit"
                if status in {SUBMISSION_STATUS_RESUBMISSION_REQUIRED, SUBMISSION_STATUS_REJECTED}
                else "/v1/verifications/live-video-submissions"
            ),
        },
        "created_at": request.get("created_at"),
        "updated_at": request.get("updated_at"),
        "raw": request,
        "notifications": notifications,
    }
    out["actions"] = _build_support_actions(kind="verification", detail=out)
    return out


def _field_review_item(
    submission: dict[str, Any],
    *,
    trigger_reasons: list[str] | None = None,
    pending_submission: bool = False,
) -> dict[str, Any]:
    field_key = _as_text(submission.get("field_key"))
    policy = _policy(field_key)
    status = "awaiting_submission" if pending_submission else _as_text(submission.get("dispute_status")) if _as_text(submission.get("dispute_status")) == FIELD_DISPUTE_STATUS_OPEN else _as_text(submission.get("status"))
    latest_review = (submission.get("reviews") or [{}])[-1] if submission.get("reviews") else {}
    required_documents = list(submission.get("required_documents") or policy.get("accepted_documents") or [])
    example_materials = list(policy.get("resubmission_examples") or [])
    reason_list = _unique_ordered(trigger_reasons or [submission.get("declared_value"), policy.get("label")])
    title = f"{policy.get('label', field_key)}{FIELD_REVIEW_TITLE_SUFFIX}"
    primary_action = {
        "kind": "submit_field_verification" if pending_submission else "resubmit_field_verification",
        "method": "POST",
        "path": (
            "/v1/profile-verifications/submissions"
            if pending_submission
            else f"/v1/profile-verifications/submissions/{submission['submission_id']}/resubmit"
        ),
    }
    if pending_submission:
        primary_action["body_template"] = {
            "field_key": field_key,
            "profile_id": submission.get("profile_id"),
            "subject_user_id": submission.get("subject_user_id"),
            "source_dsn": submission.get("source_dsn"),
            "source_table_name": submission.get("source_table_name"),
        }
    out = {
        "item_id": submission.get("submission_id"),
        "item_type": "field_verification_request" if pending_submission else "field_verification_submission",
        "field_key": field_key,
        "title": title,
        "status": status,
        "status_label": _status_label(status),
        "work_state": _verification_work_state(status),
        "trigger_reasons": reason_list,
        "required_materials": required_documents,
        "example_materials": example_materials,
        "review_eta": _review_eta_text("field_verification"),
        "failure_reason": _as_text(submission.get("dispute_reason") or (latest_review or {}).get("review_note")),
        "support_hint": "把材料、说明和原始声明尽量对应起来，避免前后说法不一致。",
        "detail_ref": {
            "kind": "field_verification_submission",
            "submission_id": submission.get("submission_id"),
            "source_dsn": submission.get("source_dsn"),
            "source_table_name": submission.get("source_table_name"),
        },
        "primary_action": primary_action,
        "created_at": submission.get("created_at"),
        "updated_at": submission.get("updated_at"),
        "raw": submission,
    }
    out["actions"] = _build_support_actions(kind="verification", detail=out)
    return out


def _appeal_common_item(
    *,
    item_id: Any,
    target_type: str,
    target_id: str,
    title: str,
    status: str,
    reason_text: str,
    trigger_reasons: list[str] | None,
    required_materials: list[str],
    example_materials: list[str],
    created_at: Any,
    updated_at: Any,
    primary_action: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    out = {
        "item_id": item_id,
        "item_type": "appeal",
        "target_type": target_type,
        "target_id": target_id,
        "title": title,
        "status": status,
        "status_label": _status_label(status),
        "work_state": _appeal_work_state(status),
        "trigger_reasons": _unique_ordered(trigger_reasons or []),
        "required_materials": required_materials,
        "example_materials": example_materials,
        "review_eta": _review_eta_text("appeal"),
        "failure_reason": reason_text,
        "support_hint": "先把说明写清楚，再补截图、证明或原始材料。",
        "detail_ref": {
            "kind": target_type,
            "target_id": target_id,
        },
        "primary_action": primary_action,
        "created_at": created_at,
        "updated_at": updated_at,
        "raw": raw,
    }
    out["actions"] = _build_support_actions(kind="appeal", detail=out)
    return out


def _chat_risk_appeal_item(case: dict[str, Any], appeal: dict[str, Any] | None) -> dict[str, Any]:
    action = _as_text(case.get("applied_action") or case.get("recommended_action"))
    status = _as_text((appeal or {}).get("appeal_status")) or ("available" if action in {ACTION_LIMIT_CHAT, ACTION_FREEZE} and _as_text(case.get("status")) == "action_applied" else "resolved")
    title = CHAT_RISK_APPEAL_TITLE
    return _appeal_common_item(
        item_id=(appeal or {}).get("appeal_id") or case.get("risk_case_id"),
        target_type="chat_risk_case",
        target_id=_as_text(case.get("risk_case_id")),
        title=title,
        status=status,
        reason_text=_as_text((appeal or {}).get("resolution_note") or case.get("resolution_note") or case.get("reason_summary") or case.get("recommended_action")),
        trigger_reasons=list(case.get("signal_codes") or []),
        required_materials=["文字说明", "补充证明或截图"],
        example_materials=["聊天截图", "补充说明", "必要时可附视频或其他材料"],
        created_at=(appeal or case).get("created_at"),
        updated_at=(appeal or case).get("updated_at"),
        primary_action={
            "kind": "submit_chat_risk_appeal" if not appeal else "view_chat_risk_appeal",
            "method": "POST" if not appeal else "GET",
            "path": (
                f"/v1/chat/risk-cases/{case['risk_case_id']}/appeals"
                if not appeal
                else f"/v1/chat/risk-appeals/{appeal['appeal_id']}"
            ),
        },
        raw={"risk_case": case, "appeal": appeal},
    )


def _profile_review_appeal_item(case: dict[str, Any], appeal: dict[str, Any] | None) -> dict[str, Any]:
    action = _as_text((case.get("applied_action") or case.get("recommended_action")))
    status = _as_text((appeal or {}).get("appeal_status")) or ("available" if action == ACTION_LIMITED_EXPOSURE and _as_text(case.get("status")) in {PROFILE_REVIEW_STATUS_OPEN, PROFILE_REVIEW_STATUS_UNDER_REVIEW, PROFILE_REVIEW_STATUS_ACTION_APPLIED} else "resolved")
    reason_bits = list(case.get("rule_codes") or [])
    summaries = []
    for hit in (case.get("evidence_summary") or {}).get("rule_hits", []):
        summary = _as_text(((hit or {}).get("evidence") or {}).get("summary"))
        if summary:
            summaries.append(summary)
    return _appeal_common_item(
        item_id=(appeal or {}).get("appeal_id") or case.get("profile_review_case_id"),
        target_type="profile_review_case",
        target_id=_as_text(case.get("profile_review_case_id")),
        title=PROFILE_REVIEW_APPEAL_TITLE,
        status=status,
        reason_text=_as_text((appeal or {}).get("resolution_note") or case.get("resolution_note") or case.get("recommended_action")),
        trigger_reasons=_unique_ordered(reason_bits + summaries),
        required_materials=["文字说明", "补充材料", "必要时可附最新证明"],
        example_materials=["补充职业证明", "补充收入材料", "解释资料变化原因"],
        created_at=(appeal or case).get("created_at"),
        updated_at=(appeal or case).get("updated_at"),
        primary_action={
            "kind": "submit_profile_review_appeal" if not appeal else "view_profile_review_appeal",
            "method": "POST" if not appeal else "GET",
            "path": (
                f"/v1/profile-review/risk-cases/{case['profile_review_case_id']}/appeals"
                if not appeal
                else f"/v1/profile-review/appeals/{appeal['appeal_id']}"
            ),
        },
        raw={"profile_review_case": case, "appeal": appeal},
    )


def _field_dispute_item(submission: dict[str, Any]) -> dict[str, Any]:
    field_key = _as_text(submission.get("field_key"))
    policy = _policy(field_key)
    status = "under_review" if _as_text(submission.get("dispute_status")) == FIELD_DISPUTE_STATUS_OPEN else _as_text(submission.get("status"))
    return _appeal_common_item(
        item_id=submission.get("submission_id"),
        target_type="field_verification_submission",
        target_id=_as_text(submission.get("submission_id")),
        title=f"{policy.get('label', field_key)}{FIELD_APPEAL_TITLE_SUFFIX}",
        status=status,
        reason_text=_as_text(submission.get("dispute_reason") or submission.get("review_note")),
        trigger_reasons=[policy.get("label", field_key)],
        required_materials=["文字说明", "补充证明"],
        example_materials=list(policy.get("resubmission_examples") or []),
        created_at=submission.get("disputed_at") or submission.get("created_at"),
        updated_at=submission.get("disputed_at") or submission.get("updated_at"),
        primary_action={
            "kind": "submit_field_verification_dispute" if _as_text(submission.get("dispute_status")) != FIELD_DISPUTE_STATUS_OPEN else "view_field_verification_dispute",
            "method": "POST" if _as_text(submission.get("dispute_status")) != FIELD_DISPUTE_STATUS_OPEN else "GET",
            "path": (
                f"/v1/profile-verifications/submissions/{submission['submission_id']}/dispute"
                if _as_text(submission.get("dispute_status")) != FIELD_DISPUTE_STATUS_OPEN
                else f"/v1/profile-verifications/submissions/{submission['submission_id']}"
            ),
        },
        raw=submission,
    )


def _build_field_trigger_map(profile_cases: list[dict[str, Any]]) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    for case in profile_cases:
        reasons: list[str] = []
        for hit in (case.get("evidence_summary") or {}).get("rule_hits", []):
            summary = _as_text(((hit or {}).get("evidence") or {}).get("summary")) or _as_text((hit or {}).get("rule_code"))
            if summary:
                reasons.append(summary)
        for field_key in _unique_ordered((case.get("evidence_summary") or {}).get("required_verifications") or []):
            mapping.setdefault(field_key, []).extend(reasons or [_as_text(case.get("recommended_action"))])
    return {key: _unique_ordered(values) for key, values in mapping.items()}


# 标准认证项配置 - 用于认证状态面板展示
STANDARD_VERIFICATION_ITEMS = [
    {
        "field_key": "live_video",
        "name": "身份认证",
        "description_unverified": "录制一段简短视频完成认证",
        "description_verified": "已完成真人核验",
        "description_pending": "审核中",
    },
    {
        "field_key": "education",
        "name": "学历认证",
        "description_unverified": "上传学位证书或学信网截图",
        "description_verified": "学历已核验",
        "description_pending": "审核中",
    },
    {
        "field_key": "job",
        "name": "职业认证",
        "description_unverified": "上传工牌或在职证明",
        "description_verified": "职业已核验",
        "description_pending": "审核中",
    },
    {
        "field_key": "income",
        "name": "收入认证",
        "description_unverified": "上传近三个月收入材料",
        "description_verified": "收入已核验",
        "description_pending": "审核中",
    },
]


def normalize_field_submission_status(status: str) -> str:
    """将字段提交状态转换为标准认证状态

    标准认证状态（前端约定）：
    - verified: 已认证
    - pending: 审核中
    - action_required: 已驳回/需重提/已过期
    - unverified: 未认证
    """
    if status in {FIELD_SUBMISSION_STATUS_APPROVED}:
        return "verified"
    if status in {FIELD_SUBMISSION_STATUS_SUBMITTED, FIELD_SUBMISSION_STATUS_UNDER_REVIEW}:
        return "pending"
    if status in {FIELD_SUBMISSION_STATUS_REJECTED, FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED, FIELD_SUBMISSION_STATUS_EXPIRED}:
        return "action_required"
    return "unverified"


def _build_verification_items(
    *,
    user_id: str,
    profile_id: int | None,
    photo_requests: list[dict[str, Any]],
    field_submissions: list[dict[str, Any]],
    profile_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """构建认证状态面板 - 始终返回所有标准认证项及其正确状态

    设计理念（根治方案）：
    1. 始终返回所有标准认证项（身份、学历、职业、收入），而非只返回有任务的
    2. 统一命名规范（使用"认证"而非"核验"、"补录"等）
    3. 每个认证项根据实际提交情况返回正确的 status 和 description
    4. 前端可直接渲染，无需复杂的兜底或合并逻辑

    返回结构：
    - item_id: 认证项唯一标识
    - item_type: "verification_item"（标准认证项）
    - title: 统一的认证项名称（"身份认证"、"学历认证"等）
    - status: 标准状态（verified/pending/action_required/unverified）
    - status_label: 中文状态标签
    - description: 状态描述
    - field_key: 认证项标识符
    """
    items: list[dict[str, Any]] = []

    # 构建 field_submissions 的查询 map（field_key -> 最新提交）
    # 这里直接信任后端列表的排序结果：list_profile_field_verification_submissions
    # 已按 updated_at DESC, created_at DESC 返回。不要再次做字符串时间比较，
    # 否则在时间格式不完全一致时，旧的“审核中”记录可能覆盖新的“已驳回”记录。
    submission_by_field_key: dict[str, dict[str, Any]] = {}
    for submission in field_submissions:
        field_key = _as_text(submission.get("field_key"))
        if field_key and field_key not in submission_by_field_key:
            submission_by_field_key[field_key] = submission

    # 构建 photo_requests 的状态（身份认证）
    photo_request_status = "unverified"
    photo_request_description = "录制一段简短视频完成认证"
    if photo_requests:
        # 取最新的 photo_request
        latest_request = photo_requests[0] if photo_requests else {}
        photo_status = _as_text(latest_request.get("derived_status") or latest_request.get("status"))
        if photo_status in {SUBMISSION_STATUS_APPROVED}:
            photo_request_status = "verified"
            photo_request_description = "已完成真人核验"
        elif photo_status in {SUBMISSION_STATUS_SUBMITTED, SUBMISSION_STATUS_UNDER_REVIEW}:
            photo_request_status = "pending"
            photo_request_description = "审核中"
        elif photo_status in {SUBMISSION_STATUS_RESUBMISSION_REQUIRED, SUBMISSION_STATUS_REJECTED}:
            photo_request_status = "action_required"
            photo_request_description = "需重新提交"

    # 遍历标准认证项配置，构建完整的认证项列表
    for standard_item in STANDARD_VERIFICATION_ITEMS:
        field_key = standard_item["field_key"]
        name = standard_item["name"]

        if field_key == "live_video":
            # 身份认证（照片核验）
            latest_review = (latest_request.get("reviews") or [{}])[-1] if latest_request.get("reviews") else {}
            items.append({
                "item_id": f"verification-{user_id}-{field_key}",
                "item_type": "verification_item",
                "title": name,
                "status": photo_request_status,
                "status_label": _status_label(photo_status) if photo_status else _status_label(photo_request_status),
                "description": photo_request_description,
                "failure_reason": _as_text((latest_review or {}).get("review_note")),
                "support_hint": "请按审核意见重新录制，确保画面清晰、正脸、无遮挡。",
                "field_key": field_key,
            })
        else:
            # 字段认证（学历、职业、收入）
            submission = submission_by_field_key.get(field_key)

            if submission:
                # 有提交记录，基于实际状态
                submission_status = _as_text(submission.get("status"))
                status = normalize_field_submission_status(submission_status)
                latest_review = (submission.get("reviews") or [{}])[-1] if submission.get("reviews") else {}
                failure_reason = _as_text(
                    submission.get("dispute_reason") or (latest_review or {}).get("review_note")
                )

                # 根据状态选择描述
                if status == "verified":
                    description = standard_item["description_verified"]
                elif status == "pending":
                    description = standard_item["description_pending"]
                elif submission_status == FIELD_SUBMISSION_STATUS_REJECTED:
                    description = "已驳回"
                elif submission_status == FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED:
                    description = "需重新提交"
                elif submission_status == FIELD_SUBMISSION_STATUS_EXPIRED:
                    description = "认证已过期"
                else:
                    description = standard_item["description_unverified"]

                items.append({
                    "item_id": submission.get("submission_id"),
                    "item_type": "field_verification_submission",
                    "title": name,
                    "status": status,
                    "status_label": _status_label(submission_status),
                    "description": description,
                    "failure_reason": failure_reason,
                    "support_hint": (
                        "请根据审核意见补充更清晰、更完整的证明材料。"
                        if submission_status in {
                            FIELD_SUBMISSION_STATUS_REJECTED,
                            FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED,
                            FIELD_SUBMISSION_STATUS_EXPIRED,
                        }
                        else None
                    ),
                    "field_key": field_key,
                })
            else:
                # 无提交记录，显示未认证状态
                items.append({
                    "item_id": f"verification-{user_id}-{field_key}",
                    "item_type": "verification_item",
                    "title": name,
                    "status": "unverified",
                    "status_label": "未认证",
                    "description": standard_item["description_unverified"],
                    "field_key": field_key,
                })

    return items


def _build_appeal_items(
    *,
    chat_cases: list[dict[str, Any]],
    chat_appeals: list[dict[str, Any]],
    profile_cases: list[dict[str, Any]],
    profile_appeals: list[dict[str, Any]],
    field_submissions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    appeals_by_chat_case: dict[str, list[dict[str, Any]]] = {}
    for appeal in chat_appeals:
        appeals_by_chat_case.setdefault(_as_text(appeal.get("risk_case_id")), []).append(appeal)
    appeals_by_profile_case: dict[str, list[dict[str, Any]]] = {}
    for appeal in profile_appeals:
        appeals_by_profile_case.setdefault(_as_text(appeal.get("profile_review_case_id")), []).append(appeal)

    for case in chat_cases:
        existing = appeals_by_chat_case.get(_as_text(case.get("risk_case_id"))) or []
        if existing:
            items.append(_chat_risk_appeal_item(case, existing[0]))
        elif _as_text(case.get("status")) == "action_applied" and _as_text(case.get("applied_action") or case.get("recommended_action")) in {ACTION_LIMIT_CHAT, ACTION_FREEZE}:
            items.append(_chat_risk_appeal_item(case, None))

    for case in profile_cases:
        existing = appeals_by_profile_case.get(_as_text(case.get("profile_review_case_id"))) or []
        action = _as_text(case.get("applied_action") or case.get("recommended_action"))
        if existing:
            items.append(_profile_review_appeal_item(case, existing[0]))
        elif action == ACTION_LIMITED_EXPOSURE and _as_text(case.get("status")) in {PROFILE_REVIEW_STATUS_OPEN, PROFILE_REVIEW_STATUS_UNDER_REVIEW, PROFILE_REVIEW_STATUS_ACTION_APPLIED}:
            items.append(_profile_review_appeal_item(case, None))

    for submission in field_submissions:
        status = _as_text(submission.get("status"))
        dispute_status = _as_text(submission.get("dispute_status"))
        if dispute_status == FIELD_DISPUTE_STATUS_OPEN:
            items.append(_field_dispute_item(submission))
        elif status in {FIELD_SUBMISSION_STATUS_REJECTED, FIELD_SUBMISSION_STATUS_RESUBMISSION_REQUIRED, FIELD_SUBMISSION_STATUS_EXPIRED}:
            items.append(_field_dispute_item(submission))
        elif status == FIELD_SUBMISSION_STATUS_APPROVED and dispute_status not in {FIELD_DISPUTE_STATUS_OPEN, FIELD_DISPUTE_STATUS_NONE}:
            items.append(_field_dispute_item(submission))
    return items


def _build_risk_records(
    *,
    chat_cases: list[dict[str, Any]],
    profile_cases: list[dict[str, Any]],
    chat_appeals: list[dict[str, Any]],
    profile_appeals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    appeals_by_chat_case: dict[str, list[dict[str, Any]]] = {}
    for appeal in chat_appeals:
        appeals_by_chat_case.setdefault(_as_text(appeal.get("risk_case_id")), []).append(appeal)
    appeals_by_profile_case: dict[str, list[dict[str, Any]]] = {}
    for appeal in profile_appeals:
        appeals_by_profile_case.setdefault(_as_text(appeal.get("profile_review_case_id")), []).append(appeal)
    items: list[dict[str, Any]] = []
    for case in chat_cases:
        latest_appeal = (appeals_by_chat_case.get(_as_text(case.get("risk_case_id"))) or [None])[0]
        items.append(
            {
                "record_id": case.get("risk_case_id"),
                "record_type": "chat_risk_case",
                "status": case.get("status"),
                "status_label": _status_label(_as_text(case.get("status"))),
                "title": "聊天风险处理记录",
                "summary": _as_text(case.get("reason_summary") or case.get("resolution_note") or case.get("recommended_action")),
                "trigger_reasons": list(case.get("signal_codes") or []),
                "current_action": _as_text(case.get("applied_action") or case.get("recommended_action")),
                "appeal_status": _as_text((latest_appeal or {}).get("appeal_status")),
                "result_summary": _as_text((latest_appeal or {}).get("resolution_note") or case.get("resolution_note")),
                "created_at": case.get("created_at"),
                "updated_at": case.get("updated_at"),
                "detail_ref": {"kind": "chat_risk_case", "risk_case_id": case.get("risk_case_id")},
            }
        )
    for case in profile_cases:
        latest_appeal = (appeals_by_profile_case.get(_as_text(case.get("profile_review_case_id"))) or [None])[0]
        items.append(
            {
                "record_id": case.get("profile_review_case_id"),
                "record_type": "profile_review_case",
                "status": case.get("status"),
                "status_label": _status_label(_as_text(case.get("status"))),
                "title": "资料一致性处理记录",
                "summary": _as_text(case.get("resolution_note") or case.get("recommended_action")),
                "trigger_reasons": _unique_ordered(
                    [
                        _as_text(hit.get("rule_code"))
                        for hit in (case.get("evidence_summary") or {}).get("rule_hits", [])
                    ]
                ),
                "current_action": _as_text(case.get("applied_action") or case.get("recommended_action")),
                "appeal_status": _as_text((latest_appeal or {}).get("appeal_status")),
                "result_summary": _as_text((latest_appeal or {}).get("resolution_note") or case.get("resolution_note")),
                "created_at": case.get("created_at"),
                "updated_at": case.get("updated_at"),
                "detail_ref": {"kind": "profile_review_case", "profile_review_case_id": case.get("profile_review_case_id")},
            }
        )
    return sorted(items, key=lambda item: _item_time(item), reverse=True)


def _build_notifications(
    *,
    user_notifications: list[dict[str, Any]],
    verification_items: list[dict[str, Any]],
    appeal_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in user_notifications:
        items.append(
            {
                "notification_id": row.get("notification_id"),
                "notification_type": row.get("notification_type"),
                "title": row.get("title"),
                "body": row.get("body"),
                "status": "action_required" if _as_text(row.get("notification_type")) in {"photo_review_requested", "photo_review_resubmission_required"} else "result",
                "created_at": row.get("created_at"),
                "detail_ref": {
                    "kind": "verification_submission",
                    "submission_id": row.get("submission_id"),
                },
            }
        )
    for item in verification_items:
        if item.get("item_type") == "photo_review_request":
            continue
        work_state = _as_text(item.get("work_state"))
        if work_state in {STATE_ACTION_REQUIRED, STATE_IN_PROGRESS}:
            items.append(
                {
                    "notification_id": None,
                    "notification_type": f"{item['item_type']}_pending",
                    "title": item.get("title"),
                    "body": item.get("failure_reason") or item.get("support_hint"),
                    "status": work_state,
                    "created_at": item.get("updated_at") or item.get("created_at"),
                    "detail_ref": item.get("detail_ref"),
                }
            )
    for item in appeal_items:
        status = _as_text(item.get("status"))
        work_state = _as_text(item.get("work_state"))
        if status in {"available", PROFILE_REVIEW_APPEAL_STATUS_SUBMITTED, PROFILE_REVIEW_APPEAL_STATUS_UNDER_REVIEW, PROFILE_REVIEW_APPEAL_STATUS_UPHELD, PROFILE_REVIEW_APPEAL_STATUS_REJECTED, "submitted", "under_review", "upheld", "rejected"}:
            items.append(
                {
                    "notification_id": None,
                    "notification_type": f"{item['target_type']}_appeal_{status}",
                    "title": item.get("title"),
                    "body": item.get("failure_reason") or item.get("support_hint"),
                    "status": work_state,
                    "created_at": item.get("updated_at") or item.get("created_at"),
                    "detail_ref": item.get("detail_ref"),
                }
            )
    return sorted(items, key=lambda item: _as_text(item.get("created_at")), reverse=True)


def build_user_trust_hub(
    conn,
    *,
    user_id: str,
    profile_id: int | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    normalized_user_id = _as_text(user_id)
    if not normalized_user_id:
        raise ValueError("user_id is required")
    limit = max(1, min(int(limit), 100))
    photo_requests = list_photo_review_requests(conn, user_id=normalized_user_id, profile_id=profile_id, limit=limit)
    field_submissions = list_profile_field_verification_submissions(
        conn,
        subject_user_id=normalized_user_id,
        profile_id=profile_id,
        limit=limit,
    )
    profile_cases = list_profile_review_cases(
        conn,
        subject_user_id=normalized_user_id,
        profile_id=profile_id,
        statuses=[PROFILE_REVIEW_STATUS_OPEN, PROFILE_REVIEW_STATUS_UNDER_REVIEW, PROFILE_REVIEW_STATUS_ACTION_APPLIED, PROFILE_REVIEW_STATUS_DISMISSED, PROFILE_REVIEW_STATUS_RESOLVED],
        limit=limit,
    )
    active_profile_cases = [
        item
        for item in profile_cases
        if _as_text(item.get("status")) in {PROFILE_REVIEW_STATUS_OPEN, PROFILE_REVIEW_STATUS_UNDER_REVIEW, PROFILE_REVIEW_STATUS_ACTION_APPLIED}
    ]
    chat_cases = list_risk_cases(conn, subject_user_id=normalized_user_id, limit=limit)
    chat_appeals = list_risk_appeals(conn, subject_user_id=normalized_user_id, limit=limit * 3)
    profile_appeals = list_profile_review_case_appeals(conn, subject_user_id=normalized_user_id, limit=limit * 3)
    user_notifications = list_verification_notifications(conn, user_id=normalized_user_id, limit=limit * 5)

    verification_items = _build_verification_items(
        user_id=normalized_user_id,
        profile_id=profile_id,
        photo_requests=photo_requests,
        field_submissions=field_submissions,
        profile_cases=active_profile_cases,
    )
    appeal_items = _build_appeal_items(
        chat_cases=chat_cases,
        chat_appeals=chat_appeals,
        profile_cases=profile_cases,
        profile_appeals=profile_appeals,
        field_submissions=field_submissions,
    )
    risk_records = _build_risk_records(
        chat_cases=chat_cases,
        profile_cases=profile_cases,
        chat_appeals=chat_appeals,
        profile_appeals=profile_appeals,
    )
    notifications = _build_notifications(
        user_notifications=user_notifications,
        verification_items=verification_items,
        appeal_items=appeal_items,
    )

    pending_verification_count = len([item for item in verification_items if _as_text(item.get("work_state")) in {STATE_ACTION_REQUIRED, STATE_IN_PROGRESS}])
    pending_appeal_count = len([item for item in appeal_items if _as_text(item.get("work_state")) in {STATE_ACTION_REQUIRED, STATE_IN_PROGRESS}])
    active_risk_count = len([item for item in risk_records if _as_text(item.get("status")) not in {"dismissed", "resolved"}])

    summary = {
        "pending_verification_count": pending_verification_count,
        "pending_appeal_count": pending_appeal_count,
        "active_risk_count": active_risk_count,
        "notification_count": len(notifications),
    }
    faqs = [
        {
            "key": "why_income_verification",
            "question": "为什么要核验收入？",
            "answer": "平台只核验收入区间真实性，不展示精确收入值。",
        },
        {
            "key": "why_live_video",
            "question": "为什么要补录身份认证视频？",
            "answer": "这是为了确认照片和真人一致，降低冒用和修图风险。",
        },
        {
            "key": "why_restore_not_immediate",
            "question": "为什么不能立刻恢复曝光？",
            "answer": "风控动作需要先确认材料和申诉结果，再决定是否恢复。",
        },
    ]
    return {
        "user_id": normalized_user_id,
        "profile_id": profile_id,
        "summary": summary,
        "verification_center": {
            "items": sorted(verification_items, key=lambda item: (_as_text(item.get("status")), _item_time(item)), reverse=False),
        },
        "appeal_center": {
            "items": sorted(appeal_items, key=lambda item: (_as_text(item.get("status")), _item_time(item)), reverse=False),
        },
        "risk_records": {
            "items": risk_records,
        },
        "notifications": notifications,
        "faqs": faqs,
    }


__all__ = ["build_user_trust_hub"]
