"""Chat outbox worker wrappers built on the shared runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    mark_claimed_outbox_rows_published,
    mark_outbox_row_retry_pending,
    mark_outbox_rows_published,
    mark_pending_outbox_published_batch,
    recover_stale_outbox_claims,
    requeue_outbox_rows,
    summarize_outbox,
)
from .outbox_consumer import chat_outbox_event_handler  # noqa: E402


def _enrich_chat_worker_result(result: dict[str, Any]) -> dict[str, Any]:
    agent_tasks_enqueued = 0
    for batch in list(result.get("batches") or []):
        refs = list(batch.get("handler_results") or [])
        enqueued = len([item for item in refs if item])
        batch["agent_tasks_enqueued"] = enqueued
        batch["agent_task_refs"] = refs
        agent_tasks_enqueued += enqueued
    for cycle in list(result.get("cycles") or []):
        cycle_totals = dict(cycle.get("totals") or {})
        cycle_agent = 0
        for batch in list(cycle.get("batches") or []):
            refs = list(batch.get("handler_results") or [])
            enqueued = len([item for item in refs if item])
            batch["agent_tasks_enqueued"] = enqueued
            batch["agent_task_refs"] = refs
            cycle_agent += enqueued
        cycle_totals["agent_tasks_enqueued"] = cycle_agent
        cycle["totals"] = cycle_totals
    totals = dict(result.get("totals") or {})
    if "batches" in result:
        totals["agent_tasks_enqueued"] = agent_tasks_enqueued
    elif "cycles" in result:
        totals["agent_tasks_enqueued"] = sum(
            int((cycle.get("totals") or {}).get("agent_tasks_enqueued") or 0)
            for cycle in list(result.get("cycles") or [])
        )
    result["totals"] = totals
    return result


(
    resolve_outbox_consume_config,
    run_chat_outbox_worker,
    serve_chat_outbox_worker,
) = build_external_outbox_helpers(
    env_prefix="HER_CHAT_OUTBOX",
    system="chat",
    default_worker_name="chat-outbox-worker",
    handler=chat_outbox_event_handler,
    enrich_worker_result=_enrich_chat_worker_result,
)


__all__ = [
    "claim_pending_outbox_batch",
    "get_outbox_row",
    "list_failed_outbox",
    "list_pending_outbox",
    "list_processing_outbox",
    "list_retry_pending_outbox",
    "mark_claimed_outbox_rows_published",
    "mark_outbox_row_retry_pending",
    "mark_outbox_rows_published",
    "mark_pending_outbox_published_batch",
    "recover_stale_outbox_claims",
    "requeue_outbox_rows",
    "resolve_outbox_consume_config",
    "run_chat_outbox_worker",
    "serve_chat_outbox_worker",
    "summarize_outbox",
]
