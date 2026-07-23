from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _sched_db(sched_var: str, partner_var: str) -> str | None:
    """Scheduler DSN; falls back to the matching PARTNER_*_DB used by gateway/services."""
    raw = os.environ.get(sched_var) or os.environ.get(partner_var) or ""
    return raw.strip() or None


def _photo_analysis_enabled() -> bool:
    raw = os.environ.get("HER_PHOTO_ANALYSIS_ENABLED") or ""
    return raw.strip().lower() in {"1", "true", "on", "yes"}


@dataclass(frozen=True)
class SchedulerSettings:
    """Load MySQL DSNs for outer systems and per-job intervals from the environment."""

    recommendation_db: str | None
    matchmaking_db: str | None
    chat_db: str | None
    photo_analysis_db: str | None
    recommendation_async_job_sec: int
    recommendation_outbox_sec: int
    recommendation_refresh_subscriptions_sec: int
    recommendation_deliver_cards_sec: int
    recommendation_dispatch_proxy_sec: int
    recommendation_close_proxy_timeout_sec: int
    matchmaking_async_job_sec: int
    matchmaking_outbox_sec: int
    matchmaking_refresh_pool_sec: int
    matchmaking_build_pairs_sec: int
    matchmaking_open_cases_sec: int
    matchmaking_close_stale_sec: int
    chat_async_job_sec: int
    chat_maintenance_sec: int
    chat_outbox_sec: int
    photo_analysis_interval_sec: int

    @classmethod
    def from_environ(cls) -> SchedulerSettings:
        rec_db = _sched_db("HER_SCHED_RECOMMENDATION_DB", "PARTNER_RECOMMENDATION_DB")
        mm_db = _sched_db("HER_SCHED_MATCHMAKING_DB", "PARTNER_MATCHMAKING_DB")
        chat_db = _sched_db("HER_SCHED_CHAT_DB", "PARTNER_CHAT_DB")
        photo_db = None
        if _photo_analysis_enabled():
            photo_db = _sched_db("HER_SCHED_PHOTO_ANALYSIS_DB", "PERSONA_MEMORY_MYSQL_SOURCE")
        return cls(
            recommendation_db=rec_db,
            matchmaking_db=mm_db,
            chat_db=chat_db,
            photo_analysis_db=photo_db,
            recommendation_async_job_sec=_env_int("HER_SCHED_RECOMMENDATION_ASYNC_JOB_SEC", 10),
            recommendation_outbox_sec=_env_int("HER_SCHED_RECOMMENDATION_OUTBOX_SEC", 30),
            recommendation_refresh_subscriptions_sec=_env_int("HER_SCHED_REFRESH_SUBSCRIPTIONS_SEC", 300),
            recommendation_deliver_cards_sec=_env_int("HER_SCHED_DELIVER_CARDS_SEC", 60),
            recommendation_dispatch_proxy_sec=_env_int("HER_SCHED_DISPATCH_PROXY_SEC", 120),
            recommendation_close_proxy_timeout_sec=_env_int("HER_SCHED_CLOSE_PROXY_TIMEOUT_SEC", 300),
            matchmaking_async_job_sec=_env_int("HER_SCHED_MATCHMAKING_ASYNC_JOB_SEC", 10),
            matchmaking_outbox_sec=_env_int("HER_SCHED_MATCHMAKING_OUTBOX_SEC", 30),
            matchmaking_refresh_pool_sec=_env_int("HER_SCHED_MM_REFRESH_POOL_SEC", 600),
            matchmaking_build_pairs_sec=_env_int("HER_SCHED_MM_BUILD_PAIRS_SEC", 300),
            matchmaking_open_cases_sec=_env_int("HER_SCHED_MM_OPEN_CASES_SEC", 120),
            matchmaking_close_stale_sec=_env_int("HER_SCHED_MM_CLOSE_STALE_SEC", 600),
            chat_async_job_sec=_env_int("HER_SCHED_CHAT_ASYNC_JOB_SEC", 10),
            chat_maintenance_sec=_env_int("HER_SCHED_CHAT_MAINTENANCE_SEC", 120),
            chat_outbox_sec=_env_int("HER_SCHED_CHAT_OUTBOX_SEC", 15),
            photo_analysis_interval_sec=_env_int("HER_SCHED_PHOTO_ANALYSIS_INTERVAL_SEC", 10),
        )
