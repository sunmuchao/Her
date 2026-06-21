"""检索文本标准化：统一入库摘要和查询文本的表达口径。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


SUMMARY_NORMALIZATION_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    "partner_expectation": (
        ("性格温柔", "温和"),
        ("温柔", "温和"),
        ("好脾气", "情绪稳定"),
        ("会沟通", "善沟通"),
        ("好沟通", "善沟通"),
        ("有上进心", "目标感强"),
        ("上进心", "目标感强"),
        ("有事业心", "目标感强"),
        ("有冲劲", "成长驱动强"),
        ("愿意努力", "成长驱动强"),
        ("认真推进关系", "关系推进明确"),
        ("奔着恋爱去", "关系推进明确"),
        ("愿意投入关系", "持续投入关系"),
        ("不想暧昧", "不暧昧"),
        ("不要太卷", "排斥高压内卷"),
        ("生活规律", "作息规律"),
        ("稳定一点", "生活稳定"),
    ),
    "personality_traits": (
        ("性格温柔", "温和"),
        ("温柔", "温和"),
        ("好脾气", "情绪稳定"),
        ("会沟通", "善沟通"),
        ("好沟通", "善沟通"),
        ("有上进心", "目标感强"),
        ("上进心", "目标感强"),
    ),
    "life_attitude": (
        ("不要太卷", "排斥高压内卷"),
        ("生活规律", "作息规律"),
        ("稳定一点", "生活稳定"),
    ),
    "emotional_needs": (
        ("会沟通", "善沟通"),
        ("好沟通", "善沟通"),
        ("认真推进关系", "关系推进明确"),
        ("不想暧昧", "不暧昧"),
    ),
    "partner_relationship_pacing": (
        ("认真推进关系", "关系推进明确"),
        ("奔着恋爱去", "关系推进明确"),
        ("奔着结婚去", "关系推进明确"),
        ("愿意投入关系", "持续投入关系"),
        ("不想暧昧", "不暧昧"),
        ("不喜欢暧昧", "不暧昧"),
        ("稳定推进", "节奏明确"),
    ),
    "partner_lifestyle_preference": (
        ("生活规律", "作息规律"),
        ("不要太卷", "排斥高压内卷"),
        ("别太卷", "排斥高压内卷"),
        ("太忙太卷", "排斥高压内卷"),
        ("向往规律", "作息规律"),
        ("稳定的生活节奏", "生活稳定"),
    ),
}


QUERY_NORMALIZATION_RULES: tuple[tuple[str, str], ...] = (
    ("性格温柔", "温和"),
    ("温柔", "温和"),
    ("有上进心", "目标感强"),
    ("上进心", "目标感强"),
    ("有事业心", "目标感强"),
    ("有冲劲", "成长驱动强"),
    ("认真推进关系", "关系推进明确"),
    ("不想暧昧", "不暧昧"),
    ("生活规律", "作息规律"),
    ("不要太卷", "排斥高压内卷"),
    ("会沟通", "善沟通"),
    ("好沟通", "善沟通"),
)


@dataclass(frozen=True)
class NormalizedText:
    original_text: str
    normalized_text: str
    applied_rules: list[str]
    retrieval_text: str
    semantic_tags: list[str]


@dataclass(frozen=True)
class NormalizedQuery:
    original_text: str
    normalized_text: str
    applied_rules: list[str]
    route_vector_types: list[str]
    retrieval_text: str
    semantic_tags: list[str]


RETRIEVAL_EXPANSION_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("目标感强", ("目标感强", "成长驱动强", "做事积极", "有责任感")),
    ("关系推进明确", ("关系推进明确", "不暧昧", "持续投入关系", "节奏明确")),
    ("慢热", ("慢热", "真诚", "关系推进明确", "不暧昧", "节奏明确")),
    ("真诚", ("真诚", "稳定投入关系", "不敷衍")),
    ("温和", ("温和", "细腻", "有耐心")),
    ("善沟通", ("善沟通", "愿意沟通", "不冷处理")),
    ("作息规律", ("作息规律", "生活稳定", "有计划有条理")),
    ("排斥高压内卷", ("排斥高压内卷", "工作生活平衡", "不喜欢太卷")),
    ("生活稳定", ("生活稳定", "稳定的生活节奏", "规律生活", "工作生活平衡")),
    ("有时间陪伴", ("有时间陪伴", "下班后有时间", "愿意经营关系")),
)


SEMANTIC_TAG_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("tag:温和型", ("温和", "细腻", "有耐心")),
    ("tag:沟通型", ("善沟通", "愿意沟通", "不冷处理")),
    ("tag:目标感", ("目标感强", "成长驱动强", "做事积极", "有事业心")),
    ("tag:责任感", ("有责任感", "靠谱", "稳定投入")),
    ("tag:关系推进明确", ("关系推进明确", "不暧昧", "持续投入关系", "节奏明确")),
    ("tag:生活规律", ("作息规律", "生活稳定", "有计划有条理")),
    ("tag:及时回应", ("及时回复", "有回应", "不冷处理", "高回应度")),
    ("tag:边界感", ("边界感", "独立", "界限清楚")),
    ("tag:慢热真诚", ("慢热", "真诚")),
)


def _dedupe_segments(text: str) -> str:
    raw_segments = re.split(r"[，,、；;]+", text)
    ordered: list[str] = []
    seen: set[str] = set()
    for segment in raw_segments:
        cleaned = str(segment or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return "，".join(ordered)


def normalize_summary_text(field_name: str, text: str) -> NormalizedText:
    normalized = str(text or "").strip()
    applied_rules: list[str] = []
    rules = SUMMARY_NORMALIZATION_RULES.get(str(field_name or "").strip(), ())

    for source, target in rules:
        if source in normalized:
            normalized = normalized.replace(source, target)
            applied_rules.append(f"{source}->{target}")

    normalized = _dedupe_segments(normalized)
    semantic_tags = extract_semantic_tags(normalized)
    retrieval_text = build_retrieval_text(normalized, semantic_tags=semantic_tags)
    return NormalizedText(
        original_text=str(text or "").strip(),
        normalized_text=normalized,
        applied_rules=applied_rules,
        retrieval_text=retrieval_text,
        semantic_tags=semantic_tags,
    )


def route_query_vector_types(text: str) -> list[str]:
    normalized = str(text or "").strip()
    routes: list[str] = []

    if any(marker in normalized for marker in ("及时回复", "有回应", "不冷处理")):
        routes.extend(["emotional_needs", "partner_expectation"])

    if any(marker in normalized for marker in ("生活规律", "作息规律", "不要太卷", "排斥高压内卷", "稳定")):
        routes.extend(["partner_lifestyle_preference", "life_attitude"])

    if any(marker in normalized for marker in ("慢热", "认真推进关系", "关系推进明确", "不暧昧", "持续投入关系")):
        routes.extend(["partner_relationship_pacing", "emotional_needs"])

    if any(marker in normalized for marker in ("温和", "细腻", "有耐心", "善沟通", "独立", "边界感", "目标感强", "成长驱动强")):
        routes.extend(["partner_personality_preference", "partner_expectation", "personality_traits"])

    # 默认兜底，避免无路由时完全不搜。
    if not routes:
        routes.extend(
            [
                "partner_personality_preference",
                "partner_relationship_pacing",
                "partner_lifestyle_preference",
                "partner_expectation",
                "personality_traits",
                "life_attitude",
                "emotional_needs",
            ]
        )

    ordered: list[str] = []
    seen: set[str] = set()
    for item in routes:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def normalize_query_text(text: str) -> NormalizedQuery:
    normalized = str(text or "").strip()
    applied_rules: list[str] = []

    for source, target in QUERY_NORMALIZATION_RULES:
        if source in normalized:
            normalized = normalized.replace(source, target)
            applied_rules.append(f"{source}->{target}")

    normalized = _dedupe_segments(normalized)
    semantic_tags = extract_semantic_tags(normalized)
    retrieval_text = build_retrieval_text(normalized, semantic_tags=semantic_tags)
    return NormalizedQuery(
        original_text=str(text or "").strip(),
        normalized_text=normalized,
        applied_rules=applied_rules,
        route_vector_types=route_query_vector_types(normalized),
        retrieval_text=retrieval_text,
        semantic_tags=semantic_tags,
    )


def extract_semantic_tags(text: str) -> list[str]:
    normalized = str(text or "").strip()
    tags: list[str] = []
    for tag, markers in SEMANTIC_TAG_RULES:
        if any(marker in normalized for marker in markers):
            tags.append(tag)
    return tags


def build_retrieval_text(text: str, *, semantic_tags: list[str] | None = None) -> str:
    base_segments = [segment.strip() for segment in re.split(r"[，,、；;]+", str(text or "").strip()) if segment.strip()]
    expanded_segments: list[str] = list(base_segments)

    for marker, expansions in RETRIEVAL_EXPANSION_RULES:
        if marker in text:
            expanded_segments.extend(expansions)

    for tag in list(semantic_tags or []):
        expanded_segments.append(tag)

    ordered: list[str] = []
    seen: set[str] = set()
    for segment in expanded_segments:
        cleaned = str(segment or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return "，".join(ordered)


__all__ = [
    "NormalizedQuery",
    "NormalizedText",
    "build_retrieval_text",
    "extract_semantic_tags",
    "normalize_query_text",
    "normalize_summary_text",
    "route_query_vector_types",
]
