from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime

from dotenv import load_dotenv

SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

for root in (SYSTEM_ROOT, REPO_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from chat_system import (  # noqa: E402
    create_assistant_case_layout,
    get_agent_session_by_case,
    list_agent_tasks,
    list_conversation_messages,
    post_conversation_message,
    run_chat_maintenance,
)
from chat_system.storage import connect_db, initialize_database  # noqa: E402
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN, reset_all_tables  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test the triggered matchmaker C flow.")
    parser.add_argument("--dsn", default=DEFAULT_CHAT_TEST_MYSQL_DSN)
    parser.add_argument("--reset", action="store_true", help="Clear all chat tables before running")
    parser.add_argument("--case-id", default="case-matchmaker-smoke-001")
    parser.add_argument("--relation-key", default="rel-matchmaker-smoke-001")
    parser.add_argument("--participant-a-id", default="user-a")
    parser.add_argument("--participant-b-id", default="user-b")
    parser.add_argument("--agent-id", default="agent-c")
    parser.add_argument("--metadata-json", help="Optional case metadata JSON passed into the assistant layout")
    parser.add_argument("--message-author-id", default="user-a")
    parser.add_argument(
        "--message-body",
        default="她这两天回复有点慢，我怕刚开始聊天就冷掉了，你怎么看？",
    )
    parser.add_argument("--now", default="2026-05-09 20:00:00")
    parser.add_argument("--recent-limit", type=int, default=30)
    return parser.parse_args()


def _by_role(layout: dict) -> dict[str, dict]:
    return {
        str(item["metadata"]["layout_role"]): item
        for item in layout["conversations"]
    }


def main() -> int:
    load_dotenv(REPO_ROOT / ".env", override=True)
    args = _parse_args()
    now = datetime.strptime(args.now, "%Y-%m-%d %H:%M:%S")

    conn = connect_db(args.dsn)
    try:
        initialize_database(conn)
        if args.reset:
            reset_all_tables(conn)
        metadata = None
        if args.metadata_json:
            metadata = json.loads(pathlib.Path(args.metadata_json).read_text(encoding="utf-8"))
        layout = create_assistant_case_layout(
            conn,
            case_id=args.case_id,
            relation_key=args.relation_key,
            participant_a_id=args.participant_a_id,
            participant_b_id=args.participant_b_id,
            agent_id=args.agent_id,
            metadata=metadata,
            now=now,
        )
        role_map = _by_role(layout)
        main_group = role_map["main_group"]
        posted = post_conversation_message(
            conn,
            main_group["conversation_id"],
            args.message_author_id,
            args.message_body,
            now=now,
        )
        maintenance = run_chat_maintenance(
            conn,
            persona_limit=0,
            assistant_limit=10,
            assistant_idle_seconds=0,
            flush_outbox=True,
            summary_max_threads=0,
            now=now,
        )

        session = get_agent_session_by_case(conn, args.case_id)
        tasks = list_agent_tasks(conn, case_id=args.case_id, limit=20)
        dm_a_messages = list_conversation_messages(
            conn,
            role_map["assistant_dm_a"]["conversation_id"],
            args.participant_a_id,
            limit=20,
        )
        dm_b_messages = list_conversation_messages(
            conn,
            role_map["assistant_dm_b"]["conversation_id"],
            args.participant_b_id,
            limit=20,
        )

        payload = {
            "case_id": args.case_id,
            "posted_message": {
                "message_id": posted["message_id"],
                "conversation_id": posted["conversation_id"],
                "author_id": posted["author_id"],
                "source": posted["source"],
            },
            "maintenance": maintenance,
            "session": session,
            "tasks": tasks,
            "dm_a_messages": dm_a_messages,
            "dm_b_messages": dm_b_messages,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
