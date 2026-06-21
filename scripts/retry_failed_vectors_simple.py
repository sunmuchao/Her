#!/usr/bin/env python3
"""最小重试器：直接重试 failed 的 conversation_summaries 向量，不依赖 retry_count/error_message 列。"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    from dotenv import load_dotenv

    load_dotenv(repo_root / ".env")
except ImportError:
    pass

import pymysql


async def main() -> int:
    parser = argparse.ArgumentParser(description="重试 failed 向量")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--requester-id", type=int, default=None)
    args = parser.parse_args()

    conn = pymysql.connect(
        host="127.0.0.1",
        port=3307,
        user="root",
        password="",
        charset="utf8mb4",
        database="her",
    )
    cur = conn.cursor()

    where = "vector_status = 'failed'"
    params: list[object] = []
    if args.requester_id is not None:
        where += " AND requester_id = %s"
        params.append(int(args.requester_id))

    cur.execute(
        f"""
        SELECT requester_id, summary_key, summary_text, conversation_id
        FROM conversation_summaries
        WHERE {where}
        ORDER BY updated_at DESC
        LIMIT %s
        """,
        tuple(params + [int(args.limit)]),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        print("no_failed_rows")
        return 0

    from match_domain.embedding_service import EmbeddingService
    from match_domain.vector_store_lite import VectorStoreLite

    embedding_service = EmbeddingService(model_name="text-embedding-v3")
    vector_store = VectorStoreLite()

    success = 0
    failed = 0
    try:
        for requester_id, summary_key, summary_text, conversation_id in rows:
            try:
                embedding = await embedding_service.generate_embedding(summary_text)
                if not embedding:
                    raise ValueError("empty embedding")

                result = vector_store.save_vector_with_version(
                    user_id=int(requester_id),
                    vector_type=str(summary_key),
                    embedding=embedding,
                    raw_text=str(summary_text),
                    conversation_id=str(conversation_id),
                )

                new_status = "done" if result.get("success") else "failed"
                update_conn = pymysql.connect(
                    host="127.0.0.1",
                    port=3307,
                    user="root",
                    password="",
                    charset="utf8mb4",
                    database="her",
                )
                update_cur = update_conn.cursor()
                update_cur.execute(
                    """
                    UPDATE conversation_summaries
                    SET vector_status = %s, updated_at = NOW()
                    WHERE requester_id = %s AND summary_key = %s AND conversation_id = %s
                    """,
                    (new_status, requester_id, summary_key, conversation_id),
                )
                update_conn.commit()
                update_conn.close()

                if new_status == "done":
                    success += 1
                    print(f"done requester_id={requester_id} key={summary_key}")
                else:
                    failed += 1
                    print(f"failed requester_id={requester_id} key={summary_key}")
            except Exception as exc:
                failed += 1
                print(f"error requester_id={requester_id} key={summary_key} error={exc}")
    finally:
        await embedding_service.aclose()
        vector_store.close()

    print(f"summary success={success} failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
