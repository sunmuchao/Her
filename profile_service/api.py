"""Unified read/write entrypoints for persona and profile data."""

from __future__ import annotations

import os
import re
import threading
import time
from collections.abc import Callable
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


# 全局 profile 连接池缓存
_profile_pool_cache: dict[str, ProfileConnectionPool] = {}
_profile_pool_lock = threading.Lock()
_profile_metadata_cache: dict[tuple[str, str, str], tuple[float, Any]] = {}
_profile_metadata_lock = threading.Lock()


def _profile_metadata_ttl_seconds() -> float:
    raw = str(os.environ.get("PROFILE_METADATA_CACHE_TTL_SECONDS", "60") or "60").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 60.0


def _profile_metadata_cache_get(cache_key: tuple[str, str, str]) -> Any | None:
    ttl = _profile_metadata_ttl_seconds()
    if ttl <= 0:
        return None
    now = time.monotonic()
    with _profile_metadata_lock:
        cached = _profile_metadata_cache.get(cache_key)
        if cached is None:
            return None
        expires_at, value = cached
        if expires_at < now:
            _profile_metadata_cache.pop(cache_key, None)
            return None
        return value


def _profile_metadata_cache_set(cache_key: tuple[str, str, str], value: Any) -> Any:
    ttl = _profile_metadata_ttl_seconds()
    if ttl <= 0:
        return value
    with _profile_metadata_lock:
        _profile_metadata_cache[cache_key] = (time.monotonic() + ttl, value)
    return value


class ProfileConnectionPool:
    """简单的有界连接池，避免每次请求都新建连接"""

    __slots__ = ("_avail", "_cfg", "_lock", "_sem", "_dsn", "_initialized")

    def __init__(self, dsn: str, max_size: int = 8) -> None:
        self._dsn = dsn
        self._cfg = schema.parse_mysql_dsn(dsn)
        self._sem = threading.BoundedSemaphore(max(1, max_size))
        self._lock = threading.Lock()
        self._avail: list[Any] = []
        self._initialized = False

        # 初始化时确保数据库存在（只执行一次，避免重复 CREATE DATABASE）
        try:
            schema.ensure_database(self._cfg)
            self._initialized = True
        except Exception:
            # 如果数据库已存在，忽略错误
            self._initialized = True

    def acquire(self, timeout: float | None = None) -> MySQLCompatConnection:
        """获取连接，支持超时保护"""
        acquired = self._sem.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"Profile 连接池等待超时（{timeout}秒）")

        try:
            with self._lock:
                raw = self._avail.pop() if self._avail else schema.mysql_database_connect(self._cfg)
        except Exception:
            self._sem.release()
            raise
        return MySQLCompatConnection(raw, self._cfg)

    def release(self, conn: MySQLCompatConnection) -> None:
        """释放连接回池"""
        try:
            conn.rollback()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            self._sem.release()
            return
        raw = conn.driver_connection
        with self._lock:
            self._avail.append(raw)
        self._sem.release()


def _get_profile_pool(source_dsn: str) -> ProfileConnectionPool:
    """获取或创建 profile 连接池"""
    with _profile_pool_lock:
        if source_dsn not in _profile_pool_cache:
            max_pool_size = int(os.environ.get("PROFILE_DB_POOL_MAX", "8") or "8")
            _profile_pool_cache[source_dsn] = ProfileConnectionPool(source_dsn, max_size=max_pool_size)
        return _profile_pool_cache[source_dsn]


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


def _connect_profile_db(source_dsn: str, use_pool: bool = True, timeout: float = 10.0) -> MySQLCompatConnection:
    """连接 profile 数据库，默认使用连接池"""
    if use_pool:
        pool = _get_profile_pool(source_dsn)
        return pool.acquire(timeout=timeout)
    else:
        # 不使用连接池，直接创建连接（用于特殊场景）
        config = schema.parse_mysql_dsn(str(source_dsn))
        raw = schema.mysql_database_connect(config)
        return MySQLCompatConnection(raw, config)


def release_profile_connection(source_dsn: str, conn: MySQLCompatConnection) -> None:
    """释放连接回连接池"""
    pool = _get_profile_pool(source_dsn)
    pool.release(conn)


def _normalize_column_key(value: Any) -> str:
    return re.sub(r"[\s\-]+", "_", str(value or "").strip().lower())


