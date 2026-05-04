#!/usr/bin/env python3

"""Migrate external-system SQLite state tables into MySQL.

This tool currently supports the two outer systems in this repository:

- recommendation
- matchmaking

It creates MySQL tables from explicit table metadata and then copies rows
from a source SQLite database using idempotent upserts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence
from urllib.parse import parse_qs, unquote, urlparse


MYSQL_SCHEMES = {"mysql", "mysql+pymysql"}
DEFAULT_CHARSET = "utf8mb4"
DEFAULT_COLLATION = "utf8mb4_unicode_ci"
NO_DEFAULT = object()


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


SOURCE_COLUMN_DEFAULTS: dict[tuple[str, str], Any] = {
    ("saved_search_subscriptions", "initial_request_json"): "{}",
    ("saved_search_subscriptions", "subscription_overrides_json"): "{}",
    ("saved_search_subscriptions", "recommendation_mode"): "direct_greet_only",
    ("saved_search_subscriptions", "direct_greet_profile_json"): "{}",
    ("saved_search_subscriptions", "max_review_candidates_per_refresh"): 3,
    ("saved_search_subscriptions", "min_direct_greet_score"): 60,
    ("saved_search_subscriptions", "auto_reject_on_follow_up_questions"): 1,
    ("saved_search_subscriptions", "auto_reject_on_risk_flags"): 1,
    ("profile_recommendations", "final_review_status"): "match_ready",
    ("profile_recommendations", "final_review_score"): 0,
    ("profile_recommendations", "final_review_payload_json"): "{}",
    ("profile_recommendations", "user_review_status"): "not_requested",
    ("profile_recommendations", "user_review_payload_json"): "{}",
    ("profile_recommendations", "owner_profile_ref_json"): "{}",
    ("profile_recommendations", "target_profile_ref_json"): "{}",
    ("match_cases", "case_type"): "proxy_intro",
}


def quote_mysql_ident(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"


def quote_sqlite_ident(identifier: str) -> str:
    return f'"{identifier.replace(chr(34), chr(34) * 2)}"'


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
    parsed = urlparse(str(dsn))
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
    with mysql_server_connect(config) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {quote_mysql_ident(config['database'])} "
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


def build_upsert_sql(table: TableDef, *, prefix: str | None = None) -> str:
    dest_table = destination_table_name(table.name, prefix)
    columns = list(table.column_names)
    placeholders = ", ".join(["%s"] * len(columns))
    quoted_columns = ", ".join(quote_mysql_ident(column) for column in columns)
    non_pk_columns = [column for column in columns if column not in set(table.primary_key)]
    if non_pk_columns:
        update_clause = ", ".join(
            f"{quote_mysql_ident(column)} = VALUES({quote_mysql_ident(column)})"
            for column in non_pk_columns
        )
    else:
        primary_key = table.primary_key[0]
        update_clause = f"{quote_mysql_ident(primary_key)} = VALUES({quote_mysql_ident(primary_key)})"
    return (
        f"INSERT INTO {quote_mysql_ident(dest_table)} ({quoted_columns}) "
        f"VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )


def build_select_sql(table: TableDef) -> str:
    columns = ", ".join(quote_sqlite_ident(column) for column in table.column_names)
    if table.primary_key:
        order_by = ", ".join(quote_sqlite_ident(column) for column in table.primary_key)
        return f"SELECT {columns} FROM {quote_sqlite_ident(table.name)} ORDER BY {order_by}"
    return f"SELECT {columns} FROM {quote_sqlite_ident(table.name)}"


def normalize_mysql_value(value: Any) -> Any:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, memoryview):
        return bytes(value)
    return value


def chunked(rows: Sequence[Sequence[Any]], batch_size: int) -> Iterator[Sequence[Sequence[Any]]]:
    for index in range(0, len(rows), batch_size):
        yield rows[index : index + batch_size]


def sqlite_table_exists(sqlite_conn: sqlite3.Connection, table_name: str) -> bool:
    row = sqlite_conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return row is not None


def load_sqlite_rows(sqlite_conn: sqlite3.Connection, table: TableDef) -> list[tuple[Any, ...]]:
    if not sqlite_table_exists(sqlite_conn, table.name):
        return []
    actual_columns = {
        row["name"] for row in sqlite_conn.execute(f"PRAGMA table_info({quote_sqlite_ident(table.name)})").fetchall()
    }
    query = build_select_sql(table)
    rows = sqlite_conn.execute(query).fetchall()
    values: list[tuple[Any, ...]] = []
    for row in rows:
        rendered: list[Any] = []
        for column in table.columns:
            if column.name in actual_columns:
                value = row[column.name]
            else:
                default = SOURCE_COLUMN_DEFAULTS.get((table.name, column.name), NO_DEFAULT)
                if default is not NO_DEFAULT:
                    value = default
                elif column.nullable:
                    value = None
                else:
                    raise ValueError(
                        f"Source table {table.name!r} is missing required column {column.name!r} "
                        "and no migration default is defined."
                    )
            rendered.append(normalize_mysql_value(value))
        values.append(tuple(rendered))
    return values


def table_exists(mysql_conn, table_name: str) -> bool:
    with mysql_conn.cursor() as cursor:
        cursor.execute("SHOW TABLES LIKE %s", (table_name,))
        return cursor.fetchone() is not None


def index_exists(mysql_conn, table_name: str, index_name: str) -> bool:
    with mysql_conn.cursor() as cursor:
        cursor.execute(f"SHOW INDEX FROM {quote_mysql_ident(table_name)} WHERE Key_name = %s", (index_name,))
        return cursor.fetchone() is not None


def ensure_table(mysql_conn, table: TableDef, *, prefix: str | None = None, config: dict[str, Any] | None = None) -> None:
    sql = build_create_table_sql(table, prefix=prefix, config=config)
    with mysql_conn.cursor() as cursor:
        cursor.execute(sql)


def ensure_indexes(mysql_conn, table: TableDef, *, prefix: str | None = None) -> list[str]:
    dest_table = destination_table_name(table.name, prefix)
    created: list[str] = []
    with mysql_conn.cursor() as cursor:
        for index in table.indexes:
            index_name = stable_name(normalize_prefix(prefix), index.name)
            if index_exists(mysql_conn, dest_table, index_name):
                continue
            cursor.execute(
                f"CREATE INDEX {quote_mysql_ident(index_name)} ON {quote_mysql_ident(dest_table)} ("
                + ", ".join(quote_mysql_ident(column) for column in index.columns)
                + ")"
            )
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


def migrate_table(mysql_conn, sqlite_conn: sqlite3.Connection, table: TableDef, *, prefix: str | None = None, batch_size: int = 500) -> int:
    rows = load_sqlite_rows(sqlite_conn, table)
    if not rows:
        return 0

    sql = build_upsert_sql(table, prefix=prefix)
    with mysql_conn.cursor() as cursor:
        for batch in chunked(rows, batch_size):
            cursor.executemany(sql, list(batch))
    return len(rows)


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
                ColumnDef("latest_card_id", "VARCHAR(191)"),
            ),
            primary_key=("recommendation_id",),
            uniques=(
                UniqueKeyDef(("subscription_id", "candidate_id")),
            ),
            indexes=(
                IndexDef(("subscription_id", "delivery_status", "score"), "idx_recommendations_subscription_status"),
                IndexDef(("requester_id", "delivery_status", "notified_at"), "idx_recommendations_requester_status"),
                IndexDef(("subscription_id", "final_review_status", "score"), "idx_recommendations_review_status"),
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
    )


SYSTEM_TABLES: dict[str, tuple[TableDef, ...]] = {
    "recommendation": recommendation_tables(),
    "matchmaking": matchmaking_tables(),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate outer-system SQLite tables into MySQL.")
    parser.add_argument(
        "--system",
        required=True,
        choices=sorted(SYSTEM_TABLES),
        help="Which outer-system schema to migrate.",
    )
    parser.add_argument(
        "--sqlite",
        required=True,
        help="Source SQLite database path.",
    )
    parser.add_argument(
        "--target-dsn",
        required=True,
        help="Target MySQL DSN, for example mysql://user:pass@127.0.0.1:3306/her_recommendation",
    )
    parser.add_argument(
        "--table-prefix",
        default="",
        help="Optional destination table prefix, useful if both systems share one MySQL database.",
    )
    parser.add_argument(
        "--schema-only",
        action="store_true",
        help="Only create the target schema; do not copy rows.",
    )
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Only copy rows; assume the target schema already exists.",
    )
    parser.add_argument(
        "--truncate-first",
        action="store_true",
        help="Delete existing rows from destination tables before importing.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Batch size for MySQL executemany inserts.",
    )
    return parser.parse_args()


def ensure_schema(mysql_conn, tables: Sequence[TableDef], *, prefix: str | None, config: dict[str, Any]) -> dict[str, list[str]]:
    created_indexes: dict[str, list[str]] = {}
    for table in tables:
        ensure_table(mysql_conn, table, prefix=prefix, config=config)
    for table in tables:
        created_indexes[destination_table_name(table.name, prefix)] = ensure_indexes(mysql_conn, table, prefix=prefix)
    mysql_conn.commit()
    return created_indexes


def migrate(mysql_conn, sqlite_conn: sqlite3.Connection, tables: Sequence[TableDef], *, prefix: str | None, batch_size: int) -> dict[str, int]:
    migrated: dict[str, int] = {}
    for table in tables:
        migrated[destination_table_name(table.name, prefix)] = migrate_table(
            mysql_conn,
            sqlite_conn,
            table,
            prefix=prefix,
            batch_size=batch_size,
        )
    mysql_conn.commit()
    return migrated


def main() -> int:
    args = parse_args()
    if args.schema_only and args.data_only:
        raise SystemExit("Choose at most one of --schema-only or --data-only.")
    if args.batch_size <= 0:
        raise SystemExit("--batch-size must be greater than 0.")

    sqlite_path = Path(args.sqlite).resolve()
    if not sqlite_path.exists():
        raise SystemExit(f"SQLite file not found: {sqlite_path}")

    tables = SYSTEM_TABLES[args.system]
    config = parse_mysql_dsn(args.target_dsn)
    prefix = normalize_prefix(args.table_prefix)

    ensure_database(config)
    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row
    try:
        mysql_conn = mysql_database_connect(config)
        try:
            created_indexes: dict[str, list[str]] = {}
            if not args.data_only:
                created_indexes = ensure_schema(mysql_conn, tables, prefix=prefix, config=config)

            if args.truncate_first and not args.schema_only:
                clear_tables(mysql_conn, tables, prefix=prefix)
                mysql_conn.commit()

            migrated_rows: dict[str, int] = {}
            if not args.schema_only:
                migrated_rows = migrate(
                    mysql_conn,
                    sqlite_conn,
                    tables,
                    prefix=prefix,
                    batch_size=args.batch_size,
                )

            summary = {
                "system": args.system,
                "sqlite_path": str(sqlite_path),
                "target_database": config["database"],
                "table_prefix": prefix,
                "schema_only": bool(args.schema_only),
                "data_only": bool(args.data_only),
                "truncate_first": bool(args.truncate_first),
                "tables": [destination_table_name(table.name, prefix) for table in tables],
                "created_indexes": created_indexes,
                "migrated_rows": migrated_rows,
                "total_rows": sum(migrated_rows.values()),
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0
        finally:
            mysql_conn.close()
    finally:
        sqlite_conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
