"""Unified read/write entrypoints for persona and profile data."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence
from urllib.parse import parse_qs, unquote, urlparse

import outer_system_mysql_schema as schema
from outer_mysql_compat import MySQLCompatConnection
from partner_moderation import current_time
from profile_source_refs import resolve_profile_source as _resolve_profile_source

DEFAULT_PROFILE_PHOTOS_TABLE = "profile_photos"
PROFILE_TABLE_DETECTION_ALIASES = {
    "id": {"id", "编号"},
    "name": {"name", "姓名", "昵称"},
    "gender": {"gender", "性别"},
    "age": {"age", "年龄"},
    "city": {"city", "城市", "所在地", "现居地"},
    "profile_status": {"profile_status", "资料状态", "档案状态"},
    "verified_level": {"verified_level", "认证等级", "认证级别"},
}
PROFILE_TABLE_DETECTION_WEIGHTS = {
    "id": 2,
    "name": 2,
    "gender": 2,
    "age": 2,
    "city": 2,
    "profile_status": 1,
    "verified_level": 1,
}


def resolve_profile_source(
    source_dsn: str | None,
    source_table_name: str | None = None,
) -> tuple[str | None, str | None]:
    return _resolve_profile_source(source_dsn, source_table_name)


def _require_profile_source(*, source_dsn: str, source_table_name: str) -> None:
    if not source_dsn:
        raise ValueError("source_dsn is required")
    if not source_table_name:
        raise ValueError("source_table_name is required")


def _connect_profile_db(source_dsn: str) -> MySQLCompatConnection:
    config = schema.parse_mysql_dsn(str(source_dsn))
    raw = schema.mysql_database_connect(config)
    return MySQLCompatConnection(raw, config)


def _normalize_column_key(value: Any) -> str:
    return re.sub(r"[\s\-]+", "_", str(value or "").strip().lower())


def _list_schema_tables(profile_conn: MySQLCompatConnection) -> list[str]:
    rows = profile_conn.execute(
        """
        SELECT table_name AS table_name
        FROM information_schema.tables
        WHERE table_schema = ?
        ORDER BY table_name
        """,
        (profile_conn.config["database"],),
    ).fetchall()
    return [str(row.get("table_name") or "").strip() for row in rows if str(row.get("table_name") or "").strip()]


def _list_table_columns(profile_conn: MySQLCompatConnection, source_table_name: str) -> list[str]:
    rows = profile_conn.execute(
        """
        SELECT column_name AS column_name
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ?
        ORDER BY ordinal_position
        """,
        (profile_conn.config["database"], source_table_name),
    ).fetchall()
    return [str(row.get("column_name") or "").strip() for row in rows if str(row.get("column_name") or "").strip()]


def _score_profile_table(columns: Sequence[str]) -> int:
    normalized_columns = {_normalize_column_key(item) for item in columns if _normalize_column_key(item)}
    score = 0
    for field_name, aliases in PROFILE_TABLE_DETECTION_ALIASES.items():
        normalized_aliases = {_normalize_column_key(item) for item in aliases if _normalize_column_key(item)}
        if normalized_columns.intersection(normalized_aliases):
            score += PROFILE_TABLE_DETECTION_WEIGHTS.get(field_name, 0)
    return score


def _resolve_profile_photos_table(
    source_dsn: str,
    photos_table_name: str | None = None,
) -> str | None:
    explicit = str(photos_table_name or "").strip()
    if explicit:
        return explicit
    parsed = urlparse(source_dsn)
    query = parse_qs(parsed.query)
    table_name = query.get("photos_table", [DEFAULT_PROFILE_PHOTOS_TABLE])[0]
    normalized = str(table_name or "").strip()
    return unquote(normalized) if normalized else None


def _photo_table_order_clauses(
    raw_conn: Any,
    photo_table: str,
    *,
    include_profile_id: bool = False,
    prioritize_avatar_type: bool = False,
) -> list[str]:
    clauses: list[str] = []
    if include_profile_id:
        clauses.append(f"{schema.quote_mysql_ident('profile_id')} ASC")
    if schema.column_exists(raw_conn, photo_table, "is_primary"):
        clauses.append(f"{schema.quote_mysql_ident('is_primary')} DESC")
    if prioritize_avatar_type and schema.column_exists(raw_conn, photo_table, "photo_type"):
        clauses.append(
            f"CASE WHEN {schema.quote_mysql_ident('photo_type')} = 'avatar' THEN 0 ELSE 1 END ASC"
        )
    if schema.column_exists(raw_conn, photo_table, "sort_order"):
        clauses.append(f"{schema.quote_mysql_ident('sort_order')} ASC")
    if schema.column_exists(raw_conn, photo_table, "id"):
        clauses.append(f"{schema.quote_mysql_ident('id')} ASC")
    return clauses


def _append_unique_photo_entries(
    out: list[dict[str, Any]],
    seen: set[str],
    rows: Sequence[Mapping[str, Any]],
    *,
    source_key: str,
    asset_origin: str,
    owner_key: str,
    owner_id_fallback: int | None = None,
) -> None:
    for row in rows:
        photo_source = str(row.get(source_key) or "").strip()
        if not photo_source or photo_source in seen:
            continue
        seen.add(photo_source)
        owner_id_raw = row.get(owner_key, owner_id_fallback)
        owner_id = int(owner_id_raw) if owner_id_raw is not None else None
        out.append(
            {
                "source_profile_id": owner_id,
                "photo_source": photo_source,
                "asset_origin": asset_origin,
            }
        )


def _photo_sources(items: Sequence[Mapping[str, Any]]) -> list[str]:
    return [str(item.get("photo_source") or "").strip() for item in items if str(item.get("photo_source") or "").strip()]


def detect_profile_table(*, source_dsn: str) -> str | None:
    profile_conn = _connect_profile_db(source_dsn)
    try:
        scored_tables: list[tuple[str, int]] = []
        for table_name in _list_schema_tables(profile_conn):
            score = _score_profile_table(_list_table_columns(profile_conn, table_name))
            scored_tables.append((table_name, score))
        if not scored_tables:
            return None
        best_score = max(score for _, score in scored_tables)
        if best_score <= 0:
            return None
        best_tables = [table_name for table_name, score in scored_tables if score == best_score]
        if len(best_tables) > 1:
            raise ValueError(
                "Ambiguous MySQL candidate tables: "
                + ", ".join(best_tables)
                + ". Specify ?table=... in the DSN or pass --table."
            )
        return best_tables[0]
    finally:
        profile_conn.close()


def list_profile_columns(
    *,
    source_dsn: str,
    source_table_name: str,
) -> list[str]:
    _require_profile_source(source_dsn=source_dsn, source_table_name=source_table_name)
    profile_conn = _connect_profile_db(source_dsn)
    try:
        raw_conn = profile_conn.driver_connection
        if not schema.table_exists(raw_conn, source_table_name):
            raise ValueError(f"profile table {source_table_name} was not found")
        return _list_table_columns(profile_conn, source_table_name)
    finally:
        profile_conn.close()


def list_profiles(
    *,
    source_dsn: str,
    source_table_name: str,
    where_clause: str = "",
    params: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    _require_profile_source(source_dsn=source_dsn, source_table_name=source_table_name)
    profile_conn = _connect_profile_db(source_dsn)
    try:
        raw_conn = profile_conn.driver_connection
        if not schema.table_exists(raw_conn, source_table_name):
            raise ValueError(f"profile table {source_table_name} was not found")
        normalized_where = str(where_clause or "").strip()
        sql = f"SELECT * FROM {schema.quote_mysql_ident(source_table_name)}"
        if normalized_where:
            sql = f"{sql} {normalized_where}"
        rows = profile_conn.execute(sql, tuple(params or ())).fetchall()
        return [dict(row) for row in rows]
    finally:
        profile_conn.close()


def apply_persona_patch(
    request: Any | Mapping[str, Any],
) -> dict[str, Any]:
    from .persona_bridge import apply_persona_patch as _apply_persona_patch

    return _apply_persona_patch(request)


def render_public_profile(
    request: Any | Mapping[str, Any],
) -> dict[str, Any]:
    from .persona_bridge import render_public_profile as _render_public_profile

    return _render_public_profile(request)


def get_profile(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int,
) -> dict[str, Any]:
    _require_profile_source(source_dsn=source_dsn, source_table_name=source_table_name)
    profile_conn = _connect_profile_db(source_dsn)
    try:
        raw_conn = profile_conn.driver_connection
        if not schema.column_exists(raw_conn, source_table_name, "id"):
            raise ValueError(f"profile table {source_table_name} is missing id column")
        row = profile_conn.execute(
            f"SELECT * FROM {schema.quote_mysql_ident(source_table_name)} "
            f"WHERE {schema.quote_mysql_ident('id')} = ? LIMIT 1",
            (int(profile_id),),
        ).fetchone()
        if not row:
            raise ValueError(f"profile {profile_id} was not found in table {source_table_name}")
        return dict(row)
    finally:
        profile_conn.close()


def get_public_profile(
    *,
    source_dsn: str,
    profile_id: int,
    public_view_name: str = "public_profile_view",
) -> dict[str, Any]:
    source_dsn = str(source_dsn or "").strip()
    public_view_name = str(public_view_name or "").strip() or "public_profile_view"
    if not source_dsn:
        raise ValueError("source_dsn is required")
    profile_conn = _connect_profile_db(source_dsn)
    try:
        raw_conn = profile_conn.driver_connection
        if not schema.table_exists(raw_conn, public_view_name):
            raise ValueError(f"public profile view {public_view_name} was not found")
        row = profile_conn.execute(
            f"SELECT * FROM {schema.quote_mysql_ident(public_view_name)} "
            f"WHERE {schema.quote_mysql_ident('id')} = ? LIMIT 1",
            (int(profile_id),),
        ).fetchone()
        if not row:
            raise ValueError(f"public profile {profile_id} was not found in view {public_view_name}")
        return dict(row)
    finally:
        profile_conn.close()


def list_profile_photo_previews(
    *,
    source_dsn: str,
    profile_ids: Sequence[int],
    source_table_name: str | None = None,
    photos_table_name: str | None = None,
    preview_count: int = 3,
) -> dict[int, list[str]]:
    normalized_profile_ids = [int(item) for item in profile_ids if item is not None]
    if preview_count <= 0 or not normalized_profile_ids:
        return {}
    profile_conn = _connect_profile_db(source_dsn)
    try:
        raw_conn = profile_conn.driver_connection
        photo_table = _resolve_profile_photos_table(source_dsn, photos_table_name=photos_table_name)
        if not photo_table:
            return {}
        if not schema.table_exists(raw_conn, photo_table):
            raise ValueError(f"profile photos table {photo_table} was not found")
        if not schema.column_exists(raw_conn, photo_table, "profile_id") or not schema.column_exists(raw_conn, photo_table, "photo_url"):
            raise ValueError(f"profile photos table {photo_table} must contain profile_id and photo_url columns")
        placeholders = ", ".join(["?"] * len(normalized_profile_ids))
        order_clauses = [f"{schema.quote_mysql_ident('profile_id')} ASC"]
        has_is_primary = schema.column_exists(raw_conn, photo_table, "is_primary")
        if schema.column_exists(raw_conn, photo_table, "is_primary"):
            order_clauses.append(f"CASE WHEN {schema.quote_mysql_ident('is_primary')} = 1 THEN 0 ELSE 1 END")
        else:
            if schema.column_exists(raw_conn, photo_table, "photo_type"):
                order_clauses.append(
                    f"CASE WHEN {schema.quote_mysql_ident('photo_type')} = 'avatar' THEN 0 ELSE 1 END"
                )
        order_clauses.extend(
            clause
            for clause in _photo_table_order_clauses(
                raw_conn,
                photo_table,
            )
            if clause not in order_clauses
            and (not has_is_primary or clause != f"{schema.quote_mysql_ident('is_primary')} DESC")
        )
        rows = profile_conn.execute(
            (
                f"SELECT {schema.quote_mysql_ident('profile_id')} AS profile_id, "
                f"{schema.quote_mysql_ident('photo_url')} AS photo_url "
                f"FROM {schema.quote_mysql_ident(photo_table)} "
                f"WHERE {schema.quote_mysql_ident('profile_id')} IN ({placeholders}) "
                f"ORDER BY {', '.join(order_clauses)}"
            ),
            tuple(normalized_profile_ids),
        ).fetchall()
        previews: dict[int, list[str]] = {}
        for row in rows:
            profile_id = int(row["profile_id"]) if row.get("profile_id") is not None else None
            photo_url = str(row.get("photo_url") or "").strip()
            if profile_id is None or not photo_url:
                continue
            previews.setdefault(profile_id, [])
            if photo_url in previews[profile_id]:
                continue
            if len(previews[profile_id]) >= preview_count:
                continue
            previews[profile_id].append(photo_url)
        return previews
    finally:
        profile_conn.close()


def list_profile_photos(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int,
    photos_table_name: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    _require_profile_source(source_dsn=source_dsn, source_table_name=source_table_name)
    if limit is not None and int(limit) <= 0:
        return []
    profile_conn = _connect_profile_db(source_dsn)
    try:
        raw_conn = profile_conn.driver_connection
        if not schema.table_exists(raw_conn, source_table_name) or not schema.column_exists(raw_conn, source_table_name, "id"):
            return []
        profile = profile_conn.execute(
            f"SELECT * FROM {schema.quote_mysql_ident(source_table_name)} "
            f"WHERE {schema.quote_mysql_ident('id')} = ? LIMIT 1",
            (int(profile_id),),
        ).fetchone()
        if not profile:
            return []
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        photo_table = _resolve_profile_photos_table(source_dsn, photos_table_name=photos_table_name)
        if (
            photo_table
            and schema.table_exists(raw_conn, photo_table)
            and schema.column_exists(raw_conn, photo_table, "profile_id")
            and schema.column_exists(raw_conn, photo_table, "photo_url")
        ):
            order_clauses = _photo_table_order_clauses(
                raw_conn,
                photo_table,
                prioritize_avatar_type=True,
            )
            order_sql = ", ".join(order_clauses) if order_clauses else f"{schema.quote_mysql_ident('photo_url')} ASC"
            limit_sql = " LIMIT ?" if limit is not None else ""
            photo_params: list[Any] = [int(profile_id)]
            if limit is not None:
                photo_params.append(max(1, int(limit)))
            rows = profile_conn.execute(
                (
                    f"SELECT {schema.quote_mysql_ident('photo_url')} AS photo_url "
                    f"FROM {schema.quote_mysql_ident(photo_table)} "
                    f"WHERE {schema.quote_mysql_ident('profile_id')} = ? "
                    f"ORDER BY {order_sql}{limit_sql}"
                ),
                tuple(photo_params),
            ).fetchall()
            _append_unique_photo_entries(
                out,
                seen,
                [dict(row) for row in rows],
                source_key="photo_url",
                asset_origin="photo_table",
                owner_key="profile_id",
                owner_id_fallback=int(profile_id),
            )
        avatar_url = str(profile.get("avatar_url") or "").strip()
        if avatar_url and avatar_url not in seen and not out:
            out.append(
                {
                    "source_profile_id": int(profile_id),
                    "photo_source": avatar_url,
                    "asset_origin": "avatar_fallback",
                }
            )
        return out
    finally:
        profile_conn.close()


def list_profile_photo_sources(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int,
    photos_table_name: str | None = None,
    limit: int | None = None,
) -> list[str]:
    return _photo_sources(
        list_profile_photos(
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            profile_id=profile_id,
            photos_table_name=photos_table_name,
            limit=limit,
        )
    )


def list_comparison_profile_photos(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int,
    photos_table_name: str | None = None,
    limit: int = 24,
) -> list[dict[str, Any]]:
    _require_profile_source(source_dsn=source_dsn, source_table_name=source_table_name)
    normalized_limit = max(1, int(limit))
    profile_conn = _connect_profile_db(source_dsn)
    try:
        raw_conn = profile_conn.driver_connection
        photo_table = _resolve_profile_photos_table(source_dsn, photos_table_name=photos_table_name)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        if (
            photo_table
            and schema.table_exists(raw_conn, photo_table)
            and schema.column_exists(raw_conn, photo_table, "profile_id")
            and schema.column_exists(raw_conn, photo_table, "photo_url")
        ):
            order_sql = ", ".join(_photo_table_order_clauses(raw_conn, photo_table, include_profile_id=True))
            rows = profile_conn.execute(
                (
                    f"SELECT {schema.quote_mysql_ident('profile_id')} AS profile_id, "
                    f"{schema.quote_mysql_ident('photo_url')} AS photo_url "
                    f"FROM {schema.quote_mysql_ident(photo_table)} "
                    f"WHERE {schema.quote_mysql_ident('profile_id')} <> ? "
                    f"ORDER BY {order_sql} LIMIT ?"
                ),
                (int(profile_id), normalized_limit),
            ).fetchall()
            _append_unique_photo_entries(
                out,
                seen,
                [dict(row) for row in rows],
                source_key="photo_url",
                asset_origin="photo_table",
                owner_key="profile_id",
            )
        if out:
            return out
        if schema.table_exists(raw_conn, source_table_name) and schema.column_exists(raw_conn, source_table_name, "avatar_url"):
            rows = profile_conn.execute(
                (
                    f"SELECT {schema.quote_mysql_ident('id')} AS id, "
                    f"{schema.quote_mysql_ident('avatar_url')} AS avatar_url "
                    f"FROM {schema.quote_mysql_ident(source_table_name)} "
                    f"WHERE {schema.quote_mysql_ident('id')} <> ? "
                    f"AND {schema.quote_mysql_ident('avatar_url')} IS NOT NULL "
                    f"ORDER BY {schema.quote_mysql_ident('id')} ASC LIMIT ?"
                ),
                (int(profile_id), normalized_limit),
            ).fetchall()
            _append_unique_photo_entries(
                out,
                seen,
                [dict(row) for row in rows],
                source_key="avatar_url",
                asset_origin="avatar_fallback",
                owner_key="id",
            )
        return out
    finally:
        profile_conn.close()


def list_comparison_profile_photo_sources(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int,
    photos_table_name: str | None = None,
    limit: int = 24,
) -> list[str]:
    return _photo_sources(
        list_comparison_profile_photos(
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            profile_id=profile_id,
            photos_table_name=photos_table_name,
            limit=limit,
        )
    )


def apply_profile_updates(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int,
    updates: Mapping[str, Any],
) -> dict[str, Any]:
    _require_profile_source(source_dsn=source_dsn, source_table_name=source_table_name)
    profile_conn = _connect_profile_db(source_dsn)
    try:
        raw_conn = profile_conn.driver_connection
        if not schema.column_exists(raw_conn, source_table_name, "id"):
            raise ValueError(f"profile table {source_table_name} is missing id column")
        assignments: list[str] = []
        values: list[Any] = []
        updated_fields: list[str] = []
        for column, value in dict(updates).items():
            if value is None:
                continue
            if not schema.column_exists(raw_conn, source_table_name, column):
                continue
            assignments.append(f"{schema.quote_mysql_ident(column)} = ?")
            values.append(value)
            updated_fields.append(column)
        if (
            schema.column_exists(raw_conn, source_table_name, "updated_at")
            and "updated_at" not in updated_fields
        ):
            assignments.append(f"{schema.quote_mysql_ident('updated_at')} = ?")
            values.append(current_time())
            updated_fields.append("updated_at")
        if not assignments:
            return {"status": "skipped", "reason": "no_sync_columns", "updated_fields": []}
        sql = (
            f"UPDATE {schema.quote_mysql_ident(source_table_name)} "
            f"SET {', '.join(assignments)} "
            f"WHERE {schema.quote_mysql_ident('id')} = ?"
        )
        values.append(int(profile_id))
        result = profile_conn.execute(sql, tuple(values))
        if int(result.rowcount or 0) <= 0:
            exists = profile_conn.execute(
                f"SELECT 1 FROM {schema.quote_mysql_ident(source_table_name)} "
                f"WHERE {schema.quote_mysql_ident('id')} = ? LIMIT 1",
                (int(profile_id),),
            ).fetchone()
            if not exists:
                raise ValueError(f"profile {profile_id} was not found in table {source_table_name}")
        profile_conn.commit()
        return {
            "status": "synced",
            "profile_id": int(profile_id),
            "table_name": source_table_name,
            "updated_fields": updated_fields,
        }
    finally:
        profile_conn.close()
