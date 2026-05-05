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
from .risk import (
    get_risk_case,
    list_member_reports,
    list_risk_cases,
    review_risk_case,
    submit_member_report,
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
    "get_risk_case",
    "get_thread",
    "get_thread_summary",
    "get_thread_by_case",
    "initialize_database",
    "list_messages",
    "list_member_reports",
    "list_pending_outbox",
    "list_risk_cases",
    "post_message",
    "reset_all_tables",
    "review_risk_case",
    "run_chat_maintenance",
    "submit_member_report",
]
