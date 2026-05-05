#!/usr/bin/env python3
"""Export all ``chat_messages`` rows for a thread (ordered by ``message_id``) to Markdown or JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_repo_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve()
    for p in (here.parent, *here.parents):
        if (p / "match_domain").is_dir() and (p / "pyproject.toml").is_file():
            env = p / ".env"
            if env.is_file():
                load_dotenv(env, override=True)
            return


_load_repo_dotenv()

_partner_chat_root = Path(__file__).resolve().parents[1]
if str(_partner_chat_root) not in sys.path:
    sys.path.insert(0, str(_partner_chat_root))

from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN, connect_db, row_to_dict  # noqa: E402


def _fetch_messages(conn, thread_id: str) -> list[dict]:
    cur = conn.execute(
        """
        SELECT * FROM chat_messages
        WHERE thread_id = ?
        ORDER BY message_id ASC
        """,
        (thread_id,),
    )
    return [dict(row_to_dict(r)) for r in cur.fetchall()]


def _to_markdown(rows: list[dict], *, thread_id: str) -> str:
    lines: list[str] = [
        f"# 聊天导出 `thread_id={thread_id}`",
        "",
        f"共 {len(rows)} 条消息（含双方可见与仅自己可见等）。",
        "",
    ]
    dyadic = [r for r in rows if r.get("visibility") == "dyadic"]
    other = [r for r in rows if r.get("visibility") != "dyadic"]

    lines.append("## 双方可见（主对话正文）")
    lines.append("")
    if not dyadic:
        lines.append("（无）")
    else:
        for r in dyadic:
            lines.extend(_msg_block(r))
    lines.append("")
    lines.append("## 其他可见性（含用户问助手、助手草稿等）")
    lines.append("")
    if not other:
        lines.append("（无）")
    else:
        for r in other:
            lines.extend(_msg_block(r))
    lines.append("")
    return "\n".join(lines)


def _msg_block(r: dict) -> list[str]:
    mid = r.get("message_id")
    who = r.get("author_id")
    vis = r.get("visibility")
    src = r.get("source")
    to = r.get("message_recipient_id")
    ts = r.get("created_at")
    body = (r.get("body") or "").strip()
    head = f"### #{mid} | {who} | {vis} | {src} | →{to} | {ts}"
    return [head, "", body, ""]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--thread-id", help="chat_threads.thread_id")
    g.add_argument(
        "--roleplay-json",
        type=Path,
        help="``run_dyadic_agent_roleplay.py`` 输出的 JSON（读取其中的 thread_id）",
    )
    p.add_argument("--db", default=DEFAULT_CHAT_TEST_MYSQL_DSN, help="MySQL DSN")
    p.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="markdown=人类可读分区；json=完整行数组",
    )
    p.add_argument("-o", "--output", type=Path, default=None, help="写入文件；默认打印 stdout")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.roleplay_json:
        data = json.loads(args.roleplay_json.read_text(encoding="utf-8"))
        thread_id = str(data["thread_id"])
    else:
        thread_id = str(args.thread_id)

    conn = connect_db(args.db)
    try:
        rows = _fetch_messages(conn, thread_id)
    finally:
        conn.close()

    if args.format == "json":
        out = json.dumps(rows, ensure_ascii=False, indent=2, default=str)
    else:
        out = _to_markdown(rows, thread_id=thread_id)

    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
