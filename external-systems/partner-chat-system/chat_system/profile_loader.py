"""Load dating ``profiles`` rows from MySQL for roleplay personas."""

from __future__ import annotations

import os
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


def roleplay_participant_id(profile_id: int) -> str:
    return f"profile-{int(profile_id)}"


__all__ = [
    "DEFAULT_PROFILE_MYSQL_DSN",
    "fetch_profile_by_id",
    "profile_row_to_brief",
    "roleplay_participant_id",
]
