from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import SchedulerSettings
from .jobs import (
    JOB_CHAT_ASYNC_WORKER,
    JOB_CHAT_MAINTENANCE,
    JOB_CHAT_OUTBOX,
    JOB_MM_ASYNC_WORKER,
    JOB_MM_OPEN,
    JOB_MM_OUTBOX,
    JOB_MM_PAIRS,
    JOB_MM_REFRESH,
    JOB_MM_STALE,
    JOB_REC_ASYNC_WORKER,
    JOB_REC_CLOSE_TIMEOUT,
    JOB_REC_DELIVER,
    JOB_REC_DISPATCH,
    JOB_REC_OUTBOX,
    JOB_REC_REFRESH,
    make_chat_job,
    make_matchmaking_job,
    make_proxy_intro_job,
    make_recommendation_job,
)
from .paths import (
    ensure_chat_system_on_path,
    ensure_matchmaking_system_on_path,
    ensure_recommendation_system_on_path,
)

if TYPE_CHECKING:
    from apscheduler.schedulers.blocking import BlockingScheduler

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ConfiguredJobSpec:
    job_id: str
    interval_seconds: int
    build: Callable[[], Callable[[], None]]


def _recommendation_job_specs(settings: SchedulerSettings) -> list[_ConfiguredJobSpec]:
    if not settings.recommendation_db:
        return []

    db = settings.recommendation_db
    built_jobs: dict[str, Callable[[], None]] | None = None

    def get_jobs() -> dict[str, Callable[[], None]]:
        nonlocal built_jobs
        if built_jobs is None:
            ensure_recommendation_system_on_path()
            from recommendation_system import (  # noqa: PLC0415
                deliver_in_app_recommendations,
                refresh_due_subscriptions,
            )
            from recommendation_system.async_tasks import run_recommendation_async_job_worker  # noqa: PLC0415
            from recommendation_system.outbox import run_recommendation_outbox_worker  # noqa: PLC0415

            built_jobs = {
                JOB_REC_ASYNC_WORKER: make_recommendation_job(
                    JOB_REC_ASYNC_WORKER,
                    run_recommendation_async_job_worker,
                    db=db,
                ),
                JOB_REC_OUTBOX: make_recommendation_job(
                    JOB_REC_OUTBOX,
                    run_recommendation_outbox_worker,
                    db=db,
                ),
                JOB_REC_REFRESH: make_recommendation_job(
                    JOB_REC_REFRESH,
                    refresh_due_subscriptions,
                    db=db,
                ),
                JOB_REC_DELIVER: make_recommendation_job(
                    JOB_REC_DELIVER,
                    deliver_in_app_recommendations,
                    db=db,
                ),
            }
        return built_jobs

    return [
        _ConfiguredJobSpec(
            JOB_REC_ASYNC_WORKER,
            settings.recommendation_async_job_sec,
            lambda: get_jobs()[JOB_REC_ASYNC_WORKER],
        ),
        _ConfiguredJobSpec(
            JOB_REC_OUTBOX,
            settings.recommendation_outbox_sec,
            lambda: get_jobs()[JOB_REC_OUTBOX],
        ),
        _ConfiguredJobSpec(
            JOB_REC_REFRESH,
            settings.recommendation_refresh_subscriptions_sec,
            lambda: get_jobs()[JOB_REC_REFRESH],
        ),
        _ConfiguredJobSpec(
            JOB_REC_DELIVER,
            settings.recommendation_deliver_cards_sec,
            lambda: get_jobs()[JOB_REC_DELIVER],
        ),
    ]


