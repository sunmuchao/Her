from __future__ import annotations

import json
import logging
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
JOB_REC_OUTBOX = "recommendation.outbox_worker"
JOB_REC_ASYNC_WORKER = "recommendation.async_job_worker"
JOB_MM_REFRESH = "matchmaking.refresh_active_pool"
JOB_MM_OUTBOX = "matchmaking.outbox_worker"
JOB_MM_ASYNC_WORKER = "matchmaking.async_job_worker"
JOB_CHAT_MAINTENANCE = "chat.maintenance"
JOB_CHAT_OUTBOX = "chat.outbox_worker"
JOB_CHAT_ASYNC_WORKER = "chat.async_job_worker"


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


def make_recommendation_job(job_id: str, fn: Callable[..., Any], **kwargs: Any) -> Callable[[], None]:
    def run() -> None:
        ensure_recommendation_system_on_path()
        from observability import alert_signal  # noqa: PLC0415
        from observability.health import run_recommendation_health  # noqa: PLC0415
        from recommendation_system import connect_db, initialize_database  # noqa: PLC0415

        db_path = kwargs.get("db")
        if not db_path:
            raise RuntimeError("recommendation job requires db path")
        try:
            conn = connect_db(db_path)
        except Exception as exc:
            alert_signal(
                "system.db_unreachable",
                str(exc),
                severity="critical",
                subsystem="recommendation",
                dsn_hint=_safe_dsn_hint(str(db_path)),
                error_type=type(exc).__name__,
            )
            raise
        try:
            initialize_database(conn)
            result = fn(conn, **{k: v for k, v in kwargs.items() if k != "db"})
            _log_summary(job_id, result)
            now = datetime.now()
            if job_id == JOB_REC_REFRESH and isinstance(result, dict):
                run_recommendation_health(
                    conn,
                    now=now,
                    refresh_summaries=result.get("summaries"),
                    refresh_errors=result.get("errors"),
                )
            elif job_id.startswith("recommendation."):
                run_recommendation_health(conn, now=now)
        finally:
            conn.close()

    return run


def make_matchmaking_job(job_id: str, fn: Callable[..., Any], **kwargs: Any) -> Callable[[], None]:
    def run() -> None:
        ensure_matchmaking_system_on_path()
        from observability import alert_signal  # noqa: PLC0415
        from observability.health import run_matchmaking_health  # noqa: PLC0415
        from matchmaking_system import connect_db, initialize_database  # noqa: PLC0415

        db_path = kwargs.get("db")
        if not db_path:
            raise RuntimeError("matchmaking job requires db path")
        try:
            conn = connect_db(db_path)
        except Exception as exc:
            alert_signal(
                "system.db_unreachable",
                str(exc),
                severity="critical",
                subsystem="matchmaking",
                dsn_hint=_safe_dsn_hint(str(db_path)),
                error_type=type(exc).__name__,
            )
            raise
        try:
            initialize_database(conn)
            result = fn(conn, **{k: v for k, v in kwargs.items() if k != "db"})
            _log_summary(job_id, result)
            now = datetime.now()
            pool_summaries = result if job_id == JOB_MM_REFRESH and isinstance(result, list) else None
            run_matchmaking_health(conn, now=now, pool_refresh_summaries=pool_summaries)
        finally:
            conn.close()

    return run


def make_chat_job(job_id: str, fn: Callable[..., Any], **kwargs: Any) -> Callable[[], None]:
    def run() -> None:
        ensure_chat_system_on_path()
        from observability import alert_signal  # noqa: PLC0415
        from chat_system import connect_db, initialize_database  # noqa: PLC0415

        db_path = kwargs.get("db")
        if not db_path:
            raise RuntimeError("chat job requires db path")
        try:
            conn = connect_db(db_path)
        except Exception as exc:
            alert_signal(
                "system.db_unreachable",
                str(exc),
                severity="critical",
                subsystem="chat",
                dsn_hint=_safe_dsn_hint(str(db_path)),
                error_type=type(exc).__name__,
            )
            raise
        try:
            initialize_database(conn)
            result = fn(conn, **{k: v for k, v in kwargs.items() if k != "db"})
            _log_summary(job_id, result)
        finally:
            conn.close()

    return run
