"""Recommendation outbox worker wrappers built on the shared runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from match_domain.outbox_runtime import (  # noqa: E402
    claim_pending_outbox_batch,
    get_outbox_row,
    list_failed_outbox,
    list_pending_outbox,
    list_processing_outbox,
    list_retry_pending_outbox,
    mark_pending_outbox_published_batch,
    recover_stale_outbox_claims,
    requeue_outbox_rows,
    resolve_outbox_consume_config as resolve_shared_outbox_consume_config,
    run_outbox_worker,
    serve_outbox_worker,
    summarize_outbox,
)


def resolve_outbox_consume_config() -> dict[str, Any]:
    return resolve_shared_outbox_consume_config(
        env_prefix="HER_RECOMMENDATION_OUTBOX",
        system="recommendation",
        default_worker_name="recommendation-outbox-worker",
    )


def run_recommendation_outbox_worker(conn, **kwargs: Any) -> dict[str, Any]:
    return run_outbox_worker(
        conn,
        system="recommendation",
        config=resolve_outbox_consume_config(),
        **kwargs,
    )


def serve_recommendation_outbox_worker(conn, **kwargs: Any) -> dict[str, Any]:
    return serve_outbox_worker(
        conn,
        system="recommendation",
        config=resolve_outbox_consume_config(),
        **kwargs,
    )


__all__ = [
    "claim_pending_outbox_batch",
    "get_outbox_row",
    "list_failed_outbox",
    "list_pending_outbox",
    "list_processing_outbox",
    "list_retry_pending_outbox",
    "mark_pending_outbox_published_batch",
    "recover_stale_outbox_claims",
    "requeue_outbox_rows",
    "resolve_outbox_consume_config",
    "run_recommendation_outbox_worker",
    "serve_recommendation_outbox_worker",
    "summarize_outbox",
]