def _list_schema_tables(profile_conn: MySQLCompatConnection) -> list[str]:
    cache_key = ("schema_tables", str(profile_conn.config["database"]), "")
    cached = _profile_metadata_cache_get(cache_key)
    if isinstance(cached, list):
        return list(cached)
    rows = profile_conn.execute(
        """
        SELECT table_name AS table_name
        FROM information_schema.tables
        WHERE table_schema = ?
        ORDER BY table_name
        """,
        (profile_conn.config["database"],),
    ).fetchall()
    tables = [str(row.get("table_name") or "").strip() for row in rows if str(row.get("table_name") or "").strip()]
    return list(_profile_metadata_cache_set(cache_key, tables))


def _list_table_columns(profile_conn: MySQLCompatConnection, source_table_name: str) -> list[str]:
    cache_key = ("table_columns", str(profile_conn.config["database"]), str(source_table_name))
    cached = _profile_metadata_cache_get(cache_key)
    if isinstance(cached, list):
        return list(cached)
    rows = profile_conn.execute(
        """
        SELECT column_name AS column_name
        FROM information_schema.columns
        WHERE table_schema = ? AND table_name = ?
        ORDER BY ordinal_position
        """,
        (profile_conn.config["database"], source_table_name),
    ).fetchall()
    columns = [str(row.get("column_name") or "").strip() for row in rows if str(row.get("column_name") or "").strip()]
    return list(_profile_metadata_cache_set(cache_key, columns))


def _table_exists(profile_conn: MySQLCompatConnection, table_name: str) -> bool:
    return str(table_name or "").strip() in set(_list_schema_tables(profile_conn))


def _table_column_set(profile_conn: MySQLCompatConnection, table_name: str) -> set[str]:
    return set(_list_table_columns(profile_conn, table_name))


def _column_exists(profile_conn: MySQLCompatConnection, table_name: str, column_name: str) -> bool:
    return str(column_name or "").strip() in _table_column_set(profile_conn, table_name)


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
    profile_conn: MySQLCompatConnection,
    photo_table: str,
    *,
    include_profile_id: bool = False,
    prioritize_avatar_type: bool = False,
) -> list[str]:
    columns = _table_column_set(profile_conn, photo_table)
    clauses: list[str] = []
    if include_profile_id:
        clauses.append(f"{schema.quote_mysql_ident('profile_id')} ASC")
    if "is_primary" in columns:
        clauses.append(f"{schema.quote_mysql_ident('is_primary')} DESC")
    if prioritize_avatar_type and "photo_type" in columns:
        clauses.append(
            f"CASE WHEN {schema.quote_mysql_ident('photo_type')} = 'avatar' THEN 0 ELSE 1 END ASC"
        )
    if "sort_order" in columns:
        clauses.append(f"{schema.quote_mysql_ident('sort_order')} ASC")
    if "id" in columns:
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
    cache_key = ("detected_profile_table", str(source_dsn), "")
    cached = _profile_metadata_cache_get(cache_key)
    if cached is not None:
        return str(cached) or None
    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
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
        return str(_profile_metadata_cache_set(cache_key, best_tables[0]))
    finally:
        release_profile_connection(source_dsn, profile_conn)


def list_profile_columns(
    *,
    source_dsn: str,
    source_table_name: str,
) -> list[str]:
    _require_profile_source(source_dsn=source_dsn, source_table_name=source_table_name)
    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        if not _table_exists(profile_conn, source_table_name):
            raise ValueError(f"profile table {source_table_name} was not found")
        return _list_table_columns(profile_conn, source_table_name)
    finally:
        release_profile_connection(source_dsn, profile_conn)


def list_profiles(
    *,
    source_dsn: str,
    source_table_name: str,
    where_clause: str = "",
    params: Sequence[Any] | None = None,
) -> list[dict[str, Any]]:
    return [
        row
        for batch in iter_profile_batches(
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            where_clause=where_clause,
            params=params,
            batch_size=0,
        )
        for row in batch
    ]


