"""Shared field normalization helpers for persona-memory-sync."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, List, Optional

from her_time_utils import clean_text, unique_ordered_texts


def normalize_boolish(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return 1 if value else 0
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "是", "有"}:
        return 1
    if lowered in {"0", "false", "no", "n", "否", "无"}:
        return 0
    return None


def split_multi_value(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                items = parsed
            else:
                items = re.split(r"[，,、;/\n|]+", value)
        else:
            items = re.split(r"[，,、;/\n|]+", value)
    else:
        items = re.split(r"[，,、;/\n|]+", str(value))
    result: List[str] = []
    seen = set()
    for item in items:
        text = clean_text(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def unique_ordered(items: Iterable[str]) -> List[str]:
    return unique_ordered_texts(items)


def csv_from_items(items: Iterable[str]) -> Optional[str]:
    normalized = split_multi_value(list(items))
    return ",".join(normalized) if normalized else None


def items_from_csv(value: Any) -> List[str]:
    return split_multi_value(value)


__all__ = [
    "csv_from_items",
    "items_from_csv",
    "normalize_boolish",
    "split_multi_value",
    "unique_ordered",
]
