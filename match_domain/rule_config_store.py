"""Persistent rule-config version store (§13.5 phase 2)."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Mapping

from her_time_utils import current_time, format_dt

from .rule_config_schema import ALL_RULE_SLICES, code_defaults_for_slice

STATUS_DRAFT = "draft"
STATUS_ACTIVE = "active"
STATUS_ARCHIVED = "archived"

SCOPE_GLOBAL = "global"
SCOPE_SUBSCRIPTION = "subscription"
SCOPE_PROFILE = "profile"
SCOPE_EXPERIMENT_BUCKET = "experiment_bucket"


def _row_to_dict(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return None


def _json_loads(raw: Any, default: Any) -> Any:
    if raw in {None, ""}:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    return json.loads(str(raw))


def seed_global_defaults_from_code(conn, *, operator_id: str = "system") -> list[str]:
    """Insert active global config versions from code/env defaults when missing."""

    created: list[str] = []
    now = current_time()
    for slice_id in ALL_RULE_SLICES:
        defaults = code_defaults_for_slice(slice_id)
        if not defaults:
            continue
        existing = get_active_assignment(conn, slice_id=slice_id, scope_type=SCOPE_GLOBAL, scope_key="*")
        if existing is not None:
            continue
        version_id = f"seed_{slice_id.replace('.', '_')}_v1"
        create_version(
            conn,
            version_id=version_id,
            slice_id=slice_id,
            params=defaults,
            schema_version="1",
            status=STATUS_ACTIVE,
            created_by=operator_id,
            now=now,
        )
        create_assignment(
            conn,
            assignment_id=f"assign_{version_id}",
            version_id=version_id,
            slice_id=slice_id,
            scope_type=SCOPE_GLOBAL,
            scope_key="*",
            priority=0,
            created_by=operator_id,
            now=now,
        )
        created.append(version_id)
    if created:
        conn.commit()
    return created


def create_version(
    conn,
    *,
    version_id: str,
    slice_id: str,
    params: Mapping[str, Any],
    schema_version: str = "1",
    status: str = STATUS_DRAFT,
    created_by: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = format_dt(current_time(now))
    conn.execute(
        """
        INSERT INTO rule_config_versions (
          version_id, slice_id, params_json, schema_version, status, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
          params_json = VALUES(params_json),
          schema_version = VALUES(schema_version),
          status = VALUES(status)
        """,
        (
            version_id,
            slice_id,
            json.dumps(dict(params), ensure_ascii=False),
            schema_version,
            status,
            created_by,
            ts,
        ),
    )
    return get_version(conn, version_id) or {}


def get_version(conn, version_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM rule_config_versions WHERE version_id = ?",
        (version_id,),
    ).fetchone()
    out = _row_to_dict(row)
    if out is None:
        return None
    out["params"] = _json_loads(out.pop("params_json", None), {})
    return out


def activate_version(conn, version_id: str, *, operator_id: str, now: datetime | None = None) -> dict[str, Any]:
    version = get_version(conn, version_id)
    if not version:
        raise ValueError(f"Unknown version_id={version_id}")
    ts = format_dt(current_time(now))
    conn.execute(
        """
        UPDATE rule_config_versions
        SET status = ?
        WHERE slice_id = ? AND status = ? AND version_id <> ?
        """,
        (STATUS_ARCHIVED, version["slice_id"], STATUS_ACTIVE, version_id),
    )
    conn.execute(
        "UPDATE rule_config_versions SET status = ? WHERE version_id = ?",
        (STATUS_ACTIVE, version_id),
    )
    conn.execute(
        """
        UPDATE rule_config_assignments
        SET effective_until = ?
        WHERE slice_id = ? AND scope_type = ? AND scope_key = ? AND effective_until IS NULL
        """,
        (ts, version["slice_id"], SCOPE_GLOBAL, "*"),
    )
    create_assignment(
        conn,
        assignment_id=f"assign_active_{version_id}",
        version_id=version_id,
        slice_id=str(version["slice_id"]),
        scope_type=SCOPE_GLOBAL,
        scope_key="*",
        priority=0,
        created_by=operator_id,
        now=now,
    )
    conn.commit()
    return get_version(conn, version_id) or {}


def create_assignment(
    conn,
    *,
    assignment_id: str,
    version_id: str,
    slice_id: str,
    scope_type: str,
    scope_key: str,
    priority: int,
    created_by: str,
    now: datetime | None = None,
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
) -> dict[str, Any]:
    ts = format_dt(current_time(now))
    conn.execute(
        """
        INSERT INTO rule_config_assignments (
          assignment_id, version_id, slice_id, scope_type, scope_key, priority,
          effective_from, effective_until, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE
          version_id = VALUES(version_id),
          priority = VALUES(priority),
          effective_from = VALUES(effective_from),
          effective_until = VALUES(effective_until)
        """,
        (
            assignment_id,
            version_id,
            slice_id,
            scope_type,
            scope_key,
            int(priority),
            format_dt(effective_from) if effective_from else None,
            format_dt(effective_until) if effective_until else None,
            created_by,
            ts,
        ),
    )
    return get_assignment(conn, assignment_id) or {}


def get_assignment(conn, assignment_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM rule_config_assignments WHERE assignment_id = ?",
        (assignment_id,),
    ).fetchone()
    return _row_to_dict(row)


def get_active_assignment(
    conn,
    *,
    slice_id: str,
    scope_type: str,
    scope_key: str,
) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT a.*, v.params_json, v.status AS version_status, v.schema_version
        FROM rule_config_assignments a
        JOIN rule_config_versions v ON v.version_id = a.version_id
        WHERE a.slice_id = ?
          AND a.scope_type = ?
          AND a.scope_key = ?
          AND v.status = ?
          AND (a.effective_until IS NULL OR a.effective_until > NOW())
        ORDER BY a.priority DESC, a.created_at DESC
        LIMIT 1
        """,
        (slice_id, scope_type, scope_key, STATUS_ACTIVE),
    ).fetchone()
    out = _row_to_dict(row)
    if out is None:
        return None
    out["params"] = _json_loads(out.pop("params_json", None), {})
    return out


def list_active_global_configs(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT v.version_id, v.slice_id, v.params_json, v.schema_version, v.status,
               v.created_by, v.created_at, a.scope_type, a.scope_key
        FROM rule_config_versions v
        JOIN rule_config_assignments a ON a.version_id = v.version_id
        WHERE v.status = ?
          AND a.scope_type = ?
          AND a.scope_key = ?
          AND (a.effective_until IS NULL OR a.effective_until > NOW())
        ORDER BY v.slice_id, v.created_at DESC
        """,
        (STATUS_ACTIVE, SCOPE_GLOBAL, "*"),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows or []:
        item = _row_to_dict(row)
        if item is None:
            continue
        item["params"] = _json_loads(item.pop("params_json", None), {})
        out.append(item)
    return out


def list_versions(conn, *, slice_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    if slice_id:
        rows = conn.execute(
            """
            SELECT * FROM rule_config_versions
            WHERE slice_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (slice_id, int(limit)),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM rule_config_versions
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows or []:
        item = _row_to_dict(row)
        if item is None:
            continue
        item["params"] = _json_loads(item.pop("params_json", None), {})
        out.append(item)
    return out


__all__ = [
    "SCOPE_EXPERIMENT_BUCKET",
    "SCOPE_GLOBAL",
    "SCOPE_PROFILE",
    "SCOPE_SUBSCRIPTION",
    "STATUS_ACTIVE",
    "STATUS_ARCHIVED",
    "STATUS_DRAFT",
    "activate_version",
    "create_assignment",
    "create_version",
    "get_active_assignment",
    "get_assignment",
    "get_version",
    "list_active_global_configs",
    "list_versions",
    "seed_global_defaults_from_code",
]
