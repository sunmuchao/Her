"""MySQL schema metadata and DDL helpers for recommendation and matchmaking outer systems."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Sequence
from urllib.parse import parse_qs, unquote, urlparse

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

def quote_mysql_ident(identifier: str) -> str:
    return f"`{identifier.replace('`', '``')}`"


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
            cursor.execute(alter_sql)


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
                ColumnDef("status", "VARCHAR(32)", nullable=False),
                ColumnDef("patch_json", "LONGTEXT", nullable=True),
                ColumnDef("evidence_json", "LONGTEXT", nullable=False),
                ColumnDef("sync_result_json", "LONGTEXT", nullable=True),
                ColumnDef("created_at", "DATETIME", nullable=False),
                ColumnDef("processed_at", "DATETIME", nullable=True),
            ),
            primary_key=("job_id",),
            uniques=(
                UniqueKeyDef(("message_id", "subject_user_id"), name="uniq_persona_job_msg_subject"),
            ),
            indexes=(
                IndexDef(("status", "created_at"), "idx_persona_jobs_status_time"),
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
    )


SYSTEM_TABLES: dict[str, tuple[TableDef, ...]] = {
    "recommendation": recommendation_tables(),
    "matchmaking": matchmaking_tables(),
    "chat": chat_tables(),
}

def ensure_schema(mysql_conn, tables: Sequence[TableDef], *, prefix: str | None, config: dict[str, Any]) -> dict[str, list[str]]:
    created_indexes: dict[str, list[str]] = {}
    for table in tables:
        ensure_table(mysql_conn, table, prefix=prefix, config=config)
    for table in tables:
        ensure_table_columns(mysql_conn, table, prefix=prefix)
    for table in tables:
        created_indexes[destination_table_name(table.name, prefix)] = ensure_indexes(mysql_conn, table, prefix=prefix)
    mysql_conn.commit()
    return created_indexes
