"""Shared external-system storage and async job helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from async_jobs import (
    AsyncJobHandler,
    enqueue_async_job,
    run_async_job_worker,
)
from db_migrations import initialize_target_database
from observability.health import emit_async_job_gauges
import outer_system_mysql_schema as _schema
from outer_mysql_compat import (
    MySQLCompatConnection,
    connect_mysql_repo_db,
    json_dumps,
    json_loads,
    row_to_dict,
)


def connect_external_db(dsn: str, *, subsystem_name: str) -> MySQLCompatConnection:
    return connect_mysql_repo_db(dsn, subsystem_name=subsystem_name)


def initialize_external_database(
    conn: MySQLCompatConnection,
    *,
    target: str,
    mode: str | None = None,
) -> None:
    initialize_target_database(conn, target=target, mode=mode)


def reset_external_tables(
    conn: MySQLCompatConnection,
    *,
    table_names: Callable[[], Sequence[str]],
) -> None:
    _schema.clear_tables(conn._conn, table_names(), prefix=None)
    conn.commit()


def build_external_storage_helpers(
    *,
    subsystem_name: str,
    target: str,
    table_names: Callable[[], Sequence[str]],
) -> tuple[
    Callable[[str], MySQLCompatConnection],
    Callable[[MySQLCompatConnection], None],
    Callable[[MySQLCompatConnection], None],
]:
    def connect_db(dsn: str) -> MySQLCompatConnection:
        return connect_external_db(dsn, subsystem_name=subsystem_name)

    def initialize_database(conn: MySQLCompatConnection, *, mode: str | None = None) -> None:
        initialize_external_database(conn, target=target, mode=mode)

    def reset_all_tables(conn: MySQLCompatConnection) -> None:
        reset_external_tables(conn, table_names=table_names)

    return connect_db, initialize_database, reset_all_tables


def enqueue_external_async_job(
    conn,
    *,
    handlers: Mapping[str, AsyncJobHandler],
    subsystem_name: str,
    job_type: str,
    payload: dict[str, Any] | None = None,
    created_by: str | None = None,
    trace_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    handler = handlers.get(job_type)
    if handler is None:
        raise ValueError(f"unsupported {subsystem_name} async job type: {job_type}")
    return enqueue_async_job(
        conn,
        job_type=job_type,
        payload=payload,
        created_by=created_by,
        trace_id=trace_id,
        max_attempts=handler.max_attempts,
        now=now,
    )


def run_external_async_job_worker(
    conn,
    *,
    handlers: Mapping[str, AsyncJobHandler],
    system: str,
    limit: int = 10,
    retry_delay_seconds: int = 15,
    retry_backoff_multiplier: int = 2,
    retry_max_delay_seconds: int = 300,
    claim_timeout_seconds: int = 300,
    worker_name: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    out = run_async_job_worker(
        conn,
        handlers=handlers,
        limit=limit,
        retry_delay_seconds=retry_delay_seconds,
        retry_backoff_multiplier=retry_backoff_multiplier,
        retry_max_delay_seconds=retry_max_delay_seconds,
        claim_timeout_seconds=claim_timeout_seconds,
        worker_name=worker_name,
        now=now,
    )
    out["summary"] = emit_async_job_gauges(
        conn,
        system=system,
        now=(now or datetime.now()).replace(microsecond=0),
        claim_timeout_seconds=claim_timeout_seconds,
    )
    return out


__all__ = [
    "AsyncJobHandler",
    "MySQLCompatConnection",
    "build_external_storage_helpers",
    "connect_external_db",
    "enqueue_external_async_job",
    "initialize_external_database",
    "json_dumps",
    "json_loads",
    "reset_external_tables",
    "row_to_dict",
    "run_external_async_job_worker",
]
