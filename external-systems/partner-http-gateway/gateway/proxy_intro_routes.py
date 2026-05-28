"""Proxy-intro case APIs for end-user relationship flows."""

from __future__ import annotations

import os
import re
from typing import Any, Protocol

from match_domain import get_trace_id  # noqa: E402
from matchmaking_system.proxy_intro import (  # type: ignore[import-untyped]
    close_match_case,
    create_match_case,
    dispatch_match_case_outreach,
    get_match_case,
    list_match_cases_for_participant,
    record_match_case_reply,
)
from chat_system import (  # type: ignore[import-untyped]
    create_assistant_case_layout,
    find_user_id_by_profile_id,
    get_conversation_by_case_and_key,
)

from .http_helpers import _json_safe, _parse_json_body, _parse_optional_now, _read_body


class ProxyIntroGateway(Protocol):
    def _get_case_for_actor(
        self,
        environ: dict[str, Any],
        case_id: str,
    ) -> dict[str, Any]: ...

    def _get_recommendation_subscription_for_actor(
        self,
        environ: dict[str, Any],
        subscription_id: str,
    ) -> dict[str, Any]: ...

    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False) -> Any: ...

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...

    def _with_proxy_intro(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def _counterpart_snapshot(case: dict[str, Any], viewer_profile_id: int) -> tuple[str, int | None, dict[str, Any]]:
    if int(case.get("requester_id") or 0) == int(viewer_profile_id):
        candidate_snapshot = dict(case.get("candidate_snapshot") or {})
        return (
            str(case.get("candidate_name") or candidate_snapshot.get("name") or "候选人"),
            int(case.get("candidate_id") or 0) or None,
            dict(candidate_snapshot.get("profile") or {}),
        )
    requester_snapshot = dict(case.get("requester_profile_snapshot") or {})
    self_profile = dict(requester_snapshot.get("self_profile") or {})
    return (
        str(
            self_profile.get("display_name")
            or self_profile.get("name")
            or self_profile.get("nickname")
            or "对方"
        ),
        int(case.get("requester_id") or 0) or None,
        self_profile,
    )


def _stage_label(case: dict[str, Any], *, has_main_conversation: bool) -> str:
    if has_main_conversation:
        return "已开聊"
    status = str(case.get("case_status") or "").strip()
    if status == "pending_outreach":
        return "待联系"
    if status == "awaiting_reply":
        return "等待回复"
    if status == "accepted":
        return "可聊天"
    if status == "declined":
        return "已婉拒"
    if status == "timed_out":
        return "已超时"
    if status == "closed":
        close_reason = str(case.get("close_reason") or "").strip()
        if close_reason == "handoff_completed":
            return "已开聊"
        if close_reason == "requester_cancelled":
            return "已取消"
        return "已结束"
    return status or "牵线中"


def _build_case_view(
    gateway: ProxyIntroGateway,
    case: dict[str, Any],
    *,
    viewer_profile_id: int,
) -> dict[str, Any]:
    counterpart_name, counterpart_profile_id, counterpart_profile = _counterpart_snapshot(
        case,
        viewer_profile_id,
    )
    main_conversation = gateway._with_chat(
        get_conversation_by_case_and_key,
        str(case["case_id"]),
        "main_group",
    )
    case_status = str(case.get("case_status") or "").strip()
    close_reason = str(case.get("close_reason") or "").strip()
    can_open_chat = (
        case_status == "accepted"
        or (case_status == "closed" and close_reason == "handoff_completed")
        or bool(main_conversation)
    )
    return {
        "case_id": case["case_id"],
        "subscription_id": case.get("subscription_id"),
        "recommendation_id": case.get("recommendation_id"),
        "case_status": case_status,
        "canonical_case_status": case.get("canonical_case_status"),
        "close_reason": case.get("close_reason"),
        "reply_deadline_at": case.get("reply_deadline_at"),
        "created_at": case.get("created_at"),
        "updated_at": case.get("updated_at"),
        "role": "requester" if int(case.get("requester_id") or 0) == int(viewer_profile_id) else "candidate",
        "counterpart_name": counterpart_name,
        "counterpart_profile_id": counterpart_profile_id,
        "counterpart_profile": counterpart_profile,
        "counterpart_image": counterpart_profile.get("avatar_url")
        or counterpart_profile.get("photo_url")
        or counterpart_profile.get("cover_url"),
        "safe_summary": case.get("safe_summary") or {},
        "stage_label": _stage_label(case, has_main_conversation=bool(main_conversation)),
        "can_reply": int(case.get("candidate_id") or 0) == int(viewer_profile_id) and case_status == "awaiting_reply",
        "can_open_chat": can_open_chat,
        "main_conversation_id": (
            str(main_conversation.get("conversation_id") or "").strip() if main_conversation else None
        ),
    }


def rest_proxy_intro_create_request(
    gateway: ProxyIntroGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    subscription_id = str(body.get("subscription_id") or "").strip()
    candidate_id = int(body.get("candidate_id") or 0)
    if not subscription_id:
        raise ValueError("subscription_id is required")
    if candidate_id <= 0:
        raise ValueError("candidate_id is required")
    gateway._get_recommendation_subscription_for_actor(environ, subscription_id)
    now = _parse_optional_now(body)
    created = gateway._with_proxy_intro(
        create_match_case,
        subscription_id=subscription_id,
        candidate_id=candidate_id,
        now=now,
        request_payload={
            "source": str(body.get("source") or "recommendation_detail"),
        },
    )
    case = gateway._with_proxy_intro(
        dispatch_match_case_outreach,
        case_id=str(created["case_id"]),
        now=now,
        payload={"source": str(body.get("source") or "recommendation_detail")},
    )
    principal = gateway._resolve_end_user_principal(environ, require_profile=True)
    return 201, {
        "case": _json_safe(_build_case_view(gateway, case, viewer_profile_id=int(principal.profile_id))),
        "trace_id": get_trace_id(),
    }


def rest_proxy_intro_list_mine(
    gateway: ProxyIntroGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    principal = gateway._resolve_end_user_principal(environ, require_profile=True)
    profile_id = int(principal.profile_id)
    cases = gateway._with_proxy_intro(list_match_cases_for_participant, profile_id)
    views = [_build_case_view(gateway, case, viewer_profile_id=profile_id) for case in cases]
    return 200, {
        "profile_id": profile_id,
        "cases": _json_safe(views),
        "count": len(views),
        "trace_id": get_trace_id(),
    }


def rest_proxy_intro_get_case(
    gateway: ProxyIntroGateway,
    environ: dict[str, Any],
    case_id: str,
) -> tuple[int, dict[str, Any]]:
    case = gateway._get_case_for_actor(environ, case_id)
    principal = gateway._resolve_end_user_principal(environ, require_profile=True)
    return 200, {
        "case": _json_safe(_build_case_view(gateway, case, viewer_profile_id=int(principal.profile_id))),
        "trace_id": get_trace_id(),
    }


def rest_proxy_intro_reply_case(
    gateway: ProxyIntroGateway,
    environ: dict[str, Any],
    case_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    principal = gateway._resolve_end_user_principal(environ, require_profile=True)
    case = gateway._get_case_for_actor(environ, case_id)
    if int(case.get("candidate_id") or 0) != int(principal.profile_id):
        raise ValueError("只有被推荐的一方可以回复这条牵线")
    reply_type = str(body.get("reply_type") or "").strip().lower()
    if reply_type not in {"accepted", "declined"}:
        raise ValueError("reply_type must be accepted or declined")
    updated = gateway._with_proxy_intro(
        record_match_case_reply,
        case_id=case_id,
        reply_type=reply_type,
        now=_parse_optional_now(body),
        reply_payload={"source": str(body.get("source") or "relationships_page")},
    )
    return 200, {
        "case": _json_safe(_build_case_view(gateway, updated, viewer_profile_id=int(principal.profile_id))),
        "trace_id": get_trace_id(),
    }


def rest_proxy_intro_open_chat(
    gateway: ProxyIntroGateway,
    environ: dict[str, Any],
    case_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    principal = gateway._resolve_end_user_principal(environ, require_profile=True)
    case = gateway._get_case_for_actor(environ, case_id)
    main_conversation = gateway._with_chat(get_conversation_by_case_and_key, case_id, "main_group")
    close_reason = str(case.get("close_reason") or "").strip()
    case_status = str(case.get("case_status") or "").strip()
    if not main_conversation and case_status != "accepted":
        if not (case_status == "closed" and close_reason == "handoff_completed"):
            raise ValueError("双方还没都同意，暂时不能开始聊天")

    if main_conversation and case_status == "accepted":
        case = gateway._with_proxy_intro(
            close_match_case,
            case_id=case_id,
            close_reason="handoff_completed",
            now=_parse_optional_now(body),
            close_payload={"opened_by_profile_id": int(principal.profile_id), "reused_existing_conversation": True},
        )
        case_status = str(case.get("case_status") or "").strip()

    requester_user_id = gateway._with_chat(find_user_id_by_profile_id, int(case["requester_id"]))
    candidate_user_id = gateway._with_chat(find_user_id_by_profile_id, int(case["candidate_id"]))
    if not requester_user_id or not candidate_user_id:
        raise ValueError("用户账号映射缺失，暂时无法开聊")

    if not main_conversation:
        relation_key = str(case.get("relation_key") or "").strip()
        if not relation_key:
            raise ValueError("关系键缺失，暂时无法开聊")
        layout = gateway._with_chat(
            create_assistant_case_layout,
            case_id=case_id,
            relation_key=relation_key,
            participant_a_id=str(requester_user_id),
            participant_b_id=str(candidate_user_id),
            agent_id=str(os.environ.get("HER_MATCHMAKER_AGENT_ID") or "agent-c"),
            metadata={"source": "proxy_intro_handoff"},
            now=_parse_optional_now(body),
        )
        conversations = list(layout.get("conversations") or [])
        main_conversation = next(
            (
                item
                for item in conversations
                if str(item.get("channel_key") or "").strip() == "main_group"
            ),
            None,
        )
        if case_status == "accepted":
            case = gateway._with_proxy_intro(
                close_match_case,
                case_id=case_id,
                close_reason="handoff_completed",
                now=_parse_optional_now(body),
                close_payload={"opened_by_profile_id": int(principal.profile_id)},
            )
        else:
            case = gateway._with_proxy_intro(get_match_case, case_id)

    if not main_conversation:
        raise ValueError("主会话创建失败")

    return 200, {
        "case": _json_safe(_build_case_view(gateway, case, viewer_profile_id=int(principal.profile_id))),
        "conversation": _json_safe(main_conversation),
        "trace_id": get_trace_id(),
    }


def dispatch_proxy_intro_rest(
    gateway: ProxyIntroGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v1/proxy-intro/requests" and method == "POST":
        return rest_proxy_intro_create_request(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )
    if path == "/v1/proxy-intro/cases/mine" and method == "GET":
        return rest_proxy_intro_list_mine(gateway, environ)
    match = re.fullmatch(r"/v1/proxy-intro/cases/([^/]+)/reply", path)
    if match and method == "POST":
        return rest_proxy_intro_reply_case(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/proxy-intro/cases/([^/]+)/open-chat", path)
    if match and method == "POST":
        return rest_proxy_intro_open_chat(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v1/proxy-intro/cases/([^/]+)", path)
    if match and method == "GET":
        return rest_proxy_intro_get_case(gateway, environ, match.group(1))
    return None
