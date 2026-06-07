#!/usr/bin/env python3
"""Reproducible perf benchmarks for the 2026-06 backend optimizations."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import statistics
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GATEWAY_ROOT = REPO_ROOT / "external-systems" / "partner-http-gateway"
CHAT_ROOT = REPO_ROOT / "external-systems" / "partner-chat-system"
RECOMMENDATION_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"
DISCOVERY_ROOT = REPO_ROOT / "external-systems" / "partner-discovery-system"
MATCHMAKING_ROOT = REPO_ROOT / "external-systems" / "partner-matchmaking-system"

for root in (REPO_ROOT, GATEWAY_ROOT, CHAT_ROOT, RECOMMENDATION_ROOT, DISCOVERY_ROOT, MATCHMAKING_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from outer_mysql_compat import MySQLCompatConnection, _CursorResult  # noqa: E402
from partner_search.search_cache import clear_search_cache  # noqa: E402
from partner_search.search_snapshot_store import clear_persisted_search_runs  # noqa: E402
import partner_search.api as partner_search_api  # noqa: E402
import partner_search.search_candidates as search_engine  # noqa: E402
from partner_search.search_sources import build_mysql_prefilter  # noqa: E402
from profile_service import iter_profile_batches  # noqa: E402
from gateway_tests.helpers import (  # noqa: E402
    ensure_search_schema,
    insert_search_profiles,
    open_search_conn,
    reset_search_rows,
    search_test_config,
)
from chat_system import (  # noqa: E402
    build_case_conversation_timeline,
    build_user_trust_hub,
    create_assistant_case_layout,
    get_or_create_thread,
)
import chat_system.self_service as self_service_module  # noqa: E402
import chat_system.verification as verification_module  # noqa: E402
import chat_system.profile_reviews as profile_reviews_module  # noqa: E402
from chat_system.assistant_sessions import (  # noqa: E402
    SESSION_STATUS_OPEN,
    TASK_REASON_OPENING_PROBE,
    TASK_STATUS_PENDING,
    TASK_STATUS_RUNNING,
    _case_has_any_messages,
    _inflate_session,
    _latest_main_group_message,
    _session_has_pending_tasks,
    enqueue_agent_task,
    enqueue_due_opening_probe_tasks,
    get_or_create_agent_session,
)
from chat_system.conversations import (  # noqa: E402
    CONV_KIND_DM,
    CONV_KIND_GROUP,
    ROLE_AGENT,
    ROLE_HUMAN,
    get_conversation_by_case_and_key,
    get_conversation_member,
    _inflate_conversation,
    _inflate_message,
    list_case_conversations,
    list_conversation_members,
)
from chat_system.storage import (  # noqa: E402
    DEFAULT_CHAT_TEST_MYSQL_DSN,
    connect_db as connect_chat_db,
    initialize_database as initialize_chat_db,
    reset_all_tables as reset_chat_tables,
    row_to_dict,
)
from recommendation_system import (  # noqa: E402
    create_subscription,
    list_recommendations_for_subscription,
)
from recommendation_system.recommendation_rows import (  # noqa: E402
    _merge_recommendation_subscription_fields,
    inflate_recommendation as inflate_recommendation_row,
    list_recommendation_actions_for_recommendation,
)
from recommendation_system.storage import (  # noqa: E402
    DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN,
    connect_db as connect_recommendation_db,
    initialize_database as initialize_recommendation_db,
    reset_all_tables as reset_recommendation_tables,
)
from discovery_system.storage import StoredSession  # noqa: E402
import discovery_system.service_integrations as discovery_integrations  # noqa: E402
from matchmaking_system import (  # noqa: E402
    build_mutual_pairs,
    create_pool_member,
    refresh_active_pool,
)
import matchmaking_system.pairs as matchmaking_pairs_module  # noqa: E402
from matchmaking_system.storage import (  # noqa: E402
    DEFAULT_MATCHMAKING_TEST_MYSQL_DSN,
    connect_db as connect_matchmaking_db,
    initialize_database as initialize_matchmaking_db,
    reset_all_tables as reset_matchmaking_tables,
)
from relationship_ledger.storage import (  # noqa: E402
    DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN,
    connect_db as connect_ledger_db,
    initialize_database as initialize_ledger_db,
    reset_all_tables as reset_ledger_tables,
)

DEFAULT_SEARCH_DSN = os.environ.get(
    "PARTNER_SEARCH_BENCHMARK_DB",
    "mysql://root@127.0.0.1:3307/her_partner_search_benchmark?table=profiles&photos_table=profile_photos",
)
SEARCH_FILLER_COLUMN_COUNT = 32
SEARCH_FILLER_DEFAULT = "perf-benchmark-filler-value" * 4


@dataclass
class QueryStats:
    execute_count: int = 0
    fetched_cells: int = 0


@dataclass
class RunResult:
    elapsed_ms: float
    execute_count: int
    fetched_cells: int


@dataclass
class BenchmarkSummary:
    label: str
    runs: list[RunResult]
    result_count: int

    @property
    def avg_ms(self) -> float:
        return statistics.fmean(item.elapsed_ms for item in self.runs)

    @property
    def min_ms(self) -> float:
        return min(item.elapsed_ms for item in self.runs)

    @property
    def max_ms(self) -> float:
        return max(item.elapsed_ms for item in self.runs)

    @property
    def avg_executes(self) -> float:
        return statistics.fmean(item.execute_count for item in self.runs)

    @property
    def avg_cells(self) -> float:
        return statistics.fmean(item.fetched_cells for item in self.runs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "result_count": self.result_count,
            "avg_ms": round(self.avg_ms, 3),
            "min_ms": round(self.min_ms, 3),
            "max_ms": round(self.max_ms, 3),
            "avg_execute_count": round(self.avg_executes, 3),
            "avg_fetched_cells": round(self.avg_cells, 3),
            "runs": [
                {
                    "elapsed_ms": round(item.elapsed_ms, 3),
                    "execute_count": item.execute_count,
                    "fetched_cells": item.fetched_cells,
                }
                for item in self.runs
            ],
        }


@contextmanager
def query_counter() -> Iterable[QueryStats]:
    stats = QueryStats()
    original_execute = MySQLCompatConnection.execute
    original_fetchall = _CursorResult.fetchall
    original_fetchone = _CursorResult.fetchone

    def counted_execute(self: MySQLCompatConnection, sql: str, parameters: Iterable[Any] | None = None):
        stats.execute_count += 1
        return original_execute(self, sql, parameters)

    def counted_fetchall(self: _CursorResult):
        rows = original_fetchall(self)
        stats.fetched_cells += sum(len(row) if isinstance(row, dict) else 1 for row in (rows or []))
        return rows

    def counted_fetchone(self: _CursorResult):
        row = original_fetchone(self)
        if row is not None:
            stats.fetched_cells += len(row) if isinstance(row, dict) else 1
        return row

    MySQLCompatConnection.execute = counted_execute  # type: ignore[assignment]
    _CursorResult.fetchall = counted_fetchall  # type: ignore[assignment]
    _CursorResult.fetchone = counted_fetchone  # type: ignore[assignment]
    try:
        yield stats
    finally:
        MySQLCompatConnection.execute = original_execute  # type: ignore[assignment]
        _CursorResult.fetchall = original_fetchall  # type: ignore[assignment]
        _CursorResult.fetchone = original_fetchone  # type: ignore[assignment]


def _disable_search_cache() -> None:
    os.environ["PARTNER_SEARCH_CACHE_TTL_SECONDS"] = "0"
    os.environ["PARTNER_SEARCH_SNAPSHOT_PERSIST"] = "0"
    clear_search_cache()
    clear_persisted_search_runs()


def _build_search_rows(total_profiles: int) -> list[tuple[Any, ...]]:
    base_time = datetime(2026, 6, 1, 12, 0, 0)
    rows: list[tuple[Any, ...]] = []
    for index in range(total_profiles):
        profile_id = 100000 + index
        city = "上海" if index % 3 else "无锡"
        rows.append(
            (
                profile_id,
                f"候选人{index}",
                "女" if index % 5 else "男",
                24 + (index % 10),
                city,
                "本科" if index % 4 else "硕士",
                "产品经理" if index % 7 else "行政助理",
                "20-30万/年" if index % 6 else "80-120万/年",
                "未婚",
                0,
                "认真恋爱" if index % 2 else "结婚导向",
                "active",
                "basic" if index % 8 else "id",
                "uploaded",
                "self_reported",
                "self_reported",
                "self_reported",
                "approved",
                index % 3,
                3 + (index % 5),
                "生活规律",
                "主动沟通",
                "情绪稳定，愿意沟通，认真长期关系",
                f"基准测试资料 {index}",
                base_time - timedelta(minutes=index % 240),
            )
        )
    return rows


def _prepare_search_db(total_profiles: int) -> str:
    search_config = search_test_config(DEFAULT_SEARCH_DSN)
    ensure_search_schema(search_config)
    conn = open_search_conn(search_config)
    try:
        with conn.cursor() as cursor:
            for index in range(SEARCH_FILLER_COLUMN_COUNT):
                column_name = f"perf_filler_{index:02d}"
                cursor.execute(
                    f"ALTER TABLE `profiles` ADD COLUMN `{column_name}` VARCHAR(255) NOT NULL DEFAULT %s",
                    (SEARCH_FILLER_DEFAULT,),
                )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()
    reset_search_rows(search_config)
    rows = _build_search_rows(total_profiles)
    chunk_size = 1000
    for offset in range(0, len(rows), chunk_size):
        insert_search_profiles(search_config, rows[offset : offset + chunk_size])
    return DEFAULT_SEARCH_DSN


def _legacy_load_mysql_records(
    *,
    source: str,
    table_name: str | None,
    criteria: dict[str, Any],
    include_ids: list[Any] | None = None,
) -> list[dict[str, Any]]:
    runtime = search_engine._build_search_source_runtime()
    config = search_engine.parse_mysql_source(source, table_name=table_name)
    normalized_source, normalized_table = search_engine.resolve_profile_source(source, config.get("table"))
    effective_source = normalized_source or str(source)
    table = normalized_table or search_engine.detect_profile_table(source_dsn=effective_source)
    if not table:
        raise ValueError("Could not detect a candidate table in benchmark source")

    canonical_to_actual: dict[str, str] = {}
    for actual in runtime.list_profile_columns(source_dsn=effective_source, source_table_name=table):
        canonical = runtime.alias_lookup.get(runtime.normalize_key(actual), runtime.normalize_key(actual))
        canonical_to_actual.setdefault(canonical, actual)

    prefilter = build_mysql_prefilter(
        runtime,
        criteria,
        canonical_to_actual,
        include_ids=include_ids,
        include_ids_mode="or",
    )
    where_clause, params = prefilter or ("", [])
    normalized_where = where_clause.replace("%s", "?")

    rows: list[dict[str, Any]] = []
    for batch in iter_profile_batches(
        source_dsn=effective_source,
        source_table_name=table,
        where_clause=normalized_where,
        params=params,
        selected_columns=None,
        batch_size=500,
    ):
        rows.extend(batch)

    try:
        from match_domain.persona_loader import load_personas_by_profile_ids
    except Exception:  # noqa: BLE001
        load_personas_by_profile_ids = None  # type: ignore[assignment]

    try:
        from match_domain.reciprocal_preferences import merge_persona_into_profile_record
    except Exception:  # noqa: BLE001
        merge_persona_into_profile_record = None  # type: ignore[assignment]

    profile_ids = [int(row["id"]) for row in rows if row.get("id") is not None]
    personas_by_profile: dict[int, dict[str, Any]] = {}
    if profile_ids and load_personas_by_profile_ids is not None:
        try:
            personas_by_profile = load_personas_by_profile_ids(source=effective_source, profile_ids=profile_ids)
        except Exception:  # noqa: BLE001
            personas_by_profile = {}

    source_file_ref = search_engine.build_source_file_ref(effective_source, table)
    records: list[dict[str, Any]] = []
    for row in rows:
        row_dict = dict(row)
        profile_id = int(row_dict["id"]) if row_dict.get("id") is not None else None
        persona_row = personas_by_profile.get(profile_id) if profile_id is not None else None
        if persona_row is not None and merge_persona_into_profile_record is not None:
            row_dict = merge_persona_into_profile_record(row_dict, persona_row)
        records.append(search_engine.normalize_record({**row_dict, "source_file": source_file_ref}))
    return records


def _legacy_execute_partner_search(
    *,
    source: str,
    criteria: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    request = search_engine.build_search_request(
        source=source,
        criteria=criteria,
        limit=limit,
        photo_preview_count=0,
    )
    normalized_criteria = search_engine.normalize_request_criteria(request.get("criteria"))
    sources = search_engine.resolve_request_sources(request)
    records = _legacy_load_mysql_records(
        source=sources[0],
        table_name=request.get("table_name"),
        criteria=normalized_criteria,
        include_ids=[],
    )
    search_engine.apply_request_self_profile_context(request, normalized_criteria, records)
    results = search_engine.evaluate_records(records, normalized_criteria, limit)
    search_run = search_engine.build_search_run(normalized_criteria, records, results)
    if results:
        search_run["records"] = []
    return search_engine.populate_no_match_details(search_run, argparse.Namespace(limit=limit))


def benchmark_partner_search(total_profiles: int, repeat: int) -> dict[str, Any]:
    source = _prepare_search_db(total_profiles)
    _disable_search_cache()
    criteria = {
        "gender": "女",
        "cities": ["上海", "无锡"],
        "relationship_goals": ["认真恋爱", "结婚导向"],
        "must_have": ["情绪稳定", "愿意沟通"],
    }

    def current_call() -> dict[str, Any]:
        clear_search_cache()
        return partner_search_api.search_profiles(source=source, criteria=criteria, limit=20)

    def legacy_call() -> dict[str, Any]:
        clear_search_cache()
        return search_engine.build_structured_search_response(
            _legacy_execute_partner_search(source=source, criteria=criteria, limit=20)
        )

    return {
        "scenario": "partner_search_full_scan",
        "current": _run_benchmark("current", current_call, repeat=repeat),
        "legacy_emulation": _run_benchmark("legacy_emulation", legacy_call, repeat=repeat),
    }


def _seed_chat_timeline_db(messages_per_conversation: int) -> str:
    conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
    initialize_chat_db(conn)
    reset_chat_tables(conn)
    layout = create_assistant_case_layout(
        conn,
        case_id="bench-case-1",
        relation_key="bench-rel-1",
        participant_a_id="user-a",
        participant_b_id="user-b",
        agent_id="agent-c",
        now=datetime(2026, 6, 1, 9, 0, 0),
    )
    by_role = {item["metadata"]["layout_role"]: item["conversation_id"] for item in layout["conversations"]}
    rows: list[tuple[Any, ...]] = []
    ts = datetime(2026, 6, 1, 9, 1, 0)
    for offset in range(messages_per_conversation):
        rows.append(
            (
                by_role["main_group"],
                "user-a" if offset % 2 == 0 else "agent-c",
                "user" if offset % 2 == 0 else "agent",
                f"main_group message {offset}",
                None,
                None,
                "{}",
                ts + timedelta(seconds=offset),
            )
        )
        rows.append(
            (
                by_role["assistant_dm_a"],
                "agent-c",
                "agent",
                f"assistant_dm_a message {offset}",
                None,
                None,
                "{}",
                ts + timedelta(seconds=offset),
            )
        )
        rows.append(
            (
                by_role["assistant_dm_b"],
                "agent-c",
                "agent",
                f"assistant_dm_b message {offset}",
                None,
                None,
                "{}",
                ts + timedelta(seconds=offset),
            )
        )
    raw_conn = conn.driver_connection
    with raw_conn.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO chat_conversation_messages (
              conversation_id, author_id, source, body, client_msg_id,
              reply_to_message_id, metadata_json, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
    raw_conn.commit()
    conn.close()
    return "bench-case-1"


def _legacy_list_case_conversations(conn: MySQLCompatConnection, case_id: str, requester_id: str | None = None) -> list[dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT * FROM chat_conversations
        WHERE case_id = ?
        ORDER BY created_at ASC, conversation_id ASC
        """,
        (case_id,),
    )
    conversations = [_inflate_conversation(row_to_dict(row)) for row in cur.fetchall()]
    out: list[dict[str, Any]] = []
    requester = str(requester_id or "").strip()
    for conversation in conversations:
        if not conversation:
            continue
        members = list_conversation_members(conn, str(conversation["conversation_id"]))
        if requester:
            member_map = {str(member["participant_id"]): member for member in members}
            requester_member = member_map.get(requester)
            if not requester_member or not requester_member.get("can_read"):
                continue
        out.append({**conversation, "members": members})
    return sorted(out, key=lambda item: (str((item.get("metadata") or {}).get("layout_role") or ""), str(item.get("conversation_id") or "")))


