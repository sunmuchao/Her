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


def _push_proxy_intro_to_discovery_timeline(
    case: dict[str, Any],
    candidate_profile_id: int,
    now: Any,
) -> bool:
    """立即推送被动推荐到候选人的discovery timeline（有人想认识你）

    逻辑：
    1. 打开discovery数据库连接
    2. 查询候选人的最新discovery session（按updated_at降序）
    3. 如果没有session，跳过（下次创建session时会推送）
    4. 获取发起方基本信息（从案件数据中提取）
    5. 构建候选人卡片
    6. 在timeline中插入assistant_message和result_group
    7. 更新session的latest_view_json
    8. 标记案件为已推送（outreach_payload.discovery_pushed=True）

    Args:
        case: 被动推荐案件数据
        candidate_profile_id: 候选人的profile_id（被推荐方）
        now: 当前时间

    Returns:
        bool: 推送是否成功
    """
    import json
    import logging
    from datetime import datetime

    from her_external_systems import connect_external_db, json_dumps, json_loads, row_to_dict
    from outer_mysql_compat import connect_mysql_repo_db

    _logger = logging.getLogger(__name__)
    _logger.info(
        "【推送开始】case_id=%s, candidate_profile_id=%s",
        case.get("case_id"),
        candidate_profile_id,
    )

    # 1. 打开discovery数据库连接
    discovery_dsn = os.environ.get(
        "PARTNER_DISCOVERY_DB",
        "mysql://root@127.0.0.1:3307/her_discovery",
    )
    conn = connect_mysql_repo_db(discovery_dsn, subsystem_name="discovery")

    try:
        # 2. 查询候选人的最新session（按updated_at降序）
        row = conn.execute(
            """
            SELECT session_id, requester_id, profile_id, status, phase,
                   state_json, latest_view_json, created_at, updated_at
            FROM discovery_agent_sessions
            WHERE profile_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (int(candidate_profile_id),),
        ).fetchone()

        if not row:
            # 候选人没有discovery session，跳过（下次创建session时会推送）
            _logger.warning(
                "【推送跳过】候选人没有discovery session: candidate_profile_id=%s",
                candidate_profile_id,
            )
            conn.close()
            return False  # ✅ 返回失败标志

        session_data = row_to_dict(row)
        _logger.info(
            "【推送成功】找到session: session_id=%s",
            session_data["session_id"],
        )

        view_json = str(session_data.get("latest_view_json") or "{}")
        view = json_loads(view_json, {}) or {}

        # 3. 获取发起方基本信息（从案件数据中提取）
        requester_snapshot = dict(case.get("requester_profile_snapshot") or {})
        self_profile = dict(requester_snapshot.get("self_profile") or {})

        name = str(
            self_profile.get("display_name")
            or self_profile.get("name")
            or self_profile.get("nickname")
            or "对方"
        ).strip()
        age = self_profile.get("age")
        city = self_profile.get("city")
        occupation = self_profile.get("occupation") or self_profile.get("job")

        requester_id = int(case.get("requester_id") or 0)
        case_id = str(case.get("case_id") or "")

        # 4. 构建候选人卡片（简化版本）
        candidate_card = {
            "card_id": f"candidate-{requester_id}",
            "profile_id": requester_id,
            "title": f"{name} {age or ''}",
            "subtitle": f"{city or ''} · {occupation or ''}",
            "cover_image_url": None,
            "match_score": 0,  # 被动推荐没有匹配度分数
            "reason_summary": "",
            "open_profile_action": {
                "type": "open_profile",
                "profile_id": requester_id,
            },
        }

        # 5. 在timeline中插入assistant_message和result_group
        timeline = list(view.get("timeline") or [])

        # 检查是否已经推送过（避免重复推送）
        already_pushed = any(
            str(item.get("item_id") or "").startswith(f"proxy-intro-msg-{case_id}")
            for item in timeline
        )
        if already_pushed:
            _logger.warning(
                "【推送跳过】案件已推送: case_id=%s",
                case_id,
            )
            conn.close()
            return True  # ✅ 返回成功标志（已经推送过，视为成功）

        # 插入消息
        timeline.append({
            "item_type": "assistant_message",
            "item_id": f"proxy-intro-msg-{case_id}",
            "body": f"有人想认识你：{name}，{age}岁{city or ''}{occupation or ''}",
            "created_at": now.isoformat() if hasattr(now, 'isoformat') else str(now),
        })

        # 插入候选人卡片
        timeline.append({
            "item_type": "result_group",
            "item_id": f"proxy-intro-group-{case_id}",
            "title": "有人想认识你",
            "cards": [candidate_card],
        })

        # 6. 更新session的latest_view_json
        view["timeline"] = timeline
        updated_at = datetime.now()

        conn.execute(
            """
            UPDATE discovery_agent_sessions
            SET latest_view_json = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (
                json_dumps(view),
                updated_at,
                str(session_data["session_id"]),
            ),
        )
        conn.commit()

        _logger.info(
            "【推送成功】timeline已更新: session_id=%s, timeline长度=%d",
            session_data["session_id"],
            len(timeline),
        )

        # 7. 标记案件为已推送（更新proxy_intro数据库）
        outreach_payload = dict(case.get("outreach_payload") or {})
        outreach_payload["discovery_pushed"] = True

        # 打开proxy_intro数据库连接
        proxy_intro_dsn = os.environ.get(
            "PARTNER_MATCHMAKING_DB",
            "mysql://root@127.0.0.1:3307/her_matchmaking",
        )
        proxy_conn = connect_mysql_repo_db(proxy_intro_dsn, subsystem_name="matchmaking")
        try:
            proxy_conn.execute(
                """
                UPDATE proxy_intro_cases
                SET outreach_payload_json = ?
                WHERE case_id = ?
                """,
                (
                    json.dumps(outreach_payload, ensure_ascii=False),
                    case_id,
                ),
            )
            proxy_conn.commit()

            _logger.info(
                "【推送成功】案件已标记: case_id=%s, discovery_pushed=True",
                case_id,
            )
            return True  # ✅ 返回成功标志
        finally:
            proxy_conn.close()

    except Exception as e:
        _logger.error(
            "【推送失败】内部错误: candidate_profile_id=%s, error=%s",
            candidate_profile_id,
            e,
            exc_info=True,
        )
        return False  # ✅ 返回失败标志，不抛出异常
    finally:
        if conn:
            conn.close()

    # ✅ 默认返回失败（如果代码执行到这里说明有问题）
    return False


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

    # Step 1: 创建案件（状态: pending_outreach）
    created = gateway._with_proxy_intro(
        create_match_case,
        subscription_id=subscription_id,
        candidate_id=candidate_id,
        now=now,
        request_payload={
            "source": str(body.get("source") or "recommendation_detail"),
        },
    )

    # Step 2: ✅ 先推送被动推荐到discovery timeline（数据库写入）
    # 确保数据持久化成功后再推送SSE实时通知
    timeline_push_success = False
    try:
        _push_proxy_intro_to_discovery_timeline(
            case=created,  # 使用created（案件已创建但未分发）
            candidate_profile_id=candidate_id,
            now=now,
        )
        timeline_push_success = True
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info(
            "【推送顺序优化】timeline已写入: case_id=%s, candidate_id=%s",
            created.get("case_id"),
            candidate_id,
        )
    except Exception as e:
        import logging
        _logger = logging.getLogger(__name__)
        _logger.error(
            "推送被动推荐到discovery timeline失败: case_id=%s, candidate_id=%s, error=%s",
            created.get("case_id"),
            candidate_id,
            e,
        )

    # Step 3: 分发案件（状态更新为awaiting_reply）
    case = gateway._with_proxy_intro(
        dispatch_match_case_outreach,
        case_id=str(created["case_id"]),
        now=now,
        payload={"source": str(body.get("source") or "recommendation_detail")},
    )

    # Step 4: ✅ 数据库写入成功后，推送SSE实时通知
    if timeline_push_success:
        try:
            _push_passive_recommendation_notification(
                case=case,
                now=now,
            )
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(
                "【推送顺序优化】SSE通知已发送: case_id=%s, candidate_id=%s",
                case.get("case_id"),
                candidate_id,
            )
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.warning(
                "SSE推送失败（不影响主流程，timeline已更新）: case_id=%s, error=%s",
                case.get("case_id"),
                e,
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
