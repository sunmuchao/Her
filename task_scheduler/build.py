from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import SchedulerSettings
from .jobs import JOB_CHAT_MAINTENANCE, make_chat_job, make_matchmaking_job, make_recommendation_job
from .paths import (
    ensure_chat_system_on_path,
    ensure_matchmaking_system_on_path,
    ensure_recommendation_system_on_path,
)

if TYPE_CHECKING:
    from apscheduler.schedulers.blocking import BlockingScheduler

logger = logging.getLogger(__name__)

JOB_REC_REFRESH = "recommendation.refresh_saved_searches"
JOB_REC_DELIVER = "recommendation.deliver_in_app_recommendations"
JOB_REC_DISPATCH = "recommendation.dispatch_proxy_intro_outreach"
JOB_REC_CLOSE_TIMEOUT = "recommendation.close_timed_out_proxy_cases"
JOB_MM_REFRESH = "matchmaking.refresh_active_pool"
JOB_MM_PAIRS = "matchmaking.build_mutual_pairs"
JOB_MM_OPEN = "matchmaking.open_match_cases"
JOB_MM_STALE = "matchmaking.close_stale_cases"


def register_jobs(scheduler: BaseScheduler, settings: SchedulerSettings) -> list[str]:
    """Register interval jobs; returns the list of registered job ids."""
    registered: list[str] = []

    if settings.recommendation_db:
        ensure_recommendation_system_on_path()
        from recommendation_system import (  # noqa: PLC0415
            close_timed_out_match_cases,
            deliver_in_app_recommendations,
            dispatch_pending_match_cases,
            refresh_due_subscriptions,
        )

        db = settings.recommendation_db
        specs: list[tuple[str, int, Callable[[], None]]] = [
            (
                JOB_REC_REFRESH,
                settings.recommendation_refresh_subscriptions_sec,
                make_recommendation_job(
                    JOB_REC_REFRESH,
                    refresh_due_subscriptions,
                    db=db,
                ),
            ),
            (
                JOB_REC_DELIVER,
                settings.recommendation_deliver_cards_sec,
                make_recommendation_job(
                    JOB_REC_DELIVER,
                    deliver_in_app_recommendations,
                    db=db,
                ),
            ),
            (
                JOB_REC_DISPATCH,
                settings.recommendation_dispatch_proxy_sec,
                make_recommendation_job(
                    JOB_REC_DISPATCH,
                    dispatch_pending_match_cases,
                    db=db,
                ),
            ),
            (
                JOB_REC_CLOSE_TIMEOUT,
                settings.recommendation_close_proxy_timeout_sec,
                make_recommendation_job(
                    JOB_REC_CLOSE_TIMEOUT,
                    close_timed_out_match_cases,
                    db=db,
                ),
            ),
        ]
        for job_id, seconds, fn in specs:
            scheduler.add_job(
                fn,
                trigger=IntervalTrigger(seconds=seconds),
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            registered.append(job_id)
            logger.info("registered job %s every %ss", job_id, seconds)
    else:
        logger.warning("HER_SCHED_RECOMMENDATION_DB unset; recommendation scheduler jobs skipped")

    if settings.matchmaking_db:
        ensure_matchmaking_system_on_path()
        from matchmaking_system import (  # noqa: PLC0415
            build_mutual_pairs,
            close_stale_cases,
            open_match_cases,
            refresh_active_pool,
        )

        db = settings.matchmaking_db
        mm_specs: list[tuple[str, int, Callable[[], None]]] = [
            (
                JOB_MM_REFRESH,
                settings.matchmaking_refresh_pool_sec,
                make_matchmaking_job(JOB_MM_REFRESH, refresh_active_pool, db=db),
            ),
            (
                JOB_MM_PAIRS,
                settings.matchmaking_build_pairs_sec,
                make_matchmaking_job(JOB_MM_PAIRS, build_mutual_pairs, db=db),
            ),
            (
                JOB_MM_OPEN,
                settings.matchmaking_open_cases_sec,
                make_matchmaking_job(JOB_MM_OPEN, open_match_cases, db=db),
            ),
            (
                JOB_MM_STALE,
                settings.matchmaking_close_stale_sec,
                make_matchmaking_job(JOB_MM_STALE, close_stale_cases, db=db),
            ),
        ]
        for job_id, seconds, fn in mm_specs:
            scheduler.add_job(
                fn,
                trigger=IntervalTrigger(seconds=seconds),
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )
            registered.append(job_id)
            logger.info("registered job %s every %ss", job_id, seconds)
    else:
        logger.warning("HER_SCHED_MATCHMAKING_DB unset; matchmaking scheduler jobs skipped")

    if settings.chat_db:
        ensure_chat_system_on_path()
        from chat_system.maintenance import run_chat_maintenance  # noqa: PLC0415

        db = settings.chat_db
        scheduler.add_job(
            make_chat_job(JOB_CHAT_MAINTENANCE, run_chat_maintenance, db=db),
            trigger=IntervalTrigger(seconds=settings.chat_maintenance_sec),
            id=JOB_CHAT_MAINTENANCE,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        registered.append(JOB_CHAT_MAINTENANCE)
        logger.info("registered job %s every %ss", JOB_CHAT_MAINTENANCE, settings.chat_maintenance_sec)
    else:
        logger.warning("HER_SCHED_CHAT_DB unset; chat scheduler jobs skipped")

    return registered


def run_job_once(job_id: str, settings: SchedulerSettings) -> None:
    """Execute a single registered job synchronously (for CLI / tests)."""
    mapping: dict[str, Callable[[], None]] = {}

    if settings.recommendation_db:
        ensure_recommendation_system_on_path()
        from recommendation_system import (  # noqa: PLC0415
            close_timed_out_match_cases,
            deliver_in_app_recommendations,
            dispatch_pending_match_cases,
            refresh_due_subscriptions,
        )

        db = settings.recommendation_db
        mapping[JOB_REC_REFRESH] = make_recommendation_job(
            JOB_REC_REFRESH, refresh_due_subscriptions, db=db
        )
        mapping[JOB_REC_DELIVER] = make_recommendation_job(
            JOB_REC_DELIVER, deliver_in_app_recommendations, db=db
        )
        mapping[JOB_REC_DISPATCH] = make_recommendation_job(
            JOB_REC_DISPATCH, dispatch_pending_match_cases, db=db
        )
        mapping[JOB_REC_CLOSE_TIMEOUT] = make_recommendation_job(
            JOB_REC_CLOSE_TIMEOUT, close_timed_out_match_cases, db=db
        )

    if settings.matchmaking_db:
        ensure_matchmaking_system_on_path()
        from matchmaking_system import (  # noqa: PLC0415
            build_mutual_pairs,
            close_stale_cases,
            open_match_cases,
            refresh_active_pool,
        )

        db = settings.matchmaking_db
        mapping[JOB_MM_REFRESH] = make_matchmaking_job(JOB_MM_REFRESH, refresh_active_pool, db=db)
        mapping[JOB_MM_PAIRS] = make_matchmaking_job(JOB_MM_PAIRS, build_mutual_pairs, db=db)
        mapping[JOB_MM_OPEN] = make_matchmaking_job(JOB_MM_OPEN, open_match_cases, db=db)
        mapping[JOB_MM_STALE] = make_matchmaking_job(JOB_MM_STALE, close_stale_cases, db=db)

    if settings.chat_db:
        ensure_chat_system_on_path()
        from chat_system.maintenance import run_chat_maintenance  # noqa: PLC0415

        mapping[JOB_CHAT_MAINTENANCE] = make_chat_job(JOB_CHAT_MAINTENANCE, run_chat_maintenance, db=settings.chat_db)

    if job_id not in mapping:
        raise KeyError(f"unknown job or subsystem db not configured: {job_id}")
    mapping[job_id]()


def all_job_ids(settings: SchedulerSettings) -> list[str]:
    ids: list[str] = []
    if settings.recommendation_db:
        ids.extend(
            [
                JOB_REC_REFRESH,
                JOB_REC_DELIVER,
                JOB_REC_DISPATCH,
                JOB_REC_CLOSE_TIMEOUT,
            ]
        )
    if settings.matchmaking_db:
        ids.extend([JOB_MM_REFRESH, JOB_MM_PAIRS, JOB_MM_OPEN, JOB_MM_STALE])
    if settings.chat_db:
        ids.append(JOB_CHAT_MAINTENANCE)
    return ids


def create_blocking_scheduler(settings: SchedulerSettings) -> BlockingScheduler:
    from apscheduler.schedulers.blocking import BlockingScheduler  # noqa: PLC0415

    scheduler = BlockingScheduler()
    registered = register_jobs(scheduler, settings)
    if not registered:
        raise RuntimeError(
            "No scheduler jobs registered. Set HER_SCHED_RECOMMENDATION_DB, "
            "HER_SCHED_MATCHMAKING_DB, and/or HER_SCHED_CHAT_DB to MySQL DSNs."
        )
    return scheduler
