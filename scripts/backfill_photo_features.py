#!/usr/bin/env python3
"""批量回填资料照片特征与外貌向量。"""

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

from match_domain.appearance_features import backfill_profile_photo_features
from profile_service import resolve_profile_source


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="批量回填 profile_photo_features 和 appearance_profile 向量")
    parser.add_argument(
        "--persona-source",
        default=os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE") or os.environ.get("HER_PERSONA_DB") or "",
        help="persona MySQL DSN，用于写入 profile_photo_features",
    )
    parser.add_argument(
        "--profile-source",
        default=os.environ.get("HER_PROFILE_SOURCE_DSN") or "",
        help="资料库 MySQL DSN；为空时默认复用 persona-source",
    )
    parser.add_argument("--table", default="", help="资料主表名；为空时沿用 DSN 中的 table 参数")
    parser.add_argument("--photos-table", default="", help="照片表名；为空时沿用 DSN 中的 photos_table 参数")
    parser.add_argument("--where", default="", help="可选过滤条件，例如 `status = ?`")
    parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="where 参数，支持多次传入，对应 ? 占位符顺序",
    )
    parser.add_argument("--batch-size", type=int, default=200, help="每批加载资料数")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少个 profile；0 表示不限制")
    parser.add_argument("--sync-embedding", action="store_true", help="同时写 appearance_profile 向量")
    parser.add_argument("--only-missing", action="store_true", help="只补还没有 photo_features 的资料")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    persona_source = str(args.persona_source or "").strip()
    profile_source = str(args.profile_source or persona_source).strip()
    if not persona_source:
        raise SystemExit("missing --persona-source or PERSONA_MEMORY_MYSQL_SOURCE")

    resolved_profile_source, resolved_table = resolve_profile_source(profile_source, args.table or None)
    if not resolved_profile_source or not resolved_table:
        raise SystemExit("profile source/table could not be resolved")

    result = backfill_profile_photo_features(
        source_dsn=persona_source,
        profile_source_dsn=resolved_profile_source,
        source_table_name=args.table or resolved_table,
        photos_table_name=args.photos_table or None,
        where_clause=args.where,
        params=args.param,
        batch_size=args.batch_size,
        limit=args.limit or None,
        sync_embedding=bool(args.sync_embedding),
        only_missing=bool(args.only_missing),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("saved") else 1


if __name__ == "__main__":
    raise SystemExit(main())
