"""MySQL schema metadata and DDL helpers for recommendation and matchmaking outer systems."""

from __future__ import annotations

import hashlib
import re
import os
from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import parse_qs, quote, unquote, urlparse, urlunparse

MYSQL_SCHEMES = {"mysql", "mysql+pymysql"}
DEFAULT_CHARSET = "utf8mb4"
DEFAULT_COLLATION = "utf8mb4_unicode_ci"


@dataclass(frozen=True)
class ColumnDef:
    name: str
    mysql_type: str
    nullable: bool = True
    auto_increment: bool = False


@dataclass(frozen=True)
class UniqueKeyDef:
    columns: tuple[str, ...]
    name: str | None = None


@dataclass(frozen=True)
class IndexDef:
    columns: tuple[str, ...]
    name: str


@dataclass(frozen=True)
class ForeignKeyDef:
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]
    name: str | None = None


@dataclass(frozen=True)
class TableDef:
    name: str
    columns: tuple[ColumnDef, ...]
    primary_key: tuple[str, ...]
    uniques: tuple[UniqueKeyDef, ...] = ()
    indexes: tuple[IndexDef, ...] = ()
    foreign_keys: tuple[ForeignKeyDef, ...] = ()

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)


ASYNC_JOB_TABLE = TableDef(
    name="async_jobs",
    columns=(
        ColumnDef("job_id", "VARCHAR(64)", nullable=False),
        ColumnDef("job_type", "VARCHAR(128)", nullable=False),
        ColumnDef("status", "VARCHAR(32)", nullable=False),
        ColumnDef("payload_json", "LONGTEXT", nullable=False),
        ColumnDef("result_json", "LONGTEXT", nullable=True),
        ColumnDef("error_text", "LONGTEXT", nullable=True),
        ColumnDef("attempt_count", "INT DEFAULT 0", nullable=False),
        ColumnDef("max_attempts", "INT DEFAULT 3", nullable=False),
        ColumnDef("next_attempt_at", "DATETIME", nullable=True),
        ColumnDef("created_by", "VARCHAR(191)", nullable=True),
        ColumnDef("trace_id", "VARCHAR(128)", nullable=True),
        ColumnDef("claim_token", "VARCHAR(64)", nullable=True),
        ColumnDef("claim_started_at", "DATETIME", nullable=True),
        ColumnDef("claim_worker", "VARCHAR(191)", nullable=True),
        ColumnDef("created_at", "DATETIME", nullable=False),
        ColumnDef("started_at", "DATETIME", nullable=True),
        ColumnDef("finished_at", "DATETIME", nullable=True),
    ),
    primary_key=("job_id",),
    indexes=(
        IndexDef(("status", "next_attempt_at", "created_at"), "idx_async_jobs_due"),
        IndexDef(("claim_token",), "idx_async_jobs_claim_token"),
        IndexDef(("created_at",), "idx_async_jobs_created_at"),
    ),
)

def quote_mysql_ident(identifier: str) -> str:
    """
    安全地引用 MySQL 标识符（表名、列名），防止 SQL 注入。

    安全措施：
    1. 替换反引号为双反引号（MySQL 标准）
    2. 移除 NULL 字符（可能导致绕过）
    3. 限制长度（MySQL 标识符最长 64 字符）
    4. 验证标识符格式（只允许合法字符）

    Args:
        identifier: 待引用的标识符

    Returns:
        安全引用后的标识符，如 `table_name`

    Raises:
        ValueError: 如果标识符包含非法字符或过长
    """
    # 移除 NULL 字符和不可见字符
    normalized = str(identifier or "").strip()
    normalized = normalized.replace("\x00", "").replace("�", "")

    # 检查标识符长度
    if len(normalized) > 64:
        raise ValueError(
            f"MySQL identifier too long: {len(normalized)} characters (max 64). "
            f"Identifier: {normalized[:20]}..."
        )

    # 检查标识符是否为空
    if not normalized:
        raise ValueError("MySQL identifier cannot be empty")

    # 检查标识符是否包含非法字符（除了字母、数字、下划线、美元符号）
    # MySQL 标识符规则：第一个字符必须是字母或下划线，后续可以是字母、数字、下划线、美元符号
    # 但我们放宽限制，允许更多字符（如中文字符），只是用反引号引用
    illegal_chars = set()
    for char in normalized:
        # 禁止反引号（会被转义）、分号（注入风险）、斜杠（路径风险）
        if char in {";", "/", "\\"}:
            illegal_chars.add(char)

    if illegal_chars:
        raise ValueError(
            f"MySQL identifier contains illegal characters: {illegal_chars}. "
            f"Identifier: {normalized[:20]}..."
        )

    # 替换反引号为双反引号（MySQL 标准转义）
    escaped = normalized.replace("`", "``")

    # 返回引用后的标识符
    return f"`{escaped}`"


def normalize_prefix(prefix: str | None) -> str:
    value = (prefix or "").strip()
    if not value:
        return ""
    return value


def destination_table_name(table_name: str, prefix: str | None = None) -> str:
    return f"{normalize_prefix(prefix)}{table_name}"


def stable_name(*parts: str) -> str:
    base = "_".join(part for part in parts if part)
    safe = re.sub(r"[^0-9A-Za-z_]+", "_", base).strip("_")
    safe = re.sub(r"_+", "_", safe)
    if not safe:
        safe = "idx"
    if len(safe) <= 64:
        return safe
    digest = hashlib.sha1(safe.encode("utf-8")).hexdigest()[:8]
    head = safe[:55]
    return f"{head}_{digest}"


def parse_mysql_dsn(dsn: str) -> dict[str, Any]:
    parsed = urlparse(inject_mysql_password_into_dsn(str(dsn)))
    if parsed.scheme.lower() not in MYSQL_SCHEMES:
        raise ValueError(f"Unsupported MySQL DSN: {dsn}")

    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise ValueError("MySQL DSN must include a database name.")

    query = parse_qs(parsed.query)
    return {
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 3306,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else "",
        "database": database,
        "charset": query.get("charset", [DEFAULT_CHARSET])[0],
        "collation": query.get("collation", [DEFAULT_COLLATION])[0],
    }


