#!/usr/bin/env python3
"""对当前向量库做最小可复用的召回质量审计。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict, dataclass
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

from match_domain.embedding_service import EmbeddingService
from match_domain.retrieval_text_normalizer import normalize_query_text
from match_domain.vector_store_lite import VectorStoreLite


DEFAULT_CASES: tuple[dict[str, Any], ...] = (
    {
        "query": "我希望找一个性格温柔，有上进心的",
        "expected_markers": ["温和", "目标感强", "有责任感", "成长驱动强"],
    },
    {
        "query": "我喜欢慢热，真诚，认真推进关系的",
        "expected_markers": ["慢热", "关系推进明确", "不暧昧", "持续投入关系", "节奏明确"],
    },
    {
        "query": "我希望对方生活规律，不要太卷",
        "expected_markers": ["作息规律", "排斥高压内卷", "生活稳定", "工作生活平衡"],
    },
    {
        "query": "我需要对方及时回复，事事有回应，不冷处理",
        "expected_markers": ["及时回复", "有回应", "不冷处理", "愿意沟通"],
    },
)


@dataclass
class RetrievalHit:
    vector_type: str
    rank: int
    user_id: int | None
    similarity: float
    raw_text: str
    matched_markers: list[str]


@dataclass
class RetrievalCaseResult:
    query: str
    normalized_text: str
    retrieval_text: str
    route_vector_types: list[str]
    expected_markers: list[str]
    grade: str
    hits: list[RetrievalHit]


def grade_hits(hits: list[RetrievalHit]) -> str:
    if not hits:
        return "偏"

    top1 = hits[0]
    top3 = hits[:3]
    top1_match_count = len(top1.matched_markers)
    top3_with_match = sum(1 for hit in top3 if hit.matched_markers)

    if top1_match_count >= 2 or (top1_match_count >= 1 and top3_with_match >= 2):
        return "准"
    if top1_match_count >= 1 or top3_with_match >= 1:
        return "一般"
    return "偏"


def build_markers(raw_text: str, expected_markers: list[str]) -> list[str]:
    text = str(raw_text or "").strip()
    return [marker for marker in expected_markers if marker in text]


async def run_case(
    query: str,
    expected_markers: list[str],
    *,
    top_k: int,
    threshold: float,
    vector_types: list[str] | None,
) -> RetrievalCaseResult:
    normalized = normalize_query_text(query)
    chosen_vector_types = vector_types or list(normalized.route_vector_types)

    embedding_service = EmbeddingService(model_name="text-embedding-v3")
    vector_store = VectorStoreLite()
    try:
        embedding = await embedding_service.generate_embedding(normalized.retrieval_text)
        if not embedding:
            raise RuntimeError("embedding generation returned empty vector")

        hits: list[RetrievalHit] = []
        for vector_type in chosen_vector_types:
            results = vector_store.search_similar_users(
                user_vector=embedding,
                vector_type=vector_type,
                top_k=top_k,
                similarity_threshold=threshold,
            )
            for rank, row in enumerate(results[:top_k], start=1):
                raw_text = str(row.get("raw_text") or "").strip()
                hits.append(
                    RetrievalHit(
                        vector_type=vector_type,
                        rank=rank,
                        user_id=row.get("user_id"),
                        similarity=float(row.get("similarity") or 0.0),
                        raw_text=raw_text,
                        matched_markers=build_markers(raw_text, expected_markers),
                    )
                )

        hits.sort(key=lambda item: item.similarity, reverse=True)
        final_hits = hits[:top_k]
        return RetrievalCaseResult(
            query=query,
            normalized_text=normalized.normalized_text,
            retrieval_text=normalized.retrieval_text,
            route_vector_types=chosen_vector_types,
            expected_markers=expected_markers,
            grade=grade_hits(final_hits),
            hits=final_hits,
        )
    finally:
        await embedding_service.aclose()
        vector_store.close()


def render_markdown(results: list[RetrievalCaseResult]) -> str:
    lines: list[str] = []
    lines.append("# 召回质量审计表")
    lines.append("")
    lines.append("| 查询 | 标准化后 | 路由槽位 | 分级 | Top结果摘要 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for result in results:
        if result.hits:
            top = result.hits[0]
            top_summary = (
                f"{top.vector_type} | sim={top.similarity:.3f} | "
                f"命中={','.join(top.matched_markers) or '无'} | {top.raw_text[:48]}"
            )
        else:
            top_summary = "无结果"
        lines.append(
            f"| {result.query} | {result.normalized_text} | "
            f"{', '.join(result.route_vector_types)} | {result.grade} | {top_summary} |"
        )

    lines.append("")
    lines.append("## 详细结果")
    lines.append("")
    for result in results:
        lines.append(f"### {result.query}")
        lines.append(f"- 分级：{result.grade}")
        lines.append(f"- 标准化：{result.normalized_text}")
        lines.append(f"- 检索文本：{result.retrieval_text}")
        lines.append(f"- 路由槽位：{', '.join(result.route_vector_types)}")
        lines.append(f"- 期望命中：{', '.join(result.expected_markers)}")
        if not result.hits:
            lines.append("- Top结果：无")
            lines.append("")
            continue
        for hit in result.hits:
            lines.append(
                f"- [{hit.vector_type} #{hit.rank}] sim={hit.similarity:.3f} "
                f"user_id={hit.user_id} 命中={','.join(hit.matched_markers) or '无'} "
                f"text={hit.raw_text}"
            )
        lines.append("")

    return "\n".join(lines).strip() + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser(description="召回质量审计")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--threshold", type=float, default=0.55)
    parser.add_argument("--output", default="tmp/retrieval_quality_audit.md")
    parser.add_argument(
        "--vector-type",
        action="append",
        default=None,
        help="只审计指定槽位，可传多次；默认按查询路由自动决定",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=None,
        help="自定义查询；如果传了，就只跑这些查询，expected_markers 走空列表",
    )
    args = parser.parse_args()

    if args.query:
        cases = [{"query": query, "expected_markers": []} for query in args.query]
    else:
        cases = list(DEFAULT_CASES)

    results: list[RetrievalCaseResult] = []
    for case in cases:
        result = await run_case(
            str(case["query"]),
            list(case.get("expected_markers") or []),
            top_k=int(args.top_k),
            threshold=float(args.threshold),
            vector_types=args.vector_type,
        )
        results.append(result)

    output_path = repo_root / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(results), encoding="utf-8")

    printable = [
        {
            **asdict(result),
            "hits": [asdict(hit) for hit in result.hits],
        }
        for result in results
    ]
    print(json.dumps(printable, ensure_ascii=False, indent=2))
    print(f"markdown_report={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
