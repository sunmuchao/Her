#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from persona_memory_lib import (
    DEFAULT_PERSONA_TABLE,
    build_profile_payload,
    mysql_connect,
    parse_mysql_source,
    quote_mysql_ident,
)


def allocate_profile_id(cursor, profile_table: str) -> int:
    cursor.execute(f"SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM {quote_mysql_ident(profile_table)}")
    row = cursor.fetchone()
    return int(row["next_id"])


def fetch_persona(cursor, persona_table: str, user_key=None, profile_id=None):
    if user_key:
        cursor.execute(
            f"SELECT * FROM {quote_mysql_ident(persona_table)} WHERE user_key = %s",
            (user_key,),
        )
        return cursor.fetchone()
    cursor.execute(
        f"SELECT * FROM {quote_mysql_ident(persona_table)} WHERE profile_id = %s",
        (profile_id,),
    )
    return cursor.fetchone()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync a saved user persona into the internal profiles table.")
    parser.add_argument("--source", default=None, help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE or local her DB.")
    parser.add_argument("--persona-table", default=DEFAULT_PERSONA_TABLE)
    parser.add_argument("--profile-table", default=None, help="Override the profile table name.")
    parser.add_argument("--user-key", default=None)
    parser.add_argument("--profile-id", type=int, default=None)
    args = parser.parse_args()

    if not args.user_key and args.profile_id is None:
        raise SystemExit("Provide --user-key or --profile-id.")

    config = parse_mysql_source(args.source)
    profile_table = args.profile_table or config["table"]
    conn = mysql_connect(args.source)
    summary = {}
    try:
        with conn.cursor() as cursor:
            persona = fetch_persona(cursor, args.persona_table, user_key=args.user_key, profile_id=args.profile_id)
            if not persona:
                raise SystemExit("Persona not found.")

            profile_id = persona.get("profile_id") or args.profile_id
            if profile_id is None:
                profile_id = allocate_profile_id(cursor, profile_table)
                cursor.execute(
                    f"UPDATE {quote_mysql_ident(args.persona_table)} SET profile_id = %s WHERE id = %s",
                    (profile_id, persona["id"]),
                )
                persona["profile_id"] = profile_id

            cursor.execute(
                f"SELECT * FROM {quote_mysql_ident(profile_table)} WHERE id = %s",
                (profile_id,),
            )
            existing_profile = cursor.fetchone()

            payload = build_profile_payload(persona, existing_profile=existing_profile or {})
            if existing_profile is None:
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
                existing_profile = {}

            update_columns = [column for column, value in payload.items() if value is not None]
            cursor.execute(
                f"""
                UPDATE {quote_mysql_ident(profile_table)}
                SET {", ".join(f"{quote_mysql_ident(column)} = %s" for column in update_columns)}
                WHERE id = %s
                """,
                [payload[column] for column in update_columns] + [profile_id],
            )

            summary = {
                "user_key": persona["user_key"],
                "profile_id": profile_id,
                "updated_columns": update_columns,
                "public_personality": payload.get("public_personality"),
                "public_values": payload.get("public_values"),
                "public_notes": payload.get("public_notes"),
            }

        conn.commit()
    finally:
        conn.close()

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

