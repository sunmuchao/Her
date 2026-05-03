"""SQLite storage for the Phase 3/4 external recommendation system."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS saved_search_subscriptions (
      subscription_id TEXT PRIMARY KEY,
      requester_id INTEGER NOT NULL,
      title TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'active',
      is_still_searching INTEGER NOT NULL DEFAULT 1,
      source TEXT NOT NULL,
      table_name TEXT,
      photos_table_name TEXT,
      search_criteria_json TEXT NOT NULL,
      initial_request_json TEXT NOT NULL DEFAULT '{}',
      subscription_overrides_json TEXT NOT NULL DEFAULT '{}',
      self_profile_json TEXT,
      self_id INTEGER,
      limit_count INTEGER NOT NULL DEFAULT 10,
      top_k INTEGER NOT NULL DEFAULT 5,
      min_notify_score INTEGER NOT NULL DEFAULT 40,
      daily_notification_cap INTEGER NOT NULL DEFAULT 2,
      quiet_hours_start INTEGER NOT NULL DEFAULT 22,
      quiet_hours_end INTEGER NOT NULL DEFAULT 9,
      refresh_interval_hours INTEGER NOT NULL DEFAULT 24,
      skip_cooldown_days INTEGER NOT NULL DEFAULT 30,
      recommendation_mode TEXT NOT NULL DEFAULT 'direct_greet_only',
      direct_greet_profile_json TEXT NOT NULL DEFAULT '{}',
      max_review_candidates_per_refresh INTEGER NOT NULL DEFAULT 3,
      min_direct_greet_score INTEGER NOT NULL DEFAULT 60,
      auto_reject_on_follow_up_questions INTEGER NOT NULL DEFAULT 1,
      auto_reject_on_risk_flags INTEGER NOT NULL DEFAULT 1,
      last_refreshed_at TEXT,
      last_result_count INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS profile_recommendations (
      recommendation_id INTEGER PRIMARY KEY AUTOINCREMENT,
      subscription_id TEXT NOT NULL,
      requester_id INTEGER NOT NULL,
      candidate_id INTEGER NOT NULL,
      candidate_name TEXT NOT NULL,
      score INTEGER NOT NULL,
      fit_score INTEGER NOT NULL DEFAULT 0,
      confidence_score INTEGER NOT NULL DEFAULT 0,
      risk_score INTEGER NOT NULL DEFAULT 0,
      delivery_status TEXT NOT NULL,
      delivery_reason TEXT,
      first_seen_at TEXT NOT NULL,
      last_seen_at TEXT NOT NULL,
      notified_at TEXT,
      cooling_until TEXT,
      last_action_type TEXT,
      matched_on_json TEXT NOT NULL,
      risk_flags_json TEXT NOT NULL,
      latest_payload_json TEXT NOT NULL,
      final_review_status TEXT NOT NULL DEFAULT 'match_ready',
      final_review_reason TEXT,
      final_review_score INTEGER NOT NULL DEFAULT 0,
      final_review_payload_json TEXT NOT NULL DEFAULT '{}',
      reviewed_at TEXT,
      candidate_snapshot_hash TEXT,
      user_review_status TEXT NOT NULL DEFAULT 'not_requested',
      user_review_reason TEXT,
      user_review_payload_json TEXT NOT NULL DEFAULT '{}',
      user_reviewed_at TEXT,
      relation_key TEXT,
      owner_profile_ref_json TEXT NOT NULL DEFAULT '{}',
      target_profile_ref_json TEXT NOT NULL DEFAULT '{}',
      active_match_case_id TEXT,
      latest_card_id TEXT,
      UNIQUE(subscription_id, candidate_id),
      FOREIGN KEY(subscription_id) REFERENCES saved_search_subscriptions(subscription_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS recommendation_actions (
      action_id INTEGER PRIMARY KEY AUTOINCREMENT,
      subscription_id TEXT NOT NULL,
      recommendation_id INTEGER NOT NULL,
      requester_id INTEGER NOT NULL,
      candidate_id INTEGER NOT NULL,
      action_type TEXT NOT NULL,
      action_payload_json TEXT,
      occurred_at TEXT NOT NULL,
      FOREIGN KEY(recommendation_id) REFERENCES profile_recommendations(recommendation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS in_app_recommendation_cards (
      card_id TEXT PRIMARY KEY,
      subscription_id TEXT NOT NULL,
      recommendation_id INTEGER NOT NULL,
      requester_id INTEGER NOT NULL,
      candidate_id INTEGER NOT NULL,
      card_status TEXT NOT NULL DEFAULT 'unread',
      title TEXT NOT NULL,
      subtitle TEXT NOT NULL,
      body TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      created_at TEXT NOT NULL,
      delivered_at TEXT NOT NULL,
      FOREIGN KEY(recommendation_id) REFERENCES profile_recommendations(recommendation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS saved_search_runs (
      run_id INTEGER PRIMARY KEY AUTOINCREMENT,
      subscription_id TEXT NOT NULL,
      requester_id INTEGER NOT NULL,
      source TEXT NOT NULL,
      table_name TEXT,
      photos_table_name TEXT,
      self_id INTEGER,
      persona_profile_json TEXT NOT NULL DEFAULT '{}',
      effective_criteria_json TEXT NOT NULL,
      search_request_json TEXT NOT NULL DEFAULT '{}',
      result_count INTEGER NOT NULL DEFAULT 0,
      top_candidate_ids_json TEXT NOT NULL DEFAULT '[]',
      status_counts_json TEXT NOT NULL DEFAULT '{}',
      review_counts_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL,
      FOREIGN KEY(subscription_id) REFERENCES saved_search_subscriptions(subscription_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS match_cases (
      case_id TEXT PRIMARY KEY,
      subscription_id TEXT NOT NULL,
      recommendation_id INTEGER NOT NULL,
      requester_id INTEGER NOT NULL,
      candidate_id INTEGER NOT NULL,
      candidate_name TEXT NOT NULL,
      initiated_by TEXT NOT NULL DEFAULT 'requester',
      case_type TEXT NOT NULL DEFAULT 'proxy_intro',
      case_status TEXT NOT NULL,
      close_reason TEXT,
      outreach_channel TEXT NOT NULL DEFAULT 'in_app_proxy_intro',
      safe_summary_json TEXT NOT NULL DEFAULT '{}',
      requester_profile_snapshot_json TEXT NOT NULL DEFAULT '{}',
      candidate_snapshot_json TEXT NOT NULL DEFAULT '{}',
      outreach_payload_json TEXT NOT NULL DEFAULT '{}',
      reply_payload_json TEXT NOT NULL DEFAULT '{}',
      reply_deadline_at TEXT,
      outreach_sent_at TEXT,
      replied_at TEXT,
      cooling_until TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(subscription_id) REFERENCES saved_search_subscriptions(subscription_id),
      FOREIGN KEY(recommendation_id) REFERENCES profile_recommendations(recommendation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS match_case_events (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id TEXT NOT NULL,
      subscription_id TEXT NOT NULL,
      recommendation_id INTEGER NOT NULL,
      requester_id INTEGER NOT NULL,
      candidate_id INTEGER NOT NULL,
      event_type TEXT NOT NULL,
      from_status TEXT,
      to_status TEXT,
      actor_type TEXT NOT NULL,
      payload_json TEXT NOT NULL DEFAULT '{}',
      occurred_at TEXT NOT NULL,
      FOREIGN KEY(case_id) REFERENCES match_cases(case_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS match_case_outreach_attempts (
      attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id TEXT NOT NULL,
      attempt_number INTEGER NOT NULL,
      channel TEXT NOT NULL,
      delivery_status TEXT NOT NULL,
      payload_json TEXT NOT NULL DEFAULT '{}',
      provider_message_id TEXT,
      error_code TEXT,
      sent_at TEXT NOT NULL,
      UNIQUE(case_id, attempt_number),
      FOREIGN KEY(case_id) REFERENCES match_cases(case_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_saved_search_due ON saved_search_subscriptions(status, is_still_searching, last_refreshed_at)",
    "CREATE INDEX IF NOT EXISTS idx_recommendations_subscription_status ON profile_recommendations(subscription_id, delivery_status, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_recommendations_requester_status ON profile_recommendations(requester_id, delivery_status, notified_at)",
    "CREATE INDEX IF NOT EXISTS idx_recommendations_review_status ON profile_recommendations(subscription_id, final_review_status, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_saved_search_runs_subscription_time ON saved_search_runs(subscription_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_match_cases_subscription_status ON match_cases(subscription_id, case_status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_match_cases_recommendation_status ON match_cases(recommendation_id, case_status, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_match_cases_requester_status ON match_cases(requester_id, case_status, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_match_case_events_case_time ON match_case_events(case_id, occurred_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_match_case_attempts_case_time ON match_case_outreach_attempts(case_id, sent_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_actions_recommendation_time ON recommendation_actions(recommendation_id, occurred_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cards_requester_time ON in_app_recommendation_cards(requester_id, delivered_at DESC)",
)


def connect_db(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    columns = {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def initialize_database(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)
    ensure_column(conn, "saved_search_subscriptions", "self_id", "INTEGER")
    ensure_column(
        conn,
        "saved_search_subscriptions",
        "recommendation_mode",
        "TEXT NOT NULL DEFAULT 'direct_greet_only'",
    )
    ensure_column(
        conn,
        "saved_search_subscriptions",
        "direct_greet_profile_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )
    ensure_column(
        conn,
        "saved_search_subscriptions",
        "initial_request_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )
    ensure_column(
        conn,
        "saved_search_subscriptions",
        "subscription_overrides_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )
    ensure_column(
        conn,
        "saved_search_subscriptions",
        "max_review_candidates_per_refresh",
        "INTEGER NOT NULL DEFAULT 3",
    )
    ensure_column(
        conn,
        "saved_search_subscriptions",
        "min_direct_greet_score",
        "INTEGER NOT NULL DEFAULT 60",
    )
    ensure_column(
        conn,
        "saved_search_subscriptions",
        "auto_reject_on_follow_up_questions",
        "INTEGER NOT NULL DEFAULT 1",
    )
    ensure_column(
        conn,
        "saved_search_subscriptions",
        "auto_reject_on_risk_flags",
        "INTEGER NOT NULL DEFAULT 1",
    )
    ensure_column(
        conn,
        "profile_recommendations",
        "final_review_status",
        "TEXT NOT NULL DEFAULT 'match_ready'",
    )
    ensure_column(conn, "profile_recommendations", "final_review_reason", "TEXT")
    ensure_column(
        conn,
        "profile_recommendations",
        "final_review_score",
        "INTEGER NOT NULL DEFAULT 0",
    )
    ensure_column(
        conn,
        "profile_recommendations",
        "final_review_payload_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )
    ensure_column(conn, "profile_recommendations", "reviewed_at", "TEXT")
    ensure_column(conn, "profile_recommendations", "candidate_snapshot_hash", "TEXT")
    ensure_column(
        conn,
        "profile_recommendations",
        "user_review_status",
        "TEXT NOT NULL DEFAULT 'not_requested'",
    )
    ensure_column(conn, "profile_recommendations", "user_review_reason", "TEXT")
    ensure_column(
        conn,
        "profile_recommendations",
        "user_review_payload_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )
    ensure_column(conn, "profile_recommendations", "user_reviewed_at", "TEXT")
    ensure_column(conn, "profile_recommendations", "relation_key", "TEXT")
    ensure_column(
        conn,
        "profile_recommendations",
        "owner_profile_ref_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )
    ensure_column(
        conn,
        "profile_recommendations",
        "target_profile_ref_json",
        "TEXT NOT NULL DEFAULT '{}'",
    )
    ensure_column(conn, "profile_recommendations", "active_match_case_id", "TEXT")
    ensure_column(
        conn,
        "match_cases",
        "case_type",
        "TEXT NOT NULL DEFAULT 'proxy_intro'",
    )
    ensure_column(conn, "saved_search_runs", "persona_profile_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(conn, "saved_search_runs", "effective_criteria_json", "TEXT NOT NULL DEFAULT '{}'")  # noqa: B950
    ensure_column(conn, "saved_search_runs", "search_request_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(conn, "saved_search_runs", "top_candidate_ids_json", "TEXT NOT NULL DEFAULT '[]'")
    ensure_column(conn, "saved_search_runs", "status_counts_json", "TEXT NOT NULL DEFAULT '{}'")
    ensure_column(conn, "saved_search_runs", "review_counts_json", "TEXT NOT NULL DEFAULT '{}'")
    conn.commit()


def json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)
