from __future__ import annotations

import os
from dataclasses import dataclass


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class SchedulerSettings:
    """Load MySQL DSNs for outer systems and per-job intervals from the environment."""

    recommendation_db: str | None
    matchmaking_db: str | None
    chat_db: str | None
    recommendation_refresh_subscriptions_sec: int
    recommendation_deliver_cards_sec: int
    recommendation_dispatch_proxy_sec: int
    recommendation_close_proxy_timeout_sec: int
    matchmaking_refresh_pool_sec: int
    matchmaking_build_pairs_sec: int
    matchmaking_open_cases_sec: int
    matchmaking_close_stale_sec: int
    chat_maintenance_sec: int

    @classmethod
    def from_environ(cls) -> SchedulerSettings:
        rec_db = os.environ.get("HER_SCHED_RECOMMENDATION_DB") or None
        mm_db = os.environ.get("HER_SCHED_MATCHMAKING_DB") or None
        chat_db = os.environ.get("HER_SCHED_CHAT_DB") or None
        return cls(
            recommendation_db=rec_db,
            matchmaking_db=mm_db,
            chat_db=chat_db,
            recommendation_refresh_subscriptions_sec=_env_int("HER_SCHED_REFRESH_SUBSCRIPTIONS_SEC", 300),
            recommendation_deliver_cards_sec=_env_int("HER_SCHED_DELIVER_CARDS_SEC", 60),
            recommendation_dispatch_proxy_sec=_env_int("HER_SCHED_DISPATCH_PROXY_SEC", 120),
            recommendation_close_proxy_timeout_sec=_env_int("HER_SCHED_CLOSE_PROXY_TIMEOUT_SEC", 300),
            matchmaking_refresh_pool_sec=_env_int("HER_SCHED_MM_REFRESH_POOL_SEC", 600),
            matchmaking_build_pairs_sec=_env_int("HER_SCHED_MM_BUILD_PAIRS_SEC", 300),
            matchmaking_open_cases_sec=_env_int("HER_SCHED_MM_OPEN_CASES_SEC", 120),
            matchmaking_close_stale_sec=_env_int("HER_SCHED_MM_CLOSE_STALE_SEC", 600),
            chat_maintenance_sec=_env_int("HER_SCHED_CHAT_MAINTENANCE_SEC", 120),
        )
