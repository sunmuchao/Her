"""Partner chat subsystem: threads, messages, assistant side-channel (MVP)."""

from pathlib import Path

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from .coaching_jobs import (
    list_pending_coaching_entry_jobs,
    process_pending_coaching_entry_jobs,
)
from .maintenance import run_chat_maintenance
from .mode_router import fast_mode_route
from .outbox_admin import list_pending_outbox
from .service import (
    ASSISTANT_AUTHOR_ID,
    SRC_AGENT_HINT_ENTRY,
    adopt_draft,
    assistant_mode_route,
    assistant_open_coaching_entry,
    assistant_proactive_hint,
    assistant_query,
    current_time,
    get_or_create_thread,
    get_thread,
    get_thread_by_case,
    list_messages,
    post_message,
)
from .risk import (
    build_thread_risk_overview,
    get_risk_case,
    list_member_reports,
    list_meeting_feedback,
    list_risk_cases,
    list_risk_signals,
    review_risk_case,
    submit_meeting_feedback,
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
    "SRC_AGENT_HINT_ENTRY",
    "adopt_draft",
    "assistant_mode_route",
    "assistant_open_coaching_entry",
    "assistant_proactive_hint",
    "assistant_query",
    "build_thread_risk_overview",
    "build_chat_timeline",
    "connect_db",
    "current_time",
    "fast_mode_route",
    "get_or_create_thread",
    "get_risk_case",
    "get_thread",
    "get_thread_summary",
    "get_thread_by_case",
    "initialize_database",
    "list_pending_coaching_entry_jobs",
    "list_messages",
    "list_member_reports",
    "list_meeting_feedback",
    "list_pending_outbox",
    "list_risk_cases",
    "list_risk_signals",
    "post_message",
    "process_pending_coaching_entry_jobs",
    "reset_all_tables",
    "review_risk_case",
    "run_chat_maintenance",
    "submit_meeting_feedback",
    "submit_member_report",
]