def _legacy_list_conversation_messages_for_conversations(
    conn: MySQLCompatConnection,
    conversation_ids: Iterable[str],
    requester_id: str,
    *,
    limit: int = 50,
) -> dict[str, list[dict[str, Any]]]:
    normalized_ids = [str(item).strip() for item in conversation_ids if str(item or "").strip()]
    if not normalized_ids:
        return {}
    requester = str(requester_id or "").strip()
    lim = max(1, min(int(limit), 500))
    out: dict[str, list[dict[str, Any]]] = {cid: [] for cid in normalized_ids}
    if not requester:
        return out

    placeholders = ", ".join(["?"] * len(normalized_ids))
    cur = conn.execute(
        f"""
        SELECT conversation_id
        FROM chat_conversation_members
        WHERE conversation_id IN ({placeholders})
          AND participant_id = ?
          AND can_read = 1
        """,
        [*normalized_ids, requester],
    )
    allowed_ids = [str(row["conversation_id"]) for row in cur.fetchall()]
    if not allowed_ids:
        return out

    allowed_placeholders = ", ".join(["?"] * len(allowed_ids))
    cur = conn.execute(
        f"""
        SELECT * FROM chat_conversation_messages
        WHERE conversation_id IN ({allowed_placeholders})
        ORDER BY conversation_id ASC, message_id DESC
        """,
        allowed_ids,
    )
    grouped: dict[str, list[dict[str, Any]]] = {cid: [] for cid in allowed_ids}
    for row in cur.fetchall():
        row_dict = row_to_dict(row)
        message = _inflate_message(row_dict)
        if not message:
            continue
        cid = str(row_dict.get("conversation_id") or "")
        bucket = grouped.get(cid)
        if bucket is None or len(bucket) >= lim:
            continue
        bucket.append(message)
    for cid, messages in grouped.items():
        out[cid] = list(reversed(messages))
    return out


