"""Text evidence and note-redaction helpers for partner search."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Sequence


PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
EMAIL_PATTERN = re.compile(r"(?P<local>[A-Za-z0-9._%+-]+)@(?P<domain>[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
NATIONAL_ID_PATTERN = re.compile(r"(?<![\dXx])(\d{6})\d{8}(\d{3}[\dXx])(?![\dXx])")
CONTACT_HANDLE_PATTERN = re.compile(
    r"(?P<label>(?:微信(?:号)?|wechat|wx|vx|qq)\s*[:：]?\s*)(?P<handle>[A-Za-z][-_A-Za-z0-9]{5,19}|\d{5,12})",
    re.IGNORECASE,
)
ADDRESS_DETAIL_PATTERN = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9]{2,30}(?:路|街|道|巷|弄|村|苑|城|湾|里|花园|小区|大厦|公寓|广场)\s*\d{1,4}(?:号|栋|幢|单元|室)?"
)
ORG_DETAIL_PATTERN = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9]{2,30}(?:小学|中学|幼儿园|大学|学院|医院|公司)"
)
CHILD_DETAIL_PATTERN = re.compile(r"(?:儿子|女儿|孩子)\s*\d{1,2}\s*岁")

SENSITIVE_NOTE_PATTERNS = (
    PHONE_PATTERN,
    EMAIL_PATTERN,
    NATIONAL_ID_PATTERN,
    CONTACT_HANDLE_PATTERN,
    ADDRESS_DETAIL_PATTERN,
    ORG_DETAIL_PATTERN,
    CHILD_DETAIL_PATTERN,
)

SENSITIVE_RELATION_NOTE_PATTERNS = (
    re.compile(r"(孩子|带娃|生育|备孕|不要孩子|丁克)"),
    re.compile(r"(离异|再婚|婚史|前任|前夫|前妻)"),
)


@dataclass(frozen=True)
class SearchTextSignalsRuntime:
    as_lower: Callable[[Any], str]
    as_text: Callable[[Any], str]
    contains_any_text: Callable[[Any, Any], bool]
    normalize_whitespace: Callable[[Any], str]
    split_evidence_segments: Callable[[Any], list[str]]
    requires_explicit_children_acceptance: Callable[[dict[str, Any]], bool]
    get_combined_text_lazy: Callable[[dict[str, Any]], str]  # 性能优化：惰性 combined_text 构建
    keyword_evidence_fields: Sequence[tuple[str, str]]
    structured_keyword_signal_rules: dict[str, Sequence[tuple[str, str, Sequence[str]]]]
    textual_keyword_signal_rules: dict[str, Sequence[tuple[str, str, Sequence[str]]]]


def mask_value(value: Any, left: int = 2, right: int = 2, mask: str = "***") -> str:
    text = str(value)
    if not text:
        return text
    if len(text) <= left + right:
        if len(text) <= 2:
            return "*" * len(text)
        return text[:1] + mask
    suffix = text[-right:] if right > 0 else ""
    return text[:left] + mask + suffix


def redact_sensitive_text(value: Any) -> Any:
    if value is None or value == "":
        return value

    text = str(value)
    text = PHONE_PATTERN.sub(lambda match: f"{match.group(1)}****{match.group(2)}", text)
    text = NATIONAL_ID_PATTERN.sub(
        lambda match: f"{match.group(1)}********{match.group(2)}",
        text,
    )
    text = EMAIL_PATTERN.sub(
        lambda match: f"{mask_value(match.group('local'), left=1, right=0)}@{match.group('domain')}",
        text,
    )
    text = CONTACT_HANDLE_PATTERN.sub(
        lambda match: f"{match.group('label')}{mask_value(match.group('handle'), left=2, right=2)}",
        text,
    )
    return text


def contains_sensitive_note_detail(value: Any) -> bool:
    if value is None or value == "":
        return False
    text = str(value)
    return any(pattern.search(text) for pattern in SENSITIVE_NOTE_PATTERNS)


def summarize_notes(
    runtime: SearchTextSignalsRuntime,
    value: Any,
    max_segments: int = 2,
    max_length: int = 80,
) -> str | None:
    if value is None or value == "":
        return None

    text = runtime.normalize_whitespace(value)
    if not text:
        return None

    if contains_sensitive_note_detail(text):
        return "有补充备注，已隐藏敏感细节"

    redacted = runtime.normalize_whitespace(redact_sensitive_text(text))
    parts = [
        part.strip(" ,，。;；|")
        for part in re.split(r"[。；;\n|]+", redacted)
        if part.strip(" ,，。;；|")
    ]
    if not parts:
        return None

    summary = "；".join(parts[:max_segments])
    if len(summary) > max_length:
        summary = summary[: max_length - 3].rstrip() + "..."
    return summary or None


def shorten_text(runtime: SearchTextSignalsRuntime, value: Any, max_length: int = 60) -> str:
    text = runtime.normalize_whitespace(value)
    if len(text) <= max_length:
        return text
    return text[: max_length - 3].rstrip() + "..."


def extract_literal_keyword_evidence(
    runtime: SearchTextSignalsRuntime,
    record: dict[str, Any],
    keyword: str,
) -> str | None:
    lowered_keyword = runtime.as_lower(keyword)
    if not lowered_keyword:
        return None

    for field, label in runtime.keyword_evidence_fields:
        value = record.get(field)
        if not value:
            continue
        segments = runtime.split_evidence_segments(value)
        for segment in segments:
            if lowered_keyword in segment.lower():
                if contains_sensitive_note_detail(segment):
                    return f"{label}: 命中关键词，敏感细节已隐藏"
                return f"{label}: {shorten_text(runtime, redact_sensitive_text(segment))}"
    return None


def collect_keyword_signal_evidence(
    runtime: SearchTextSignalsRuntime,
    record: dict[str, Any],
    keyword: str,
) -> list[str]:
    lowered_keyword = runtime.as_lower(keyword)
    signal_parts = []

    for field, label, expected_values in runtime.structured_keyword_signal_rules.get(lowered_keyword, []):
        value = runtime.as_text(record.get(field))
        if value and value in expected_values:
            signal_parts.append(f"{label}={value}")

    for field, label, cues in runtime.textual_keyword_signal_rules.get(lowered_keyword, []):
        value = record.get(field)
        if not value or not runtime.contains_any_text(value, cues):
            continue
        signal_parts.append(
            f"{label}={shorten_text(runtime, redact_sensitive_text(value), max_length=20)}"
        )

    if len(signal_parts) < 3:
        return []
    return signal_parts[:3]


def keyword_matches_record(
    runtime: SearchTextSignalsRuntime,
    record: dict[str, Any],
    keyword: str,
) -> bool:
    """检查关键词是否匹配记录。

    性能优化版本：
    - 使用惰性 combined_text 构建，避免不必要的全字段遍历
    - 缓存 combined_text 结果，避免重复计算
    """
    lowered_keyword = runtime.as_lower(keyword)
    if not lowered_keyword:
        return False

    # 使用惰性 combined_text 获取（仅在需要时构建）
    combined_text = runtime.get_combined_text_lazy(record)
    if lowered_keyword in combined_text:
        return True
    return bool(collect_keyword_signal_evidence(runtime, record, keyword))


def extract_keyword_evidence(
    runtime: SearchTextSignalsRuntime,
    record: dict[str, Any],
    keyword: str,
) -> str | None:
    literal_evidence = extract_literal_keyword_evidence(runtime, record, keyword)
    if literal_evidence:
        return literal_evidence

    signal_evidence = collect_keyword_signal_evidence(runtime, record, keyword)
    if signal_evidence:
        return f"结构化信号: {'；'.join(signal_evidence)}"
    return None


def child_or_marital_topic_requested(
    runtime: SearchTextSignalsRuntime,
    criteria: dict[str, Any],
    self_profile: dict[str, Any],
) -> bool:
    if runtime.requires_explicit_children_acceptance(self_profile):
        return True
    joined = " ".join(
        criteria.get("must_have", [])
        + criteria.get("prefer", [])
        + criteria.get("must_not_have", [])
        + criteria.get("relationship_goals", [])
    )
    return runtime.contains_any_text(joined, {"孩子", "带娃", "婚史", "再婚", "生育", "接受孩子现实"})


def summarize_notes_for_result(
    runtime: SearchTextSignalsRuntime,
    record: dict[str, Any],
    criteria: dict[str, Any],
    self_profile: dict[str, Any],
    max_segments: int = 2,
    max_length: int = 80,
) -> str | None:
    notes = record.get("notes")
    summary = summarize_notes(runtime, notes, max_segments=max_segments, max_length=max_length)
    if not summary:
        return None
    if child_or_marital_topic_requested(runtime, criteria, self_profile):
        return summary

    parts = [
        part.strip(" ,，。;；|")
        for part in re.split(r"[。；;\n|]+", summary)
        if part.strip(" ,，。;；|")
    ]
    filtered = [
        part
        for part in parts
        if not any(pattern.search(part) for pattern in SENSITIVE_RELATION_NOTE_PATTERNS)
    ]
    if not filtered:
        return None
    compact = "；".join(filtered[:max_segments])
    if len(compact) > max_length:
        compact = compact[: max_length - 3].rstrip() + "..."
    return compact or None


__all__ = [
    "SearchTextSignalsRuntime",
    "child_or_marital_topic_requested",
    "collect_keyword_signal_evidence",
    "contains_sensitive_note_detail",
    "extract_keyword_evidence",
    "extract_literal_keyword_evidence",
    "keyword_matches_record",
    "mask_value",
    "redact_sensitive_text",
    "shorten_text",
    "summarize_notes",
    "summarize_notes_for_result",
]
