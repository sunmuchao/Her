"""Matchmaking outbox worker wrappers built on the shared runtime."""

from __future__ import annotations

from pathlib import Path

from her_external_systems import build_external_outbox_helpers

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
    summarize_outbox,
)


(
    resolve_outbox_consume_config,
    run_matchmaking_outbox_worker,
    serve_matchmaking_outbox_worker,
) = build_external_outbox_helpers(
    env_prefix="HER_MATCHMAKING_OUTBOX",
    system="matchmaking",
    default_worker_name="matchmaking-outbox-worker",
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
    "run_matchmaking_outbox_worker",
    "serve_matchmaking_outbox_worker",
    "summarize_outbox",
]