def _legacy_build_case_conversation_timeline(
    conn: MySQLCompatConnection,
    case_id: str,
    requester_id: str,
    *,
    message_limit: int = 50,
) -> dict[str, Any]:
    conversations = _legacy_list_case_conversations(conn, case_id, requester_id=requester_id)
    conversation_ids = [str(conversation["conversation_id"]) for conversation in conversations]
    messages_by_conversation_id = _legacy_list_conversation_messages_for_conversations(
        conn,
        conversation_ids,
        requester_id,
        limit=message_limit,
    )
    out: list[dict[str, Any]] = []
    for conversation in conversations:
        conversation_id = str(conversation["conversation_id"])
        out.append({"conversation": conversation, "messages": messages_by_conversation_id.get(conversation_id, [])})
    return {
        "case_id": case_id,
        "requester_id": requester_id,
        "conversation_count": len(out),
        "conversations": out,
    }


def benchmark_chat_timeline(messages_per_conversation: int, repeat: int) -> dict[str, Any]:
    case_id = _seed_chat_timeline_db(messages_per_conversation)

    def current_call() -> dict[str, Any]:
        conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        try:
            return build_case_conversation_timeline(conn, case_id, "user-a", message_limit=20)
        finally:
            conn.close()

    def legacy_call() -> dict[str, Any]:
        conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        try:
            return _legacy_build_case_conversation_timeline(conn, case_id, "user-a", message_limit=20)
        finally:
            conn.close()

    return {
        "scenario": "chat_case_timeline",
        "current": _run_benchmark("current", current_call, repeat=repeat),
        "legacy_emulation": _run_benchmark("legacy_emulation", legacy_call, repeat=repeat),
    }


def _seed_opening_probe_db(case_count: int) -> None:
    conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
    initialize_chat_db(conn)
    reset_chat_tables(conn)
    base_time = datetime(2026, 6, 1, 8, 0, 0)
    for index in range(case_count):
        create_assistant_case_layout(
            conn,
            case_id=f"bench-opening-{index}",
            relation_key=f"bench-rel-{index}",
            participant_a_id=f"user-a-{index}",
            participant_b_id=f"user-b-{index}",
            agent_id=f"agent-c-{index}",
            now=base_time + timedelta(seconds=index),
        )
    conn.close()


