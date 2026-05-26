"""MySQL-backed search run snapshots (§10.3 performance — materialized criteria cache)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Mapping

from her_env import env_int
from her_time_utils import format_dt, parse_dt

_TABLE = "partner_search_snapshots"


def snapshot_persist_enabled() -> bool:
    raw = os.environ.get("PARTNER_SEARCH_SNAPSHOT_PERSIST", "1").strip().lower()
    return raw not in {"", "0", "false", "no", "off"}


def _snapshot_dsn() -> str | None:
    for key in (
        "PARTNER_SEARCH_SNAPSHOT_DSN",
        "HER_PROFILE_SOURCE_DSN",
        "PERSONA_MEMORY_MYSQL_SOURCE",
    ):
        value = str(os.environ.get(key) or "").strip()
        if value:
            return value
    return None


def _ttl_seconds() -> int:
    return max(0, env_int("PARTNER_SEARCH_CACHE_TTL_SECONDS", 120))


def ensure_search_snapshot_table() -> None:
    """Create partner_search_snapshots if missing (no full persona migration)."""
    import outer_system_mysql_schema as schema
    from db_migrations.targets.persona.m0004_partner_search_snapshots import PARTNER_SEARCH_SNAPSHOTS

    dsn = _snapshot_dsn()
    if not dsn:
        return
    cfg = schema.parse_mysql_dsn(dsn)
    schema.ensure_database(cfg)
    conn = schema.mysql_database_connect(cfg)
    try:
        schema.ensure_table(conn, PARTNER_SEARCH_SNAPSHOTS, prefix=None)
        conn.commit()
    finally:
        conn.close()


def _connect():
    import outer_system_mysql_schema as schema

    dsn = _snapshot_dsn()
    if not dsn:
        return None
    ensure_search_snapshot_table()
    cfg = schema.parse_mysql_dsn(dsn)
    return schema.mysql_database_connect(cfg)


def get_persisted_search_run(criteria_hash: str) -> dict[str, Any] | None:
    if not snapshot_persist_enabled() or not criteria_hash:
        return None
    conn = _connect()
    if conn is None:
        return None
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT search_run_json, expires_at
                FROM `{_TABLE}`
                WHERE criteria_hash = %s
                LIMIT 1
                """,
                (criteria_hash,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        expires_at = parse_dt(row[1] if isinstance(row, (list, tuple)) else row.get("expires_at"))
        if expires_at is not None and datetime.utcnow() > expires_at.replace(tzinfo=None):
            delete_persisted_search_run(criteria_hash)
            return None
        raw = row[0] if isinstance(row, (list, tuple)) else row.get("search_run_json")
        payload = json.loads(raw or "{}")
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None
    finally:
        conn.close()


def store_persisted_search_run(criteria_hash: str, search_run: Mapping[str, Any]) -> None:
    if not snapshot_persist_enabled() or not criteria_hash:
        return
    ttl = _ttl_seconds()
    if ttl <= 0:
        return
    conn = _connect()
    if conn is None:
        return
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=ttl)
    payload = json.dumps(dict(search_run), ensure_ascii=False, default=str)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO `{_TABLE}` (
                  criteria_hash, search_run_json, expires_at, updated_at
                ) VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  search_run_json = VALUES(search_run_json),
                  expires_at = VALUES(expires_at),
                  updated_at = VALUES(updated_at)
                """,
                (criteria_hash, payload, format_dt(expires_at), format_dt(now)),
            )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


def delete_persisted_search_run(criteria_hash: str) -> None:
    conn = _connect()
    if conn is None or not criteria_hash:
        return
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM `{_TABLE}` WHERE criteria_hash = %s",
                (criteria_hash,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()


__all__ = [
    "delete_persisted_search_run",
    "ensure_search_snapshot_table",
    "get_persisted_search_run",
    "snapshot_persist_enabled",
    "store_persisted_search_run",
]
