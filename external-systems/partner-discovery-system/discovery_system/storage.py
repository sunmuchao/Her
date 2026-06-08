"""Storage for the discovery system.

The discovery service can run in two modes:

- in-memory: fast local tests and stub/demo runs
- MySQL: persistent discovery session / turn / action / search-run storage
"""

from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from her_external_systems import (  # noqa: E402
    MySQLCompatConnection,
    build_external_storage_helpers,
    json_dumps,
    json_loads,
    row_to_dict,
    schema_table_names,
)


DEFAULT_DISCOVERY_MYSQL_DSN = os.environ.get(
    "PARTNER_DISCOVERY_DB",
    "mysql://root@127.0.0.1:3307/her_discovery",
)
DEFAULT_DISCOVERY_TEST_MYSQL_DSN = os.environ.get(
    "PARTNER_DISCOVERY_TEST_DB",
    "mysql://root@127.0.0.1:3307/her_discovery_test",
)


@dataclass
class StoredAction:
    action_id: str
    session_id: str
    label: str
    style: str
    semantic_payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime | None
    consumed_at: datetime | None = None


@dataclass
class StoredSession:
    session_id: str
    requester_id: int
    profile_id: int
    status: str
    phase: str
    created_at: datetime
    updated_at: datetime
    view: dict[str, Any]
    visible_action_ids: list[str] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class StoredSearchRun:
    search_run_id: int
    session_id: str
    requester_id: int
    profile_id: int
    source: str
    criteria: dict[str, Any]
    self_profile: dict[str, Any] | None
    limit_count: int
    result_count: int
    has_match: bool
    response: dict[str, Any]
    created_at: datetime


@dataclass
class StoredToolCall:
    tool_call_id: int
    session_id: str
    turn_id: int
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    status: str
    search_run_id: int | None
    trace_id: str | None
    created_at: datetime


@dataclass
class StoredViewSnapshot:
    snapshot_id: int
    session_id: str
    turn_id: int | None
    phase: str
    view: dict[str, Any]
    trace_id: str | None
    created_at: datetime
connect_db, initialize_database, reset_all_tables = build_external_storage_helpers(
    subsystem_name="Discovery",
    target="discovery",
    table_names=schema_table_names("discovery_tables"),
    default_dsn=DEFAULT_DISCOVERY_MYSQL_DSN,
)


