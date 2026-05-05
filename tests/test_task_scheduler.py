from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

from task_scheduler.build import all_job_ids, register_jobs
from task_scheduler.config import SchedulerSettings


def test_settings_defaults() -> None:
    with mock.patch.dict(os.environ, {}, clear=True):
        s = SchedulerSettings.from_environ()
        assert s.recommendation_db is None
        assert s.matchmaking_db is None
        assert s.chat_db is None
        assert s.recommendation_refresh_subscriptions_sec == 300


def test_all_job_ids_respects_env() -> None:
    s = SchedulerSettings(
        recommendation_db="/tmp/rec.db",
        matchmaking_db=None,
        chat_db=None,
        recommendation_refresh_subscriptions_sec=300,
        recommendation_deliver_cards_sec=60,
        recommendation_dispatch_proxy_sec=120,
        recommendation_close_proxy_timeout_sec=300,
        matchmaking_refresh_pool_sec=600,
        matchmaking_build_pairs_sec=300,
        matchmaking_open_cases_sec=120,
        matchmaking_close_stale_sec=600,
        chat_maintenance_sec=120,
    )
    ids = all_job_ids(s)
    assert "recommendation.refresh_saved_searches" in ids
    assert "matchmaking.refresh_active_pool" not in ids


def test_register_jobs_skips_without_db_paths() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    s = SchedulerSettings(
        recommendation_db=None,
        matchmaking_db=None,
        chat_db=None,
        recommendation_refresh_subscriptions_sec=1,
        recommendation_deliver_cards_sec=1,
        recommendation_dispatch_proxy_sec=1,
        recommendation_close_proxy_timeout_sec=1,
        matchmaking_refresh_pool_sec=1,
        matchmaking_build_pairs_sec=1,
        matchmaking_open_cases_sec=1,
        matchmaking_close_stale_sec=1,
        chat_maintenance_sec=120,
    )
    sched = BlockingScheduler()
    registered = register_jobs(sched, s)
    assert registered == []


def test_register_jobs_recommendation(tmp_path: Path) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler

    db = "mysql://root@127.0.0.1:3307/her_recommendation_test"
    s = SchedulerSettings(
        recommendation_db=db,
        matchmaking_db=None,
        chat_db=None,
        recommendation_refresh_subscriptions_sec=30,
        recommendation_deliver_cards_sec=30,
        recommendation_dispatch_proxy_sec=30,
        recommendation_close_proxy_timeout_sec=30,
        matchmaking_refresh_pool_sec=30,
        matchmaking_build_pairs_sec=30,
        matchmaking_open_cases_sec=30,
        matchmaking_close_stale_sec=30,
        chat_maintenance_sec=120,
    )
    sched = BlockingScheduler()
    registered = register_jobs(sched, s)
    assert len(registered) == 4
    assert sched.get_job("recommendation.refresh_saved_searches") is not None
