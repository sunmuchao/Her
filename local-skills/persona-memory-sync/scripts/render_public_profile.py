#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from persona_memory_lib import (
    DEFAULT_PERSONA_TABLE,
    build_profile_payload,
    build_public_profile,
    mysql_connect,
    parse_mysql_source,
    quote_mysql_ident,
)


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
    parser = argparse.ArgumentParser(description="Preview or refresh the public-safe profile rendering.")
    parser.add_argument("--source", default=None, help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE.")
    parser.add_argument("--persona-table", default=DEFAULT_PERSONA_TABLE)
    parser.add_argument("--profile-table", default=None, help="Override the profile table name.")
    parser.add_argument("--user-key", default=None)
    parser.add_argument("--profile-id", type=int, default=None)
    parser.add_argument("--write-profile", action="store_true", help="Write public_* and compatibility text fields back into profiles.")
    args = parser.parse_args()

    if not args.user_key and args.profile_id is None:
        raise SystemExit("Provide --user-key or --profile-id.")

    config = parse_mysql_source(args.source)
    profile_table = args.profile_table or config["table"]
    conn = mysql_connect(args.source)
    output = {}
    try:
        with conn.cursor() as cursor:
            persona = fetch_persona(cursor, args.persona_table, user_key=args.user_key, profile_id=args.profile_id)
            if not persona:
                raise SystemExit("Persona not found.")
            public_payload = build_public_profile(persona)
            output = {
                "user_key": persona["user_key"],
                "profile_id": persona.get("profile_id"),
                **public_payload,
            }
            if args.write_profile and persona.get("profile_id") is not None:
                cursor.execute(
                    f"SELECT * FROM {quote_mysql_ident(profile_table)} WHERE id = %s",
                    (persona["profile_id"],),
                )
                existing_profile = cursor.fetchone() or {}
                profile_payload = build_profile_payload(persona, existing_profile=existing_profile)
                update_columns = [
                    "public_personality",
                    "public_values",
                    "public_notes",
                    "personality",
                    "values",
                    "notes",
                ]
                cursor.execute(
                    f"""
                    UPDATE {quote_mysql_ident(profile_table)}
                    SET {", ".join(f"{quote_mysql_ident(column)} = %s" for column in update_columns)}
                    WHERE id = %s
                    """,
                    [profile_payload[column] for column in update_columns] + [persona["profile_id"]],
                )
        conn.commit()
    finally:
        conn.close()

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