def _matchmaking_job_specs(settings: SchedulerSettings) -> list[_ConfiguredJobSpec]:
    if not settings.matchmaking_db:
        return []

    db = settings.matchmaking_db
    built_jobs: dict[str, Callable[[], None]] | None = None

    def get_jobs() -> dict[str, Callable[[], None]]:
        nonlocal built_jobs
        if built_jobs is None:
            ensure_matchmaking_system_on_path()
            from matchmaking_system import (  # noqa: PLC0415
                build_mutual_pairs,
                close_stale_cases,
                open_match_cases,
                refresh_active_pool,
            )
            from matchmaking_system.async_tasks import run_matchmaking_async_job_worker  # noqa: PLC0415
            from matchmaking_system.outbox import run_matchmaking_outbox_worker  # noqa: PLC0415
            from match_domain.proxy_intro_storage import use_matchmaking_storage  # noqa: PLC0415
            from matchmaking_system.proxy_intro import (  # noqa: PLC0415
                close_timed_out_match_cases,
                dispatch_pending_match_cases,
            )

            rec_db = settings.recommendation_db or ""
            built_jobs = {
                JOB_MM_ASYNC_WORKER: make_matchmaking_job(
                    JOB_MM_ASYNC_WORKER,
                    run_matchmaking_async_job_worker,
                    db=db,
                ),
                JOB_MM_OUTBOX: make_matchmaking_job(
                    JOB_MM_OUTBOX,
                    run_matchmaking_outbox_worker,
                    db=db,
                ),
                JOB_MM_REFRESH: make_matchmaking_job(
                    JOB_MM_REFRESH,
                    refresh_active_pool,
                    db=db,
                ),
                JOB_MM_PAIRS: make_matchmaking_job(
                    JOB_MM_PAIRS,
                    build_mutual_pairs,
                    db=db,
                ),
                JOB_MM_OPEN: make_matchmaking_job(
                    JOB_MM_OPEN,
                    open_match_cases,
                    db=db,
                ),
                JOB_MM_STALE: make_matchmaking_job(
                    JOB_MM_STALE,
                    close_stale_cases,
                    db=db,
                ),
            }
            if rec_db:
                if use_matchmaking_storage():
                    built_jobs[JOB_REC_DISPATCH] = make_proxy_intro_job(
                        JOB_REC_DISPATCH,
                        dispatch_pending_match_cases,
                        matchmaking_db=db,
                        recommendation_db=rec_db,
                    )
                    built_jobs[JOB_REC_CLOSE_TIMEOUT] = make_proxy_intro_job(
                        JOB_REC_CLOSE_TIMEOUT,
                        close_timed_out_match_cases,
                        matchmaking_db=db,
                        recommendation_db=rec_db,
                    )
                else:
                    built_jobs[JOB_REC_DISPATCH] = make_recommendation_job(
                        JOB_REC_DISPATCH,
                        dispatch_pending_match_cases,
                        db=rec_db,
                    )
                    built_jobs[JOB_REC_CLOSE_TIMEOUT] = make_recommendation_job(
                        JOB_REC_CLOSE_TIMEOUT,
                        close_timed_out_match_cases,
                        db=rec_db,
                    )
        return built_jobs

    proxy_specs: list[_ConfiguredJobSpec] = []
    if settings.recommendation_db:
        proxy_specs = [
            _ConfiguredJobSpec(
                JOB_REC_DISPATCH,
                settings.recommendation_dispatch_proxy_sec,
                lambda: get_jobs()[JOB_REC_DISPATCH],
            ),
            _ConfiguredJobSpec(
                JOB_REC_CLOSE_TIMEOUT,
                settings.recommendation_close_proxy_timeout_sec,
                lambda: get_jobs()[JOB_REC_CLOSE_TIMEOUT],
            ),
        ]

    return [
        _ConfiguredJobSpec(
            JOB_MM_ASYNC_WORKER,
            settings.matchmaking_async_job_sec,
            lambda: get_jobs()[JOB_MM_ASYNC_WORKER],
        ),
        _ConfiguredJobSpec(
            JOB_MM_OUTBOX,
            settings.matchmaking_outbox_sec,
            lambda: get_jobs()[JOB_MM_OUTBOX],
        ),
        _ConfiguredJobSpec(
            JOB_MM_REFRESH,
            settings.matchmaking_refresh_pool_sec,
            lambda: get_jobs()[JOB_MM_REFRESH],
        ),
        _ConfiguredJobSpec(
            JOB_MM_PAIRS,
            settings.matchmaking_build_pairs_sec,
            lambda: get_jobs()[JOB_MM_PAIRS],
        ),
        _ConfiguredJobSpec(
            JOB_MM_OPEN,
            settings.matchmaking_open_cases_sec,
            lambda: get_jobs()[JOB_MM_OPEN],
        ),
        _ConfiguredJobSpec(
            JOB_MM_STALE,
            settings.matchmaking_close_stale_sec,
            lambda: get_jobs()[JOB_MM_STALE],
        ),
        *proxy_specs,
    ]


