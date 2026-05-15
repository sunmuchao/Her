"""Shared JSON-safe conversion helpers for API and CLI payloads."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Any, Callable


def json_safe(
    value: Any,
    *,
    datetime_formatter: Callable[[datetime], Any] | None = None,
    stringify_mapping_keys: bool = False,
    sort_sets: bool = False,
) -> Any:
    if isinstance(value, datetime):
        if datetime_formatter is not None:
            return datetime_formatter(value)
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            normalized_key = str(key) if stringify_mapping_keys else key
            out[normalized_key] = json_safe(
                item,
                datetime_formatter=datetime_formatter,
                stringify_mapping_keys=stringify_mapping_keys,
                sort_sets=sort_sets,
            )
        return out
    if isinstance(value, set):
        items = sorted(value, key=repr) if sort_sets else value
        return [
            json_safe(
                item,
                datetime_formatter=datetime_formatter,
                stringify_mapping_keys=stringify_mapping_keys,
                sort_sets=sort_sets,
            )
            for item in items
        ]
    if isinstance(value, (list, tuple)):
        return [
            json_safe(
                item,
                datetime_formatter=datetime_formatter,
                stringify_mapping_keys=stringify_mapping_keys,
                sort_sets=sort_sets,
            )
            for item in value
        ]
    return value


__all__ = ["json_safe"]
