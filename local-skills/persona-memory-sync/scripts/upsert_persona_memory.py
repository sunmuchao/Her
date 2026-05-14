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
    DEFAULT_OBSERVATION_TABLE,
    DEFAULT_PERSONA_TABLE,
    UpsertPersonaMemoryRequest,
    execute_upsert_persona_memory,
    parse_patch_json,
)

def main() -> None:
    parser = argparse.ArgumentParser(description="Upsert persona memory from a structured patch and optionally sync to profiles.")
    parser.add_argument("--source", default=None, help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE.")
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
    result = execute_upsert_persona_memory(
        UpsertPersonaMemoryRequest(
            source=args.source,
            user_key=args.user_key,
            source_type=args.source_type,
            patch=patch,
            persona_table=args.persona_table,
            observation_table=args.observation_table,
            profile_table=args.profile_table,
            confidence_score=args.confidence_score,
            evidence_text=args.evidence_text,
            conversation_ref=args.conversation_ref,
            sync_profile=args.sync_profile,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
