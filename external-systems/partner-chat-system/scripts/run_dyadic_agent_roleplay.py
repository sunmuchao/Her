#!/usr/bin/env python3
"""Run two LLM personas in a real chat thread; optional proactive assistant rescue; persona self-ratings."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from time import perf_counter


def _load_repo_dotenv() -> None:
    """Load ``Her/.env`` only when monorepo root is found; ``override=True`` beats bad shell OPENAI_API_KEY."""
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

_partner_chat_root = Path(__file__).resolve().parents[1]
if str(_partner_chat_root) not in sys.path:
    sys.path.insert(0, str(_partner_chat_root))

from chat_system.dyadic_roleplay import parse_int_csv, run_dyadic_roleplay  # noqa: E402
from chat_system.profile_loader import (  # noqa: E402
    DEFAULT_PROFILE_MYSQL_DSN,
    fetch_profile_by_id,
    profile_row_to_brief,
    roleplay_participant_id,
)
from chat_system.scenario_stress import list_beat_ids  # noqa: E402
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN, connect_db, initialize_database  # noqa: E402

DEFAULT_ROLEPLAY_BASE_TIME = datetime(2026, 5, 4, 12, 0, 0)


def _parse_str_csv(s: str) -> list[str]:
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def _parse_base_time(s: str) -> datetime:
    try:
        return datetime.fromisoformat(str(s).strip())
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            "base time must be ISO 8601, e.g. 2026-05-04T12:00:00"
        ) from e


def _log(message: str) -> None:
    ts = datetime.now().isoformat(sep=" ", timespec="seconds")
    print(f"[run_dyadic_agent_roleplay {ts}] {message}", file=sys.stderr, flush=True)


def _preview_text(text: str, *, limit: int = 120) -> str:
    single_line = " ".join((text or "").split())
    if len(single_line) <= limit:
        return single_line
    return single_line[: limit - 1] + "…"


def _extract_marked_value(text: str, prefix: str, suffix: str) -> str:
    start = text.find(prefix)
    if start < 0:
        return ""
    start += len(prefix)
    end = text.find(suffix, start)
    if end < 0:
        return text[start:].strip()
    return text[start:end].strip()


def _classify_llm_call(messages: list[dict[str, str]]) -> tuple[str, str]:
    if not messages:
        return "unknown", ""
    sys_c = messages[0].get("content") or ""
    user_c = messages[-1].get("content") or ""
    if "对话调度员" in sys_c and "下一位即将发言的用户ID" in user_c:
        return "orchestrator_rescue_decision", _extract_marked_value(
            user_c, "下一位即将发言的用户ID：", "\n"
        )
    if "附加任务" in sys_c and "请输出 JSON" in user_c:
        return "persona_self_evaluation", _extract_marked_value(sys_c, "你的用户ID是「", "」")
    if "请写出下一条你要发给对方的聊天内容" in user_c:
        return "persona_next_message", _extract_marked_value(sys_c, "你的用户ID是「", "」")
    return "unknown", ""


def _make_logged_llm(
    complete: Callable[[list[dict[str, str]]], str],
    *,
    stats: dict[str, dict[str, int]] | None = None,
) -> Callable[[list[dict[str, str]]], str]:
    call_counts: dict[str, int] = {}

    def wrapped(messages: list[dict[str, str]]) -> str:
        kind, subject = _classify_llm_call(messages)
        call_counts[kind] = call_counts.get(kind, 0) + 1
        seq = call_counts[kind]
        label = f"{kind}#{seq}"
        if subject:
            label = f"{label}({subject})"
        _log(f"LLM start {label}")
        started = perf_counter()
        try:
            output = complete(messages)
        except Exception as e:
            elapsed_ms = int((perf_counter() - started) * 1000)
            _log(f"LLM failed {label} after {elapsed_ms} ms: {type(e).__name__}: {e}")
            raise
        elapsed_ms = int((perf_counter() - started) * 1000)
        if stats is not None:
            bucket = stats.setdefault(kind, {"calls": 0, "total_ms": 0, "max_ms": 0})
            bucket["calls"] += 1
            bucket["total_ms"] += elapsed_ms
            bucket["max_ms"] = max(bucket["max_ms"], elapsed_ms)
        _log(f"LLM done {label} in {elapsed_ms} ms: {_preview_text(output)}")
        return output

    return wrapped


def _make_local_demo_llm(*, log: Callable[[str], None] | None = None) -> Callable[[list[dict[str, str]]], str]:
    """Deterministic offline LLM stand-in (no API key)."""

    import json as _json

    if log is not None:
        log("LLM backend=local-demo")

    orch = {"n": 0}
    eval_round = {"n": 0}

    def complete(messages: list[dict[str, str]]) -> str:
        sys_c = messages[0]["content"]
        user_c = messages[-1]["content"]
        if "对话调度员" in sys_c and "下一位即将发言的用户ID" in user_c:
            orch["n"] += 1
            if orch["n"] == 2:
                return _json.dumps(
                    {
                        "need_rescue": True,
                        "situation": "awkward",
                        "mutual_intent_assessment": "communication_problem",
                        "interaction_mode": "repair",
                        "rescue_style": "switch_topic",
                        "reason": "demo：第二轮接话略生硬",
                    },
                    ensure_ascii=False,
                )
            return _json.dumps(
                {
                    "need_rescue": False,
                    "situation": "none",
                    "mutual_intent_assessment": "normal",
                    "interaction_mode": "none",
                    "rescue_style": "none",
                    "reason": "demo：气氛正常",
                },
                ensure_ascii=False,
            )
        if "请写出下一条" in user_c:
            return "demo：你好，我也挺喜欢慢慢了解的，方便说说你平时周末一般怎么安排吗？"
        if "附加任务" in sys_c and "请输出 JSON" in user_c:
            eval_round["n"] += 1
            if eval_round["n"] == 1:
                return _json.dumps(
                    {
                        "conversation_satisfied": True,
                        "conversation_score": 4,
                        "assistant_satisfied": True,
                        "assistant_score": 4,
                        "used_assistant": orch["n"] >= 2,
                        "conversation_note": "demo：对方节奏还行",
                        "assistant_note": "demo：救场建议有用",
                    },
                    ensure_ascii=False,
                )
            return _json.dumps(
                {
                    "conversation_satisfied": True,
                    "conversation_score": 3,
                    "assistant_satisfied": True,
                    "assistant_score": 3,
                    "used_assistant": False,
                    "conversation_note": "demo：聊得中规中矩",
                    "assistant_note": "demo：我这轮没触发助手建议",
                },
                ensure_ascii=False,
            )
        return "{}"

    return complete


def _make_llm(*, log: Callable[[str], None] | None = None) -> Callable[[list[dict[str, str]]], str]:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        raise SystemExit("OPENAI_API_KEY is required for roleplay (set in env or Her/.env).")
    try:
        from openai import OpenAI
    except ImportError as e:
        raise SystemExit("Install openai package: pip install openai") from e
    model = (os.environ.get("HER_ROLEPLAY_MODEL") or os.environ.get("HER_CHAT_ASSISTANT_MODEL") or "gpt-4o-mini").strip()
    fast_model = (
        os.environ.get("HER_ROLEPLAY_FAST_MODEL")
        or os.environ.get("HER_ROLEPLAY_ORCHESTRATOR_MODEL")
        or model
    ).strip()
    message_model = (
        os.environ.get("HER_ROLEPLAY_MESSAGE_MODEL")
        or fast_model
        or model
    ).strip()
    eval_model = (os.environ.get("HER_ROLEPLAY_EVAL_MODEL") or model).strip()
    base = (
        os.environ.get("HER_ROLEPLAY_BASE_URL")
        or os.environ.get("HER_CHAT_ASSISTANT_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or ""
    ).strip()
    try:
        timeout_sec = float(os.environ.get("HER_ROLEPLAY_TIMEOUT_SEC") or "45")
    except ValueError:
        timeout_sec = 45.0
    kwargs: dict[str, object] = {
        "api_key": key,
        "max_retries": 0,
        "timeout": max(10.0, min(timeout_sec, 120.0)),
    }
    if base:
        kwargs["base_url"] = base
    if log is not None:
        log(
            "LLM backend=remote "
            f"model_main={model} model_fast={fast_model} model_message={message_model} model_eval={eval_model} "
            f"base_url={base or 'default'}"
        )
    client = OpenAI(**kwargs)

    def complete(messages: list[dict[str, str]]) -> str:
        kind, _subject = _classify_llm_call(messages)
        selected_model = model
        max_tokens = 400
        temperature = 0.5
        try:
            message_max_tokens = int(os.environ.get("HER_ROLEPLAY_MESSAGE_MAX_TOKENS") or "120")
        except ValueError:
            message_max_tokens = 120
        if kind == "orchestrator_rescue_decision":
            selected_model = fast_model
            max_tokens = 180
            temperature = 0.1
        elif kind == "persona_next_message":
            selected_model = message_model
            max_tokens = max(60, min(message_max_tokens, 220))
            temperature = 0.55
        elif kind == "persona_self_evaluation":
            selected_model = eval_model
            max_tokens = 260
            temperature = 0.3
        resp = client.chat.completions.create(
            model=selected_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (resp.choices[0].message.content or "").strip()

    return complete


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=DEFAULT_CHAT_TEST_MYSQL_DSN, help="MySQL DSN (default: test DB).")
    p.add_argument(
        "--case-id",
        default=None,
        help="chat_threads.case_id (default: random roleplay-*)",
    )
    p.add_argument("--rounds", type=int, default=6, help="Alternating dyadic turns (A,B,A,…).")
    p.add_argument(
        "--assistant-mode",
        choices=("proactive", "fixed_turns", "none"),
        default="proactive",
        help="proactive=模型判断尬聊/冷场等再触发助手；fixed_turns=按回合；none=不调助手",
    )
    p.add_argument(
        "--assistant-on-turns",
        default="",
        help='仅 fixed_turns：逗号分隔回合下标，如 "0,2"',
    )
    p.add_argument("--participant-a", default="roleplay-user-a", help="participant_a_id")
    p.add_argument("--participant-b", default="roleplay-user-b", help="participant_b_id")
    p.add_argument(
        "--brief-a",
        default="28岁无锡女生，互联网运营，认真找对象，重视沟通和情绪稳定，慢热但真诚。",
        help="Persona brief for A",
    )
    p.add_argument(
        "--brief-b",
        default="30岁苏州男生，工程师，希望两年内稳定成家，务实、话不多但肯倾听。",
        help="Persona brief for B",
    )
    p.add_argument("--output", default=None, help="Write JSON result to this path.")
    p.add_argument(
        "--base-time",
        type=_parse_base_time,
        default=DEFAULT_ROLEPLAY_BASE_TIME,
        help="模拟对话起始时间（ISO 8601，默认 2026-05-04T12:00:00）",
    )
    p.add_argument(
        "--no-init-schema",
        action="store_true",
        help="Skip ensure_database/ensure_schema (use when tables already exist).",
    )
    p.add_argument(
        "--resume-existing",
        action="store_true",
        help="允许复用同一个 case_id 的已有线程；默认禁止，避免把新实验接到旧对话后面。",
    )
    p.add_argument(
        "--local-demo",
        action="store_true",
        help="不调用远程模型，用内置占位逻辑跑通全流程（含一次 proactive 救场），无需 OPENAI_API_KEY。",
    )
    p.add_argument(
        "--profile-a-id",
        type=int,
        default=None,
        help="从 profiles 表加载 A 的完整画像（库：--profile-dsn）；与 participant/brief 互斥优先",
    )
    p.add_argument("--profile-b-id", type=int, default=None, help="profiles.id for B")
    p.add_argument(
        "--profile-dsn",
        default=os.environ.get("HER_PROFILE_MYSQL_DSN") or DEFAULT_PROFILE_MYSQL_DSN,
        help="画像库 DSN，默认 HER_PROFILE_MYSQL_DSN 或 mysql://root@127.0.0.1:3307/her",
    )
    p.add_argument(
        "--stress",
        choices=("auto", "none", "rotate", "random"),
        default="auto",
        help="auto：填了 profile 两 id 时用 rotate 轮播压力剧情，否则 none",
    )
    p.add_argument(
        "--stress-beat-ids",
        default="",
        help="只使用这些 beat_id（逗号分隔），见 --list-stress-beats",
    )
    p.add_argument("--stress-seed", type=int, default=None, help="random 模式可复现种子")
    p.add_argument(
        "--list-stress-beats",
        action="store_true",
        help="打印全部压力剧情 id 后退出",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_stress_beats:
        print("\n".join(list_beat_ids()))
        return 0
    if args.local_demo:
        os.environ.pop("OPENAI_API_KEY", None)
    case_id = args.case_id or f"roleplay-dyadic-{secrets.token_hex(4)}"
    fixed_turns = parse_int_csv(args.assistant_on_turns)
    stress_mode = args.stress
    if stress_mode == "auto":
        stress_mode = "rotate" if (args.profile_a_id is not None and args.profile_b_id is not None) else "none"
    stress_beat_ids = _parse_str_csv(args.stress_beat_ids) or None

    if (args.profile_a_id is None) != (args.profile_b_id is None):
        raise SystemExit("请同时提供 --profile-a-id 与 --profile-b-id，或都不提供。")

    if args.profile_a_id is not None:
        row_a = fetch_profile_by_id(str(args.profile_dsn), int(args.profile_a_id))
        row_b = fetch_profile_by_id(str(args.profile_dsn), int(args.profile_b_id))
        brief_a = profile_row_to_brief(row_a)
        brief_b = profile_row_to_brief(row_b)
        pid_a = roleplay_participant_id(int(args.profile_a_id))
        pid_b = roleplay_participant_id(int(args.profile_b_id))
        relation_key = f"{pid_a}|{pid_b}"
        participant_summary = (
            f"profiles a={int(args.profile_a_id)}->{pid_a}, b={int(args.profile_b_id)}->{pid_b}"
        )
    else:
        brief_a = str(args.brief_a)
        brief_b = str(args.brief_b)
        pid_a = str(args.participant_a)
        pid_b = str(args.participant_b)
        relation_key = f"{pid_a}|{pid_b}"
        participant_summary = f"inline participants a={pid_a}, b={pid_b}"

    _log(
        "starting roleplay "
        f"case_id={case_id}, rounds={int(args.rounds)}, assistant_mode={args.assistant_mode}, "
        f"stress_mode={stress_mode}, base_time={args.base_time.isoformat(sep=' ')}, "
        f"resume_existing={bool(args.resume_existing)}, local_demo={bool(args.local_demo)}"
    )
    _log(participant_summary)
    if args.assistant_mode == "fixed_turns":
        _log(f"fixed assistant turns={fixed_turns}")
    if stress_beat_ids:
        _log(f"stress beat filter={','.join(stress_beat_ids)}")

    _log(f"connecting chat db: {args.db}")
    conn = connect_db(args.db)
    llm_stats: dict[str, dict[str, int]] = {}
    try:
        if not args.no_init_schema:
            _log("initializing chat schema")
            initialize_database(conn)
        else:
            _log("skipping chat schema initialization")
        llm_factory = _make_local_demo_llm if args.local_demo else _make_llm
        llm = _make_logged_llm(llm_factory(log=_log), stats=llm_stats)
        _log("running dyadic roleplay")
        result = run_dyadic_roleplay(
            conn,
            case_id=str(case_id),
            relation_key=relation_key,
            participant_a_id=pid_a,
            participant_b_id=pid_b,
            brief_a=brief_a,
            brief_b=brief_b,
            rounds=int(args.rounds),
            llm=llm,
            assistant_mode=str(args.assistant_mode),
            fixed_assistant_turns=fixed_turns if args.assistant_mode == "fixed_turns" else [],
            base_time=args.base_time,
            resume_existing=bool(args.resume_existing),
            stress_mode=stress_mode,
            stress_beat_ids=stress_beat_ids,
            stress_seed=args.stress_seed,
            log=_log,
        )
    except ValueError as e:
        msg = str(e)
        if "roleplay refuses to append by default" in msg or "does not match the requested roleplay participants" in msg:
            _log(f"roleplay aborted: {msg}")
            print(msg, file=sys.stderr)
            return 2
        raise
    except Exception as e:
        err = str(e).lower()
        if "401" in err or "authentication" in err or "invalid_api_key" in err or "invalid access token" in err:
            print(
                "鉴权失败：请检查 Her 仓库根目录 `.env` 里的 OPENAI_API_KEY（或 DashScope 等兼容网关的 key）是否有效、未过期；"
                "并确认 HER_CHAT_ASSISTANT_BASE_URL 与 key 所属平台一致。",
                file=sys.stderr,
            )
        _log(f"roleplay failed: {type(e).__name__}: {e}")
        raise
    finally:
        conn.close()
        _log("chat db connection closed")
    if args.profile_a_id is not None:
        result["source_profiles"] = {
            "dsn": str(args.profile_dsn),
            "profile_a_id": int(args.profile_a_id),
            "profile_b_id": int(args.profile_b_id),
        }
    if llm_stats:
        result["llm_stats"] = {
            key: {
                "calls": value["calls"],
                "avg_ms": int(value["total_ms"] / value["calls"]) if value["calls"] else 0,
                "max_ms": value["max_ms"],
            }
            for key, value in llm_stats.items()
        }
        _log(
            "llm stats "
            + ", ".join(
                f"{key}:calls={value['calls']},avg_ms={int(value['total_ms'] / value['calls']) if value['calls'] else 0},max_ms={value['max_ms']}"
                for key, value in sorted(llm_stats.items())
            )
        )
    _log(
        "roleplay completed "
        f"thread_id={result.get('thread_id')}, reused={result.get('thread_reused')}, "
        f"rescue_events={len(result.get('proactive_rescue_events') or [])}, "
        f"repair_turns={(result.get('assistant_metrics') or {}).get('repair_intervention_turns')}, "
        f"probe_turns={(result.get('assistant_metrics') or {}).get('probe_intervention_turns')}, "
        f"hold_turns={(result.get('assistant_metrics') or {}).get('hold_decision_turns')}, "
        f"stress_events={len(result.get('stress_events') or [])}"
    )
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        _log(f"result written to {args.output}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
