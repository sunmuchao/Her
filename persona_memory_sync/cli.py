"""Console entrypoints for the packaged persona-memory-sync skill."""

from __future__ import annotations

import argparse
import json
from typing import Any

from .persona_memory_engine import (
    DEFAULT_OBSERVATION_TABLE,
    DEFAULT_PERSONA_TABLE,
    RenderPublicProfileRequest,
    SyncPersonaProfileRequest,
    UpsertPersonaMemoryRequest,
    execute_render_public_profile,
    execute_sync_persona_profile,
    execute_upsert_persona_memory,
    parse_patch_json,
)
from .persona_memory_lib import DEFAULT_PUBLIC_VIEW, mysql_connect
from .schema_tools import ensure_persona_schema


def run_ensure_schema(
    *,
    source: str | None,
    persona_table: str = DEFAULT_PERSONA_TABLE,
    observation_table: str = DEFAULT_OBSERVATION_TABLE,
    profile_table: str | None = None,
    public_view: str = DEFAULT_PUBLIC_VIEW,
) -> dict[str, Any]:
    conn = mysql_connect(source)
    try:
        return ensure_persona_schema(
            conn,
            source=source,
            persona_table=persona_table,
            observation_table=observation_table,
            profile_table=profile_table,
            public_view=public_view,
        )
    finally:
        conn.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persona memory CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ensure_schema = subparsers.add_parser("ensure-schema", help="Create or validate persona schema tables.")
    ensure_schema.add_argument("--source", default=None, help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE.")
    ensure_schema.add_argument("--persona-table", default=DEFAULT_PERSONA_TABLE)
    ensure_schema.add_argument("--observation-table", default=DEFAULT_OBSERVATION_TABLE)
    ensure_schema.add_argument("--profile-table", default=None, help="Override the profile table name.")
    ensure_schema.add_argument("--public-view", default=DEFAULT_PUBLIC_VIEW)

    upsert = subparsers.add_parser("upsert", help="Upsert persona memory from a structured patch.")
    upsert.add_argument("--source", default=None, help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE.")
    upsert.add_argument("--persona-table", default=DEFAULT_PERSONA_TABLE)
    upsert.add_argument("--observation-table", default=DEFAULT_OBSERVATION_TABLE)
    upsert.add_argument("--profile-table", default=None, help="Override the profile table name.")
    upsert.add_argument("--user-key", required=True, help="Stable user identifier.")
    upsert.add_argument("--profile-id", type=int, help="Explicit profile id to bind.")
    upsert.add_argument("--display-name", help="Public display name.")
    upsert.add_argument("--source-type", choices=["explicit", "strong_inference", "weak_inference"], required=True)
    upsert.add_argument("--confidence-score", type=int, default=None)
    upsert.add_argument("--evidence-text", default=None)
    upsert.add_argument("--conversation-ref", default=None)
    upsert.add_argument("--patch-json", default=None)
    upsert.add_argument("--patch-file", default=None)
    upsert.add_argument("--sync-profile", action="store_true", help="Also sync the merged persona into profiles.")

    sync_profile = subparsers.add_parser("sync-profile", help="Sync a saved persona into profiles.")
    sync_profile.add_argument("--source", default=None, help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE.")
    sync_profile.add_argument("--persona-table", default=DEFAULT_PERSONA_TABLE)
    sync_profile.add_argument("--profile-table", default=None, help="Override the profile table name.")
    sync_profile.add_argument("--user-key", default=None)
    sync_profile.add_argument("--profile-id", type=int, default=None)

    render_public = subparsers.add_parser("render-public", help="Render or write the public-safe profile view.")
    render_public.add_argument("--source", default=None, help="MySQL DSN. Defaults to PERSONA_MEMORY_MYSQL_SOURCE.")
    render_public.add_argument("--persona-table", default=DEFAULT_PERSONA_TABLE)
    render_public.add_argument("--profile-table", default=None, help="Override the profile table name.")
    render_public.add_argument("--user-key", default=None)
    render_public.add_argument("--profile-id", type=int, default=None)
    render_public.add_argument("--write-profile", action="store_true", help="Write public fields back into profiles.")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "ensure-schema":
        result = run_ensure_schema(
            source=args.source,
            persona_table=args.persona_table,
            observation_table=args.observation_table,
            profile_table=args.profile_table,
            public_view=args.public_view,
        )
    elif args.command == "upsert":
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
    elif args.command == "sync-profile":
        if not args.user_key and args.profile_id is None:
            raise SystemExit("Provide --user-key or --profile-id.")
        result = execute_sync_persona_profile(
            SyncPersonaProfileRequest(
                source=args.source,
                user_key=args.user_key,
                profile_id=args.profile_id,
                persona_table=args.persona_table,
                profile_table=args.profile_table,
            )
        )
    else:
        if not args.user_key and args.profile_id is None:
            raise SystemExit("Provide --user-key or --profile-id.")
        result = execute_render_public_profile(
            RenderPublicProfileRequest(
                source=args.source,
                user_key=args.user_key,
                profile_id=args.profile_id,
                persona_table=args.persona_table,
                profile_table=args.profile_table,
                write_profile=args.write_profile,
            )
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))


__all__ = ["main", "run_ensure_schema"]


if __name__ == "__main__":
    main()
