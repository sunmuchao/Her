#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from persona_memory_sync.persona_memory_engine import (
    DEFAULT_PERSONA_TABLE,
    RenderPublicProfileRequest,
    execute_render_public_profile,
)

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

    try:
        output = execute_render_public_profile(
            RenderPublicProfileRequest(
                source=args.source,
                user_key=args.user_key,
                profile_id=args.profile_id,
                persona_table=args.persona_table,
                profile_table=args.profile_table,
                write_profile=args.write_profile,
            )
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
