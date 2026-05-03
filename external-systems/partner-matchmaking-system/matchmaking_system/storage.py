"""SQLite storage for the Phase 5 matchmaking outer system."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS matchmaking_pool_members (
      member_id TEXT PRIMARY KEY,
      user_key TEXT NOT NULL,
      source TEXT NOT NULL,
      table_name TEXT,
      photos_table_name TEXT,
      self_id INTEGER,
      self_profile_json TEXT NOT NULL,
      search_criteria_json TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'active_single',
      is_still_searching INTEGER NOT NULL DEFAULT 1,
      allowed_channels_json TEXT NOT NULL DEFAULT '[]',
      min_pair_score INTEGER NOT NULL DEFAULT 80,
      daily_case_cap INTEGER NOT NULL DEFAULT 1,
      refresh_interval_hours INTEGER NOT NULL DEFAULT 24,
      limit_count INTEGER NOT NULL DEFAULT 10,
      last_scanned_at TEXT,
      last_state_reason TEXT,
      needs_refresh INTEGER NOT NULL DEFAULT 1,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(source, user_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matchmaking_edges (
      edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
      owner_member_id TEXT NOT NULL,
      candidate_member_id TEXT NOT NULL,
      score INTEGER NOT NULL,
      fit_score INTEGER NOT NULL DEFAULT 0,
      confidence_score INTEGER NOT NULL DEFAULT 0,
      risk_score INTEGER NOT NULL DEFAULT 0,
      edge_status TEXT NOT NULL DEFAULT 'active',
      edge_reason TEXT,
      snapshot_hash TEXT,
      payload_json TEXT NOT NULL,
      discovered_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(owner_member_id, candidate_member_id),
      FOREIGN KEY(owner_member_id) REFERENCES matchmaking_pool_members(member_id),
      FOREIGN KEY(candidate_member_id) REFERENCES matchmaking_pool_members(member_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matchmaking_pairs (
      pair_key TEXT PRIMARY KEY,
      member_low_id TEXT NOT NULL,
      member_high_id TEXT NOT NULL,
      score_low_to_high INTEGER NOT NULL DEFAULT 0,
      score_high_to_low INTEGER NOT NULL DEFAULT 0,
      pair_score INTEGER NOT NULL DEFAULT 0,
      pair_status TEXT NOT NULL,
      block_reason TEXT,
      cooling_until TEXT,
      latest_payload_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(member_low_id) REFERENCES matchmaking_pool_members(member_id),
      FOREIGN KEY(member_high_id) REFERENCES matchmaking_pool_members(member_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS match_cases (
      case_id TEXT PRIMARY KEY,
      pair_key TEXT NOT NULL,
      initiator_type TEXT NOT NULL DEFAULT 'system',
      case_type TEXT NOT NULL DEFAULT 'matchmaking',
      status TEXT NOT NULL,
      first_contact_member_id TEXT NOT NULL,
      second_contact_member_id TEXT NOT NULL,
      first_reply_status TEXT,
      second_reply_status TEXT,
      first_contacted_at TEXT,
      second_contacted_at TEXT,
      closed_reason TEXT,
      expires_at TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(pair_key) REFERENCES matchmaking_pairs(pair_key),
      FOREIGN KEY(first_contact_member_id) REFERENCES matchmaking_pool_members(member_id),
      FOREIGN KEY(second_contact_member_id) REFERENCES matchmaking_pool_members(member_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS match_case_events (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT,
      case_id TEXT NOT NULL,
      pair_key TEXT NOT NULL,
      event_type TEXT NOT NULL,
      actor_member_id TEXT,
      payload_json TEXT NOT NULL DEFAULT '{}',
      occurred_at TEXT NOT NULL,
      FOREIGN KEY(case_id) REFERENCES match_cases(case_id),
      FOREIGN KEY(pair_key) REFERENCES matchmaking_pairs(pair_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS matchmaking_feedback_events (
      feedback_id TEXT PRIMARY KEY,
      member_id TEXT NOT NULL,
      feedback_kind TEXT NOT NULL,
      feedback_type TEXT NOT NULL,
      feedback_text TEXT,
      persona_patch_json TEXT NOT NULL DEFAULT '{}',
      raw_payload_json TEXT NOT NULL DEFAULT '{}',
      persona_sync_result_json TEXT NOT NULL DEFAULT '{}',
      synced_to_persona_memory INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      FOREIGN KEY(member_id) REFERENCES matchmaking_pool_members(member_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_pool_members_status_scan ON matchmaking_pool_members(status, is_still_searching, last_scanned_at)",
    "CREATE INDEX IF NOT EXISTS idx_edges_owner_status ON matchmaking_edges(owner_member_id, edge_status, score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_pairs_status_score ON matchmaking_pairs(pair_status, pair_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cases_status_time ON match_cases(status, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_case_events_case_time ON match_case_events(case_id, occurred_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_member_time ON matchmaking_feedback_events(member_id, created_at DESC)",
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
    ensure_column(
        conn,
        "match_cases",
        "case_type",
        "TEXT NOT NULL DEFAULT 'matchmaking'",
    )
    conn.commit()


def json_dumps(value: Any) -> str:
    if value is None:
        value = {}
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)
