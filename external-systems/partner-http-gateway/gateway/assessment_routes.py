"""Assessment REST handlers."""

from __future__ import annotations

from typing import Any, Protocol

from assessment.service import (
    answer_assessment,
    begin_assessment,
    get_assessment_interpretation,
    get_or_create_assessment,  # 新增：断点续传
    get_xiaoya_message,        # 新增：小雅消息
    mark_xiaoya_message_read,  # 新增：标记已读
    start_assessment,
    add_xiaoya_message_to_discovery_session,  # 新增：添加小雅消息到对话历史
)

from .collected_routes import _default_profile_source
from .http_helpers import _json_safe, _parse_json_body, _query_dict, _read_body


class AssessmentGateway(Protocol):
    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False) -> Any: ...


def _resolve_user_key(gateway: AssessmentGateway, environ: dict[str, Any], body: dict[str, Any] | None = None) -> str:
    resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
    bound_user_key = str(resolved.profile_id).strip() if resolved is not None and resolved.profile_id is not None else ""
    supplied = str((body or {}).get("user_key") or _query_dict(environ).get("user_key") or "").strip()
    if bound_user_key:
        if supplied and supplied != bound_user_key:
            raise ValueError("user_key does not match current actor")
        return bound_user_key
    if not supplied:
        raise ValueError("user_key is required")
    return supplied


def rest_assessment_start(gateway: AssessmentGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    body = _parse_json_body(_read_body(environ))
    user_key = _resolve_user_key(gateway, environ, body)
    assessment_type = str(body.get("assessment_type") or "mbti_16")
    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}
    return 200, _json_safe(start_assessment(source=source, user_key=user_key, assessment_type=assessment_type))


def rest_assessment_get_or_create(gateway: AssessmentGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """断点续传：获取未完成的测评，或创建新测评

    防呆机制：用户退出App后，下次进来能接着上次的进度继续做，
    不会从第1题重新开始。
    """
    body = _parse_json_body(_read_body(environ))
    user_key = _resolve_user_key(gateway, environ, body)
    assessment_type = str(body.get("assessment_type") or "mbti_16")
    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}
    return 200, _json_safe(get_or_create_assessment(source=source, user_key=user_key, assessment_type=assessment_type))


def rest_assessment_begin(gateway: AssessmentGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    body = _parse_json_body(_read_body(environ))
    assessment_id = str(body.get("assessment_id") or "").strip()
    if not assessment_id:
        raise ValueError("assessment_id is required")
    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}
    return 200, _json_safe(begin_assessment(source=source, assessment_id=assessment_id))


def rest_assessment_answer(gateway: AssessmentGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    body = _parse_json_body(_read_body(environ))
    assessment_id = str(body.get("assessment_id") or "").strip()
    answer = str(body.get("answer") or "").strip()
    try:
        question_index = int(body.get("question_index"))
    except (TypeError, ValueError):
        raise ValueError("question_index is required")
    if not assessment_id:
        raise ValueError("assessment_id is required")
    user_key = _resolve_user_key(gateway, environ, body)
    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}
    return 200, _json_safe(
        answer_assessment(
            source=source,
            assessment_id=assessment_id,
            question_index=question_index,
            answer=answer,
            user_key=user_key,
        )
    )


def rest_assessment_interpretation(gateway: AssessmentGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    body = _parse_json_body(_read_body(environ))
    assessment_id = str(body.get("assessment_id") or "").strip()
    if not assessment_id:
        raise ValueError("assessment_id is required")
    user_key = _resolve_user_key(gateway, environ, body)
    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}
    return 200, _json_safe(
        get_assessment_interpretation(
            source=source,
            assessment_id=assessment_id,
            user_key=user_key,
        )
    )


