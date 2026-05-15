"""Service layer for the discovery system skeleton."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from typing import Any

from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path
from partner_search import load_self_profile, search_profiles
from profile_detail_reader import load_profile_detail

from .agent_runtime import (
    DiscoveryActionSuggestion,
    DiscoveryAgentRuntime,
    DiscoveryDecision,
    DiscoveryRunInput,
    DiscoveryRuntimeResult,
    create_default_discovery_agent_runtime,
)
from .agent_session_store import create_default_discovery_agent_session_store
from .storage import InMemoryDiscoveryStorage, MySQLDiscoveryStorage, StoredSession
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
        runtime_result = self.runtime.initial_decision(self._build_runtime_input(session, now=current))
        search_run_id = self._apply_runtime_result(session, runtime_result, now=current)
        self.storage.save_session(session)
        self.storage.create_turn(
            session_id=session.session_id,
            request_kind="session_opened",
            user_message_text=None,
            consumed_action_id=None,
            agent_decision=self._decision_payload(runtime_result.decision),
            view_snapshot=clone_view(session.view),
            created_at=current,
            search_run_id=search_run_id,
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
        if user_message_text is not None and user_message_text.strip():
            text = user_message_text.strip()
            normalized_user_message = text
            new_items.append(user_message(self.storage.next_item_id("msg-u"), text))
            runtime_result = self.runtime.run_turn(
                self._build_runtime_input(session, now=current),
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
                self._build_runtime_input(session, now=current),
                action_context={
                    "label": action.label,
                    "semantic_payload": deepcopy(action.semantic_payload),
                }
            )

        session.view["timeline"] = list(session.view.get("timeline") or []) + new_items
        search_run_id = self._apply_runtime_result(session, runtime_result, now=current)
        self.storage.save_session(session)
        self.storage.create_turn(
            session_id=session.session_id,
            request_kind=request_kind,
            user_message_text=normalized_user_message,
            consumed_action_id=consumed_action_id,
            agent_decision=self._decision_payload(runtime_result.decision),
            view_snapshot=clone_view(session.view),
            created_at=current,
            search_run_id=search_run_id,
        )
        return self._session_payload(session)

    def get_session_view(self, session_id: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        return self._session_payload(session)

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
            get_discovery_session_state=lambda: self._build_session_state_snapshot(session.session_id),
            get_requester_profile=lambda: self._load_requester_profile(session),
            search_partner_candidates=lambda criteria, limit: self._search_partner_candidates(
                session,
                criteria=criteria,
                limit=limit,
            ),
            create_saved_search_subscription_from_last_search=lambda: self._create_saved_search_subscription_from_last_search(
                session,
                now=now,
            ),
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

    def _build_session_state_snapshot(self, session_id: str) -> dict[str, Any]:
        session = self._require_session(session_id)
        return {
            "session_id": session.session_id,
            "requester_id": session.requester_id,
            "profile_id": session.profile_id,
            "status": session.status,
            "phase": session.phase,
            "state": deepcopy(session.state),
            "criteria_labels": [
                str(item.get("label") or "").strip()
                for item in list(session.view.get("criteria_chips") or [])
                if str(item.get("label") or "").strip()
            ],
            "recent_timeline": list(session.view.get("timeline") or [])[-6:],
        }

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

    def _build_profile_detail_notes(
        self,
        session: StoredSession | None,
        profile_id: int,
    ) -> list[str]:
        if session is None:
            return []
        for item in reversed(list(session.view.get("timeline") or [])):
            if item.get("item_type") != "result_group":
                continue
            for card in list(item.get("cards") or []):
                if int(card.get("profile_id") or 0) != profile_id:
                    continue
                reason_summary = str(card.get("reason_summary") or "").strip()
                if reason_summary:
                    return [f"红娘当时把这位放到你面前，主要因为：{reason_summary}"]
                return []
        return []

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

def create_default_discovery_service(*, discovery_dsn: str | None = None) -> DiscoveryService:
    resolved_dsn = str(discovery_dsn or os.environ.get("PARTNER_DISCOVERY_DB") or "").strip()
    storage = MySQLDiscoveryStorage(resolved_dsn) if resolved_dsn else InMemoryDiscoveryStorage()
    return DiscoveryService(
        storage=storage,
        runtime=create_default_discovery_agent_runtime(),
        agent_session_store=create_default_discovery_agent_session_store(discovery_dsn=resolved_dsn),
    )
