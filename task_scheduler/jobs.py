from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .paths import (
    ensure_chat_system_on_path,
    ensure_matchmaking_system_on_path,
    ensure_recommendation_system_on_path,
)

logger = logging.getLogger(__name__)

JOB_REC_REFRESH = "recommendation.refresh_saved_searches"
JOB_REC_DELIVER = "recommendation.deliver_in_app_recommendations"
JOB_REC_DISPATCH = "matchmaking.dispatch_proxy_intro_outreach"
JOB_REC_CLOSE_TIMEOUT = "matchmaking.close_timed_out_proxy_cases"
JOB_REC_OUTBOX = "recommendation.outbox_worker"
JOB_REC_ASYNC_WORKER = "recommendation.async_job_worker"
JOB_MM_REFRESH = "matchmaking.refresh_active_pool"
JOB_MM_PAIRS = "matchmaking.build_mutual_pairs"
JOB_MM_OPEN = "matchmaking.open_match_cases"
JOB_MM_STALE = "matchmaking.close_stale_cases"
JOB_MM_OUTBOX = "matchmaking.outbox_worker"
JOB_MM_ASYNC_WORKER = "matchmaking.async_job_worker"
JOB_CHAT_MAINTENANCE = "chat.maintenance"
JOB_CHAT_OUTBOX = "chat.outbox_worker"
JOB_CHAT_ASYNC_WORKER = "chat.async_job_worker"


@dataclass(frozen=True)
class _JobRuntime:
    connect_db: Callable[[str], Any]
    initialize_database: Callable[..., Any]
    post_run: Callable[[Any, str, Any, datetime], None] | None = None


def _safe_dsn_hint(dsn: str) -> str:
    text = str(dsn)
    if "@" in text:
        return text.split("@", 1)[-1]
    return text[:96]


def _log_summary(job_id: str, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) > 2000:
        text = text[:2000] + "…"
    logger.info("%s finished: %s", job_id, text)


def _job_kwargs_without_db(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in kwargs.items() if key != "db"}


def _build_db_job(
    job_id: str,
    fn: Callable[..., Any],
    *,
    kwargs: dict[str, Any],
    subsystem: str,
    ensure_on_path: Callable[[], Any],
    load_runtime: Callable[[], _JobRuntime],
) -> Callable[[], None]:
    def run() -> None:
        ensure_on_path()
        from observability import alert_signal  # noqa: PLC0415

        db_path = kwargs.get("db")
        if not db_path:
            raise RuntimeError(f"{subsystem} job requires db path")

        runtime = load_runtime()
        try:
            conn = runtime.connect_db(db_path)
        except Exception as exc:
            alert_signal(
                "system.db_unreachable",
                str(exc),
                severity="critical",
                subsystem=subsystem,
                dsn_hint=_safe_dsn_hint(str(db_path)),
                error_type=type(exc).__name__,
            )
            raise

        try:
            runtime.initialize_database(conn)
            result = fn(conn, **_job_kwargs_without_db(kwargs))
            _log_summary(job_id, result)
            if runtime.post_run is not None:
                runtime.post_run(conn, job_id, result, datetime.now())
        finally:
            conn.close()

    return run


def _load_recommendation_runtime() -> _JobRuntime:
    from observability.health import run_recommendation_health  # noqa: PLC0415
    from recommendation_system import connect_db, initialize_database  # noqa: PLC0415

    def post_run(conn: Any, job_id: str, result: Any, now: datetime) -> None:
        if job_id == JOB_REC_REFRESH and isinstance(result, dict):
            run_recommendation_health(
                conn,
                now=now,
                refresh_summaries=result.get("summaries"),
                refresh_errors=result.get("errors"),
            )
        elif job_id.startswith("recommendation."):
            run_recommendation_health(conn, now=now)

    return _JobRuntime(
        connect_db=connect_db,
        initialize_database=initialize_database,
        post_run=post_run,
    )


def _load_matchmaking_runtime() -> _JobRuntime:
    from observability.health import run_matchmaking_health  # noqa: PLC0415
    from matchmaking_system import connect_db, initialize_database  # noqa: PLC0415

    def post_run(conn: Any, job_id: str, result: Any, now: datetime) -> None:
        pool_summaries = result if job_id == JOB_MM_REFRESH and isinstance(result, list) else None
        run_matchmaking_health(conn, now=now, pool_refresh_summaries=pool_summaries)

    return _JobRuntime(
        connect_db=connect_db,
        initialize_database=initialize_database,
        post_run=post_run,
    )


def _load_chat_runtime() -> _JobRuntime:
    from chat_system import connect_db, initialize_database  # noqa: PLC0415

    return _JobRuntime(
        connect_db=connect_db,
        initialize_database=initialize_database,
    )


def make_recommendation_job(job_id: str, fn: Callable[..., Any], **kwargs: Any) -> Callable[[], None]:
    return _build_db_job(
        job_id,
        fn,
        kwargs=kwargs,
        subsystem="recommendation",
        ensure_on_path=ensure_recommendation_system_on_path,
        load_runtime=_load_recommendation_runtime,
    )


def make_matchmaking_job(job_id: str, fn: Callable[..., Any], **kwargs: Any) -> Callable[[], None]:
    return _build_db_job(
        job_id,
        fn,
        kwargs=kwargs,
        subsystem="matchmaking",
        ensure_on_path=ensure_matchmaking_system_on_path,
        load_runtime=_load_matchmaking_runtime,
    )


def make_proxy_intro_job(
    job_id: str,
    fn: Callable[..., Any],
    *,
    matchmaking_db: str,
    recommendation_db: str,
) -> Callable[[], None]:
    """Run proxy-intro workers on matchmaking DB with recommendation DB for mirrors."""

    def run(case_conn: Any) -> Any:
        ensure_recommendation_system_on_path()
        from recommendation_system import connect_db as rec_connect, initialize_database as rec_init  # noqa: PLC0415

        rec_conn = rec_connect(recommendation_db)
        try:
            rec_init(rec_conn)
            return fn(case_conn, recommendation_conn=rec_conn)
        finally:
            rec_conn.close()

    return make_matchmaking_job(job_id, run, db=matchmaking_db)


def make_chat_job(job_id: str, fn: Callable[..., Any], **kwargs: Any) -> Callable[[], None]:
    return _build_db_job(
        job_id,
        fn,
        kwargs=kwargs,
        subsystem="chat",
        ensure_on_path=ensure_chat_system_on_path,
        load_runtime=_load_chat_runtime,
    )
