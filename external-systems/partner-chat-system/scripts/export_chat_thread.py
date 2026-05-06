#!/usr/bin/env python3
"""Export a thread to Markdown or JSON, with optional roleplay evaluation summary."""

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

from chat_system.reporting import build_roleplay_report_summary, build_thread_export_markdown  # noqa: E402
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
    roleplay_result: dict | None = None
    if args.roleplay_json:
        roleplay_result = json.loads(args.roleplay_json.read_text(encoding="utf-8"))
        if not isinstance(roleplay_result, dict):
            raise SystemExit("roleplay_json must contain a JSON object")
        if not roleplay_result.get("report_summary"):
            roleplay_result["report_summary"] = build_roleplay_report_summary(roleplay_result)
        thread_id = str(roleplay_result["thread_id"])
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
        out = build_thread_export_markdown(
            rows,
            thread_id=thread_id,
            roleplay_result=roleplay_result,
        )

    if args.output:
        args.output.write_text(out, encoding="utf-8")
    else:
        print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
