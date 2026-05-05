"""Optional LLM assistant replies via OpenAI-compatible Chat Completions API."""

from __future__ import annotations

import os
from typing import Any

_VIS_DYADIC = "dyadic"


def build_dyadic_context_for_assistant(conn, thread_id: str, *, limit: int = 20) -> str:
    lim = max(1, min(int(limit), 50))
    cur = conn.execute(
        """
        SELECT author_id, body FROM chat_messages
        WHERE thread_id = ? AND visibility = ?
        ORDER BY message_id DESC LIMIT ?
        """,
        (thread_id, _VIS_DYADIC, lim),
    )
    rows = list(reversed(cur.fetchall()))
    return "\n".join(f"{r['author_id']}: {r['body']}" for r in rows)


def generate_assistant_reply(*, user_query: str, thread_context: str) -> str | None:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        return None
    model = (os.environ.get("HER_CHAT_ASSISTANT_MODEL") or "gpt-4o-mini").strip()
    base = (
        os.environ.get("HER_CHAT_ASSISTANT_BASE_URL") or os.environ.get("OPENAI_BASE_URL") or ""
    ).strip()
    try:
        from openai import OpenAI
    except ImportError:
        return None
    client_kwargs: dict[str, str] = {"api_key": key}
    if base:
        client_kwargs["base_url"] = base
    client = OpenAI(**client_kwargs)
    system = (
        "你是相亲/交友场景下的对话助手。根据最近的双方可见聊天记录与用户问题，"
        "给出简短、得体、可操作的建议或草稿回复（中文）。不要编造用户未提及的事实。"
    )
    user_block = f"最近对话（双方可见）：\n{thread_context or '（暂无）'}\n\n用户问题：{user_query}"
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_block},
            ],
            max_tokens=500,
            temperature=0.4,
        )
        choice = resp.choices[0].message.content
        out = (choice or "").strip()
        return out or None
    except Exception:
        return None


__all__ = ["build_dyadic_context_for_assistant", "generate_assistant_reply"]
