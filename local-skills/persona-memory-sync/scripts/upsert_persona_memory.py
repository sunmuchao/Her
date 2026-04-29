#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from persona_memory_lib import (
    DEFAULT_OBSERVATION_TABLE,
    DEFAULT_PERSONA_TABLE,
    build_profile_payload,
    merge_persona,
    mysql_connect,
    normalize_patch,
    now_string,
    parse_mysql_source,
    parse_patch_json,
    quote_mysql_ident,
)


def fetch_persona(cursor, persona_table: str, user_key: str):
    cursor.execute(
        f"SELECT * FROM {quote_mysql_ident(persona_table)} WHERE user_key = %s",
        (user_key,),
    )
    return cursor.fetchone()


def upsert_persona(cursor, persona_table: str, merged_persona):
    payload = {key: value for key, value in merged_persona.items() if key not in {"id", "created_at"}}
    columns = list(payload.keys())
    values = [payload[column] for column in columns]
    update_clause = ", ".join(
        f"{quote_mysql_ident(column)} = VALUES({quote_mysql_ident(column)})" for column in columns
    )
    cursor.execute(
        f"""
        INSERT INTO {quote_mysql_ident(persona_table)} ({", ".join(quote_mysql_ident(column) for column in columns)})
        VALUES ({", ".join(["%s"] * len(columns))})
        ON DUPLICATE KEY UPDATE {update_clause}
        """,
        values,
    )
    cursor.execute(
        f"SELECT * FROM {quote_mysql_ident(persona_table)} WHERE user_key = %s",
        (merged_persona["user_key"],),
    )
    return cursor.fetchone()


def insert_observations(
    cursor,
    observation_table: str,
    user_key: str,
    persona_id,
    source_type: str,
    confidence_score,
    evidence_text,
    conversation_ref,
    field_results,
):
    for item in field_results:
        cursor.execute(
            f"""
            INSERT INTO {quote_mysql_ident(observation_table)}
              (user_key, persona_id, field_name, field_value, source_type, confidence_score,
               evidence_text, conversation_ref, action_type, applied_to_persona, applied_to_profile, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_key,
                persona_id,
                item["field_name"],
                item["new_value"],
                source_type,
                confidence_score,
                evidence_text,
                conversation_ref,
                item["action_type"],
                1 if item["applied_to_persona"] else 0,
                0,
                now_string(),
            ),
        )


def upsert_profile(cursor, profile_table: str, payload, profile_id):
    cursor.execute(
        f"SELECT * FROM {quote_mysql_ident(profile_table)} WHERE id = %s",
        (profile_id,),
    )
    existing = cursor.fetchone()
    if existing is None:
        cursor.execute(
            f"""
            INSERT INTO {quote_mysql_ident(profile_table)}
              (id, name, profile_status, verified_level, source_channel, last_active_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                profile_id,
                payload["name"],
                payload["profile_status"],
                payload["verified_level"],
                payload["source_channel"],
                payload["last_active_at"],
            ),
        )
        existing = {}

    update_columns = [column for column, value in payload.items() if value is not None]
    cursor.execute(
        f"""
        UPDATE {quote_mysql_ident(profile_table)}
        SET {", ".join(f"{quote_mysql_ident(column)} = %s" for column in update_columns)}
        WHERE id = %s
        """,
        [payload[column] for column in update_columns] + [profile_id],
    )


def allocate_profile_id(cursor, profile_table: str) -> int:
    cursor.execute(f"SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM {quote_mysql_ident(profile_table)}")
    row = cursor.fetchone()
    return int(row["next_id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert persona memory from a structured patch and optionally sync to profiles.")
    parser.add_argument("--source", default=None, help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE or local her DB.")
    parser.add_argument("--persona-table", default=DEFAULT_PERSONA_TABLE)
    parser.add_argument("--observation-table", default=DEFAULT_OBSERVATION_TABLE)
    parser.add_argument("--profile-table", default=None, help="Override the profile table name.")
    parser.add_argument("--user-key", required=True, help="Stable user identifier.")
    parser.add_argument("--profile-id", type=int, help="Explicit profile id to bind.")
    parser.add_argument("--display-name", help="Public display name.")
    parser.add_argument("--source-type", choices=["explicit", "strong_inference", "weak_inference"], required=True)
    parser.add_argument("--confidence-score", type=int, default=None)
    parser.add_argument("--evidence-text", default=None)
    parser.add_argument("--conversation-ref", default=None)
    parser.add_argument("--patch-json", default=None)
    parser.add_argument("--patch-file", default=None)
    parser.add_argument("--sync-profile", action="store_true", help="Also sync the merged persona into profiles.")
    args = parser.parse_args()

    patch = parse_patch_json(raw_json=args.patch_json, patch_file=args.patch_file)
    if args.profile_id is not None:
        patch.setdefault("profile_id", args.profile_id)
    if args.display_name:
        patch.setdefault("display_name", args.display_name)
    normalized_patch = normalize_patch(patch)

    config = parse_mysql_source(args.source)
    profile_table = args.profile_table or config["table"]
    conn = mysql_connect(args.source)
    try:
        with conn.cursor() as cursor:
            existing = fetch_persona(cursor, args.persona_table, args.user_key)
            base = dict(existing or {})
            base["user_key"] = args.user_key
            merged, field_results = merge_persona(base, normalized_patch, args.source_type)
            merged["user_key"] = args.user_key
            saved_persona = upsert_persona(cursor, args.persona_table, merged)
            insert_observations(
                cursor=cursor,
                observation_table=args.observation_table,
                user_key=args.user_key,
                persona_id=saved_persona["id"],
                source_type=args.source_type,
                confidence_score=args.confidence_score,
                evidence_text=args.evidence_text,
                conversation_ref=args.conversation_ref,
                field_results=field_results,
            )

            if args.sync_profile and args.source_type != "weak_inference":
                profile_id = saved_persona.get("profile_id")
                if profile_id is None:
                    profile_id = allocate_profile_id(cursor, profile_table)
                    cursor.execute(
                        f"UPDATE {quote_mysql_ident(args.persona_table)} SET profile_id = %s WHERE id = %s",
                        (profile_id, saved_persona["id"]),
                    )
                    saved_persona["profile_id"] = profile_id
                cursor.execute(
                    f"SELECT * FROM {quote_mysql_ident(profile_table)} WHERE id = %s",
                    (profile_id,),
                )
                existing_profile = cursor.fetchone() or {}
                persona_for_profile = dict(saved_persona)
                persona_for_profile["user_key"] = args.user_key
                payload = build_profile_payload(persona_for_profile, existing_profile=existing_profile)
                upsert_profile(cursor, profile_table, payload, profile_id)

        conn.commit()
    finally:
        conn.close()

    print(
        json.dumps(
            {
                "user_key": args.user_key,
                "source_type": args.source_type,
                "applied_fields": [item for item in field_results if item["applied_to_persona"]],
                "skipped_fields": [item for item in field_results if not item["applied_to_persona"]],
                "synced_profile": bool(args.sync_profile and args.source_type != "weak_inference"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

