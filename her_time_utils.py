"""Shared time and scalar helpers used across Her subsystems."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any


def current_time(now: datetime | None = None) -> datetime:
    return (now or datetime.now()).replace(microsecond=0)


def format_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return current_time(value).isoformat(sep=" ")


def parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return current_time(value)
    text = str(value).strip()
    if not text:
        return None
    return datetime.fromisoformat(text)


def coerce_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_dt_trimmed(value: Any) -> datetime | None:
    parsed = coerce_dt(value)
    if parsed is None:
        return None
    return parsed.replace(microsecond=0)


def bool_to_int(value: bool) -> int:
    return 1 if value else 0


def coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value)
    digits = []
    started = False
    for char in text:
        if char == "-" and not started and not digits:
            digits.append(char)
            started = True
            continue
        if char.isdigit():
            digits.append(char)
            started = True
            continue
        if started:
            break
    if not digits or digits == ["-"]:
        return None
    return int("".join(digits))


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clean_text(value: Any) -> str | None:
    text = as_text(value)
    return text or None


def unique_ordered_texts(values: Iterable[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        item = as_text(value)
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


__all__ = [
    "as_text",
    "bool_to_int",
    "clean_text",
    "coerce_dt",
    "coerce_int",
    "current_time",
    "format_dt",
    "parse_dt",
    "parse_dt_trimmed",
    "unique_ordered_texts",
]