def rest_assessment_add_labels(gateway: AssessmentGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """添加测评标签到个人标签（用户选择后添加）

    Request body:
    {
        "user_key": "123",
        "labels": ["情绪永动机", "分享欲晚期患者"]
    }

    将选中的标签添加到用户的 preferred_traits 字段。
    """
    from persona_memory_sync.persona_memory_lib import apply_persona_patch, normalize_patch

    body = _parse_json_body(_read_body(environ))
    user_key = _resolve_user_key(gateway, environ, body)

    # 获取要添加的标签
    labels = body.get("labels") or []
    if not isinstance(labels, list) or len(labels) == 0:
        return 400, {"error": {"code": "invalid_request", "message": "labels 必须是非空列表"}}

    # 过滤空字符串
    clean_labels = [str(l).strip() for l in labels if str(l).strip()]
    if not clean_labels:
        return 400, {"error": {"code": "invalid_request", "message": "没有有效的标签"}}

    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    # 添加到 preferred_traits
    try:
        result = apply_persona_patch(
            source=source,
            user_key=user_key,
            source_type="explicit",
            source_channel="assessment",
            normalized_patch=normalize_patch({"preferred_traits": clean_labels}),
            evidence_text=f"用户添加测评标签：{', '.join(clean_labels)}",
            apply_scope="persona_only",
        )
    except Exception as e:
        return 500, {"error": {"code": "internal_error", "message": str(e)}}

    return 200, {
        "user_key": user_key,
        "added_labels": clean_labels,
        "message": f"已添加 {len(clean_labels)} 个标签",
    }


def rest_assessment_get_xiaoya_message(gateway: AssessmentGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """获取小雅解读消息（用于在对话页面显示）

    Request body:
    {
        "user_key": "123"
    }

    返回：
    - has_message: bool
    - message: str (如果有消息)
    - assessment_id: str (如果有消息)
    """
    body = _parse_json_body(_read_body(environ))
    user_key = _resolve_user_key(gateway, environ, body)
    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    return 200, _json_safe(get_xiaoya_message(source=source, user_key=user_key))


def rest_assessment_mark_xiaoya_read(gateway: AssessmentGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """标记小雅消息为已读

    Request body:
    {
        "user_key": "123",
        "assessment_id": "mbti_xxx"
    }
    """
    body = _parse_json_body(_read_body(environ))
    user_key = _resolve_user_key(gateway, environ, body)
    assessment_id = str(body.get("assessment_id") or "").strip()
    if not assessment_id:
        return 400, {"error": {"code": "invalid_request", "message": "assessment_id is required"}}

    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    return 200, _json_safe(mark_xiaoya_message_read(source=source, user_key=user_key, assessment_id=assessment_id))


def rest_assessment_add_xiaoya_to_discovery(gateway: AssessmentGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """将小雅消息添加到discovery session的对话历史

    Request body:
    {
        "user_key": "123",
        "session_id": "xxx",
        "message": "亲爱的，你的测试结果出来啦！...",
        "result_data": {...}
    }

    这样小雅消息会固定在对话流中，AI也能看到。
    """
    body = _parse_json_body(_read_body(environ))
    user_key = _resolve_user_key(gateway, environ, body)
    session_id = str(body.get("session_id") or "").strip()
    message = str(body.get("message") or "").strip()
    result_data = body.get("result_data")

    if not session_id:
        return 400, {"error": {"code": "invalid_request", "message": "session_id is required"}}
    if not message:
        return 400, {"error": {"code": "invalid_request", "message": "message is required"}}

    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    try:
        result = add_xiaoya_message_to_discovery_session(
            discovery_source=source,
            session_id=session_id,
            user_key=user_key,
            message=message,
            result_data=result_data if isinstance(result_data, dict) else None,
        )
        return 200, _json_safe(result)
    except Exception as e:
        return 500, {"error": {"code": "internal_error", "message": str(e)}}


def dispatch_assessment_rest(
    gateway: AssessmentGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    # 断点续传API（推荐使用）
    if path == "/v1/assessment/get-or-create" and method == "POST":
        return rest_assessment_get_or_create(gateway, environ)
    # 旧API（仍然保留，兼容旧版本）
    if path == "/v1/assessment/start" and method == "POST":
        return rest_assessment_start(gateway, environ)
    if path == "/v1/assessment/begin" and method == "POST":
        return rest_assessment_begin(gateway, environ)
    if path == "/v1/assessment/answer" and method == "POST":
        return rest_assessment_answer(gateway, environ)
    if path == "/v1/assessment/interpretation" and method == "POST":
        return rest_assessment_interpretation(gateway, environ)
    # 新增：添加标签到个人标签
    if path == "/v1/assessment/add-labels" and method == "POST":
        return rest_assessment_add_labels(gateway, environ)
    # 新增：小雅消息相关
    if path == "/v1/assessment/xiaoya-message" and method == "POST":
        return rest_assessment_get_xiaoya_message(gateway, environ)
    if path == "/v1/assessment/xiaoya-read" and method == "POST":
        return rest_assessment_mark_xiaoya_read(gateway, environ)
    # 新增：将小雅消息添加到discovery session
    if path == "/v1/assessment/add-xiaoya-to-discovery" and method == "POST":
        return rest_assessment_add_xiaoya_to_discovery(gateway, environ)
    return None


__all__ = [
    "dispatch_assessment_rest",
    "rest_assessment_answer",
    "rest_assessment_begin",
    "rest_assessment_get_or_create",
    "rest_assessment_add_labels",  # 新增
    "rest_assessment_interpretation",
    "rest_assessment_start",
]
