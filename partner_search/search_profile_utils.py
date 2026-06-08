"""Shared profile parsing and normalization helpers for partner search."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache  # 性能优化：引入 lru_cache
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlparse


@dataclass(frozen=True)
class SearchProfileUtilsRuntime:
    mysql_schemes: Sequence[str]
    default_mysql_source: str | None
    alias_lookup: Mapping[str, str]
    text_fields: Sequence[str]
    unknown_values: set[str]
    education_order: Mapping[str, int]
    verified_level_order: Mapping[str, int]
    photo_verification_level_order: Mapping[str, int]
    profile_status_order: Mapping[str, int]
    as_lower: Callable[[Any], str]
    as_text: Callable[[Any], str]
    normalize_bool: Callable[[Any], bool | None]
    normalize_key: Callable[[Any], str]
    parse_json_object: Callable[[Any], Any]
    unique_ordered: Callable[[Any], list[Any]]
    split_source_file_ref: Callable[[str | None], tuple[str, str | None]]


def is_mysql_source(runtime: SearchProfileUtilsRuntime, source: Any) -> bool:
    try:
        return urlparse(str(source)).scheme.lower() in runtime.mysql_schemes
    except Exception:
        return False


def redact_mysql_source(runtime: SearchProfileUtilsRuntime, source: Any) -> str:
    text = str(source)
    try:
        parsed = urlparse(text)
    except Exception:
        return text
    if parsed.scheme.lower() not in runtime.mysql_schemes:
        return text

    userinfo = ""
    if parsed.username:
        username = unquote(parsed.username)
        if parsed.password:
            userinfo = f"{username}:***@"
        else:
            userinfo = f"{username}@"

    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    query = parse_qs(parsed.query)
    safe_query_parts = []
    for key in ("table", "photos_table", "charset"):
        value = query.get(key, [None])[0]
        if value:
            safe_query_parts.append(f"{key}={value}")
    query_text = f"?{'&'.join(safe_query_parts)}" if safe_query_parts else ""
    return f"{parsed.scheme}://{userinfo}{host}{port}{parsed.path}{query_text}"


def redact_source_ref(runtime: SearchProfileUtilsRuntime, source_ref: Any) -> str:
    if not source_ref:
        return ""
    source, table_name = runtime.split_source_file_ref(source_ref)
    if not table_name:
        return redact_mysql_source(runtime, source_ref)
    redacted = redact_mysql_source(runtime, source)
    return f"{redacted}#{table_name}" if table_name else redacted


def default_source_help_text(runtime: SearchProfileUtilsRuntime) -> str:
    if runtime.default_mysql_source:
        return (
            "Defaults to PARTNER_SEARCH_MYSQL_SOURCE="
            f"{redact_mysql_source(runtime, runtime.default_mysql_source)}."
        )
    return "Required unless PARTNER_SEARCH_MYSQL_SOURCE is set."


def as_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def education_rank(runtime: SearchProfileUtilsRuntime, value: Any) -> int | None:
    return runtime.education_order.get(str(value).strip()) if value else None


def verified_rank(runtime: SearchProfileUtilsRuntime, value: Any) -> int:
    return runtime.verified_level_order.get(runtime.as_lower(value), 0)


def photo_verification_rank(runtime: SearchProfileUtilsRuntime, value: Any) -> int:
    return runtime.photo_verification_level_order.get(runtime.as_lower(value), 0)


def profile_status_rank(runtime: SearchProfileUtilsRuntime, value: Any) -> int:
    return runtime.profile_status_order.get(runtime.as_lower(value), 0)


@lru_cache(maxsize=256)  # 性能优化：缓存最近 256 次收入范围解析结果
def parse_income_range_to_wan(value: Any) -> tuple[int | None, int | None]:
    if value is None:
        return (None, None)
    numbers = [int(item) for item in re.findall(r"\d+", str(value))]
    if not numbers:
        return (None, None)
    if len(numbers) == 1:
        return (numbers[0], numbers[0])
    return (min(numbers[0], numbers[1]), max(numbers[0], numbers[1]))


def effective_has_children(runtime: SearchProfileUtilsRuntime, record: Mapping[str, Any]) -> bool | None:
    direct = runtime.normalize_bool(record.get("has_children"))
    if direct is not None:
        return direct
    marital_status = runtime.as_lower(record.get("marital_status"))
    if "已育" in marital_status:
        return True
    if marital_status in {"未婚", "离异未育", "离异无孩"} or "无孩" in marital_status:
        return False
    return None


def marital_status_match_options(
    runtime: SearchProfileUtilsRuntime,
    record: Mapping[str, Any],
) -> list[str]:
    status = runtime.as_text(record.get("marital_status"))
    if not status:
        return []
    options = [status]
    lowered = runtime.as_lower(status)
    has_children = runtime.normalize_bool(record.get("has_children"))
    if lowered in {"离异", "离异无孩", "离异未育", "离异已育"}:
        options.append("离异")
    if lowered == "离异":
        if has_children is True:
            options.append("离异已育")
        elif has_children is False:
            options.append("离异未育")
            options.append("离异无孩")
    elif lowered == "离异已育":
        options.append("离异")
    elif lowered in {"离异未育", "离异无孩"}:
        options.append("离异")
        options.append("离异未育")
        options.append("离异无孩")
    return runtime.unique_ordered(options)


def effective_activity_info(
    runtime: SearchProfileUtilsRuntime,
    record: Mapping[str, Any],
) -> tuple[str | None, datetime | None]:
    del runtime
    for field in ("last_active_at", "updated_at", "created_at"):
        parsed = as_datetime(record.get(field))
        if parsed is not None:
            return (field, parsed)
    return (None, None)


def effective_activity_datetime(
    runtime: SearchProfileUtilsRuntime,
    record: Mapping[str, Any],
) -> datetime | None:
    return effective_activity_info(runtime, record)[1]


def format_datetime(value: Any) -> str | None:
    parsed = as_datetime(value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S") if parsed else None


def has_explicit_field_value(runtime: Any, record: Mapping[str, Any], field: str) -> bool:
    if field == "has_children":
        return runtime.effective_has_children(record) is not None

    value = record.get(field)
    if value is None or value == "":
        return False

    lowered = runtime.as_lower(value)
    if lowered in runtime.unknown_values:
        return False
    return True


def normalize_record(
    runtime: SearchProfileUtilsRuntime,
    raw: Mapping[str, Any],
) -> dict[str, Any]:
    record = {}
    for key, value in raw.items():
        canonical = runtime.alias_lookup.get(runtime.normalize_key(key), runtime.normalize_key(key))
        record[canonical] = value

    if "source_file" not in record:
        record["source_file"] = ""

    for key, value in list(record.items()):
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                value = None
        record[key] = value

    if record.get("age") is not None:
        match = re.search(r"\d+", str(record["age"]))
        record["age"] = int(match.group()) if match else None

    if record.get("height") is not None:
        match = re.search(r"\d+", str(record["height"]))
        record["height"] = int(match.group()) if match else None

    if record.get("income_min_wan") is None and record.get("income_max_wan") is None:
        income_min, income_max = parse_income_range_to_wan(record.get("income_range"))
        if income_min is not None:
            record["income_min_wan"] = income_min
        if income_max is not None:
            record["income_max_wan"] = income_max

    record["matcher_traits"] = runtime.parse_json_object(record.get("matcher_traits_json"))
    record["matcher_preferences"] = runtime.parse_json_object(record.get("matcher_preferences_json"))
    record["matcher_risks"] = runtime.parse_json_object(record.get("matcher_risks_json"))

    # 性能优化: combined_text 改为惰性构建，仅在实际需要关键词匹配时才计算
    # 使用 None 作为标记，表示尚未构建，避免在 normalize_record 时遍历所有 text_fields
    record["combined_text"] = None
    record["_combined_text_needs_build"] = True
    return record


def build_combined_text(runtime: SearchProfileUtilsRuntime, record: Mapping[str, Any]) -> str:
    """构建用于关键词匹配的全文本拼接字符串。

    性能优化版本：
    - 仅在首次调用时构建
    - 缓存结果避免重复计算
    - 仅遍历必要的 text_fields（约20个核心字段而非全量70个）
    - 使用列表 + join 避免多次字符串拼接（减少临时对象）
    """
    # 如果已有缓存，直接返回
    cached = record.get("_combined_text_cached")
    if isinstance(cached, str):
        return cached

    # 核心关键词匹配字段（仅20个最常用的，而非全量70个）
    # 这些字段涵盖了绝大多数关键词匹配场景
    core_text_fields = (
        "job", "education", "city", "district", "settlement_city",
        "notes", "values", "family_background",
        "relationship_goal", "marriage_timeline",
        "career_intensity", "life_routine", "communication_style",
        "warmth_style", "chat_texture", "life_texture",
        "growth_signal", "consumption_attitude", "expression_style",
        "dating_pace",
    )

    # 性能优化：使用列表收集，避免多次字符串拼接
    parts = []
    append_part = parts.append

    for key in core_text_fields:
        value = record.get(key)
        if value:
            append_part(str(value))

    # 如果核心字段全空，再检查备用字段
    if not parts:
        # 仅在核心字段全空时才遍历全量 text_fields
        for key in runtime.text_fields:
            if key not in core_text_fields:
                value = record.get(key)
                if value:
                    append_part(str(value))

    # 性能优化：使用 join 一次性拼接，避免多次创建临时字符串
    result = " | ".join(parts).lower()

    # 缓存结果（仅在 record 是可变字典时）
    if isinstance(record, dict):
        record["_combined_text_cached"] = result
        record["_combined_text_needs_build"] = False

    return result


def get_combined_text_lazy(runtime: SearchProfileUtilsRuntime, record: dict[str, Any]) -> str:
    """惰性获取 combined_text，仅在需要时构建。

    这是 keyword_matches_record 应使用的入口函数。
    """
    cached = record.get("_combined_text_cached")
    if isinstance(cached, str):
        return cached

    if record.get("_combined_text_needs_build"):
        return build_combined_text(runtime, record)

    # 兜底：如果 combined_text 已存在且非 None，直接返回
    existing = record.get("combined_text")
    if isinstance(existing, str):
        return existing

    return build_combined_text(runtime, record)


__all__ = [
    "SearchProfileUtilsRuntime",
    "as_datetime",
    "build_combined_text",
    "default_source_help_text",
    "education_rank",
    "effective_activity_datetime",
    "effective_activity_info",
    "effective_has_children",
    "format_datetime",
    "get_combined_text_lazy",
    "has_explicit_field_value",
    "is_mysql_source",
    "marital_status_match_options",
    "normalize_record",
    "parse_income_range_to_wan",
    "photo_verification_rank",
    "profile_status_rank",
    "redact_mysql_source",
    "redact_source_ref",
    "verified_rank",
]
