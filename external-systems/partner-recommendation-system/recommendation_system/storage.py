"""SQLite storage for the Phase 3 external recommendation system."""

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
      self_profile_json TEXT,
      limit_count INTEGER NOT NULL DEFAULT 10,
      top_k INTEGER NOT NULL DEFAULT 5,
      min_notify_score INTEGER NOT NULL DEFAULT 40,
      daily_notification_cap INTEGER NOT NULL DEFAULT 2,
      quiet_hours_start INTEGER NOT NULL DEFAULT 22,
      quiet_hours_end INTEGER NOT NULL DEFAULT 9,
      refresh_interval_hours INTEGER NOT NULL DEFAULT 24,
      skip_cooldown_days INTEGER NOT NULL DEFAULT 30,
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
    "CREATE INDEX IF NOT EXISTS idx_saved_search_due ON saved_search_subscriptions(status, is_still_searching, last_refreshed_at)",
    "CREATE INDEX IF NOT EXISTS idx_recommendations_subscription_status ON profile_recommendations(subscription_id, delivery_status, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_recommendations_requester_status ON profile_recommendations(requester_id, delivery_status, notified_at)",
    "CREATE INDEX IF NOT EXISTS idx_actions_recommendation_time ON recommendation_actions(recommendation_id, occurred_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cards_requester_time ON in_app_recommendation_cards(requester_id, delivered_at DESC)",
)


def connect_db(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize_database(conn: sqlite3.Connection) -> None:
    for statement in SCHEMA_STATEMENTS:
        conn.execute(statement)
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
