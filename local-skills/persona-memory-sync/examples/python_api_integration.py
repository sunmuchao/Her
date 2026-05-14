#!/usr/bin/env python3

"""Minimal outer-system integration example for persona-memory-sync.

This file stays outside the sync engine itself. It shows the product-layer
shape:

1. Load a memory update event from your own system.
2. Call persona-memory-sync as a pure write/sync dependency.
3. Decide downstream actions such as review, moderation, or event logging.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path


def ensure_repo_root_on_path() -> Path:
    import sys

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


REPO_ROOT = ensure_repo_root_on_path()

from persona_memory_sync import render_public_profile, upsert_persona_memory  # noqa: E402


def build_demo_memory_update() -> dict:
    return {
        "event_id": "memory-update-1001",
        "user_key": "demo-user",
        "source_type": "explicit",
        "patch": {
            "self_city": "上海",
            "self_relationship_goal": "认真恋爱",
            "preferred_traits": "沟通顺畅,情绪稳定",
        },
        "sync_profile": True,
        "evidence_text": "用户在本轮对话中明确提到现居上海，认真恋爱，偏好沟通顺畅和情绪稳定。",
        "conversation_ref": "conversation/demo/1001",
    }


def build_sync_batch(memory_update: dict, upsert_result: dict, public_profile: dict | None = None) -> dict:
    return {
        "event_id": memory_update["event_id"],
        "user_key": memory_update["user_key"],
        "synced_at": datetime.now().isoformat(timespec="seconds"),
        "source_type": memory_update["source_type"],
        "upsert_result": upsert_result,
        "public_profile": public_profile or {},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Example outer-system caller for the persona-memory-sync Python API.",
    )
    parser.add_argument(
        "--source",
        default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE"),
        help=(
            "MySQL DSN such as mysql://user:pass@host:3306/db?table=profiles. "
            "Defaults to PERSONA_MEMORY_MYSQL_SOURCE."
        ),
    )
    parser.add_argument(
        "--render-public",
        action="store_true",
        help="Also render the public-safe profile after upsert.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.source:
        raise SystemExit(
            "Pass --source mysql://user:pass@host:3306/db?table=profiles "
            "or set PERSONA_MEMORY_MYSQL_SOURCE first."
        )

    memory_update = build_demo_memory_update()
    upsert_result = upsert_persona_memory(
        {
            **memory_update,
            "source": args.source,
        }
    )

    public_profile = None
    if args.render_public:
        public_profile = render_public_profile(
            {
                "source": args.source,
                "user_key": memory_update["user_key"],
                "write_profile": True,
            }
        )

    sync_batch = build_sync_batch(memory_update, upsert_result, public_profile)
    print(json.dumps(sync_batch, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
