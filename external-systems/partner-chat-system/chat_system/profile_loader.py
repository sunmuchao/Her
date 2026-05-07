"""Load dating ``profiles`` rows from MySQL for roleplay personas."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from outer_mysql_compat import connect_mysql_repo_db, row_to_dict  # noqa: E402

DEFAULT_PROFILE_MYSQL_DSN = os.environ.get(
    "HER_PROFILE_MYSQL_DSN", "mysql://root@127.0.0.1:3307/her"
)

# Align with ``generate_virtual_profiles.FIELDNAMES`` (subset ok if older schema).
_BRIEF_KEYS = (
    "name",
    "gender",
    "age",
    "city",
    "district",
    "hometown",
    "settlement_city",
    "height",
    "education",
    "job",
    "income_range",
    "housing_status",
    "car_status",
    "relationship_goal",
    "marital_status",
    "has_children",
    "children_count",
    "want_children",
    "smoking",
    "drinking",
    "long_distance",
    "accept_long_distance",
    "personality",
    "values",
    "lifestyle",
    "hobbies",
    "preferred_age_min",
    "preferred_age_max",
    "preferred_cities",
    "preferred_height_min",
    "preferred_height_max",
    "preferred_education_min",
    "preferred_income_min_wan",
    "preferred_income_max_wan",
    "must_have",
    "must_not_have",
    "marriage_timeline",
    "family_background",
    "notes",
    "verified_level",
    "source_channel",
)

_ASSISTANT_SUMMARY_KEYS = (
    "name",
    "age",
    "settlement_city",
    "job",
    "relationship_goal",
    "personality",
    "values",
    "lifestyle",
    "hobbies",
    "marriage_timeline",
    "notes",
)

_PROFILE_USER_KEY_COLUMNS = (
    "user_key",
    "participant_id",
    "owner_user_id",
    "owner_id",
    "app_user_id",
)


def fetch_profile_by_id(dsn: str, profile_id: int) -> dict[str, Any]:
    conn = connect_mysql_repo_db(str(dsn), subsystem_name="Profile")
    try:
        cur = conn.execute("SELECT * FROM profiles WHERE id = ? LIMIT 1", (int(profile_id),))
        row = row_to_dict(cur.fetchone())
        if not row:
            raise ValueError(f"profiles.id={profile_id} not found in {dsn}")
        return dict(row)
    finally:
        conn.close()


@lru_cache(maxsize=32)
def _profile_lookup_columns(dsn: str) -> tuple[str, ...]:
    conn = connect_mysql_repo_db(str(dsn), subsystem_name="Profile")
    try:
        cur = conn.execute("SHOW COLUMNS FROM profiles")
        rows = cur.fetchall()
        names = {str(row.get("Field") or "") for row in rows}
    except Exception:
        return ()
    finally:
        conn.close()
    return tuple(column for column in _PROFILE_USER_KEY_COLUMNS if column in names)


def _fetch_profile_by_column(dsn: str, column: str, value: Any) -> dict[str, Any] | None:
    conn = connect_mysql_repo_db(str(dsn), subsystem_name="Profile")
    try:
        cur = conn.execute(f"SELECT * FROM profiles WHERE {column} = ? LIMIT 1", (value,))
        row = row_to_dict(cur.fetchone())
        return dict(row) if row else None
    finally:
        conn.close()


def parse_profile_id_candidate(participant_id: str) -> int | None:
    text = str(participant_id or "").strip()
    if not text:
        return None
    if text.startswith("profile-"):
        try:
            return int(text.split("-", 1)[1])
        except ValueError:
            return None
    if text.isdigit():
        try:
            return int(text)
        except ValueError:
            return None
    return None


def profile_row_to_brief(row: dict[str, Any]) -> str:
    """Turn a DB row into a single block the persona model can follow."""
    lines: list[str] = []
    pid = row.get("id")
    if pid is not None:
        lines.append(f"资料库用户 id：{pid}")
    for key in _BRIEF_KEYS:
        if key not in row:
            continue
        val = row[key]
        if val is None or val == "":
            continue
        lines.append(f"{key}：{val}")
    if not lines:
        return "（资料行几乎为空，请用温和默认相亲用户口吻）"
    lines.append(
        "请严格按以上真实字段扮演，不要编造与表内冲突的年龄、婚史、城市、收入等；"
        "缺项不要说死，可自然带过。"
    )
    return "\n".join(lines)


def profile_row_to_assistant_summary(row: dict[str, Any]) -> str:
    """Compact profile summary safe for coaching suggestions."""
    lines: list[str] = []
    for key in _ASSISTANT_SUMMARY_KEYS:
        val = row.get(key)
        if val is None or val == "":
            continue
        lines.append(f"{key}：{val}")
    return "\n".join(lines)


def _split_profile_hooks(raw: Any) -> list[str]:
    text = str(raw or "").replace("，", ",").replace("、", ",")
    out: list[str] = []
    for part in text.split(","):
        item = part.strip()
        if not item or item in out:
            continue
        out.append(item)
    return out


def profile_row_to_hook_list(row: dict[str, Any], *, limit: int = 8) -> list[str]:
    hooks: list[str] = []
    for key in ("settlement_city", "hometown", "job", "lifestyle", "hobbies", "notes"):
        if key not in row:
            continue
        items = _split_profile_hooks(row.get(key))
        if key in ("settlement_city", "hometown", "job") and row.get(key):
            items = [str(row.get(key)).strip()]
        for item in items:
            if not item or item in hooks:
                continue
            hooks.append(item)
            if len(hooks) >= max(1, int(limit)):
                return hooks
    return hooks


def parse_roleplay_profile_id(participant_id: str) -> int | None:
    text = str(participant_id or "").strip()
    if not text.startswith("profile-"):
        return None
    return parse_profile_id_candidate(text)


def fetch_profile_for_participant(
    dsn: str,
    participant_id: str,
    *,
    profile_id_hint: int | None = None,
    user_key_hint: str | None = None,
) -> dict[str, Any] | None:
    profile_id = profile_id_hint if profile_id_hint is not None else parse_profile_id_candidate(participant_id)
    if profile_id is not None:
        try:
            return fetch_profile_by_id(str(dsn), profile_id)
        except ValueError:
            pass

    user_key = str(user_key_hint or participant_id or "").strip()
    if not user_key:
        return None
    for column in _profile_lookup_columns(str(dsn)):
        row = _fetch_profile_by_column(str(dsn), column, user_key)
        if row:
            return row
    return None


def roleplay_participant_id(profile_id: int) -> str:
    return f"profile-{int(profile_id)}"


__all__ = [
    "DEFAULT_PROFILE_MYSQL_DSN",
    "fetch_profile_for_participant",
    "fetch_profile_by_id",
    "parse_profile_id_candidate",
    "parse_roleplay_profile_id",
    "profile_row_to_assistant_summary",
    "profile_row_to_brief",
    "profile_row_to_hook_list",
    "roleplay_participant_id",
]