def _mysql_secret_from_env() -> str:
    direct = str(os.environ.get("MYSQL_ROOT_PASSWORD") or "").strip()
    if direct:
        return direct
    secret_file = str(os.environ.get("MYSQL_ROOT_PASSWORD_FILE") or "").strip()
    if not secret_file:
        return ""
    try:
        with open(secret_file, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def inject_mysql_password_into_dsn(dsn: str) -> str:
    parsed = urlparse(str(dsn))
    if parsed.scheme.lower() not in MYSQL_SCHEMES:
        return str(dsn)
    if parsed.password or (parsed.username or "") != "root":
        return str(dsn)

    password = _mysql_secret_from_env()
    if not password:
        return str(dsn)

    host = parsed.hostname or "127.0.0.1"
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    userinfo = f"{quote(unquote(parsed.username or 'root'), safe='')}:{quote(password, safe='')}"
    netloc = f"{userinfo}@{host}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def mysql_server_connect(config: dict[str, Any]):
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
        raise SystemExit("Missing dependency: pymysql") from exc

    return pymysql.connect(
        host=config["host"],
        port=int(config["port"]),
        user=config.get("user"),
        password=config.get("password") or "",
        charset=config.get("charset") or DEFAULT_CHARSET,
        autocommit=True,
        cursorclass=DictCursor,
    )


def mysql_database_connect(config: dict[str, Any]):
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:  # pragma: no cover - exercised only when dependency is missing
        raise SystemExit("Missing dependency: pymysql") from exc

    return pymysql.connect(
        host=config["host"],
        port=int(config["port"]),
        user=config.get("user"),
        password=config.get("password") or "",
        database=config["database"],
        charset=config.get("charset") or DEFAULT_CHARSET,
        autocommit=False,
        cursorclass=DictCursor,
    )


def ensure_database(config: dict[str, Any]) -> None:
    """确保数据库存在，先检查后创建，避免不必要的 metadata lock"""
    database_name = config['database']

    # 先检查数据库是否已存在
    with mysql_server_connect(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
                "WHERE SCHEMA_NAME = %s",
                (database_name,)
            )
            result = cursor.fetchone()

            # 只有数据库不存在时才创建
            if not result:
                cursor.execute(
                    f"CREATE DATABASE {quote_mysql_ident(database_name)} "
                    f"CHARACTER SET {config.get('charset') or DEFAULT_CHARSET} "
                    f"COLLATE {config.get('collation') or DEFAULT_COLLATION}"
                )


def build_create_table_sql(table: TableDef, *, prefix: str | None = None, config: dict[str, Any] | None = None) -> str:
    charset = (config or {}).get("charset") or DEFAULT_CHARSET
    collation = (config or {}).get("collation") or DEFAULT_COLLATION
    dest_table = destination_table_name(table.name, prefix)
    parts: list[str] = []

    for column in table.columns:
        rendered = f"{quote_mysql_ident(column.name)} {column.mysql_type}"
        if not column.nullable:
            rendered += " NOT NULL"
        if column.auto_increment:
            rendered += " AUTO_INCREMENT"
        parts.append(rendered)

    parts.append(
        "PRIMARY KEY ("
        + ", ".join(quote_mysql_ident(column) for column in table.primary_key)
        + ")"
    )

    for unique in table.uniques:
        unique_name = unique.name or stable_name("uniq", dest_table, *unique.columns)
        parts.append(
            f"UNIQUE KEY {quote_mysql_ident(unique_name)} ("
            + ", ".join(quote_mysql_ident(column) for column in unique.columns)
            + ")"
        )

    for foreign_key in table.foreign_keys:
        fk_name = foreign_key.name or stable_name("fk", dest_table, *foreign_key.columns, foreign_key.ref_table)
        ref_table = destination_table_name(foreign_key.ref_table, prefix)
        parts.append(
            f"CONSTRAINT {quote_mysql_ident(fk_name)} FOREIGN KEY ("
            + ", ".join(quote_mysql_ident(column) for column in foreign_key.columns)
            + ") REFERENCES "
            + quote_mysql_ident(ref_table)
            + " ("
            + ", ".join(quote_mysql_ident(column) for column in foreign_key.ref_columns)
            + ")"
        )

    return (
        f"CREATE TABLE IF NOT EXISTS {quote_mysql_ident(dest_table)} (\n  "
        + ",\n  ".join(parts)
        + f"\n) ENGINE=InnoDB DEFAULT CHARSET={charset} COLLATE={collation}"
    )


def table_exists(mysql_conn, table_name: str) -> bool:
    with mysql_conn.cursor() as cursor:
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        return cursor.fetchone() is not None


def index_exists(mysql_conn, table_name: str, index_name: str) -> bool:
    with mysql_conn.cursor() as cursor:
        cursor.execute(f"SHOW INDEX FROM {quote_mysql_ident(table_name)} WHERE Key_name = %s", (index_name,))
        return cursor.fetchone() is not None


def column_exists(mysql_conn, table_name: str, column_name: str) -> bool:
    with mysql_conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            LIMIT 1
            """,
            (table_name, column_name),
        )
        return cursor.fetchone() is not None


def ensure_table_columns(mysql_conn, table: TableDef, *, prefix: str | None = None) -> None:
    """Apply ``ALTER TABLE ... ADD COLUMN`` for any column missing from an existing table."""

    dest = destination_table_name(table.name, prefix)
    if not table_exists(mysql_conn, dest):
        return
    for col in table.columns:
        if column_exists(mysql_conn, dest, col.name):
            continue
        rendered = f"{quote_mysql_ident(col.name)} {col.mysql_type}"
        if col.nullable:
            rendered += " NULL"
        else:
            rendered += " NOT NULL"
        if col.auto_increment:
            rendered += " AUTO_INCREMENT"
        alter_sql = f"ALTER TABLE {quote_mysql_ident(dest)} ADD COLUMN {rendered}"
        with mysql_conn.cursor() as cursor:
            try:
                cursor.execute(alter_sql)
            except Exception as exc:  # noqa: BLE001
                if "Duplicate column name" in str(exc):
                    continue
                raise


def ensure_table(mysql_conn, table: TableDef, *, prefix: str | None = None, config: dict[str, Any] | None = None) -> None:
    sql = build_create_table_sql(table, prefix=prefix, config=config)
    with mysql_conn.cursor() as cursor:
        cursor.execute(sql)


def ensure_unique_keys(mysql_conn, table: TableDef, *, prefix: str | None = None) -> list[str]:
    dest_table = destination_table_name(table.name, prefix)
    created: list[str] = []
    with mysql_conn.cursor() as cursor:
        for unique in table.uniques:
            unique_name = unique.name or stable_name("uniq", dest_table, *unique.columns)
            if index_exists(mysql_conn, dest_table, unique_name):
                continue
            try:
                cursor.execute(
                    f"ALTER TABLE {quote_mysql_ident(dest_table)} ADD UNIQUE KEY {quote_mysql_ident(unique_name)} ("
                    + ", ".join(quote_mysql_ident(column) for column in unique.columns)
                    + ")"
                )
            except Exception as exc:  # noqa: BLE001
                if "Duplicate key name" in str(exc):
                    continue
                raise
            created.append(unique_name)
    return created


def ensure_indexes(mysql_conn, table: TableDef, *, prefix: str | None = None) -> list[str]:
    dest_table = destination_table_name(table.name, prefix)
    created: list[str] = []
    with mysql_conn.cursor() as cursor:
        for index in table.indexes:
            index_name = stable_name(normalize_prefix(prefix), index.name)
            if index_exists(mysql_conn, dest_table, index_name):
                continue
            try:
                cursor.execute(
                    f"CREATE INDEX {quote_mysql_ident(index_name)} ON {quote_mysql_ident(dest_table)} ("
                    + ", ".join(quote_mysql_ident(column) for column in index.columns)
                    + ")"
                )
            except Exception as exc:  # noqa: BLE001
                if "Duplicate key name" in str(exc):
                    continue
                raise
            created.append(index_name)
    return created


def clear_tables(mysql_conn, tables: Sequence[TableDef], *, prefix: str | None = None) -> None:
    ordered_names = [destination_table_name(table.name, prefix) for table in reversed(tables)]
    with mysql_conn.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        try:
            for table_name in ordered_names:
                if not table_exists(mysql_conn, table_name):
                    continue
                cursor.execute(f"DELETE FROM {quote_mysql_ident(table_name)}")
        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")


def validate_schema(mysql_conn, tables: Sequence[TableDef], *, prefix: str | None = None) -> dict[str, list[str]]:
    missing_tables: list[str] = []
    missing_columns: list[str] = []
    missing_unique_keys: list[str] = []
    missing_indexes: list[str] = []

    for table in tables:
        dest_table = destination_table_name(table.name, prefix)
        if not table_exists(mysql_conn, dest_table):
            missing_tables.append(dest_table)
            continue

        for column in table.columns:
            if not column_exists(mysql_conn, dest_table, column.name):
                missing_columns.append(f"{dest_table}.{column.name}")

        for unique in table.uniques:
            unique_name = unique.name or stable_name("uniq", dest_table, *unique.columns)
            if not index_exists(mysql_conn, dest_table, unique_name):
                missing_unique_keys.append(f"{dest_table}.{unique_name}")

        for index in table.indexes:
            index_name = stable_name(normalize_prefix(prefix), index.name)
            if not index_exists(mysql_conn, dest_table, index_name):
                missing_indexes.append(f"{dest_table}.{index_name}")

    return {
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "missing_unique_keys": missing_unique_keys,
        "missing_indexes": missing_indexes,
    }

def recommendation_tables() -> tuple[TableDef, ...]:
    return (
        TableDef(
            name="saved_search_subscriptions",
            columns=(
                ColumnDef("subscription_id", "VARCHAR(191)", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                ColumnDef("title", "VARCHAR(255)", nullable=False),
                ColumnDef("status", "VARCHAR(64)", nullable=False),
                ColumnDef("is_still_searching", "TINYINT(1)", nullable=False),
                ColumnDef("source", "VARCHAR(512)", nullable=False),
                ColumnDef("table_name", "VARCHAR(191)"),
                ColumnDef("photos_table_name", "VARCHAR(191)"),
                ColumnDef("search_criteria_json", "LONGTEXT", nullable=False),
                ColumnDef("initial_request_json", "LONGTEXT", nullable=False),
                ColumnDef("subscription_overrides_json", "LONGTEXT", nullable=False),
                ColumnDef("self_profile_json", "LONGTEXT"),
                ColumnDef("self_id", "BIGINT"),
                ColumnDef("limit_count", "INT", nullable=False),
                ColumnDef("top_k", "INT", nullable=False),
                ColumnDef("min_notify_score", "INT", nullable=False),
                ColumnDef("daily_notification_cap", "INT", nullable=False),
                ColumnDef("quiet_hours_start", "INT", nullable=False),
                ColumnDef("quiet_hours_end", "INT", nullable=False),
                ColumnDef("refresh_interval_hours", "INT", nullable=False),
                ColumnDef("skip_cooldown_days", "INT", nullable=False),
                ColumnDef("recommendation_mode", "VARCHAR(64)", nullable=False),
                ColumnDef("direct_greet_profile_json", "LONGTEXT", nullable=False),
                ColumnDef("max_review_candidates_per_refresh", "INT", nullable=False),
                ColumnDef("min_direct_greet_score", "INT", nullable=False),
                ColumnDef("auto_reject_on_follow_up_questions", "TINYINT(1)", nullable=False),
                ColumnDef("auto_reject_on_risk_flags", "TINYINT(1)", nullable=False),
                ColumnDef("last_refreshed_at", "DATETIME"),
                ColumnDef("last_result_count", "INT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("subscription_id",),
            indexes=(
                IndexDef(("status", "is_still_searching", "last_refreshed_at"), "idx_saved_search_due"),
            ),
        ),
        TableDef(
            name="profile_recommendations",
            columns=(
                ColumnDef("recommendation_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("subscription_id", "VARCHAR(191)", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                ColumnDef("candidate_id", "BIGINT", nullable=False),
                ColumnDef("candidate_name", "VARCHAR(255)", nullable=False),
                ColumnDef("score", "INT", nullable=False),
                ColumnDef("fit_score", "INT", nullable=False),
                ColumnDef("confidence_score", "INT", nullable=False),
                ColumnDef("risk_score", "INT", nullable=False),
                ColumnDef("delivery_status", "VARCHAR(64)", nullable=False),
                ColumnDef("delivery_reason", "TEXT"),
                ColumnDef("first_seen_at", "DATETIME", nullable=False),
                ColumnDef("last_seen_at", "DATETIME", nullable=False),
                ColumnDef("notified_at", "DATETIME"),
                ColumnDef("cooling_until", "DATETIME"),
                ColumnDef("last_action_type", "VARCHAR(64)"),
                ColumnDef("matched_on_json", "LONGTEXT", nullable=False),
                ColumnDef("risk_flags_json", "LONGTEXT", nullable=False),
                ColumnDef("latest_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("final_review_status", "VARCHAR(64)", nullable=False),
                ColumnDef("final_review_reason", "TEXT"),
                ColumnDef("final_review_score", "INT", nullable=False),
                ColumnDef("final_review_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("reviewed_at", "DATETIME"),
                ColumnDef("candidate_snapshot_hash", "VARCHAR(64)"),
                ColumnDef("user_review_status", "VARCHAR(64)", nullable=False),
                ColumnDef("user_review_reason", "TEXT"),
                ColumnDef("user_review_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("user_reviewed_at", "DATETIME"),
                ColumnDef("relation_key", "VARCHAR(768)"),
                ColumnDef("owner_profile_ref_json", "LONGTEXT", nullable=False),
                ColumnDef("target_profile_ref_json", "LONGTEXT", nullable=False),
                ColumnDef("active_match_case_id", "VARCHAR(191)"),
                ColumnDef("active_case_status", "VARCHAR(64)"),
                ColumnDef("gate_outcome", "VARCHAR(16)"),
                ColumnDef("gate_reason_codes_json", "LONGTEXT"),
                ColumnDef("gate_owner_service", "VARCHAR(64)"),
                ColumnDef("gate_details_ref", "VARCHAR(255)"),
                ColumnDef("gate_evaluated_at", "DATETIME"),
                ColumnDef("latest_card_id", "VARCHAR(191)"),
                ColumnDef("rule_provenance_json", "LONGTEXT"),
            ),
            primary_key=("recommendation_id",),
            uniques=(
                UniqueKeyDef(("subscription_id", "candidate_id")),
            ),
            indexes=(
                IndexDef(("subscription_id", "delivery_status", "score"), "idx_recommendations_subscription_status"),
                IndexDef(("requester_id", "delivery_status", "notified_at"), "idx_recommendations_requester_status"),
                IndexDef(("subscription_id", "final_review_status", "score"), "idx_recommendations_review_status"),
                IndexDef(("subscription_id", "score", "last_seen_at", "recommendation_id"), "idx_recommendations_subscription_score_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("subscription_id",), "saved_search_subscriptions", ("subscription_id",)),
            ),
        ),
        TableDef(
            name="recommendation_actions",
            columns=(
                ColumnDef("action_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("subscription_id", "VARCHAR(191)", nullable=False),
                ColumnDef("recommendation_id", "BIGINT", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                ColumnDef("candidate_id", "BIGINT", nullable=False),
                ColumnDef("action_type", "VARCHAR(64)", nullable=False),
                ColumnDef("action_payload_json", "LONGTEXT"),
                ColumnDef("client_idempotency_key", "VARCHAR(191)"),
                ColumnDef("occurred_at", "DATETIME", nullable=False),
            ),
            primary_key=("action_id",),
            indexes=(
                IndexDef(("recommendation_id", "occurred_at"), "idx_actions_recommendation_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("recommendation_id",), "profile_recommendations", ("recommendation_id",)),
            ),
        ),
        TableDef(
            name="in_app_recommendation_cards",
            columns=(
                ColumnDef("card_id", "VARCHAR(191)", nullable=False),
                ColumnDef("subscription_id", "VARCHAR(191)", nullable=False),
                ColumnDef("recommendation_id", "BIGINT", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                ColumnDef("candidate_id", "BIGINT", nullable=False),
                ColumnDef("card_status", "VARCHAR(32)", nullable=False),
                ColumnDef("title", "VARCHAR(255)", nullable=False),
                ColumnDef("subtitle", "VARCHAR(512)", nullable=False),
                ColumnDef("body", "TEXT", nullable=False),
                ColumnDef("payload_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("delivered_at", "DATETIME", nullable=False),
                ColumnDef("read_at", "DATETIME"),
            ),
            primary_key=("card_id",),
            indexes=(
                IndexDef(("requester_id", "delivered_at"), "idx_cards_requester_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("recommendation_id",), "profile_recommendations", ("recommendation_id",)),
            ),
        ),
        TableDef(
            name="saved_search_runs",
            columns=(
                ColumnDef("run_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("subscription_id", "VARCHAR(191)", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                ColumnDef("source", "VARCHAR(512)", nullable=False),
                ColumnDef("table_name", "VARCHAR(191)"),
                ColumnDef("photos_table_name", "VARCHAR(191)"),
                ColumnDef("self_id", "BIGINT"),
                ColumnDef("persona_profile_json", "LONGTEXT", nullable=False),
                ColumnDef("effective_criteria_json", "LONGTEXT", nullable=False),
                ColumnDef("search_request_json", "LONGTEXT", nullable=False),
                ColumnDef("result_count", "INT", nullable=False),
                ColumnDef("top_candidate_ids_json", "LONGTEXT", nullable=False),
                ColumnDef("status_counts_json", "LONGTEXT", nullable=False),
                ColumnDef("review_counts_json", "LONGTEXT", nullable=False),
                ColumnDef("rule_provenance_json", "LONGTEXT"),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("run_id",),
            indexes=(
                IndexDef(("subscription_id", "created_at"), "idx_saved_search_runs_subscription_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("subscription_id",), "saved_search_subscriptions", ("subscription_id",)),
            ),
        ),
        TableDef(
            name="match_cases",
            columns=(
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("subscription_id", "VARCHAR(191)", nullable=False),
                ColumnDef("recommendation_id", "BIGINT", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                ColumnDef("candidate_id", "BIGINT", nullable=False),
                ColumnDef("candidate_name", "VARCHAR(255)", nullable=False),
                ColumnDef("initiated_by", "VARCHAR(64)", nullable=False),
                ColumnDef("case_type", "VARCHAR(64)", nullable=False),
                ColumnDef("case_status", "VARCHAR(64)", nullable=False),
                ColumnDef("close_reason", "VARCHAR(191)"),
                ColumnDef("outreach_channel", "VARCHAR(64)", nullable=False),
                ColumnDef("safe_summary_json", "LONGTEXT", nullable=False),
                ColumnDef("requester_profile_snapshot_json", "LONGTEXT", nullable=False),
                ColumnDef("candidate_snapshot_json", "LONGTEXT", nullable=False),
                ColumnDef("outreach_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("reply_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("reply_deadline_at", "DATETIME"),
                ColumnDef("outreach_sent_at", "DATETIME"),
                ColumnDef("replied_at", "DATETIME"),
                ColumnDef("cooling_until", "DATETIME"),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("case_id",),
            indexes=(
                IndexDef(("subscription_id", "case_status", "created_at"), "idx_match_cases_subscription_status"),
                IndexDef(("recommendation_id", "case_status", "updated_at"), "idx_match_cases_recommendation_status"),
                IndexDef(("requester_id", "case_status", "updated_at"), "idx_match_cases_requester_status"),
            ),
            foreign_keys=(
                ForeignKeyDef(("subscription_id",), "saved_search_subscriptions", ("subscription_id",)),
                ForeignKeyDef(("recommendation_id",), "profile_recommendations", ("recommendation_id",)),
            ),
        ),
        TableDef(
            name="match_case_events",
            columns=(
                ColumnDef("event_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("subscription_id", "VARCHAR(191)", nullable=False),
                ColumnDef("recommendation_id", "BIGINT", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                ColumnDef("candidate_id", "BIGINT", nullable=False),
                ColumnDef("event_type", "VARCHAR(64)", nullable=False),
                ColumnDef("from_status", "VARCHAR(64)"),
                ColumnDef("to_status", "VARCHAR(64)"),
                ColumnDef("actor_type", "VARCHAR(32)", nullable=False),
                ColumnDef("canonical_event_json", "LONGTEXT", nullable=True),
                ColumnDef("payload_json", "LONGTEXT", nullable=False),
                ColumnDef("occurred_at", "DATETIME", nullable=False),
            ),
            primary_key=("event_id",),
            indexes=(
                IndexDef(("case_id", "occurred_at"), "idx_match_case_events_case_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("case_id",), "match_cases", ("case_id",)),
            ),
        ),
        TableDef(
            name="match_case_outreach_attempts",
            columns=(
                ColumnDef("attempt_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("attempt_number", "INT", nullable=False),
                ColumnDef("channel", "VARCHAR(64)", nullable=False),
                ColumnDef("delivery_status", "VARCHAR(64)", nullable=False),
                ColumnDef("payload_json", "LONGTEXT", nullable=False),
                ColumnDef("provider_message_id", "VARCHAR(191)"),
                ColumnDef("error_code", "VARCHAR(64)"),
                ColumnDef("sent_at", "DATETIME", nullable=False),
            ),
            primary_key=("attempt_id",),
            uniques=(
                UniqueKeyDef(("case_id", "attempt_number")),
            ),
            indexes=(
                IndexDef(("case_id", "sent_at"), "idx_match_case_attempts_case_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("case_id",), "match_cases", ("case_id",)),
            ),
        ),
        TableDef(
            name="outbox_events",
            columns=(
                ColumnDef("outbox_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("canonical_event_id", "VARCHAR(64)", nullable=False),
                ColumnDef("aggregate_type", "VARCHAR(32)", nullable=False),
                ColumnDef("aggregate_id", "VARCHAR(191)", nullable=False),
                ColumnDef("event_type", "VARCHAR(64)", nullable=False),
                ColumnDef("source_service", "VARCHAR(64)", nullable=False),
                ColumnDef("canonical_event_json", "LONGTEXT", nullable=False),
                ColumnDef("source_row_table", "VARCHAR(64)", nullable=False),
                ColumnDef("source_row_id", "BIGINT", nullable=True),
                ColumnDef("publish_status", "VARCHAR(32)", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("published_at", "DATETIME", nullable=True),
            ),
            primary_key=("outbox_id",),
            uniques=(
                UniqueKeyDef(("canonical_event_id",), name="uniq_outbox_canonical_event_id"),
            ),
            indexes=(
                IndexDef(("publish_status", "created_at"), "idx_outbox_pending_time"),
            ),
        ),
        TableDef(
            name="criteria_snapshots",
            columns=(
                ColumnDef("snapshot_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("scene", "VARCHAR(64)", nullable=False),
                ColumnDef("criteria_hash", "VARCHAR(64)", nullable=False),
                ColumnDef("compiled_json", "LONGTEXT", nullable=False),
                ColumnDef("source_map_json", "LONGTEXT", nullable=False),
                ColumnDef("runtime_explanation_json", "LONGTEXT"),
                ColumnDef("profile_id", "BIGINT"),
                ColumnDef("requester_id", "BIGINT"),
                ColumnDef("user_key", "VARCHAR(191)"),
                ColumnDef("subscription_id", "VARCHAR(191)"),
                ColumnDef("discovery_session_id", "VARCHAR(191)"),
                ColumnDef("recommendation_id", "BIGINT"),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("snapshot_id",),
            indexes=(
                IndexDef(("recommendation_id", "created_at"), "idx_criteria_snapshots_recommendation_time"),
                IndexDef(("profile_id", "created_at"), "idx_criteria_snapshots_profile_time"),
                IndexDef(("discovery_session_id", "created_at"), "idx_criteria_snapshots_discovery_time"),
                IndexDef(("criteria_hash",), "idx_criteria_snapshots_hash"),
            ),
            foreign_keys=(
                ForeignKeyDef(("recommendation_id",), "profile_recommendations", ("recommendation_id",)),
            ),
        ),
        ASYNC_JOB_TABLE,
        TableDef(
            name="rule_config_versions",
            columns=(
                ColumnDef("version_id", "VARCHAR(191)", nullable=False),
                ColumnDef("slice_id", "VARCHAR(191)", nullable=False),
                ColumnDef("params_json", "LONGTEXT", nullable=False),
                ColumnDef("schema_version", "VARCHAR(32)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("created_by", "VARCHAR(191)", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("version_id",),
            indexes=(
                IndexDef(("slice_id", "status", "created_at"), "idx_rule_config_versions_slice_status"),
            ),
        ),
        TableDef(
            name="rule_config_assignments",
            columns=(
                ColumnDef("assignment_id", "VARCHAR(191)", nullable=False),
                ColumnDef("version_id", "VARCHAR(191)", nullable=False),
                ColumnDef("slice_id", "VARCHAR(191)", nullable=False),
                ColumnDef("scope_type", "VARCHAR(64)", nullable=False),
                ColumnDef("scope_key", "VARCHAR(191)", nullable=False),
                ColumnDef("priority", "INT", nullable=False),
                ColumnDef("effective_from", "DATETIME"),
                ColumnDef("effective_until", "DATETIME"),
                ColumnDef("created_by", "VARCHAR(191)", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("assignment_id",),
            indexes=(
                IndexDef(
                    ("slice_id", "scope_type", "scope_key", "priority"),
                    "idx_rule_config_assignments_scope",
                ),
            ),
            foreign_keys=(
                ForeignKeyDef(("version_id",), "rule_config_versions", ("version_id",)),
            ),
        ),
        TableDef(
            name="experiment_bucket_members",
            columns=(
                ColumnDef("profile_id", "BIGINT", nullable=False),
                ColumnDef("bucket_key", "VARCHAR(191)", nullable=False),
                ColumnDef("updated_by", "VARCHAR(191)", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("profile_id",),
            indexes=(
                IndexDef(("bucket_key", "updated_at"), "idx_experiment_bucket_members_bucket"),
            ),
        ),
    )


def chat_tables() -> tuple[TableDef, ...]:
    """Standalone chat persistence (see ``docs/chat-agent-architecture.md``)."""

    return (
        TableDef(
            name="chat_threads",
            columns=(
                ColumnDef("thread_id", "VARCHAR(64)", nullable=False),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("relation_key", "VARCHAR(191)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("participant_a_id", "VARCHAR(191)", nullable=False),
                ColumnDef("participant_b_id", "VARCHAR(191)", nullable=False),
                ColumnDef("metadata_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("thread_id",),
            uniques=(UniqueKeyDef(("case_id",), name="uniq_chat_threads_case_id"),),
            indexes=(IndexDef(("relation_key",), "idx_chat_threads_relation_key"),),
        ),
        TableDef(
            name="chat_messages",
            columns=(
                ColumnDef("message_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("thread_id", "VARCHAR(64)", nullable=False),
                ColumnDef("author_id", "VARCHAR(191)", nullable=False),
                ColumnDef("message_recipient_id", "VARCHAR(191)", nullable=True),
                ColumnDef("visibility", "VARCHAR(32)", nullable=False),
                ColumnDef("source", "VARCHAR(32)", nullable=False),
                ColumnDef("body", "LONGTEXT", nullable=False),
                ColumnDef("client_msg_id", "VARCHAR(191)", nullable=True),
                ColumnDef("reply_to_message_id", "BIGINT", nullable=True),
                ColumnDef("metadata_json", "LONGTEXT", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("message_id",),
            uniques=(
                UniqueKeyDef(("thread_id", "client_msg_id"), name="uniq_chat_messages_thread_client"),
            ),
            indexes=(
                IndexDef(("thread_id", "created_at"), "idx_chat_messages_thread_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("thread_id",), "chat_threads", ("thread_id",)),
            ),
        ),
        TableDef(
            name="chat_conversations",
            columns=(
                ColumnDef("conversation_id", "VARCHAR(64)", nullable=False),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("relation_key", "VARCHAR(191)", nullable=False),
                ColumnDef("channel_key", "VARCHAR(191)", nullable=False),
                ColumnDef("conversation_kind", "VARCHAR(32)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("metadata_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("conversation_id",),
            uniques=(
                UniqueKeyDef(("case_id", "channel_key"), name="uniq_chat_conversations_case_channel"),
            ),
            indexes=(
                IndexDef(("case_id", "created_at"), "idx_chat_conversations_case_time"),
                IndexDef(("conversation_kind", "status"), "idx_chat_conversations_kind_status"),
                IndexDef(("channel_key", "status", "created_at", "case_id"), "idx_chat_conversations_channel_status_time"),
            ),
        ),
        TableDef(
            name="chat_conversation_members",
            columns=(
                ColumnDef("conversation_id", "VARCHAR(64)", nullable=False),
                ColumnDef("participant_id", "VARCHAR(191)", nullable=False),
                ColumnDef("member_role", "VARCHAR(32)", nullable=False),
                ColumnDef("can_read", "TINYINT(1)", nullable=False),
                ColumnDef("can_send", "TINYINT(1)", nullable=False),
                ColumnDef("metadata_json", "LONGTEXT", nullable=False),
                ColumnDef("joined_at", "DATETIME", nullable=False),
                ColumnDef("left_at", "DATETIME", nullable=True),
            ),
            primary_key=("conversation_id", "participant_id"),
            indexes=(
                IndexDef(("participant_id", "conversation_id"), "idx_chat_conversation_members_participant"),
            ),
            foreign_keys=(
                ForeignKeyDef(("conversation_id",), "chat_conversations", ("conversation_id",)),
            ),
        ),
        TableDef(
            name="chat_conversation_messages",
            columns=(
                ColumnDef("message_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("conversation_id", "VARCHAR(64)", nullable=False),
                ColumnDef("author_id", "VARCHAR(191)", nullable=False),
                ColumnDef("source", "VARCHAR(32)", nullable=False),
                ColumnDef("body", "LONGTEXT", nullable=False),
                ColumnDef("client_msg_id", "VARCHAR(191)", nullable=True),
                ColumnDef("reply_to_message_id", "BIGINT", nullable=True),
                ColumnDef("metadata_json", "LONGTEXT", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("message_id",),
            uniques=(
                UniqueKeyDef(("conversation_id", "client_msg_id"), name="uniq_chat_conversation_messages_client"),
            ),
            indexes=(
                IndexDef(("conversation_id", "created_at"), "idx_chat_conversation_messages_time"),
                IndexDef(("conversation_id", "message_id"), "idx_chat_conversation_messages_conversation_message"),
                IndexDef(("conversation_id", "author_id", "source", "created_at"), "idx_chat_conversation_messages_author_source_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("conversation_id",), "chat_conversations", ("conversation_id",)),
            ),
        ),
        TableDef(
            name="chat_agent_sessions",
            columns=(
                ColumnDef("session_id", "VARCHAR(64)", nullable=False),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("relation_key", "VARCHAR(191)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("participant_a_id", "VARCHAR(191)", nullable=False),
                ColumnDef("participant_b_id", "VARCHAR(191)", nullable=False),
                ColumnDef("agent_participant_id", "VARCHAR(191)", nullable=False),
                ColumnDef("triggered_by_message_id", "BIGINT", nullable=True),
                ColumnDef("last_seen_message_id", "BIGINT", nullable=True),
                ColumnDef("last_user_message_at", "DATETIME", nullable=True),
                ColumnDef("last_agent_message_at", "DATETIME", nullable=True),
                ColumnDef("last_replied_at", "DATETIME", nullable=True),
                ColumnDef("cooldown_until", "DATETIME", nullable=True),
                ColumnDef("close_reason", "VARCHAR(64)", nullable=True),
                ColumnDef("state_json", "LONGTEXT", nullable=False),
                ColumnDef("started_at", "DATETIME", nullable=False),
                ColumnDef("ended_at", "DATETIME", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("session_id",),
            uniques=(
                UniqueKeyDef(("case_id",), name="uniq_chat_agent_sessions_case"),
            ),
            indexes=(
                IndexDef(("status", "updated_at"), "idx_chat_agent_sessions_status_updated"),
                IndexDef(("agent_participant_id", "status"), "idx_chat_agent_sessions_agent_status"),
                IndexDef(("status", "last_user_message_at", "session_id"), "idx_chat_agent_sessions_status_last_user"),
            ),
        ),
        TableDef(
            name="chat_agent_tasks",
            columns=(
                ColumnDef("task_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("session_id", "VARCHAR(64)", nullable=False),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("trigger_conversation_id", "VARCHAR(64)", nullable=False),
                ColumnDef("trigger_message_id", "BIGINT", nullable=False),
                ColumnDef("trigger_author_id", "VARCHAR(191)", nullable=False),
                ColumnDef("trigger_channel_key", "VARCHAR(191)", nullable=False),
                ColumnDef("reason", "VARCHAR(64)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("attempt_count", "INT", nullable=False),
                ColumnDef("lease_until", "DATETIME", nullable=True),
                ColumnDef("dedupe_key", "VARCHAR(191)", nullable=False),
                ColumnDef("result_json", "LONGTEXT", nullable=True),
                ColumnDef("error_text", "LONGTEXT", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("started_at", "DATETIME", nullable=True),
                ColumnDef("finished_at", "DATETIME", nullable=True),
            ),
            primary_key=("task_id",),
            uniques=(
                UniqueKeyDef(("dedupe_key",), name="uniq_chat_agent_tasks_dedupe"),
            ),
            indexes=(
                IndexDef(("status", "created_at"), "idx_chat_agent_tasks_status_created"),
                IndexDef(("session_id", "created_at"), "idx_chat_agent_tasks_session_created"),
                IndexDef(("case_id", "trigger_message_id"), "idx_chat_agent_tasks_case_message"),
                IndexDef(("session_id", "status", "created_at"), "idx_chat_agent_tasks_session_status_created"),
                IndexDef(("status", "lease_until", "created_at"), "idx_chat_agent_tasks_status_lease_created"),
            ),
            foreign_keys=(
                ForeignKeyDef(("session_id",), "chat_agent_sessions", ("session_id",)),
            ),
        ),
        TableDef(
            name="chat_thread_summaries",
            columns=(
                ColumnDef("thread_id", "VARCHAR(64)", nullable=False),
                ColumnDef("summary_text", "LONGTEXT", nullable=False),
                ColumnDef("summary_mode", "VARCHAR(32)", nullable=False),
                ColumnDef("last_message_id", "BIGINT", nullable=True),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("thread_id",),
            indexes=(IndexDef(("updated_at",), "idx_chat_thread_summaries_updated"),),
            foreign_keys=(
                ForeignKeyDef(("thread_id",), "chat_threads", ("thread_id",)),
            ),
        ),
        TableDef(
            name="outbox_events",
            columns=(
                ColumnDef("outbox_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("canonical_event_id", "VARCHAR(64)", nullable=False),
                ColumnDef("aggregate_type", "VARCHAR(32)", nullable=False),
                ColumnDef("aggregate_id", "VARCHAR(191)", nullable=False),
                ColumnDef("event_type", "VARCHAR(64)", nullable=False),
                ColumnDef("source_service", "VARCHAR(64)", nullable=False),
                ColumnDef("canonical_event_json", "LONGTEXT", nullable=False),
                ColumnDef("source_row_table", "VARCHAR(64)", nullable=False),
                ColumnDef("source_row_id", "BIGINT", nullable=True),
                ColumnDef("publish_status", "VARCHAR(32)", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("published_at", "DATETIME", nullable=True),
            ),
            primary_key=("outbox_id",),
            uniques=(
                UniqueKeyDef(("canonical_event_id",), name="uniq_chat_outbox_canonical_event_id"),
            ),
            indexes=(
                IndexDef(("publish_status", "created_at"), "idx_chat_outbox_pending_time"),
            ),
        ),
        TableDef(
            name="persona_sync_jobs",
            columns=(
                ColumnDef("job_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("thread_id", "VARCHAR(64)", nullable=False),
                ColumnDef("message_id", "BIGINT", nullable=False),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("update_key", "VARCHAR(191)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("patch_json", "LONGTEXT", nullable=True),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("sync_result_json", "LONGTEXT", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("processed_at", "DATETIME", nullable=True),
            ),
            primary_key=("job_id",),
            uniques=(
                UniqueKeyDef(("update_key",), name="uniq_persona_job_update_key"),
            ),
            indexes=(
                IndexDef(("status", "created_at"), "idx_persona_jobs_status_time"),
            ),
        ),
        ASYNC_JOB_TABLE,
        TableDef(
            name="verification_submissions",
            columns=(
                ColumnDef("submission_id", "VARCHAR(64)", nullable=False),
                ColumnDef("verification_type", "VARCHAR(32)", nullable=False),
                ColumnDef("user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("profile_id", "BIGINT", nullable=True),
                ColumnDef("source_dsn", "VARCHAR(512)", nullable=True),
                ColumnDef("source_table_name", "VARCHAR(191)", nullable=True),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("resubmission_count", "INT", nullable=False),
                ColumnDef("challenge_phrase", "VARCHAR(191)", nullable=True),
                ColumnDef("review_decision", "VARCHAR(32)", nullable=True),
                ColumnDef("review_note", "LONGTEXT", nullable=True),
                ColumnDef("reviewer_id", "VARCHAR(191)", nullable=True),
                ColumnDef("latest_asset_id", "BIGINT", nullable=True),
                ColumnDef("latest_sync_status", "VARCHAR(32)", nullable=True),
                ColumnDef("latest_sync_error", "LONGTEXT", nullable=True),
                ColumnDef("submitted_at", "DATETIME", nullable=False),
                ColumnDef("reviewed_at", "DATETIME", nullable=True),
                ColumnDef("approved_at", "DATETIME", nullable=True),
                ColumnDef("rejected_at", "DATETIME", nullable=True),
                ColumnDef("machine_review_outcome", "VARCHAR(32)", nullable=True),
                ColumnDef("machine_review_score", "INT", nullable=True),
                ColumnDef("expires_at", "DATETIME", nullable=True),
                ColumnDef("revoked_at", "DATETIME", nullable=True),
                ColumnDef("revocation_reason", "VARCHAR(191)", nullable=True),
                ColumnDef("metadata_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("submission_id",),
            indexes=(
                IndexDef(("user_id", "status", "updated_at"), "idx_verification_submissions_user_status"),
                IndexDef(("status", "updated_at"), "idx_verification_submissions_status_time"),
                IndexDef(("profile_id", "updated_at"), "idx_verification_submissions_profile_time"),
                IndexDef(("machine_review_outcome", "updated_at"), "idx_verification_submissions_machine_outcome"),
                IndexDef(("expires_at",), "idx_verification_submissions_expires_at"),
            ),
        ),
        TableDef(
            name="verification_assets",
            columns=(
                ColumnDef("asset_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("submission_id", "VARCHAR(64)", nullable=False),
                ColumnDef("asset_kind", "VARCHAR(32)", nullable=False),
                ColumnDef("storage_key", "VARCHAR(512)", nullable=False),
                ColumnDef("original_file_name", "VARCHAR(255)", nullable=False),
                ColumnDef("content_type", "VARCHAR(128)", nullable=False),
                ColumnDef("file_size_bytes", "BIGINT", nullable=False),
                ColumnDef("sha256_hex", "VARCHAR(64)", nullable=False),
                ColumnDef("upload_attempt", "INT", nullable=False),
                ColumnDef("metadata_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("asset_id",),
            indexes=(
                IndexDef(("submission_id", "created_at"), "idx_verification_assets_submission_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("submission_id",), "verification_submissions", ("submission_id",)),
            ),
        ),
        TableDef(
            name="verification_reviews",
            columns=(
                ColumnDef("review_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("submission_id", "VARCHAR(64)", nullable=False),
                ColumnDef("reviewer_id", "VARCHAR(191)", nullable=False),
                ColumnDef("decision", "VARCHAR(32)", nullable=False),
                ColumnDef("review_note", "LONGTEXT", nullable=True),
                ColumnDef("liveness_result", "VARCHAR(32)", nullable=True),
                ColumnDef("face_match_result", "VARCHAR(32)", nullable=True),
                ColumnDef("profile_consistency_result", "VARCHAR(32)", nullable=True),
                ColumnDef("metadata_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("review_id",),
            indexes=(
                IndexDef(("submission_id", "created_at"), "idx_verification_reviews_submission_time"),
                IndexDef(("reviewer_id", "created_at"), "idx_verification_reviews_reviewer_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("submission_id",), "verification_submissions", ("submission_id",)),
            ),
        ),
        TableDef(
            name="verification_notifications",
            columns=(
                ColumnDef("notification_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("submission_id", "VARCHAR(64)", nullable=False),
                ColumnDef("user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("notification_type", "VARCHAR(64)", nullable=False),
                ColumnDef("delivery_channel", "VARCHAR(32)", nullable=False),
                ColumnDef("delivery_status", "VARCHAR(32)", nullable=False),
                ColumnDef("title", "VARCHAR(255)", nullable=True),
                ColumnDef("body", "LONGTEXT", nullable=True),
                ColumnDef("metadata_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("sent_at", "DATETIME", nullable=True),
            ),
            primary_key=("notification_id",),
            indexes=(
                IndexDef(("submission_id", "created_at"), "idx_verification_notifications_submission_time"),
                IndexDef(("user_id", "created_at"), "idx_verification_notifications_user_time"),
                IndexDef(("delivery_status", "created_at"), "idx_verification_notifications_status_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("submission_id",), "verification_submissions", ("submission_id",)),
            ),
        ),
        # ===== 认证等级权重配置表 =====
        TableDef(
            name="verification_level_weights",
            columns=(
                ColumnDef("level_name", "VARCHAR(32)", nullable=False),
                ColumnDef("weight", "INT", nullable=False),
                ColumnDef("label", "VARCHAR(64)", nullable=False),
                ColumnDef("expires_after_days", "INT", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("level_name",),
        ),
        # ===== 认证提交元数据表（拆分metadata_json） =====
        TableDef(
            name="verification_submission_metadata",
            columns=(
                ColumnDef("submission_id", "VARCHAR(64)", nullable=False),
                ColumnDef("machine_review_json", "LONGTEXT", nullable=True),
                ColumnDef("workflow_history_json", "LONGTEXT", nullable=True),
                ColumnDef("photo_review_task_json", "LONGTEXT", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("submission_id",),
            foreign_keys=(
                ForeignKeyDef(("submission_id",), "verification_submissions", ("submission_id",)),
            ),
        ),
        # ===== 认证撤销记录表 =====
        TableDef(
            name="verification_revocations",
            columns=(
                ColumnDef("revocation_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("submission_id", "VARCHAR(64)", nullable=False),
                ColumnDef("user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("profile_id", "BIGINT", nullable=True),
                ColumnDef("revocation_reason", "VARCHAR(191)", nullable=False),
                ColumnDef("revoked_by", "VARCHAR(191)", nullable=False),
                ColumnDef("revoked_at", "DATETIME", nullable=False),
                ColumnDef("metadata_json", "LONGTEXT", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("revocation_id",),
            indexes=(
                IndexDef(("user_id", "revoked_at"), "idx_revocations_user_time"),
                IndexDef(("submission_id",), "idx_revocations_submission"),
            ),
            foreign_keys=(
                ForeignKeyDef(("submission_id",), "verification_submissions", ("submission_id",)),
            ),
        ),
        # ===== 自动审核质量统计表 =====
        TableDef(
            name="verification_auto_review_stats",
            columns=(
                ColumnDef("stat_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("stat_date", "DATE", nullable=False),
                ColumnDef("verification_type", "VARCHAR(32)", nullable=False),
                ColumnDef("total_auto_reviews", "INT", nullable=False),
                ColumnDef("auto_approved", "INT", nullable=False),
                ColumnDef("auto_resubmission", "INT", nullable=False),
                ColumnDef("manual_review", "INT", nullable=False),
                ColumnDef("manual_approved_after_auto", "INT", nullable=False),
                ColumnDef("manual_rejected_after_auto", "INT", nullable=False),
                ColumnDef("false_positive_rate", "DECIMAL(5,2)", nullable=True),
                ColumnDef("false_negative_recall_count", "INT", nullable=False),
                ColumnDef("post_approval_revocation_rate", "DECIMAL(5,2)", nullable=True),
                ColumnDef("avg_auto_review_latency_ms", "INT", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("stat_id",),
            uniques=(
                UniqueKeyDef(("stat_date", "verification_type"), "uk_date_type"),
            ),
            indexes=(
                IndexDef(("stat_date",), "idx_stats_date"),
            ),
        ),
        # ===== 审核延迟明细表 =====
        TableDef(
            name="verification_review_latency",
            columns=(
                ColumnDef("latency_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("submission_id", "VARCHAR(64)", nullable=False),
                ColumnDef("review_type", "VARCHAR(32)", nullable=False),
                ColumnDef("decision", "VARCHAR(32)", nullable=False),
                ColumnDef("latency_ms", "INT", nullable=False),
                ColumnDef("recorded_at", "DATETIME", nullable=False),
            ),
            primary_key=("latency_id",),
            indexes=(
                IndexDef(("recorded_at",), "idx_review_latency_time"),
                IndexDef(("submission_id",), "idx_review_latency_submission"),
            ),
        ),
        # ===== 认证敏感数据治理策略表 =====
        TableDef(
            name="verification_data_governance_policies",
            columns=(
                ColumnDef("policy_key", "VARCHAR(64)", nullable=False),
                ColumnDef("retention_days", "INT", nullable=False),
                ColumnDef("encryption_required", "TINYINT", nullable=False),
                ColumnDef("access_scope", "VARCHAR(64)", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("policy_key",),
        ),
        TableDef(
            name="user_accounts",
            columns=(
                ColumnDef("user_id", "VARCHAR(64)", nullable=False),
                ColumnDef("account_status", "VARCHAR(32)", nullable=False),
                ColumnDef("primary_phone", "VARCHAR(255)", nullable=True),
                ColumnDef("phone_verified_at", "DATETIME", nullable=True),
                ColumnDef("register_source", "VARCHAR(32)", nullable=False),
                ColumnDef("onboarding_status", "VARCHAR(32)", nullable=False),
                ColumnDef("first_login_at", "DATETIME", nullable=True),
                ColumnDef("last_login_at", "DATETIME", nullable=True),
                ColumnDef("last_login_ip", "VARCHAR(64)", nullable=True),
                ColumnDef("last_login_device_id", "VARCHAR(128)", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("user_id",),
            uniques=(
                UniqueKeyDef(("primary_phone",), name="uniq_user_accounts_primary_phone"),
            ),
            indexes=(
                IndexDef(("account_status", "created_at"), "idx_user_accounts_status_time"),
            ),
        ),
        TableDef(
            name="user_account_identities",
            columns=(
                ColumnDef("identity_id", "VARCHAR(64)", nullable=False),
                ColumnDef("user_id", "VARCHAR(64)", nullable=False),
                ColumnDef("identity_type", "VARCHAR(32)", nullable=False),
                ColumnDef("identity_value", "VARCHAR(255)", nullable=False),
                ColumnDef("is_primary", "TINYINT(1)", nullable=False),
                ColumnDef("verified_at", "DATETIME", nullable=True),
                ColumnDef("bound_at", "DATETIME", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("identity_id",),
            uniques=(
                UniqueKeyDef(("identity_type", "identity_value"), name="uniq_user_identity_type_value"),
            ),
            indexes=(
                IndexDef(("user_id", "identity_type"), "idx_user_identities_user_type"),
            ),
            foreign_keys=(
                ForeignKeyDef(("user_id",), "user_accounts", ("user_id",)),
            ),
        ),
        TableDef(
            name="auth_phone_role_bindings",
            columns=(
                ColumnDef("binding_id", "VARCHAR(64)", nullable=False),
                ColumnDef("phone_hash", "VARCHAR(64)", nullable=False),
                ColumnDef("role_key", "VARCHAR(64)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("note", "VARCHAR(255)", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("binding_id",),
            uniques=(
                UniqueKeyDef(("phone_hash", "role_key"), name="uniq_auth_phone_role_phone_role"),
            ),
            indexes=(
                IndexDef(("phone_hash", "status"), "idx_auth_phone_role_phone_status"),
                IndexDef(("role_key", "status"), "idx_auth_phone_role_role_status"),
            ),
        ),
        TableDef(
            name="auth_otp_challenges",
            columns=(
                ColumnDef("challenge_id", "VARCHAR(64)", nullable=False),
                ColumnDef("phone", "VARCHAR(255)", nullable=False),
                ColumnDef("scene", "VARCHAR(32)", nullable=False),
                ColumnDef("scenario", "VARCHAR(32)", nullable=False),
                ColumnDef("code_hash", "VARCHAR(64)", nullable=False),
                ColumnDef("code_salt", "VARCHAR(64)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("expires_at", "DATETIME", nullable=False),
                ColumnDef("resend_available_at", "DATETIME", nullable=False),
                ColumnDef("verify_attempt_count", "INT", nullable=False),
                ColumnDef("max_verify_attempts", "INT", nullable=False),
                ColumnDef("client_ip", "VARCHAR(64)", nullable=True),
                ColumnDef("device_id", "VARCHAR(128)", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("challenge_id",),
            indexes=(
                IndexDef(("phone", "scene", "created_at"), "idx_auth_otp_phone_scene_time"),
                IndexDef(("status", "expires_at"), "idx_auth_otp_status_expires"),
            ),
        ),
        TableDef(
            name="auth_sessions",
            columns=(
                ColumnDef("session_id", "VARCHAR(64)", nullable=False),
                ColumnDef("user_id", "VARCHAR(64)", nullable=False),
                ColumnDef("access_token_hash", "VARCHAR(64)", nullable=False),
                ColumnDef("refresh_token_hash", "VARCHAR(64)", nullable=False),
                ColumnDef("login_method", "VARCHAR(32)", nullable=False),
                ColumnDef("client_type", "VARCHAR(32)", nullable=True),
                ColumnDef("client_ip", "VARCHAR(64)", nullable=True),
                ColumnDef("device_id", "VARCHAR(128)", nullable=True),
                ColumnDef("access_expires_at", "DATETIME", nullable=False),
                ColumnDef("refresh_expires_at", "DATETIME", nullable=False),
                ColumnDef("last_seen_at", "DATETIME", nullable=True),
                ColumnDef("revoked_at", "DATETIME", nullable=True),
                ColumnDef("revoke_reason", "VARCHAR(64)", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("session_id",),
            uniques=(
                UniqueKeyDef(("access_token_hash",), name="uniq_auth_sessions_access_token"),
                UniqueKeyDef(("refresh_token_hash",), name="uniq_auth_sessions_refresh_token"),
            ),
            indexes=(
                IndexDef(("user_id", "created_at"), "idx_auth_sessions_user_time"),
                IndexDef(("revoked_at", "access_expires_at"), "idx_auth_sessions_revoked_access_exp"),
            ),
            foreign_keys=(
                ForeignKeyDef(("user_id",), "user_accounts", ("user_id",)),
            ),
        ),
        TableDef(
            name="auth_login_events",
            columns=(
                ColumnDef("event_id", "VARCHAR(64)", nullable=False),
                ColumnDef("user_id", "VARCHAR(64)", nullable=True),
                ColumnDef("phone", "VARCHAR(255)", nullable=True),
                ColumnDef("event_type", "VARCHAR(64)", nullable=False),
                ColumnDef("result", "VARCHAR(32)", nullable=False),
                ColumnDef("reason_code", "VARCHAR(64)", nullable=True),
                ColumnDef("client_ip", "VARCHAR(64)", nullable=True),
                ColumnDef("device_id", "VARCHAR(128)", nullable=True),
                ColumnDef("metadata_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("event_id",),
            indexes=(
                IndexDef(("user_id", "created_at"), "idx_auth_events_user_time"),
                IndexDef(("phone", "created_at"), "idx_auth_events_phone_time"),
                IndexDef(("event_type", "created_at"), "idx_auth_events_type_time"),
            ),
        ),
        TableDef(
            name="user_onboarding_profiles",
            columns=(
                ColumnDef("user_id", "VARCHAR(64)", nullable=False),
                ColumnDef("onboarding_status", "VARCHAR(32)", nullable=False),
                ColumnDef("current_step", "VARCHAR(64)", nullable=True),
                ColumnDef("basic_info_json", "LONGTEXT", nullable=False),
                ColumnDef("preference_json", "LONGTEXT", nullable=False),
                ColumnDef("completed_at", "DATETIME", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("user_id",),
            foreign_keys=(
                ForeignKeyDef(("user_id",), "user_accounts", ("user_id",)),
            ),
        ),
        TableDef(
            name="wechat_accounts",
            columns=(
                ColumnDef("wechat_account_id", "VARCHAR(64)", nullable=False),
                ColumnDef("user_id", "VARCHAR(64)", nullable=False),
                ColumnDef("openid", "VARCHAR(191)", nullable=False),
                ColumnDef("unionid", "VARCHAR(191)", nullable=True),
                ColumnDef("nickname", "VARCHAR(191)", nullable=True),
                ColumnDef("avatar_url", "VARCHAR(512)", nullable=True),
                ColumnDef("raw_profile_json", "LONGTEXT", nullable=False),
                ColumnDef("bound_at", "DATETIME", nullable=False),
                ColumnDef("last_login_at", "DATETIME", nullable=True),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("wechat_account_id",),
            uniques=(
                UniqueKeyDef(("openid",), name="uniq_wechat_accounts_openid"),
            ),
            indexes=(
                IndexDef(("user_id", "status"), "idx_wechat_accounts_user_status"),
                IndexDef(("unionid",), "idx_wechat_accounts_unionid"),
            ),
            foreign_keys=(
                ForeignKeyDef(("user_id",), "user_accounts", ("user_id",)),
            ),
        ),
        TableDef(
            name="auth_one_tap_attempts",
            columns=(
                ColumnDef("attempt_id", "VARCHAR(64)", nullable=False),
                ColumnDef("provider", "VARCHAR(64)", nullable=False),
                ColumnDef("masked_phone", "VARCHAR(32)", nullable=False),
                ColumnDef("operator_request_id", "VARCHAR(191)", nullable=True),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("provider_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("client_ip", "VARCHAR(64)", nullable=True),
                ColumnDef("device_id", "VARCHAR(128)", nullable=True),
                ColumnDef("client_type", "VARCHAR(32)", nullable=True),
                ColumnDef("verified_phone", "VARCHAR(255)", nullable=True),
                ColumnDef("expires_at", "DATETIME", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("attempt_id",),
            indexes=(
                IndexDef(("status", "expires_at"), "idx_auth_one_tap_status_expires"),
                IndexDef(("device_id", "created_at"), "idx_auth_one_tap_device_time"),
            ),
        ),
        TableDef(
            name="chat_member_reports",
            columns=(
                ColumnDef("report_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("thread_id", "VARCHAR(64)", nullable=False),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("message_id", "BIGINT", nullable=True),
                ColumnDef("reporter_id", "VARCHAR(191)", nullable=False),
                ColumnDef("reported_user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("report_source", "VARCHAR(32)", nullable=False),
                ColumnDef("report_type", "VARCHAR(64)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("severity", "VARCHAR(16)", nullable=False),
                ColumnDef("reason_text", "LONGTEXT", nullable=True),
                ColumnDef("signal_codes_json", "LONGTEXT", nullable=False),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("risk_case_id", "VARCHAR(64)", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("reviewed_at", "DATETIME", nullable=True),
            ),
            primary_key=("report_id",),
            uniques=(
                UniqueKeyDef(("message_id", "report_source"), name="uniq_chat_reports_message_source"),
            ),
            indexes=(
                IndexDef(("thread_id", "created_at"), "idx_chat_reports_thread_time"),
                IndexDef(("reported_user_id", "status", "created_at"), "idx_chat_reports_subject_status"),
                IndexDef(("risk_case_id",), "idx_chat_reports_risk_case"),
            ),
            foreign_keys=(
                ForeignKeyDef(("thread_id",), "chat_threads", ("thread_id",)),
                ForeignKeyDef(("message_id",), "chat_messages", ("message_id",)),
            ),
        ),
        TableDef(
            name="chat_risk_cases",
            columns=(
                ColumnDef("risk_case_id", "VARCHAR(64)", nullable=False),
                ColumnDef("thread_id", "VARCHAR(64)", nullable=False),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("severity", "VARCHAR(16)", nullable=False),
                ColumnDef("source_types_json", "LONGTEXT", nullable=False),
                ColumnDef("signal_codes_json", "LONGTEXT", nullable=False),
                ColumnDef("evidence_summary_json", "LONGTEXT", nullable=False),
                ColumnDef("report_count", "INT", nullable=False),
                ColumnDef("recommended_action", "VARCHAR(32)", nullable=False),
                ColumnDef("applied_action", "VARCHAR(32)", nullable=True),
                ColumnDef("resolver_id", "VARCHAR(191)", nullable=True),
                ColumnDef("resolution_note", "LONGTEXT", nullable=True),
                ColumnDef("last_reported_at", "DATETIME", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
                ColumnDef("resolved_at", "DATETIME", nullable=True),
            ),
            primary_key=("risk_case_id",),
            indexes=(
                IndexDef(("thread_id", "subject_user_id", "status"), "idx_chat_risk_cases_thread_subject"),
                IndexDef(("status", "severity", "updated_at"), "idx_chat_risk_cases_status_severity"),
                IndexDef(("subject_user_id", "status"), "idx_chat_risk_cases_subject_status"),
            ),
            foreign_keys=(
                ForeignKeyDef(("thread_id",), "chat_threads", ("thread_id",)),
            ),
        ),
        TableDef(
            name="chat_risk_signals",
            columns=(
                ColumnDef("signal_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("thread_id", "VARCHAR(64)", nullable=False),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("message_id", "BIGINT", nullable=True),
                ColumnDef("report_id", "BIGINT", nullable=True),
                ColumnDef("risk_case_id", "VARCHAR(64)", nullable=True),
                ColumnDef("source_type", "VARCHAR(32)", nullable=False),
                ColumnDef("signal_code", "VARCHAR(64)", nullable=False),
                ColumnDef("severity", "VARCHAR(16)", nullable=False),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("signal_id",),
            indexes=(
                IndexDef(("subject_user_id", "created_at"), "idx_chat_risk_signals_subject_time"),
                IndexDef(("thread_id", "created_at"), "idx_chat_risk_signals_thread_time"),
                IndexDef(("signal_code", "created_at"), "idx_chat_risk_signals_code_time"),
                IndexDef(("risk_case_id",), "idx_chat_risk_signals_risk_case"),
            ),
            foreign_keys=(
                ForeignKeyDef(("thread_id",), "chat_threads", ("thread_id",)),
                ForeignKeyDef(("message_id",), "chat_messages", ("message_id",)),
                ForeignKeyDef(("report_id",), "chat_member_reports", ("report_id",)),
            ),
        ),
        TableDef(
            name="chat_meeting_feedback",
            columns=(
                ColumnDef("feedback_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("thread_id", "VARCHAR(64)", nullable=False),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("reviewer_id", "VARCHAR(191)", nullable=False),
                ColumnDef("counterpart_user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("photo_match_status", "VARCHAR(32)", nullable=False),
                ColumnDef("profile_consistency_status", "VARCHAR(32)", nullable=False),
                ColumnDef("income_job_consistency_status", "VARCHAR(32)", nullable=False),
                ColumnDef("safety_concern_status", "VARCHAR(32)", nullable=False),
                ColumnDef("willing_video_status", "VARCHAR(32)", nullable=False),
                ColumnDef("willing_offline_status", "VARCHAR(32)", nullable=False),
                ColumnDef("notes", "LONGTEXT", nullable=True),
                ColumnDef("derived_report_ids_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("feedback_id",),
            indexes=(
                IndexDef(("thread_id", "created_at"), "idx_chat_meeting_feedback_thread_time"),
                IndexDef(("counterpart_user_id", "created_at"), "idx_chat_meeting_feedback_counterpart_time"),
                IndexDef(("reviewer_id", "created_at"), "idx_chat_meeting_feedback_reviewer_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("thread_id",), "chat_threads", ("thread_id",)),
            ),
        ),
        TableDef(
            name="account_moderation_states",
            columns=(
                ColumnDef("state_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("subject_key", "VARCHAR(191)", nullable=False),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=True),
                ColumnDef("source_dsn", "VARCHAR(512)", nullable=True),
                ColumnDef("source_table_name", "VARCHAR(191)", nullable=True),
                ColumnDef("profile_id", "BIGINT", nullable=True),
                ColumnDef("moderation_status", "VARCHAR(32)", nullable=False),
                ColumnDef("applied_action", "VARCHAR(32)", nullable=False),
                ColumnDef("reason_code", "VARCHAR(64)", nullable=True),
                ColumnDef("reason_summary", "LONGTEXT", nullable=True),
                ColumnDef("required_verifications_json", "LONGTEXT", nullable=False),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("linked_risk_case_id", "VARCHAR(64)", nullable=True),
                ColumnDef("linked_profile_review_case_id", "VARCHAR(64)", nullable=True),
                ColumnDef("resolver_id", "VARCHAR(191)", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
                ColumnDef("cleared_at", "DATETIME", nullable=True),
            ),
            primary_key=("state_id",),
            uniques=(
                UniqueKeyDef(("subject_key",), name="uniq_account_moderation_subject"),
            ),
            indexes=(
                IndexDef(("moderation_status", "applied_action", "updated_at"), "idx_account_moderation_status_action"),
                IndexDef(("subject_user_id", "moderation_status"), "idx_account_moderation_subject_status"),
                IndexDef(("source_table_name", "profile_id"), "idx_account_moderation_profile_ref"),
            ),
            foreign_keys=(
                ForeignKeyDef(("linked_risk_case_id",), "chat_risk_cases", ("risk_case_id",)),
            ),
        ),
        TableDef(
            name="chat_risk_appeals",
            columns=(
                ColumnDef("appeal_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("risk_case_id", "VARCHAR(64)", nullable=False),
                ColumnDef("subject_key", "VARCHAR(191)", nullable=True),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=True),
                ColumnDef("appellant_id", "VARCHAR(191)", nullable=False),
                ColumnDef("appeal_status", "VARCHAR(32)", nullable=False),
                ColumnDef("reason_text", "LONGTEXT", nullable=False),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("resolution_note", "LONGTEXT", nullable=True),
                ColumnDef("resolver_id", "VARCHAR(191)", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
                ColumnDef("resolved_at", "DATETIME", nullable=True),
            ),
            primary_key=("appeal_id",),
            indexes=(
                IndexDef(("risk_case_id", "created_at"), "idx_chat_risk_appeals_case_time"),
                IndexDef(("appeal_status", "updated_at"), "idx_chat_risk_appeals_status_time"),
                IndexDef(("subject_user_id", "created_at"), "idx_chat_risk_appeals_subject_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("risk_case_id",), "chat_risk_cases", ("risk_case_id",)),
            ),
        ),
        TableDef(
            name="chat_risk_entity_links",
            columns=(
                ColumnDef("entity_link_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("source_dsn", "VARCHAR(512)", nullable=True),
                ColumnDef("source_table_name", "VARCHAR(191)", nullable=True),
                ColumnDef("profile_id", "BIGINT", nullable=True),
                ColumnDef("thread_id", "VARCHAR(64)", nullable=True),
                ColumnDef("case_id", "VARCHAR(191)", nullable=True),
                ColumnDef("risk_case_id", "VARCHAR(64)", nullable=True),
                ColumnDef("report_id", "BIGINT", nullable=True),
                ColumnDef("source_type", "VARCHAR(32)", nullable=False),
                ColumnDef("event_type", "VARCHAR(64)", nullable=False),
                ColumnDef("entity_type", "VARCHAR(64)", nullable=False),
                ColumnDef("entity_hash", "VARCHAR(128)", nullable=False),
                ColumnDef("entity_key_hint", "VARCHAR(128)", nullable=True),
                ColumnDef("entity_weight", "INT", nullable=False),
                ColumnDef("signal_codes_json", "LONGTEXT", nullable=False),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("first_seen_at", "DATETIME", nullable=False),
                ColumnDef("last_seen_at", "DATETIME", nullable=False),
                ColumnDef("occurrence_count", "INT", nullable=False),
            ),
            primary_key=("entity_link_id",),
            uniques=(
                UniqueKeyDef(("subject_user_id", "entity_type", "entity_hash"), name="uniq_chat_risk_entity_link"),
            ),
            indexes=(
                IndexDef(("subject_user_id", "last_seen_at"), "idx_chat_risk_entity_links_subject_time"),
                IndexDef(("entity_type", "entity_hash"), "idx_chat_risk_entity_links_entity_hash"),
                IndexDef(("risk_case_id",), "idx_chat_risk_entity_links_risk_case"),
                IndexDef(("report_id",), "idx_chat_risk_entity_links_report"),
            ),
            foreign_keys=(
                ForeignKeyDef(("thread_id",), "chat_threads", ("thread_id",)),
                ForeignKeyDef(("risk_case_id",), "chat_risk_cases", ("risk_case_id",)),
                ForeignKeyDef(("report_id",), "chat_member_reports", ("report_id",)),
            ),
        ),
        TableDef(
            name="chat_risk_account_links",
            columns=(
                ColumnDef("account_link_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("linked_user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("shared_entity_types_json", "LONGTEXT", nullable=False),
                ColumnDef("shared_signal_codes_json", "LONGTEXT", nullable=False),
                ColumnDef("shared_entity_count", "INT", nullable=False),
                ColumnDef("link_score", "INT", nullable=False),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("first_seen_at", "DATETIME", nullable=False),
                ColumnDef("last_seen_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("account_link_id",),
            uniques=(
                UniqueKeyDef(("subject_user_id", "linked_user_id"), name="uniq_chat_risk_account_link"),
            ),
            indexes=(
                IndexDef(("subject_user_id", "link_score"), "idx_chat_risk_account_links_subject_score"),
                IndexDef(("linked_user_id", "link_score"), "idx_chat_risk_account_links_linked_score"),
            ),
        ),
        TableDef(
            name="chat_risk_network_profiles",
            columns=(
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=False),
                ColumnDef("source_dsn", "VARCHAR(512)", nullable=True),
                ColumnDef("source_table_name", "VARCHAR(191)", nullable=True),
                ColumnDef("profile_id", "BIGINT", nullable=True),
                ColumnDef("review_status", "VARCHAR(32)", nullable=False),
                ColumnDef("graph_risk_score", "INT", nullable=False),
                ColumnDef("risk_level", "VARCHAR(16)", nullable=False),
                ColumnDef("connected_subject_count", "INT", nullable=False),
                ColumnDef("high_risk_neighbor_count", "INT", nullable=False),
                ColumnDef("shared_entity_type_counts_json", "LONGTEXT", nullable=False),
                ColumnDef("signal_codes_json", "LONGTEXT", nullable=False),
                ColumnDef("recommended_action", "VARCHAR(32)", nullable=True),
                ColumnDef("applied_action", "VARCHAR(32)", nullable=True),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("last_evaluated_at", "DATETIME", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("subject_user_id",),
            indexes=(
                IndexDef(("review_status", "graph_risk_score"), "idx_chat_risk_network_profiles_status_score"),
                IndexDef(("source_table_name", "profile_id"), "idx_chat_risk_network_profiles_profile_ref"),
                IndexDef(("applied_action", "updated_at"), "idx_chat_risk_network_profiles_action_time"),
            ),
        ),
        TableDef(
            name="profile_field_verification_submissions",
            columns=(
                ColumnDef("submission_id", "VARCHAR(64)", nullable=False),
                ColumnDef("field_key", "VARCHAR(32)", nullable=False),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=True),
                ColumnDef("profile_id", "BIGINT", nullable=False),
                ColumnDef("source_dsn", "VARCHAR(512)", nullable=False),
                ColumnDef("source_table_name", "VARCHAR(191)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("declared_value", "VARCHAR(255)", nullable=True),
                ColumnDef("approved_value", "VARCHAR(255)", nullable=True),
                ColumnDef("resubmission_count", "INT", nullable=False),
                ColumnDef("required_documents_json", "LONGTEXT", nullable=False),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("evidence_type", "VARCHAR(64)", nullable=True),
                ColumnDef("evidence_channel", "VARCHAR(64)", nullable=True),
                ColumnDef("reverify_strategy", "VARCHAR(32)", nullable=True),
                ColumnDef("verification_expires_at", "DATETIME", nullable=True),
                ColumnDef("next_review_due_at", "DATETIME", nullable=True),
                ColumnDef("dispute_status", "VARCHAR(32)", nullable=True),
                ColumnDef("dispute_reason", "LONGTEXT", nullable=True),
                ColumnDef("dispute_evidence_json", "LONGTEXT", nullable=True),
                ColumnDef("disputed_at", "DATETIME", nullable=True),
                ColumnDef("dispute_resolved_at", "DATETIME", nullable=True),
                ColumnDef("review_decision", "VARCHAR(32)", nullable=True),
                ColumnDef("review_note", "LONGTEXT", nullable=True),
                ColumnDef("reviewer_id", "VARCHAR(191)", nullable=True),
                ColumnDef("latest_sync_status", "VARCHAR(32)", nullable=True),
                ColumnDef("latest_sync_error", "LONGTEXT", nullable=True),
                ColumnDef("submitted_at", "DATETIME", nullable=False),
                ColumnDef("reviewed_at", "DATETIME", nullable=True),
                ColumnDef("approved_at", "DATETIME", nullable=True),
                ColumnDef("rejected_at", "DATETIME", nullable=True),
                ColumnDef("ocr_extracted_text", "LONGTEXT", nullable=True),
                ColumnDef("ocr_confidence_score", "INT", nullable=True),
                ColumnDef("ocr_processed_at", "DATETIME", nullable=True),
                ColumnDef("authority_verification_status", "VARCHAR(32)", nullable=True),
                ColumnDef("authority_verification_result", "LONGTEXT", nullable=True),
                ColumnDef("revoked_at", "DATETIME", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("submission_id",),
            indexes=(
                IndexDef(("field_key", "status", "updated_at"), "idx_profile_field_verif_field_status"),
                IndexDef(("profile_id", "updated_at"), "idx_profile_field_verif_profile_time"),
                IndexDef(("subject_user_id", "status", "updated_at"), "idx_profile_field_verif_subject_status"),
            ),
        ),
        TableDef(
            name="profile_field_verification_reviews",
            columns=(
                ColumnDef("review_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("submission_id", "VARCHAR(64)", nullable=False),
                ColumnDef("reviewer_id", "VARCHAR(191)", nullable=False),
                ColumnDef("decision", "VARCHAR(32)", nullable=False),
                ColumnDef("review_note", "LONGTEXT", nullable=True),
                ColumnDef("approved_value", "VARCHAR(255)", nullable=True),
                ColumnDef("requested_documents_json", "LONGTEXT", nullable=False),
                ColumnDef("metadata_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("review_id",),
            indexes=(
                IndexDef(("submission_id", "created_at"), "idx_profile_field_verif_reviews_submission_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("submission_id",), "profile_field_verification_submissions", ("submission_id",)),
            ),
        ),
        TableDef(
            name="profile_review_cases",
            columns=(
                ColumnDef("profile_review_case_id", "VARCHAR(64)", nullable=False),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=True),
                ColumnDef("profile_id", "BIGINT", nullable=False),
                ColumnDef("source_dsn", "VARCHAR(512)", nullable=False),
                ColumnDef("source_table_name", "VARCHAR(191)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("severity", "VARCHAR(16)", nullable=False),
                ColumnDef("rule_codes_json", "LONGTEXT", nullable=False),
                ColumnDef("evidence_summary_json", "LONGTEXT", nullable=False),
                ColumnDef("recommended_action", "VARCHAR(32)", nullable=False),
                ColumnDef("applied_action", "VARCHAR(32)", nullable=True),
                ColumnDef("resolver_id", "VARCHAR(191)", nullable=True),
                ColumnDef("resolution_note", "LONGTEXT", nullable=True),
                ColumnDef("last_evaluated_at", "DATETIME", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
                ColumnDef("resolved_at", "DATETIME", nullable=True),
            ),
            primary_key=("profile_review_case_id",),
            indexes=(
                IndexDef(("profile_id", "source_table_name", "status"), "idx_profile_review_cases_profile_status"),
                IndexDef(("status", "severity", "updated_at"), "idx_profile_review_cases_status_severity"),
                IndexDef(("subject_user_id", "status"), "idx_profile_review_cases_subject_status"),
            ),
        ),
        TableDef(
            name="profile_review_events",
            columns=(
                ColumnDef("event_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("profile_review_case_id", "VARCHAR(64)", nullable=False),
                ColumnDef("rule_code", "VARCHAR(64)", nullable=False),
                ColumnDef("severity", "VARCHAR(16)", nullable=False),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("event_id",),
            indexes=(
                IndexDef(("profile_review_case_id", "created_at"), "idx_profile_review_events_case_time"),
                IndexDef(("rule_code", "created_at"), "idx_profile_review_events_rule_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("profile_review_case_id",), "profile_review_cases", ("profile_review_case_id",)),
            ),
        ),
        TableDef(
            name="profile_review_case_appeals",
            columns=(
                ColumnDef("appeal_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("profile_review_case_id", "VARCHAR(64)", nullable=False),
                ColumnDef("subject_key", "VARCHAR(191)", nullable=True),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=True),
                ColumnDef("appellant_id", "VARCHAR(191)", nullable=False),
                ColumnDef("appeal_status", "VARCHAR(32)", nullable=False),
                ColumnDef("reason_text", "LONGTEXT", nullable=False),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("resolution_note", "LONGTEXT", nullable=True),
                ColumnDef("resolver_id", "VARCHAR(191)", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
                ColumnDef("resolved_at", "DATETIME", nullable=True),
            ),
            primary_key=("appeal_id",),
            indexes=(
                IndexDef(("profile_review_case_id", "created_at"), "idx_profile_review_appeals_case_time"),
                IndexDef(("appeal_status", "updated_at"), "idx_profile_review_appeals_status_time"),
                IndexDef(("subject_user_id", "created_at"), "idx_profile_review_appeals_subject_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("profile_review_case_id",), "profile_review_cases", ("profile_review_case_id",)),
            ),
        ),
        TableDef(
            name="photo_risk_assets",
            columns=(
                ColumnDef("asset_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("source_dsn", "VARCHAR(512)", nullable=False),
                ColumnDef("source_table_name", "VARCHAR(191)", nullable=False),
                ColumnDef("source_profile_id", "BIGINT", nullable=True),
                ColumnDef("asset_origin", "VARCHAR(32)", nullable=False),
                ColumnDef("photo_source", "VARCHAR(1024)", nullable=False),
                ColumnDef("photo_source_sha1", "CHAR(40)", nullable=False),
                ColumnDef("first_seen_at", "DATETIME", nullable=False),
                ColumnDef("last_seen_at", "DATETIME", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("asset_id",),
            uniques=(
                UniqueKeyDef(
                    ("source_dsn", "source_table_name", "source_profile_id", "photo_source_sha1"),
                    name="uniq_photo_risk_asset_src",
                ),
            ),
            indexes=(
                IndexDef(("source_profile_id", "updated_at"), "idx_photo_risk_asset_profile"),
                IndexDef(("photo_source_sha1",), "idx_photo_risk_asset_sha1"),
            ),
        ),
        TableDef(
            name="photo_risk_score_runs",
            columns=(
                ColumnDef("score_run_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("profile_id", "BIGINT", nullable=False),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=True),
                ColumnDef("source_dsn", "VARCHAR(512)", nullable=False),
                ColumnDef("source_table_name", "VARCHAR(191)", nullable=False),
                ColumnDef("profile_review_case_id", "VARCHAR(64)", nullable=True),
                ColumnDef("trigger_source", "VARCHAR(64)", nullable=False),
                ColumnDef("engine_name", "VARCHAR(64)", nullable=False),
                ColumnDef("engine_version", "VARCHAR(64)", nullable=False),
                ColumnDef("analysis_status", "VARCHAR(32)", nullable=False),
                ColumnDef("photo_authenticity_score", "INT", nullable=False),
                ColumnDef("same_person_score", "INT", nullable=False),
                ColumnDef("photo_edit_risk_score", "INT", nullable=False),
                ColumnDef("deepfake_risk_score", "INT", nullable=False),
                ColumnDef("stolen_media_risk_score", "INT", nullable=False),
                ColumnDef("source_count", "INT", nullable=False),
                ColumnDef("loaded_source_count", "INT", nullable=False),
                ColumnDef("valid_face_photo_count", "INT", nullable=False),
                ColumnDef("multiple_face_photo_count", "INT", nullable=False),
                ColumnDef("comparison_source_count", "INT", nullable=False),
                ColumnDef("risk_flags_json", "LONGTEXT", nullable=False),
                ColumnDef("score_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("score_run_id",),
            indexes=(
                IndexDef(("profile_id", "created_at"), "idx_photo_risk_run_profile"),
                IndexDef(("subject_user_id", "created_at"), "idx_photo_risk_run_subject"),
                IndexDef(("profile_review_case_id", "created_at"), "idx_photo_risk_run_case"),
            ),
        ),
        TableDef(
            name="photo_risk_feature_snapshots",
            columns=(
                ColumnDef("feature_snapshot_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("asset_id", "BIGINT", nullable=False),
                ColumnDef("score_run_id", "BIGINT", nullable=False),
                ColumnDef("asset_role", "VARCHAR(32)", nullable=False),
                ColumnDef("feature_version", "VARCHAR(64)", nullable=False),
                ColumnDef("face_count", "INT", nullable=False),
                ColumnDef("face_detection_score", "INT", nullable=False),
                ColumnDef("image_hash_hex", "VARCHAR(32)", nullable=True),
                ColumnDef("embedding_available", "TINYINT(1)", nullable=False),
                ColumnDef("embedding_dim", "INT", nullable=False),
                ColumnDef("embedding_preview_json", "LONGTEXT", nullable=False),
                ColumnDef("photo_edit_metrics_json", "LONGTEXT", nullable=True),
                ColumnDef("deepfake_metrics_json", "LONGTEXT", nullable=True),
                ColumnDef("metadata_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("feature_snapshot_id",),
            indexes=(
                IndexDef(("asset_id", "created_at"), "idx_photo_risk_feat_asset"),
                IndexDef(("score_run_id", "asset_role"), "idx_photo_risk_feat_run"),
            ),
            foreign_keys=(
                ForeignKeyDef(("asset_id",), "photo_risk_assets", ("asset_id",)),
                ForeignKeyDef(("score_run_id",), "photo_risk_score_runs", ("score_run_id",)),
            ),
        ),
        TableDef(
            name="photo_risk_decisions",
            columns=(
                ColumnDef("decision_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("score_run_id", "BIGINT", nullable=False),
                ColumnDef("profile_review_case_id", "VARCHAR(64)", nullable=True),
                ColumnDef("decision_source", "VARCHAR(64)", nullable=False),
                ColumnDef("decision_status", "VARCHAR(32)", nullable=False),
                ColumnDef("severity", "VARCHAR(16)", nullable=False),
                ColumnDef("recommended_action", "VARCHAR(32)", nullable=False),
                ColumnDef("required_verifications_json", "LONGTEXT", nullable=False),
                ColumnDef("rule_codes_json", "LONGTEXT", nullable=False),
                ColumnDef("signal_codes_json", "LONGTEXT", nullable=False),
                ColumnDef("decision_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("decision_id",),
            uniques=(UniqueKeyDef(("score_run_id",), name="uniq_photo_risk_decision_run"),),
            indexes=(
                IndexDef(("profile_review_case_id", "updated_at"), "idx_photo_risk_dec_case"),
                IndexDef(("decision_status", "updated_at"), "idx_photo_risk_dec_status"),
            ),
            foreign_keys=(
                ForeignKeyDef(("score_run_id",), "photo_risk_score_runs", ("score_run_id",)),
            ),
        ),
        TableDef(
            name="photo_risk_review_queue",
            columns=(
                ColumnDef("queue_item_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("profile_id", "BIGINT", nullable=False),
                ColumnDef("subject_user_id", "VARCHAR(191)", nullable=True),
                ColumnDef("source_dsn", "VARCHAR(512)", nullable=False),
                ColumnDef("source_table_name", "VARCHAR(191)", nullable=False),
                ColumnDef("profile_review_case_id", "VARCHAR(64)", nullable=False),
                ColumnDef("score_run_id", "BIGINT", nullable=False),
                ColumnDef("decision_id", "BIGINT", nullable=False),
                ColumnDef("queue_status", "VARCHAR(32)", nullable=False),
                ColumnDef("priority", "VARCHAR(16)", nullable=False),
                ColumnDef("reason_codes_json", "LONGTEXT", nullable=False),
                ColumnDef("queue_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
                ColumnDef("resolved_at", "DATETIME", nullable=True),
            ),
            primary_key=("queue_item_id",),
            uniques=(UniqueKeyDef(("profile_review_case_id",), name="uniq_photo_risk_queue_case"),),
            indexes=(
                IndexDef(("queue_status", "priority", "updated_at"), "idx_photo_risk_queue_status"),
                IndexDef(("subject_user_id", "updated_at"), "idx_photo_risk_queue_subject"),
                IndexDef(("profile_id", "updated_at"), "idx_photo_risk_queue_profile"),
            ),
            foreign_keys=(
                ForeignKeyDef(("score_run_id",), "photo_risk_score_runs", ("score_run_id",)),
                ForeignKeyDef(("decision_id",), "photo_risk_decisions", ("decision_id",)),
                ForeignKeyDef(("profile_review_case_id",), "profile_review_cases", ("profile_review_case_id",)),
            ),
        ),
        TableDef(
            name="call_sessions",
            columns=(
                ColumnDef("call_id", "VARCHAR(64)", nullable=False),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("conversation_id", "VARCHAR(64)", nullable=True),
                ColumnDef("caller_id", "VARCHAR(191)", nullable=False),
                ColumnDef("callee_id", "VARCHAR(191)", nullable=False),
                ColumnDef("call_type", "VARCHAR(32)", nullable=False),
                ColumnDef("room_id", "VARCHAR(64)", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("started_at", "DATETIME"),
                ColumnDef("ended_at", "DATETIME"),
                ColumnDef("duration_seconds", "INT"),
                ColumnDef("end_reason", "VARCHAR(64)"),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("call_id",),
            indexes=(
                IndexDef(("case_id", "created_at"), "idx_call_sessions_case_time"),
                IndexDef(("caller_id", "status", "created_at"), "idx_call_sessions_caller_status"),
                IndexDef(("callee_id", "status", "created_at"), "idx_call_sessions_callee_status"),
            ),
        ),
    )


def discovery_tables() -> tuple[TableDef, ...]:
    return (
        TableDef(
            name="discovery_agent_sessions",
            columns=(
                ColumnDef("session_id", "VARCHAR(191)", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                ColumnDef("profile_id", "BIGINT", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("phase", "VARCHAR(64)", nullable=False),
                ColumnDef("state_json", "LONGTEXT", nullable=False),
                ColumnDef("latest_view_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("session_id",),
            indexes=(
                IndexDef(("requester_id", "updated_at"), "idx_discovery_sessions_requester_updated"),
                IndexDef(("status", "updated_at"), "idx_discovery_sessions_status_updated"),
            ),
        ),
        TableDef(
            name="discovery_agent_turns",
            columns=(
                ColumnDef("turn_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("session_id", "VARCHAR(191)", nullable=False),
                ColumnDef("request_kind", "VARCHAR(32)", nullable=False),
                ColumnDef("user_message_text", "TEXT"),
                ColumnDef("consumed_action_id", "VARCHAR(191)"),
                ColumnDef("agent_decision_json", "LONGTEXT", nullable=False),
                ColumnDef("view_snapshot_json", "LONGTEXT", nullable=False),
                ColumnDef("search_run_id", "BIGINT"),
                ColumnDef("trace_id", "VARCHAR(191)"),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("turn_id",),
            indexes=(
                IndexDef(("session_id", "created_at"), "idx_discovery_turns_session_time"),
                IndexDef(("consumed_action_id",), "idx_discovery_turns_action_id"),
                IndexDef(("trace_id",), "idx_discovery_turns_trace_id"),
            ),
            foreign_keys=(
                ForeignKeyDef(("session_id",), "discovery_agent_sessions", ("session_id",)),
            ),
        ),
        TableDef(
            name="discovery_agent_actions",
            columns=(
                ColumnDef("action_id", "VARCHAR(191)", nullable=False),
                ColumnDef("session_id", "VARCHAR(191)", nullable=False),
                ColumnDef("label", "VARCHAR(255)", nullable=False),
                ColumnDef("style", "VARCHAR(32)", nullable=False),
                ColumnDef("semantic_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("expires_at", "DATETIME"),
                ColumnDef("consumed_at", "DATETIME"),
            ),
            primary_key=("action_id",),
            indexes=(
                IndexDef(("session_id", "created_at"), "idx_discovery_actions_session_time"),
                IndexDef(("session_id", "consumed_at"), "idx_discovery_actions_session_consumed"),
            ),
            foreign_keys=(
                ForeignKeyDef(("session_id",), "discovery_agent_sessions", ("session_id",)),
            ),
        ),
        TableDef(
            name="discovery_search_runs",
            columns=(
                ColumnDef("search_run_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("session_id", "VARCHAR(191)", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                ColumnDef("profile_id", "BIGINT", nullable=False),
                ColumnDef("source", "VARCHAR(512)", nullable=False),
                ColumnDef("criteria_json", "LONGTEXT", nullable=False),
                ColumnDef("self_profile_json", "LONGTEXT"),
                ColumnDef("limit_count", "INT", nullable=False),
                ColumnDef("result_count", "INT", nullable=False),
                ColumnDef("has_match", "TINYINT(1)", nullable=False),
                ColumnDef("response_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("search_run_id",),
            indexes=(
                IndexDef(("session_id", "created_at"), "idx_discovery_search_runs_session_time"),
                IndexDef(("requester_id", "created_at"), "idx_discovery_search_runs_requester_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("session_id",), "discovery_agent_sessions", ("session_id",)),
            ),
        ),
        TableDef(
            name="discovery_agent_tool_calls",
            columns=(
                ColumnDef("tool_call_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("session_id", "VARCHAR(191)", nullable=False),
                ColumnDef("turn_id", "BIGINT", nullable=False),
                ColumnDef("tool_name", "VARCHAR(191)", nullable=False),
                ColumnDef("tool_args_json", "LONGTEXT", nullable=False),
                ColumnDef("tool_result_json", "LONGTEXT", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("search_run_id", "BIGINT"),
                ColumnDef("trace_id", "VARCHAR(191)"),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("tool_call_id",),
            indexes=(
                IndexDef(("session_id", "created_at"), "idx_discovery_tool_calls_session_time"),
                IndexDef(("turn_id",), "idx_discovery_tool_calls_turn_id"),
                IndexDef(("tool_name", "created_at"), "idx_discovery_tool_calls_name_time"),
                IndexDef(("trace_id",), "idx_discovery_tool_calls_trace_id"),
            ),
            foreign_keys=(
                ForeignKeyDef(("session_id",), "discovery_agent_sessions", ("session_id",)),
                ForeignKeyDef(("turn_id",), "discovery_agent_turns", ("turn_id",)),
                ForeignKeyDef(("search_run_id",), "discovery_search_runs", ("search_run_id",)),
            ),
        ),
        TableDef(
            name="discovery_view_snapshots",
            columns=(
                ColumnDef("snapshot_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("session_id", "VARCHAR(191)", nullable=False),
                ColumnDef("turn_id", "BIGINT"),
                ColumnDef("phase", "VARCHAR(64)", nullable=False),
                ColumnDef("view_json", "LONGTEXT", nullable=False),
                ColumnDef("trace_id", "VARCHAR(191)"),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("snapshot_id",),
            indexes=(
                IndexDef(("session_id", "created_at"), "idx_discovery_view_snapshots_session_time"),
                IndexDef(("turn_id",), "idx_discovery_view_snapshots_turn_id"),
                IndexDef(("trace_id",), "idx_discovery_view_snapshots_trace_id"),
            ),
            foreign_keys=(
                ForeignKeyDef(("session_id",), "discovery_agent_sessions", ("session_id",)),
                ForeignKeyDef(("turn_id",), "discovery_agent_turns", ("turn_id",)),
            ),
        ),
        TableDef(
            name="discovery_agent_session_memory_items",
            columns=(
                ColumnDef("item_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("session_id", "VARCHAR(191)", nullable=False),
                ColumnDef("item_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("item_id",),
            indexes=(
                IndexDef(("session_id", "item_id"), "idx_discovery_agent_memory_session_item"),
            ),
            foreign_keys=(
                ForeignKeyDef(("session_id",), "discovery_agent_sessions", ("session_id",)),
            ),
        ),
        TableDef(
            name="discovery_profile_update_requests",
            columns=(
                ColumnDef("request_id", "VARCHAR(64)", nullable=False),
                ColumnDef("session_id", "VARCHAR(191)", nullable=False),
                ColumnDef("profile_id", "BIGINT", nullable=False),
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("proposed_patch_json", "LONGTEXT", nullable=False),
                ColumnDef("current_snapshot_json", "LONGTEXT"),
                ColumnDef("evidence_text", "TEXT"),
                ColumnDef("expires_at", "DATETIME"),
                ColumnDef("confirmed_at", "DATETIME"),
                ColumnDef("rejected_at", "DATETIME"),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("request_id",),
            indexes=(
                IndexDef(("session_id", "status"), "idx_discovery_profile_updates_session_status"),
                IndexDef(("profile_id", "status"), "idx_discovery_profile_updates_profile_status"),
            ),
            foreign_keys=(
                ForeignKeyDef(("session_id",), "discovery_agent_sessions", ("session_id",)),
            ),
        ),
        # 新增：拒绝反馈表
        TableDef(
            name="discovery_rejection_feedbacks",
            columns=(
                ColumnDef("feedback_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("session_id", "VARCHAR(64)", nullable=False),
                ColumnDef("turn_id", "BIGINT", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                # 反馈内容
                ColumnDef("feedback_type", "VARCHAR(32)", nullable=False),
                ColumnDef("feedback_text", "VARCHAR(255)", nullable=False),
                ColumnDef("feedback_detail", "TEXT"),
                # 拒绝对象
                ColumnDef("rejected_batch_id", "VARCHAR(64)"),
                ColumnDef("rejected_candidate_ids", "JSON"),
                # 反馈来源
                ColumnDef("source_type", "VARCHAR(16)", nullable=False),
                ColumnDef("追问_triggered", "TINYINT(1)", nullable=False),
                ColumnDef("追问_skipped", "TINYINT(1)", nullable=False),
                # 二级追问
                ColumnDef("is_secondary_feedback", "TINYINT(1)", nullable=False),
                ColumnDef("primary_feedback_id", "BIGINT"),
                # 时间戳
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("feedback_id",),
            indexes=(
                IndexDef(("session_id", "turn_id"), "idx_rejection_feedbacks_session_turn"),
                IndexDef(("requester_id", "created_at"), "idx_rejection_feedbacks_requester_time"),
                IndexDef(("feedback_type",), "idx_rejection_feedbacks_type"),
                IndexDef(("primary_feedback_id",), "idx_rejection_feedbacks_primary"),
            ),
            foreign_keys=(
                ForeignKeyDef(("session_id",), "discovery_agent_sessions", ("session_id",)),
                ForeignKeyDef(("turn_id",), "discovery_agent_turns", ("turn_id",)),
            ),
        ),
        # 新增：working_criteria调整记录表
        TableDef(
            name="discovery_working_criteria_adjustments",
            columns=(
                ColumnDef("adjustment_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("session_id", "VARCHAR(64)", nullable=False),
                ColumnDef("turn_id", "BIGINT", nullable=False),
                # 调整内容
                ColumnDef("adjustment_type", "VARCHAR(32)", nullable=False),
                ColumnDef("affected_field", "VARCHAR(64)", nullable=False),
                ColumnDef("before_value", "JSON"),
                ColumnDef("after_value", "JSON"),
                # 调整依据
                ColumnDef("triggered_by_feedback_id", "BIGINT"),
                ColumnDef("adjustment_reason", "TEXT"),
                # 时间戳
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("adjustment_id",),
            indexes=(
                IndexDef(("session_id",), "idx_working_criteria_adjustments_session"),
                IndexDef(("triggered_by_feedback_id",), "idx_working_criteria_adjustments_feedback"),
            ),
            foreign_keys=(
                ForeignKeyDef(("session_id",), "discovery_agent_sessions", ("session_id",)),
                ForeignKeyDef(("turn_id",), "discovery_agent_turns", ("turn_id",)),
                ForeignKeyDef(("triggered_by_feedback_id",), "discovery_rejection_feedbacks", ("feedback_id",)),
            ),
        ),
    )


def matchmaking_tables() -> tuple[TableDef, ...]:
    return (
        TableDef(
            name="matchmaking_pool_members",
            columns=(
                ColumnDef("member_id", "VARCHAR(191)", nullable=False),
                ColumnDef("user_key", "VARCHAR(191)", nullable=False),
                ColumnDef("source", "VARCHAR(512)", nullable=False),
                ColumnDef("table_name", "VARCHAR(191)"),
                ColumnDef("photos_table_name", "VARCHAR(191)"),
                ColumnDef("self_id", "BIGINT"),
                ColumnDef("self_profile_json", "LONGTEXT", nullable=False),
                ColumnDef("search_criteria_json", "LONGTEXT", nullable=False),
                ColumnDef("status", "VARCHAR(64)", nullable=False),
                ColumnDef("is_still_searching", "TINYINT(1)", nullable=False),
                ColumnDef("allowed_channels_json", "LONGTEXT", nullable=False),
                ColumnDef("min_pair_score", "INT", nullable=False),
                ColumnDef("daily_case_cap", "INT", nullable=False),
                ColumnDef("refresh_interval_hours", "INT", nullable=False),
                ColumnDef("limit_count", "INT", nullable=False),
                ColumnDef("last_scanned_at", "DATETIME"),
                ColumnDef("last_state_reason", "VARCHAR(191)"),
                ColumnDef("needs_refresh", "TINYINT(1)", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("member_id",),
            uniques=(
                UniqueKeyDef(("source", "user_key")),
            ),
            indexes=(
                IndexDef(("status", "is_still_searching", "last_scanned_at"), "idx_pool_members_status_scan"),
            ),
        ),
        TableDef(
            name="matchmaking_edges",
            columns=(
                ColumnDef("edge_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("owner_member_id", "VARCHAR(191)", nullable=False),
                ColumnDef("candidate_member_id", "VARCHAR(191)", nullable=False),
                ColumnDef("score", "INT", nullable=False),
                ColumnDef("fit_score", "INT", nullable=False),
                ColumnDef("confidence_score", "INT", nullable=False),
                ColumnDef("risk_score", "INT", nullable=False),
                ColumnDef("edge_status", "VARCHAR(64)", nullable=False),
                ColumnDef("edge_reason", "VARCHAR(191)"),
                ColumnDef("snapshot_hash", "VARCHAR(64)"),
                ColumnDef("payload_json", "LONGTEXT", nullable=False),
                ColumnDef("discovered_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("edge_id",),
            uniques=(
                UniqueKeyDef(("owner_member_id", "candidate_member_id")),
            ),
            indexes=(
                IndexDef(("owner_member_id", "edge_status", "score"), "idx_edges_owner_status"),
            ),
            foreign_keys=(
                ForeignKeyDef(("owner_member_id",), "matchmaking_pool_members", ("member_id",)),
                ForeignKeyDef(("candidate_member_id",), "matchmaking_pool_members", ("member_id",)),
            ),
        ),
        TableDef(
            name="matchmaking_pairs",
            columns=(
                ColumnDef("pair_key", "VARCHAR(191)", nullable=False),
                ColumnDef("member_low_id", "VARCHAR(191)", nullable=False),
                ColumnDef("member_high_id", "VARCHAR(191)", nullable=False),
                ColumnDef("score_low_to_high", "INT", nullable=False),
                ColumnDef("score_high_to_low", "INT", nullable=False),
                ColumnDef("pair_score", "INT", nullable=False),
                ColumnDef("pair_status", "VARCHAR(64)", nullable=False),
                ColumnDef("block_reason", "VARCHAR(191)"),
                ColumnDef("cooling_until", "DATETIME"),
                ColumnDef("latest_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("pair_key",),
            indexes=(
                IndexDef(("pair_status", "pair_score"), "idx_pairs_status_score"),
            ),
            foreign_keys=(
                ForeignKeyDef(("member_low_id",), "matchmaking_pool_members", ("member_id",)),
                ForeignKeyDef(("member_high_id",), "matchmaking_pool_members", ("member_id",)),
            ),
        ),
        TableDef(
            name="match_cases",
            columns=(
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("pair_key", "VARCHAR(191)", nullable=False),
                ColumnDef("initiator_type", "VARCHAR(64)", nullable=False),
                ColumnDef("case_type", "VARCHAR(64)", nullable=False),
                ColumnDef("status", "VARCHAR(64)", nullable=False),
                ColumnDef("first_contact_member_id", "VARCHAR(191)", nullable=False),
                ColumnDef("second_contact_member_id", "VARCHAR(191)", nullable=False),
                ColumnDef("first_reply_status", "VARCHAR(64)"),
                ColumnDef("second_reply_status", "VARCHAR(64)"),
                ColumnDef("first_contacted_at", "DATETIME"),
                ColumnDef("second_contacted_at", "DATETIME"),
                ColumnDef("closed_reason", "VARCHAR(191)"),
                ColumnDef("expires_at", "DATETIME"),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("case_id",),
            indexes=(
                IndexDef(("status", "created_at"), "idx_cases_status_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("pair_key",), "matchmaking_pairs", ("pair_key",)),
                ForeignKeyDef(("first_contact_member_id",), "matchmaking_pool_members", ("member_id",)),
                ForeignKeyDef(("second_contact_member_id",), "matchmaking_pool_members", ("member_id",)),
            ),
        ),
        TableDef(
            name="match_case_events",
            columns=(
                ColumnDef("event_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("pair_key", "VARCHAR(191)", nullable=False),
                ColumnDef("event_type", "VARCHAR(64)", nullable=False),
                ColumnDef("actor_member_id", "VARCHAR(191)"),
                ColumnDef("canonical_event_json", "LONGTEXT", nullable=True),
                ColumnDef("payload_json", "LONGTEXT", nullable=False),
                ColumnDef("occurred_at", "DATETIME", nullable=False),
            ),
            primary_key=("event_id",),
            indexes=(
                IndexDef(("case_id", "occurred_at"), "idx_case_events_case_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("case_id",), "match_cases", ("case_id",)),
                ForeignKeyDef(("pair_key",), "matchmaking_pairs", ("pair_key",)),
            ),
        ),
        TableDef(
            name="matchmaking_feedback_events",
            columns=(
                ColumnDef("feedback_id", "VARCHAR(191)", nullable=False),
                ColumnDef("member_id", "VARCHAR(191)", nullable=False),
                ColumnDef("feedback_kind", "VARCHAR(64)", nullable=False),
                ColumnDef("feedback_type", "VARCHAR(64)", nullable=False),
                ColumnDef("feedback_text", "TEXT"),
                ColumnDef("persona_patch_json", "LONGTEXT", nullable=False),
                ColumnDef("raw_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("persona_sync_result_json", "LONGTEXT", nullable=False),
                ColumnDef("synced_to_persona_memory", "TINYINT(1)", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("feedback_id",),
            indexes=(
                IndexDef(("member_id", "created_at"), "idx_feedback_member_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("member_id",), "matchmaking_pool_members", ("member_id",)),
            ),
        ),
        TableDef(
            name="outbox_events",
            columns=(
                ColumnDef("outbox_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("canonical_event_id", "VARCHAR(64)", nullable=False),
                ColumnDef("aggregate_type", "VARCHAR(32)", nullable=False),
                ColumnDef("aggregate_id", "VARCHAR(191)", nullable=False),
                ColumnDef("event_type", "VARCHAR(64)", nullable=False),
                ColumnDef("source_service", "VARCHAR(64)", nullable=False),
                ColumnDef("canonical_event_json", "LONGTEXT", nullable=False),
                ColumnDef("source_row_table", "VARCHAR(64)", nullable=False),
                ColumnDef("source_row_id", "BIGINT", nullable=True),
                ColumnDef("publish_status", "VARCHAR(32)", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("published_at", "DATETIME", nullable=True),
            ),
            primary_key=("outbox_id",),
            uniques=(
                UniqueKeyDef(("canonical_event_id",), name="uniq_outbox_canonical_event_id"),
            ),
            indexes=(
                IndexDef(("publish_status", "created_at"), "idx_outbox_pending_time"),
            ),
        ),
        *proxy_intro_matchmaking_tables(),
        ASYNC_JOB_TABLE,
    )


def proxy_intro_matchmaking_tables() -> tuple[TableDef, ...]:
    """Proxy-intro cases owned by matchmaking; recommendation rows stay on rec DB."""
    return (
        TableDef(
            name="proxy_intro_cases",
            columns=(
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("subscription_id", "VARCHAR(191)", nullable=False),
                ColumnDef("recommendation_id", "BIGINT", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                ColumnDef("candidate_id", "BIGINT", nullable=False),
                ColumnDef("candidate_name", "VARCHAR(255)", nullable=False),
                ColumnDef("initiated_by", "VARCHAR(64)", nullable=False),
                ColumnDef("case_type", "VARCHAR(64)", nullable=False),
                ColumnDef("case_status", "VARCHAR(64)", nullable=False),
                ColumnDef("close_reason", "VARCHAR(191)"),
                ColumnDef("outreach_channel", "VARCHAR(64)", nullable=False),
                ColumnDef("safe_summary_json", "LONGTEXT", nullable=False),
                ColumnDef("requester_profile_snapshot_json", "LONGTEXT", nullable=False),
                ColumnDef("candidate_snapshot_json", "LONGTEXT", nullable=False),
                ColumnDef("outreach_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("reply_payload_json", "LONGTEXT", nullable=False),
                ColumnDef("reply_deadline_at", "DATETIME"),
                ColumnDef("outreach_sent_at", "DATETIME"),
                ColumnDef("replied_at", "DATETIME"),
                ColumnDef("cooling_until", "DATETIME"),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("case_id",),
            indexes=(
                IndexDef(
                    ("subscription_id", "case_status", "created_at"),
                    "idx_proxy_intro_cases_subscription_status",
                ),
                IndexDef(
                    ("recommendation_id", "case_status", "updated_at"),
                    "idx_proxy_intro_cases_recommendation_status",
                ),
                IndexDef(
                    ("requester_id", "case_status", "updated_at"),
                    "idx_proxy_intro_cases_requester_status",
                ),
            ),
        ),
        TableDef(
            name="proxy_intro_case_events",
            columns=(
                ColumnDef("event_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("subscription_id", "VARCHAR(191)", nullable=False),
                ColumnDef("recommendation_id", "BIGINT", nullable=False),
                ColumnDef("requester_id", "BIGINT", nullable=False),
                ColumnDef("candidate_id", "BIGINT", nullable=False),
                ColumnDef("event_type", "VARCHAR(64)", nullable=False),
                ColumnDef("from_status", "VARCHAR(64)"),
                ColumnDef("to_status", "VARCHAR(64)"),
                ColumnDef("actor_type", "VARCHAR(32)", nullable=False),
                ColumnDef("canonical_event_json", "LONGTEXT", nullable=True),
                ColumnDef("payload_json", "LONGTEXT", nullable=False),
                ColumnDef("occurred_at", "DATETIME", nullable=False),
            ),
            primary_key=("event_id",),
            indexes=(
                IndexDef(("case_id", "occurred_at"), "idx_proxy_intro_case_events_case_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("case_id",), "proxy_intro_cases", ("case_id",)),
            ),
        ),
        TableDef(
            name="proxy_intro_case_outreach_attempts",
            columns=(
                ColumnDef("attempt_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("attempt_number", "INT", nullable=False),
                ColumnDef("channel", "VARCHAR(64)", nullable=False),
                ColumnDef("delivery_status", "VARCHAR(64)", nullable=False),
                ColumnDef("payload_json", "LONGTEXT", nullable=False),
                ColumnDef("provider_message_id", "VARCHAR(191)"),
                ColumnDef("error_code", "VARCHAR(64)"),
                ColumnDef("sent_at", "DATETIME", nullable=False),
            ),
            primary_key=("attempt_id",),
            uniques=(
                UniqueKeyDef(("case_id", "attempt_number")),
            ),
            indexes=(
                IndexDef(("case_id", "sent_at"), "idx_proxy_intro_attempts_case_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("case_id",), "proxy_intro_cases", ("case_id",)),
            ),
        ),
    )


def relationship_ledger_tables() -> tuple[TableDef, ...]:
    return (
        TableDef(
            name="match_relations",
            columns=(
                ColumnDef("relation_id", "VARCHAR(191)", nullable=False),
                ColumnDef("relation_key", "VARCHAR(255)", nullable=False),
                ColumnDef("owner_profile_ref_json", "LONGTEXT"),
                ColumnDef("target_profile_ref_json", "LONGTEXT"),
                ColumnDef("relation_status", "VARCHAR(64)", nullable=False),
                ColumnDef("current_phase", "VARCHAR(64)", nullable=False),
                ColumnDef("active_case_id", "VARCHAR(191)"),
                ColumnDef("active_case_type", "VARCHAR(32)"),
                ColumnDef("active_case_status", "VARCHAR(64)"),
                ColumnDef("latest_chat_thread_id", "VARCHAR(191)"),
                ColumnDef("last_chat_message_at", "DATETIME"),
                ColumnDef("source_summary_json", "LONGTEXT"),
                ColumnDef("last_event_type", "VARCHAR(128)"),
                ColumnDef("last_event_at", "DATETIME", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("relation_id",),
            uniques=(
                UniqueKeyDef(("relation_key",), name="uniq_match_relations_relation_key"),
            ),
            indexes=(
                IndexDef(("relation_status", "last_event_at"), "idx_match_relations_status_time"),
                IndexDef(("current_phase", "last_event_at"), "idx_match_relations_phase_time"),
            ),
        ),
        TableDef(
            name="match_relation_cases",
            columns=(
                ColumnDef("case_id", "VARCHAR(191)", nullable=False),
                ColumnDef("relation_id", "VARCHAR(191)", nullable=False),
                ColumnDef("case_type", "VARCHAR(32)", nullable=False),
                ColumnDef("owner_service", "VARCHAR(64)", nullable=False),
                ColumnDef("case_status", "VARCHAR(64)", nullable=False),
                ColumnDef("close_reason", "VARCHAR(64)"),
                ColumnDef("linked_aggregate_type", "VARCHAR(32)", nullable=False),
                ColumnDef("linked_aggregate_id", "VARCHAR(191)", nullable=False),
                ColumnDef("latest_event_type", "VARCHAR(128)"),
                ColumnDef("opened_at", "DATETIME", nullable=False),
                ColumnDef("closed_at", "DATETIME"),
                ColumnDef("last_event_at", "DATETIME", nullable=False),
                ColumnDef("metadata_json", "LONGTEXT"),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("updated_at", "DATETIME", nullable=False),
            ),
            primary_key=("case_id",),
            indexes=(
                IndexDef(("relation_id", "last_event_at"), "idx_match_relation_cases_relation_time"),
                IndexDef(("case_status", "last_event_at"), "idx_match_relation_cases_status_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("relation_id",), "match_relations", ("relation_id",)),
            ),
        ),
        TableDef(
            name="match_relation_events",
            columns=(
                ColumnDef("ledger_event_id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("relation_id", "VARCHAR(191)", nullable=False),
                ColumnDef("canonical_event_id", "VARCHAR(64)", nullable=False),
                ColumnDef("aggregate_type", "VARCHAR(32)", nullable=False),
                ColumnDef("aggregate_id", "VARCHAR(191)", nullable=False),
                ColumnDef("case_id", "VARCHAR(191)"),
                ColumnDef("case_type", "VARCHAR(32)"),
                ColumnDef("event_type", "VARCHAR(128)", nullable=False),
                ColumnDef("source_service", "VARCHAR(64)", nullable=False),
                ColumnDef("actor_type", "VARCHAR(32)", nullable=False),
                ColumnDef("actor_id", "VARCHAR(191)", nullable=False),
                ColumnDef("canonical_event_json", "LONGTEXT", nullable=False),
                ColumnDef("event_payload_json", "LONGTEXT"),
                ColumnDef("occurred_at", "DATETIME", nullable=False),
                ColumnDef("created_at", "DATETIME", nullable=False),
            ),
            primary_key=("ledger_event_id",),
            uniques=(
                UniqueKeyDef(("canonical_event_id",), name="uniq_match_relation_events_canonical_event_id"),
            ),
            indexes=(
                IndexDef(("relation_id", "occurred_at"), "idx_match_relation_events_relation_time"),
                IndexDef(("case_id", "occurred_at"), "idx_match_relation_events_case_time"),
                IndexDef(("aggregate_type", "aggregate_id", "occurred_at"), "idx_match_relation_events_aggregate_time"),
            ),
            foreign_keys=(
                ForeignKeyDef(("relation_id",), "match_relations", ("relation_id",)),
            ),
        ),
        # 档案状态转换审计日志表（新增）
        TableDef(
            name="profile_status_audit",
            columns=(
                ColumnDef("id", "BIGINT", nullable=False, auto_increment=True),
                ColumnDef("profile_id", "BIGINT", nullable=False),
                ColumnDef("from_status", "VARCHAR(20)", nullable=False),
                ColumnDef("to_status", "VARCHAR(20)", nullable=False),
                ColumnDef("reason", "VARCHAR(50)", nullable=False),
                ColumnDef("details", "JSON"),
                ColumnDef("actor_type", "VARCHAR(20)"),
                ColumnDef("actor_id", "BIGINT"),
                ColumnDef("occurred_at", "DATETIME", nullable=False),
            ),
            primary_key=("id",),
            indexes=(
                IndexDef(("profile_id", "occurred_at"), "idx_profile_status_audit_profile_time"),
                IndexDef(("reason", "occurred_at"), "idx_profile_status_audit_reason_time"),
                IndexDef(("from_status", "to_status"), "idx_profile_status_audit_from_to"),
            ),
        ),
    )


SYSTEM_TABLES: dict[str, tuple[TableDef, ...]] = {
    "recommendation": recommendation_tables(),
    "matchmaking": matchmaking_tables(),
    "chat": chat_tables(),
    "discovery": discovery_tables(),
    "relationship_ledger": relationship_ledger_tables(),
}

def ensure_schema(
    mysql_conn,
    tables: Sequence[TableDef],
    *,
    prefix: str | None,
    config: dict[str, Any],
    commit: bool = True,
) -> dict[str, list[str]]:
    created_indexes: dict[str, list[str]] = {}
    for table in tables:
        ensure_table(mysql_conn, table, prefix=prefix, config=config)
    for table in tables:
        ensure_table_columns(mysql_conn, table, prefix=prefix)
    for table in tables:
        dest_table = destination_table_name(table.name, prefix)
        created_uniques = ensure_unique_keys(mysql_conn, table, prefix=prefix)
        created_non_unique = ensure_indexes(mysql_conn, table, prefix=prefix)
        created_indexes[dest_table] = created_uniques + created_non_unique
    if commit:
        mysql_conn.commit()
    return created_indexes
