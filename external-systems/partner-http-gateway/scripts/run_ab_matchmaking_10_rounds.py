#!/usr/bin/env python3
"""Create the A-C / B-C / A-B-C layout, then post a 10-round A/B dating chat."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from urllib import error, parse, request


DEFAULT_DIALOGUE: list[tuple[str, str]] = [
    (
        "user-a",
        "你好，很高兴认识你。我在上海做产品经理，看到你的资料感觉你应该是个挺有想法的人。",
    ),
    (
        "user-b",
        "你好呀，也很高兴认识你。谢谢你主动打招呼，我在上海做品牌市场，平时还挺喜欢和有想法的人聊天的。",
    ),
    (
        "user-a",
        "那还挺巧，我们工作上多少都算跟表达和用户打交道。你平时工作节奏会不会比较快？",
    ),
    (
        "user-b",
        "有时候会，尤其是做活动或者赶节点的时候会比较满。你们产品岗应该也经常要同时处理很多事情吧？",
    ),
    (
        "user-a",
        "是，会同时盯需求、排期和沟通，但我还算会给自己找节奏。忙完的时候我一般会去打羽毛球或者出去走走放空。",
    ),
    (
        "user-b",
        "那还挺健康的，我忙完更喜欢去喝咖啡、看展，或者在上海随便 citywalk 一下。感觉这样能把脑子重新清空。",
    ),
    (
        "user-a",
        "我也挺喜欢这种轻松一点的放松方式。要是第一次见面的话，你会更喜欢安静聊天，还是去有点氛围感的地方？",
    ),
    (
        "user-b",
        "我可能会更偏安静一点，先把人聊明白比较重要。熟一点之后再去热闹一点的地方，体验会更自然。",
    ),
    (
        "user-a",
        "我想法差不多，先相处舒服最重要。说到这里，我还挺想知道你对认真进入一段关系最看重什么？",
    ),
    (
        "user-b",
        "对我来说是稳定和真诚吧，情绪别太飘，事情上也别只会说不会做。两个人能不能把日常过踏实，我会比较在意这个。",
    ),
    (
        "user-a",
        "这个我挺认同的，关系能走长远，还是得落在具体生活里。我自己也更偏向认真稳定的节奏，而不是一开始聊得很热闹后面就散掉。",
    ),
    (
        "user-b",
        "对，我也是这种想法，所以聊天我会更看重有没有持续交流的感觉。比起一时上头，我更相信慢慢建立起来的信任感。",
    ),
    (
        "user-a",
        "那我们在这点上应该挺一致的。你会希望以后长期留在上海吗，还是会看合适的机会再决定？",
    ),
    (
        "user-b",
        "我目前还是想留在上海，工作和生活圈都在这边，也比较有熟悉感。除非以后真的遇到特别合适的人和机会，不然大方向不会变。",
    ),
    (
        "user-a",
        "我也是偏向在上海长期发展，至少这几年计划比较明确。工作之外我还挺喜欢研究吃的，所以也会自己做一点简单的菜。",
    ),
    (
        "user-b",
        "那挺加分的，我也会做一点家常菜，但不算特别厉害。相比起复杂料理，我更擅长把日常过得舒服一点。",
    ),
    (
        "user-a",
        "这其实就很难得了，生活感比花样更重要。我感觉跟你聊天挺顺的，不会有那种硬找话题的感觉。",
    ),
    (
        "user-b",
        "我也有这种感觉，至少现在聊下来是轻松的。你说话会让人觉得比较有分寸，也挺自然。",
    ),
    (
        "user-a",
        "那我们可以继续慢慢聊，看看是不是能从顺着聊发展到真正聊得来。要是这周你时间合适，后面也可以约个咖啡见一面。",
    ),
    (
        "user-b",
        "可以呀，先继续聊两天也挺好，如果感觉还是这么自然，我们再约时间见面。我对这种循序渐进的节奏会更舒服。",
    ),
]

DEFAULT_CONVERSATION_IDS = {
    "main_group": "cvt-main-group-demo-001",
    "assistant_dm_a": "cvt-assistant-dm-a-demo-001",
    "assistant_dm_b": "cvt-assistant-dm-b-demo-001",
}


def _request_json(method: str, url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with request.urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} {exc.reason}: {body}") from exc


def _build_layout(
    *,
    base_url: str,
    case_id: str,
    relation_key: str,
    participant_a_id: str,
    participant_b_id: str,
    agent_id: str,
    conversation_ids: dict[str, str],
    started_at: datetime,
) -> dict:
    url = f"{base_url}/v2/chat/cases/{parse.quote(case_id)}/assistant-layout"
    return _request_json(
        "POST",
        url,
        {
            "relation_key": relation_key,
            "participant_a_id": participant_a_id,
            "participant_b_id": participant_b_id,
            "agent_id": agent_id,
            "conversation_ids": conversation_ids,
            "now": started_at.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


def _main_group_conversation_id(layout_payload: dict) -> str:
    conversations = layout_payload.get("layout", {}).get("conversations", [])
    for item in conversations:
        metadata = item.get("metadata") or {}
        if metadata.get("layout_role") == "main_group":
            return str(item["conversation_id"])
    raise SystemExit("main_group conversation not found in layout response")


def _post_message(
    *,
    base_url: str,
    conversation_id: str,
    author_id: str,
    body: str,
    when: datetime,
) -> dict:
    url = f"{base_url}/v2/chat/conversations/{parse.quote(conversation_id)}/messages"
    return _request_json(
        "POST",
        url,
        {
            "author_id": author_id,
            "body": body,
            "now": when.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Post a 10-round A/B matchmaking conversation.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--case-id", default="case-demo-10-rounds")
    parser.add_argument("--relation-key", default="rel-demo-10-rounds")
    parser.add_argument("--participant-a-id", default="user-a")
    parser.add_argument("--participant-b-id", default="user-b")
    parser.add_argument("--agent-id", default="agent-c")
    parser.add_argument("--start-at", default="2026-05-08 23:00:00")
    parser.add_argument("--main-group-id", default=DEFAULT_CONVERSATION_IDS["main_group"])
    parser.add_argument("--assistant-dm-a-id", default=DEFAULT_CONVERSATION_IDS["assistant_dm_a"])
    parser.add_argument("--assistant-dm-b-id", default=DEFAULT_CONVERSATION_IDS["assistant_dm_b"])
    args = parser.parse_args()

    started_at = datetime.strptime(args.start_at, "%Y-%m-%d %H:%M:%S")
    base_url = f"http://{args.host}:{args.port}"

    layout_payload = _build_layout(
        base_url=base_url,
        case_id=args.case_id,
        relation_key=args.relation_key,
        participant_a_id=args.participant_a_id,
        participant_b_id=args.participant_b_id,
        agent_id=args.agent_id,
        conversation_ids={
            "main_group": args.main_group_id,
            "assistant_dm_a": args.assistant_dm_a_id,
            "assistant_dm_b": args.assistant_dm_b_id,
        },
        started_at=started_at,
    )
    main_group_id = _main_group_conversation_id(layout_payload)

    posted: list[dict[str, str]] = []
    current_time = started_at + timedelta(minutes=1)
    for author_id, body in DEFAULT_DIALOGUE:
        response = _post_message(
            base_url=base_url,
            conversation_id=main_group_id,
            author_id=author_id,
            body=body,
            when=current_time,
        )
        posted.append(
            {
                "message_id": str(response["message"]["message_id"]),
                "author_id": author_id,
                "body": body,
            }
        )
        current_time += timedelta(minutes=1)

    print(json.dumps(
        {
            "case_id": args.case_id,
            "relation_key": args.relation_key,
            "main_group_conversation_id": main_group_id,
            "assistant_dm_a_conversation_id": args.assistant_dm_a_id,
            "assistant_dm_b_conversation_id": args.assistant_dm_b_id,
            "round_count": len(DEFAULT_DIALOGUE) // 2,
            "message_count": len(DEFAULT_DIALOGUE),
            "messages": posted,
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
