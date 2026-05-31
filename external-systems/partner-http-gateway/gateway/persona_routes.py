"""Persona patch API for user-editable tags."""

from __future__ import annotations

import os
from typing import Any, Protocol

from assessment.service import get_personality_traits
from persona_memory_sync.persona_memory_lib import apply_persona_patch, normalize_patch

from .http_helpers import _json_safe, _read_body, _parse_json_body
from .collected_routes import _default_profile_source, CollectedGateway


def rest_persona_patch(gateway: CollectedGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """PATCH /v1/persona/patch - Update user persona tags.

    Request body:
    {
        "patch": {
            "preferred_traits": ["情绪稳定", "生活规律", "喜欢运动"]
        }
    }

    Only tag fields are allowed: preferred_traits, must_have_tags, must_not_have_tags, disliked_traits.
    """
    # 1. 验证登录状态
    actor = gateway._current_actor(environ)
    if actor is None or not gateway._is_auth_session_end_user(actor):
        return 401, {"error": {"code": "unauthorized", "message": "需要登录"}}

    # 2. 获取 profile_id
    resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
    if resolved is None or resolved.profile_id is None:
        return 400, {"error": {"code": "invalid_request", "message": "缺少 profile_id"}}

    profile_id = int(resolved.profile_id)
    user_key = str(profile_id)

    # 3. 解析请求体
    body = _parse_json_body(_read_body(environ))
    if not body or "patch" not in body:
        return 400, {"error": {"code": "invalid_request", "message": "请求体需要 patch 字段"}}

    patch = body.get("patch") or {}
    if not isinstance(patch, dict):
        return 400, {"error": {"code": "invalid_request", "message": "patch 必须是字典"}}

    # 4. 只允许更新标签字段
    allowed_fields = {"preferred_traits", "must_have_tags", "must_not_have_tags", "disliked_traits"}
    filtered_patch = {k: v for k, v in patch.items() if k in allowed_fields}
    if not filtered_patch:
        return 400, {"error": {"code": "invalid_request", "message": "只允许更新标签字段"}}

    # 5. 获取数据源
    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}

    # 6. 规范化数据（将列表转为 CSV 字符串）
    normalized = normalize_patch(filtered_patch)

    # 7. 调用 apply_persona_patch 写入数据库
    try:
        result = apply_persona_patch(
            source=source,
            user_key=user_key,
            source_type="explicit",
            source_channel="profile_form",
            normalized_patch=normalized,
            evidence_text="用户手动编辑标签",
            apply_scope="persona_only",
        )
    except Exception as e:
        return 500, {"error": {"code": "internal_error", "message": str(e)}}

    # 8. 返回结果
    return 200, {
        "profile_id": profile_id,
        "applied_fields": _json_safe(result.get("applied_fields", [])),
        "skipped_fields": _json_safe(result.get("skipped_fields", [])),
    }


def dispatch_persona_rest(
    gateway: CollectedGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    """Dispatch persona REST routes."""
    if path == "/v1/persona/patch" and method == "PATCH":
        return rest_persona_patch(gateway, environ)
    if path == "/v1/persona/personality-traits" and method == "GET":
        q = (environ.get("QUERY_STRING") or "").strip()
        user_key = ""
        for part in q.split("&"):
            if part.startswith("user_key="):
                user_key = part.split("=", 1)[-1].strip()
                break
        resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
        if resolved is not None and resolved.profile_id is not None:
            user_key = str(resolved.profile_id)
        if not user_key:
            return 400, {"error": {"code": "invalid_request", "message": "user_key is required"}}
        source = _default_profile_source()
        if not source:
            return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}
        return 200, {"user_key": user_key, **_json_safe(get_personality_traits(source=source, user_key=user_key))}
    return None


__all__ = ["dispatch_persona_rest", "rest_persona_patch"]
