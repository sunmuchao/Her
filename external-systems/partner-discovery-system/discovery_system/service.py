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
    parse_rejection_feedback_text,
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
    propose_requester_profile_update as _propose_requester_profile_update_impl,
    search_partner_candidates as _search_partner_candidates_impl,
    sync_requester_persona_memory as _sync_requester_persona_memory_impl,
)
from match_domain.profile_write_guard import is_search_criteria_key, merge_working_criteria
from partner_search.personality_traits_reader import load_traits_for_discovery
from .storage import InMemoryDiscoveryStorage, MySQLDiscoveryStorage, StoredSearchRun, StoredSession
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

_BATCH_REFRESH_PATTERNS = (
    "换一批",
    "重新找",
    "再看几位",
    "再给我看看",
    "看看更多",
    "看更多",
    "换一组",
)


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


def _is_personality_explanation_request(text: str | None) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    keywords = ("为什么", "测评", "MBTI", "依恋", "价值观", "合拍", "性格")
    return "不要重新搜索" in value or any(keyword in value for keyword in keywords)


def _pick_existing_candidate(cards: list[dict[str, Any]], user_message_text: str | None) -> dict[str, Any] | None:
    if not cards:
        return None
    text = str(user_message_text or "")
    markers = (("第一位", 0), ("第一个", 0), ("1", 0), ("第二位", 1), ("第二个", 1), ("2", 1), ("第三位", 2), ("第三个", 2), ("3", 2))
    for marker, index in markers:
        if marker in text and index < len(cards):
            return dict(cards[index] or {})
    for card in cards:
        title = str(card.get("title") or "").strip()
        name = re.split(r"\s+", title, maxsplit=1)[0] if title else ""
        if name and name in text:
            return dict(card)
    return dict(cards[0] or {})


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


def _looks_like_basic_reason_summary(text: str | None) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    personality_keywords = ("MBTI", "依恋", "价值观", "同频", "安全型", "测评", "节奏")
    if any(keyword in value for keyword in personality_keywords):
        return False
    generic_keywords = ("城市", "年龄", "关系目标", "工作", "状态", "学历", "认证")
    return any(keyword in value for keyword in generic_keywords)


