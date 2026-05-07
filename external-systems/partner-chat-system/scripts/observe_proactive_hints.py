#!/usr/bin/env python3
"""Replay canned dyadic transcripts and inspect proactive assistant hint behavior."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path


def _load_repo_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve()
    for p in (here.parent, *here.parents):
        if (p / "match_domain").is_dir() and (p / "pyproject.toml").is_file():
            env = p / ".env"
            if env.is_file():
                load_dotenv(env, override=True)
            return


_load_repo_dotenv()

PARTNER_CHAT_ROOT = Path(__file__).resolve().parents[1]
if str(PARTNER_CHAT_ROOT) not in sys.path:
    sys.path.insert(0, str(PARTNER_CHAT_ROOT))

from chat_system import assistant_proactive_hint, get_or_create_thread, post_message  # noqa: E402
from chat_system.service import VIS_DYADIC  # noqa: E402
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN, connect_db, initialize_database, reset_all_tables  # noqa: E402


TRANSCRIPTS: dict[str, list[tuple[str, str]]] = {
    "normal_match": [
        (
            "user-a",
            "你好，刚看到你的资料，感觉你还挺有自己节奏的。你平时下班之后一般会怎么放松？",
        ),
        (
            "user-b",
            "我一般会找家安静点的咖啡店坐一会儿，或者回家做点吃的，顺手看看展讯之类的。你呢，下班后会怎么切换状态？",
        ),
        (
            "user-a",
            "还挺巧，我也会靠咖啡续命，不过工作日一般是先走一走清空下脑子，或者找朋友打会儿羽毛球。要是那天不太累，也会顺手看看最近有没有想去的展。",
        ),
        (
            "user-b",
            "那还挺像的，先走一走确实比直接瘫着更能缓过来。羽毛球我不算会打，最近如果有你觉得不错的展，也可以推荐我看看。",
        ),
        (
            "user-a",
            "行，最近要是碰到不错的我可以发你，不过我看展也比较随缘，主要看当周有没有想看的主题。你平时会偏喜欢哪一类，艺术类、摄影类，还是设计相关的？",
        ),
        (
            "user-b",
            "我会偏摄影和设计相关一点，艺术类如果主题有意思我也会去。可能跟工作有关系，看到做得好的视觉和策展会忍不住多看一会儿。",
        ),
    ],
    "mild_cold_v1": [
        (
            "user-a",
            "你好，刚看到你的资料，感觉你还挺有自己节奏的。你平时下班之后一般会怎么放松？",
        ),
        (
            "user-b",
            "我一般会找家安静点的咖啡店坐一会儿，或者回家做点吃的，顺手看看展讯之类的。你呢，下班后会怎么切换状态？",
        ),
        (
            "user-a",
            "还挺巧，我也会靠咖啡续命，不过工作日一般是先走一走清空下脑子，或者找朋友打会儿羽毛球。要是那天不太累，也会顺手看看最近有没有想去的展。",
        ),
        ("user-b", "嗯，先走一走是会好一点。羽毛球我不太会。"),
        ("user-a", "哈哈，那确实比直接瘫着强一点。你平时会偏喜欢哪类展，摄影、设计，还是更综合一点的？"),
        ("user-b", "设计和摄影吧。看主题。"),
        ("user-a", "那还挺巧的，我也更容易看进去这两类。你是工作也偏这方面吗？"),
        ("user-b", "算是吧，我做品牌设计。"),
    ],
    "mild_cold_v2": [
        (
            "user-a",
            "你好，刚看到你的资料，感觉你还挺有自己节奏的。你平时下班之后一般会怎么放松？",
        ),
        (
            "user-b",
            "我一般会找家安静点的咖啡店坐一会儿，或者回家做点吃的，顺手看看展讯之类的。你呢，下班后会怎么切换状态？",
        ),
        (
            "user-a",
            "还挺巧，我也会靠咖啡续命，不过工作日一般是先走一走清空下脑子，或者找朋友打会儿羽毛球。要是那天不太累，也会顺手看看最近有没有想去的展。",
        ),
        ("user-b", "嗯，还行。羽毛球我不太会。"),
        ("user-a", "哈哈，那也正常。你平时会偏喜欢哪类展，摄影、设计，还是更综合一点的？"),
        ("user-b", "设计吧。"),
        ("user-a", "那还挺巧的，我也更容易看进去这两类。你是工作也偏这方面吗？"),
        ("user-b", "算是。"),
        ("user-a", "是设计相关吗？"),
        ("user-b", "嗯，品牌。"),
    ],
    "mild_cold_recover": [
        (
            "user-a",
            "你好，刚看到你的资料，感觉你还挺有自己节奏的。你平时下班之后一般会怎么放松？",
        ),
        (
            "user-b",
            "我一般会找家安静点的咖啡店坐一会儿，或者回家做点吃的，顺手看看展讯之类的。你呢，下班后会怎么切换状态？",
        ),
        (
            "user-a",
            "还挺巧，我也会靠咖啡续命，不过工作日一般是先走一走清空下脑子，或者找朋友打会儿羽毛球。要是那天不太累，也会顺手看看最近有没有想去的展。",
        ),
        ("user-b", "嗯，先走一走会好一点。"),
        ("user-a", "我也是，不然脑子还停在工作里。你平时会偏喜欢哪类展，摄影、设计，还是更综合一点的？"),
        ("user-b", "设计和摄影吧，不过要看主题。"),
        ("user-a", "那还挺巧的，我也差不多。你是工作也偏这方面吗？"),
        ("user-b", "对，我做品牌设计，所以看这些会多留意一点。"),
    ],
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=sorted(TRANSCRIPTS),
        default="mild_cold_v2",
        help="Which built-in transcript to replay.",
    )
    parser.add_argument(
        "--dsn",
        default=DEFAULT_CHAT_TEST_MYSQL_DSN,
        help="Chat DB DSN. Defaults to PARTNER_CHAT_TEST_DB.",
    )
    parser.add_argument(
        "--base-time",
        default="2026-05-07T21:00:00",
        help="Base message timestamp in ISO 8601 format.",
    )
    return parser.parse_args()


def _next_speaker(author_id: str) -> str:
    return "user-b" if author_id == "user-a" else "user-a"


def main() -> int:
    args = _parse_args()
    transcript = TRANSCRIPTS[args.scenario]
    base_time = datetime.fromisoformat(args.base_time)

    conn = connect_db(args.dsn)
    try:
        initialize_database(conn)
        reset_all_tables(conn)

        thread = get_or_create_thread(
            conn,
            case_id=f"observe-{args.scenario}",
            relation_key=f"{args.scenario}-a|b",
            participant_a_id="user-a",
            participant_b_id="user-b",
            now=base_time,
        )

        observations: list[dict[str, object]] = []
        first_hint_turn: int | None = None

        for idx, (author_id, body) in enumerate(transcript, start=1):
            post_message(
                conn,
                thread["thread_id"],
                author_id,
                body,
                visibility=VIS_DYADIC,
                now=base_time + timedelta(minutes=idx),
            )
            if idx == len(transcript):
                break

            hint = assistant_proactive_hint(
                conn,
                thread["thread_id"],
                _next_speaker(author_id),
                now=base_time + timedelta(minutes=idx, seconds=10),
            )
            route = dict(hint.get("assistant_route_decision") or {})
            event = dict(hint.get("assistant_hint_event") or {})
            guidance = dict(hint.get("assistant_guidance") or {})
            row = {
                "after_turn": idx,
                "next_speaker": _next_speaker(author_id),
                "last_message": body,
                "hint_posted": bool(hint.get("hint_posted")),
                "interaction_mode": route.get("interaction_mode"),
                "mutual_intent_assessment": route.get("mutual_intent_assessment"),
                "route_reason": route.get("reason"),
                "trigger_type": event.get("trigger_type"),
                "suppression_reason": event.get("suppression_reason"),
                "guidance_source": guidance.get("guidance_source"),
                "guidance_mode": guidance.get("interaction_mode"),
                "guidance_advice": guidance.get("advice"),
                "assistant_latency_ms": hint.get("assistant_latency_ms"),
            }
            observations.append(row)
            if row["hint_posted"] and first_hint_turn is None:
                first_hint_turn = idx

        payload = {
            "scenario": args.scenario,
            "thread_id": thread["thread_id"],
            "message_turns": len(transcript),
            "first_hint_turn": first_hint_turn,
            "observations": observations,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
