#!/usr/bin/env python3
"""批量回填历史聊天记录到摘要表和向量库。

用途：
- 扫描历史 discovery 会话
- 对未生成摘要的会话补写 conversation_summaries
- 可选生成向量并写入 Milvus Lite

默认策略：
- 只处理有聊天消息的会话
- 默认跳过已经存在摘要记录的会话
- 回填模式下不清理 working_criteria，避免影响在线会话状态
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    from dotenv import load_dotenv

    load_dotenv(repo_root / ".env")
except ImportError:
    pass

from external_systems.partner_discovery_system.discovery_system.storage import connect_db
from match_domain.session_end_processor import process_session_end
from persona_memory_sync.persona_memory_lib import (
    mysql_connect,
    quote_mysql_ident,
    release_persona_connection,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_logger = logging.getLogger(__name__)


@dataclass
class SessionCandidate:
    session_id: str
    requester_id: int
    profile_id: int
    status: str
    phase: str
    created_at: Any
    updated_at: Any
    message_count: int
    existing_summary_count: int


def _resolve_discovery_dsn(cli_value: str | None) -> str:
    return str(cli_value or os.environ.get("PARTNER_DISCOVERY_DB") or "").strip()


def _resolve_persona_dsn(cli_value: str | None) -> str:
    return str(
        cli_value
        or os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE")
        or os.environ.get("HER_PERSONA_DB")
        or ""
    ).strip()


def list_session_candidates(
    discovery_dsn: str,
    persona_dsn: str,
    *,
    limit: int | None,
    offset: int,
    min_messages: int,
    include_existing: bool,
    requester_id: int | None,
    session_id: str | None,
) -> list[SessionCandidate]:
    """列出符合回填条件的会话。"""

    discovery_conn = connect_db(discovery_dsn)
    persona_conn = mysql_connect(persona_dsn, use_pool=True, timeout=10.0)
    try:
        where_clauses = ["s.status IN ('active', 'completed', 'closed')"]
        params: list[Any] = []

        if requester_id is not None:
            where_clauses.append("s.requester_id = ?")
            params.append(int(requester_id))

        if session_id:
            where_clauses.append("s.session_id = ?")
            params.append(session_id)

        limit_sql = ""
        limit_params: list[Any] = []
        if limit is not None:
            limit_sql = " LIMIT ? OFFSET ?"
            limit_params.extend([int(limit), int(offset)])
        elif offset:
            limit_sql = " LIMIT 18446744073709551615 OFFSET ?"
            limit_params.append(int(offset))

        rows = discovery_conn.execute(
            f"""
            SELECT
                s.session_id,
                s.requester_id,
                s.profile_id,
                s.status,
                s.phase,
                s.created_at,
                s.updated_at,
                COUNT(m.item_id) AS message_count
            FROM discovery_agent_sessions s
            LEFT JOIN discovery_agent_session_memory_items m
              ON m.session_id = s.session_id
            WHERE {' AND '.join(where_clauses)}
            GROUP BY
                s.session_id, s.requester_id, s.profile_id,
                s.status, s.phase, s.created_at, s.updated_at
            HAVING COUNT(m.item_id) >= ?
            ORDER BY s.created_at ASC
            {limit_sql}
            """,
            tuple(params + [int(min_messages)] + limit_params),
        ).fetchall()

        candidates: list[SessionCandidate] = []
        with persona_conn.cursor() as cursor:
            for row in rows:
                candidate_session_id = str(row["session_id"])
                cursor.execute(
                    f"""
                    SELECT COUNT(*) AS count
                    FROM {quote_mysql_ident("conversation_summaries")}
                    WHERE conversation_id = %s
                    """,
                    (candidate_session_id,),
                )
                summary_row = cursor.fetchone() or {}
                existing_summary_count = int(summary_row.get("count") or 0)

                if existing_summary_count > 0 and not include_existing:
                    continue

                candidates.append(
                    SessionCandidate(
                        session_id=candidate_session_id,
                        requester_id=int(row["requester_id"]),
                        profile_id=int(row["profile_id"]),
                        status=str(row["status"]),
                        phase=str(row["phase"]),
                        created_at=row.get("created_at"),
                        updated_at=row.get("updated_at"),
                        message_count=int(row["message_count"] or 0),
                        existing_summary_count=existing_summary_count,
                    )
                )

        return candidates
    finally:
        discovery_conn.close()
        release_persona_connection(persona_dsn, persona_conn)


async def process_candidate(
    candidate: SessionCandidate,
    *,
    discovery_dsn: str,
    vectorize: bool,
) -> dict[str, Any]:
    """执行单个会话回填。"""

    result = await process_session_end(
        session_id=candidate.session_id,
        requester_id=candidate.requester_id,
        profile_id=candidate.profile_id,
        conversation_type="discovery",
        dsn=discovery_dsn,
        processed_at=None,
        storage=None,
        vectorize_summaries=vectorize,
        clear_working_criteria_after_processing=False,
    )

    return {
        "session_id": candidate.session_id,
        "requester_id": candidate.requester_id,
        "profile_id": candidate.profile_id,
        "message_count": candidate.message_count,
        "existing_summary_count": candidate.existing_summary_count,
        **result,
    }


async def backfill_sessions(args: argparse.Namespace) -> int:
    discovery_dsn = _resolve_discovery_dsn(args.discovery_dsn)
    persona_dsn = _resolve_persona_dsn(args.persona_dsn)

    if not discovery_dsn:
        print("缺少 discovery DSN。请传 --discovery-dsn 或设置 PARTNER_DISCOVERY_DB。", file=sys.stderr)
        return 2
    if not persona_dsn:
        print("缺少 persona DSN。请传 --persona-dsn 或设置 PERSONA_MEMORY_MYSQL_SOURCE。", file=sys.stderr)
        return 2

    candidates = list_session_candidates(
        discovery_dsn,
        persona_dsn,
        limit=args.limit,
        offset=args.offset,
        min_messages=args.min_messages,
        include_existing=args.include_existing,
        requester_id=args.requester_id,
        session_id=args.session_id,
    )

    print(f"候选会话数: {len(candidates)}")
    print(
        f"参数: vectorize={not args.skip_vector}, dry_run={args.dry_run}, "
        f"include_existing={args.include_existing}, min_messages={args.min_messages}"
    )

    if args.list_only or args.dry_run:
        for idx, candidate in enumerate(candidates, start=1):
            print(
                f"[{idx}] session_id={candidate.session_id} requester_id={candidate.requester_id} "
                f"profile_id={candidate.profile_id} messages={candidate.message_count} "
                f"existing_summaries={candidate.existing_summary_count} status={candidate.status}"
            )
        return 0

    success_count = 0
    skipped_count = 0
    failed_count = 0

    for idx, candidate in enumerate(candidates, start=1):
        print(
            f"[{idx}/{len(candidates)}] 回填 session_id={candidate.session_id} "
            f"requester_id={candidate.requester_id} messages={candidate.message_count}"
        )
        try:
            result = await process_candidate(
                candidate,
                discovery_dsn=discovery_dsn,
                vectorize=not args.skip_vector,
            )
        except Exception as exc:
            failed_count += 1
            _logger.exception("回填异常: session_id=%s error=%s", candidate.session_id, exc)
            continue

        if result.get("success"):
            success_count += 1
            print(
                f"  success saved={len(result.get('saved_keys', []))} "
                f"vectorized={len(result.get('vectorized_keys', []))} "
                f"quantifiable={len(result.get('quantifiable_data', {}))} "
                f"non_quantifiable={len(result.get('non_quantifiable_data', {}))}"
            )
        elif result.get("error") == "no_new_messages":
            skipped_count += 1
            print(f"  skipped reason=no_new_messages")
        else:
            failed_count += 1
            print(
                f"  failed error={result.get('error')} message={result.get('message')}"
            )

    print(
        f"完成: total={len(candidates)} success={success_count} "
        f"skipped={skipped_count} failed={failed_count}"
    )
    return 0 if failed_count == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="批量回填历史聊天摘要和向量")
    parser.add_argument("--discovery-dsn", default=None, help="Discovery MySQL DSN，默认读取 PARTNER_DISCOVERY_DB")
    parser.add_argument("--persona-dsn", default=None, help="Persona MySQL DSN，默认读取 PERSONA_MEMORY_MYSQL_SOURCE")
    parser.add_argument("--limit", type=int, default=None, help="最多处理多少个会话")
    parser.add_argument("--offset", type=int, default=0, help="从第几个候选会话开始")
    parser.add_argument("--min-messages", type=int, default=2, help="最少消息数，默认 2")
    parser.add_argument("--requester-id", type=int, default=None, help="只处理指定 requester_id")
    parser.add_argument("--session-id", type=str, default=None, help="只处理指定 session_id")
    parser.add_argument("--include-existing", action="store_true", help="包含已存在摘要记录的会话")
    parser.add_argument("--skip-vector", action="store_true", help="只写摘要，不写向量")
    parser.add_argument("--dry-run", action="store_true", help="只展示候选会话，不实际执行")
    parser.add_argument("--list-only", action="store_true", help="列出候选会话后退出")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(backfill_sessions(args))


if __name__ == "__main__":
    raise SystemExit(main())
