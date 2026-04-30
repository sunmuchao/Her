#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

from persona_memory_lib import (
    DEFAULT_PERSONA_TABLE,
    sync_persona_profile,
    parse_mysql_source,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync a saved user persona into the internal profiles table.")
    parser.add_argument("--source", default=None, help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE.")
    parser.add_argument("--persona-table", default=DEFAULT_PERSONA_TABLE)
    parser.add_argument("--profile-table", default=None, help="Override the profile table name.")
    parser.add_argument("--user-key", default=None)
    parser.add_argument("--profile-id", type=int, default=None)
    args = parser.parse_args()

    if not args.user_key and args.profile_id is None:
        raise SystemExit("Provide --user-key or --profile-id.")

    config = parse_mysql_source(args.source)
    profile_table = args.profile_table or config["table"]
    try:
        summary = sync_persona_profile(
            source=args.source,
            persona_table=args.persona_table,
            profile_table=profile_table,
            user_key=args.user_key,
            profile_id=args.profile_id,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
