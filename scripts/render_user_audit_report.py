#!/usr/bin/env python3
"""Render a readable HTML audit report for one user across subsystems."""

from __future__ import annotations

import argparse
import html
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


def _html(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return html.escape(json.dumps(value, ensure_ascii=False, indent=2))
    return html.escape(str(value))


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
        return self._render_html(payload)

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

    def _render_html(self, payload: dict[str, Any]) -> str:
        overview_cards = [
            ("用户ID", self.ctx.user_id),
            ("发现会话", len(payload.get("discovery", {}).get("sessions", []) or [])),
            ("聊天线程", len(payload.get("chat", {}).get("threads", []) or [])),
            ("匹配案例", len(payload.get("matchmaking", {}).get("match_cases", []) or [])),
            ("关系链路", len(payload.get("ledger", {}).get("relations", []) or [])),
        ]
        narrative = self._build_narrative(payload)

        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>用户全景审计报告 #{self.ctx.user_id}</title>
  <style>
    :root {{
      --bg: #f4efe7;
      --paper: #fffdf8;
      --ink: #1f2933;
      --muted: #6b7280;
      --line: #e7dccb;
      --accent: #a64b2a;
      --accent-soft: #f4d6c8;
      --chip: #f6efe4;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans SC", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(166,75,42,.10), transparent 24rem),
        linear-gradient(180deg, #f9f5ee 0%, var(--bg) 100%);
      color: var(--ink);
    }}
    .wrap {{
      width: min(1280px, calc(100vw - 32px));
      margin: 24px auto 64px;
    }}
    .hero, .section {{
      background: rgba(255,253,248,.92);
      backdrop-filter: blur(10px);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 24px;
      box-shadow: 0 20px 60px rgba(80,55,35,.08);
    }}
    .hero {{
      margin-bottom: 20px;
    }}
    .hero h1 {{
      margin: 0 0 8px;
      font-size: 34px;
      line-height: 1.1;
    }}
    .hero p {{
      margin: 0;
      color: var(--muted);
      font-size: 15px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-top: 20px;
    }}
    .card {{
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 16px;
    }}
    .card .label {{
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 8px;
    }}
    .card .value {{
      font-size: 26px;
      font-weight: 700;
    }}
    .stack {{
      display: grid;
      gap: 18px;
    }}
    .section h2 {{
      margin: 0 0 12px;
      font-size: 22px;
    }}
    .section h3 {{
      margin: 20px 0 10px;
      font-size: 16px;
    }}
    .two {{
      display: grid;
      gap: 18px;
      grid-template-columns: 1.15fr .85fr;
    }}
    .facts {{
      display: grid;
      gap: 10px;
    }}
    .fact {{
      border-bottom: 1px dashed var(--line);
      padding-bottom: 10px;
    }}
    .fact:last-child {{
      border-bottom: 0;
      padding-bottom: 0;
    }}
    .fact strong {{
      display: inline-block;
      min-width: 108px;
      color: var(--muted);
      font-weight: 600;
    }}
    .timeline {{
      display: grid;
      gap: 12px;
    }}
    .event {{
      position: relative;
      padding: 14px 14px 14px 18px;
      border-left: 4px solid var(--accent);
      background: linear-gradient(180deg, rgba(244,214,200,.35), rgba(255,255,255,.6));
      border-radius: 14px;
    }}
    .event .time {{
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .event .title {{
      font-weight: 700;
      margin-bottom: 6px;
    }}
    .event .desc {{
      color: #334155;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .chip {{
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--chip);
      border: 1px solid var(--line);
      font-size: 12px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      padding: 10px 8px;
    }}
    th {{
      color: var(--muted);
      font-weight: 600;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-size: 12px;
      line-height: 1.45;
      background: #fbf7f1;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
    }}
    .muted {{ color: var(--muted); }}
    .warning {{
      padding: 12px 14px;
      border-radius: 14px;
      background: #fff0eb;
      border: 1px solid #efc3b4;
      color: #7c2d12;
      font-size: 13px;
    }}
    @media (max-width: 900px) {{
      .two {{ grid-template-columns: 1fr; }}
      .wrap {{ width: min(100vw - 20px, 1280px); }}
      .hero, .section {{ padding: 18px; border-radius: 18px; }}
      .hero h1 {{ font-size: 28px; }}
    }}
  </style>
</head>
<body>
  <div class="wrap stack">
    <section class="hero">
      <h1>用户全景审计报告</h1>
      <p>把这个用户在系统里“是谁、做过什么、系统怎么响应、数据库留下了什么痕迹”整理成一页。</p>
      <div class="grid">
        {''.join(f'<div class="card"><div class="label">{_html(label)}</div><div class="value">{_html(value)}</div></div>' for label, value in overview_cards)}
      </div>
    </section>

    {self._render_warnings()}

    <section class="section">
      <h2>一句话看懂这个用户</h2>
      <div class="two">
        <div class="card">
          <h3>当前状态</h3>
          {self._render_bullets(narrative["status"])}
        </div>
        <div class="card">
          <h3>值得关注</h3>
          {self._render_bullets(narrative["attention"])}
        </div>
      </div>
      <div class="two" style="margin-top:18px">
        <div class="card">
          <h3>最近在发生什么</h3>
          {self._render_bullets(narrative["recent"])}
        </div>
        <div class="card">
          <h3>系统为什么这么处理</h3>
          {self._render_bullets(narrative["system"])}
        </div>
      </div>
    </section>

    <section class="section">
      <h2>用户是谁</h2>
      <div class="two">
        <div class="card">
          <h3>账号与基础信息</h3>
          {self._render_account_facts(payload.get("user_account", {}), payload.get("profile", {}), payload.get("onboarding", {}))}
        </div>
        <div class="card">
          <h3>人格/偏好摘要</h3>
          {self._render_persona_summary(payload.get("persona", {}))}
        </div>
      </div>
    </section>

    <section class="section">
      <h2>用户做过什么</h2>
      <div class="two">
        <div class="card">
          <h3>Discovery 过程</h3>
          {self._render_discovery_timeline(payload.get("discovery", {}))}
        </div>
        <div class="card">
          <h3>聊天与互动</h3>
          {self._render_chat_timeline(payload.get("chat", {}))}
        </div>
      </div>
    </section>

    <section class="section">
      <h2>系统怎么执行的</h2>
      <div class="two">
        <div class="card">
          <h3>工具调用与系统决策</h3>
          {self._render_tool_calls(payload.get("discovery", {}))}
        </div>
        <div class="card">
          <h3>关系链路与统一时间线</h3>
          {self._render_ledger(payload.get("ledger", {}))}
        </div>
      </div>
    </section>

    <section class="section">
      <h2>数据库里存了什么</h2>
      <div class="two">
        <div class="card">
          <h3>Matchmaking / Recommendation</h3>
          {self._render_matchmaking_and_recommendation(payload.get("matchmaking", {}), payload.get("recommendation", {}))}
        </div>
        <div class="card">
          <h3>原始数据样本</h3>
          {self._render_raw_samples(payload)}
        </div>
      </div>
    </section>
  </div>
</body>
</html>"""

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

    def _render_warnings(self) -> str:
        if not self.warnings:
            return ""
        return (
            '<section class="section"><h2>读取提醒</h2>'
            + "".join(f'<div class="warning">{_html(item)}</div>' for item in self.warnings)
            + "</section>"
        )

    def _render_account_facts(
        self,
        account_block: dict[str, Any],
        profile_block: dict[str, Any],
        onboarding_block: dict[str, Any],
    ) -> str:
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
        rendered = "".join(
            f'<div class="fact"><strong>{_html(label)}</strong><span>{_html(value or "暂无")}</span></div>'
            for label, value in facts
        )
        identities = account_block.get("identities") or []
        chips = "".join(
            f'<span class="chip">{_html(row.get("identity_type"))}: {_html(row.get("identity_value"))}</span>'
            for row in identities[:10]
        ) or '<span class="muted">没有读到账号绑定标识</span>'
        return f'<div class="facts">{rendered}</div><h3>账号绑定</h3><div class="chips">{chips}</div>'

    def _render_persona_summary(self, persona_block: dict[str, Any]) -> str:
        latest = persona_block.get("latest_summary_by_key") or {}
        meta = persona_block.get("summary_meta") or {}
        if not latest:
            return '<p class="muted">暂无 conversation_summaries 数据。</p>'
        rows = "".join(
            f'<div class="fact"><strong>{_html(key)}</strong><span>{_html(value)}</span></div>'
            for key, value in latest.items()
        )
        return (
            f'<div class="chips"><span class="chip">已加载字段 {len(latest)}</span>'
            f'<span class="chip">完整度 {_html(meta.get("completeness"))}</span></div>'
            f'<div class="facts" style="margin-top:12px">{rows}</div>'
        )

    def _render_discovery_timeline(self, discovery: dict[str, Any]) -> str:
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
        return self._render_events(events[:24])

    def _render_chat_timeline(self, chat_block: dict[str, Any]) -> str:
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
        return self._render_events(events[:28])

    def _render_tool_calls(self, discovery: dict[str, Any]) -> str:
        rows = discovery.get("tool_calls") or []
        if not rows:
            return '<p class="muted">暂无 tool call 审计记录。</p>'
        table_rows = []
        for row in rows[:20]:
            args_text = _truncate(json.dumps(_safe_json_loads(row.get("tool_args_json"), row.get("tool_args_json")), ensure_ascii=False), 90)
            result_text = _truncate(json.dumps(_safe_json_loads(row.get("tool_result_json"), row.get("tool_result_json")), ensure_ascii=False), 90)
            table_rows.append(
                "<tr>"
                f"<td>{_html(_pretty_time(row.get('created_at')))}</td>"
                f"<td>{_html(row.get('tool_name'))}</td>"
                f"<td>{_html(row.get('status'))}</td>"
                f"<td>{_html(args_text)}</td>"
                f"<td>{_html(result_text)}</td>"
                "</tr>"
            )
        return (
            "<table><thead><tr><th>时间</th><th>工具</th><th>状态</th><th>参数</th><th>结果摘要</th></tr></thead>"
            f"<tbody>{''.join(table_rows)}</tbody></table>"
        )

    def _render_ledger(self, ledger_block: dict[str, Any]) -> str:
        relations = ledger_block.get("relations") or []
        if not relations:
            return '<p class="muted">没有查到 relationship ledger 关系。</p>'
        chunks: list[str] = []
        for item in relations[:6]:
            relation = item.get("relation") or {}
            summary = item.get("summary") or {}
            timeline = item.get("timeline") or []
            timeline_html = self._render_events(
                [
                    (
                        str(event.get("occurred_at") or event.get("created_at") or ""),
                        str(event.get("title") or event.get("event_type") or "事件"),
                        _truncate(event.get("description") or event.get("summary") or event.get("detail") or event, 140),
                    )
                    for event in timeline[:8]
                ]
            )
            chunks.append(
                '<div class="card" style="margin-bottom:12px">'
                f"<div class='chips'><span class='chip'>{_html(relation.get('relation_key'))}</span>"
                f"<span class='chip'>阶段 {_html(summary.get('current_phase') or relation.get('current_phase'))}</span>"
                f"<span class='chip'>事件数 {_html(summary.get('event_count'))}</span></div>"
                f"<div style='margin-top:12px'>{timeline_html}</div></div>"
            )
        return "".join(chunks)

    def _render_matchmaking_and_recommendation(
        self,
        matchmaking: dict[str, Any],
        recommendation: dict[str, Any],
    ) -> str:
        facts = [
            ("匹配池成员", len(matchmaking.get("members", []) or [])),
            ("匹配边", len(matchmaking.get("edges", []) or [])),
            ("匹配案例", len(matchmaking.get("match_cases", []) or [])),
            ("代理牵线", len(matchmaking.get("proxy_cases", []) or [])),
            ("推荐订阅", len(recommendation.get("recommendation_subscriptions", []) or [])),
            ("推荐结果", len(recommendation.get("recommendation_results", []) or [])),
            ("推荐动作", len(recommendation.get("recommendation_actions", []) or [])),
        ]
        rendered = "".join(
            f'<div class="fact"><strong>{_html(label)}</strong><span>{_html(value)}</span></div>'
            for label, value in facts
        )
        case_preview = "".join(
            f'<span class="chip">{_html(row.get("case_id"))}: {_html(row.get("status") or row.get("case_status"))}</span>'
            for row in (matchmaking.get("match_cases") or [])[:8]
        ) or '<span class="muted">暂无案例</span>'
        return f'<div class="facts">{rendered}</div><h3>关键案例</h3><div class="chips">{case_preview}</div>'

    def _render_raw_samples(self, payload: dict[str, Any]) -> str:
        sample = {
            "profile": payload.get("profile"),
            "latest_discovery_session": (payload.get("discovery", {}).get("sessions") or [None])[0],
            "latest_chat_thread": (payload.get("chat", {}).get("threads") or [None])[0],
            "latest_match_case": (payload.get("matchmaking", {}).get("match_cases") or [None])[0],
        }
        return f"<pre>{_html(sample)}</pre>"

    def _render_events(self, events: list[tuple[str, str, str]]) -> str:
        if not events:
            return '<p class="muted">暂无记录。</p>'
        return '<div class="timeline">' + "".join(
            f'<div class="event"><div class="time">{_html(_pretty_time(time_text))}</div>'
            f'<div class="title">{_html(title)}</div><div class="desc">{_html(desc)}</div></div>'
            for time_text, title, desc in events
        ) + "</div>"

    def _render_bullets(self, items: list[str]) -> str:
        if not items:
            return '<p class="muted">暂无。</p>'
        return "<div class='facts'>" + "".join(
            f"<div class='fact'>{_html(item)}</div>" for item in items
        ) + "</div>"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a readable HTML audit report for one user.")
    parser.add_argument("user_id", type=int, help="Target user/profile id")
    parser.add_argument("--source", default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE"), help="Profile/persona source DSN")
    parser.add_argument("--profile-table", default=os.environ.get("PERSONA_PROFILE_TABLE", "profiles"), help="Profile table name")
    parser.add_argument(
        "--output",
        default=None,
        help="Output html path; default: artifacts/user-audit-report-<user_id>.html",
    )
    parser.add_argument("--chat-dsn", default=DEFAULT_CHAT_MYSQL_DSN)
    parser.add_argument("--discovery-dsn", default=DEFAULT_DISCOVERY_MYSQL_DSN)
    parser.add_argument("--matchmaking-dsn", default=DEFAULT_MATCHMAKING_MYSQL_DSN)
    parser.add_argument("--recommendation-dsn", default=DEFAULT_RECOMMENDATION_MYSQL_DSN)
    parser.add_argument("--ledger-dsn", default=DEFAULT_RELATION_LEDGER_MYSQL_DSN)
    parser.add_argument("--persona-dsn", default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE"))
    return parser.parse_args()


def main() -> int:
    _load_dotenv()
    args = parse_args()
    output = Path(args.output) if args.output else REPO_ROOT / "artifacts" / f"user-audit-report-{args.user_id}.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    ctx = ReportContext(
        user_id=int(args.user_id),
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
