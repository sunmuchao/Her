#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from persona_memory_sync.audit import (  # noqa: E402
    PERSONA_SNAPSHOT_FIELDS,
    PROFILE_SNAPSHOT_FIELDS,
    PUBLIC_VIEW_SNAPSHOT_FIELDS,
    mask_snapshot_for_review,
    prune_none,
)
from persona_memory_sync.persona_memory_lib import mysql_connect, quote_mysql_ident  # noqa: E402


DEFAULT_PERSONA_TABLE = "user_personas"
DEFAULT_OBSERVATION_TABLE = "user_persona_observations"
DEFAULT_PROFILE_TABLE = "profiles"
DEFAULT_PUBLIC_VIEW = "public_profile_view"
OBSERVATION_FIELDS = [
    "id",
    "field_name",
    "field_value",
    "source_type",
    "confidence_score",
    "evidence_text",
    "conversation_ref",
    "action_type",
    "applied_to_persona",
    "applied_to_profile",
    "created_at",
]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build persona-eval memory snapshots from MySQL plus input persona metadata.",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Persona input JSON such as input_personas.json.",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="MySQL DSN used by persona-memory-sync.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Where to write memory_snapshots.json.",
    )
    parser.add_argument("--persona-table", default=DEFAULT_PERSONA_TABLE)
    parser.add_argument("--observation-table", default=DEFAULT_OBSERVATION_TABLE)
    parser.add_argument("--profile-table", default=DEFAULT_PROFILE_TABLE)
    parser.add_argument("--public-view", default=DEFAULT_PUBLIC_VIEW)
    return parser.parse_args()


def load_json(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"Expected a JSON list in {path}")
    return payload


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def fetch_row(cursor, table_name, where_column, where_value):
    cursor.execute(
        f"SELECT * FROM {quote_mysql_ident(table_name)} WHERE {quote_mysql_ident(where_column)} = %s",
        (where_value,),
    )
    return cursor.fetchone() or {}


def fetch_observations(cursor, table_name, user_key):
    cursor.execute(
        f"""
        SELECT {", ".join(quote_mysql_ident(field) for field in OBSERVATION_FIELDS)}
        FROM {quote_mysql_ident(table_name)}
        WHERE user_key = %s
        ORDER BY id ASC
        """,
        (user_key,),
    )
    return [prune_none({field: row.get(field) for field in OBSERVATION_FIELDS}) for row in cursor.fetchall()]


def build_snapshot_entry(
    cursor,
    persona_entry,
    *,
    persona_table,
    observation_table,
    profile_table,
    public_view,
):
    user_key = persona_entry.get("user_key")
    if not user_key:
        raise ValueError(f"Persona entry missing user_key: {persona_entry.get('persona_id')}")

    persona_row = fetch_row(cursor, persona_table, "user_key", user_key)
    profile_id = persona_row.get("profile_id") or persona_entry.get("profile_id")
    profile_row = fetch_row(cursor, profile_table, "id", profile_id) if profile_id else {}
    public_row = fetch_row(cursor, public_view, "id", profile_id) if profile_id else {}
    observations = fetch_observations(cursor, observation_table, user_key)

    raw_snapshot = {
        "user_persona": prune_none({field: persona_row.get(field) for field in PERSONA_SNAPSHOT_FIELDS}),
        "profile_internal": prune_none({field: profile_row.get(field) for field in PROFILE_SNAPSHOT_FIELDS}),
        "public_profile_view": prune_none({field: public_row.get(field) for field in PUBLIC_VIEW_SNAPSHOT_FIELDS}),
    }
    masked_snapshot = mask_snapshot_for_review(raw_snapshot, persona_entry.get("private_boundaries"))

    return {
        "persona_id": persona_entry.get("persona_id"),
        "display_name": persona_entry.get("display_name"),
        "agent_id": persona_entry.get("agent_id"),
        "user_key": user_key,
        "profile_id": profile_id,
        "private_boundaries": persona_entry.get("private_boundaries") or [],
        "roleplay_answers": persona_entry.get("roleplay_answers") or [],
        "notes_about_possible_drift": persona_entry.get("notes_about_possible_drift") or [],
        "user_persona_observations": observations,
        "user_persona": masked_snapshot["user_persona"],
        "profile_internal": masked_snapshot["profile_internal"],
        "public_profile_view": masked_snapshot["public_profile_view"],
    }


def main():
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    personas = load_json(input_path)

    conn = mysql_connect(args.source)
    try:
        with conn.cursor() as cursor:
            snapshots = [
                build_snapshot_entry(
                    cursor,
                    persona_entry,
                    persona_table=args.persona_table,
                    observation_table=args.observation_table,
                    profile_table=args.profile_table,
                    public_view=args.public_view,
                )
                for persona_entry in personas
            ]
    finally:
        conn.close()

    write_json(output_path, snapshots)
    print(
        json.dumps(
            {
                "input": str(input_path),
                "output": str(output_path),
                "persona_count": len(snapshots),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
