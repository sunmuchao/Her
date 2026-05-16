"""Shared helpers for profile review workflows."""

from __future__ import annotations

import re
from typing import Any

from her_json_utils import json_safe
from her_time_utils import as_text as _as_text

LOW_WAGE_JOB_KEYWORDS = ("助理", "文员", "行政", "客服", "店员", "实习")
HIGH_INCOME_CITY_MISMATCH = {
    "镇江",
    "扬州",
    "湖州",
    "嘉兴",
    "南通",
    "常州",
    "无锡",
}


def as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_income_max_wan(value: Any) -> int | None:
    text = _as_text(value)
    if not text:
        return None
    matches = [int(item) for item in re.findall(r"(\d+)", text)]
    if not matches:
        return None
    if "+" in text:
        return matches[0]
    return max(matches)


def json_safe_profile_value(value: Any) -> Any:
    return json_safe(value, stringify_mapping_keys=True)


__all__ = [
    "HIGH_INCOME_CITY_MISMATCH",
    "LOW_WAGE_JOB_KEYWORDS",
    "as_int",
    "json_safe_profile_value",
    "parse_income_max_wan",
]