def iter_profile_batches(
    *,
    source_dsn: str,
    source_table_name: str,
    where_clause: str = "",
    params: Sequence[Any] | None = None,
    batch_size: int = 500,
):
    """Yield profile rows in batches. batch_size=0 yields a single batch (full fetch)."""
    _require_profile_source(source_dsn=source_dsn, source_table_name=source_table_name)
    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        if not _table_exists(profile_conn, source_table_name):
            raise ValueError(f"profile table {source_table_name} was not found")
        normalized_where = str(where_clause or "").strip()
        base_sql = f"SELECT * FROM {schema.quote_mysql_ident(source_table_name)}"
        if normalized_where:
            base_sql = f"{base_sql} {normalized_where}"
        query_params = tuple(params or ())

        if int(batch_size or 0) <= 0:
            rows = profile_conn.execute(base_sql, query_params).fetchall()
            if rows:
                yield [dict(row) for row in rows]
            return

        has_id_column = _column_exists(profile_conn, source_table_name, "id")
        page_size = max(1, int(batch_size))
        if not has_id_column:
            offset = 0
            while True:
                paged_sql = f"{base_sql} LIMIT {page_size} OFFSET {offset}"
                rows = profile_conn.execute(paged_sql, query_params).fetchall()
                if not rows:
                    break
                yield [dict(row) for row in rows]
                if len(rows) < page_size:
                    break
                offset += page_size
            return

        id_column = schema.quote_mysql_ident("id")
        ordered_base_sql = f"{base_sql} ORDER BY {id_column} ASC"
        last_seen_id: int | None = None
        while True:
            if last_seen_id is None:
                paged_sql = f"{ordered_base_sql} LIMIT {page_size}"
                paged_params = query_params
            elif normalized_where:
                paged_sql = (
                    f"SELECT * FROM {schema.quote_mysql_ident(source_table_name)} "
                    f"{normalized_where} AND {id_column} > ? "
                    f"ORDER BY {id_column} ASC LIMIT {page_size}"
                )
                paged_params = query_params + (last_seen_id,)
            else:
                paged_sql = (
                    f"SELECT * FROM {schema.quote_mysql_ident(source_table_name)} "
                    f"WHERE {id_column} > ? ORDER BY {id_column} ASC LIMIT {page_size}"
                )
                paged_params = (last_seen_id,)
            rows = profile_conn.execute(paged_sql, paged_params).fetchall()
            if not rows:
                break
            batch = [dict(row) for row in rows]
            yield batch
            if len(batch) < page_size:
                break
            last_ids = [int(row["id"]) for row in batch if row.get("id") is not None]
            if not last_ids:
                break
            last_seen_id = last_ids[-1]
    finally:
        release_profile_connection(source_dsn, profile_conn)


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
    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        if not _column_exists(profile_conn, source_table_name, "id"):
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
        # 释放连接回连接池，而不是关闭
        release_profile_connection(source_dsn, profile_conn)


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
    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        if not _table_exists(profile_conn, public_view_name):
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
        # 释放连接回连接池，而不是关闭
        release_profile_connection(source_dsn, profile_conn)


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
    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        photo_table = _resolve_profile_photos_table(source_dsn, photos_table_name=photos_table_name)
        if not photo_table:
            return {}
        if not _table_exists(profile_conn, photo_table):
            raise ValueError(f"profile photos table {photo_table} was not found")
        photo_columns = _table_column_set(profile_conn, photo_table)
        if "profile_id" not in photo_columns or "photo_url" not in photo_columns:
            raise ValueError(f"profile photos table {photo_table} must contain profile_id and photo_url columns")
        placeholders = ", ".join(["?"] * len(normalized_profile_ids))
        order_clauses = [f"{schema.quote_mysql_ident('profile_id')} ASC"]
        has_is_primary = "is_primary" in photo_columns
        if has_is_primary:
            order_clauses.append(f"CASE WHEN {schema.quote_mysql_ident('is_primary')} = 1 THEN 0 ELSE 1 END")
        elif "photo_type" in photo_columns:
            order_clauses.append(
                f"CASE WHEN {schema.quote_mysql_ident('photo_type')} = 'avatar' THEN 0 ELSE 1 END"
            )
        order_clauses.extend(
            clause
            for clause in _photo_table_order_clauses(
                profile_conn,
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
        release_profile_connection(source_dsn, profile_conn)


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
    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        if not _table_exists(profile_conn, source_table_name) or not _column_exists(profile_conn, source_table_name, "id"):
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
            and _table_exists(profile_conn, photo_table)
        ):
            photo_columns = _table_column_set(profile_conn, photo_table)
            if "profile_id" not in photo_columns or "photo_url" not in photo_columns:
                return out
            order_clauses = _photo_table_order_clauses(
                profile_conn,
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
        release_profile_connection(source_dsn, profile_conn)


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
    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        photo_table = _resolve_profile_photos_table(source_dsn, photos_table_name=photos_table_name)
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        if (
            photo_table
            and _table_exists(profile_conn, photo_table)
        ):
            photo_columns = _table_column_set(profile_conn, photo_table)
            if "profile_id" in photo_columns and "photo_url" in photo_columns:
                order_sql = ", ".join(_photo_table_order_clauses(profile_conn, photo_table, include_profile_id=True))
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
        if _table_exists(profile_conn, source_table_name) and _column_exists(profile_conn, source_table_name, "avatar_url"):
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
        release_profile_connection(source_dsn, profile_conn)


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


def create_profile_row(
    *,
    source_dsn: str,
    source_table_name: str,
    fields: Mapping[str, Any],
) -> int:
    """Insert a new row into the partner profile table and return its id."""
    _require_profile_source(source_dsn=source_dsn, source_table_name=source_table_name)
    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
    try:
        raw_conn = profile_conn.driver_connection
        if not schema.column_exists(raw_conn, source_table_name, "id"):
            raise ValueError(f"profile table {source_table_name} is missing id column")

        insert_fields: dict[str, Any] = {}
        for column, value in dict(fields).items():
            if value is None:
                continue
            if schema.column_exists(raw_conn, source_table_name, column):
                insert_fields[column] = value

        if schema.column_exists(raw_conn, source_table_name, "profile_status") and "profile_status" not in insert_fields:
            insert_fields["profile_status"] = "active"
        if schema.column_exists(raw_conn, source_table_name, "verified_level") and "verified_level" not in insert_fields:
            insert_fields["verified_level"] = "none"
        if schema.column_exists(raw_conn, source_table_name, "last_active_at") and "last_active_at" not in insert_fields:
            insert_fields["last_active_at"] = current_time()

        if not insert_fields:
            raise ValueError("no profile columns available for insert")

        columns = list(insert_fields.keys())
        placeholders = ", ".join("?" for _ in columns)
        quoted_columns = ", ".join(schema.quote_mysql_ident(column) for column in columns)
        values = [insert_fields[column] for column in columns]

        try:
            result = profile_conn.execute(
                f"INSERT INTO {schema.quote_mysql_ident(source_table_name)} "
                f"({quoted_columns}) VALUES ({placeholders})",
                tuple(values),
            )
            profile_id = int(getattr(result, "lastrowid", 0) or 0)
            if profile_id > 0:
                profile_conn.commit()
                return profile_id
        except Exception:
            pass

        next_row = profile_conn.execute(
            f"SELECT COALESCE(MAX({schema.quote_mysql_ident('id')}), 0) + 1 AS next_id "
            f"FROM {schema.quote_mysql_ident(source_table_name)}"
        ).fetchone()
        next_id = int((next_row or {}).get("next_id") or 0)
        if next_id <= 0:
            raise ValueError(f"Could not allocate profile id from {source_table_name}")

        profile_conn.execute(
            f"INSERT INTO {schema.quote_mysql_ident(source_table_name)} "
            f"({schema.quote_mysql_ident('id')}, {quoted_columns}) "
            f"VALUES (?, {placeholders})",
            (next_id,) + tuple(values),
        )
        profile_conn.commit()
        return next_id
    finally:
        release_profile_connection(source_dsn, profile_conn)


def upsert_profile_for_onboarding(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int | None,
    fields: Mapping[str, Any],
) -> tuple[int, str]:
    if profile_id is not None and int(profile_id) > 0:
        apply_profile_updates(
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            profile_id=int(profile_id),
            updates=fields,
        )
        return int(profile_id), "updated"
    new_id = create_profile_row(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        fields=fields,
    )
    return new_id, "created"


def apply_profile_updates(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_id: int,
    updates: Mapping[str, Any],
) -> dict[str, Any]:
    _require_profile_source(source_dsn=source_dsn, source_table_name=source_table_name)
    profile_conn = _connect_profile_db(source_dsn, use_pool=True, timeout=10.0)
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
        release_profile_connection(source_dsn, profile_conn)