def _effective_reason_summary(candidate: dict[str, Any], selection_reason: str | None) -> str:
    reasoning = dict(candidate.get("personality_reasoning") or {})
    personality_summary = str(reasoning.get("summary") or "").strip()
    selected_summary = str(selection_reason or "").strip()
    if personality_summary and _looks_like_basic_reason_summary(selected_summary):
        return personality_summary
    return selected_summary


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
        return self._session_payload(session)

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
            parsed_feedback = self._parse_rejection_feedback_from_text(session, text)
            new_items.append(
                user_message(
                    self.storage.next_item_id("msg-u"),
                    text,
                    created_at=current,
                )
            )
            if self._should_prompt_for_batch_refresh_feedback(session, user_message_text=text):
                runtime_result = self._build_batch_refresh_prompt_result(run_input)
            elif self._should_force_rejection_feedback_from_text(session, parsed_feedback):
                runtime_result = self._force_rejection_feedback_turn(
                    session,
                    run_input=run_input,
                    action_context={
                        "label": text,
                        "semantic_payload": {
                            "kind": "rejection_feedback",
                            "feedback_type": str(parsed_feedback.get("feedback_type") or "").strip(),
                            "feedback_text": text,
                            "search_criteria_patch": dict(parsed_feedback.get("search_criteria_patch") or {}),
                        },
                    },
                    now=current,
                )
            else:
                runtime_result = self.runtime.run_turn(
                    run_input,
                    user_message=text,
                )
            fallback_decision = self._build_personality_explanation_decision(
                session,
                user_message_text=text,
            )
            if (
                fallback_decision is not None
                and runtime_result.search_response is None
                and runtime_result.decision.phase == "collecting_preferences"
            ):
                runtime_result = DiscoveryRuntimeResult(decision=fallback_decision)
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
            action_context = {
                "label": action.label,
                "semantic_payload": deepcopy(action.semantic_payload),
            }
            action_kind = str(action_context["semantic_payload"].get("kind") or "").strip()
            if action_kind == "show_more_candidates":
                runtime_result = self._build_batch_refresh_prompt_result(run_input)
            elif action_kind == "rejection_feedback":
                runtime_result = self._force_rejection_feedback_turn(
                    session,
                    run_input=run_input,
                    action_context=action_context,
                    now=current,
                )
            else:
                runtime_result = self.runtime.run_turn(
                    run_input,
                    action_context=action_context,
                )

        session.view["timeline"] = list(session.view.get("timeline") or []) + new_items
        search_run_id = self._apply_runtime_result(session, runtime_result, now=current)
        self._update_rejection_feedback_waiting_state(
            session,
            user_message_text=normalized_user_message,
            runtime_result=runtime_result,
        )
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

        def _search_partner_candidates(criteria: dict[str, Any], limit: int) -> dict[str, Any]:
            response = self._search_partner_candidates(
                session,
                criteria=criteria,
                limit=limit,
            )
            self._append_tool_call(
                tool_call_buffer,
                "search_partner_candidates",
                {
                    "criteria": deepcopy(criteria),
                    "limit": int(limit or 0),
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

        def _propose_requester_profile_update(patch_json: str, evidence_text: str = "") -> dict[str, Any]:
            import json

            patch = json.loads(str(patch_json or "{}"))
            if not isinstance(patch, dict):
                raise ValueError("patch_json must decode into a JSON object")
            result = self._propose_requester_profile_update(
                session,
                patch=patch,
                evidence_text=str(evidence_text or "").strip() or None,
                now=now,
            )
            if result.get("proposed"):
                pending_timeline = list(session.state.get("profile_prompts_for_timeline") or [])
                pending_timeline.append(result)
                session.state["profile_prompts_for_timeline"] = pending_timeline
            self._append_tool_call(
                tool_call_buffer,
                "propose_requester_profile_update",
                {"patch": deepcopy(patch), "evidence_text": evidence_text},
                result,
                status="succeeded" if result.get("proposed") else "skipped",
            )
            return result

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
            propose_requester_profile_update=_propose_requester_profile_update,
            create_saved_search_subscription_from_last_search=_create_saved_search_subscription_from_last_search,
            # 新增：反馈收集工具
            submit_rejection_feedback=self._bind_submit_rejection_feedback(session),
            get_feedback_options=self._bind_get_feedback_options(session),
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
            rendered_cards = self._reuse_existing_result_cards(session, decision=decision)
            if not rendered_cards:
                decision = DiscoveryDecision(
                    phase="collecting_preferences",
                    assistant_message="我这轮还没真正跑出候选人卡片，你再发一次，我马上重新给你筛。",
                    criteria_labels=list(decision.criteria_labels),
                    suggested_actions=[],
                )
                assistant_body = decision.assistant_message
        session.view["timeline"] = list(session.view.get("timeline") or []) + [
            assistant_message(
                self.storage.next_item_id("msg-a"),
                assistant_body,
                created_at=now,
            )
        ]
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
        session.view["composer"] = composer("继续告诉红娘你的要求", disabled=False)
        session.phase = decision.phase
        session.updated_at = now
        self._replace_suggested_actions(session, decision.suggested_actions, now=now)
        session.state["phase"] = session.phase
        return search_run_id

    def _force_rejection_feedback_turn(
        self,
        session: StoredSession,
        *,
        run_input: DiscoveryRunInput,
        action_context: dict[str, Any],
        now: datetime,
    ) -> DiscoveryRuntimeResult:
        payload = dict(action_context.get("semantic_payload") or {})
        feedback_type = str(payload.get("feedback_type") or "").strip()
        feedback_text = str(payload.get("feedback_text") or action_context.get("label") or "这批先换一下").strip()
        criteria_patch = dict(payload.get("search_criteria_patch") or {})

        if feedback_type == "skip_feedback":
            feedback_result = self.skip_rejection_feedback(session_id=session.session_id, now=now)
            self._append_tool_call(
                run_input.tool_call_buffer,
                "submit_rejection_feedback",
                {
                    "feedback_text": feedback_text,
                    "feedback_type": feedback_type,
                    "is_secondary": False,
                },
                feedback_result,
                status="succeeded" if feedback_result.get("success") else "failed",
            )
        else:
            feedback_result = run_input.submit_rejection_feedback(
                feedback_text=feedback_text,
                feedback_type=feedback_type or None,
                criteria_patch=criteria_patch,
                feedback_detail=None,
                is_secondary=False,
            )
            self._append_tool_call(
                run_input.tool_call_buffer,
                "submit_rejection_feedback",
                {
                    "feedback_text": feedback_text,
                    "feedback_type": feedback_type or None,
                    "criteria_patch": deepcopy(criteria_patch),
                    "is_secondary": False,
                },
                feedback_result,
                status="succeeded" if feedback_result.get("success") else "failed",
            )

        refreshed_session = self.storage.get_session(session.session_id)
        if refreshed_session is not None:
            session.state.update(deepcopy(refreshed_session.state))

        criteria_override = self._feedback_search_override(
            session,
            feedback_type=feedback_type,
            action_context=action_context,
        )
        limit = self._feedback_search_limit(session)
        search_response = run_input.search_partner_candidates(criteria_override, limit)
        prepared_response = self._dedupe_feedback_search_results(session, search_response)
        request_meta = dict(prepared_response.get("request_meta") or {})
        criteria_labels = criteria_labels_from_search_criteria(dict(request_meta.get("criteria") or {}))
        has_results = bool(prepared_response.get("has_match")) and bool(prepared_response.get("results"))

        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="results_shown" if has_results else "no_result",
                assistant_message=self._feedback_followup_message(
                    feedback_type=feedback_type,
                    feedback_text=feedback_text,
                    has_results=has_results,
                ),
                criteria_labels=criteria_labels,
                suggested_actions=[],
                result_group_title="按你刚才的反馈，重新给你换一批",
                selected_candidates=selected_candidates_from_search(prepared_response) if has_results else [],
            ),
            search_response=prepared_response,
        )

    def _feedback_search_limit(self, session: StoredSession) -> int:
        search_run_id = int(session.state.get("last_search_run_id") or 0)
        if search_run_id > 0:
            search_run = self.storage.get_search_run(search_run_id)
            if search_run is not None and int(search_run.limit_count or 0) > 0:
                return max(1, min(int(search_run.limit_count or 5), 10))
        return PROFILE_FIRST_SEARCH_LIMIT

    def _feedback_search_override(
        self,
        session: StoredSession,
        *,
        feedback_type: str,
        action_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        override: dict[str, Any] = {}
        payload = dict((action_context or {}).get("semantic_payload") or {})
        parsed_patch = dict(payload.get("search_criteria_patch") or {})
        for key, value in parsed_patch.items():
            if value not in (None, "", [], {}):
                override[key] = value
        requester_profile = self._load_requester_profile(session) or {}
        self_city = str(requester_profile.get("city") or requester_profile.get("self_city") or "").strip()
        self_age_raw = requester_profile.get("age") or requester_profile.get("self_age")
        try:
            self_age = int(self_age_raw) if self_age_raw not in (None, "") else None
        except (TypeError, ValueError):
            self_age = None

        if feedback_type == "location_distance" and self_city:
            override["cities"] = [self_city]
        elif feedback_type in {"age_gap", "criteria_age"} and self_age is not None:
            override["age_min"] = max(18, self_age - 3)
            override["age_max"] = self_age + 3
        return override

    def _dedupe_feedback_search_results(
        self,
        session: StoredSession,
        search_response: dict[str, Any],
    ) -> dict[str, Any]:
        response = deepcopy(search_response)
        previous_ids = {
            int(card.get("profile_id") or 0)
            for card in self._existing_result_cards(session)
            if int(card.get("profile_id") or 0) > 0
        }
        if not previous_ids:
            return response
        original_results = list(response.get("results") or [])
        filtered_results = [
            item for item in original_results
            if int(item.get("id") or 0) not in previous_ids
        ]
        if not filtered_results:
            return response
        response["results"] = filtered_results
        response["result_count"] = len(filtered_results)
        response["has_match"] = bool(filtered_results)
        return response

    def _feedback_followup_message(
        self,
        *,
        feedback_type: str,
        feedback_text: str,
        has_results: bool,
    ) -> str:
        if has_results:
            if feedback_type == "occupation_mismatch":
                return "明白了，你更在意职业方向。我按这个意思重新筛了一批，先看这组。"
            if feedback_type == "location_distance":
                return "明白了，你更希望距离近一点。我按同城优先重新筛了一批。"
            if feedback_type in {"age_gap", "criteria_age"}:
                return "明白了，你更想看年龄更接近的。我按这个方向重新筛了一批。"
            if feedback_type == "work_life_balance":
                return "明白了，你更在意生活节奏。我按更稳定的作息方向重新筛了一批。"
            if feedback_type == "interest_mismatch":
                return "明白了，你更在意能不能玩到一起。我按这个方向重新筛了一批。"
            return "收到，我按你刚才的意思重新筛了一批，你先看这组。"

        if feedback_type == "occupation_mismatch":
            return "明白了，你更在意职业方向。我按这个意思重筛了一轮，但这次还没出到更合适的，你可以再补一句更想看什么类型。"
        return f"收到，你刚才提到“{feedback_text}”。我已经按这个方向重筛了一轮，这次还没出到更合适的。"

    def _should_force_rejection_feedback_from_text(
        self,
        session: StoredSession,
        parsed_feedback: dict[str, Any],
    ) -> bool:
        if not bool(session.state.get("awaiting_rejection_feedback")):
            return False
        return bool(parsed_feedback.get("is_rejection_feedback"))

    def _should_prompt_for_batch_refresh_feedback(
        self,
        session: StoredSession,
        *,
        user_message_text: str | None,
    ) -> bool:
        if bool(session.state.get("awaiting_rejection_feedback")):
            return False
        text = str(user_message_text or "").strip()
        if not text:
            return False
        return any(pattern in text for pattern in _BATCH_REFRESH_PATTERNS)

    def _build_batch_refresh_prompt_result(
        self,
        run_input: DiscoveryRunInput,
    ) -> DiscoveryRuntimeResult:
        return DiscoveryRuntimeResult(
            decision=DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="好的，帮你换一批新的。换之前能简单告诉我上一批哪里不太合适吗？这样我下轮会更准。",
                criteria_labels=list(run_input.criteria_labels),
                suggested_actions=[
                    DiscoveryActionSuggestion(
                        label="太远了（都是异地）",
                        semantic_payload={
                            "kind": "rejection_feedback",
                            "feedback_type": "location_distance",
                            "feedback_text": "太远了（都是异地）",
                        },
                        style="ghost",
                    ),
                    DiscoveryActionSuggestion(
                        label="职业不太匹配（程序员偏多）",
                        semantic_payload={
                            "kind": "rejection_feedback",
                            "feedback_type": "occupation_mismatch",
                            "feedback_text": "职业不太匹配（程序员偏多）",
                        },
                        style="secondary",
                    ),
                    DiscoveryActionSuggestion(
                        label="太忙太卷（工作压力大）",
                        semantic_payload={
                            "kind": "rejection_feedback",
                            "feedback_type": "work_life_balance",
                            "feedback_text": "太忙太卷（工作压力大）",
                        },
                        style="ghost",
                    ),
                    DiscoveryActionSuggestion(
                        label="兴趣爱好不一样",
                        semantic_payload={
                            "kind": "rejection_feedback",
                            "feedback_type": "interest_mismatch",
                            "feedback_text": "兴趣爱好不一样",
                        },
                        style="ghost",
                    ),
                    DiscoveryActionSuggestion(
                        label="跳过，直接换",
                        semantic_payload={
                            "kind": "rejection_feedback",
                            "feedback_type": "skip_feedback",
                            "feedback_text": "跳过，直接换",
                        },
                        style="ghost",
                    ),
                ],
            )
        )

    def _parse_rejection_feedback_from_text(
        self,
        session: StoredSession,
        text: str,
    ) -> dict[str, Any]:
        if not bool(session.state.get("awaiting_rejection_feedback")):
            return {
                "is_rejection_feedback": False,
                "feedback_type": "",
                "summary": "",
                "search_criteria_patch": {},
            }
        parsed = parse_rejection_feedback_text(
            text,
            runtime_context=self._build_runtime_context(
                session,
                recent_timeline=clone_view({"timeline": session.view.get("timeline") or []}).get("timeline") or [],
            ),
        )
        if not isinstance(parsed, dict):
            return {
                "is_rejection_feedback": False,
                "feedback_type": "",
                "summary": "",
                "search_criteria_patch": {},
            }
        return parsed

    def _update_rejection_feedback_waiting_state(
        self,
        session: StoredSession,
        *,
        user_message_text: str | None,
        runtime_result: DiscoveryRuntimeResult,
    ) -> None:
        semantic_kinds = {
            str((action.semantic_payload or {}).get("kind") or "").strip()
            for action in list(runtime_result.decision.suggested_actions or [])
        }
        if "rejection_feedback" in semantic_kinds:
            session.state["awaiting_rejection_feedback"] = True
            session.state["awaiting_rejection_feedback_since"] = datetime.now().isoformat()
            return

        text = str(user_message_text or "").strip()
        if text and any(pattern in text for pattern in _BATCH_REFRESH_PATTERNS):
            session.state["awaiting_rejection_feedback"] = True
            session.state["awaiting_rejection_feedback_since"] = datetime.now().isoformat()
            return

        if runtime_result.search_response is not None or str(runtime_result.decision.phase or "").strip() in {"results_shown", "no_result"}:
            session.state.pop("awaiting_rejection_feedback", None)
            session.state.pop("awaiting_rejection_feedback_since", None)

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

    def _build_personality_explanation_decision(
        self,
        session: StoredSession,
        *,
        user_message_text: str | None,
    ) -> DiscoveryDecision | None:
        if not _is_personality_explanation_request(user_message_text):
            return None
        cards = self._existing_result_cards(session)
        candidate = _pick_existing_candidate(cards, user_message_text)
        if not candidate:
            return None

        requester_profile = self._load_requester_profile(session) or {}
        self_traits = dict(requester_profile.get("personality_traits") or {})
        candidate_traits = dict(candidate.get("personality_match_context") or {})
        if not candidate_traits:
            return None

        candidate_name = _candidate_first_name(candidate)
        reasoning = dict(candidate.get("personality_reasoning") or {})
        reasoning_reasons = [
            str(item).strip()
            for item in list(reasoning.get("reasons") or [])
            if str(item or "").strip()
        ]
        if reasoning_reasons:
            return DiscoveryDecision(
                phase="results_shown",
                assistant_message=f"先说{candidate_name}。从测评角度看，" + "，".join(reasoning_reasons[:3]) + "。",
                criteria_labels=[
                    str(item.get("label") or "").strip()
                    for item in list(session.view.get("criteria_chips") or [])
                    if str(item.get("label") or "").strip()
                ],
                suggested_actions=[],
            )
        clauses: list[str] = []

        self_mbti = str((self_traits.get("mbti") or {}).get("type_code") or "").strip()
        candidate_mbti = str((candidate_traits.get("mbti") or {}).get("type_code") or "").strip()
        if self_mbti and candidate_mbti:
            if self_mbti[:3] and self_mbti[:3] == candidate_mbti[:3]:
                clauses.append(
                    f"MBTI 上你是 {self_mbti}，她是 {candidate_mbti}，前 3 个维度很接近，通常都偏务实、慢热、先看长期稳定。"
                )
            else:
                clauses.append(
                    f"MBTI 上你是 {self_mbti}，她是 {candidate_mbti}，虽然不是同一型，但都不是很跳脱的相处节奏，更偏稳定推进。"
                )
        elif candidate_mbti:
            clauses.append(f"她的 MBTI 是 {candidate_mbti}，这类类型通常更偏稳定、务实，不是只靠感觉往前冲。")

        self_attachment = dict(self_traits.get("attachment") or {})
        candidate_attachment = dict(candidate_traits.get("attachment") or {})
        self_attachment_type = str(self_attachment.get("type_code") or "").strip()
        candidate_attachment_type = str(candidate_attachment.get("type_code") or "").strip()
        if self_attachment_type and candidate_attachment_type:
            if self_attachment_type == "secure" and candidate_attachment_type == "secure":
                clauses.append("依恋上你们都偏安全型，焦虑和回避都不高，相处时更容易稳定沟通，不太会一方追一方躲。")
            else:
                clauses.append("依恋上你们都不是特别高冲突的组合，靠近和拉开距离的方式比较容易协商。")
        elif candidate_attachment_type == "secure":
            clauses.append("她在依恋上偏安全型，通常不容易忽冷忽热，关系推进会更稳。")

        overlap = _shared_values(self_traits, candidate_traits)
        if overlap:
            shared = "、".join(overlap[:2])
            clauses.append(f"价值观上你们都把“{shared}”放得比较前，这类人通常更容易在长期投入和生活方向上同频。")
        else:
            self_value_type = str((self_traits.get("values") or {}).get("value_type") or "").strip()
            candidate_value_type = str((candidate_traits.get("values") or {}).get("value_type") or "").strip()
            if self_value_type and candidate_value_type:
                clauses.append(
                    f"价值观上你偏{self_value_type}，她偏{candidate_value_type}，虽然不完全一样，但都不是只看短期新鲜感的类型。"
                )
            elif candidate_value_type:
                clauses.append(f"价值观上她偏{candidate_value_type}，而且把长期稳定相关内容放得比较靠前，所以我会先把她往前推。")

        if not clauses:
            return None

        return DiscoveryDecision(
            phase="results_shown",
            assistant_message=f"先说{candidate_name}。{''.join(clauses[:3])}",
            criteria_labels=[
                str(item.get("label") or "").strip()
                for item in list(session.view.get("criteria_chips") or [])
                if str(item.get("label") or "").strip()
            ],
            suggested_actions=[],
        )

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

    def _coerce_search_failure_decision(
        self,
        decision: DiscoveryDecision,
        search_response: dict[str, Any] | None,
    ) -> DiscoveryDecision:
        if decision.phase == "searching" and search_response is None:
            return DiscoveryDecision(
                phase="collecting_preferences",
                assistant_message="我这轮还没真正发起筛选，你再点一次“先看看有没有人”，或者直接说“开始搜索”，我马上给你跑。",
                criteria_labels=list(decision.criteria_labels),
                suggested_actions=list(decision.suggested_actions),
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
        limit: int,
    ) -> dict[str, Any]:
        return _search_partner_candidates_impl(
            session,
            criteria=criteria,
            limit=limit,
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

    def _propose_requester_profile_update(
        self,
        session: StoredSession,
        *,
        patch: dict[str, Any],
        evidence_text: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return _propose_requester_profile_update_impl(
            self.storage,
            session,
            patch=patch,
            evidence_text=evidence_text,
            load_profile=load_self_profile,
            source=self._profile_source(),
            now=now,
        )

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

    # ========== 新增：反馈收集相关方法 ==========

    def submit_rejection_feedback(
        self,
        *,
        session_id: str,
        feedback_text: str,
        feedback_type: str | None = None,
        criteria_patch: dict[str, Any] | None = None,
        feedback_detail: str | None = None,
        rejected_candidate_ids: list[str] | None = None,
        is_secondary: bool = False,
        primary_feedback_id: int | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        提交拒绝反馈并触发调整。

        Args:
            session_id: Discovery session ID
            feedback_text: 用户选择的反馈文案
            feedback_type: 反馈类型（可推断）
            feedback_detail: 二级追问细节
            rejected_candidate_ids: 被拒绝的候选人ID列表
            is_secondary: 是否为二级追问结果
            primary_feedback_id: 一级反馈ID（二级追问时）
            now: 当前时间

        Returns:
            包含feedback_id和调整状态的字典
        """
        from .feedback_service import infer_feedback_type, FEEDBACK_TO_CRITERIA_ADJUSTMENT

        current = now or datetime.now()
        session = self._require_session(session_id)

        # 1. 推断反馈类型（如果没有显式提供）
        if feedback_type is None:
            feedback_type = infer_feedback_type(feedback_text)

        # 2. 获取上一批候选人ID（如果没有提供）
        if rejected_candidate_ids is None:
            last_search_run = self._get_last_search_run(session_id)
            if last_search_run is not None:
                rejected_candidate_ids = [
                    str(item.get("id"))
                    for item in (last_search_run.response.get("results") or [])
                    if item.get("id")
                ]

        # 3. 记录反馈
        turn_id = self._current_turn_id_for_feedback(session_id)
        feedback_id = self.storage.insert_rejection_feedback(
            session_id=session_id,
            turn_id=turn_id,
            requester_id=session.requester_id,
            feedback_type=feedback_type,
            feedback_text=feedback_text,
            feedback_detail=feedback_detail,
            rejected_batch_id=str(self._get_last_search_run_id(session_id) or ""),
            rejected_candidate_ids=rejected_candidate_ids,
            source_type="explicit",
            追问_triggered=True,
            追问_skipped=False,
            is_secondary_feedback=is_secondary,
            primary_feedback_id=primary_feedback_id,
            created_at=current,
        )

        # 4. 应用criteria调整
        adjustment = self._apply_feedback_adjustment(
            session_id=session_id,
            feedback_type=feedback_type,
            feedback_id=feedback_id,
            turn_id=turn_id,
            criteria_patch=criteria_patch,
            now=current,
        )

        # 5. 同步到persona（如果策略有persona_write）
        strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get(feedback_type)
        persona_updated = False
        if strategy and strategy.get("persona_write"):
            persona_updated = self._sync_persona_from_feedback(
                requester_id=session.requester_id,
                feedback_type=feedback_type,
                feedback_text=feedback_text,
                now=current,
            )

        return {
            "success": True,
            "feedback_id": feedback_id,
            "feedback_type": feedback_type,
            "adjustment_id": adjustment.get("adjustment_id"),
            "persona_updated": persona_updated,
            "criteria_adjusted": adjustment.get("applied", False),
        }

    def skip_rejection_feedback(
        self,
        *,
        session_id: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """
        记录用户跳过反馈。
        """
        current = now or datetime.now()
        session = self._require_session(session_id)

        turn_id = self._current_turn_id_for_feedback(session_id)
        feedback_id = self.storage.insert_rejection_feedback(
            session_id=session_id,
            turn_id=turn_id,
            requester_id=session.requester_id,
            feedback_type="skipped",
            feedback_text="跳过，直接换",
            source_type="explicit",
            追问_triggered=True,
            追问_skipped=True,
            is_secondary_feedback=False,
            created_at=current,
        )

        return {
            "success": True,
            "feedback_id": feedback_id,
        }

    def get_feedback_options(
        self,
        *,
        session_id: str,
        include_secondary: bool = False,
        primary_option: str | None = None,
    ) -> dict[str, Any]:
        """
        获取反馈选项列表。
        """
        from .feedback_service import generate_feedback_options

        session = self._require_session(session_id)

        # 获取上一批候选人
        last_search_run = self._get_last_search_run(session_id)
        last_batch_candidates = []
        if last_search_run is not None:
            last_batch_candidates = last_search_run.response.get("results") or []

        # 获取用户profile
        user_profile = session.state.get("self_profile") or {}

        # 生成选项
        result = generate_feedback_options(
            last_batch_candidates,
            user_profile,
            include_secondary=include_secondary,
            primary_option=primary_option,
        )

        return {
            "success": True,
            "options": result.get("options", []),
            "prompt_message": result.get("追问文案", ""),
        }

    def _apply_feedback_adjustment(
        self,
        *,
        session_id: str,
        feedback_type: str,
        feedback_id: int,
        turn_id: int,
        criteria_patch: dict[str, Any] | None,
        now: datetime,
    ) -> dict[str, Any]:
        """应用反馈对应的criteria调整。"""
        from .feedback_service import FEEDBACK_TO_CRITERIA_ADJUSTMENT

        session = self._require_session(session_id)
        strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get(feedback_type)
        inferred_patch = self._default_feedback_criteria_patch(session, feedback_type=feedback_type)
        normalized_patch = {
            str(key).strip(): value
            for key, value in dict(criteria_patch or {}).items()
            if str(key or "").strip() and value not in (None, "", [], {})
        }
        patch_to_apply = {**inferred_patch, **normalized_patch}

        if not strategy and not patch_to_apply:
            return {"applied": False, "reason": "no strategy found"}

        before_value = deepcopy(dict(session.state.get("working_criteria") or {}))
        merged = merge_working_criteria(session.state, patch_to_apply)
        session.state["working_criteria"] = {
            key: merged[key]
            for key in merged
            if is_search_criteria_key(key)
        }
        after_value = deepcopy(dict(session.state.get("working_criteria") or {}))
        self.storage.save_session(session)

        adjustment_id = self.storage.insert_criteria_adjustment(
            session_id=session_id,
            turn_id=turn_id,
            adjustment_type=(strategy or {}).get("adjustment_type", "shift"),
            affected_field=(strategy or {}).get("affected_field", "multiple"),
            before_value=before_value,
            after_value=after_value,
            triggered_by_feedback_id=feedback_id,
            adjustment_reason=f"根据用户反馈'{feedback_type}'调整",
            created_at=now,
        )

        return {
            "applied": True,
            "adjustment_id": adjustment_id,
            "affected_field": (strategy or {}).get("affected_field", "multiple"),
        }

    def _default_feedback_criteria_patch(
        self,
        session: StoredSession,
        *,
        feedback_type: str,
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        requester_profile = self._load_requester_profile(session) or {}
        self_city = str(requester_profile.get("city") or requester_profile.get("self_city") or "").strip()
        self_age_raw = requester_profile.get("age") or requester_profile.get("self_age")
        try:
            self_age = int(self_age_raw) if self_age_raw not in (None, "") else None
        except (TypeError, ValueError):
            self_age = None

        if feedback_type == "location_distance" and self_city:
            patch["cities"] = [self_city]
            patch["prefer"] = ["同城优先"]
        elif feedback_type in {"age_gap", "criteria_age"} and self_age is not None:
            patch["age_min"] = max(18, self_age - 3)
            patch["age_max"] = self_age + 3
            patch["prefer"] = ["年龄接近"]
        elif feedback_type == "work_life_balance":
            patch["prefer"] = ["工作稳定", "生活规律"]
            patch["must_not_have"] = ["高强度工作"]
        elif feedback_type == "occupation_mismatch":
            patch["prefer"] = ["职业匹配"]
        elif feedback_type == "interest_mismatch":
            patch["prefer"] = ["兴趣相投"]
        return patch

    def _sync_persona_from_feedback(
        self,
        *,
        requester_id: int,
        feedback_type: str,
        feedback_text: str,
        now: datetime,
    ) -> bool:
        """同步反馈到persona。"""
        from .feedback_service import FEEDBACK_TO_CRITERIA_ADJUSTMENT

        strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get(feedback_type)
        if not strategy or not strategy.get("persona_write"):
            return False

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

    def _get_last_search_run_id(self, session_id: str) -> int | None:
        """获取session的最后一次搜索run ID。"""
        session = self.storage.get_session(session_id)
        if session is None:
            return None
        search_run_id = int(session.state.get("last_search_run_id") or 0)
        return search_run_id if search_run_id > 0 else None

    def _current_turn_id_for_feedback(self, session_id: str) -> int:
        getter = getattr(self.storage, "get_latest_turn_id", None)
        if callable(getter):
            try:
                return int(getter(session_id) or 0)
            except Exception:  # noqa: BLE001
                return 0
        getter = getattr(self.storage, "get_current_turn_id", None)
        if callable(getter):
            try:
                return int(getter(session_id) or 0)
            except Exception:  # noqa: BLE001
                return 0
        return 0

    def _bind_submit_rejection_feedback(self, session: StoredSession) -> Callable[..., dict[str, Any]]:
        """绑定提交反馈方法。"""
        def submit_feedback_wrapper(
            feedback_text: str,
            feedback_type: str | None = None,
            criteria_patch: dict[str, Any] | None = None,
            feedback_detail: str | None = None,
            is_secondary: bool = False,
        ) -> dict[str, Any]:
            return self.submit_rejection_feedback(
                session_id=session.session_id,
                feedback_text=feedback_text,
                feedback_type=feedback_type,
                criteria_patch=criteria_patch,
                feedback_detail=feedback_detail,
                is_secondary=is_secondary,
            )
        return submit_feedback_wrapper

    def _bind_get_feedback_options(self, session: StoredSession) -> Callable[..., dict[str, Any]]:
        """绑定获取反馈选项方法。"""
        def get_options_wrapper(
            include_secondary: bool = False,
            primary_option: str | None = None,
        ) -> dict[str, Any]:
            return self.get_feedback_options(
                session_id=session.session_id,
                include_secondary=include_secondary,
                primary_option=primary_option,
            )
        return get_options_wrapper

    def _agent_session_for(self, session_id: str) -> Any | None:
        if self.agent_session_store is None:
            return None
        return self.agent_session_store.get_session(session_id)

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
    return DiscoveryService(
        storage=storage,
        runtime=create_default_discovery_agent_runtime(),
        agent_session_store=create_default_discovery_agent_session_store(discovery_dsn=resolved_dsn),
    )