def _chat_job_specs(settings: SchedulerSettings) -> list[_ConfiguredJobSpec]:
    if not settings.chat_db:
        return []

    db = settings.chat_db
    built_jobs: dict[str, Callable[[], None]] | None = None

    def get_jobs() -> dict[str, Callable[[], None]]:
        nonlocal built_jobs
        if built_jobs is None:
            ensure_chat_system_on_path()
            from chat_system.async_tasks import run_chat_async_job_worker  # noqa: PLC0415
            from chat_system.maintenance import run_chat_maintenance  # noqa: PLC0415
            from chat_system.outbox import run_chat_outbox_worker  # noqa: PLC0415

            built_jobs = {
                JOB_CHAT_ASYNC_WORKER: make_chat_job(
                    JOB_CHAT_ASYNC_WORKER,
                    run_chat_async_job_worker,
                    db=db,
                ),
                JOB_CHAT_OUTBOX: make_chat_job(
                    JOB_CHAT_OUTBOX,
                    run_chat_outbox_worker,
                    db=db,
                ),
                JOB_CHAT_MAINTENANCE: make_chat_job(
                    JOB_CHAT_MAINTENANCE,
                    run_chat_maintenance,
                    db=db,
                    flush_outbox=False,
                ),
            }
        return built_jobs

    return [
        _ConfiguredJobSpec(
            JOB_CHAT_ASYNC_WORKER,
            settings.chat_async_job_sec,
            lambda: get_jobs()[JOB_CHAT_ASYNC_WORKER],
        ),
        _ConfiguredJobSpec(
            JOB_CHAT_OUTBOX,
            settings.chat_outbox_sec,
            lambda: get_jobs()[JOB_CHAT_OUTBOX],
        ),
        _ConfiguredJobSpec(
            JOB_CHAT_MAINTENANCE,
            settings.chat_maintenance_sec,
            lambda: get_jobs()[JOB_CHAT_MAINTENANCE],
        ),
    ]


def _configured_job_specs(settings: SchedulerSettings) -> list[_ConfiguredJobSpec]:
    return [
        *_recommendation_job_specs(settings),
        *_matchmaking_job_specs(settings),
        *_chat_job_specs(settings),
    ]


def register_jobs(scheduler: BaseScheduler, settings: SchedulerSettings) -> list[str]:
    """Register interval jobs; returns the list of registered job ids."""
    if not settings.recommendation_db:
        logger.warning("HER_SCHED_RECOMMENDATION_DB unset; recommendation scheduler jobs skipped")
    if not settings.matchmaking_db:
        logger.warning("HER_SCHED_MATCHMAKING_DB unset; matchmaking scheduler jobs skipped")
    if not settings.chat_db:
        logger.warning("HER_SCHED_CHAT_DB unset; chat scheduler jobs skipped")

    registered: list[str] = []
    for spec in _configured_job_specs(settings):
        scheduler.add_job(
            spec.build(),
            trigger=IntervalTrigger(seconds=spec.interval_seconds),
            id=spec.job_id,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        registered.append(spec.job_id)
        logger.info("registered job %s every %ss", spec.job_id, spec.interval_seconds)
    return registered


def run_job_once(job_id: str, settings: SchedulerSettings) -> None:
    """Execute a single registered job synchronously (for CLI / tests)."""
    mapping = {spec.job_id: spec for spec in _configured_job_specs(settings)}
    if job_id not in mapping:
        raise KeyError(f"unknown job or subsystem db not configured: {job_id}")
    mapping[job_id].build()()


def all_job_ids(settings: SchedulerSettings) -> list[str]:
    return [spec.job_id for spec in _configured_job_specs(settings)]


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
