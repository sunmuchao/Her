"""Per-case chat view for unified timeline responses."""

from __future__ import annotations

from typing import Any

from .service import get_thread_by_case, list_messages
from .summaries import get_thread_summary


def build_chat_timeline(
    conn,
    case_id: str,
    viewer_id: str,
    *,
    message_limit: int = 50,
) -> dict[str, Any]:
    thread = get_thread_by_case(conn, case_id)
    if not thread:
        return {"thread": None, "messages": [], "summary": None}
    msgs = list_messages(conn, thread["thread_id"], viewer_id, limit=message_limit)
    summary = get_thread_summary(conn, thread["thread_id"])
    return {"thread": thread, "messages": msgs, "summary": summary}


__all__ = ["build_chat_timeline"]
