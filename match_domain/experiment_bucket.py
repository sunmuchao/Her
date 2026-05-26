"""Resolve experiment bucket for rule_config A/B (§13.5 phase 4)."""

from __future__ import annotations

import json
from typing import Any, Mapping


def experiment_bucket_from_subscription_overrides(subscription: Mapping[str, Any]) -> str | None:
    raw = subscription.get("subscription_overrides_json")
    if raw in {None, ""}:
        return None
    if isinstance(raw, Mapping):
        overrides = dict(raw)
    else:
        try:
            overrides = json.loads(str(raw))
        except json.JSONDecodeError:
            return None
    if not isinstance(overrides, Mapping):
        return None
    bucket = str(overrides.get("experiment_bucket") or "").strip()
    return bucket or None


def profile_id_from_subscription(subscription: Mapping[str, Any]) -> int | None:
    for key in ("self_id", "requester_id", "profile_id"):
        value = subscription.get(key)
        if value in {None, ""}:
            continue
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def get_experiment_bucket_member(conn, profile_id: int) -> str | None:
    row = conn.execute(
        "SELECT bucket_key FROM experiment_bucket_members WHERE profile_id = ?",
        (int(profile_id),),
    ).fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        bucket = row.get("bucket_key")
    else:
        bucket = row[0] if row else None
    normalized = str(bucket or "").strip()
    return normalized or None


def upsert_experiment_bucket_member(
    conn,
    *,
    profile_id: int,
    bucket_key: str,
    updated_by: str,
) -> dict[str, Any]:
    from her_time_utils import current_time, format_dt

    ts = format_dt(current_time())
    conn.execute(
        """
        INSERT INTO experiment_bucket_members (profile_id, bucket_key, updated_by, updated_at)
        VALUES (?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
          bucket_key = VALUES(bucket_key),
          updated_by = VALUES(updated_by),
          updated_at = VALUES(updated_at)
        """,
        (int(profile_id), str(bucket_key).strip(), str(updated_by), ts),
    )
    return {
        "profile_id": int(profile_id),
        "bucket_key": str(bucket_key).strip(),
        "updated_by": str(updated_by),
        "updated_at": ts,
    }


def delete_experiment_bucket_member(conn, profile_id: int) -> bool:
    cursor = conn.execute(
        "DELETE FROM experiment_bucket_members WHERE profile_id = ?",
        (int(profile_id),),
    )
    return bool(getattr(cursor, "rowcount", 0))


def list_experiment_bucket_members(conn, *, limit: int = 100) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT profile_id, bucket_key, updated_by, updated_at
        FROM experiment_bucket_members
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (max(int(limit), 1),),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows or []:
        if isinstance(row, dict):
            out.append(dict(row))
        else:
            out.append(
                {
                    "profile_id": row[0],
                    "bucket_key": row[1],
                    "updated_by": row[2],
                    "updated_at": row[3],
                }
            )
    return out


def resolve_experiment_bucket_for_subscription(
    subscription: Mapping[str, Any],
    *,
    conn=None,
    profile_id: int | None = None,
) -> str | None:
    """Priority: subscription_overrides.experiment_bucket > DB member row."""

    bucket = experiment_bucket_from_subscription_overrides(subscription)
    if bucket:
        return bucket
    pid = profile_id if profile_id is not None else profile_id_from_subscription(subscription)
    if conn is not None and pid is not None:
        return get_experiment_bucket_member(conn, pid)
    return None


__all__ = [
    "delete_experiment_bucket_member",
    "experiment_bucket_from_subscription_overrides",
    "get_experiment_bucket_member",
    "list_experiment_bucket_members",
    "profile_id_from_subscription",
    "resolve_experiment_bucket_for_subscription",
    "upsert_experiment_bucket_member",
]
