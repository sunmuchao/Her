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

for root in (REPO_ROOT, GATEWAY_ROOT, CHAT_ROOT):
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
    create_assistant_case_layout,
)
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
