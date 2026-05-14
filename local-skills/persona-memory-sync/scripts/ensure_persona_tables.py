#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from persona_memory_sync.persona_memory_lib import (
    DEFAULT_OBSERVATION_TABLE,
    DEFAULT_PERSONA_TABLE,
    DEFAULT_PUBLIC_VIEW,
    mysql_connect,
)
from persona_memory_sync.schema_tools import ensure_persona_schema


def main() -> None:
    parser = argparse.ArgumentParser(description="Create persona memory tables and extend profiles for internal/public sync.")
    parser.add_argument("--source", default=None, help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE.")
    parser.add_argument("--persona-table", default=DEFAULT_PERSONA_TABLE)
    parser.add_argument("--observation-table", default=DEFAULT_OBSERVATION_TABLE)
    parser.add_argument("--profile-table", default=None, help="Override the profile table name.")
    parser.add_argument("--public-view", default=DEFAULT_PUBLIC_VIEW)
    args = parser.parse_args()

    conn = mysql_connect(args.source)
    try:
        result = ensure_persona_schema(
            conn,
            source=args.source,
            persona_table=args.persona_table,
            observation_table=args.observation_table,
            profile_table=args.profile_table,
            public_view=args.public_view,
        )
    finally:
        conn.close()

    print(f"persona_table={result['persona_table']}")
    print(f"observation_table={result['observation_table']}")
    print(f"profile_table={result['profile_table']}")
    print(f"public_view={result['public_view']}")
    if result["created_profile_columns"]:
        print("created_profile_columns=" + ",".join(result["created_profile_columns"]))
    else:
        print("created_profile_columns=")


if __name__ == "__main__":
    main()
