"""Shared external-system storage and async job helpers."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any

from async_jobs import (
    AsyncJobHandler,
    get_async_job,
    list_async_jobs,
    enqueue_async_job,
    run_async_job_worker,
    summarize_async_jobs,
    summarize_async_jobs_by_type,
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
    default_dsn: str | None = None,
) -> tuple[
    Callable[[str | None], MySQLCompatConnection],
    Callable[[MySQLCompatConnection], None],
    Callable[[MySQLCompatConnection], None],
]:
    def connect_db(dsn: str | None = None) -> MySQLCompatConnection:
        resolved = str(dsn or default_dsn or "").strip()
        if not resolved:
            raise ValueError(f"{subsystem_name} database DSN is required")
        return connect_external_db(resolved, subsystem_name=subsystem_name)

    def initialize_database(conn: MySQLCompatConnection, *, mode: str | None = None) -> None:
        initialize_external_database(conn, target=target, mode=mode)

    def reset_all_tables(conn: MySQLCompatConnection) -> None:
        reset_external_tables(conn, table_names=table_names)

    return connect_db, initialize_database, reset_all_tables


def schema_table_names(loader_name: str) -> Callable[[], list[str]]:
    def load_table_names() -> list[str]:
        import outer_system_mysql_schema as _schema  # noqa: PLC0415

        return list(getattr(_schema, loader_name)())

    return load_table_names


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


def build_external_async_job_helpers(
    *,
    handlers: Mapping[str, AsyncJobHandler],
    subsystem_name: str,
    system: str,
    default_worker_name: str,
) -> tuple[
    Callable[..., dict[str, Any]],
    Callable[..., dict[str, Any] | None],
    Callable[..., list[dict[str, Any]]],
    Callable[..., dict[str, Any]],
    Callable[..., list[dict[str, Any]]],
    Callable[..., dict[str, Any]],
]:
    def enqueue_job(
        conn,
        *,
        job_type: str,
        payload: dict[str, Any] | None = None,
        created_by: str | None = None,
        trace_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return enqueue_external_async_job(
            conn,
            handlers=handlers,
            subsystem_name=subsystem_name,
            job_type=job_type,
            payload=payload,
            created_by=created_by,
            trace_id=trace_id,
            now=now,
        )

    def get_job(conn, job_id: str) -> dict[str, Any] | None:
        return get_async_job(conn, job_id)

    def list_jobs(
        conn,
        *,
        statuses: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return list_async_jobs(conn, statuses=statuses, limit=limit)

    def summarize_jobs(
        conn,
        *,
        now: datetime | None = None,
        claim_timeout_seconds: int = 300,
    ) -> dict[str, Any]:
        return summarize_async_jobs(conn, now=now, claim_timeout_seconds=claim_timeout_seconds)

    def summarize_jobs_by_type(
        conn,
        *,
        now: datetime | None = None,
        claim_timeout_seconds: int = 300,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        return summarize_async_jobs_by_type(conn, now=now, claim_timeout_seconds=claim_timeout_seconds, limit=limit)

    def run_worker(
        conn,
        *,
        limit: int = 10,
        retry_delay_seconds: int = 15,
        retry_backoff_multiplier: int = 2,
        retry_max_delay_seconds: int = 300,
        claim_timeout_seconds: int = 300,
        worker_name: str = default_worker_name,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        return run_external_async_job_worker(
            conn,
            handlers=handlers,
            system=system,
            limit=limit,
            retry_delay_seconds=retry_delay_seconds,
            retry_backoff_multiplier=retry_backoff_multiplier,
            retry_max_delay_seconds=retry_max_delay_seconds,
            claim_timeout_seconds=claim_timeout_seconds,
            worker_name=worker_name,
            now=now,
        )

    return (
        enqueue_job,
        get_job,
        list_jobs,
        summarize_jobs,
        summarize_jobs_by_type,
        run_worker,
    )


def build_external_outbox_helpers(
    *,
    env_prefix: str,
    system: str,
    default_worker_name: str,
    handler: Callable[..., Any] | None = None,
    enrich_worker_result: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> tuple[
    Callable[[], dict[str, Any]],
    Callable[..., dict[str, Any]],
    Callable[..., dict[str, Any]],
]:
    from match_domain.outbox_runtime import (
        resolve_outbox_consume_config as resolve_shared_outbox_consume_config,
        run_outbox_worker,
        serve_outbox_worker,
    )

    def resolve_config() -> dict[str, Any]:
        return resolve_shared_outbox_consume_config(
            env_prefix=env_prefix,
            system=system,
            default_worker_name=default_worker_name,
        )

    def run_worker(conn, **kwargs: Any) -> dict[str, Any]:
        result = run_outbox_worker(
            conn,
            system=system,
            config=resolve_config(),
            handler=handler,
            **kwargs,
        )
        if enrich_worker_result is not None:
            return enrich_worker_result(result)
        return result

    def serve_worker(conn, **kwargs: Any) -> dict[str, Any]:
        result = serve_outbox_worker(
            conn,
            system=system,
            config=resolve_config(),
            handler=handler,
            **kwargs,
        )
        if enrich_worker_result is not None:
            return enrich_worker_result(result)
        return result

    return resolve_config, run_worker, serve_worker


__all__ = [
    "AsyncJobHandler",
    "MySQLCompatConnection",
    "build_external_async_job_helpers",
    "build_external_outbox_helpers",
    "build_external_storage_helpers",
    "connect_external_db",
    "enqueue_external_async_job",
    "initialize_external_database",
    "json_dumps",
    "json_loads",
    "reset_external_tables",
    "row_to_dict",
    "run_external_async_job_worker",
    "schema_table_names",
]
