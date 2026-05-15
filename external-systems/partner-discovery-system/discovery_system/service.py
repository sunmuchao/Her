"""Service layer for the discovery system skeleton."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
import os
from pathlib import Path
from typing import Any

from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path
from her_runtime_context import get_trace_id
from observability import audit_event, funnel_stage, metric_gauge
from partner_search import load_self_profile, search_profiles
from profile_detail_reader import load_profile_detail

from .agent_runtime import (
    DiscoveryActionSuggestion,
    DiscoveryAgentRuntime,
    DiscoveryDecision,
    DiscoveryRunInput,
    DiscoveryRuntimeResult,
    DiscoveryToolCall,
    create_default_discovery_agent_runtime,
)
from .agent_session_store import create_default_discovery_agent_session_store
from .storage import InMemoryDiscoveryStorage, MySQLDiscoveryStorage, StoredSession
from .service_context import (
    DiscoveryServiceContextRuntime,
    build_last_search_summary as _build_last_search_summary,
    build_page_summary as _build_page_summary,
    build_profile_detail_notes as _build_profile_detail_notes,
    build_runtime_context as _build_runtime_context,
    build_visible_action_summaries as _build_visible_action_summaries,
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
        run_input = self._build_runtime_input(session, now=current)
        runtime_result = self.runtime.initial_decision(run_input)
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
            tool_calls=run_input.tool_call_buffer,
            search_run_id=search_run_id,
            created_at=current,
            trace_id=trace_id,
        )
        self._increment_metric("sessions.created")
        self._increment_metric("turns.created")
        funnel_stage(
            system="discovery",
            stage="session_open",
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
            new_items.append(user_message(self.storage.next_item_id("msg-u"), text))
            runtime_result = self.runtime.run_turn(
                run_input,
                user_message=text,
            )
        else:
            action = self.storage.get_action(session_id, str(action_id or "").strip())
            if action is None:
                raise DiscoveryActionNotFoundError("action_id not found for this discovery session")
            if action.consumed_at is not None:
                raise DiscoveryActionExpiredError("action_id has already been consumed")
            if action.expires_at is not None and action.expires_at <= current:
                raise DiscoveryActionExpiredError("action_id has expired")
            self.storage.mark_action_consumed(action.action_id, current)
            request_kind = "action_click"
            consumed_action_id = action.action_id
            runtime_result = self.runtime.run_turn(
                run_input,
                action_context={
                    "label": action.label,
                    "semantic_payload": deepcopy(action.semantic_payload),
                }
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
            create_saved_search_subscription_from_last_search=_create_saved_search_subscription_from_last_search,
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
        decision = runtime_result.decision
        session.view["timeline"] = list(session.view.get("timeline") or []) + [
            assistant_message(
                self.storage.next_item_id("msg-a"),
                decision.assistant_message,
            )
        ]
        if decision.criteria_labels:
            session.view["criteria_chips"] = [
                criteria_chip(f"chip-{index + 1}", label)
                for index, label in enumerate(decision.criteria_labels)
            ]
        search_run_id: int | None = None
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

    def _build_result_cards(
        self,
        search_response: dict[str, Any],
        *,
        decision: DiscoveryDecision,
    ) -> list[dict[str, Any]]:
        selected_by_id = {
            int(selection.profile_id): selection
            for selection in decision.selected_candidates
            if int(selection.profile_id) > 0
        }
        cards: list[dict[str, Any]] = []
        for candidate in list(search_response.get("results") or []):
            profile_id = int(candidate.get("id") or 0)
            selection = selected_by_id.get(profile_id)
            if selection is None:
                continue
            cards.append(
                build_candidate_card(
                    candidate,
                    reason_summary=selection.reason_summary,
                )
            )
        return cards

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
        source = self._profile_source()
        if not source or session.profile_id <= 0:
            return None
        try:
            profile = load_self_profile(
                source=source,
                self_id=session.profile_id,
            )
        except Exception:  # noqa: BLE001
            return None
        if not isinstance(profile, dict):
            return None
        return profile

    def _search_partner_candidates(
        self,
        session: StoredSession,
        *,
        criteria: dict[str, Any],
        limit: int,
    ) -> dict[str, Any]:
        source = self._profile_source()
        if not source:
            return {
                "has_match": False,
                "result_count": 0,
                "results": [],
                "fallback_results": [],
                "diagnostics": {
                    "error": "search_source_not_configured",
                },
            }
        self_profile = self._load_requester_profile(session)
        normalized_limit = max(1, min(int(limit or 5), 10))
        try:
            response = search_profiles(
                source=source,
                criteria=dict(criteria or {}),
                self_profile=self_profile,
                self_id=session.profile_id,
                limit=normalized_limit,
                photo_preview_count=3,
                moderation_dsn=os.environ.get("PARTNER_CHAT_DB"),
            )
            response["request_meta"] = {
                "source": source,
                "criteria": dict(criteria or {}),
                "self_profile": deepcopy(self_profile),
                "self_id": session.profile_id,
                "table_name": None,
                "photos_table_name": None,
                "limit_count": normalized_limit,
            }
            return response
        except Exception as exc:  # noqa: BLE001
            return {
                "has_match": False,
                "result_count": 0,
                "results": [],
                "fallback_results": [],
                "diagnostics": {
                    "error": str(exc)[:200],
                },
                "request_meta": {
                    "source": source,
                    "criteria": dict(criteria or {}),
                    "self_profile": deepcopy(self_profile),
                    "self_id": session.profile_id,
                    "table_name": None,
                    "photos_table_name": None,
                    "limit_count": normalized_limit,
                },
            }

    def _profile_source(self) -> str:
        for name in (
            "HER_DISCOVERY_PROFILE_SOURCE",
            "PARTNER_SEARCH_MYSQL_SOURCE",
            "PERSONA_MEMORY_MYSQL_SOURCE",
        ):
            value = (os.environ.get(name) or "").strip()
            if value:
                return value
        return ""

    def _persona_memory_source(self) -> str:
        for name in (
            "PERSONA_MEMORY_MYSQL_SOURCE",
            "HER_DISCOVERY_PROFILE_SOURCE",
            "PARTNER_SEARCH_MYSQL_SOURCE",
        ):
            value = (os.environ.get(name) or "").strip()
            if value:
                return value
        return ""

    def _sync_requester_persona_memory(
        self,
        session: StoredSession,
        *,
        patch: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        normalized_patch = dict(patch or {})
        if not normalized_patch:
            return {
                "synced": False,
                "error_code": "empty_persona_patch",
                "message": "没有可写入画像的字段。",
            }
        source = self._persona_memory_source()
        if not source:
            return {
                "synced": False,
                "error_code": "persona_memory_source_not_configured",
                "message": "当前没有配置 persona-memory-sync 数据源。",
            }
        current = now or datetime.now()
        try:
            upsert_persona_memory = self._load_persona_memory_bindings()
            upsert_result = upsert_persona_memory(
                {
                    "source": source,
                    "user_key": str(session.requester_id),
                    "source_type": "explicit",
                    "patch": normalized_patch,
                    "sync_profile": True,
                    "conversation_ref": f"discovery/{session.session_id}",
                    "basis": "discovery_agent",
                },
                include_normalized_patch=True,
            )
        except Exception as exc:  # noqa: BLE001
            return {
                "synced": False,
                "error_code": "persona_memory_sync_failed",
                "message": str(exc)[:200],
            }
        session.state["last_persona_sync_at"] = current.isoformat()
        session.state["last_persona_sync_fields"] = sorted(
            str(key).strip()
            for key in normalized_patch.keys()
            if str(key or "").strip()
        )
        return {
            "synced": True,
            "user_key": str(session.requester_id),
            "patch_keys": list(session.state["last_persona_sync_fields"]),
            "upsert": upsert_result,
        }

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
        request_meta = dict(search_response.get("request_meta") or {})
        source = str(request_meta.get("source") or "").strip()
        if not source:
            return None
        search_run_id = self.storage.create_search_run(
            session_id=session.session_id,
            requester_id=session.requester_id,
            profile_id=session.profile_id,
            source=source,
            criteria=dict(request_meta.get("criteria") or {}),
            self_profile=request_meta.get("self_profile"),
            limit_count=int(request_meta.get("limit_count") or 5),
            response=search_response,
            created_at=now,
        )
        session.state["last_search_run_id"] = search_run_id
        session.state["last_search_result_count"] = int(search_response.get("result_count") or 0)
        session.state["last_search_has_match"] = bool(search_response.get("has_match"))
        self._increment_metric("search_runs.created")
        metric_gauge(
            "discovery.search_runs.result_count",
            int(search_response.get("result_count") or 0),
            session_id=session.session_id,
            search_run_id=search_run_id,
        )
        return search_run_id

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
        if search_run.has_match or int(search_run.result_count or 0) > 0:
            return {
                "created_subscription": False,
                "error_code": "search_run_not_empty",
                "message": "上一轮不是空结果，当前不需要创建持续留意。",
            }

        request_meta = dict((search_run.response or {}).get("request_meta") or {})
        search_request = {
            "source": request_meta.get("source") or search_run.source,
            "criteria": dict(request_meta.get("criteria") or search_run.criteria or {}),
            "self_profile": deepcopy(request_meta.get("self_profile") or search_run.self_profile),
            "self_id": request_meta.get("self_id") or session.profile_id,
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
        connect_recommendation_db, _, initialize_recommendation_database = self._load_recommendation_bindings()
        dsn = str(os.environ.get("PARTNER_RECOMMENDATION_DB") or "mysql://root@127.0.0.1:3307/her_recommendation").strip()
        conn = connect_recommendation_db(dsn)
        initialize_recommendation_database(
            conn,
            mode=(os.environ.get("HER_SCHEMA_INIT_MODE") or "").strip() or None,
        )
        return conn

    def _load_recommendation_bindings(self):
        ensure_partner_system_roots_on_sys_path(Path(__file__).resolve().parents[3])
        from recommendation_system import (  # type: ignore[import-untyped]
            connect_db as connect_recommendation_db,
            handle_opt_in_decision,
            initialize_database as initialize_recommendation_database,
        )

        return (
            connect_recommendation_db,
            handle_opt_in_decision,
            initialize_recommendation_database,
        )

    def _load_persona_memory_bindings(self):
        from persona_memory_sync import upsert_persona_memory

        return upsert_persona_memory

    def _decision_payload(self, decision: DiscoveryDecision) -> dict[str, Any]:
        return {
            "phase": decision.phase,
            "assistant_message": decision.assistant_message,
            "criteria_labels": list(decision.criteria_labels),
            "suggested_actions": [
                {
                    "label": action.label,
                    "style": action.style,
                    "semantic_payload": deepcopy(action.semantic_payload),
                }
                for action in list(decision.suggested_actions)
            ],
            "result_group_title": decision.result_group_title,
            "selected_candidates": [
                {
                    "profile_id": candidate.profile_id,
                    "reason_summary": candidate.reason_summary,
                }
                for candidate in list(decision.selected_candidates)
            ],
        }

    def _require_session(self, session_id: str) -> StoredSession:
        session = self.storage.get_session(session_id)
        if session is None:
            raise DiscoverySessionNotFoundError("discovery session not found")
        return session

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
