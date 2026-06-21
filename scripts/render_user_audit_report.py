#!/usr/bin/env python3
"""Render a consolidated Markdown audit report for one user across subsystems."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from _repo_bootstrap import REPO_ROOT, bootstrap_repo

bootstrap_repo()

from match_domain.summary_loader import build_summary_meta
from outer_mysql_compat import connect_mysql_repo_db, json_loads
from profile_detail_reader import load_profile_detail
from relationship_ledger import (
    DEFAULT_RELATION_LEDGER_MYSQL_DSN,
    build_unified_timeline_from_ledger,
    get_relation_by_key,
    list_relations_for_profile_refs,
    summarize_ledger_relation_for_timeline,
)

sys.path.insert(0, str(REPO_ROOT / "external-systems" / "partner-chat-system"))
sys.path.insert(0, str(REPO_ROOT / "external-systems" / "partner-discovery-system"))
sys.path.insert(0, str(REPO_ROOT / "external-systems" / "partner-matchmaking-system"))
sys.path.insert(0, str(REPO_ROOT / "external-systems" / "partner-recommendation-system"))

from chat_system.storage import DEFAULT_CHAT_MYSQL_DSN  # type: ignore  # noqa: E402
from discovery_system.storage import DEFAULT_DISCOVERY_MYSQL_DSN  # type: ignore  # noqa: E402
from matchmaking_system.storage import DEFAULT_MATCHMAKING_MYSQL_DSN  # type: ignore  # noqa: E402
from recommendation_system.storage import DEFAULT_RECOMMENDATION_MYSQL_DSN  # type: ignore  # noqa: E402


def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path, override=False)


def _safe_json_loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json_loads(value, default)
    except Exception:
        return default


def _pretty_time(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return raw


def _truncate(value: Any, limit: int = 220) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _query_all(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def _query_one(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def _optional_read(label: str, fn: Any) -> tuple[Any, str | None]:
    try:
        return fn(), None
    except Exception as exc:  # noqa: BLE001
        return None, f"{label}: {type(exc).__name__}: {exc}"


@dataclass
class ReportContext:
    user_id: int
    source: str | None
    profile_table: str | None
    output: Path
    chat_dsn: str
    discovery_dsn: str
    matchmaking_dsn: str
    recommendation_dsn: str
    ledger_dsn: str
    persona_dsn: str | None


class UserAuditReportBuilder:
    def __init__(self, ctx: ReportContext) -> None:
        self.ctx = ctx
        self.warnings: list[str] = []

    def build(self) -> str:
        payload = {
            "user_account": self._load_user_account(),
            "profile": self._load_profile(),
            "onboarding": self._load_onboarding(),
            "discovery": self._load_discovery(),
            "chat": self._load_chat(),
            "matchmaking": self._load_matchmaking(),
            "recommendation": self._load_recommendation(),
            "persona": self._load_persona(),
            "ledger": self._load_ledger(),
        }
        return self._render_markdown(payload)

    def _connect(self, dsn: str, subsystem_name: str) -> Any:
        return connect_mysql_repo_db(dsn, subsystem_name=subsystem_name)

    def _load_user_account(self) -> dict[str, Any]:
        def _reader() -> dict[str, Any]:
            conn = self._connect(self.ctx.chat_dsn, "Chat")
            try:
                account = _query_one(conn, "SELECT * FROM user_accounts WHERE user_id = ?", (str(self.ctx.user_id),))
                identities = _query_all(
                    conn,
                    "SELECT * FROM user_account_identities WHERE user_id = ? ORDER BY created_at DESC",
                    (str(self.ctx.user_id),),
                )
                sessions = _query_all(
                    conn,
                    "SELECT * FROM auth_sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT 20",
                    (str(self.ctx.user_id),),
                )
                logins = _query_all(
                    conn,
                    "SELECT * FROM auth_login_events WHERE user_id = ? ORDER BY created_at DESC LIMIT 30",
                    (str(self.ctx.user_id),),
                )
                return {
                    "account": account,
                    "identities": identities,
                    "sessions": sessions,
                    "login_events": logins,
                }
            finally:
                conn.close()

        data, warning = _optional_read("chat auth", _reader)
        if warning:
            self.warnings.append(warning)
        return data or {}

    def _load_profile(self) -> dict[str, Any]:
        detail, warning = _optional_read(
            "profile detail",
            lambda: load_profile_detail(
                source=self.ctx.source,
                table_name=self.ctx.profile_table,
                profile_id=self.ctx.user_id,
                include_source=True,
            ),
        )
        if warning:
            self.warnings.append(warning)
        return detail or {}

    def _load_onboarding(self) -> dict[str, Any]:
        def _reader() -> dict[str, Any]:
            conn = self._connect(self.ctx.chat_dsn, "Chat")
            try:
                row = _query_one(
                    conn,
                    "SELECT * FROM user_onboarding_profiles WHERE user_id = ?",
                    (str(self.ctx.user_id),),
                )
                if not row:
                    return {}
                row["basic_info"] = _safe_json_loads(row.pop("basic_info_json", None), {})
                row["preference"] = _safe_json_loads(row.pop("preference_json", None), {})
                return row
            finally:
                conn.close()

        data, warning = _optional_read("onboarding", _reader)
        if warning:
            self.warnings.append(warning)
        return data or {}

    def _load_discovery(self) -> dict[str, Any]:
        def _reader() -> dict[str, Any]:
            conn = self._connect(self.ctx.discovery_dsn, "Discovery")
            try:
                sessions = _query_all(
                    conn,
                    "SELECT * FROM discovery_agent_sessions WHERE requester_id = ? ORDER BY updated_at DESC LIMIT 20",
                    (self.ctx.user_id,),
                )
                session_ids = [row["session_id"] for row in sessions]
                turns: list[dict[str, Any]] = []
                tool_calls: list[dict[str, Any]] = []
                view_snapshots: list[dict[str, Any]] = []
                search_runs: list[dict[str, Any]] = []
                profile_updates: list[dict[str, Any]] = []
                rejection_feedbacks: list[dict[str, Any]] = []
                for session_id in session_ids:
                    turns.extend(
                        _query_all(
                            conn,
                            "SELECT * FROM discovery_agent_turns WHERE session_id = ? ORDER BY created_at ASC LIMIT 100",
                            (session_id,),
                        )
                    )
                    tool_calls.extend(
                        _query_all(
                            conn,
                            "SELECT * FROM discovery_agent_tool_calls WHERE session_id = ? ORDER BY created_at ASC LIMIT 100",
                            (session_id,),
                        )
                    )
                    view_snapshots.extend(
                        _query_all(
                            conn,
                            "SELECT * FROM discovery_view_snapshots WHERE session_id = ? ORDER BY created_at ASC LIMIT 100",
                            (session_id,),
                        )
                    )
                    search_runs.extend(
                        _query_all(
                            conn,
                            "SELECT * FROM discovery_search_runs WHERE session_id = ? ORDER BY created_at ASC LIMIT 100",
                            (session_id,),
                        )
                    )
                    profile_updates.extend(
                        _query_all(
                            conn,
                            "SELECT * FROM discovery_profile_update_requests WHERE session_id = ? ORDER BY created_at DESC LIMIT 50",
                            (session_id,),
                        )
                    )
                    rejection_feedbacks.extend(
                        _query_all(
                            conn,
                            "SELECT * FROM discovery_rejection_feedbacks WHERE session_id = ? ORDER BY created_at DESC LIMIT 50",
                            (session_id,),
                        )
                    )
                return {
                    "sessions": sessions,
                    "turns": turns,
                    "tool_calls": tool_calls,
                    "view_snapshots": view_snapshots,
                    "search_runs": search_runs,
                    "profile_updates": profile_updates,
                    "rejection_feedbacks": rejection_feedbacks,
                }
            finally:
                conn.close()

        data, warning = _optional_read("discovery", _reader)
        if warning:
            self.warnings.append(warning)
        return data or {}

    def _load_chat(self) -> dict[str, Any]:
        def _reader() -> dict[str, Any]:
            conn = self._connect(self.ctx.chat_dsn, "Chat")
            try:
                threads = _query_all(
                    conn,
                    """
                    SELECT *
                    FROM chat_threads
                    WHERE participant_a_id = ? OR participant_b_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 30
                    """,
                    (str(self.ctx.user_id), str(self.ctx.user_id)),
                )
                thread_ids = [row["thread_id"] for row in threads]
                messages: list[dict[str, Any]] = []
                summaries: list[dict[str, Any]] = []
                risk_cases = _query_all(
                    conn,
                    "SELECT * FROM chat_risk_cases WHERE subject_user_id = ? ORDER BY updated_at DESC LIMIT 20",
                    (str(self.ctx.user_id),),
                )
                moderation = _query_all(
                    conn,
                    "SELECT * FROM account_moderation_states WHERE subject_user_id = ? ORDER BY updated_at DESC LIMIT 20",
                    (str(self.ctx.user_id),),
                )
                for thread_id in thread_ids:
                    messages.extend(
                        _query_all(
                            conn,
                            "SELECT * FROM chat_messages WHERE thread_id = ? ORDER BY created_at ASC LIMIT 200",
                            (thread_id,),
                        )
                    )
                    summary = _query_one(
                        conn,
                        "SELECT * FROM chat_thread_summaries WHERE thread_id = ?",
                        (thread_id,),
                    )
                    if summary:
                        summaries.append(summary)
                return {
                    "threads": threads,
                    "messages": messages,
                    "summaries": summaries,
                    "risk_cases": risk_cases,
                    "moderation": moderation,
                }
            finally:
                conn.close()

        data, warning = _optional_read("chat", _reader)
        if warning:
            self.warnings.append(warning)
        return data or {}

    def _load_matchmaking(self) -> dict[str, Any]:
        def _reader() -> dict[str, Any]:
            conn = self._connect(self.ctx.matchmaking_dsn, "Matchmaking")
            try:
                members = _query_all(
                    conn,
                    "SELECT * FROM matchmaking_pool_members WHERE self_id = ? ORDER BY updated_at DESC LIMIT 10",
                    (self.ctx.user_id,),
                )
                member_ids = [row["member_id"] for row in members]
                edges: list[dict[str, Any]] = []
                feedbacks: list[dict[str, Any]] = []
                match_cases: list[dict[str, Any]] = []
                case_events: list[dict[str, Any]] = []
                proxy_cases = _query_all(
                    conn,
                    """
                    SELECT * FROM proxy_intro_cases
                    WHERE requester_id = ? OR candidate_id = ?
                    ORDER BY updated_at DESC LIMIT 30
                    """,
                    (self.ctx.user_id, self.ctx.user_id),
                )
                proxy_events = _query_all(
                    conn,
                    """
                    SELECT * FROM proxy_intro_case_events
                    WHERE requester_id = ? OR candidate_id = ?
                    ORDER BY occurred_at DESC LIMIT 50
                    """,
                    (self.ctx.user_id, self.ctx.user_id),
                )
                for member_id in member_ids:
                    edges.extend(
                        _query_all(
                            conn,
                            """
                            SELECT * FROM matchmaking_edges
                            WHERE owner_member_id = ? OR candidate_member_id = ?
                            ORDER BY updated_at DESC LIMIT 50
                            """,
                            (member_id, member_id),
                        )
                    )
                    feedbacks.extend(
                        _query_all(
                            conn,
                            "SELECT * FROM matchmaking_feedback_events WHERE member_id = ? ORDER BY updated_at DESC LIMIT 50",
                            (member_id,),
                        )
                    )
                    match_cases.extend(
                        _query_all(
                            conn,
                            """
                            SELECT * FROM match_cases
                            WHERE first_contact_member_id = ? OR second_contact_member_id = ?
                            ORDER BY updated_at DESC LIMIT 50
                            """,
                            (member_id, member_id),
                        )
                    )
                for row in match_cases:
                    case_id = row["case_id"]
                    case_events.extend(
                        _query_all(
                            conn,
                            "SELECT * FROM match_case_events WHERE case_id = ? ORDER BY occurred_at ASC LIMIT 100",
                            (case_id,),
                        )
                    )
                return {
                    "members": members,
                    "edges": edges,
                    "feedbacks": feedbacks,
                    "match_cases": match_cases,
                    "case_events": case_events,
                    "proxy_cases": proxy_cases,
                    "proxy_events": proxy_events,
                }
            finally:
                conn.close()

        data, warning = _optional_read("matchmaking", _reader)
        if warning:
            self.warnings.append(warning)
        return data or {}

    def _load_recommendation(self) -> dict[str, Any]:
        def _reader() -> dict[str, Any]:
            conn = self._connect(self.ctx.recommendation_dsn, "Recommendation")
            try:
                table_names = [
                    "recommendation_subscriptions",
                    "recommendation_results",
                    "recommendation_actions",
                    "outbox_events",
                    "async_jobs",
                ]
                available: dict[str, list[dict[str, Any]]] = {}
                for table_name in table_names:
                    try:
                        if table_name == "recommendation_subscriptions":
                            rows = _query_all(
                                conn,
                                "SELECT * FROM recommendation_subscriptions WHERE requester_id = ? ORDER BY updated_at DESC LIMIT 30",
                                (self.ctx.user_id,),
                            )
                        elif table_name == "recommendation_results":
                            rows = _query_all(
                                conn,
                                "SELECT * FROM recommendation_results WHERE requester_id = ? ORDER BY updated_at DESC LIMIT 50",
                                (self.ctx.user_id,),
                            )
                        elif table_name == "recommendation_actions":
                            rows = _query_all(
                                conn,
                                "SELECT * FROM recommendation_actions WHERE requester_id = ? ORDER BY created_at DESC LIMIT 50",
                                (self.ctx.user_id,),
                            )
                        elif table_name == "outbox_events":
                            rows = _query_all(
                                conn,
                                "SELECT * FROM outbox_events ORDER BY created_at DESC LIMIT 50",
                            )
                        else:
                            rows = _query_all(
                                conn,
                                "SELECT * FROM async_jobs ORDER BY created_at DESC LIMIT 50",
                            )
                    except Exception:
                        rows = []
                    available[table_name] = rows
                return available
            finally:
                conn.close()

        data, warning = _optional_read("recommendation", _reader)
        if warning:
            self.warnings.append(warning)
        return data or {}

    def _load_persona(self) -> dict[str, Any]:
        if not self.ctx.persona_dsn:
            self.warnings.append("persona: no PERSONA_MEMORY_MYSQL_SOURCE configured")
            return {}

        def _reader() -> dict[str, Any]:
            conn = self._connect(self.ctx.persona_dsn, "Persona")
            try:
                summaries = _query_all(
                    conn,
                    """
                    SELECT *
                    FROM conversation_summaries
                    WHERE requester_id = ? OR profile_id = ?
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 100
                    """,
                    (self.ctx.user_id, self.ctx.user_id),
                )
                latest_by_key: dict[str, str] = {}
                for row in summaries:
                    key = str(row.get("summary_key") or row.get("vector_type") or "").strip()
                    text = str(row.get("summary_text") or row.get("summary") or "").strip()
                    if key and text and key not in latest_by_key:
                        latest_by_key[key] = text
                return {
                    "conversation_summaries": summaries,
                    "summary_meta": build_summary_meta(latest_by_key),
                    "latest_summary_by_key": latest_by_key,
                }
            finally:
                conn.close()

        data, warning = _optional_read("persona", _reader)
        if warning:
            self.warnings.append(warning)
        return data or {}

    def _load_ledger(self) -> dict[str, Any]:
        def _reader() -> dict[str, Any]:
            conn = self._connect(self.ctx.ledger_dsn, "RelationshipLedger")
            try:
                profile_ref = f"profile:{self.ctx.user_id}"
                relations = list_relations_for_profile_refs(conn, [profile_ref])
                expanded: list[dict[str, Any]] = []
                for relation in relations[:20]:
                    relation_key = relation.get("relation_key")
                    if not relation_key:
                        continue
                    full_relation = get_relation_by_key(conn, relation_key)
                    if not full_relation:
                        continue
                    expanded.append(
                        {
                            "relation": full_relation,
                            "summary": summarize_ledger_relation_for_timeline(full_relation),
                            "timeline": build_unified_timeline_from_ledger(full_relation),
                        }
                    )
                return {"profile_ref": profile_ref, "relations": expanded}
            finally:
                conn.close()

        data, warning = _optional_read("ledger", _reader)
        if warning:
            self.warnings.append(warning)
        return data or {}

    def _render_markdown(self, payload: dict[str, Any]) -> str:
        narrative = self._build_narrative(payload)
        lines: list[str] = []
        lines.append("# 用户全景审计报告")
        lines.append("")
        lines.append(f"- 用户ID: `{self.ctx.user_id}`")
        lines.append(f"- 生成时间: `{datetime.now().replace(microsecond=0).isoformat(sep=' ')}`")
        lines.append("- 说明: 这份 Markdown 目的是把所有重要信息尽量完整整理出来，方便后续再交给大模型重写为更通俗的 HTML。")
        lines.append("")
        lines.append("## 概览")
        lines.extend(self._md_overview(payload))
        lines.append("")
        if self.warnings:
            lines.append("## 读取提醒")
            lines.extend(self._md_bullets(self.warnings))
            lines.append("")
        lines.append("## 一句话看懂这个用户")
        lines.append("### 当前状态")
        lines.extend(self._md_bullets(narrative["status"]))
        lines.append("")
        lines.append("### 值得关注")
        lines.extend(self._md_bullets(narrative["attention"]))
        lines.append("")
        lines.append("### 最近在发生什么")
        lines.extend(self._md_bullets(narrative["recent"]))
        lines.append("")
        lines.append("### 系统为什么这么处理")
        lines.extend(self._md_bullets(narrative["system"]))
        lines.append("")
        lines.append("## 用户是谁")
        lines.append("### 账号与基础信息")
        lines.extend(self._md_account_facts(payload.get("user_account", {}), payload.get("profile", {}), payload.get("onboarding", {})))
        lines.append("")
        lines.append("### Persona / 偏好摘要")
        lines.extend(self._md_persona_summary(payload.get("persona", {})))
        lines.append("")
        lines.append("## 用户做过什么")
        lines.append("### Discovery 过程时间线")
        lines.extend(self._md_discovery_timeline(payload.get("discovery", {})))
        lines.append("")
        lines.append("### 聊天与互动时间线")
        lines.extend(self._md_chat_timeline(payload.get("chat", {})))
        lines.append("")
        lines.append("## 系统怎么执行的")
        lines.append("### 工具调用与系统决策")
        lines.extend(self._md_tool_calls(payload.get("discovery", {})))
        lines.append("")
        lines.append("### Relationship Ledger / 统一时间线")
        lines.extend(self._md_ledger(payload.get("ledger", {})))
        lines.append("")
        lines.append("## 数据库存了什么")
        lines.append("### Matchmaking / Recommendation 汇总")
        lines.extend(self._md_matchmaking_and_recommendation(payload.get("matchmaking", {}), payload.get("recommendation", {})))
        lines.append("")
        lines.append("### 关键原始数据样本")
        lines.append("```json")
        lines.append(json.dumps(self._raw_samples(payload), ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
        lines.append("## 全量结构化数据")
        lines.append("```json")
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
        return "\n".join(lines)

    def _build_narrative(self, payload: dict[str, Any]) -> dict[str, list[str]]:
        account = payload.get("user_account", {}).get("account") or {}
        profile_block = payload.get("profile") or {}
        profile = profile_block.get("profile") or {}
        discovery = payload.get("discovery") or {}
        chat = payload.get("chat") or {}
        persona = payload.get("persona") or {}
        matchmaking = payload.get("matchmaking") or {}
        recommendation = payload.get("recommendation") or {}
        ledger = payload.get("ledger") or {}

        sessions = discovery.get("sessions") or []
        tool_calls = discovery.get("tool_calls") or []
        search_runs = discovery.get("search_runs") or []
        threads = chat.get("threads") or []
        messages = chat.get("messages") or []
        risk_cases = chat.get("risk_cases") or []
        moderation = chat.get("moderation") or []
        match_cases = matchmaking.get("match_cases") or []
        proxy_cases = matchmaking.get("proxy_cases") or []
        latest_summary = persona.get("latest_summary_by_key") or {}
        relations = ledger.get("relations") or []

        status: list[str] = []
        recent: list[str] = []
        system: list[str] = []
        attention: list[str] = []

        display_name = profile_block.get("name") or profile.get("name") or f"用户 {self.ctx.user_id}"
        city = profile.get("city") or profile.get("self_city")
        age = profile.get("age") or profile.get("self_age")
        job = profile.get("job") or profile.get("self_job")
        if city or age or job:
            status.append(
                f"{display_name} 当前画像里显示为"
                f"{_truncate('、'.join(str(part) for part in [age and f'{age}岁', city and city, job and job] if part), 80)}。"
            )
        else:
            status.append(f"{display_name} 在系统里已有画像，但基础资料还不算完整。")

        if account:
            status.append(
                f"账号状态是 {account.get('account_status') or '未知'}，"
                f"Onboarding 状态是 {account.get('onboarding_status') or '未知'}。"
            )
        else:
            status.append("这个人更多像是画像/业务用户，账号层信息目前没完整读到。")

        if sessions:
            latest_session = sessions[0]
            status.append(
                f"最近一次 discovery 会话还在 {latest_session.get('phase') or '未知阶段'}，"
                f"会话状态是 {latest_session.get('status') or '未知'}。"
            )
        if threads:
            latest_thread = threads[0]
            counterpart = (
                latest_thread.get("participant_b_id")
                if str(latest_thread.get("participant_a_id")) == str(self.ctx.user_id)
                else latest_thread.get("participant_a_id")
            )
            status.append(
                f"他最近已经和用户 {counterpart} 进入聊天线程，聊天状态是 {latest_thread.get('status') or '未知'}。"
            )
        elif match_cases:
            status.append("系统里已经出现匹配案例，但还没看到稳定聊天线程。")
        else:
            status.append("目前还没看到明确进入稳定匹配/聊天关系的证据。")

        if search_runs:
            latest_search = search_runs[0]
            recent.append(
                f"最近一次系统搜索发生在 {_pretty_time(latest_search.get('created_at'))}，"
                f"当次返回了 {latest_search.get('result_count')} 个结果，命中标记是 {latest_search.get('has_match')}。"
            )
        if messages:
            own_messages = [row for row in messages if str(row.get("author_id")) == str(self.ctx.user_id)]
            if own_messages:
                recent.append(
                    f"最近的聊天里，他自己发出的内容偏生活化/推进关系，"
                    f"例如“{_truncate(own_messages[-1].get('body') or '', 30)}”。"
                )
        if latest_summary:
            expectation = latest_summary.get("partner_expectation") or latest_summary.get("values")
            if expectation:
                recent.append(f"从 persona 摘要看，他当前最明确的择偶导向是：{_truncate(expectation, 80)}。")
        if proxy_cases:
            recent.append(f"系统里还能看到 {len(proxy_cases)} 条代理牵线记录，说明他不只走自然聊天链路。")

        if tool_calls:
            search_calls = [row for row in tool_calls if str(row.get("tool_name")) == "search_partner_candidates"]
            sync_calls = [row for row in tool_calls if "persona" in str(row.get("tool_name") or "")]
            if search_calls:
                system.append(
                    f"系统对他最常做的动作是“找候选人”，说明当前主流程仍然是给他持续筛人、推人。"
                )
            if sync_calls:
                ok_sync = [row for row in sync_calls if str(row.get("status")) == "succeeded"]
                failed_sync = [row for row in sync_calls if str(row.get("status")) != "succeeded"]
                if ok_sync:
                    system.append("系统会把对话里提炼出的偏好同步回 persona，说明画像会边聊边更新。")
                if failed_sync:
                    system.append("有些 persona 同步失败，常见原因是这一轮对话没有提取出足够明确的新偏好。")
        if relations:
            system.append("relationship ledger 已经在尝试把跨系统事件串成统一关系链，适合后续做完整因果追踪。")
        else:
            system.append("当前关系总账没有顺利串起来，所以这份报告主要还是基于各业务库分开拼装。")

        if moderation:
            attention.append(
                f"这个用户存在 {len(moderation)} 条账号风控/治理记录，建议重点看是否影响推荐、聊天或资料展示。"
            )
        if risk_cases:
            attention.append(
                f"聊天风控里有 {len(risk_cases)} 条案件，说明他至少被系统作为风险主体观察过。"
            )
        if self.warnings:
            attention.append("有部分子系统读取失败或字段不兼容，所以当前报告仍然不是 100% 全量。")
        if sessions and all(str(row.get("status")) == "active" for row in sessions[: min(5, len(sessions))]):
            attention.append("这个用户最近积累了较多 active discovery 会话，可能存在重复会话、未收口会话或调试痕迹。")
        if not attention:
            attention.append("目前没有看到特别明显的异常，更像是一个持续活跃、正常被系统服务的用户。")

        if recommendation.get("recommendation_subscriptions"):
            system.append("推荐系统里存在订阅记录，说明这个用户可能同时在被动接收推荐，而不只是主动搜索。")
        if match_cases:
            system.append("Matchmaking 库里已经有案例，说明系统对这个用户不只是展示候选人，还进入了撮合执行层。")

        return {
            "status": status or ["暂无可解释状态。"],
            "recent": recent or ["最近行为还不够明显，更多要看原始记录。"],
            "system": system or ["暂时还无法从现有数据推断稳定的系统执行模式。"],
            "attention": attention or ["暂无。"],
        }

    def _md_overview(self, payload: dict[str, Any]) -> list[str]:
        overview = [
            ("发现会话", len(payload.get("discovery", {}).get("sessions", []) or [])),
            ("聊天线程", len(payload.get("chat", {}).get("threads", []) or [])),
            ("匹配案例", len(payload.get("matchmaking", {}).get("match_cases", []) or [])),
            ("代理牵线", len(payload.get("matchmaking", {}).get("proxy_cases", []) or [])),
            ("关系链路", len(payload.get("ledger", {}).get("relations", []) or [])),
        ]
        return [f"- {label}: `{value}`" for label, value in overview]

    def _md_account_facts(
        self,
        account_block: dict[str, Any],
        profile_block: dict[str, Any],
        onboarding_block: dict[str, Any],
    ) -> list[str]:
        account = account_block.get("account") or {}
        profile = profile_block.get("profile") or {}
        facts = [
            ("账号状态", account.get("account_status")),
            ("手机号", account.get("primary_phone")),
            ("注册来源", account.get("register_source")),
            ("首次登录", _pretty_time(account.get("first_login_at"))),
            ("最近登录", _pretty_time(account.get("last_login_at"))),
            ("Onboarding", account.get("onboarding_status") or onboarding_block.get("onboarding_status")),
            ("昵称/姓名", profile_block.get("name") or profile.get("name")),
            ("城市", profile.get("city") or profile.get("self_city")),
            ("年龄", profile.get("age") or profile.get("self_age")),
            ("职业", profile.get("job") or profile.get("self_job")),
            ("教育", profile.get("education") or profile.get("self_education")),
        ]
        identities = account_block.get("identities") or []
        lines = [f"- {label}: `{value if value not in (None, '') else '暂无'}`" for label, value in facts]
        if identities:
            lines.append("- 账号绑定:")
            for row in identities[:10]:
                lines.append(f"  - `{row.get('identity_type')}`: `{row.get('identity_value')}`")
        else:
            lines.append("- 账号绑定: `没有读到账号绑定标识`")
        return lines

    def _md_persona_summary(self, persona_block: dict[str, Any]) -> list[str]:
        latest = persona_block.get("latest_summary_by_key") or {}
        meta = persona_block.get("summary_meta") or {}
        if not latest:
            return ["- 暂无 `conversation_summaries` 数据。"]
        lines = [
            f"- 已加载字段数: `{len(latest)}`",
            f"- 完整度: `{meta.get('completeness')}`",
        ]
        for key, value in latest.items():
            lines.append(f"- {key}: {value}")
        return lines

    def _md_discovery_timeline(self, discovery: dict[str, Any]) -> list[str]:
        events: list[tuple[str, str, str]] = []
        for row in discovery.get("sessions", [])[:10]:
            events.append((
                str(row.get("updated_at") or row.get("created_at") or ""),
                f"Discovery 会话 {row.get('session_id')}",
                f"状态 {row.get('status')}，阶段 {row.get('phase')}",
            ))
        for row in discovery.get("profile_updates", [])[:12]:
            events.append((
                str(row.get("created_at") or ""),
                f"资料更新请求 {row.get('request_id')}",
                f"状态 {row.get('status')}，证据 {_truncate(row.get('evidence_text') or '无')}",
            ))
        for row in discovery.get("rejection_feedbacks", [])[:12]:
            events.append((
                str(row.get("created_at") or ""),
                f"拒绝反馈 #{row.get('feedback_id')}",
                f"{row.get('feedback_type')} / {_truncate(row.get('feedback_text') or row.get('feedback_detail') or '')}",
            ))
        for row in discovery.get("search_runs", [])[:12]:
            events.append((
                str(row.get("created_at") or ""),
                f"搜索执行 #{row.get('search_run_id')}",
                f"结果 {row.get('result_count')}，是否命中 {row.get('has_match')}",
            ))
        events.sort(key=lambda item: item[0], reverse=True)
        return self._md_events(events[:24])

    def _md_chat_timeline(self, chat_block: dict[str, Any]) -> list[str]:
        events: list[tuple[str, str, str]] = []
        for row in chat_block.get("threads", [])[:10]:
            events.append((
                str(row.get("updated_at") or row.get("created_at") or ""),
                f"聊天线程 {row.get('thread_id')}",
                f"状态 {row.get('status')}，对方 {row.get('participant_b_id') if str(row.get('participant_a_id')) == str(self.ctx.user_id) else row.get('participant_a_id')}",
            ))
        for row in chat_block.get("messages", [])[:24]:
            body = _truncate(row.get("body") or "", 100)
            prefix = "用户发言" if str(row.get("author_id")) == str(self.ctx.user_id) else "对方/系统发言"
            events.append((
                str(row.get("created_at") or ""),
                prefix,
                body,
            ))
        for row in chat_block.get("risk_cases", [])[:10]:
            events.append((
                str(row.get("updated_at") or row.get("created_at") or ""),
                f"风控案件 {row.get('risk_case_id')}",
                f"状态 {row.get('status')}，建议动作 {row.get('recommended_action')}",
            ))
        events.sort(key=lambda item: item[0], reverse=True)
        return self._md_events(events[:28])

    def _md_tool_calls(self, discovery: dict[str, Any]) -> list[str]:
        rows = discovery.get("tool_calls") or []
        if not rows:
            return ["- 暂无 tool call 审计记录。"]
        lines: list[str] = []
        for row in rows[:20]:
            args_text = _truncate(json.dumps(_safe_json_loads(row.get("tool_args_json"), row.get("tool_args_json")), ensure_ascii=False), 90)
            result_text = _truncate(json.dumps(_safe_json_loads(row.get("tool_result_json"), row.get("tool_result_json")), ensure_ascii=False), 90)
            lines.append(
                f"- `{_pretty_time(row.get('created_at'))}` | `{row.get('tool_name')}` | `{row.get('status')}` | 参数: {args_text} | 结果: {result_text}"
            )
        return lines

    def _md_ledger(self, ledger_block: dict[str, Any]) -> list[str]:
        relations = ledger_block.get("relations") or []
        if not relations:
            return ["- 没有查到 relationship ledger 关系。"]
        chunks: list[str] = []
        for item in relations[:6]:
            relation = item.get("relation") or {}
            summary = item.get("summary") or {}
            timeline = item.get("timeline") or []
            chunks.append(
                f"- relation_key: `{relation.get('relation_key')}` | current_phase: `{summary.get('current_phase') or relation.get('current_phase')}` | event_count: `{summary.get('event_count')}`"
            )
            timeline_lines = self._md_events(
                [
                    (
                        str(event.get("occurred_at") or event.get("created_at") or ""),
                        str(event.get("title") or event.get("event_type") or "事件"),
                        _truncate(event.get("description") or event.get("summary") or event.get("detail") or event, 140),
                    )
                    for event in timeline[:8]
                ]
            )
            chunks.extend([f"  {line}" for line in timeline_lines])
        return chunks

    def _md_matchmaking_and_recommendation(
        self,
        matchmaking: dict[str, Any],
        recommendation: dict[str, Any],
    ) -> list[str]:
        facts = [
            ("匹配池成员", len(matchmaking.get("members", []) or [])),
            ("匹配边", len(matchmaking.get("edges", []) or [])),
            ("匹配案例", len(matchmaking.get("match_cases", []) or [])),
            ("代理牵线", len(matchmaking.get("proxy_cases", []) or [])),
            ("推荐订阅", len(recommendation.get("recommendation_subscriptions", []) or [])),
            ("推荐结果", len(recommendation.get("recommendation_results", []) or [])),
            ("推荐动作", len(recommendation.get("recommendation_actions", []) or [])),
        ]
        lines = [f"- {label}: `{value}`" for label, value in facts]
        if matchmaking.get("match_cases"):
            lines.append("- 关键案例:")
            for row in (matchmaking.get("match_cases") or [])[:8]:
                lines.append(f"  - `{row.get('case_id')}`: `{row.get('status') or row.get('case_status')}`")
        else:
            lines.append("- 关键案例: `暂无案例`")
        return lines

    def _raw_samples(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "profile": payload.get("profile"),
            "latest_discovery_session": (payload.get("discovery", {}).get("sessions") or [None])[0],
            "latest_chat_thread": (payload.get("chat", {}).get("threads") or [None])[0],
            "latest_match_case": (payload.get("matchmaking", {}).get("match_cases") or [None])[0],
        }

    def _md_events(self, events: list[tuple[str, str, str]]) -> list[str]:
        if not events:
            return ["- 暂无记录。"]
        return [f"- `{_pretty_time(time_text)}` | {title} | {desc}" for time_text, title, desc in events]

    def _md_bullets(self, items: list[str]) -> list[str]:
        if not items:
            return ["- 暂无。"]
        return [f"- {item}" for item in items]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a consolidated Markdown audit report for one user.")
    parser.add_argument("user_id", nargs="?", type=int, help="Target user/profile id; omit to auto-detect")
    parser.add_argument("--source", default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE"), help="Profile/persona source DSN")
    parser.add_argument("--profile-table", default=os.environ.get("PERSONA_PROFILE_TABLE", "profiles"), help="Profile table name")
    parser.add_argument(
        "--output",
        default=None,
        help="Output markdown path; default: artifacts/user-audit-report-<user_id>.md",
    )
    parser.add_argument("--chat-dsn", default=DEFAULT_CHAT_MYSQL_DSN)
    parser.add_argument("--discovery-dsn", default=DEFAULT_DISCOVERY_MYSQL_DSN)
    parser.add_argument("--matchmaking-dsn", default=DEFAULT_MATCHMAKING_MYSQL_DSN)
    parser.add_argument("--recommendation-dsn", default=DEFAULT_RECOMMENDATION_MYSQL_DSN)
    parser.add_argument("--ledger-dsn", default=DEFAULT_RELATION_LEDGER_MYSQL_DSN)
    parser.add_argument("--persona-dsn", default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE"))
    return parser.parse_args()


def resolve_default_user_id(chat_dsn: str, discovery_dsn: str) -> int:
    attempts = [
        (
            discovery_dsn,
            "Discovery",
            "SELECT requester_id, MAX(updated_at) AS latest_at, COUNT(*) AS session_count FROM discovery_agent_sessions GROUP BY requester_id ORDER BY latest_at DESC, session_count DESC LIMIT 1",
            "requester_id",
        ),
        (
            chat_dsn,
            "Chat",
            "SELECT author_id AS user_id, MAX(created_at) AS latest_at, COUNT(*) AS message_count FROM chat_messages GROUP BY author_id ORDER BY latest_at DESC, message_count DESC LIMIT 1",
            "user_id",
        ),
    ]
    for dsn, subsystem_name, sql, key in attempts:
        try:
            conn = connect_mysql_repo_db(dsn, subsystem_name=subsystem_name)
            try:
                row = _query_one(conn, sql)
            finally:
                conn.close()
            if row and row.get(key) not in (None, ""):
                return int(row[key])
        except Exception:
            continue
    raise ValueError("unable to auto-detect a user_id; please pass one explicitly")


def main() -> int:
    _load_dotenv()
    args = parse_args()
    user_id = int(args.user_id) if args.user_id is not None else resolve_default_user_id(args.chat_dsn, args.discovery_dsn)
    output = Path(args.output) if args.output else REPO_ROOT / "artifacts" / f"user-audit-report-{user_id}.md"
    output.parent.mkdir(parents=True, exist_ok=True)
    ctx = ReportContext(
        user_id=user_id,
        source=args.source,
        profile_table=args.profile_table,
        output=output,
        chat_dsn=args.chat_dsn,
        discovery_dsn=args.discovery_dsn,
        matchmaking_dsn=args.matchmaking_dsn,
        recommendation_dsn=args.recommendation_dsn,
        ledger_dsn=args.ledger_dsn,
        persona_dsn=args.persona_dsn,
    )
    report = UserAuditReportBuilder(ctx).build()
    output.write_text(report, encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
