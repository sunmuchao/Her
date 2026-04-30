#!/usr/bin/env python3

"""Minimal external-system integration example for partner-search.

This file intentionally stays outside the matching engine itself. It shows the
product-layer shape:

1. Load a saved search and requester profile from your own system.
2. Call partner-search as a pure matching dependency.
3. Decide downstream actions such as history comparison or notification.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def ensure_skill_root_on_path() -> Path:
    skill_root = Path(__file__).resolve().parents[1]
    if str(skill_root) not in sys.path:
        sys.path.insert(0, str(skill_root))
    return skill_root


SKILL_ROOT = ensure_skill_root_on_path()

from partner_search import search_profiles  # noqa: E402


def build_demo_saved_search() -> dict:
    return {
        "subscription_id": "saved-search-1001",
        "requester_id": 70001,
        "criteria": {
            "gender": "女",
            "cities": ["无锡"],
            "relationship_goals": ["认真恋爱", "结婚导向"],
            "must_have": ["情绪稳定"],
            "prefer": ["消费观正常", "生活规律"],
            "smoking": "否",
            "verified_level_min": "photo",
            "photo_count_min": 3,
        },
    }


def build_demo_requester_profile() -> dict:
    return {
        "age": 28,
        "city": "无锡",
        "height": 178,
        "education": "本科",
        "income_wan": 40,
        "marital_status": "未婚",
        "has_children": 0,
    }


def build_recommendation_batch(saved_search: dict, response: dict) -> dict:
    candidate_ids = [item["id"] for item in response.get("results", []) if item.get("id") is not None]
    return {
        "subscription_id": saved_search["subscription_id"],
        "requester_id": saved_search["requester_id"],
        "searched_at": datetime.now().isoformat(timespec="seconds"),
        "result_count": response.get("result_count", 0),
        "top_candidate_ids": candidate_ids,
        "search_response": response,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Example outer-system caller for the partner-search Python API.",
    )
    parser.add_argument(
        "--source",
        default=os.environ.get("PARTNER_SEARCH_MYSQL_SOURCE"),
        help=(
            "MySQL DSN such as mysql://user:pass@host:3306/db?table=profiles. "
            "Defaults to PARTNER_SEARCH_MYSQL_SOURCE."
        ),
    )
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of candidates to fetch.")
    parser.add_argument(
        "--include-text",
        action="store_true",
        help="Include the human-readable text rendering alongside the structured payload.",
    )
    parser.add_argument(
        "--show-source",
        action="store_true",
        help="Include the redacted source reference in each result.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.source:
        raise SystemExit(
            "Pass --source mysql://user:pass@host:3306/db?table=profiles "
            "or set PARTNER_SEARCH_MYSQL_SOURCE first."
        )

    saved_search = build_demo_saved_search()
    requester_profile = build_demo_requester_profile()

    response = search_profiles(
        source=args.source,
        criteria=saved_search["criteria"],
        self_profile=requester_profile,
        limit=args.limit,
        include_source=args.show_source,
        include_text=args.include_text,
    )

    recommendation_batch = build_recommendation_batch(saved_search, response)

    # A real outer system would compare `top_candidate_ids` against its own
    # recommendation history before deciding whether to notify the user.
    print(json.dumps(recommendation_batch, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