class InMemoryDiscoveryStorage:
    def __init__(self) -> None:
        self._session_seq = 0
        self._action_seq = 0
        self._item_seq = 0
        self._turn_seq = 0
        self._search_run_seq = 0
        self._tool_call_seq = 0
        self._view_snapshot_seq = 0
        self._feedback_seq = 0
        self._criteria_adjustment_seq = 0
        self._sessions: dict[str, StoredSession] = {}
        self._actions: dict[str, StoredAction] = {}
        self._search_runs: dict[int, StoredSearchRun] = {}
        self._tool_calls: list[StoredToolCall] = []
        self._view_snapshots: list[StoredViewSnapshot] = []
        self._profile_update_requests: dict[str, dict[str, Any]] = {}
        self._rejection_feedbacks: list[dict[str, Any]] = []
        self._criteria_adjustments: list[dict[str, Any]] = []

    def next_session_id(self) -> str:
        self._session_seq += 1
        return f"discovery-session-{self._session_seq:03d}"

    def next_action_id(self) -> str:
        self._action_seq += 1
        return f"act-{self._action_seq:03d}"

    def next_item_id(self, prefix: str) -> str:
        self._item_seq += 1
        return f"{prefix}-{self._item_seq:03d}"

    def save_session(self, session: StoredSession) -> None:
        self._sessions[session.session_id] = deepcopy(session)

    def get_session(self, session_id: str) -> StoredSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        return deepcopy(session)

    def save_action(self, action: StoredAction) -> None:
        self._actions[action.action_id] = deepcopy(action)

    def get_action(self, session_id: str, action_id: str) -> StoredAction | None:
        action = self._actions.get(action_id)
        if action is None or action.session_id != session_id:
            return None
        return deepcopy(action)

    def get_actions(self, session_id: str, action_ids: list[str]) -> dict[str, StoredAction]:
        out: dict[str, StoredAction] = {}
        for raw_action_id in action_ids:
            action_id = str(raw_action_id or "").strip()
            if not action_id:
                continue
            action = self.get_action(session_id, action_id)
            if action is not None:
                out[action_id] = action
        return out

    def mark_action_consumed(self, action_id: str, now: datetime) -> None:
        action = self._actions[action_id]
        action.consumed_at = now
        self._actions[action_id] = action

    def replace_visible_actions(self, session_id: str, action_ids: list[str]) -> None:
        session = self._sessions[session_id]
        session.visible_action_ids = list(action_ids)
        session.state["visible_action_ids"] = list(action_ids)
        self._sessions[session_id] = session

    def create_action(
        self,
        *,
        session_id: str,
        label: str,
        style: str,
        semantic_payload: dict[str, Any] | None,
        now: datetime,
        ttl: timedelta = timedelta(days=7),  # 延长到7天，避免用户点击时action已过期
    ) -> StoredAction:
        action = StoredAction(
            action_id=self.next_action_id(),
            session_id=session_id,
            label=label,
            style=style,
            semantic_payload=deepcopy(semantic_payload or {}),
            created_at=now,
            expires_at=now + ttl,
        )
        self.save_action(action)
        return deepcopy(action)

    def create_turn(
        self,
        *,
        session_id: str,
        request_kind: str,
        user_message_text: str | None,
        consumed_action_id: str | None,
        agent_decision: dict[str, Any],
        view_snapshot: dict[str, Any],
        created_at: datetime,
        search_run_id: int | None = None,
        trace_id: str | None = None,
    ) -> int:
        del session_id, request_kind, user_message_text, consumed_action_id, agent_decision, view_snapshot, created_at, search_run_id, trace_id
        self._turn_seq += 1
        return self._turn_seq

    def get_latest_turn_id(self, session_id: str) -> int | None:
        del session_id
        return self._turn_seq if self._turn_seq > 0 else None

    def create_search_run(
        self,
        *,
        session_id: str,
        requester_id: int,
        profile_id: int,
        source: str,
        criteria: dict[str, Any],
        self_profile: dict[str, Any] | None,
        limit_count: int,
        response: dict[str, Any],
        created_at: datetime,
    ) -> int:
        self._search_run_seq += 1
        self._search_runs[self._search_run_seq] = StoredSearchRun(
            search_run_id=self._search_run_seq,
            session_id=session_id,
            requester_id=int(requester_id),
            profile_id=int(profile_id),
            source=str(source),
            criteria=deepcopy(criteria),
            self_profile=deepcopy(self_profile),
            limit_count=int(limit_count),
            result_count=int(response.get("result_count") or 0),
            has_match=bool(response.get("has_match")),
            response=deepcopy(response),
            created_at=created_at,
        )
        return self._search_run_seq

    def get_search_run(self, search_run_id: int) -> StoredSearchRun | None:
        search_run = self._search_runs.get(int(search_run_id))
        if search_run is None:
            return None
        return deepcopy(search_run)

    def create_tool_call(
        self,
        *,
        session_id: str,
        turn_id: int,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        status: str,
        search_run_id: int | None,
        created_at: datetime,
        trace_id: str | None = None,
    ) -> int:
        self._tool_call_seq += 1
        self._tool_calls.append(
            StoredToolCall(
                tool_call_id=self._tool_call_seq,
                session_id=session_id,
                turn_id=int(turn_id),
                tool_name=str(tool_name),
                arguments=deepcopy(arguments),
                result=deepcopy(result),
                status=str(status),
                search_run_id=int(search_run_id) if search_run_id is not None else None,
                trace_id=str(trace_id).strip() or None if trace_id is not None else None,
                created_at=created_at,
            )
        )
        return self._tool_call_seq

    def list_tool_calls(self, session_id: str, *, turn_id: int | None = None) -> list[StoredToolCall]:
        return [
            deepcopy(tool_call)
            for tool_call in self._tool_calls
            if tool_call.session_id == session_id and (turn_id is None or tool_call.turn_id == int(turn_id))
        ]

    def create_view_snapshot(
        self,
        *,
        session_id: str,
        turn_id: int | None,
        phase: str,
        view_snapshot: dict[str, Any],
        created_at: datetime,
        trace_id: str | None = None,
    ) -> int:
        self._view_snapshot_seq += 1
        self._view_snapshots.append(
            StoredViewSnapshot(
                snapshot_id=self._view_snapshot_seq,
                session_id=session_id,
                turn_id=int(turn_id) if turn_id is not None else None,
                phase=str(phase),
                view=deepcopy(view_snapshot),
                trace_id=str(trace_id).strip() or None if trace_id is not None else None,
                created_at=created_at,
            )
        )
        return self._view_snapshot_seq

    def insert_rejection_feedback(
        self,
        *,
        session_id: str,
        turn_id: int,
        requester_id: int,
        feedback_type: str,
        feedback_text: str,
        feedback_detail: str | None = None,
        rejected_batch_id: str | None = None,
        rejected_candidate_ids: list[str] | None = None,
        source_type: str = "explicit",
        追问_triggered: bool = True,
        追问_skipped: bool = False,
        is_secondary_feedback: bool = False,
        primary_feedback_id: int | None = None,
        created_at: datetime,
    ) -> int:
        self._feedback_seq += 1
        self._rejection_feedbacks.append(
            {
                "feedback_id": self._feedback_seq,
                "session_id": session_id,
                "turn_id": int(turn_id),
                "requester_id": int(requester_id),
                "feedback_type": feedback_type,
                "feedback_text": feedback_text,
                "feedback_detail": feedback_detail,
                "rejected_batch_id": rejected_batch_id,
                "rejected_candidate_ids": deepcopy(rejected_candidate_ids or []),
                "source_type": source_type,
                "追问_triggered": bool(追问_triggered),
                "追问_skipped": bool(追问_skipped),
                "is_secondary_feedback": bool(is_secondary_feedback),
                "primary_feedback_id": primary_feedback_id,
                "created_at": created_at,
            }
        )
        return self._feedback_seq

    def insert_criteria_adjustment(
        self,
        *,
        session_id: str,
        turn_id: int,
        adjustment_type: str,
        affected_field: str,
        before_value: dict[str, Any] | None,
        after_value: dict[str, Any] | None,
        triggered_by_feedback_id: int | None = None,
        adjustment_reason: str | None = None,
        created_at: datetime,
    ) -> int:
        self._criteria_adjustment_seq += 1
        self._criteria_adjustments.append(
            {
                "adjustment_id": self._criteria_adjustment_seq,
                "session_id": session_id,
                "turn_id": int(turn_id),
                "adjustment_type": adjustment_type,
                "affected_field": affected_field,
                "before_value": deepcopy(before_value or {}),
                "after_value": deepcopy(after_value or {}),
                "triggered_by_feedback_id": triggered_by_feedback_id,
                "adjustment_reason": adjustment_reason,
                "created_at": created_at,
            }
        )
        return self._criteria_adjustment_seq

    def load_working_criteria_adjustments(self, session_id: str) -> list[dict[str, Any]]:
        return [
            deepcopy(item)
            for item in self._criteria_adjustments
            if item["session_id"] == session_id
        ]

    def get_latest_view_snapshot(self, session_id: str) -> StoredViewSnapshot | None:
        for snapshot in reversed(self._view_snapshots):
            if snapshot.session_id == session_id:
                return deepcopy(snapshot)
        return None

    def list_view_snapshots(self, session_id: str) -> list[StoredViewSnapshot]:
        return [
            deepcopy(snapshot)
            for snapshot in self._view_snapshots
            if snapshot.session_id == session_id
        ]

    def create_profile_update_request(
        self,
        *,
        request_id: str,
        session_id: str,
        profile_id: int,
        proposed_patch: dict[str, Any],
        current_snapshot: dict[str, Any] | None,
        evidence_text: str | None,
        expires_at: datetime | None,
        created_at: datetime,
    ) -> dict[str, Any]:
        record = {
            "request_id": request_id,
            "session_id": session_id,
            "profile_id": int(profile_id),
            "status": "pending",
            "proposed_patch": deepcopy(proposed_patch),
            "current_snapshot": deepcopy(current_snapshot or {}),
            "evidence_text": evidence_text,
            "expires_at": expires_at,
            "confirmed_at": None,
            "rejected_at": None,
            "created_at": created_at,
            "updated_at": created_at,
        }
        self._profile_update_requests[request_id] = deepcopy(record)
        return deepcopy(record)

    def get_profile_update_request(self, request_id: str) -> dict[str, Any] | None:
        record = self._profile_update_requests.get(str(request_id or "").strip())
        return deepcopy(record) if record else None

    def mark_profile_update_request(
        self,
        *,
        request_id: str,
        status: str,
        now: datetime,
    ) -> None:
        record = self._profile_update_requests.get(request_id)
        if record is None:
            return
        record["status"] = status
        record["updated_at"] = now
        if status == "confirmed":
            record["confirmed_at"] = now
        if status == "rejected":
            record["rejected_at"] = now
        self._profile_update_requests[request_id] = record