def _legacy_enqueue_due_opening_probe_tasks(
    conn: MySQLCompatConnection,
    *,
    limit: int = 10,
    opening_seconds: int = 30,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = now or datetime.now()
    lim = max(1, min(int(limit), 100))
    cutoff = ts - timedelta(seconds=max(10, int(opening_seconds)))
    cur = conn.execute(
        """
        SELECT
          c.case_id,
          c.conversation_id,
          c.created_at,
          s.session_id,
          s.status AS session_status,
          s.last_user_message_at
        FROM chat_conversations c
        LEFT JOIN chat_agent_sessions s
          ON s.case_id = c.case_id
        WHERE c.channel_key = ?
          AND c.status = ?
          AND c.created_at <= ?
        ORDER BY c.created_at ASC, c.case_id ASC
        LIMIT ?
        """,
        ("main_group", SESSION_STATUS_OPEN, cutoff, max(lim * 5, lim)),
    )
    examined = 0
    enqueued_refs: list[dict[str, Any]] = []
    for raw in cur.fetchall():
        if len(enqueued_refs) >= lim:
            break
        row = row_to_dict(raw)
        if not row:
            continue
        examined += 1
        session_status = str(row.get("session_status") or "").strip()
        if session_status and session_status != SESSION_STATUS_OPEN:
            continue
        if row.get("last_user_message_at") is not None:
            continue
        if row.get("session_id") and _session_has_pending_tasks(conn, str(row["session_id"])):
            continue
        latest_bundle = _latest_main_group_message(conn, str(row["case_id"]))
        if latest_bundle is not None:
            continue
        if _case_has_any_messages(conn, str(row["case_id"])):
            continue
        session = get_or_create_agent_session(
            conn,
            case_id=str(row["case_id"]),
            triggered_by_message_id=None,
            now=ts,
        )
        if _session_has_pending_tasks(conn, str(session["session_id"])):
            continue
        task = enqueue_agent_task(
            conn,
            session_id=str(session["session_id"]),
            case_id=str(row["case_id"]),
            trigger_conversation_id=str(row["conversation_id"]),
            trigger_message_id=0,
            trigger_author_id="",
            trigger_channel_key="main_group",
            reason=TASK_REASON_OPENING_PROBE,
            update_last_user_message_at=False,
            now=ts,
        )
        if task.get("_inserted"):
            enqueued_refs.append(
                {
                    "session_id": str(session["session_id"]),
                    "task_id": int(task["task_id"]),
                    "trigger_message_id": int(task["trigger_message_id"]),
                }
            )
    return {"examined_sessions": examined, "enqueued": len(enqueued_refs), "task_refs": enqueued_refs}


def benchmark_assistant_opening(case_count: int, repeat: int) -> dict[str, Any]:
    def current_call() -> dict[str, Any]:
        _seed_opening_probe_db(case_count)
        conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        try:
            return enqueue_due_opening_probe_tasks(
                conn,
                limit=case_count,
                opening_seconds=30,
                now=datetime(2026, 6, 1, 9, 0, 0),
            )
        finally:
            conn.close()

    def legacy_call() -> dict[str, Any]:
        _seed_opening_probe_db(case_count)
        conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        try:
            return _legacy_enqueue_due_opening_probe_tasks(
                conn,
                limit=case_count,
                opening_seconds=30,
                now=datetime(2026, 6, 1, 9, 0, 0),
            )
        finally:
            conn.close()

    return {
        "scenario": "assistant_opening_probe_scan",
        "current": _run_benchmark("current", current_call, repeat=repeat),
        "legacy_emulation": _run_benchmark("legacy_emulation", legacy_call, repeat=repeat),
    }


def _seed_matchmaking_pairs_db(pair_count: int) -> None:
    os.environ["HER_RELATION_LEDGER_DB"] = DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN
    ledger_conn = connect_ledger_db(DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN)
    initialize_ledger_db(ledger_conn)
    reset_ledger_tables(ledger_conn)
    ledger_conn.close()
    conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
    initialize_matchmaking_db(conn)
    reset_matchmaking_tables(conn)
    source = "mysql://user:pass@127.0.0.1:3306/her?table=profiles"
    base_now = datetime(2026, 6, 1, 9, 0, 0)
    pair_map: dict[int, int] = {}
    for index in range(pair_count):
        left_id = 100000 + index * 2
        right_id = left_id + 1
        pair_map[left_id] = right_id
        pair_map[right_id] = left_id
        create_pool_member(
            conn,
            user_key=f"user-{left_id}",
            source=source,
            self_id=left_id,
            search_criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
            self_profile={"age": 28, "city": "无锡", "height": 175},
            min_pair_score=80,
            limit_count=5,
            refresh_interval_hours=24,
            now=base_now,
        )
        create_pool_member(
            conn,
            user_key=f"user-{right_id}",
            source=source,
            self_id=right_id,
            search_criteria={"gender": "男", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
            self_profile={"age": 27, "city": "无锡", "height": 165},
            min_pair_score=80,
            limit_count=5,
            refresh_interval_hours=24,
            now=base_now,
        )

    def fake_search_runner(**kwargs):
        self_id = int(kwargs.get("self_id") or 0)
        candidate_id = pair_map.get(self_id)
        if candidate_id is None:
            return {"results": []}
        return {
            "results": [
                {
                    "id": candidate_id,
                    "name": f"候选人{candidate_id}",
                    "score": 92 if self_id % 2 == 0 else 91,
                    "fit_score": 86,
                    "confidence_score": 10,
                    "risk_score": 0,
                    "matched_on": ["同城", "目标一致"],
                    "reciprocal_on": ["偏好匹配"],
                    "missing_fields": [],
                    "self_profile_gaps": [],
                    "risk_flags": [],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "photo_preview": [],
                    "source": source,
                    "profile": {"age": 27, "city": "无锡", "job": "产品经理", "relationship_goal": "认真恋爱"},
                }
            ]
        }

    refresh_active_pool(
        conn,
        now=base_now,
        search_runner=fake_search_runner,
    )
    conn.close()


def _legacy_build_mutual_pairs(conn, *, now: datetime | None = None) -> list[dict[str, Any]]:
    now = matchmaking_pairs_module.current_time(now)
    ledger_mirror: list[dict[str, Any]] = []
    edges = matchmaking_pairs_module.list_active_edges(conn)
    edge_by_direction = {
        (edge["owner_member_id"], edge["candidate_member_id"]): edge
        for edge in edges
    }
    processed: set[str] = set()
    updated_pair_keys: list[str] = []

    for (owner_member_id, candidate_member_id), edge_ab in edge_by_direction.items():
        reciprocal_key = (candidate_member_id, owner_member_id)
        if reciprocal_key not in edge_by_direction:
            continue
        pair_key = matchmaking_pairs_module.pair_key_for(owner_member_id, candidate_member_id)
        if pair_key in processed:
            continue
        processed.add(pair_key)
        edge_ba = edge_by_direction[reciprocal_key]
        member_low_id, member_high_id = sorted([owner_member_id, candidate_member_id])
        if member_low_id == owner_member_id:
            low_to_high = edge_ab
            high_to_low = edge_ba
        else:
            low_to_high = edge_ba
            high_to_low = edge_ab

        member_low = matchmaking_pairs_module.get_pool_member(conn, member_low_id)
        member_high = matchmaking_pairs_module.get_pool_member(conn, member_high_id)
        pair_score = min(
            int(low_to_high.get("score") or 0),
            int(high_to_low.get("score") or 0),
        )
        min_required_score = max(
            int(member_low.get("min_pair_score") or 0),
            int(member_high.get("min_pair_score") or 0),
        )
        existing = matchmaking_pairs_module.get_pair(conn, pair_key)
        pair_status, block_reason = matchmaking_pairs_module._evaluate_pair_state(
            conn,
            pair=existing,
            pair_score=pair_score,
            min_required_score=min_required_score,
            member_low=member_low,
            member_high=member_high,
            low_to_high=low_to_high,
            high_to_low=high_to_low,
            now=now,
        )
        cooling_until = existing.get("cooling_until") if existing else None
        latest_payload = {
            "member_low": {"member_id": member_low_id, "user_key": member_low["user_key"]},
            "member_high": {"member_id": member_high_id, "user_key": member_high["user_key"]},
            "low_to_high": low_to_high.get("payload") or {},
            "high_to_low": high_to_low.get("payload") or {},
            "min_required_score": min_required_score,
        }
        if existing:
            conn.execute(
                """
                UPDATE matchmaking_pairs
                SET score_low_to_high = ?,
                    score_high_to_low = ?,
                    pair_score = ?,
                    pair_status = ?,
                    block_reason = ?,
                    latest_payload_json = ?,
                    updated_at = ?
                WHERE pair_key = ?
                """,
                (
                    int(low_to_high.get("score") or 0),
                    int(high_to_low.get("score") or 0),
                    pair_score,
                    pair_status,
                    block_reason,
                    matchmaking_pairs_module.json_dumps(latest_payload),
                    matchmaking_pairs_module.format_dt(now),
                    pair_key,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO matchmaking_pairs (
                  pair_key,
                  member_low_id,
                  member_high_id,
                  score_low_to_high,
                  score_high_to_low,
                  pair_score,
                  pair_status,
                  block_reason,
                  cooling_until,
                  latest_payload_json,
                  created_at,
                  updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pair_key,
                    member_low_id,
                    member_high_id,
                    int(low_to_high.get("score") or 0),
                    int(high_to_low.get("score") or 0),
                    pair_score,
                    pair_status,
                    block_reason,
                    cooling_until,
                    matchmaking_pairs_module.json_dumps(latest_payload),
                    matchmaking_pairs_module.format_dt(now),
                    matchmaking_pairs_module.format_dt(now),
                ),
            )
        updated_pair_keys.append(pair_key)
        pair_row = matchmaking_pairs_module.get_pair(conn, pair_key)
        if pair_row:
            member_low_live = matchmaking_pairs_module.get_pool_member(conn, pair_row["member_low_id"])
            member_high_live = matchmaking_pairs_module.get_pool_member(conn, pair_row["member_high_id"])
            matchmaking_pairs_module._append_pair_event_to_ledger(
                pair_event_type=f"pair_{pair_status}",
                member_low=member_low_live,
                member_high=member_high_live,
                pair_key=pair_key,
                now=now,
                actor_type="system",
                actor_id="system",
                payload={"pair_score": pair_score, "block_reason": block_reason},
                ledger_mirror=ledger_mirror,
            )

    for pair in matchmaking_pairs_module.list_pairs(conn):
        if pair["pair_key"] in processed:
            continue
        if pair["pair_status"] == "mutual_accept":
            continue
        if pair["pair_status"] == "case_opened" and matchmaking_pairs_module._pair_has_open_case(conn, pair["pair_key"]):
            continue

        cooling_until_dt = matchmaking_pairs_module.parse_dt(pair.get("cooling_until"))
        if pair["pair_status"] == "cooling" and cooling_until_dt and now < cooling_until_dt:
            continue

        member_low = matchmaking_pairs_module.get_pool_member(conn, pair["member_low_id"])
        member_high = matchmaking_pairs_module.get_pool_member(conn, pair["member_high_id"])
        if (
            pair["pair_status"] == "needs_revalidation"
            and (member_low.get("needs_refresh") or member_high.get("needs_refresh"))
        ):
            continue

        block_reason = "reciprocal_edge_missing"
        if member_low["status"] != matchmaking_pairs_module.ACTIVE_MEMBER_STATUS or member_high["status"] != matchmaking_pairs_module.ACTIVE_MEMBER_STATUS:
            block_reason = "member_not_active"
        elif not member_low["is_still_searching"] or not member_high["is_still_searching"]:
            block_reason = "member_not_searching"

        matchmaking_pairs_module._update_pair_status(
            conn,
            pair["pair_key"],
            pair_status="stale",
            block_reason=block_reason,
            now=now,
            ledger_mirror=ledger_mirror,
        )
        updated_pair_keys.append(pair["pair_key"])

    conn.commit()
    matchmaking_pairs_module._flush_ledger_mirror(ledger_mirror)
    return [matchmaking_pairs_module.get_pair(conn, pair_key) for pair_key in updated_pair_keys]


def benchmark_matchmaking_pairs(pair_count: int, repeat: int) -> dict[str, Any]:
    def current_call() -> dict[str, Any]:
        _seed_matchmaking_pairs_db(pair_count)
        conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        try:
            return {"results": build_mutual_pairs(conn, now=datetime(2026, 6, 1, 9, 5, 0))}
        finally:
            conn.close()

    def legacy_call() -> dict[str, Any]:
        _seed_matchmaking_pairs_db(pair_count)
        conn = connect_matchmaking_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        try:
            return {"results": _legacy_build_mutual_pairs(conn, now=datetime(2026, 6, 1, 9, 5, 0))}
        finally:
            conn.close()

    return {
        "scenario": "matchmaking_mutual_pair_build",
        "current": _run_benchmark("current", current_call, repeat=repeat),
        "legacy_emulation": _run_benchmark("legacy_emulation", legacy_call, repeat=repeat),
    }


def _legacy_upsert_conversation_member(
    conn,
    conversation_id: str,
    *,
    participant_id: str,
    member_role: str,
    can_read: int,
    can_send: int,
    metadata: dict[str, Any] | None,
    joined_at: datetime,
) -> None:
    existing = get_conversation_member(conn, conversation_id, participant_id)
    payload = json.dumps(dict(metadata or {}), ensure_ascii=False, separators=(",", ":"))
    if not existing:
        conn.execute(
            """
            INSERT INTO chat_conversation_members (
              conversation_id, participant_id, member_role, can_read, can_send,
              metadata_json, joined_at, left_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                conversation_id,
                participant_id,
                member_role,
                int(can_read),
                int(can_send),
                payload,
                joined_at,
            ),
        )
        return
    conn.execute(
        """
        UPDATE chat_conversation_members
        SET member_role = ?,
            can_read = ?,
            can_send = ?,
            metadata_json = ?,
            left_at = NULL
        WHERE conversation_id = ? AND participant_id = ?
        """,
        (
            member_role,
            int(can_read),
            int(can_send),
            payload,
            conversation_id,
            participant_id,
        ),
    )


def _legacy_get_or_create_conversation_existing(
    conn,
    *,
    case_id: str,
    relation_key: str,
    channel_key: str,
    conversation_kind: str,
    member_specs: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    del relation_key, conversation_kind
    existing = get_conversation_by_case_and_key(conn, case_id, channel_key)
    if not existing:
        raise ValueError("legacy benchmark expects pre-created conversation")
    for member in member_specs:
        _legacy_upsert_conversation_member(
            conn,
            str(existing["conversation_id"]),
            participant_id=str(member["participant_id"]),
            member_role=str(member["member_role"]),
            can_read=1 if bool(member.get("can_read", True)) else 0,
            can_send=1 if bool(member.get("can_send", True)) else 0,
            metadata=dict(member.get("metadata") or {}),
            joined_at=now,
        )
    conn.commit()
    conversations = list_case_conversations(conn, case_id)
    for conversation in conversations:
        if str(conversation.get("conversation_id") or "") == str(existing["conversation_id"]):
            return conversation
    raise ValueError("conversation not found after legacy update")


def _legacy_create_assistant_case_layout_existing(
    conn,
    *,
    case_id: str,
    relation_key: str,
    participant_a_id: str,
    participant_b_id: str,
    agent_id: str,
    now: datetime,
) -> dict[str, Any]:
    main = _legacy_get_or_create_conversation_existing(
        conn,
        case_id=case_id,
        relation_key=relation_key,
        channel_key="main_group",
        conversation_kind=CONV_KIND_GROUP,
        member_specs=[
            {"participant_id": participant_a_id, "member_role": ROLE_HUMAN},
            {"participant_id": participant_b_id, "member_role": ROLE_HUMAN},
            {"participant_id": agent_id, "member_role": ROLE_AGENT},
        ],
        now=now,
    )
    dm_a = _legacy_get_or_create_conversation_existing(
        conn,
        case_id=case_id,
        relation_key=relation_key,
        channel_key="assistant_dm_a",
        conversation_kind=CONV_KIND_DM,
        member_specs=[
            {"participant_id": participant_a_id, "member_role": ROLE_HUMAN},
            {"participant_id": agent_id, "member_role": ROLE_AGENT},
        ],
        now=now,
    )
    dm_b = _legacy_get_or_create_conversation_existing(
        conn,
        case_id=case_id,
        relation_key=relation_key,
        channel_key="assistant_dm_b",
        conversation_kind=CONV_KIND_DM,
        member_specs=[
            {"participant_id": participant_b_id, "member_role": ROLE_HUMAN},
            {"participant_id": agent_id, "member_role": ROLE_AGENT},
        ],
        now=now,
    )
    return {
        "case_id": case_id,
        "relation_key": relation_key,
        "participant_a_id": participant_a_id,
        "participant_b_id": participant_b_id,
        "agent_id": agent_id,
        "conversation_count": 3,
        "conversations": [main, dm_a, dm_b],
    }


def _seed_chat_layout_db(layout_count: int) -> None:
    conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
    initialize_chat_db(conn)
    reset_chat_tables(conn)
    ts = datetime(2026, 6, 1, 9, 0, 0)
    for index in range(layout_count):
        create_assistant_case_layout(
            conn,
            case_id=f"layout-case-{index}",
            relation_key=f"layout-rel-{index}",
            participant_a_id=f"user-a-{index}",
            participant_b_id=f"user-b-{index}",
            agent_id=f"agent-{index}",
            now=ts,
        )
    conn.close()


def benchmark_chat_layout_reupsert(layout_count: int, repeat: int) -> dict[str, Any]:
    def current_call() -> dict[str, Any]:
        _seed_chat_layout_db(layout_count)
        conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        try:
            results = []
            ts = datetime(2026, 6, 1, 9, 1, 0)
            for index in range(layout_count):
                results.append(
                    create_assistant_case_layout(
                        conn,
                        case_id=f"layout-case-{index}",
                        relation_key=f"layout-rel-{index}",
                        participant_a_id=f"user-a-{index}",
                        participant_b_id=f"user-b-{index}",
                        agent_id=f"agent-{index}",
                        now=ts,
                    )
                )
            return {"results": results}
        finally:
            conn.close()

    def legacy_call() -> dict[str, Any]:
        _seed_chat_layout_db(layout_count)
        conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        try:
            results = []
            ts = datetime(2026, 6, 1, 9, 1, 0)
            for index in range(layout_count):
                results.append(
                    _legacy_create_assistant_case_layout_existing(
                        conn,
                        case_id=f"layout-case-{index}",
                        relation_key=f"layout-rel-{index}",
                        participant_a_id=f"user-a-{index}",
                        participant_b_id=f"user-b-{index}",
                        agent_id=f"agent-{index}",
                        now=ts,
                    )
                )
            return {"results": results}
        finally:
            conn.close()

    return {
        "scenario": "chat_layout_member_reupsert",
        "current": _run_benchmark("current", current_call, repeat=repeat),
        "legacy_emulation": _run_benchmark("legacy_emulation", legacy_call, repeat=repeat),
    }


def _legacy_discovery_request_bootstrap(session: StoredSession, *, source: str, limit: int) -> dict[str, Any]:
    self_profile = discovery_integrations.load_requester_profile_with(
        session,
        source=source,
        load_profile=discovery_integrations.load_self_profile,
    )
    if isinstance(self_profile, dict) and not self_profile:
        self_profile = None
    effective_self_id = session.profile_id if isinstance(self_profile, dict) and self_profile else None
    persona_row = None
    persona_source = discovery_integrations.persona_memory_source() or source
    if persona_source:
        try:
            persona_row = discovery_integrations.load_persona_for_discovery(
                source=persona_source,
                profile_id=session.profile_id,
                requester_id=session.requester_id,
            )
        except Exception:
            persona_row = None
    compiled_request = discovery_integrations.build_discovery_search_request(
        source=source,
        profile_row=self_profile,
        persona_row=persona_row,
        criteria_overrides={},
        self_id=effective_self_id,
        limit=limit,
    )
    user_traits = None
    if persona_source and session.profile_id:
        user_traits = discovery_integrations.load_traits_for_discovery(
            source=persona_source,
            profile_id=session.profile_id,
            requester_id=session.requester_id,
        )
    return {
        "compiled": compiled_request,
        "user_traits": user_traits.to_dict() if user_traits else {},
        "result_count": 1,
    }


def benchmark_discovery_request_bootstrap(repeat: int) -> dict[str, Any]:
    session = StoredSession(
        session_id="bench-discovery-session",
        requester_id=70001,
        profile_id=10001,
        status="active",
        phase="collecting_preferences",
        created_at=datetime(2026, 6, 1, 9, 0, 0),
        updated_at=datetime(2026, 6, 1, 9, 0, 0),
        view={"timeline": [], "criteria_chips": [], "suggested_actions": [], "composer": {}},
        state={},
    )
    original_profile_source = discovery_integrations.load_requester_profile_with
    original_persona_loader = discovery_integrations.load_persona_for_discovery
    original_traits_loader = discovery_integrations.load_traits_for_discovery
    original_traits_for_profiles = discovery_integrations.load_traits_for_profiles
    original_build_request = discovery_integrations.build_discovery_search_request
    original_save_snapshot = discovery_integrations.save_compiled_snapshot
    original_search_with_gate = discovery_integrations.search_profiles_with_visibility_gate

    def fake_load_profile(*_args, **_kwargs):
        time.sleep(0.01)
        return {"id": 10001, "city": "无锡"}

    def fake_load_persona(*_args, **_kwargs):
        time.sleep(0.01)
        return {
            "profile_id": 10001,
            "self_personality_traits_json": json.dumps(
                {"mbti": {"type_code": "ISTJ"}, "values": {"top_values": ["稳定经营"]}},
                ensure_ascii=False,
            ),
        }

    def fake_load_traits(*_args, **_kwargs):
        time.sleep(0.01)
        return discovery_integrations.build_traits_context_from_persona_row(
            fake_load_persona(),
            profile_id=10001,
        )

    def fake_build_request(**kwargs):
        return {"compiled": {}, "criteria": kwargs.get("criteria_overrides") or {}, "self_profile": kwargs.get("profile_row")}

    def fake_save_snapshot(*_args, **_kwargs):
        return None

    def fake_search_with_gate(search_fn, **kwargs):
        return search_fn(**kwargs)

    def fake_load_traits_for_profiles(*_args, **_kwargs):
        return {}

    def current_call() -> dict[str, Any]:
        discovery_integrations.load_requester_profile_with = fake_load_profile
        discovery_integrations.load_persona_for_discovery = fake_load_persona
        discovery_integrations.load_traits_for_discovery = fake_load_traits
        discovery_integrations.load_traits_for_profiles = fake_load_traits_for_profiles
        discovery_integrations.build_discovery_search_request = fake_build_request
        discovery_integrations.save_compiled_snapshot = fake_save_snapshot
        discovery_integrations.search_profiles_with_visibility_gate = fake_search_with_gate
        try:
            return discovery_integrations.search_partner_candidates_with(
                session,
                criteria={},
                limit=5,
                source="mysql://bench",
                load_profile=lambda **_kwargs: {"id": 10001},
                search=lambda **_kwargs: {
                    "has_match": True,
                    "result_count": 1,
                    "results": [{"id": 3001, "name": "候选人A", "score": 90, "profile": {"city": "无锡"}}],
                },
            )
        finally:
            discovery_integrations.load_requester_profile_with = original_profile_source
            discovery_integrations.load_persona_for_discovery = original_persona_loader
            discovery_integrations.load_traits_for_discovery = original_traits_loader
            discovery_integrations.load_traits_for_profiles = original_traits_for_profiles
            discovery_integrations.build_discovery_search_request = original_build_request
            discovery_integrations.save_compiled_snapshot = original_save_snapshot
            discovery_integrations.search_profiles_with_visibility_gate = original_search_with_gate

    def legacy_call() -> dict[str, Any]:
        discovery_integrations.load_requester_profile_with = fake_load_profile
        discovery_integrations.load_persona_for_discovery = fake_load_persona
        discovery_integrations.load_traits_for_discovery = fake_load_traits
        discovery_integrations.load_traits_for_profiles = fake_load_traits_for_profiles
        discovery_integrations.build_discovery_search_request = fake_build_request
        discovery_integrations.save_compiled_snapshot = fake_save_snapshot
        discovery_integrations.search_profiles_with_visibility_gate = fake_search_with_gate
        try:
            return _legacy_discovery_request_bootstrap(session, source="mysql://bench", limit=5)
        finally:
            discovery_integrations.load_requester_profile_with = original_profile_source
            discovery_integrations.load_persona_for_discovery = original_persona_loader
            discovery_integrations.load_traits_for_discovery = original_traits_loader
            discovery_integrations.load_traits_for_profiles = original_traits_for_profiles
            discovery_integrations.build_discovery_search_request = original_build_request
            discovery_integrations.save_compiled_snapshot = original_save_snapshot
            discovery_integrations.search_profiles_with_visibility_gate = original_search_with_gate

    return {
        "scenario": "discovery_request_bootstrap_synthetic",
        "current": _run_benchmark("current", current_call, repeat=repeat),
        "legacy_emulation": _run_benchmark("legacy_emulation", legacy_call, repeat=repeat),
    }


def _seed_recommendation_listing_db(recommendation_count: int) -> str:
    conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
    initialize_recommendation_db(conn)
    reset_recommendation_tables(conn)
    now = datetime(2026, 6, 1, 9, 0, 0)
    subscription = create_subscription(
        conn,
        requester_id=70001,
        source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
        criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
        self_profile={"age": 28, "city": "无锡", "height": 178},
        limit_count=20,
        top_k=10,
        min_notify_score=40,
        daily_notification_cap=3,
        quiet_hours_start=23,
        quiet_hours_end=23,
        recommendation_mode="direct_greet_only",
        max_review_candidates_per_refresh=5,
        min_direct_greet_score=60,
        now=now,
    )
    recommendation_rows: list[tuple[Any, ...]] = []
    action_rows: list[tuple[Any, ...]] = []
    for index in range(recommendation_count):
        recommendation_rows.append(
            (
                subscription["subscription_id"],
                70001,
                80000 + index,
                f"推荐对象{index}",
                80 - (index % 20),
                70 - (index % 10),
                10,
                index % 3,
                "pending_delivery",
                "seeded_for_benchmark",
                now,
                now,
                None,
                None,
                None,
                json.dumps(["城市 无锡", "目标 认真恋爱"], ensure_ascii=False),
                json.dumps([] if index % 5 else ["需要确认见面频率"], ensure_ascii=False),
                json.dumps({"profile": {"age": 27 + (index % 5), "city": "无锡", "job": "产品经理", "verified_level": "photo", "photo_count": 4}}, ensure_ascii=False),
                "direct_greet_ready",
                None,
                90,
                json.dumps({}, ensure_ascii=False),
                now,
                f"snapshot-{index}",
                "pending_review",
                None,
                json.dumps({}, ensure_ascii=False),
                None,
                f"relation-{index}",
                json.dumps({"source_dsn": "mysql://user:pass@127.0.0.1:3306/her", "source_table_name": "profiles", "profile_id": 70001}, ensure_ascii=False),
                json.dumps({"source_dsn": "mysql://user:pass@127.0.0.1:3306/her", "source_table_name": "profiles", "profile_id": 80000 + index}, ensure_ascii=False),
                None,
                None,
                "pass",
                json.dumps([], ensure_ascii=False),
                "recommendation-system",
                None,
                now,
                None,
                json.dumps({"rule": "bench"}, ensure_ascii=False),
            )
        )
        for action_index in range(3):
            action_rows.append(
                (
                    subscription["subscription_id"],
                    index + 1,
                    70001,
                    80000 + index,
                    "refresh_seen" if action_index < 2 else "queued_for_delivery",
                    json.dumps({"sequence": action_index}, ensure_ascii=False),
                    now + timedelta(seconds=action_index),
                )
            )
    with conn.driver_connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO profile_recommendations (
              subscription_id, requester_id, candidate_id, candidate_name,
              score, fit_score, confidence_score, risk_score,
              delivery_status, delivery_reason, first_seen_at, last_seen_at,
              notified_at, cooling_until, last_action_type,
              matched_on_json, risk_flags_json, latest_payload_json,
              final_review_status, final_review_reason, final_review_score, final_review_payload_json,
              reviewed_at, candidate_snapshot_hash,
              user_review_status, user_review_reason, user_review_payload_json, user_reviewed_at,
              relation_key, owner_profile_ref_json, target_profile_ref_json,
              active_match_case_id, active_case_status,
              gate_outcome, gate_reason_codes_json, gate_owner_service, gate_details_ref, gate_evaluated_at,
              latest_card_id, rule_provenance_json
            ) VALUES (
              %s, %s, %s, %s,
              %s, %s, %s, %s,
              %s, %s, %s, %s,
              %s, %s, %s,
              %s, %s, %s,
              %s, %s, %s, %s,
              %s, %s,
              %s, %s, %s, %s,
              %s, %s, %s,
              %s, %s,
              %s, %s, %s, %s, %s,
              %s, %s
            )
            """,
            recommendation_rows,
        )
        cursor.execute("SELECT recommendation_id, candidate_id FROM profile_recommendations ORDER BY recommendation_id ASC")
        recommendation_ids = {
            int(row["candidate_id"]): int(row["recommendation_id"])
            for row in cursor.fetchall()
        }
        patched_action_rows = [
            (
                subscription_id,
                recommendation_ids[candidate_id],
                requester_id,
                candidate_id,
                action_type,
                payload_json,
                occurred_at,
            )
            for subscription_id, _old_recommendation_id, requester_id, candidate_id, action_type, payload_json, occurred_at in action_rows
        ]
        cursor.executemany(
            """
            INSERT INTO recommendation_actions (
              subscription_id, recommendation_id, requester_id, candidate_id,
              action_type, action_payload_json, occurred_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            patched_action_rows,
        )
    conn.driver_connection.commit()
    conn.close()
    return str(subscription["subscription_id"])


def _legacy_list_recommendations_for_subscription(conn: MySQLCompatConnection, subscription_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM profile_recommendations
        WHERE subscription_id = ?
        ORDER BY score DESC, last_seen_at DESC, recommendation_id DESC
        """,
        (subscription_id,),
    ).fetchall()
    subscription_row = conn.execute(
        "SELECT * FROM saved_search_subscriptions WHERE subscription_id = ?",
        (subscription_id,),
    ).fetchone()
    subscription = row_to_dict(subscription_row)
    inflated: list[dict[str, Any]] = []
    for row in rows:
        row_dict = _merge_recommendation_subscription_fields(row_to_dict(row), subscription)
        inflated.append(
            inflate_recommendation_row(
                row_dict,
                conn=conn,
                preloaded_action_rows=list_recommendation_actions_for_recommendation(
                    conn,
                    int(row_dict["recommendation_id"]),
                ),
            )
        )
    return inflated


def benchmark_recommendation_listing(recommendation_count: int, repeat: int) -> dict[str, Any]:
    subscription_id = _seed_recommendation_listing_db(recommendation_count)

    def current_call() -> dict[str, Any]:
        conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        try:
            return {"results": list_recommendations_for_subscription(conn, subscription_id)}
        finally:
            conn.close()

    def legacy_call() -> dict[str, Any]:
        conn = connect_recommendation_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        try:
            return {"results": _legacy_list_recommendations_for_subscription(conn, subscription_id)}
        finally:
            conn.close()

    return {
        "scenario": "recommendation_subscription_listing",
        "current": _run_benchmark("current", current_call, repeat=repeat),
        "legacy_emulation": _run_benchmark("legacy_emulation", legacy_call, repeat=repeat),
    }


def _seed_trust_hub_db(item_count: int) -> tuple[str, int]:
    conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
    initialize_chat_db(conn)
    reset_chat_tables(conn)
    user_id = "trust-user-1"
    profile_id = 90001
    source_dsn = f"{DEFAULT_CHAT_TEST_MYSQL_DSN}?table=profiles"
    source_table_name = "profiles"
    ts = datetime(2026, 6, 1, 10, 0, 0)
    with conn.driver_connection.cursor() as cursor:
        for index in range(item_count):
            thread = get_or_create_thread(
                conn,
                case_id=f"trust-case-{index}",
                relation_key=f"trust-rel-{index}",
                participant_a_id=user_id,
                participant_b_id=f"counterpart-{index}",
                now=ts,
            )
            thread_id = str(thread["thread_id"])
            submission_id = f"sub-{index}"
            cursor.execute(
                """
                INSERT INTO verification_submissions (
                  submission_id, verification_type, user_id, profile_id, source_dsn, source_table_name,
                  status, resubmission_count, challenge_phrase, review_decision, review_note, reviewer_id,
                  latest_asset_id, latest_sync_status, latest_sync_error, submitted_at, reviewed_at,
                  approved_at, rejected_at, metadata_json, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    submission_id, "live_video", user_id, profile_id, source_dsn, source_table_name,
                    "submitted", 0, None, None, None, None,
                    None, None, None, ts, None, None, None,
                    json.dumps({"photo_review_task": {"task_kind": "photo_review", "reason_labels": ["照片真实性"], "capture_tips": ["自然光"]}}, ensure_ascii=False),
                    ts, ts,
                ),
            )
            cursor.execute(
                """
                INSERT INTO verification_assets (
                  submission_id, asset_kind, storage_key, original_file_name, content_type,
                  file_size_bytes, sha256_hex, upload_attempt, metadata_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (submission_id, "video", f"video/{submission_id}.mp4", f"{submission_id}.mp4", "video/mp4", 1024, f"sha{submission_id}", 1, "{}", ts),
            )
            cursor.execute(
                """
                INSERT INTO verification_reviews (
                  submission_id, reviewer_id, decision, review_note, liveness_result, face_match_result,
                  profile_consistency_result, metadata_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (submission_id, "reviewer", "pending", "待审核", None, None, None, "{}", ts),
            )
            cursor.execute(
                """
                INSERT INTO verification_notifications (
                  submission_id, user_id, notification_type, delivery_channel, delivery_status,
                  title, body, metadata_json, created_at, sent_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (submission_id, user_id, "photo_review_requested", "in_app", "recorded", "请补录视频", "系统需要补录", "{}", ts, ts),
            )
            field_submission_id = f"field-{index}"
            cursor.execute(
                """
                INSERT INTO profile_field_verification_submissions (
                  submission_id, field_key, subject_user_id, profile_id, source_dsn, source_table_name,
                  status, declared_value, approved_value, resubmission_count, required_documents_json,
                  evidence_json, evidence_type, evidence_channel, reverify_strategy, verification_expires_at,
                  next_review_due_at, dispute_status, dispute_reason, dispute_evidence_json, disputed_at,
                  dispute_resolved_at, review_decision, review_note, reviewer_id, latest_sync_status, latest_sync_error,
                  submitted_at, reviewed_at, approved_at, rejected_at, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    field_submission_id, "income", user_id, profile_id, source_dsn, source_table_name,
                    "submitted", "30万", None, 0, json.dumps(["收入证明"], ensure_ascii=False),
                    json.dumps({}, ensure_ascii=False), None, None, None, None, None,
                    "none", None, None, None, None, None, None, None, None, None,
                    ts, None, None, None, ts, ts,
                ),
            )
            cursor.execute(
                """
                INSERT INTO profile_field_verification_reviews (
                  submission_id, reviewer_id, decision, review_note, approved_value,
                  requested_documents_json, metadata_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (field_submission_id, "reviewer", "request_resubmission", "补充收入证明", None, json.dumps(["收入证明"], ensure_ascii=False), "{}", ts),
            )
            profile_case_id = f"profile-case-{index}"
            cursor.execute(
                """
                INSERT INTO profile_review_cases (
                  profile_review_case_id, subject_user_id, profile_id, source_dsn, source_table_name,
                  status, severity, rule_codes_json, evidence_summary_json, recommended_action, applied_action,
                  resolver_id, resolution_note, last_evaluated_at, created_at, updated_at, resolved_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    profile_case_id, user_id, profile_id, source_dsn, source_table_name,
                    "under_review", "medium", json.dumps(["income_mismatch"], ensure_ascii=False),
                    json.dumps({"required_verifications": ["income"], "rule_hits": [{"rule_code": "income_mismatch", "evidence": {"summary": "收入待核验"}}]}, ensure_ascii=False),
                    "limited_exposure", "limited_exposure", None, None, ts, ts, ts, None,
                ),
            )
            cursor.execute(
                """
                INSERT INTO profile_review_case_appeals (
                  profile_review_case_id, subject_key, subject_user_id, appellant_id, appeal_status,
                  reason_text, evidence_json, resolution_note, resolver_id, created_at, updated_at, resolved_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (profile_case_id, f"user:{user_id}", user_id, user_id, "submitted", "补充说明", "{}", None, None, ts, ts, None),
            )
            risk_case_id = f"risk-case-{index}"
            cursor.execute(
                """
                INSERT INTO chat_risk_cases (
                  risk_case_id, thread_id, case_id, subject_user_id, status, severity,
                  source_types_json, signal_codes_json, evidence_summary_json, report_count,
                  recommended_action, applied_action, resolver_id, resolution_note,
                  last_reported_at, created_at, updated_at, resolved_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    risk_case_id, thread_id, f"trust-case-{index}", user_id, "action_applied", "medium",
                    json.dumps(["report"], ensure_ascii=False), json.dumps(["off_platform"], ensure_ascii=False),
                    json.dumps({"source_dsn": source_dsn, "source_table_name": source_table_name, "profile_id": profile_id}, ensure_ascii=False),
                    1, "limit_chat", "limit_chat", None, None, ts, ts, ts, None,
                ),
            )
            cursor.execute(
                """
                INSERT INTO chat_risk_appeals (
                  risk_case_id, subject_key, subject_user_id, appellant_id, appeal_status,
                  reason_text, evidence_json, resolution_note, resolver_id, created_at, updated_at, resolved_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (risk_case_id, f"user:{user_id}", user_id, user_id, "submitted", "我已补充说明", "{}", None, None, ts, ts, None),
            )
            cursor.execute(
                """
                INSERT INTO account_moderation_states (
                  subject_key, subject_user_id, source_dsn, source_table_name, profile_id,
                  moderation_status, applied_action, reason_code, reason_summary,
                  required_verifications_json, evidence_json, linked_risk_case_id, linked_profile_review_case_id,
                  resolver_id, created_at, updated_at, cleared_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE updated_at = VALUES(updated_at)
                """,
                (
                    f"user:{user_id}", user_id, source_dsn, source_table_name, profile_id,
                    "active", "freeze", "risk", "存在风控限制", json.dumps(["live_video", "income"], ensure_ascii=False),
                    "{}", risk_case_id, profile_case_id, None, ts, ts, None,
                ),
            )
    conn.driver_connection.commit()
    conn.close()
    return user_id, profile_id


def _legacy_list_verification_submissions(conn: MySQLCompatConnection, *, user_id: str, profile_id: int, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM verification_submissions
        WHERE verification_type = ? AND user_id = ? AND profile_id = ?
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        ("live_video", user_id, profile_id, limit),
    ).fetchall()
    return [verification_module._inflate_submission(conn, row_to_dict(row)) for row in rows if row]


def _legacy_list_photo_review_requests(conn: MySQLCompatConnection, *, user_id: str, profile_id: int, limit: int) -> list[dict[str, Any]]:
    rows = _legacy_list_verification_submissions(conn, user_id=user_id, profile_id=profile_id, limit=limit)
    return [row for row in rows if verification_module._submission_has_photo_review_task(row)]


def _legacy_list_profile_field_verification_submissions(conn: MySQLCompatConnection, *, user_id: str, profile_id: int, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT * FROM profile_field_verification_submissions
        WHERE subject_user_id = ? AND profile_id = ?
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        (user_id, profile_id, limit),
    ).fetchall()
    return [profile_reviews_module._inflate_field_submission(conn, row_to_dict(row)) for row in rows if row]


def _legacy_build_user_trust_hub(conn: MySQLCompatConnection, *, user_id: str, profile_id: int, limit: int) -> dict[str, Any]:
    normalized_user_id = str(user_id)
    photo_requests = _legacy_list_photo_review_requests(conn, user_id=normalized_user_id, profile_id=profile_id, limit=limit)
    field_submissions = _legacy_list_profile_field_verification_submissions(conn, user_id=normalized_user_id, profile_id=profile_id, limit=limit)
    profile_cases = profile_reviews_module.list_profile_review_cases(
        conn,
        subject_user_id=normalized_user_id,
        profile_id=profile_id,
        statuses=[
            profile_reviews_module.PROFILE_REVIEW_STATUS_OPEN,
            profile_reviews_module.PROFILE_REVIEW_STATUS_UNDER_REVIEW,
            profile_reviews_module.PROFILE_REVIEW_STATUS_ACTION_APPLIED,
            profile_reviews_module.PROFILE_REVIEW_STATUS_DISMISSED,
            profile_reviews_module.PROFILE_REVIEW_STATUS_RESOLVED,
        ],
        limit=limit,
    )
    active_profile_cases = [
        item
        for item in profile_cases
        if str(item.get("status") or "") in {
            profile_reviews_module.PROFILE_REVIEW_STATUS_OPEN,
            profile_reviews_module.PROFILE_REVIEW_STATUS_UNDER_REVIEW,
            profile_reviews_module.PROFILE_REVIEW_STATUS_ACTION_APPLIED,
        }
    ]
    chat_cases = self_service_module.list_risk_cases(conn, subject_user_id=normalized_user_id, limit=limit)
    chat_appeals = self_service_module.list_risk_appeals(conn, subject_user_id=normalized_user_id, limit=limit * 3)
    profile_appeals = profile_reviews_module.list_profile_review_case_appeals(conn, subject_user_id=normalized_user_id, limit=limit * 3)
    user_notifications = verification_module.list_verification_notifications(conn, user_id=normalized_user_id, limit=limit * 5)
    verification_items = self_service_module._build_verification_items(
        user_id=normalized_user_id,
        profile_id=profile_id,
        photo_requests=photo_requests,
        field_submissions=field_submissions,
        profile_cases=active_profile_cases,
    )
    appeal_items = self_service_module._build_appeal_items(
        chat_cases=chat_cases,
        chat_appeals=chat_appeals,
        profile_cases=profile_cases,
        profile_appeals=profile_appeals,
        field_submissions=field_submissions,
    )
    risk_records = self_service_module._build_risk_records(
        chat_cases=chat_cases,
        profile_cases=profile_cases,
        chat_appeals=chat_appeals,
        profile_appeals=profile_appeals,
    )
    notifications = self_service_module._build_notifications(
        user_notifications=user_notifications,
        verification_items=verification_items,
        appeal_items=appeal_items,
    )
    return {
        "user_id": normalized_user_id,
        "profile_id": profile_id,
        "summary": {
            "pending_verification_count": len([item for item in verification_items if str(item.get("work_state") or "") in {"action_required", "in_progress"}]),
            "pending_appeal_count": len([item for item in appeal_items if str(item.get("work_state") or "") in {"action_required", "in_progress"}]),
            "active_risk_count": len([item for item in risk_records if str(item.get("status") or "") not in {"dismissed", "resolved"}]),
            "notification_count": len(notifications),
        },
        "verification_center": {"items": verification_items},
        "appeal_center": {"items": appeal_items},
        "risk_records": {"items": risk_records},
        "notifications": notifications,
    }


def benchmark_trust_hub_payload(item_count: int, repeat: int) -> dict[str, Any]:
    user_id, profile_id = _seed_trust_hub_db(item_count)

    def current_call() -> dict[str, Any]:
        conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        try:
            return build_user_trust_hub(conn, user_id=user_id, profile_id=profile_id, limit=item_count)
        finally:
            conn.close()

    def legacy_call() -> dict[str, Any]:
        conn = connect_chat_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        try:
            return _legacy_build_user_trust_hub(conn, user_id=user_id, profile_id=profile_id, limit=item_count)
        finally:
            conn.close()

    return {
        "scenario": "user_trust_hub_payload",
        "current": _run_benchmark("current", current_call, repeat=repeat),
        "legacy_emulation": _run_benchmark("legacy_emulation", legacy_call, repeat=repeat),
    }


def _run_benchmark(label: str, fn: Callable[[], dict[str, Any]], *, repeat: int) -> BenchmarkSummary:
    runs: list[RunResult] = []
    result_count = 0
    for _ in range(repeat):
        with query_counter() as stats:
            started = time.perf_counter()
            payload = fn()
            elapsed_ms = (time.perf_counter() - started) * 1000.0
        result_count = _extract_result_count(payload)
        runs.append(
            RunResult(
                elapsed_ms=elapsed_ms,
                execute_count=stats.execute_count,
                fetched_cells=stats.fetched_cells,
            )
        )
    return BenchmarkSummary(label=label, runs=runs, result_count=result_count)


def _extract_result_count(payload: dict[str, Any]) -> int:
    if "result_count" in payload:
        return int(payload.get("result_count") or 0)
    if "results" in payload:
        return len(payload.get("results") or [])
    if "verification_center" in payload:
        return len(((payload.get("verification_center") or {}).get("items") or []))
    if "conversations" in payload:
        return len(payload.get("conversations") or [])
    if "task_refs" in payload:
        return len(payload.get("task_refs") or [])
    return 0


def _speedup_ratio(current: BenchmarkSummary, legacy: BenchmarkSummary, attr: str) -> float | None:
    current_value = getattr(current, attr)
    legacy_value = getattr(legacy, attr)
    if current_value <= 0:
        return None
    return legacy_value / current_value


def _print_markdown_report(report: dict[str, Any]) -> None:
    print("# Performance Benchmark Report")
    print()
    print(f"Generated at: `{report['generated_at']}`")
    print()
    print("| Scenario | Variant | Avg ms | Avg SQL | Avg Cells | Result Count |")
    print("|----------|---------|--------|---------|-----------|--------------|")
    for scenario in report["benchmarks"]:
        for key in ("current", "legacy_emulation"):
            item = scenario[key]
            print(
                f"| {scenario['scenario']} | {item['label']} | {item['avg_ms']:.3f} | "
                f"{item['avg_execute_count']:.3f} | {item['avg_fetched_cells']:.3f} | {item['result_count']} |"
            )
        print(
            f"| {scenario['scenario']} | speedup | {scenario['time_speedup_vs_legacy']:.3f}x | "
                f"{scenario['query_reduction_vs_legacy']:.3f}x | {scenario['cell_reduction_vs_legacy']:.3f}x | - |"
        )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    _disable_search_cache()
    benchmarks: list[dict[str, Any]] = []

    for scenario in (
        benchmark_partner_search(args.search_profiles, args.repeat),
        benchmark_chat_timeline(args.messages_per_conversation, args.repeat),
        benchmark_assistant_opening(args.opening_cases, args.repeat),
        benchmark_matchmaking_pairs(args.matchmaking_pairs, args.repeat),
        benchmark_chat_layout_reupsert(args.layout_updates, args.repeat),
        benchmark_discovery_request_bootstrap(args.repeat),
        benchmark_recommendation_listing(args.recommendation_count, args.repeat),
        benchmark_trust_hub_payload(args.trust_hub_items, args.repeat),
    ):
        current = scenario["current"]
        legacy = scenario["legacy_emulation"]
        scenario["current"] = current.to_dict()
        scenario["legacy_emulation"] = legacy.to_dict()
        scenario["time_speedup_vs_legacy"] = round(_speedup_ratio(current, legacy, "avg_ms") or 0.0, 3)
        scenario["query_reduction_vs_legacy"] = round(_speedup_ratio(current, legacy, "avg_executes") or 0.0, 3)
        scenario["cell_reduction_vs_legacy"] = round(_speedup_ratio(current, legacy, "avg_cells") or 0.0, 3)
        benchmarks.append(scenario)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "repeat": args.repeat,
        "search_profiles": args.search_profiles,
        "messages_per_conversation": args.messages_per_conversation,
        "opening_cases": args.opening_cases,
        "matchmaking_pairs": args.matchmaking_pairs,
        "layout_updates": args.layout_updates,
        "recommendation_count": args.recommendation_count,
        "trust_hub_items": args.trust_hub_items,
        "benchmarks": benchmarks,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run reproducible backend performance benchmarks.")
    parser.add_argument("--repeat", type=int, default=3, help="How many measured runs per variant.")
    parser.add_argument("--search-profiles", type=int, default=4000, help="Profiles to seed for partner_search.")
    parser.add_argument(
        "--messages-per-conversation",
        type=int,
        default=400,
        help="Messages to seed per conversation for timeline benchmarks.",
    )
    parser.add_argument("--opening-cases", type=int, default=60, help="Cases to seed for opening probe benchmarks.")
    parser.add_argument("--matchmaking-pairs", type=int, default=40, help="Reciprocal member pairs to seed for mutual-pair benchmarks.")
    parser.add_argument("--layout-updates", type=int, default=60, help="Existing assistant layouts to re-upsert for conversation benchmarks.")
    parser.add_argument("--recommendation-count", type=int, default=200, help="Recommendations to seed for recommendation listing benchmarks.")
    parser.add_argument("--trust-hub-items", type=int, default=50, help="Per-type items to seed for trust hub benchmarks.")
    parser.add_argument("--output-json", help="Optional path to write the full JSON report.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(args)
    _print_markdown_report(report)
    if args.output_json:
        output_path = pathlib.Path(args.output_json)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print()
        print(f"JSON report written to `{output_path}`")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
