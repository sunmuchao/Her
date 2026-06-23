#!/usr/bin/env python3
"""Run a long discovery conversation and record full request/response evidence.

This script intentionally does not change business logic. It:
1. creates a real discovery session through the gateway
2. sends a long multi-turn conversation as if from a real user
3. stores raw request/response payloads
4. queries persistence evidence from MySQL
5. writes a markdown report plus a raw JSON artifact
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pymysql
import requests
from requests import exceptions as requests_exceptions

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "artifacts"
DOCS_DIR = REPO_ROOT / "docs"

GATEWAY_URL = os.environ.get("DISCOVERY_TEST_GATEWAY_URL", "http://127.0.0.1:8765").rstrip("/")
MYSQL_HOST = os.environ.get("DISCOVERY_TEST_MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("DISCOVERY_TEST_MYSQL_PORT", "3307"))
MYSQL_USER = os.environ.get("DISCOVERY_TEST_MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("DISCOVERY_TEST_MYSQL_PASSWORD", "")


@dataclass(frozen=True)
class TurnSpec:
    label: str
    user_message: str
    pause_seconds: float = 1.5


SCENARIO = [
    TurnSpec("T1", "我想认真找对象，但我现在其实有点说不清自己到底适合什么样的人。"),
    TurnSpec("T2", "先说硬条件吧，我人在无锡发展，最好对方也在无锡或者苏州，异地不是完全不行，但同城优先。"),
    TurnSpec("T3", "年龄我原来想卡在25到29，不过如果人靠谱，30到33我也可以接受。"),
    TurnSpec("T4", "我比较看重工作稳定，但不是只看编制，长期稳定、情绪稳定都重要。"),
    TurnSpec("T5", "性格上我喜欢温柔一点、真诚一点的，但也别太闷，能沟通，别让我一直猜。"),
    TurnSpec("T6", "我自己有点慢热，之前在关系里比较缺安全感，所以希望对方愿意主动表达，不要冷暴力。"),
    TurnSpec("T7", "还有一点比较现实，我不太想找烟酒都很重的人，偶尔社交喝酒能接受。"),
    TurnSpec("T8", "学历最好本科及以上，但这个不是死条件，三观和相处舒服更重要。"),
    TurnSpec("T9", "你先按这些给我看看，如果上一批太远或者太高冷，我可能会想换一批。"),
    TurnSpec("T10", "如果有一个人是无锡本地、工作稳定、愿意沟通、性格温和，这种你可以优先推。"),
    TurnSpec("T11", "对了，我自己是29岁，做产品相关，平时不抽烟，偶尔喝酒，作息算规律。"),
    TurnSpec("T12", "我家里观念比较正常，没那么催，但我确实是奔着长期关系去的，不是随便聊聊。"),
    TurnSpec("T13", "如果候选人里有人看起来太理性太冷，我大概率不太会有感觉。"),
    TurnSpec("T14", "你要是觉得我条件有冲突，也可以直接指出来，我宁愿你追问，也别给我一堆不准的结果。"),
]


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def dump_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)


def latest_assistant_message(response_json: dict[str, Any]) -> str:
    timeline = ((response_json or {}).get("view") or {}).get("timeline") or []
    for item in reversed(timeline):
        if item.get("item_type") == "assistant_message":
            return str(item.get("body") or "")
    return ""


def latest_result_groups(response_json: dict[str, Any]) -> list[dict[str, Any]]:
    timeline = ((response_json or {}).get("view") or {}).get("timeline") or []
    return [item for item in timeline if item.get("item_type") == "result_group"]


def mysql_query(db: str, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=db,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return list(cursor.fetchall())
    finally:
        conn.close()


def create_session(profile_id: int) -> dict[str, Any]:
    response = requests.post(
        f"{GATEWAY_URL}/v1/discovery/sessions",
        json={"requester_id": profile_id, "profile_id": profile_id},
        timeout=60,
    )
    return {
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "json": response.json() if response.content else None,
        "text": response.text,
    }


def send_turn(session_id: str, user_message: str) -> dict[str, Any]:
    try:
        response = requests.post(
            f"{GATEWAY_URL}/v1/discovery/sessions/{session_id}/turns",
            json={"user_message": user_message},
            timeout=45,
        )
        return {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "json": response.json() if response.content else None,
            "text": response.text,
            "error": None,
        }
    except requests_exceptions.RequestException as exc:
        return {
            "status_code": None,
            "headers": {},
            "json": None,
            "text": "",
            "error": f"{type(exc).__name__}: {exc}",
        }


def collect_evidence(session_id: str, profile_id: int) -> dict[str, Any]:
    return {
        "discovery_agent_turns": mysql_query(
            "her_discovery",
            """
            SELECT turn_id, request_kind, LEFT(user_message_text, 200) AS user_message_text,
                   search_run_id, trace_id, created_at
            FROM discovery_agent_turns
            WHERE session_id = %s
            ORDER BY turn_id ASC
            """,
            (session_id,),
        ),
        "discovery_agent_tool_calls": mysql_query(
            "her_discovery",
            """
            SELECT tool_call_id, turn_id, tool_name, status, search_run_id, trace_id, created_at,
                   LEFT(tool_args_json, 500) AS tool_args_json,
                   LEFT(tool_result_json, 500) AS tool_result_json
            FROM discovery_agent_tool_calls
            WHERE session_id = %s
            ORDER BY tool_call_id ASC
            """,
            (session_id,),
        ),
        "discovery_search_runs": mysql_query(
            "her_discovery",
            """
            SELECT search_run_id, requester_id, profile_id, source, limit_count, result_count, has_match, created_at,
                   LEFT(criteria_json, 500) AS criteria_json
            FROM discovery_search_runs
            WHERE session_id = %s
            ORDER BY search_run_id ASC
            """,
            (session_id,),
        ),
        "discovery_view_snapshots": mysql_query(
            "her_discovery",
            """
            SELECT snapshot_id, turn_id, phase, trace_id, created_at,
                   LEFT(view_json, 500) AS view_json
            FROM discovery_view_snapshots
            WHERE session_id = %s
            ORDER BY snapshot_id ASC
            """,
            (session_id,),
        ),
        "discovery_profile_update_requests": mysql_query(
            "her_discovery",
            """
            SELECT request_id, status, created_at, updated_at,
                   LEFT(proposed_patch_json, 500) AS proposed_patch_json,
                   LEFT(evidence_text, 500) AS evidence_text
            FROM discovery_profile_update_requests
            WHERE session_id = %s
            ORDER BY created_at ASC
            """,
            (session_id,),
        ),
        "discovery_agent_session_memory_items": mysql_query(
            "her_discovery",
            """
            SELECT item_id, created_at, LEFT(item_json, 500) AS item_json
            FROM discovery_agent_session_memory_items
            WHERE session_id = %s
            ORDER BY item_id ASC
            """,
            (session_id,),
        ),
        "conversation_summaries": mysql_query(
            "her",
            """
            SELECT summary_id, conversation_id, requester_id, profile_id, summary_key, summary_text,
                   vector_status, created_at, updated_at
            FROM conversation_summaries
            WHERE conversation_id = %s
            ORDER BY summary_id ASC
            """,
            (session_id,),
        ),
        "user_persona_observations": mysql_query(
            "her",
            """
            SELECT id, user_key, field_name, field_value, source_type, confidence_score,
                   conversation_ref, source_channel, applied_to_persona, applied_to_profile, created_at
            FROM user_persona_observations
            WHERE conversation_ref = %s OR user_key = %s
            ORDER BY id DESC
            LIMIT 30
            """,
            (session_id, str(profile_id)),
        ),
        "user_personas": mysql_query(
            "her",
            """
            SELECT user_key, profile_id, target_age_min, target_age_max, target_cities,
                   target_accept_long_distance, target_education_min, updated_at
            FROM user_personas
            WHERE user_key = %s
            """,
            (str(profile_id),),
        ),
    }


def build_markdown(
    *,
    started_at: str,
    profile_id: int,
    session_id: str,
    create_result: dict[str, Any],
    turns: list[dict[str, Any]],
    evidence: dict[str, Any],
    raw_json_path: Path,
    aborted: bool,
    abort_reason: str,
) -> str:
    lines: list[str] = []
    lines.append("# 发现页长时间复杂对话真实测试记录")
    lines.append("")
    lines.append(f"- 测试时间: {started_at}")
    lines.append(f"- 测试方式: 真实调用 `POST /v1/discovery/sessions` 与 `POST /v1/discovery/sessions/{{session_id}}/turns`")
    lines.append(f"- 测试用户 profile_id: `{profile_id}`")
    lines.append(f"- Session ID: `{session_id}`")
    lines.append(f"- 原始 JSON 记录: [{raw_json_path.name}]({raw_json_path})")
    lines.append("")
    lines.append("## 结论摘要")
    lines.append("")
    if aborted:
        lines.append(f"- 本次长对话未完整跑完，流程在中途终止。原因: `{abort_reason}`")
    else:
        lines.append("- 本次长对话已完整跑完。")

    search_runs = evidence.get("discovery_search_runs") or []
    tool_calls = evidence.get("discovery_agent_tool_calls") or []
    profile_updates = evidence.get("discovery_profile_update_requests") or []
    persona_obs = evidence.get("user_persona_observations") or []
    summaries = evidence.get("conversation_summaries") or []
    persona_rows = evidence.get("user_personas") or []

    lines.append(f"- 共发送 {len(turns)} 轮用户消息。")
    lines.append(f"- 共记录到 {len(search_runs)} 条 `discovery_search_runs`。")
    lines.append(f"- 共记录到 {len(tool_calls)} 条 `discovery_agent_tool_calls`。")
    lines.append(f"- `discovery_profile_update_requests` 条数: {len(profile_updates)}。")
    lines.append(f"- `conversation_summaries` 条数: {len(summaries)}。")
    lines.append(f"- `user_persona_observations` 命中条数: {len(persona_obs)}。")
    lines.append(f"- `user_personas` 命中条数: {len(persona_rows)}。")

    if not profile_updates and not persona_obs and not summaries:
        lines.append("- 画像写入侧未观察到明确新增痕迹。结合代码现状，这很可能与当前 `sync_requester_persona_memory` 被硬禁用有关。")
    elif not profile_updates:
        lines.append("- 未看到正式资料更新请求，但画像沉淀侧可能仍有摘要或 observation 写入。")

    lines.append("")
    lines.append("## 创建会话")
    lines.append("")
    lines.append("### 请求")
    lines.append("```json")
    lines.append(dump_json({"requester_id": profile_id, "profile_id": profile_id}))
    lines.append("```")
    lines.append("")
    lines.append("### 响应")
    lines.append("```json")
    lines.append(dump_json(create_result["json"]))
    lines.append("```")
    lines.append("")
    lines.append("## 多轮对话完整记录")
    lines.append("")

    for idx, item in enumerate(turns, start=1):
        lines.append(f"### 第 {idx} 轮 {item['label']}")
        lines.append("")
        lines.append("#### 用户发送")
        lines.append("```json")
        lines.append(dump_json({"user_message": item["user_message"]}))
        lines.append("```")
        lines.append("")
        lines.append("#### 系统返回")
        if item["response"]["error"]:
            lines.append(f"- 请求异常: `{item['response']['error']}`")
        else:
            lines.append("```json")
            lines.append(dump_json(item["response"]["json"]))
            lines.append("```")
        lines.append("")
        lines.append("#### 快速观察")
        lines.append(f"- HTTP 状态: `{item['response']['status_code']}`")
        lines.append(f"- Assistant 最新回复: `{item['assistant_message'][:180]}`")
        lines.append(f"- Result group 数量: {len(item['result_groups'])}")
        candidate_ids: list[int] = []
        for group in item["result_groups"]:
            for card in group.get("cards") or []:
                if card.get("profile_id") is not None:
                    candidate_ids.append(int(card["profile_id"]))
        lines.append(f"- 本轮返回候选人 ID: `{candidate_ids}`")
        lines.append("")

    lines.append("## 持久化证据")
    lines.append("")
    for key, rows in evidence.items():
        lines.append(f"### {key}")
        lines.append("")
        lines.append(f"- 记录数: {len(rows)}")
        if rows:
            lines.append("```json")
            lines.append(dump_json(rows))
            lines.append("```")
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    started_at = now_str()
    profile_id = int(os.environ.get("DISCOVERY_TEST_PROFILE_ID", "10015"))

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    create_result = create_session(profile_id)
    if create_result["status_code"] not in (200, 201):
        raise SystemExit(f"create_session failed: {create_result['status_code']} {create_result['text']}")

    session_id = str((create_result["json"] or {}).get("session", {}).get("session_id") or "").strip()
    if not session_id:
        raise SystemExit("session_id missing in create_session response")

    turns: list[dict[str, Any]] = []
    aborted = False
    abort_reason = ""
    for turn in SCENARIO:
        result = send_turn(session_id, turn.user_message)
        payload = result["json"] or {}
        turns.append(
            {
                "label": turn.label,
                "user_message": turn.user_message,
                "response": result,
                "assistant_message": latest_assistant_message(payload),
                "result_groups": latest_result_groups(payload),
                "received_at": now_str(),
            }
        )
        if result["error"]:
            aborted = True
            abort_reason = f"{turn.label} request error: {result['error']}"
            break
        if result["status_code"] != 200:
            aborted = True
            abort_reason = f"{turn.label} non-200 response: {result['status_code']} {result['text']}"
            break
        time.sleep(turn.pause_seconds)

    time.sleep(5)
    evidence = collect_evidence(session_id, profile_id)

    timestamp_slug = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_json_path = RAW_DIR / f"discovery_complex_conversation_{timestamp_slug}.json"
    report_path = DOCS_DIR / f"discovery_complex_conversation_test_{timestamp_slug}.md"

    raw_payload = {
        "meta": {
            "started_at": started_at,
            "gateway_url": GATEWAY_URL,
            "profile_id": profile_id,
            "session_id": session_id,
            "aborted": aborted,
            "abort_reason": abort_reason,
        },
        "create_session": create_result,
        "turns": turns,
        "evidence": evidence,
    }
    raw_json_path.write_text(dump_json(raw_payload), encoding="utf-8")
    report_path.write_text(
        build_markdown(
            started_at=started_at,
            profile_id=profile_id,
            session_id=session_id,
            create_result=create_result,
            turns=turns,
            evidence=evidence,
            raw_json_path=raw_json_path,
            aborted=aborted,
            abort_reason=abort_reason,
        ),
        encoding="utf-8",
    )

    print(f"session_id={session_id}")
    print(f"raw_json={raw_json_path}")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
