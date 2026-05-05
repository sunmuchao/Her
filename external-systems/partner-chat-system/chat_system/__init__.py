"""Partner chat subsystem: threads, messages, assistant side-channel (MVP)."""

from pathlib import Path

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from .maintenance import run_chat_maintenance
from .outbox_admin import list_pending_outbox
from .service import (
    ASSISTANT_AUTHOR_ID,
    adopt_draft,
    assistant_query,
    current_time,
    get_or_create_thread,
    get_thread,
    get_thread_by_case,
    list_messages,
    post_message,
)
from .summaries import get_thread_summary
from .storage import (
    connect_db,
    initialize_database,
    reset_all_tables,
)
from .timeline import build_chat_timeline

__all__ = [
    "ASSISTANT_AUTHOR_ID",
    "adopt_draft",
    "assistant_query",
    "build_chat_timeline",
    "connect_db",
    "current_time",
    "get_or_create_thread",
    "get_thread",
    "get_thread_summary",
    "get_thread_by_case",
    "initialize_database",
    "list_messages",
    "list_pending_outbox",
    "post_message",
    "reset_all_tables",
    "run_chat_maintenance",
]
