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


def _stage_label(case: dict[str, Any], *, has_main_conversation: bool, viewer_role: str = "unknown") -> str:
    if has_main_conversation:
        return "已开聊"
    status = str(case.get("case_status") or "").strip()
    if status == "pending_outreach":
        return "待联系"
    if status == "awaiting_reply":
        return "等待回复"
    if status == "viewed":
        # 🔒 隐藏"已查看"状态：对于发起方，伪装成"等待回复"，避免"已读不回"焦虑
        # 对于被推荐方，显示真实的"已查看"，保留信息透明度
        return "等待回复" if viewer_role == "requester" else "已查看"
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
    # 🔑 先计算 viewer_role，用于后续的 stage_label 显示逻辑
    viewer_role = "requester" if int(case.get("requester_id") or 0) == int(viewer_profile_id) else "candidate"
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
        "role": viewer_role,
        "counterpart_name": counterpart_name,
        "counterpart_profile_id": counterpart_profile_id,
        "counterpart_profile": counterpart_profile,
        "counterpart_image": counterpart_profile.get("avatar_url")
        or counterpart_profile.get("photo_url")
        or counterpart_profile.get("cover_url"),
        "safe_summary": case.get("safe_summary") or {},
        "stage_label": _stage_label(case, has_main_conversation=bool(main_conversation), viewer_role=viewer_role),
        "can_reply": int(case.get("candidate_id") or 0) == int(viewer_profile_id) and case_status in {"awaiting_reply", "viewed"},  # ✅ 修改：viewed状态也能回复
        "can_open_chat": can_open_chat,
        "main_conversation_id": (
            str(main_conversation.get("conversation_id") or "").strip() if main_conversation else None
        ),
        # 新增：返回 outreach_payload 和 requester_profile_snapshot，供前端提取发起方信息
        "outreach_payload": case.get("outreach_payload") or {},
        "requester_profile_snapshot": case.get("requester_profile_snapshot") or {},
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


def rest_proxy_intro_view_case(
    gateway: ProxyIntroGateway,
    environ: dict[str, Any],
    case_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """标记被动推荐为已查看状态（不改变accept/decline状态）"""
    principal = gateway._resolve_end_user_principal(environ, require_profile=True)
    case = gateway._get_case_for_actor(environ, case_id)

    # 验证用户是否有权限查看这个case（必须是candidate）
    if int(case.get("candidate_id") or 0) != int(principal.profile_id):
        raise ValueError("只有被推荐的一方可以标记查看状态")

    # 检查当前状态，只有awaiting_reply状态可以标记为viewed
    case_status = str(case.get("case_status") or "").strip()
    if case_status != "awaiting_reply":
        # 如果已经是viewed、accepted、declined等状态，不需要再次标记
        return 200, {
            "case": _json_safe(_build_case_view(gateway, case, viewer_profile_id=int(principal.profile_id))),
            "message": f"当前状态为{case_status}，无需标记为viewed",
            "trace_id": get_trace_id(),
        }

    # 调用后端函数更新状态为viewed
    from matchmaking_system.proxy_intro_core import mark_case_as_viewed  # type: ignore[import-untyped]
    updated = gateway._with_proxy_intro(
        mark_case_as_viewed,
        case_id=case_id,
        now=_parse_optional_now(body),
        view_payload={"source": str(body.get("source") or "detail_page")},
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

        # 防御性逻辑：relation_key 缺失时动态生成
        if not relation_key:
            requester_id = case.get("requester_id")
            candidate_id = case.get("candidate_id")
            if requester_id and candidate_id and requester_user_id and candidate_user_id:
                from match_domain import matchmaking_relation_key
                requester_info = {"source": "her", "self_id": requester_id, "user_key": str(requester_id)}
                candidate_info = {"source": "her", "self_id": candidate_id, "user_key": str(candidate_id)}
                member_low, member_high = sorted([requester_info, candidate_info], key=lambda x: int(x.get("self_id") or 0))
                relation_key = matchmaking_relation_key(member_low, member_high)
                print(f"[INFO] Generated relation_key for case {case_id}: {relation_key}")

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
    match = re.fullmatch(r"/v1/proxy-intro/cases/([^/]+)/view", path)
    if match and method == "POST":
        return rest_proxy_intro_view_case(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
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
    match = re.fullmatch(r"/v1/proxy-intro/cases/([^/]+)/close", path)
    if match and method == "POST":
        return rest_proxy_intro_close_case(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )

    # FIX: 清理孤儿 match case（订阅已删除但 case 仍存在）
    if path == "/v1/proxy-intro/cleanup-orphan-cases" and method == "POST":
        gateway._require_roles(
            environ,
            ["ops_workbench", "admin"],
            message="current actor cannot cleanup orphan match cases",
        )
        return rest_cleanup_orphan_match_cases(gateway, environ)

    return None


def rest_cleanup_orphan_match_cases(
    gateway: ProxyIntroGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """清理订阅已删除的孤儿 match case。

    此API需要 ops_workbench 或 admin 权限，用于：
    1. 手动触发清理孤儿 case
    2. 定期维护任务调用
    """
    from matchmaking_system.proxy_intro_core import cleanup_orphan_match_cases  # type: ignore[import-untyped]
    result = gateway._with_proxy_intro(cleanup_orphan_match_cases)
    return 200, {
        "deleted_case_count": result.get("deleted_case_count", 0),
        "updated_recommendation_count": result.get("updated_recommendation_count", 0),
        "trace_id": get_trace_id(),
    }


def rest_proxy_intro_close_case(
    gateway: ProxyIntroGateway,
    environ: dict[str, Any],
    case_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """用户主动关闭/删除关系"""
    principal = gateway._resolve_end_user_principal(environ, require_profile=True)
    case = gateway._get_case_for_actor(environ, case_id)

    # 权限验证：只有 requester 或 candidate 可以关闭
    profile_id = int(principal.profile_id)
    requester_id = int(case.get("requester_id") or 0)
    candidate_id = int(case.get("candidate_id") or 0)

    if requester_id != profile_id and candidate_id != profile_id:
        raise ValueError("无权操作此关系")

    # 检查 case 状态：只有 active 状态的 case 可以关闭
    case_status = str(case.get("case_status") or "").strip()
    if case_status not in {"accepted", "awaiting_reply", "pending_outreach"}:
        raise ValueError(f"只能关闭进行中的关系（当前状态：{case_status})")

    # 解析关闭原因和参数
    close_reason = str(body.get("close_reason") or "user_deleted").strip()
    actor_type = "requester" if requester_id == profile_id else "candidate"
    close_payload = {"source": str(body.get("source") or "relationships_page")}

    # 调用 close_match_case 函数
    updated = gateway._with_proxy_intro(
        close_match_case,
        case_id=case_id,
        close_reason=close_reason,
        now=_parse_optional_now(body),
        actor_type=actor_type,
        close_payload=close_payload,
    )

    # 返回更新后的 case 数据
    return 200, {
        "case": _json_safe(_build_case_view(gateway, updated, viewer_profile_id=profile_id)),
        "trace_id": get_trace_id(),
    }
