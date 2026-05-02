#!/usr/bin/env python3

"""Run a deterministic Phase 3 scenario: no match first, then supplement a candidate later."""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime, timedelta


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from recommendation_system import (  # noqa: E402
    connect_db,
    deliver_in_app_recommendations,
    handle_opt_in_decision,
    initialize_database,
    list_in_app_cards,
    list_recommendations_for_subscription,
    refresh_due_subscriptions,
    run_search_session,
)


def build_candidate() -> dict[str, object]:
    return {
        "id": 30010,
        "name": "周砚川",
        "score": 67,
        "fit_score": 55,
        "confidence_score": 12,
        "risk_score": 0,
        "matched_on": [
            "城市 无锡",
            "目标 结婚导向",
            "情绪稳定",
            "不对婚史设偏见",
        ],
        "reciprocal_on": [
            "年龄在对方偏好区间",
            "教育符合偏好",
        ],
        "missing_fields": [],
        "self_profile_gaps": [],
        "risk_flags": [],
        "match_evidence": [],
        "follow_up_questions": [
            "确认对再婚现实和长期关系推进节奏的看法。",
            "确认平时见面频率和城市半径。",
        ],
        "photo_preview": [],
        "profile": {
            "age": 36,
            "city": "无锡",
            "job": "法务",
            "relationship_goal": "结婚导向",
            "marital_status": "未婚",
            "smoking": "否",
            "drinking": "偶尔",
        },
    }


def build_persona() -> dict[str, object]:
    return {
        "requester_id": 88001,
        "title": "无锡稳定认真关系持续留意",
        "criteria": {
            "gender": "男",
            "cities": ["无锡", "苏州"],
            "relationship_goals": ["认真恋爱", "结婚导向"],
            "must_have": ["情绪稳定", "责任心", "稳定工作", "愿意沟通"],
            "must_not_have": ["抽烟严重", "暧昧不清", "失联冷处理"],
            "verified_level_min": "photo",
            "photo_count_min": 2,
        },
        "self_profile": {
            "age": 29,
            "city": "无锡",
            "height": 165,
            "education": "硕士",
            "income_wan": 24,
            "marital_status": "未婚",
            "has_children": 0,
        },
        "roleplay_brief": (
            "29岁无锡女生，医院药师，认真找稳定长期关系。"
            "看重情绪稳定、责任心、三观正、边界清楚和沟通能力；"
            "原则上不接受长期异地，不喜欢拉扯和失联。"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a no-match then notify roleplay scenario.")
    parser.add_argument(
        "--db",
        default="/tmp/partner-roleplay-phase3.sqlite3",
        help="SQLite database path for the recommendation system run.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON output file. Prints to stdout when omitted.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = pathlib.Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    persona = build_persona()
    candidate_pool: list[dict[str, object]] = []

    def search_runner(**_: object) -> dict[str, object]:
        return {
            "has_match": bool(candidate_pool),
            "result_count": len(candidate_pool),
            "results": list(candidate_pool),
            "fallback_results": [],
        }

    conn = connect_db(db_path)
    initialize_database(conn)
    try:
        first_search_at = datetime(2026, 5, 2, 9, 0, 0)
        session = run_search_session(
            source="mock://roleplay/no-match-then-notify",
            criteria=persona["criteria"],
            self_profile=persona["self_profile"],
            limit=5,
            search_runner=search_runner,
        )

        decision = handle_opt_in_decision(
            conn,
            requester_id=int(persona["requester_id"]),
            search_session=session,
            user_opted_in=True,
            title=str(persona["title"]),
            quiet_hours_start=23,
            quiet_hours_end=8,
            refresh_interval_hours=24,
        )

        candidate_pool.append(build_candidate())

        refresh_summaries = refresh_due_subscriptions(
            conn,
            now=first_search_at + timedelta(days=1),
            search_runner=search_runner,
        )
        delivery_summary = deliver_in_app_recommendations(
            conn,
            now=first_search_at + timedelta(days=1, hours=1),
        )

        subscription = decision["subscription"]
        recommendations = list_recommendations_for_subscription(conn, subscription["subscription_id"])
        cards = list_in_app_cards(conn, requester_id=int(persona["requester_id"]))

        output = {
            "persona": persona,
            "first_search_session": session,
            "opt_in_decision": decision,
            "supplemented_candidates": candidate_pool,
            "refresh_summaries": refresh_summaries,
            "delivery_summary": delivery_summary,
            "recommendations": recommendations,
            "cards": cards,
            "record_action_hint": {
                "db": str(db_path),
                "subscription_id": subscription["subscription_id"],
                "candidate_id": candidate_pool[0]["id"],
                "allowed_actions": ["skip", "save", "direct_greet"],
            },
        }
    finally:
        conn.close()

    rendered = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        output_path = pathlib.Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
