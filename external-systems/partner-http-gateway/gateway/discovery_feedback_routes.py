"""Feedback collection API routes for discovery system."""

from __future__ import annotations

import json
from typing import Any

from discovery_system.feedback_service import infer_feedback_type, generate_feedback_options  # type: ignore[import-untyped]
from match_domain import get_trace_id

from .http_helpers import _parse_json_body


def handle_submit_feedback(
    gateway: Any,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """
    处理用户反馈提交。

    POST /v1/discovery/feedback

    Request body:
    {
        "session_id": "xxx",
        "feedback_text": "太远了（都是异地）",
        "feedback_type": "location_distance",  # optional, can be inferred
        "feedback_detail": null,  # optional, for secondary feedback
        "is_secondary": false,  # optional
        "primary_feedback_id": null  # optional, for secondary feedback
    }

    Response:
    {
        "success": true,
        "feedback_id": 123,
        "persona_updated": true,
        "criteria_adjusted": true
    }
    """
    try:
        body = _parse_json_body(environ)
        session_id = body.get("session_id")
        feedback_text = body.get("feedback_text")
        feedback_type = body.get("feedback_type") or infer_feedback_type(feedback_text)
        feedback_detail = body.get("feedback_detail")
        is_secondary = body.get("is_secondary", False)
        primary_feedback_id = body.get("primary_feedback_id")

        if not session_id or not feedback_text:
            return 400, {
                "error": {"code": "missing_params", "message": "session_id and feedback_text are required"},
                "trace_id": get_trace_id()
            }

        # TODO: 实际的反馈记录和调整逻辑
        # 这里需要调用：
        # 1. record_rejection_feedback - 记录反馈
        # 2. sync_requester_persona_memory - 写入persona
        # 3. adjust_working_criteria - 调整搜索条件

        return 200, {
            "success": True,
            "feedback_id": 123,  # mock
            "feedback_type": feedback_type,
            "persona_updated": True,
            "criteria_adjusted": True,
            "trace_id": get_trace_id()
        }

    except Exception as exc:
        return 500, {
            "error": {"code": "internal_error", "message": str(exc)},
            "trace_id": get_trace_id()
        }


def handle_skip_feedback(
    gateway: Any,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """
    处理用户跳过反馈。

    POST /v1/discovery/feedback/skip

    Request body:
    {
        "session_id": "xxx"
    }

    Response:
    {
        "success": true
    }
    """
    try:
        body = _parse_json_body(environ)
        session_id = body.get("session_id")

        if not session_id:
            return 400, {
                "error": {"code": "missing_params", "message": "session_id is required"},
                "trace_id": get_trace_id()
            }

        # TODO: 实际的跳过记录逻辑

        return 200, {
            "success": True,
            "trace_id": get_trace_id()
        }

    except Exception as exc:
        return 500, {
            "error": {"code": "internal_error", "message": str(exc)},
            "trace_id": get_trace_id()
        }


def handle_get_feedback_options(
    gateway: Any,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """
    获取反馈选项列表。

    GET /v1/discovery/feedback/options?session_id=xxx&include_secondary=false&primary_option=xxx

    Response:
    {
        "options": ["太远了（都是异地）", "年龄差距有点大", ...],
        "prompt_message": "好的，我帮你换一批新的。顺便问一句..."
    }
    """
    try:
        query = _parse_json_body(environ)
        session_id = query.get("session_id")
        include_secondary = query.get("include_secondary", False)
        primary_option = query.get("primary_option")

        if not session_id:
            return 400, {
                "error": {"code": "missing_params", "message": "session_id is required"},
                "trace_id": get_trace_id()
            }

        # TODO: 从session获取上一批候选人
        last_batch_candidates = []
        user_profile = {}

        # 生成选项
        result = generate_feedback_options(
            last_batch_candidates,
            user_profile,
            include_secondary=include_secondary,
            primary_option=primary_option
        )

        return 200, {
            "success": True,
            "options": result.get("options", []),
            "prompt_message": result.get("追问文案", ""),
            "trace_id": get_trace_id()
        }

    except Exception as exc:
        return 500, {
            "error": {"code": "internal_error", "message": str(exc)},
            "trace_id": get_trace_id()
        }