class MySQLDiscoveryStorage:
    def __init__(self, dsn: str, *, init_mode: str | None = None) -> None:
        self._dsn = str(dsn or "").strip()
        if not self._dsn:
            raise ValueError("discovery MySQL DSN is required")
        conn = connect_db(self._dsn)
        try:
            initialize_database(conn, mode=init_mode)
        finally:
            conn.close()

    def next_session_id(self) -> str:
        return _new_prefixed_id("discovery-session")

    def next_action_id(self) -> str:
        return _new_prefixed_id("act")

    def next_item_id(self, prefix: str) -> str:
        return _new_prefixed_id(prefix)

    def save_session(self, session: StoredSession) -> None:
        conn = self._open()
        try:
            state_json = json_dumps(
                {
                    **dict(session.state or {}),
                    "visible_action_ids": list(session.visible_action_ids),
                }
            )
            conn.execute(
                """
                INSERT INTO discovery_agent_sessions (
                    session_id, requester_id, profile_id, status, phase,
                    state_json, latest_view_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    requester_id = VALUES(requester_id),
                    profile_id = VALUES(profile_id),
                    status = VALUES(status),
                    phase = VALUES(phase),
                    state_json = VALUES(state_json),
                    latest_view_json = VALUES(latest_view_json),
                    created_at = VALUES(created_at),
                    updated_at = VALUES(updated_at)
                """,
                (
                    session.session_id,
                    int(session.requester_id),
                    int(session.profile_id),
                    session.status,
                    session.phase,
                    state_json,
                    json_dumps(session.view),
                    session.created_at,
                    session.updated_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_session(self, session_id: str) -> StoredSession | None:
        conn = self._open()
        try:
            row = row_to_dict(
                conn.execute(
                    """
                    SELECT session_id, requester_id, profile_id, status, phase,
                           state_json, latest_view_json, created_at, updated_at
                    FROM discovery_agent_sessions
                    WHERE session_id = ?
                    LIMIT 1
                    """,
                    (session_id,),
                ).fetchone()
            )
        finally:
            conn.close()
        if row is None:
            return None
        state = dict(json_loads(str(row.get("state_json") or "{}"), {}) or {})
        visible_action_ids = [
            str(item).strip()
            for item in list(state.get("visible_action_ids") or [])
            if str(item or "").strip()
        ]
        return StoredSession(
            session_id=str(row["session_id"]),
            requester_id=int(row["requester_id"]),
            profile_id=int(row["profile_id"]),
            status=str(row["status"]),
            phase=str(row["phase"]),
            created_at=_parse_datetime(row.get("created_at")),
            updated_at=_parse_datetime(row.get("updated_at")),
            view=dict(json_loads(str(row.get("latest_view_json") or "{}"), {}) or {}),
            visible_action_ids=visible_action_ids,
            state=state,
        )

    def save_action(self, action: StoredAction) -> None:
        conn = self._open()
        try:
            conn.execute(
                """
                INSERT INTO discovery_agent_actions (
                    action_id, session_id, label, style, semantic_payload_json,
                    created_at, expires_at, consumed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON DUPLICATE KEY UPDATE
                    session_id = VALUES(session_id),
                    label = VALUES(label),
                    style = VALUES(style),
                    semantic_payload_json = VALUES(semantic_payload_json),
                    created_at = VALUES(created_at),
                    expires_at = VALUES(expires_at),
                    consumed_at = VALUES(consumed_at)
                """,
                (
                    action.action_id,
                    action.session_id,
                    action.label,
                    action.style,
                    json_dumps(action.semantic_payload),
                    action.created_at,
                    action.expires_at,
                    action.consumed_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _stored_action_from_row(self, row: dict[str, Any] | None) -> StoredAction | None:
        if row is None:
            return None
        return StoredAction(
            action_id=str(row["action_id"]),
            session_id=str(row["session_id"]),
            label=str(row["label"]),
            style=str(row["style"]),
            semantic_payload=dict(json_loads(str(row.get("semantic_payload_json") or "{}"), {}) or {}),
            created_at=_parse_datetime(row.get("created_at")),
            expires_at=_parse_optional_datetime(row.get("expires_at")),
            consumed_at=_parse_optional_datetime(row.get("consumed_at")),
        )

    def get_action(self, session_id: str, action_id: str) -> StoredAction | None:
        conn = self._open()
        try:
            row = row_to_dict(
                conn.execute(
                    """
                    SELECT action_id, session_id, label, style, semantic_payload_json,
                           created_at, expires_at, consumed_at
                    FROM discovery_agent_actions
                    WHERE action_id = ? AND session_id = ?
                    LIMIT 1
                    """,
                    (action_id, session_id),
                ).fetchone()
            )
        finally:
            conn.close()
        return self._stored_action_from_row(row)

    def get_actions(self, session_id: str, action_ids: list[str]) -> dict[str, StoredAction]:
        normalized = [str(item or "").strip() for item in action_ids if str(item or "").strip()]
        if not normalized:
            return {}
        placeholders = ", ".join(["?"] * len(normalized))
        conn = self._open()
        try:
            rows = conn.execute(
                f"""
                SELECT action_id, session_id, label, style, semantic_payload_json,
                       created_at, expires_at, consumed_at
                FROM discovery_agent_actions
                WHERE session_id = ?
                  AND action_id IN ({placeholders})
                """,
                [session_id, *normalized],
            ).fetchall()
        finally:
            conn.close()
        out: dict[str, StoredAction] = {}
        for raw_row in rows:
            action = self._stored_action_from_row(row_to_dict(raw_row))
            if action is not None:
                out[action.action_id] = action
        return out

    def mark_action_consumed(self, action_id: str, now: datetime) -> None:
        conn = self._open()
        try:
            conn.execute(
                "UPDATE discovery_agent_actions SET consumed_at = ? WHERE action_id = ?",
                (now, action_id),
            )
            conn.commit()
        finally:
            conn.close()

    def replace_visible_actions(self, session_id: str, action_ids: list[str]) -> None:
        session = self.get_session(session_id)
        if session is None:
            return
        session.visible_action_ids = list(action_ids)
        session.state["visible_action_ids"] = list(action_ids)
        self.save_session(session)

    def create_action(
        self,
        *,
        session_id: str,
        label: str,
        style: str,
        semantic_payload: dict[str, Any] | None,
        now: datetime,
        ttl: timedelta = timedelta(days=7),  # 延长到7天，避免用户点击时action已过期
    ) -> StoredAction:
        action = StoredAction(
            action_id=self.next_action_id(),
            session_id=session_id,
            label=label,
            style=style,
            semantic_payload=deepcopy(semantic_payload or {}),
            created_at=now,
            expires_at=now + ttl,
        )
        self.save_action(action)
        return action

    def create_turn(
        self,
        *,
        session_id: str,
        request_kind: str,
        user_message_text: str | None,
        consumed_action_id: str | None,
        agent_decision: dict[str, Any],
        view_snapshot: dict[str, Any],
        created_at: datetime,
        search_run_id: int | None = None,
        trace_id: str | None = None,
    ) -> int:
        conn = self._open()
        try:
            conn.execute(
                """
                INSERT INTO discovery_agent_turns (
                    session_id, request_kind, user_message_text, consumed_action_id,
                    agent_decision_json, view_snapshot_json, search_run_id, trace_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    request_kind,
                    user_message_text,
                    consumed_action_id,
                    json_dumps(agent_decision),
                    json_dumps(view_snapshot),
                    search_run_id,
                    trace_id,
                    created_at,
                ),
            )
            turn_id = int(conn.lastrowid)
            conn.commit()
            return turn_id
        finally:
            conn.close()

    def get_latest_turn_id(self, session_id: str) -> int | None:
        conn = self._open()
        try:
            row = conn.execute(
                """
                SELECT turn_id
                FROM discovery_agent_turns
                WHERE session_id = ?
                ORDER BY turn_id DESC
                LIMIT 1
                """,
                (session_id,),
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            return None
        row_dict = row_to_dict(row)
        raw_turn_id = row_dict.get("turn_id") if isinstance(row_dict, dict) else row[0]
        return int(raw_turn_id) if raw_turn_id not in (None, "") else None

    def create_search_run(
        self,
        *,
        session_id: str,
        requester_id: int,
        profile_id: int,
        source: str,
        criteria: dict[str, Any],
        self_profile: dict[str, Any] | None,
        limit_count: int,
        response: dict[str, Any],
        created_at: datetime,
    ) -> int:
        conn = self._open()
        try:
            conn.execute(
                """
                INSERT INTO discovery_search_runs (
                    session_id, requester_id, profile_id, source, criteria_json,
                    self_profile_json, limit_count, result_count, has_match, response_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    int(requester_id),
                    int(profile_id),
                    source,
                    json_dumps(criteria),
                    json_dumps(self_profile),
                    int(limit_count),
                    int(response.get("result_count") or 0),
                    1 if response.get("has_match") else 0,
                    json_dumps(response),
                    created_at,
                ),
            )
            search_run_id = int(conn.lastrowid)
            conn.commit()
            return search_run_id
        finally:
            conn.close()

    def get_search_run(self, search_run_id: int) -> StoredSearchRun | None:
        conn = self._open()
        try:
            row = row_to_dict(
                conn.execute(
                    """
                    SELECT search_run_id, session_id, requester_id, profile_id, source,
                           criteria_json, self_profile_json, limit_count, result_count,
                           has_match, response_json, created_at
                    FROM discovery_search_runs
                    WHERE search_run_id = ?
                    LIMIT 1
                    """,
                    (int(search_run_id),),
                ).fetchone()
            )
        finally:
            conn.close()
        if row is None:
            return None
        return StoredSearchRun(
            search_run_id=int(row["search_run_id"]),
            session_id=str(row["session_id"]),
            requester_id=int(row["requester_id"]),
            profile_id=int(row["profile_id"]),
            source=str(row["source"]),
            criteria=dict(json_loads(str(row.get("criteria_json") or "{}"), {}) or {}),
            self_profile=json_loads(str(row.get("self_profile_json") or "null"), None),
            limit_count=int(row.get("limit_count") or 0),
            result_count=int(row.get("result_count") or 0),
            has_match=bool(int(row.get("has_match") or 0)),
            response=dict(json_loads(str(row.get("response_json") or "{}"), {}) or {}),
            created_at=_parse_datetime(row.get("created_at")),
        )

    def create_tool_call(
        self,
        *,
        session_id: str,
        turn_id: int,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        status: str,
        search_run_id: int | None,
        created_at: datetime,
        trace_id: str | None = None,
    ) -> int:
        conn = self._open()
        try:
            conn.execute(
                """
                INSERT INTO discovery_agent_tool_calls (
                    session_id, turn_id, tool_name, tool_args_json,
                    tool_result_json, status, search_run_id, trace_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    int(turn_id),
                    tool_name,
                    json_dumps(arguments),
                    json_dumps(result),
                    status,
                    search_run_id,
                    trace_id,
                    created_at,
                ),
            )
            tool_call_id = int(conn.lastrowid)
            conn.commit()
            return tool_call_id
        finally:
            conn.close()

    def list_tool_calls(self, session_id: str, *, turn_id: int | None = None) -> list[StoredToolCall]:
        conn = self._open()
        try:
            if turn_id is None:
                rows = conn.execute(
                    """
                    SELECT tool_call_id, session_id, turn_id, tool_name, tool_args_json,
                           tool_result_json, status, search_run_id, trace_id, created_at
                    FROM discovery_agent_tool_calls
                    WHERE session_id = ?
                    ORDER BY tool_call_id ASC
                    """,
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT tool_call_id, session_id, turn_id, tool_name, tool_args_json,
                           tool_result_json, status, search_run_id, trace_id, created_at
                    FROM discovery_agent_tool_calls
                    WHERE session_id = ? AND turn_id = ?
                    ORDER BY tool_call_id ASC
                    """,
                    (session_id, int(turn_id)),
                ).fetchall()
        finally:
            conn.close()
        return [
            StoredToolCall(
                tool_call_id=int(row["tool_call_id"]),
                session_id=str(row["session_id"]),
                turn_id=int(row["turn_id"]),
                tool_name=str(row["tool_name"]),
                arguments=dict(json_loads(str(row.get("tool_args_json") or "{}"), {}) or {}),
                result=dict(json_loads(str(row.get("tool_result_json") or "{}"), {}) or {}),
                status=str(row["status"]),
                search_run_id=int(row["search_run_id"]) if row.get("search_run_id") is not None else None,
                trace_id=str(row.get("trace_id") or "").strip() or None,
                created_at=_parse_datetime(row.get("created_at")),
            )
            for row in (row_to_dict(item) for item in rows)
            if row is not None
        ]

    def create_view_snapshot(
        self,
        *,
        session_id: str,
        turn_id: int | None,
        phase: str,
        view_snapshot: dict[str, Any],
        created_at: datetime,
        trace_id: str | None = None,
    ) -> int:
        conn = self._open()
        try:
            conn.execute(
                """
                INSERT INTO discovery_view_snapshots (
                    session_id, turn_id, phase, view_json, trace_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    turn_id,
                    phase,
                    json_dumps(view_snapshot),
                    trace_id,
                    created_at,
                ),
            )
            snapshot_id = int(conn.lastrowid)
            conn.commit()
            return snapshot_id
        finally:
            conn.close()

    def get_latest_view_snapshot(self, session_id: str) -> StoredViewSnapshot | None:
        conn = self._open()
        try:
            row = row_to_dict(
                conn.execute(
                    """
                    SELECT snapshot_id, session_id, turn_id, phase, view_json, trace_id, created_at
                    FROM discovery_view_snapshots
                    WHERE session_id = ?
                    ORDER BY snapshot_id DESC
                    LIMIT 1
                    """,
                    (session_id,),
                ).fetchone()
            )
        finally:
            conn.close()
        if row is None:
            return None
        return StoredViewSnapshot(
            snapshot_id=int(row["snapshot_id"]),
            session_id=str(row["session_id"]),
            turn_id=int(row["turn_id"]) if row.get("turn_id") is not None else None,
            phase=str(row["phase"]),
            view=dict(json_loads(str(row.get("view_json") or "{}"), {}) or {}),
            trace_id=str(row.get("trace_id") or "").strip() or None,
            created_at=_parse_datetime(row.get("created_at")),
        )

    def list_view_snapshots(self, session_id: str) -> list[StoredViewSnapshot]:
        conn = self._open()
        try:
            rows = conn.execute(
                """
                SELECT snapshot_id, session_id, turn_id, phase, view_json, trace_id, created_at
                FROM discovery_view_snapshots
                WHERE session_id = ?
                ORDER BY snapshot_id ASC
                """,
                (session_id,),
            ).fetchall()
        finally:
            conn.close()
        return [
            StoredViewSnapshot(
                snapshot_id=int(row["snapshot_id"]),
                session_id=str(row["session_id"]),
                turn_id=int(row["turn_id"]) if row.get("turn_id") is not None else None,
                phase=str(row["phase"]),
                view=dict(json_loads(str(row.get("view_json") or "{}"), {}) or {}),
                trace_id=str(row.get("trace_id") or "").strip() or None,
                created_at=_parse_datetime(row.get("created_at")),
            )
            for row in (row_to_dict(item) for item in rows)
            if row is not None
        ]

    def create_profile_update_request(
        self,
        *,
        request_id: str,
        session_id: str,
        profile_id: int,
        proposed_patch: dict[str, Any],
        current_snapshot: dict[str, Any] | None,
        evidence_text: str | None,
        expires_at: datetime | None,
        created_at: datetime,
    ) -> dict[str, Any]:
        conn = self._open()
        try:
            conn.execute(
                """
                INSERT INTO discovery_profile_update_requests (
                    request_id, session_id, profile_id, status,
                    proposed_patch_json, current_snapshot_json, evidence_text,
                    expires_at, confirmed_at, rejected_at, created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    request_id,
                    session_id,
                    int(profile_id),
                    json_dumps(proposed_patch),
                    json_dumps(current_snapshot or {}),
                    evidence_text,
                    expires_at,
                    created_at,
                    created_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()
        return {
            "request_id": request_id,
            "session_id": session_id,
            "profile_id": int(profile_id),
            "status": "pending",
            "proposed_patch": deepcopy(proposed_patch),
            "current_snapshot": deepcopy(current_snapshot or {}),
            "evidence_text": evidence_text,
            "expires_at": expires_at,
            "confirmed_at": None,
            "rejected_at": None,
            "created_at": created_at,
            "updated_at": created_at,
        }

    def get_profile_update_request(self, request_id: str) -> dict[str, Any] | None:
        conn = self._open()
        try:
            row = row_to_dict(
                conn.execute(
                    """
                    SELECT request_id, session_id, profile_id, status,
                           proposed_patch_json, current_snapshot_json, evidence_text,
                           expires_at, confirmed_at, rejected_at, created_at, updated_at
                    FROM discovery_profile_update_requests
                    WHERE request_id = ?
                    LIMIT 1
                    """,
                    (request_id,),
                ).fetchone()
            )
        finally:
            conn.close()
        if row is None:
            return None
        return {
            "request_id": str(row["request_id"]),
            "session_id": str(row["session_id"]),
            "profile_id": int(row["profile_id"]),
            "status": str(row["status"]),
            "proposed_patch": dict(json_loads(str(row.get("proposed_patch_json") or "{}"), {}) or {}),
            "current_snapshot": dict(json_loads(str(row.get("current_snapshot_json") or "{}"), {}) or {}),
            "evidence_text": row.get("evidence_text"),
            "expires_at": _parse_optional_datetime(row.get("expires_at")),
            "confirmed_at": _parse_optional_datetime(row.get("confirmed_at")),
            "rejected_at": _parse_optional_datetime(row.get("rejected_at")),
            "created_at": _parse_datetime(row.get("created_at")),
            "updated_at": _parse_datetime(row.get("updated_at")),
        }

    def mark_profile_update_request(
        self,
        *,
        request_id: str,
        status: str,
        now: datetime,
    ) -> None:
        conn = self._open()
        try:
            confirmed_at = now if status == "confirmed" else None
            rejected_at = now if status == "rejected" else None
            conn.execute(
                """
                UPDATE discovery_profile_update_requests
                SET status = ?, confirmed_at = ?, rejected_at = ?, updated_at = ?
                WHERE request_id = ?
                """,
                (status, confirmed_at, rejected_at, now, request_id),
            )
            conn.commit()
        finally:
            conn.close()

    # ========== 新增：反馈收集相关接口 ==========

    def insert_rejection_feedback(
        self,
        *,
        session_id: str,
        turn_id: int,
        requester_id: int,
        feedback_type: str,
        feedback_text: str,
        feedback_detail: str | None = None,
        rejected_batch_id: str | None = None,
        rejected_candidate_ids: list[str] | None = None,
        source_type: str = "explicit",
        追问_triggered: bool = True,
        追问_skipped: bool = False,
        is_secondary_feedback: bool = False,
        primary_feedback_id: int | None = None,
        created_at: datetime,
    ) -> int:
        """插入拒绝反馈记录。"""
        conn = self._open()
        try:
            conn.execute(
                """
                INSERT INTO discovery_rejection_feedbacks (
                    session_id, turn_id, requester_id, feedback_type, feedback_text,
                    feedback_detail, rejected_batch_id, rejected_candidate_ids,
                    source_type, 追问_triggered, 追问_skipped,
                    is_secondary_feedback, primary_feedback_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    int(turn_id),
                    int(requester_id),
                    feedback_type,
                    feedback_text,
                    feedback_detail,
                    rejected_batch_id,
                    json_dumps(rejected_candidate_ids or []),
                    source_type,
                    int(追问_triggered),
                    int(追问_skipped),
                    int(is_secondary_feedback),
                    primary_feedback_id,
                    created_at,
                ),
            )
            feedback_id = int(conn.lastrowid)
            conn.commit()
            return feedback_id
        finally:
            conn.close()

    def insert_criteria_adjustment(
        self,
        *,
        session_id: str,
        turn_id: int,
        adjustment_type: str,
        affected_field: str,
        before_value: dict[str, Any] | None,
        after_value: dict[str, Any] | None,
        triggered_by_feedback_id: int | None = None,
        adjustment_reason: str | None = None,
        created_at: datetime,
    ) -> int:
        """插入criteria调整记录。"""
        conn = self._open()
        try:
            conn.execute(
                """
                INSERT INTO discovery_working_criteria_adjustments (
                    session_id, turn_id, adjustment_type, affected_field,
                    before_value, after_value, triggered_by_feedback_id,
                    adjustment_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    int(turn_id),
                    adjustment_type,
                    affected_field,
                    json_dumps(before_value or {}),
                    json_dumps(after_value or {}),
                    triggered_by_feedback_id,
                    adjustment_reason,
                    created_at,
                ),
            )
            adjustment_id = int(conn.lastrowid)
            conn.commit()
            return adjustment_id
        finally:
            conn.close()

    def load_working_criteria_adjustments(
        self,
        session_id: str,
    ) -> list[dict[str, Any]]:
        """加载session的所有criteria调整记录。"""
        conn = self._open()
        try:
            rows = conn.execute(
                """
                SELECT adjustment_id, session_id, turn_id, adjustment_type,
                       affected_field, before_value, after_value,
                       triggered_by_feedback_id, adjustment_reason, created_at
                FROM discovery_working_criteria_adjustments
                WHERE session_id = ?
                ORDER BY adjustment_id ASC
                """,
                (session_id,),
            ).fetchall()
            return [
                {
                    "adjustment_id": int(row[0]),
                    "session_id": str(row[1]),
                    "turn_id": int(row[2]),
                    "adjustment_type": str(row[3]),
                    "affected_field": str(row[4]),
                    "before_value": json_loads(str(row[5] or "{}"), {}),
                    "after_value": json_loads(str(row[6] or "{}"), {}),
                    "triggered_by_feedback_id": row[7],
                    "adjustment_reason": row[8],
                    "created_at": _parse_datetime(row[9]),
                }
                for row in rows
            ]
        finally:
            conn.close()

    def _open(self) -> MySQLCompatConnection:
        return connect_db(self._dsn)


def _new_prefixed_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        raise ValueError("datetime value is required")
    return datetime.fromisoformat(text)


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return _parse_datetime(value)


__all__ = [
    "DEFAULT_DISCOVERY_MYSQL_DSN",
    "DEFAULT_DISCOVERY_TEST_MYSQL_DSN",
    "InMemoryDiscoveryStorage",
    "MySQLCompatConnection",
    "MySQLDiscoveryStorage",
    "StoredAction",
    "StoredSearchRun",
    "StoredSession",
    "StoredToolCall",
    "StoredViewSnapshot",
    "connect_db",
    "initialize_database",
    "json_dumps",
    "json_loads",
    "reset_all_tables",
    "row_to_dict",
]
