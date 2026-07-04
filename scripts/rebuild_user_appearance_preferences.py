#!/usr/bin/env python3
"""按用户批量重建外貌偏好。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[1]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    from dotenv import load_dotenv

    load_dotenv(repo_root / ".env")
except ImportError:
    pass

from match_domain.appearance_features import backfill_user_appearance_preferences


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 user_key 批量重建 user_appearance_preferences")
    parser.add_argument(
        "--persona-source",
        default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or os.environ.get("HER_PERSONA_DB") or "",
        help="persona MySQL DSN",
    )
    parser.add_argument(
        "--user-key",
        action="append",
        default=[],
        help="要重建的 user_key，支持多次传入",
    )
    parser.add_argument("--scene", default="discovery", help="只重建某个 scene 的历史事件")
    parser.add_argument("--event-limit", type=int, default=200, help="每个用户最多读取多少条事件")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    persona_source = str(args.persona_source or "").strip()
    if not persona_source:
        raise SystemExit("missing --persona-source or PERSONA_MEMORY_MYSQL_SOURCE")
    result = backfill_user_appearance_preferences(
        source_dsn=persona_source,
        user_keys=args.user_key,
        scene=str(args.scene or "").strip() or None,
        event_limit=max(1, int(args.event_limit or 200)),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("saved") else 1


if __name__ == "__main__":
    raise SystemExit(main())
