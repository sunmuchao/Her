"""Service layer for the discovery system skeleton."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
import os
import re
from typing import Any

from her_json_utils import json_safe
from her_runtime_context import get_trace_id
from observability import audit_event, funnel_stage, metric_gauge
from partner_search import load_self_profile, search_profiles
from profile_detail_reader import load_profile_detail

from .agent_runtime import (
    DiscoveryActionSuggestion,
    DiscoveryAgentRuntime,
    DiscoveryCandidateSelection,
    DiscoveryDecision,
    DiscoveryRunInput,
    DiscoveryRuntimeResult,
    DiscoveryToolCall,
    create_default_discovery_agent_runtime,
)
from .service_session_open import (
    PROFILE_FIRST_SEARCH_LIMIT,
    build_profile_first_open_result,
    criteria_labels_from_search_criteria,
    discovery_create_session_mode,
    selected_candidates_from_search,
)
from .agent_session_store import create_default_discovery_agent_session_store
from .profile_updates import (
    ProfileUpdateRequestConflictError,
    ProfileUpdateRequestNotFoundError,
    confirm_profile_update as _confirm_profile_update_impl,
    profile_update_prompt_item,
    reject_profile_update as _reject_profile_update_impl,
)
from .service_integrations import (
    decision_payload as _decision_payload_impl,
    load_persona_memory_bindings as _load_persona_memory_bindings_impl,
    load_recommendation_bindings as _load_recommendation_bindings_impl,
    load_requester_profile as _load_requester_profile_impl,
    open_recommendation_conn as _open_recommendation_conn_impl,
    persona_memory_source as _persona_memory_source_impl,
    persist_search_run as _persist_search_run_impl,
    profile_source as _profile_source_impl,
    # propose_requester_profile_update as _propose_requester_profile_update_impl,  # 已注释：暂时禁用此工具
    search_partner_candidates as _search_partner_candidates_impl,
    sync_requester_persona_memory as _sync_requester_persona_memory_impl,
)
from match_domain.profile_write_guard import is_search_criteria_key, merge_working_criteria
from partner_search.personality_traits_reader import load_traits_for_discovery
from .storage import InMemoryDiscoveryStorage, MySQLDiscoveryStorage, StoredSearchRun, StoredSession, StoredViewSnapshot
from .service_context import (
    DiscoveryServiceContextRuntime,
    build_last_search_summary as _build_last_search_summary,
    build_page_summary as _build_page_summary,
    build_profile_detail_notes as _build_profile_detail_notes,
    build_runtime_context as _build_runtime_context,
    build_visible_action_summaries as _build_visible_action_summaries,
    search_error_summary as _search_error_summary_impl,
)
from .view_models import (
    assistant_message,
    build_profile_detail_view_from_payload,
    build_candidate_card,
    clone_view,
    composer,
    criteria_chip,
    result_group,
    suggested_action,
    user_message,
)

# ✅ Agent Native：移除硬编码关键词列表
# Agent 根据 Prompt 自主判断用户意图（如"换一批"、"看看更多"等）
# 不再通过硬编码关键词列表匹配意图
# 参考：Agent Native 开发实践规范 - 反模式：触发词映射表


class DiscoveryServiceError(Exception):
    code = "DISCOVERY_ERROR"
    status_code = 400
    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DiscoverySessionNotFoundError(DiscoveryServiceError):
    code = "DISCOVERY_SESSION_NOT_FOUND"
    status_code = 404


class DiscoverySessionClosedError(DiscoveryServiceError):
    code = "DISCOVERY_SESSION_CLOSED"
    status_code = 409


class DiscoveryInvalidTurnInputError(DiscoveryServiceError):
    code = "DISCOVERY_INVALID_TURN_INPUT"
    status_code = 400


class DiscoveryActionNotFoundError(DiscoveryServiceError):
    code = "DISCOVERY_ACTION_NOT_FOUND"
    status_code = 404


class DiscoveryActionExpiredError(DiscoveryServiceError):
    code = "DISCOVERY_ACTION_EXPIRED"
    status_code = 409
    retryable = True


class DiscoveryProfileNotFoundError(DiscoveryServiceError):
    code = "DISCOVERY_PROFILE_NOT_FOUND"
    status_code = 404


class DiscoveryCandidateNotFoundError(DiscoveryServiceError):
    code = "DISCOVERY_CANDIDATE_NOT_FOUND"
    status_code = 404


class DiscoveryInterestNotAvailableError(DiscoveryServiceError):
    code = "DISCOVERY_INTEREST_NOT_AVAILABLE"
    status_code = 409


class DiscoveryProfileUpdateNotFoundError(DiscoveryServiceError):
    code = "DISCOVERY_PROFILE_UPDATE_NOT_FOUND"
    status_code = 404


class DiscoveryProfileUpdateConflictError(DiscoveryServiceError):
    code = "DISCOVERY_PROFILE_UPDATE_CONFLICT"
    status_code = 409


# ✅ Agent Native：移除硬编码关键词判断
# Agent 根据 Prompt 自主理解用户意图（如"为什么推荐第一位"、"测评角度解释一下"）
# ✅ Agent Native：完全移除硬编码关键词判断
# _pick_existing_candidate 方法已删除
# Agent 根据 user_message 自主识别"第一位"、"第二位"等位置表达
# 不再提供 fallback，全靠 AI 理解
#
# 参考：Agent Native 开发实践规范 - 反模式：触发词映射表


def _shared_values(self_traits: dict[str, Any], candidate_traits: dict[str, Any]) -> list[str]:
    self_top = {str(item).strip() for item in list((self_traits.get("values") or {}).get("top_values") or []) if str(item).strip()}
    candidate_top = {
        str(item).strip()
        for item in list((candidate_traits.get("values") or {}).get("top_values") or [])
        if str(item).strip()
    }
    return [item for item in self_top if item in candidate_top]


def _candidate_first_name(card: dict[str, Any]) -> str:
    title = str(card.get("title") or "这位").strip() or "这位"
    return re.split(r"\s+", title, maxsplit=1)[0]


# ✅ Agent Native：完全移除硬编码关键词判断
# _looks_like_basic_reason_summary 方法已删除
# Agent 自主判断 reason_summary 是否足够详细
#
# 参考：Agent Native 开发实践规范 - 反模式：触发词映射表


def _effective_reason_summary(candidate: dict[str, Any], selection_reason: str | None) -> str:
    """
    获取有效的推荐理由摘要。

    ✅ Agent Native：不再通过关键词判断是否需要 personality_summary
    直接返回 selection_reason（如果有的话），否则返回 personality_summary
    Agent 自主决定是否需要更详细的解释
    """
    reasoning = dict(candidate.get("personality_reasoning") or {})
    personality_summary = str(reasoning.get("summary") or "").strip()
    selected_summary = str(selection_reason or "").strip()
    # 优先返回 selection_reason（Agent 自主判断是否足够）
    return selected_summary if selected_summary else personality_summary


@dataclass
class DiscoveryService:
    storage: Any
    runtime: DiscoveryAgentRuntime
    agent_session_store: Any | None = None
    metric_counters: dict[str, int] = field(default_factory=dict)

    def get_session_owner_id(self, session_id: str) -> int:
        session = self._require_session(session_id)
        return session.requester_id

    def create_session(
        self,
        *,
        requester_id: int,
        profile_id: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = now or datetime.now()
        trace_id = self._current_trace_id()
        session = StoredSession(
            session_id=self.storage.next_session_id(),
            requester_id=requester_id,
            profile_id=profile_id,
            status="active",
            phase="collecting_preferences",
            created_at=current,
            updated_at=current,
            view={
                "timeline": [],
                "criteria_chips": [],
                "suggested_actions": [],
                "composer": composer("告诉红娘你的偏好，她会替你整理并搜索。"),
            },
            state={},
        )
        self.storage.save_session(session)
        open_mode = discovery_create_session_mode()
        session.state["create_session_mode"] = open_mode
        if open_mode == "profile_first":
            runtime_result, open_tool_calls = self._profile_first_session_open(session)
        else:
            run_input = self._build_runtime_input(session, now=current)
            runtime_result = self.runtime.initial_decision(run_input)
            open_tool_calls = list(run_input.tool_call_buffer)
        search_run_id = self._apply_runtime_result(session, runtime_result, now=current)
        self.storage.save_session(session)
        turn_id = self.storage.create_turn(
            session_id=session.session_id,
            request_kind="session_opened",
            user_message_text=None,
            consumed_action_id=None,
            agent_decision=self._decision_payload(runtime_result.decision),
            view_snapshot=clone_view(session.view),
            created_at=current,
            search_run_id=search_run_id,
            trace_id=trace_id,
        )
        self._persist_view_snapshot(
            session,
            turn_id=turn_id,
            created_at=current,
            trace_id=trace_id,
        )
        self._record_tool_calls(
            session_id=session.session_id,
            turn_id=turn_id,
            tool_calls=open_tool_calls,
            search_run_id=search_run_id,
            created_at=current,
            trace_id=trace_id,
        )
        self._increment_metric("sessions.created")
        self._increment_metric("turns.created")
        self._increment_metric(f"sessions.create.{open_mode}")
        funnel_stage(
            system="discovery",
            stage="session_open_profile_first" if open_mode == "profile_first" else "session_open",
            session_id=session.session_id,
            requester_id=session.requester_id,
            profile_id=session.profile_id,
            trace_id=trace_id,
        )
        audit_event(
            action="discovery.session.create",
            resource_type="discovery_session",
            outcome="created",
            resource_id=session.session_id,
            requester_id=session.requester_id,
            profile_id=session.profile_id,
        )

        # 新增：异步处理用户上一个会话（触发摘要提炼）
        # 不阻塞主流程，后台偷偷处理
        # ✅ 修复：传入刚创建的会话 ID，避免把新会话误当作上一个会话处理
        self._trigger_previous_session_processing(
            requester_id=requester_id,
            profile_id=profile_id,
            conversation_type="discovery",
            current_session_id=session.session_id,  # ✅ 新增：传入刚创建的会话 ID
        )

        return self._session_payload(session)

    def switch_session(
        self,
        *,
        from_session_id: str,  # ✅ 当前会话（切换前）
        to_session_id: str,    # ✅ 目标会话（切换后）
        requester_id: int,
        profile_id: int,
    ) -> dict[str, Any]:
        """切换会话：检查切换前的会话是否有新增内容

        使用场景：
        - 用户从历史会话A切换到历史会话B
        - 前端传入 from_session_id（当前会话）和 to_session_id（目标会话）
        - 后端检查 from_session_id 是否有新增内容，如果有则处理

        Args:
            from_session_id: 当前会话ID（切换前的会话）
            to_session_id: 目标会话ID（切换后的会话）
            requester_id: 用户ID
            profile_id: 画像ID

        Returns:
            目标会话的数据
        """
        # Step 1：检查切换前的会话是否有新增内容
        self._trigger_session_processing_by_id(
            session_id=from_session_id,
            requester_id=requester_id,
            profile_id=profile_id,
            conversation_type="discovery",
        )

        # Step 2：返回目标会话的数据
        target_session = self.storage.get_session(to_session_id)
        if not target_session:
            raise ValueError(f"目标会话 {to_session_id} 不存在")

        # Step 3：恢复目标会话（设置 session_restore funnel）
        from .view_models import audit_event
        audit_event(
            action="discovery.session.restore",
            resource_type="discovery_session",
            outcome="read",
            resource_id=to_session_id,
            requester_id=requester_id,
            profile_id=profile_id,
        )

        return self._session_payload(target_session)

    def _trigger_session_processing_by_id(
        self,
        session_id: str,
        requester_id: int,
        profile_id: int,
        conversation_type: str = "discovery",
    ) -> None:
        """检查并处理指定会话的新增内容

        Args:
            session_id: 要检查的会话ID
            requester_id: 用户ID
            profile_id: 画像ID
            conversation_type: 对话类型
        """
        import logging
        from match_domain.session_end_trigger import process_session_if_has_new_content

        _logger = logging.getLogger(__name__)

        try:
            task = process_session_if_has_new_content(
                session_id=session_id,
                requester_id=requester_id,
                profile_id=profile_id,
                storage=self.storage,
                conversation_type=conversation_type,
            )

            if task:
                _logger.info(
                    f"切换会话触发处理: session_id={session_id}, "
                    f"requester_id={requester_id}, task_name={task.name}"
                )

        except Exception as exc:
            _logger.error(
                f"切换会话触发处理失败: session_id={session_id}, "
                f"requester_id={requester_id}, error={exc}"
            )
            # 不抛出异常，避免阻塞切换会话

    def process_turn(
        self,
        *,
        session_id: str,
        user_message_text: str | None = None,
        action_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = now or datetime.now()
        trace_id = self._current_trace_id()
        if bool((user_message_text or "").strip()) == bool((action_id or "").strip()):
            raise DiscoveryInvalidTurnInputError("exactly one of user_message or action_id is required")
        session = self._require_session(session_id)
        if session.status != "active":
            raise DiscoverySessionClosedError("discovery session is closed")

        new_items: list[dict[str, Any]] = []
        runtime_result: DiscoveryRuntimeResult
        request_kind = "user_message"
        consumed_action_id: str | None = None
        normalized_user_message: str | None = None
        run_input = self._build_runtime_input(session, now=current)
        if user_message_text is not None and user_message_text.strip():
            text = user_message_text.strip()
            normalized_user_message = text
            new_items.append(
                user_message(
                    self.storage.next_item_id("msg-u"),
                    text,
                    created_at=current,
                )
            )

            # ✅ Agent Native：完全移除 awaiting_rejection_feedback 状态硬编码分支
            # Agent 根据 state.awaiting_rejection_feedback 自主判断是否需要处理反馈
            # 不再通过代码强制调用 _force_rejection_feedback_turn
            # 统一走 Agent Runtime，让 Agent 自己理解用户意图
            runtime_result = self.runtime.run_turn(
                run_input,
                user_message=text,
            )
        else:
            action = self.storage.get_action(session_id, str(action_id or "").strip())
            if action is None:
                raise DiscoveryActionNotFoundError("action_id not found for this discovery session")
            if action.consumed_at is not None:
                # action已被消费，提示用户刷新session
                raise DiscoveryActionExpiredError(
                    "这个操作已经执行过了。请刷新页面获取新的操作建议。"
                )
            if action.expires_at is not None and action.expires_at <= current:
                # action已过期，提示用户刷新session
                raise DiscoveryActionExpiredError(
                    "这个操作建议已经过期了。请刷新页面获取新的操作建议。"
                )
            self.storage.mark_action_consumed(action.action_id, current)
            request_kind = "action_click"
            consumed_action_id = action.action_id

            # ✅ 新增：把用户点击的按钮作为一条消息添加到timeline
            # 这样用户可以看到自己点击了什么按钮
            new_items.append(
                user_message(
                    self.storage.next_item_id("msg-u"),
                    f"[{action.label}]",  # 显示为按钮文本，如 "[换一批]"
                    created_at=current,
                )
            )

            action_context = {
                "label": action.label,
                "semantic_payload": deepcopy(action.semantic_payload),
            }

            # ✅ Agent Native：完全移除 action_kind 硬编码分支
            # 所有按钮点击统一走 Agent Runtime
            # Agent 根据 action_context 自主理解按钮意图并编排工作流
            runtime_result = self.runtime.run_turn(
                run_input,
                action_context=action_context,
            )


        session.view["timeline"] = list(session.view.get("timeline") or []) + new_items
        search_run_id = self._apply_runtime_result(session, runtime_result, now=current)
        self.storage.save_session(session)
        turn_id = self.storage.create_turn(
            session_id=session.session_id,
            request_kind=request_kind,
            user_message_text=normalized_user_message,
            consumed_action_id=consumed_action_id,
            agent_decision=self._decision_payload(runtime_result.decision),
            view_snapshot=clone_view(session.view),
            created_at=current,
            search_run_id=search_run_id,
            trace_id=trace_id,
        )
        self._persist_view_snapshot(
            session,
            turn_id=turn_id,
            created_at=current,
            trace_id=trace_id,
        )
        self._record_tool_calls(
            session_id=session.session_id,
            turn_id=turn_id,
            tool_calls=run_input.tool_call_buffer,
            search_run_id=search_run_id,
            created_at=current,
            trace_id=trace_id,
        )
        self._increment_metric("turns.created")
        self._increment_metric(f"turns.{request_kind}")
        funnel_stage(
            system="discovery",
            stage=request_kind,
            session_id=session.session_id,
            requester_id=session.requester_id,
            profile_id=session.profile_id,
            turn_id=turn_id,
            trace_id=trace_id,
        )
        audit_event(
            action=f"discovery.turn.{request_kind}",
            resource_type="discovery_turn",
            outcome="created",
            resource_id=turn_id,
            session_id=session.session_id,
            requester_id=session.requester_id,
            profile_id=session.profile_id,
            consumed_action_id=consumed_action_id,
            search_run_id=search_run_id,
        )
        return self._session_payload(session)

    def get_session_view(self, session_id: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        if not dict(session.view or {}):
            latest_snapshot = self.storage.get_latest_view_snapshot(session_id)
            if latest_snapshot is not None:
                session.view = clone_view(latest_snapshot.view)
        self._increment_metric("session_restores")
        funnel_stage(
            system="discovery",
            stage="session_restore",
            session_id=session.session_id,
            requester_id=session.requester_id,
            trace_id=self._current_trace_id(),
        )
        audit_event(
            action="discovery.session.restore",
            resource_type="discovery_session",
            outcome="read",
            resource_id=session.session_id,
            requester_id=session.requester_id,
            profile_id=session.profile_id,
        )
        return self._session_payload(session)

    def list_sessions(
        self,
        profile_id: int,
        limit: int = 20,
    ) -> dict[str, Any]:
        """返回用户的 Discovery 会话列表。"""
        sessions = self.storage.list_sessions_by_profile_id(
            profile_id=profile_id,
            limit=limit,
            status=None,  # 返回所有状态的会话
        )
        summaries: list[dict[str, Any]] = []
        for session in sessions:
            # 从 timeline 中提取最后一条消息摘要
            timeline = list(session.view.get("timeline") or [])
            last_message_preview = None
            for item in reversed(timeline):
                if item.get("item_type") == "assistant_message":
                    last_message_preview = str(item.get("body") or "")[:100]
                    break
                elif item.get("item_type") == "result_group":
                    card_count = len(list(item.get("cards") or []))
                    last_message_preview = f"推荐了 {card_count} 位候选人"
                    break

            # 统计候选人数量
            candidate_count = 0
            for item in timeline:
                if item.get("item_type") == "result_group":
                    candidate_count += len(list(item.get("cards") or []))

            summaries.append({
                "session_id": session.session_id,
                "phase": session.phase,
                "status": session.status,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "last_message_preview": last_message_preview,
                "candidate_count": candidate_count,
            })

        self._increment_metric("session_list_queries")
        return {
            "sessions": summaries,
            "total": len(summaries),
        }

    def get_observability_snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self.metric_counters),
        }

    def get_profile_detail(self, profile_id: int, *, session_id: str | None = None) -> dict[str, Any]:
        if profile_id <= 0:
            raise DiscoveryProfileNotFoundError("profile not found")
        session: StoredSession | None = None
        if session_id:
            session = self._require_session(session_id)
        source = self._profile_source()
        if not source:
            raise DiscoveryProfileNotFoundError("profile not found")
        detail_payload = load_profile_detail(
            source=source,
            profile_id=profile_id,
            photo_preview_count=6,
            moderation_dsn=os.environ.get("PARTNER_CHAT_DB"),
        )
        if not isinstance(detail_payload, dict):
            raise DiscoveryProfileNotFoundError("profile not found")
        self._increment_metric("profile_detail_reads")
        funnel_stage(
            system="discovery",
            stage="profile_detail_read",
            session_id=session.session_id if session is not None else None,
            profile_id=profile_id,
            trace_id=self._current_trace_id(),
        )
        audit_event(
            action="discovery.profile_detail.read",
            resource_type="profile_detail",
            outcome="read",
            resource_id=profile_id,
            session_id=session.session_id if session is not None else None,
        )
        return {
            "profile_id": profile_id,
            "detail_view": build_profile_detail_view_from_payload(
                detail_payload,
                matchmaker_notes=self._build_profile_detail_notes(session, profile_id),
            ),
        }

    def express_interest(
        self,
        session_id: str,
        *,
        candidate_id: int,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if candidate_id <= 0:
            raise DiscoveryCandidateNotFoundError("candidate not found")

        current = now or datetime.now()
        session = self._require_session(session_id)
        if session.status != "active":
            raise DiscoverySessionClosedError("discovery session is closed")

        search_run_id = int(session.state.get("last_search_run_id") or 0)
        if search_run_id <= 0:
            raise DiscoveryInterestNotAvailableError("当前还没有可发起认识的推荐结果。")

        search_run = self.storage.get_search_run(search_run_id)
        if search_run is None:
            raise DiscoveryInterestNotAvailableError("推荐结果已失效，请让红娘重新搜一轮。")

        candidate = self._find_candidate_in_search_run(search_run.response, candidate_id)
        if candidate is None:
            raise DiscoveryCandidateNotFoundError("candidate not found in latest discovery results")

        request_meta = dict((search_run.response or {}).get("request_meta") or {})
        criteria = json_safe(dict(request_meta.get("criteria") or search_run.criteria or {}))
        self_profile = json_safe(deepcopy(request_meta.get("self_profile") or search_run.self_profile or {}))
        effective_self_id = request_meta.get("self_id")
        if effective_self_id in (None, ""):
            effective_self_id = session.profile_id

        initial_request = json_safe(
            {
                "source": request_meta.get("source") or search_run.source,
                "criteria": criteria,
                "self_profile": self_profile if isinstance(self_profile, dict) else {},
                "self_id": effective_self_id,
                "limit_count": max(int(search_run.limit_count or 0), int(search_run.result_count or 0), 10),
            }
        )
        safe_candidate = json_safe(candidate)

        conn = self._open_recommendation_conn()
        case_conn = None
        try:
            from match_domain.proxy_intro_storage import open_proxy_intro_case_connection  # type: ignore[import-untyped]
            from recommendation_system import (  # type: ignore[import-untyped]
                create_subscription,
            )
            from recommendation_system.recommendation_rows import (  # type: ignore[import-untyped]
                upsert_recommendation,
            )
            from matchmaking_system.proxy_intro import (  # type: ignore[import-untyped]
                create_match_case,
                dispatch_match_case_outreach,
            )

            subscription = create_subscription(
                conn,
                requester_id=session.requester_id,
                self_id=int(effective_self_id) if effective_self_id is not None else None,
                source=request_meta.get("source") or search_run.source,
                criteria=criteria,
                self_profile=self_profile if isinstance(self_profile, dict) else {},
                title=self._build_proxy_intro_title(session, candidate),
                limit_count=max(int(search_run.limit_count or 0), int(search_run.result_count or 0), 10),
                recommendation_mode="match_based",
                initial_request=initial_request,
                now=current,
            )
            subscription_id = str(subscription.get("subscription_id") or "").strip()
            if not subscription_id:
                raise DiscoveryInterestNotAvailableError("正式牵线单创建失败，请稍后重试。")
            recommendation = upsert_recommendation(
                conn,
                subscription,
                safe_candidate,
                current,
                review_rank=1,
                rule_provenance={
                    "source": "discovery_session",
                    "session_id": session.session_id,
                    "search_run_id": search_run_id,
                    "hydrated_from_search_run": True,
                },
            )

            case_conn = open_proxy_intro_case_connection(conn)
            case = create_match_case(
                case_conn,
                recommendation_conn=conn,
                subscription_id=subscription_id,
                candidate_id=int(candidate_id),
                now=current,
                request_payload={
                    "source": "discovery_session",
                    "session_id": session.session_id,
                    "search_run_id": search_run_id,
                },
            )
            case = dispatch_match_case_outreach(
                case_conn,
                recommendation_conn=conn,
                case_id=str(case["case_id"]),
                now=current,
                payload={
                    "source": "discovery_session",
                    "session_id": session.session_id,
                    "search_run_id": search_run_id,
                },
            )
        except DiscoveryServiceError:
            raise
        except ValueError as exc:
            raise DiscoveryInterestNotAvailableError(str(exc)[:200]) from exc
        except Exception as exc:  # noqa: BLE001
            raise DiscoveryInterestNotAvailableError("发起认识失败，请稍后重试。") from exc
        finally:
            if case_conn is not None and case_conn is not conn:
                case_conn.close()
            conn.close()

        session.state["last_created_subscription_id"] = subscription_id
        session.state["last_interest_candidate_id"] = int(candidate_id)
        session.state["last_interest_at"] = current.isoformat()
        self.storage.save_session(session)

        self._increment_metric("interest_expressions.created")
        funnel_stage(
            system="discovery",
            stage="express_interest",
            session_id=session.session_id,
            requester_id=session.requester_id,
            profile_id=candidate_id,
            trace_id=self._current_trace_id(),
        )
        audit_event(
            action="discovery.express_interest",
            resource_type="discovery_candidate",
            outcome="created",
            resource_id=candidate_id,
            session_id=session.session_id,
            requester_id=session.requester_id,
            profile_id=session.profile_id,
        )
        return {
            "ok": True,
            "session_id": session.session_id,
            "candidate_id": int(candidate_id),
            "subscription_id": subscription_id,
            "case": json_safe(case),
        }

    def _build_runtime_input(
        self,
        session: StoredSession,
        *,
        now: datetime | None = None,
    ) -> DiscoveryRunInput:
        recent_timeline = clone_view({"timeline": session.view.get("timeline") or []}).get("timeline") or []
        tool_call_buffer: list[DiscoveryToolCall] = []

        def _search_partner_candidates(
            criteria: dict[str, Any],
            personality_match: dict[str, Any] | int | None = None,
            limit: int | None = None,
            *,
            exclude_current_results: bool = False,
        ) -> dict[str, Any]:
            resolved_personality_match: dict[str, Any]
            resolved_limit: int
            if isinstance(personality_match, int) and limit is None:
                resolved_personality_match = {}
                resolved_limit = personality_match
            else:
                resolved_personality_match = (
                    dict(personality_match or {})
                    if isinstance(personality_match, dict)
                    else {}
                )
                resolved_limit = int(limit or 5)
            response = self._search_partner_candidates(
                session,
                criteria=criteria,
                personality_match=resolved_personality_match,
                limit=resolved_limit,
                exclude_current_results=exclude_current_results,
            )
            self._append_tool_call(
                tool_call_buffer,
                "search_partner_candidates",
                {
                    "criteria": deepcopy(criteria),
                    "personality_match": deepcopy(resolved_personality_match),
                    "limit": resolved_limit,
                    "exclude_current_results": exclude_current_results,
                },
                response,
                status=self._tool_call_status("search_partner_candidates", response),
            )
            return response

        def _sync_requester_persona_memory(patch: dict[str, Any]) -> dict[str, Any]:
            result = self._sync_requester_persona_memory(
                session,
                patch=patch,
                now=now,
            )
            self._append_tool_call(
                tool_call_buffer,
                "sync_requester_persona_memory",
                {"patch": deepcopy(patch)},
                result,
                status=self._tool_call_status("sync_requester_persona_memory", result),
            )
            return result

        # def _propose_requester_profile_update(patch_json: str, evidence_text: str = "") -> dict[str, Any]:
        #     import json
        #
        #     patch = json.loads(str(patch_json or "{}"))
        #     if not isinstance(patch, dict):
        #         raise ValueError("patch_json must decode into a JSON object")
        #     result = self._propose_requester_profile_update(
        #         session,
        #         patch=patch,
        #         evidence_text=str(evidence_text or "").strip() or None,
        #         now=now,
        #     )
        #     if result.get("proposed"):
        #         pending_timeline = list(session.state.get("profile_prompts_for_timeline") or [])
        #         pending_timeline.append(result)
        #         session.state["profile_prompts_for_timeline"] = pending_timeline
        #     self._append_tool_call(
        #         tool_call_buffer,
        #         "propose_requester_profile_update",
        #         {"patch": deepcopy(patch), "evidence_text": evidence_text},
        #         result,
        #         status="succeeded" if result.get("proposed") else "skipped",
        #     )
        #     return result

        def _create_saved_search_subscription_from_last_search() -> dict[str, Any]:
            result = self._create_saved_search_subscription_from_last_search(
                session,
                now=now,
            )
            self._append_tool_call(
                tool_call_buffer,
                "create_saved_search_subscription_from_last_search",
                {},
                result,
                status=self._tool_call_status("create_saved_search_subscription_from_last_search", result),
            )
            return result

        def _suggest_assessment(assessment_type: str) -> dict[str, Any]:
            """检查用户测评状态，返回引导卡片或性格信息。"""
            result = self._suggest_assessment(
                session,
                assessment_type=assessment_type,
            )
            self._append_tool_call(
                tool_call_buffer,
                "suggest_assessment",
                {"assessment_type": assessment_type},
                result,
                status="succeeded",
            )
            return result

        return DiscoveryRunInput(
            session_id=session.session_id,
            requester_id=session.requester_id,
            profile_id=session.profile_id,
            phase=session.phase,
            criteria_labels=[
                str(item.get("label") or "").strip()
                for item in list(session.view.get("criteria_chips") or [])
                if str(item.get("label") or "").strip()
            ],
            recent_timeline=recent_timeline,
            runtime_context=self._build_runtime_context(
                session,
                recent_timeline=recent_timeline,
            ),
            search_partner_candidates=_search_partner_candidates,
            sync_requester_persona_memory=_sync_requester_persona_memory,
            # propose_requester_profile_update=_propose_requester_profile_update,  # 已注释：暂时禁用此工具
            create_saved_search_subscription_from_last_search=_create_saved_search_subscription_from_last_search,
            suggest_assessment=_suggest_assessment,
            tool_call_buffer=tool_call_buffer,
            agent_session=self._agent_session_for(session.session_id),
        )

    def _replace_suggested_actions(
        self,
        session: StoredSession,
        suggestions: list[DiscoveryActionSuggestion],
        *,
        now: datetime,
    ) -> None:
        visible_action_ids: list[str] = []
        render_actions: list[dict[str, Any]] = []
        for suggestion in suggestions:
            action = self.storage.create_action(
                session_id=session.session_id,
                label=suggestion.label,
                style=suggestion.style,
                semantic_payload=suggestion.semantic_payload,
                now=now,
            )
            visible_action_ids.append(action.action_id)
            render_actions.append(
                suggested_action(
                    action.action_id,
                    action.label,
                    action.style,
                    action.semantic_payload,
                )
            )
        session.visible_action_ids = visible_action_ids
        session.view["suggested_actions"] = render_actions
        session.state["visible_action_ids"] = list(visible_action_ids)
        self.storage.replace_visible_actions(session.session_id, visible_action_ids)

    def _apply_runtime_result(
        self,
        session: StoredSession,
        runtime_result: DiscoveryRuntimeResult,
        *,
        now: datetime,
    ) -> int | None:
        decision = self._coerce_search_failure_decision(
            runtime_result.decision,
            runtime_result.search_response,
            session=session,  # 新增：传入session用于检测追问场景
        )
        assistant_body = decision.assistant_message
        if decision.criteria_labels:
            session.view["criteria_chips"] = [
                criteria_chip(f"chip-{index + 1}", label)
                for index, label in enumerate(decision.criteria_labels)
            ]
        search_run_id: int | None = None
        rendered_cards: list[dict[str, Any]] = []
        if runtime_result.search_response is not None:
            search_run_id = self._persist_search_run(
                session,
                search_response=runtime_result.search_response,
                now=now,
            )
            rendered_cards = self._build_result_cards(
                runtime_result.search_response,
                decision=decision,
            )
            proactive_blurb = None
            if decision.phase == "results_shown" and rendered_cards:
                proactive_blurb = self._build_proactive_personality_blurb(session, rendered_cards)
            if proactive_blurb and proactive_blurb not in assistant_body:
                assistant_body = f"{assistant_body} {proactive_blurb}".strip()
        elif decision.phase == "results_shown":
            # ✅ Agent Native：区分 reply_to_user 和 show_candidates
            # - reply_to_user（对话）：result_group_title 为 None
            #   - 如果 selected_candidates 有值：带上指定的候选人卡片（用户询问特定候选人）
            #   - 如果 selected_candidates 为空：不带卡片（纯对话）
            # - show_candidates（展示）：result_group_title 有值，应该带上候选人卡片
            if decision.result_group_title is None:
                # AI 只是想对话，根据 selected_candidates 决定是否带卡片
                if decision.selected_candidates:
                    # 用户询问特定候选人，带上指定的卡片
                    rendered_cards = self._reuse_existing_result_cards(session, decision=decision)
                else:
                    # 纯对话，不带卡片，使用 AI 的回复内容
                    rendered_cards = []
                    # 不触发 fallback，直接使用 decision.assistant_message
            else:
                # AI 想展示候选人，复用已有卡片
                rendered_cards = self._reuse_existing_result_cards(session, decision=decision)
                # 只有在"想展示但没卡片"时才触发 fallback
                if not rendered_cards:
                    decision = DiscoveryDecision(
                        phase="collecting_preferences",
                        assistant_message="我这轮还没真正跑出候选人卡片，你再发一次，我马上重新给你筛。",
                        criteria_labels=list(decision.criteria_labels),
                        suggested_actions=[],
                    )
                    assistant_body = decision.assistant_message
        # ====================================================================
        # 方案C：支持多条消息（reply_to_user + show_candidates）
        # ====================================================================
        # 检查是否有多个 payload
        all_payloads = getattr(decision, "_all_payloads", None)

        if all_payloads and len(all_payloads) > 1:
            # 方案C：处理多条消息
            # 按顺序添加每条消息到 timeline
            for payload in all_payloads:
                kind = str(payload.get("kind") or "").strip()
                message = str(payload.get("assistant_message") or "").strip()

                if kind == "reply":
                    # reply_to_user 的消息：纯对话
                    session.view["timeline"].append(
                        assistant_message(
                            self.storage.next_item_id("msg-a"),
                            message,
                            created_at=now,
                        )
                    )
                elif kind == "show":
                    # show_candidates 的消息：展示候选人
                    # 这条消息后面会跟着候选人卡片
                    assistant_body = message
                    # 添加 show_candidates 的消息
                    session.view["timeline"].append(
                        assistant_message(
                            self.storage.next_item_id("msg-a"),
                            assistant_body,
                            created_at=now,
                        )
                    )
        else:
            # 原有逻辑：只添加一条消息
            session.view["timeline"] = list(session.view.get("timeline") or []) + [
                assistant_message(
                    self.storage.next_item_id("msg-a"),
                    assistant_body,
                    created_at=now,
                )
            ]
        # 处理测评引导卡片
        assessment_payload = runtime_result.assessment_payload
        if assessment_payload and assessment_payload.get("suggest") and assessment_payload.get("card"):
            from .view_models import assessment_suggest
            session.view["timeline"].append(
                assessment_suggest(
                    item_id=self.storage.next_item_id("assessment"),
                    card=assessment_payload.get("card"),
                    created_at=now,
                )
            )
        for proposal in list(session.state.pop("profile_prompts_for_timeline", []) or []):
            if not proposal.get("proposed"):
                continue
            session.view["timeline"].append(
                profile_update_prompt_item(
                    item_id=self.storage.next_item_id("pur"),
                    request=proposal,
                    created_at=now,
                )
            )
        if rendered_cards:
            session.view["timeline"].append(
                result_group(
                    self.storage.next_item_id("group"),
                    decision.result_group_title or "这一轮先给你看这些候选人",
                    rendered_cards,
                )
            )
            shown_ids = [
                int(card.get("profile_id") or 0)
                for card in rendered_cards
                if int(card.get("profile_id") or 0) > 0
            ]
            if shown_ids:
                session.state["last_shown_candidate_ids"] = list(shown_ids)
                shown_history = [
                    int(candidate_id)
                    for candidate_id in list(session.state.get("shown_candidate_ids_history") or [])
                    if int(candidate_id) > 0
                ]
                seen = set(shown_history)
                for candidate_id in shown_ids:
                    if candidate_id not in seen:
                        shown_history.append(candidate_id)
                        seen.add(candidate_id)
                session.state["shown_candidate_ids_history"] = shown_history
        session.view["composer"] = composer("继续告诉红娘你的要求", disabled=False)
        session.phase = decision.phase
        session.updated_at = now
        self._replace_suggested_actions(session, decision.suggested_actions, now=now)
        session.state["phase"] = session.phase
        return search_run_id

    # ============================================================================
    # 遗留方法已删除（Agent Native 重构）
    # ============================================================================
    # _force_rejection_feedback_turn: 不再需要，Agent 自主处理反馈
    # _build_simple_feedback_reply: 硬编码回复模板，Agent 通过 reply_to_user 自主生成
    # _should_force_rejection_feedback_from_text: 不再需要，Agent 自主判断意图
    # _feedback_search_limit: 不再需要，Agent 自主决定搜索数量
    # _feedback_search_override: 不再需要，Agent 自主调整搜索条件
    # _dedupe_feedback_search_results: 不再需要，Agent 自主处理去重
    # ============================================================================

    # ✅ Agent Native：移除硬编码追问判断逻辑
    # Agent 根据 Prompt 中的追问原则自主判断追问时机
    # 参考：DISCOVERY_AGENT_SOUL.md "追问时机判断"部分
    # Agent 会根据对话上下文、用户性格、历史偏好自主决定是否追问
    # 不再通过硬编码关键词判断意图

    # 已废弃：_build_batch_refresh_prompt_result（硬编码追问逻辑）
    # Agent 自主决定追问方式，不再需要 fallback 函数

    def _build_result_cards(
        self,
        search_response: dict[str, Any],
        *,
        decision: DiscoveryDecision,
    ) -> list[dict[str, Any]]:
        results = list(search_response.get("results") or [])
        fallback_results = list(search_response.get("fallback_results") or [])
        card_candidates = results
        selected_by_id = {
            int(selection.profile_id): selection
            for selection in decision.selected_candidates
            if int(selection.profile_id) > 0
        }
        if not selected_by_id and decision.phase == "results_shown":
            selected_by_id = {
                int(candidate.get("id") or 0): DiscoveryCandidateSelection(
                    profile_id=int(candidate.get("id") or 0),
                    reason_summary=str(
                        candidate.get("match_reason")
                        or candidate.get("reason_summary")
                        or ""
                    ).strip(),
                )
                for candidate in results[:5]
                if int(candidate.get("id") or 0) > 0
            }
        elif not selected_by_id and decision.phase == "no_result" and fallback_results:
            card_candidates = fallback_results
            selected_by_id = {
                int(candidate.get("id") or 0): DiscoveryCandidateSelection(
                    profile_id=int(candidate.get("id") or 0),
                    reason_summary=str(
                        candidate.get("fallback_reason")
                        or candidate.get("match_reason")
                        or candidate.get("reason_summary")
                        or ""
                    ).strip(),
                )
                for candidate in fallback_results[:3]
                if int(candidate.get("id") or 0) > 0
            }
        cards: list[dict[str, Any]] = []
        for candidate in card_candidates:
            profile_id = int(candidate.get("id") or 0)
            selection = selected_by_id.get(profile_id)
            if selection is None:
                continue
            cards.append(
                build_candidate_card(
                    candidate,
                    reason_summary=_effective_reason_summary(candidate, selection.reason_summary),
                )
            )
        return cards

    def _existing_result_cards(self, session: StoredSession) -> list[dict[str, Any]]:
        for item in reversed(list(session.view.get("timeline") or [])):
            if item.get("item_type") == "result_group":
                return list(item.get("cards") or [])
        return []

    def _reuse_existing_result_cards(
        self,
        session: StoredSession,
        *,
        decision: DiscoveryDecision,
    ) -> list[dict[str, Any]]:
        existing_cards = self._existing_result_cards(session)
        if not existing_cards:
            return []
        selected_ids = {
            int(selection.profile_id)
            for selection in list(decision.selected_candidates or [])
            if int(selection.profile_id) > 0
        }
        if not selected_ids:
            return list(existing_cards)
        return [
            dict(card)
            for card in existing_cards
            if int(card.get("profile_id") or 0) in selected_ids
        ]

    # ✅ Agent Native：移除硬编码性格解释fallback机制
    # Agent 根据 Prompt 自主理解用户意图并生成性格解释回复
    # 当用户问”为什么推荐第一位”、”测评角度解释一下”等时，
    # Agent 会自主从 state.current_results 获取候选人信息并解释
    # 不再需要硬编码的 fallback 机制

    def _build_proactive_personality_blurb(
        self,
        session: StoredSession,
        cards: list[dict[str, Any]],
    ) -> str | None:
        requester_profile = self._load_requester_profile(session) or {}
        self_traits = dict(requester_profile.get("personality_traits") or {})
        if not self_traits:
            return None

        blurbs: list[str] = []
        for card in cards[:2]:
            reasoning = dict(card.get("personality_reasoning") or {})
            candidate_traits = dict(card.get("personality_match_context") or {})
            if reasoning.get("used"):
                candidate_name = _candidate_first_name(card)
                summary = str(reasoning.get("summary") or "").strip()
                if summary:
                    blurbs.append(f"{candidate_name}这位，{summary}。")
                    continue
            if not candidate_traits:
                continue
            candidate_name = _candidate_first_name(card)
            candidate_mbti = str((candidate_traits.get("mbti") or {}).get("type_code") or "").strip()
            candidate_attachment = str((candidate_traits.get("attachment") or {}).get("type_code") or "").strip()
            overlap = _shared_values(self_traits, candidate_traits)

            snippets: list[str] = []
            if candidate_mbti:
                self_mbti = str((self_traits.get("mbti") or {}).get("type_code") or "").strip()
                if self_mbti and self_mbti[:3] == candidate_mbti[:3]:
                    snippets.append(f"MBTI 和你更接近（{self_mbti}/{candidate_mbti}）")
                else:
                    snippets.append(f"MBTI 偏{candidate_mbti}，节奏比较稳")
            if candidate_attachment == "secure":
                snippets.append("依恋偏安全型")
            if overlap:
                snippets.append(f"价值观也和你同频，尤其都看重“{'、'.join(overlap[:2])}”")
            if snippets:
                blurbs.append(f"{candidate_name}这位，" + "，".join(snippets[:3]) + "。")
        if not blurbs:
            return None
        return "从测评角度看，" + "".join(blurbs)

    def _profile_first_session_open(
        self,
        session: StoredSession,
    ) -> tuple[DiscoveryRuntimeResult, list[DiscoveryToolCall]]:
        tool_call_buffer: list[DiscoveryToolCall] = []
        search_response = self._search_partner_candidates(
            session,
            criteria={},
            limit=PROFILE_FIRST_SEARCH_LIMIT,
        )
        self._append_tool_call(
            tool_call_buffer,
            "search_partner_candidates",
            {"criteria": {}, "limit": PROFILE_FIRST_SEARCH_LIMIT},
            search_response,
            status=self._tool_call_status("search_partner_candidates", search_response),
        )
        request_meta = dict(search_response.get("request_meta") or {})
        criteria_labels = criteria_labels_from_search_criteria(
            dict(request_meta.get("criteria") or {})
        )
        runtime_result = build_profile_first_open_result(
            search_response,
            criteria_labels=criteria_labels,
        )
        return runtime_result, tool_call_buffer

    def _build_runtime_context(
        self,
        session: StoredSession,
        *,
        recent_timeline: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return _build_runtime_context(
            self._build_service_context_runtime(),
            session,
            recent_timeline=recent_timeline,
            requester_profile_snapshot=self._load_requester_profile(session),
        )

    def _build_visible_action_summaries(self, session: StoredSession) -> list[dict[str, Any]]:
        return _build_visible_action_summaries(self._build_service_context_runtime(), session)

    def _build_last_search_summary(self, session: StoredSession) -> dict[str, Any] | None:
        return _build_last_search_summary(self._build_service_context_runtime(), session)

    def _build_page_summary(self, session: StoredSession) -> dict[str, Any]:
        return _build_page_summary(self._build_service_context_runtime(), session)

    def _search_error_summary(self, search_response: dict[str, Any] | None) -> dict[str, str] | None:
        return _search_error_summary_impl(search_response)

    def _candidates_match_existing_cards(
        self,
        session: StoredSession,
        selected_candidates: list[DiscoveryCandidateSelection],
    ) -> bool:
        """
        检测Agent返回的候选人是否来自对话记录中的现有卡片。

        用于区分两种场景：
        1. 追问场景：Agent从state.current_results获取候选人ID并返回 → 不是幻觉
        2. 幻觉场景：Agent没有搜索却凭空编造候选人ID → 是幻觉

        Returns:
            True: 候选人ID匹配现有卡片 → 不是幻觉，是追问场景
            False: 候选人ID不匹配 → 可能是幻觉
        """
        if not selected_candidates:
            return False

        existing_cards = self._existing_result_cards(session)
        if not existing_cards:
            return False

        existing_ids = {
            int(card.get("profile_id") or 0)
            for card in existing_cards
            if int(card.get("profile_id") or 0) > 0
        }

        selected_ids = {
            int(selection.profile_id)
            for selection in selected_candidates
            if int(selection.profile_id) > 0
        }

        # 如果所有Agent返回的候选人ID都在现有卡片中，说明是追问场景
        return selected_ids.issubset(existing_ids)

    def _coerce_search_failure_decision(
        self,
        decision: DiscoveryDecision,
        search_response: dict[str, Any] | None,
        session: StoredSession | None = None,
    ) -> DiscoveryDecision:
        if decision.phase == "searching" and search_response is None:
            return DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="我这轮还没真正发起筛选，你再点一次“先看看有没有人”，或者直接说“开始搜索”，我马上给你跑。",
                criteria_labels=list(decision.criteria_labels),
                suggested_actions=list(decision.suggested_actions),
            )
        # 检查：phase="results_shown" + 没搜索 + 返回了候选人
        # 这有两种情况：
        # 1. 追问场景：Agent从state.current_results获取候选人 → 不是幻觉，应该保留
        # 2. 幻觉场景：Agent凭空编造候选人 → 是幻觉，应该返回错误
        if (
            decision.phase == "results_shown"
            and search_response is None
            and bool(decision.selected_candidates)
        ):
            # 新增：检测候选人是否来自对话记录（追问场景）
            if session is not None and self._candidates_match_existing_cards(
                session, decision.selected_candidates
            ):
                # 追问场景：Agent从现有卡片中选择了候选人，不是幻觉
                # 应该保留Agent的decision，让回答正常展示
                return decision
            # 幻觉场景：Agent凭空编造了候选人，返回错误消息
            return DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="我这轮还没真正跑出候选人卡片，你再发一次，我马上重新给你筛。",
                criteria_labels=list(decision.criteria_labels),
                suggested_actions=[],
            )
        error_summary = self._search_error_summary(search_response)
        if error_summary is None:
            return decision
        error_code = str(error_summary.get("error_code") or "").strip()
        if error_code == "search_source_not_configured":
            message = "我这轮还没接上匹配资料库，先别把它当成没人。你可以稍后重试，或者继续补充条件，我再帮你筛。"
        else:
            message = "我这轮筛选没成功跑完，不代表没有合适人选。你可以稍后重试，或者继续补充条件，我再帮你筛。"
        return DiscoveryDecision(
            phase="collecting_preferences",
            assistant_message=message,
            criteria_labels=list(decision.criteria_labels),
            suggested_actions=[],
        )

    def _append_tool_call(
        self,
        tool_call_buffer: list[DiscoveryToolCall],
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        *,
        status: str = "succeeded",
    ) -> None:
        tool_call_buffer.append(
            DiscoveryToolCall(
                tool_name=tool_name,
                arguments=deepcopy(arguments),
                result=deepcopy(result),
                status=status,
            )
        )

    def _tool_call_status(self, tool_name: str, result: dict[str, Any]) -> str:
        del tool_name
        if not isinstance(result, dict):
            return "failed"
        if str(result.get("error_code") or "").strip():
            return "failed"
        diagnostics = dict(result.get("diagnostics") or {})
        if str(diagnostics.get("error") or "").strip():
            return "failed"
        if result.get("synced") is False:
            return "failed"
        return "succeeded"

    def _record_tool_calls(
        self,
        *,
        session_id: str,
        turn_id: int,
        tool_calls: list[DiscoveryToolCall],
        search_run_id: int | None,
        created_at: datetime,
        trace_id: str | None,
    ) -> None:
        if not tool_calls:
            return
        linked_search_index: int | None = None
        if search_run_id is not None:
            for index, tool_call in enumerate(tool_calls):
                if tool_call.tool_name == "search_partner_candidates":
                    linked_search_index = index
        for index, tool_call in enumerate(tool_calls):
            self.storage.create_tool_call(
                session_id=session_id,
                turn_id=turn_id,
                tool_name=tool_call.tool_name,
                arguments=tool_call.arguments,
                result=tool_call.result,
                status=tool_call.status,
                search_run_id=search_run_id if linked_search_index == index else None,
                created_at=created_at,
                trace_id=trace_id,
            )
            self._increment_metric("tool_calls.total")
            self._increment_metric(f"tool_calls.{tool_call.tool_name}")
            if tool_call.status != "succeeded":
                self._increment_metric("tool_calls.failed")
            audit_event(
                action="discovery.tool_call",
                resource_type="discovery_tool_call",
                outcome=tool_call.status,
                resource_id=f"{session_id}:{turn_id}:{index + 1}",
                session_id=session_id,
                turn_id=turn_id,
                tool_name=tool_call.tool_name,
                search_run_id=search_run_id if linked_search_index == index else None,
            )

    def _persist_view_snapshot(
        self,
        session: StoredSession,
        *,
        turn_id: int | None,
        created_at: datetime,
        trace_id: str | None,
    ) -> int:
        snapshot_id = self.storage.create_view_snapshot(
            session_id=session.session_id,
            turn_id=turn_id,
            phase=session.phase,
            view_snapshot=clone_view(session.view),
            created_at=created_at,
            trace_id=trace_id,
        )
        session.state["last_view_snapshot_id"] = snapshot_id
        self.storage.save_session(session)
        self._increment_metric("view_snapshots.written")
        audit_event(
            action="discovery.view_snapshot.write",
            resource_type="discovery_view_snapshot",
            outcome="written",
            resource_id=snapshot_id,
            session_id=session.session_id,
            turn_id=turn_id,
            phase=session.phase,
        )
        return snapshot_id

    def _current_trace_id(self) -> str | None:
        return get_trace_id()

    def _increment_metric(self, name: str, amount: int = 1, **tags: Any) -> int:
        next_value = int(self.metric_counters.get(name) or 0) + int(amount)
        self.metric_counters[name] = next_value
        metric_gauge(
            f"discovery.{name}",
            next_value,
            **{key: value for key, value in tags.items() if value not in (None, "")},
        )
        return next_value

    def _load_requester_profile(self, session: StoredSession) -> dict[str, Any] | None:
        profile = _load_requester_profile_impl(
            session,
            source=self._profile_source(),
            load_profile=load_self_profile,
        )
        # === Phase 1: 注入 personality_traits ===
        if profile and session.profile_id:
            persona_source = self._persona_memory_source()
            if persona_source:
                traits_ctx = load_traits_for_discovery(
                    source=persona_source,
                    profile_id=session.profile_id,
                    requester_id=session.requester_id,
                )
                if traits_ctx and traits_ctx.availability.get("overall_completeness", 0) > 0:
                    profile["personality_traits"] = traits_ctx.to_dict()
                    profile["personality_availability"] = traits_ctx.availability
        return profile

    def _search_partner_candidates(
        self,
        session: StoredSession,
        *,
        criteria: dict[str, Any],
        personality_match: dict[str, Any] = {},  # ← 新增参数
        limit: int,
        exclude_current_results: bool = False,
    ) -> dict[str, Any]:
        # ✅ 参数预处理：如果需要排除当前结果，将 last_shown_candidate_ids 转换为 exclude_ids
        if exclude_current_results:
            refresh_exclude_ids = {
                int(candidate_id)
                for candidate_id in list(session.state.get("last_shown_candidate_ids") or [])
                if int(candidate_id) > 0
            }
            if refresh_exclude_ids:
                existing_exclude_ids = criteria.get("exclude_ids")
                normalized_exclude_ids: set[int] = set()
                if isinstance(existing_exclude_ids, (list, tuple, set)):
                    for candidate_id in existing_exclude_ids:
                        try:
                            normalized_exclude_ids.add(int(candidate_id))
                        except (TypeError, ValueError):
                            continue
                elif existing_exclude_ids not in (None, ""):
                    try:
                        normalized_exclude_ids.add(int(existing_exclude_ids))
                    except (TypeError, ValueError):
                        pass
                criteria["exclude_ids"] = list(normalized_exclude_ids | refresh_exclude_ids)

        return _search_partner_candidates_impl(
            session,
            criteria=criteria,
            personality_match=personality_match,  # ← 传递参数
            limit=limit,
            exclude_current_results=exclude_current_results,
            source=self._profile_source(),
            load_profile=load_self_profile,
            search=search_profiles,
        )

    def _profile_source(self) -> str:
        return _profile_source_impl()

    def _persona_memory_source(self) -> str:
        return _persona_memory_source_impl()

    def _sync_requester_persona_memory(
        self,
        session: StoredSession,
        *,
        patch: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return _sync_requester_persona_memory_impl(
            session,
            patch=patch,
            now=now,
            load_persona_memory=self._load_persona_memory_bindings(),
            storage=self.storage,
            load_profile=load_self_profile,
            source=self._profile_source(),
        )

    # def _propose_requester_profile_update(
    #     self,
    #     session: StoredSession,
    #     *,
    #     patch: dict[str, Any],
    #     evidence_text: str | None = None,
    #     now: datetime | None = None,
    # ) -> dict[str, Any]:
    #     return _propose_requester_profile_update_impl(
    #         self.storage,
    #         session,
    #         patch=patch,
    #         evidence_text=evidence_text,
    #         load_profile=load_self_profile,
    #         source=self._profile_source(),
    #         now=now,
    #     )

    def confirm_profile_update(
        self,
        session_id: str,
        request_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        session = self._require_session(session_id)
        try:
            from profile_service import apply_profile_updates, resolve_profile_source

            source_dsn, source_table = resolve_profile_source(self._profile_source())
            result = _confirm_profile_update_impl(
                self.storage,
                session,
                request_id=request_id,
                apply_profile_updates_fn=apply_profile_updates,
                source_dsn=source_dsn,
                source_table_name=source_table,
                now=now,
            )
        except ProfileUpdateRequestNotFoundError as exc:
            raise DiscoveryProfileUpdateNotFoundError(str(exc)) from exc
        except ProfileUpdateRequestConflictError as exc:
            raise DiscoveryProfileUpdateConflictError(str(exc)) from exc
        self._refresh_profile_update_prompt_status(session, request_id, "confirmed", now=now or datetime.now())
        self.storage.save_session(session)
        return result

    def reject_profile_update(
        self,
        session_id: str,
        request_id: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        session = self._require_session(session_id)
        try:
            result = _reject_profile_update_impl(
                self.storage,
                session,
                request_id=request_id,
                now=now,
            )
        except ProfileUpdateRequestNotFoundError as exc:
            raise DiscoveryProfileUpdateNotFoundError(str(exc)) from exc
        except ProfileUpdateRequestConflictError as exc:
            raise DiscoveryProfileUpdateConflictError(str(exc)) from exc
        self._refresh_profile_update_prompt_status(session, request_id, "rejected", now=now or datetime.now())
        self.storage.save_session(session)
        return result

    def _refresh_profile_update_prompt_status(
        self,
        session: StoredSession,
        request_id: str,
        status: str,
        *,
        now: datetime,
    ) -> None:
        for item in list(session.view.get("timeline") or []):
            if str(item.get("item_type") or "") != "profile_update_prompt":
                continue
            prompt = dict(item.get("prompt") or {})
            if str(prompt.get("request_id") or "") != str(request_id):
                continue
            prompt["status"] = status
            item["prompt"] = prompt
        session.updated_at = now

    def _build_profile_detail_notes(
        self,
        session: StoredSession | None,
        profile_id: int,
    ) -> list[str]:
        return _build_profile_detail_notes(session, profile_id)

    def _persist_search_run(
        self,
        session: StoredSession,
        *,
        search_response: dict[str, Any],
        now: datetime,
    ) -> int | None:
        return _persist_search_run_impl(
            self.storage,
            self._increment_metric,
            session,
            search_response=search_response,
            now=now,
        )

    def _create_saved_search_subscription_from_last_search(
        self,
        session: StoredSession,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        current = now or datetime.now()
        search_run_id = int(session.state.get("last_search_run_id") or 0)
        if search_run_id <= 0:
            return {
                "created_subscription": False,
                "error_code": "no_last_search_run",
                "message": "当前还没有可用于持续留意的搜索记录。",
            }

        if int(session.state.get("last_opt_in_search_run_id") or 0) == search_run_id:
            existing_subscription_id = str(session.state.get("last_created_subscription_id") or "").strip()
            if existing_subscription_id:
                return {
                    "created_subscription": False,
                    "already_exists": True,
                    "subscription_id": existing_subscription_id,
                    "title": str(session.state.get("last_created_subscription_title") or "").strip() or None,
                    "search_run_id": search_run_id,
                }

        search_run = self.storage.get_search_run(search_run_id)
        if search_run is None:
            return {
                "created_subscription": False,
                "error_code": "search_run_not_found",
                "message": "上一轮搜索记录不存在，暂时不能创建持续留意。",
            }
        error_summary = self._search_error_summary(dict(search_run.response or {}))
        if error_summary is not None:
            return {
                "created_subscription": False,
                "error_code": "search_run_failed",
                "message": "上一轮搜索没有成功跑完，当前不能创建持续留意。",
                "search_error_code": str(error_summary.get("error_code") or "") or None,
            }
        if search_run.has_match or int(search_run.result_count or 0) > 0:
            return {
                "created_subscription": False,
                "error_code": "search_run_not_empty",
                "message": "上一轮不是空结果，当前不需要创建持续留意。",
            }

        request_meta = dict((search_run.response or {}).get("request_meta") or {})
        effective_self_id = request_meta["self_id"] if "self_id" in request_meta else session.profile_id
        search_request = {
            "source": request_meta.get("source") or search_run.source,
            "criteria": dict(request_meta.get("criteria") or search_run.criteria or {}),
            "self_profile": deepcopy(request_meta.get("self_profile") or search_run.self_profile),
            "self_id": effective_self_id,
            "table_name": request_meta.get("table_name"),
            "photos_table_name": request_meta.get("photos_table_name"),
            "limit": int(request_meta.get("limit_count") or search_run.limit_count or 5),
            "photo_preview_count": 0,
            "include_source": True,
            "include_text": False,
        }

        conn = self._open_recommendation_conn()
        try:
            _, handle_opt_in_decision, _ = self._load_recommendation_bindings()
            decision = handle_opt_in_decision(
                conn,
                requester_id=session.requester_id,
                search_session={
                    "needs_opt_in_prompt": True,
                    "search_request": search_request,
                },
                user_opted_in=True,
                title=self._build_saved_search_title(session),
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "created_subscription": False,
                "error_code": "subscription_create_failed",
                "message": str(exc)[:200],
            }
        finally:
            conn.close()

        subscription = dict(decision.get("subscription") or {})
        if not decision.get("created_subscription") or not subscription:
            return {
                "created_subscription": False,
                "error_code": "subscription_not_created",
                "message": "持续留意没有创建成功。",
            }

        session.state["last_opt_in_search_run_id"] = search_run_id
        session.state["last_created_subscription_id"] = str(subscription.get("subscription_id") or "")
        session.state["last_created_subscription_title"] = str(subscription.get("title") or "")
        session.state["last_created_subscription_at"] = current.isoformat()
        return {
            "created_subscription": True,
            "already_exists": False,
            "subscription_id": str(subscription.get("subscription_id") or ""),
            "title": str(subscription.get("title") or ""),
            "search_run_id": search_run_id,
        }

    def _build_saved_search_title(self, session: StoredSession) -> str:
        labels = [
            str(item.get("label") or "").strip()
            for item in list(session.view.get("criteria_chips") or [])
            if str(item.get("label") or "").strip()
        ]
        if labels:
            return "持续留意：" + " / ".join(labels[:3])
        return f"持续留意 {session.requester_id}"

    def _open_recommendation_conn(self):
        return _open_recommendation_conn_impl(
            load_bindings=self._load_recommendation_bindings,
        )

    def _load_recommendation_bindings(self):
        return _load_recommendation_bindings_impl()

    def _load_persona_memory_bindings(self):
        return _load_persona_memory_bindings_impl()

    def _decision_payload(self, decision: DiscoveryDecision) -> dict[str, Any]:
        return _decision_payload_impl(decision)

    def _build_proxy_intro_title(self, session: StoredSession, candidate: dict[str, Any]) -> str:
        candidate_name = str(candidate.get("name") or "").strip()
        if candidate_name:
            return f"牵线中：{candidate_name}"
        return self._build_saved_search_title(session)

    def _find_candidate_in_search_run(
        self,
        response: dict[str, Any] | None,
        candidate_id: int,
    ) -> dict[str, Any] | None:
        normalized_id = int(candidate_id)
        payload = dict(response or {})
        for key in ("results", "fallback_results"):
            for item in list(payload.get(key) or []):
                try:
                    item_id = int(item.get("id") or 0)
                except (TypeError, ValueError):
                    item_id = 0
                if item_id == normalized_id:
                    return deepcopy(item)
        return None

    def _require_session(self, session_id: str) -> StoredSession:
        session = self.storage.get_session(session_id)
        if session is None:
            raise DiscoverySessionNotFoundError("discovery session not found")
        return session

    def _agent_session_for(self, session_id: str) -> Any | None:
        """同步反馈到persona。"""
        # FEEDBACK_TO_CRITERIA_ADJUSTMENT 已删除
        # persona_write 不再硬编码，AI 自主决定是否同步 persona
        # strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get(feedback_type)  # 已删除
        # strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get(feedback_type)  # 已删除
        # TODO: AI 根据 Prompt 自主决定是否调用 sync_requester_persona_memory
        return False  # 暂时返回 False，由 AI 自主决定
        # TODO: 调用sync_requester_persona_memory工具
        # 这里需要调用persona memory API

        return True

    def _get_last_search_run(self, session_id: str) -> StoredSearchRun | None:
        """获取session的最后一次搜索结果。"""
        session = self.storage.get_session(session_id)
        if session is None:
            return None
        search_run_id = int(session.state.get("last_search_run_id") or 0)
        if search_run_id <= 0:
            return None
        return self.storage.get_search_run(search_run_id)

    def _suggest_assessment(
        self,
        session: StoredSession,
        *,
        assessment_type: str = "mbti_16",
    ) -> dict[str, Any]:
        """检查用户测评状态，返回引导卡片或性格信息。"""
        from .service_integrations import persona_memory_source, suggest_assessment_with
        return suggest_assessment_with(
            profile_id=session.profile_id,
            assessment_type=assessment_type,
            source=persona_memory_source(),
        )

    def _agent_session_for(self, session_id: str) -> Any | None:
        if self.agent_session_store is None:
            return None
        return self.agent_session_store.get_session(session_id)

    def _trigger_previous_session_processing(
        self,
        requester_id: int,
        profile_id: int,
        conversation_type: str = "discovery",
        current_session_id: str | None = None,  # ✅ 新增：传入刚创建的会话 ID
    ) -> None:
        """新建会话时，异步处理用户的上一个会话

        关键设计：
        - 不阻塞主流程（异步后台处理）
        - 只在新建会话时触发（不影响当前对话）
        - 从数据库加载聊天记录（避免时序漏洞）
        - 传入 current_session_id 避免把新会话误当作上一个会话处理
        """
        import logging
        from match_domain.session_end_trigger import process_previous_session_on_new_session

        _logger = logging.getLogger(__name__)

        try:
            task = process_previous_session_on_new_session(
                requester_id=requester_id,
                profile_id=profile_id,
                current_session_id=current_session_id,  # ✅ 新增：传入刚创建的会话 ID
                storage=self.storage,
                conversation_type=conversation_type,
            )

            if task:
                _logger.info(
                    f"触发上一个会话处理: requester_id={requester_id}, "
                    f"profile_id={profile_id}, task_name={task.name}"
                )

        except Exception as exc:
            _logger.error(f"触发上一个会话处理失败: requester_id={requester_id}, error={exc}")
            # 不抛出异常，避免阻塞新建会话

    def _session_payload(self, session: StoredSession) -> dict[str, Any]:
        return {
            "session": {
                "session_id": session.session_id,
                "status": session.status,
                "phase": session.phase,
                "updated_at": session.updated_at.isoformat(),
            },
            "view": clone_view(session.view),
        }

    def _build_service_context_runtime(self) -> DiscoveryServiceContextRuntime:
        return DiscoveryServiceContextRuntime(
            storage=self.storage,
            clone_view=clone_view,
        )

def create_default_discovery_service(*, discovery_dsn: str | None = None) -> DiscoveryService:
    resolved_dsn = str(discovery_dsn or os.environ.get("PARTNER_DISCOVERY_DB") or "").strip()
    storage = MySQLDiscoveryStorage(resolved_dsn) if resolved_dsn else InMemoryDiscoveryStorage()

    # 新增：启动定时任务调度器
    _start_background_scheduler(storage, discovery_dsn=resolved_dsn)

    return DiscoveryService(
        storage=storage,
        runtime=create_default_discovery_agent_runtime(),
        agent_session_store=create_default_discovery_agent_session_store(discovery_dsn=resolved_dsn),
    )


def _start_background_scheduler(storage: Any, *, discovery_dsn: str | None = None) -> None:
    """启动后台定时任务调度器

    定时任务功能：
    1. 每5分钟检查无活动会话（超过30分钟无活动）
    2. 每10分钟检查失败的向量写入并重试（最多3次）
    3. 每24小时清理旧版本向量（节省存储空间）
    4. 自动触发摘要处理和向量写入

    配置项：
    - interval_minutes: 5分钟检查一次（会话）
    - retry_interval_minutes: 10分钟检查一次（向量重试）
    - cleanup_interval_hours: 24小时清理一次（版本清理）
    - inactive_threshold_minutes: 30分钟无活动阈值
    - max_retry_count: 最大重试次数3次
    """
    import asyncio
    import logging
    from match_domain.session_end_scheduler import (
        start_inactive_session_checker,
        start_vector_retry_checker,
        start_version_cleanup_checker,
    )

    _logger = logging.getLogger(__name__)

    try:
        # 检查是否启用定时任务（默认启用）
        enable_scheduler = os.environ.get("ENABLE_SESSION_END_SCHEDULER", "1")
        if enable_scheduler != "1":
            _logger.info("定时任务调度器已禁用: ENABLE_SESSION_END_SCHEDULER != 1")
            return

        # 获取 LLM 配置
        llm_base_url = os.environ.get("HER_DISCOVERY_AGENT_BASE_URL")
        llm_api_key = os.environ.get("HER_DISCOVERY_AGENT_API_KEY")
        llm_model = os.environ.get("HER_DISCOVERY_AGENT_MODEL")
        persona_dsn = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE")

        # 创建异步任务
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 如果事件循环已运行，创建三个任务
            # 任务1：无活动会话检查
            task1 = loop.create_task(
                start_inactive_session_checker(
                    storage=storage,
                    interval_minutes=5,
                    inactive_threshold_minutes=30,
                    dsn=persona_dsn,
                    llm_base_url=llm_base_url,
                    llm_api_key=llm_api_key,
                    llm_model=llm_model,
                )
            )
            _logger.info(
                f"无活动会话检查定时任务已启动: task_name={task1.get_name()}, "
                f"interval=5分钟, threshold=30分钟"
            )

            # 任务2：向量重试检查
            task2 = loop.create_task(
                start_vector_retry_checker(
                    storage=storage,
                    interval_minutes=10,
                    max_retry_count=3,
                    dsn=persona_dsn,
                )
            )
            _logger.info(
                f"向量重试检查定时任务已启动: task_name={task2.get_name()}, "
                f"interval=10分钟, max_retry=3次"
            )

            # 任务3：版本清理
            task3 = loop.create_task(
                start_version_cleanup_checker(
                    storage=storage,
                    interval_hours=24,
                    dsn=persona_dsn,
                )
            )
            _logger.info(
                f"版本清理定时任务已启动: task_name={task3.get_name()}, "
                f"interval=24小时"
            )
        else:
            _logger.warning("事件循环未运行，无法启动定时任务调度器")

    except Exception as exc:
        _logger.error(f"启动定时任务调度器失败: {exc}")
        # 不抛出异常，避免影响服务启动
