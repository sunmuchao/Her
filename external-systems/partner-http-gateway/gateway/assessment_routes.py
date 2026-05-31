"""Assessment REST handlers."""

from __future__ import annotations

from typing import Any, Protocol

from assessment.service import (
    answer_assessment,
    begin_assessment,
    get_assessment_interpretation,
    start_assessment,
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
    assessment_type = str(body.get("assessment_type") or "big_five")
    source = _default_profile_source()
    if not source:
        return 503, {"error": {"code": "source_not_configured", "message": "数据源未配置"}}
    return 200, _json_safe(start_assessment(source=source, user_key=user_key, assessment_type=assessment_type))


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


def dispatch_assessment_rest(
    gateway: AssessmentGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v1/assessment/start" and method == "POST":
        return rest_assessment_start(gateway, environ)
    if path == "/v1/assessment/begin" and method == "POST":
        return rest_assessment_begin(gateway, environ)
    if path == "/v1/assessment/answer" and method == "POST":
        return rest_assessment_answer(gateway, environ)
    if path == "/v1/assessment/interpretation" and method == "POST":
        return rest_assessment_interpretation(gateway, environ)
    return None


__all__ = [
    "dispatch_assessment_rest",
    "rest_assessment_answer",
    "rest_assessment_begin",
    "rest_assessment_interpretation",
    "rest_assessment_start",
]
