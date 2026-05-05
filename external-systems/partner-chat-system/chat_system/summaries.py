"""Rolling thread summaries (concat of recent dyadic messages; see architecture §Phase 3)."""

from __future__ import annotations

from typing import Any

from .service import VIS_DYADIC, current_time, get_thread
from .storage import row_to_dict


def get_thread_summary(conn, thread_id: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT * FROM chat_thread_summaries WHERE thread_id = ? LIMIT 1",
        (thread_id,),
    )
    row = row_to_dict(cur.fetchone())
    return dict(row) if row else None


def refresh_thread_summary_concat(
    conn,
    thread_id: str,
    *,
    message_limit: int = 25,
    now=None,
) -> dict[str, Any] | None:
    thread = get_thread(conn, thread_id)
    if not thread:
        return None
    lim = max(1, min(int(message_limit), 100))
    cur = conn.execute(
        """
        SELECT message_id, author_id, body, created_at FROM chat_messages
        WHERE thread_id = ? AND visibility = ?
        ORDER BY message_id DESC LIMIT ?
        """,
        (thread_id, VIS_DYADIC, lim),
    )
    rows = list(reversed(cur.fetchall()))
    ts = current_time(now)
    if not rows:
        summary_text = ""
        last_mid: int | None = None
    else:
        summary_text = "\n".join(f"{r['author_id']}: {r['body']}" for r in rows)
        last_mid = int(rows[-1]["message_id"])

    existing = conn.execute(
        "SELECT thread_id FROM chat_thread_summaries WHERE thread_id = ? LIMIT 1",
        (thread_id,),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE chat_thread_summaries
            SET summary_text = ?, summary_mode = ?, last_message_id = ?, updated_at = ?
            WHERE thread_id = ?
            """,
            (summary_text, "concat", last_mid, ts, thread_id),
        )
    else:
        conn.execute(
            """
            INSERT INTO chat_thread_summaries (
              thread_id, summary_text, summary_mode, last_message_id, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (thread_id, summary_text, "concat", last_mid, ts),
        )
    conn.commit()
    row = get_thread_summary(conn, thread_id)
    return row


def refresh_stale_thread_summaries(
    conn,
    *,
    max_threads: int = 30,
    messages_per_thread: int = 25,
    now=None,
) -> dict[str, Any]:
    cap = max(1, min(int(max_threads), 200))
    cur = conn.execute(
        "SELECT thread_id FROM chat_threads ORDER BY updated_at DESC LIMIT ?",
        (cap,),
    )
    n = 0
    for r in cur.fetchall():
        refresh_thread_summary_concat(
            conn, str(r["thread_id"]), message_limit=messages_per_thread, now=now
        )
        n += 1
    return {"threads_refreshed": n}


__all__ = [
    "get_thread_summary",
    "refresh_stale_thread_summaries",
    "refresh_thread_summary_concat",
]
