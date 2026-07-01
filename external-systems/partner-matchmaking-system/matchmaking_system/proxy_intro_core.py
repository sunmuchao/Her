"""Proxy-intro case lifecycle (canonical implementation for matchmaking-system)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from match_domain import (  # noqa: E402
    CaseType,
    append_outbox_pending,
    build_case_aggregate_event,
    bundle_proxy_intro_case_entities,
    match_events_from_case_event_rows,
    reduce_case_ledger,
)
from match_domain.onboarding_search import _RELATIONSHIP_GOAL_DISPLAY  # noqa: E402
from observability import RECOMMENDATION_FUNNEL_PROXY_INTRO, funnel_stage  # noqa: E402

from recommendation_system.service import (  # noqa: E402
    append_relation_state_revision_event,
    current_time,
    format_dt,
    get_recommendation,
    get_subscription,
    insert_recommendation_action,
    parse_dt,
)
from recommendation_system.storage import json_dumps, json_loads, row_to_dict  # noqa: E402

from match_domain.proxy_intro_storage import (
    event_source_service,
    table_names,
    use_matchmaking_storage,
)
from relationship_ledger.runtime import defer_ledger_event, flush_ledger_mirror
from relationship_ledger.runtime import _CONN_LEDGER_MIRRORS  # noqa: PLC2701


def _t():
    return table_names()


from match_domain.proxy_intro_storage import _should_query_cases_on_conn  # noqa: E402


def _rec_conn(recommendation_conn, case_conn):
    return recommendation_conn if recommendation_conn is not None else case_conn


def _pair(case_conn, recommendation_conn=None):
    rec = _rec_conn(recommendation_conn, case_conn)
    return case_conn, rec


def commit_proxy_intro_transaction(case_conn, recommendation_conn=None) -> None:
    rec = _rec_conn(recommendation_conn, case_conn)
    rec.commit()
    if id(case_conn) != id(rec):
        case_conn.commit()
    entries = list(_CONN_LEDGER_MIRRORS.pop(id(rec), []))
    entries.extend(_CONN_LEDGER_MIRRORS.pop(id(case_conn), []))
    flush_ledger_mirror(entries)


DEFAULT_OUTREACH_CHANNEL = "in_app_proxy_intro"
DEFAULT_REPLY_WINDOW_HOURS = 72
DEFAULT_DECLINE_COOLDOWN_DAYS = 180
DEFAULT_TIMEOUT_COOLDOWN_DAYS = 90

OPEN_CASE_STATUSES = {"pending_outreach", "awaiting_reply", "viewed", "accepted"}  # viewed是新状态，仍然属于开放状态
CLOSED_CASE_STATUSES = {"declined", "timed_out", "closed"}
def generate_case_id() -> str:
    return f"match-case-{uuid.uuid4().hex[:12]}"


def _age_bracket(age: Any) -> str | None:
    if age in {None, ""}:
        return None
    try:
        age_int = int(age)
    except (TypeError, ValueError):
        return None
    bucket_start = (age_int // 5) * 5
    return f"{bucket_start}-{bucket_start + 4}岁"


def _height_bracket(height: Any) -> str | None:
    if height in {None, ""}:
        return None
    try:
        height_int = int(height)
    except (TypeError, ValueError):
        return None
    bucket_start = (height_int // 5) * 5
    return f"{bucket_start}-{bucket_start + 4}cm"


def build_safe_summary(subscription: dict[str, Any], recommendation: dict[str, Any]) -> dict[str, Any]:
    """构建候选人（被推荐方）的信息摘要，用于存储在案件中。"""
    payload = dict(recommendation.get("latest_payload") or {})
    profile = dict(payload.get("profile") or {})
    safe_summary = {
        "candidate_name": recommendation.get("candidate_name"),
        "age_bracket": _age_bracket(profile.get("age")),
        "city": profile.get("city") or profile.get("settlement_city"),
        "height_bracket": _height_bracket(profile.get("height")),
        "education": profile.get("education"),
        "relationship_goal": profile.get("relationship_goal"),
        "matched_on": list(payload.get("matched_on") or [])[:3],
        "subscription_title": subscription.get("title"),
    }
    safe_summary["summary_text"] = "；".join(
        part
        for part in [
            safe_summary["age_bracket"],
            safe_summary["city"],
            safe_summary["education"],
            safe_summary["relationship_goal"],
        ]
        if part
    )
    return safe_summary


def build_requester_safe_summary(subscription: dict[str, Any]) -> dict[str, Any]:
    """构建发起方（requester）的信息摘要，用于发送给被请求方。

    与 build_safe_summary 不同，此函数从 subscription（发起方的订阅）提取发起方的信息，
    用于构建发给被请求方的消息内容。

    Args:
        subscription: 发起方的订阅记录，包含 self_profile_json（发起方的资料）

    Returns:
        发起方的信息摘要，包含年龄、城市、职业等（年龄使用实际年龄而非年龄段）
    """
    self_profile = json_loads(subscription.get("self_profile_json"), {})

    # 年龄：使用实际年龄，不转换为年龄段
    age_value = self_profile.get("age")
    age_display = None
    if age_value not in {None, ""}:
        try:
            age_int = int(age_value)
            age_display = f"{age_int}岁"
        except (TypeError, ValueError):
            age_display = None

    # 关系目标：使用中文映射
    relationship_goal_raw = self_profile.get("relationship_goal")
    relationship_goal_display = None
    if relationship_goal_raw:
        relationship_goal_display = _RELATIONSHIP_GOAL_DISPLAY.get(
            relationship_goal_raw,
            _RELATIONSHIP_GOAL_DISPLAY.get(relationship_goal_raw.lower(), relationship_goal_raw)
        )

    safe_summary = {
        "requester_name": self_profile.get("display_name") or self_profile.get("name") or "有人",
        "age": age_display,  # 使用实际年龄（如"28岁")
        "age_bracket": age_display,  # 兼容性：保持字段名，但值是实际年龄
        "city": self_profile.get("city") or self_profile.get("settlement_city"),
        "height_bracket": _height_bracket(self_profile.get("height")),
        "education": self_profile.get("education"),
        "occupation": self_profile.get("job") or self_profile.get("occupation"),
        "relationship_goal": relationship_goal_display,  # 使用中文映射
        "relationship_goal_raw": relationship_goal_raw,  # 保留原始值（供查询使用）
        "matched_on": [],  # TODO: 可以从 subscription 的 criteria 中提取匹配点
        "subscription_title": subscription.get("title"),
        "avatar_url": self_profile.get("avatar_url") or self_profile.get("photo_url"),
    }

    # 构建 summary_text：使用实际年龄和中文映射
    safe_summary["summary_text"] = "；".join(
        part for part in [
            safe_summary["age"],
            safe_summary["city"],
            safe_summary["education"],
            safe_summary["occupation"],
            safe_summary["relationship_goal"],
        ] if part
    )
    return safe_summary


def build_outreach_payload(
    subscription: dict[str, Any],
    safe_summary: dict[str, Any],
    *,
    outreach_channel: str = DEFAULT_OUTREACH_CHANNEL,
) -> dict[str, Any]:
    """构建发给被请求方的消息。

    注意：此函数的 safe_summary 参数应该是候选人（被推荐方）的信息，
    用于历史兼容。新代码应使用 build_outreach_payload_from_requester。
    """
    parts = [
        "有人想通过平台进一步认识你。",
        safe_summary.get("age_bracket"),
        safe_summary.get("city"),
        safe_summary.get("relationship_goal"),
    ]
    if safe_summary.get("matched_on"):
        parts.append("匹配点：" + "；".join(str(item) for item in safe_summary["matched_on"]))
    body = "\n".join(part for part in parts if part)
    return {
        "channel": outreach_channel,
        "title": "有人想通过平台进一步了解你",
        "body": body,
        "safe_summary": safe_summary,
        "subscription_title": subscription.get("title"),
    }


def build_outreach_payload_from_requester(
    requester_summary: dict[str, Any],
    *,
    outreach_channel: str = DEFAULT_OUTREACH_CHANNEL,
) -> dict[str, Any]:
    """构建发给被请求方的消息，内容是发起方的信息。

    与 build_outreach_payload 不同，此函数使用发起方的信息摘要构建消息，
    让被请求方看到"谁想认识你"的具体信息。

    Args:
        requester_summary: 发起方的信息摘要（由 build_requester_safe_summary 生成）
        outreach_channel: 投递渠道

    Returns:
        发给被请求方的消息 payload，包含发起方的年龄、城市、职业等
    """
    requester_name = requester_summary.get("requester_name") or "有人"

    # 基本信息：年龄、城市、职业、学历、关系目标
    info_parts = [
        requester_summary.get("age"),  # 实际年龄（如"28岁")
        requester_summary.get("city"),
        requester_summary.get("occupation"),
        requester_summary.get("education"),
        requester_summary.get("relationship_goal"),  # 已映射为中文
    ]
    info_line = "；".join(part for part in info_parts if part)

    # 匹配点：单独一行
    matched_on = requester_summary.get("matched_on")
    match_line = None
    if matched_on and len(matched_on) > 0:
        match_line = "匹配点：" + "；".join(str(item) for item in matched_on[:3])

    # 组装消息：分行显示
    lines = [
        f"{requester_name}想通过平台进一步认识你。",
        info_line,
        match_line,
    ]
    body = "\n".join(line for line in lines if line)

    return {
        "channel": outreach_channel,
        "title": f"{requester_name}想认识你",
        "body": body,
        "requester_summary": requester_summary,  # 使用 requester_summary 而非 safe_summary
    }


def inflate_match_case(
    case: dict[str, Any] | None,
    *,
    conn=None,
    recommendation_conn=None,
    include_ledger_events: bool = True,
) -> dict[str, Any] | None:
    if not case:
        return None
    inflated = dict(case)
    inflated["safe_summary"] = json_loads(inflated.pop("safe_summary_json"), {})
    inflated["requester_profile_snapshot"] = json_loads(
        inflated.pop("requester_profile_snapshot_json"),
        {},
    )
    inflated["candidate_snapshot"] = json_loads(inflated.pop("candidate_snapshot_json"), {})
    inflated["outreach_payload"] = json_loads(inflated.pop("outreach_payload_json"), {})
    inflated["reply_payload"] = json_loads(inflated.pop("reply_payload_json"), {})
    inflated["case_type"] = inflated.get("case_type") or CaseType.PROXY_INTRO.value

    # relation_key 处理：优先从 case 读取（持久化），其次从 recommendation 查询，最后兜底生成
    relation_key = str(inflated.get("relation_key") or "").strip()
    recommendation = None
    case_conn, rec_conn = _pair(conn, recommendation_conn) if conn is not None else (None, None)
    if rec_conn is not None:
        recommendation_id = inflated.get("recommendation_id")
        subscription_id = inflated.get("subscription_id")
        candidate_id = inflated.get("candidate_id")
        if recommendation_id is not None and subscription_id and candidate_id is not None:
            recommendation = get_recommendation(rec_conn, str(subscription_id), int(candidate_id))

    if not relation_key and recommendation:
        # case 中没有 relation_key，尝试从 recommendation 获取
        relation_key = str(recommendation.get("relation_key") or "").strip()

    if not relation_key:
        # 兜底逻辑：根据 requester 和 candidate 信息生成 relation_key
        requester_id = inflated.get("requester_id")
        candidate_id = inflated.get("candidate_id")
        if requester_id and candidate_id:
            from match_domain import matchmaking_relation_key
            requester_info = {"source": "her", "self_id": requester_id, "user_key": str(requester_id)}
            candidate_info = {"source": "her", "self_id": candidate_id, "user_key": str(candidate_id)}
            member_low, member_high = sorted([requester_info, candidate_info], key=lambda x: int(x.get("self_id") or 0))
            relation_key = matchmaking_relation_key(member_low, member_high)

    inflated["relation_key"] = relation_key

    if recommendation:
        inflated["owner_profile_ref"] = recommendation.get("owner_profile_ref")
        inflated["target_profile_ref"] = recommendation.get("target_profile_ref")
    cid = inflated.get("case_id")
    ledger_events = []
    if include_ledger_events and case_conn is not None and cid:
        event_rows = list_match_case_events(case_conn, str(cid))
        ledger_events = match_events_from_case_event_rows(event_rows)
    inflated["case_ledger_event_count"] = len(ledger_events)
    reduced = reduce_case_ledger(ledger_events)
    inflated["canonical_case_status"] = reduced.status.value
    return inflated


def inflate_match_case_event(event: dict[str, Any] | None) -> dict[str, Any] | None:
    if not event:
        return None
    inflated = dict(event)
    canon_raw = inflated.pop("canonical_event_json", None)
    payload = json_loads(inflated.pop("payload_json"), {})
    if canon_raw is not None and (not isinstance(canon_raw, str) or str(canon_raw).strip()):
        canon_obj = json.loads(canon_raw) if isinstance(canon_raw, str) else canon_raw
        if isinstance(canon_obj, dict):
            payload = {**payload, "canonical_event": canon_obj}
    inflated["payload"] = payload
    return inflated


def inflate_match_case_attempt(attempt: dict[str, Any] | None) -> dict[str, Any] | None:
    if not attempt:
        return None
    inflated = dict(attempt)
    inflated["payload"] = json_loads(inflated.pop("payload_json"), {})
    return inflated




def get_match_case(
    case_conn,
    case_id: str,
    *,
    recommendation_conn=None,
) -> dict[str, Any] | None:
    row = case_conn.execute(f"SELECT * FROM {_t().cases} WHERE case_id = ?", (case_id,)).fetchone()
    return inflate_match_case(
        row_to_dict(row),
        conn=case_conn,
        recommendation_conn=recommendation_conn,
    )


get_proxy_intro_case = get_match_case


def list_match_cases_for_subscription(
    conn,
    subscription_id: str,
    *,
    recommendation_conn=None,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT *
        FROM {_t().cases}
        WHERE subscription_id = ?
        ORDER BY created_at DESC, case_id DESC
        """,
        (subscription_id,),
    ).fetchall()
    rec = _rec_conn(recommendation_conn, conn)
    return [
        inflate_match_case(row_to_dict(row), conn=conn, recommendation_conn=rec)
        for row in rows
    ]


def list_match_cases_for_participant(
    conn,
    profile_id: int,
    *,
    recommendation_conn=None,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT *
        FROM {_t().cases}
        WHERE requester_id = ? OR candidate_id = ?
        ORDER BY created_at DESC, case_id DESC
        """,
        (int(profile_id), int(profile_id)),
    ).fetchall()
    rec = _rec_conn(recommendation_conn, conn)
    return [
        inflate_match_case(row_to_dict(row), conn=conn, recommendation_conn=rec)
        for row in rows
    ]


def list_match_case_events(conn, case_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT *
        FROM {_t().events}
        WHERE case_id = ?
        ORDER BY occurred_at ASC, event_id ASC
        """,
        (case_id,),
    ).fetchall()
    return [inflate_match_case_event(row_to_dict(row)) for row in rows]


def list_match_case_events_for_cases(
    conn,
    case_ids: Iterable[str],
) -> dict[str, list[dict[str, Any]]]:
    normalized = [str(item).strip() for item in case_ids if str(item or "").strip()]
    if not normalized or not _should_query_cases_on_conn(conn):
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM {_t().events}
        WHERE case_id IN ({placeholders})
        ORDER BY case_id ASC, occurred_at ASC, event_id ASC
        """,
        normalized,
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        row_dict = row_to_dict(row)
        cid = str(row_dict.get("case_id") or "").strip()
        if not cid:
            continue
        inflated = inflate_match_case_event(row_dict)
        if inflated:
            grouped.setdefault(cid, []).append(inflated)
    return grouped


def list_match_cases_for_recommendations(
    conn,
    recommendation_ids: Iterable[int],
    *,
    recommendation_conn=None,
    include_ledger_events: bool = False,
) -> dict[int, list[dict[str, Any]]]:
    if not _should_query_cases_on_conn(conn):
        return {}
    normalized = [int(item) for item in recommendation_ids]
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM {_t().cases}
        WHERE recommendation_id IN ({placeholders})
        ORDER BY recommendation_id ASC, created_at DESC, case_id DESC
        """,
        normalized,
    ).fetchall()
    rec = _rec_conn(recommendation_conn, conn)
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        row_dict = row_to_dict(row)
        rid = row_dict.get("recommendation_id")
        if rid is None:
            continue
        inflated = inflate_match_case(
            row_dict,
            conn=conn,
            recommendation_conn=rec,
            include_ledger_events=include_ledger_events,
        )
        if inflated:
            grouped.setdefault(int(rid), []).append(inflated)
    return grouped


def list_match_case_outreach_attempts(conn, case_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        f"""
        SELECT *
        FROM {_t().attempts}
        WHERE case_id = ?
        ORDER BY sent_at ASC, attempt_id ASC
        """,
        (case_id,),
    ).fetchall()
    return [inflate_match_case_attempt(row_to_dict(row)) for row in rows]


def list_match_cases_for_recommendation(
    conn,
    recommendation_id: int,
    *,
    recommendation_conn=None,
) -> list[dict[str, Any]]:
    if not _should_query_cases_on_conn(conn):
        return []
    rows = conn.execute(
        f"""
        SELECT *
        FROM {_t().cases}
        WHERE recommendation_id = ?
        ORDER BY created_at DESC, case_id DESC
        """,
        (recommendation_id,),
    ).fetchall()
    rec = _rec_conn(recommendation_conn, conn)
    return [
        inflate_match_case(row_to_dict(row), conn=conn, recommendation_conn=rec)
        for row in rows
    ]


def get_latest_match_case_for_recommendation(
    conn,
    recommendation_id: int,
    *,
    recommendation_conn=None,
) -> dict[str, Any] | None:
    if not _should_query_cases_on_conn(conn):
        return None
    row = conn.execute(
        f"""
        SELECT *
        FROM {_t().cases}
        WHERE recommendation_id = ?
        ORDER BY created_at DESC, case_id DESC
        LIMIT 1
        """,
        (recommendation_id,),
    ).fetchone()
    rec = _rec_conn(recommendation_conn, conn)
    return inflate_match_case(row_to_dict(row), conn=conn, recommendation_conn=rec)


def get_active_match_case_for_recommendation(
    conn,
    recommendation_id: int,
    *,
    recommendation_conn=None,
) -> dict[str, Any] | None:
    if not _should_query_cases_on_conn(conn):
        return None
    row = conn.execute(
        f"""
        SELECT *
        FROM {_t().cases}
        WHERE recommendation_id = ?
          AND case_status IN ('pending_outreach', 'awaiting_reply', 'accepted')
        ORDER BY created_at DESC, case_id DESC
        LIMIT 1
        """,
        (recommendation_id,),
    ).fetchone()
    rec = _rec_conn(recommendation_conn, conn)
    return inflate_match_case(row_to_dict(row), conn=conn, recommendation_conn=rec)


def _record_case_event(
    case_conn,
    *,
    recommendation_conn=None,

    case: dict[str, Any],
    event_type: str,
    actor_type: str,
    from_status: str | None,
    to_status: str | None,
    now: datetime,
    payload: dict[str, Any] | None = None,
) -> None:
    _, rec_conn = _pair(case_conn, recommendation_conn)
    recommendation = get_recommendation(rec_conn, case["subscription_id"], int(case["candidate_id"]))
    event = build_case_aggregate_event(
        event_type=event_type,
        case_id=str(case["case_id"]),
        case_type=CaseType.PROXY_INTRO,
        source_service=event_source_service(),
        actor_type=actor_type,
        actor_id=(
            str(case["candidate_id"])
            if actor_type == "candidate"
            else ("system" if actor_type == "system" else str(case["requester_id"]))
        ),
        occurred_at=now,
        payload={
            "subscription_id": case["subscription_id"],
            "recommendation_id": case["recommendation_id"],
            "candidate_id": case["candidate_id"],
            **dict(payload or {}),
        },
        entity_ids=bundle_proxy_intro_case_entities(case),
    )
    occurred_str = format_dt(now)
    domain_payload = dict(payload or {})
    case_conn.execute(
        f"""
        INSERT INTO {_t().events} (
          case_id,
          subscription_id,
          recommendation_id,
          requester_id,
          candidate_id,
          event_type,
          from_status,
          to_status,
          actor_type,
          canonical_event_json,
          payload_json,
          occurred_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case["case_id"],
            case["subscription_id"],
            case["recommendation_id"],
            case["requester_id"],
            case["candidate_id"],
            event_type,
            from_status,
            to_status,
            actor_type,
            json_dumps(event.to_dict()),
            json_dumps(domain_payload),
            occurred_str,
        ),
    )
    append_outbox_pending(
        rec_conn,
        event=event,
        source_row_table=_t().events,
        source_row_id=case_conn.lastrowid or None,
        created_at_str=occurred_str,
    )
    if recommendation:
        defer_ledger_event(
            rec_conn,
            {
                "event": event,
                "relation_key": str(recommendation["relation_key"]),
                "owner_profile_ref": recommendation.get("owner_profile_ref"),
                "target_profile_ref": recommendation.get("target_profile_ref"),
                "case_id": str(case["case_id"]),
                "case_type": CaseType.PROXY_INTRO.value,
            },
        )


def _sync_recommendation_for_case(
    recommendation_conn,
    *,
    recommendation: dict[str, Any],
    case_id: str | None,
    case_status: str | None,
    delivery_status: str,
    delivery_reason: str,
    cooling_until: datetime | None = None,
    active: bool = False,
    now: datetime | None = None,
) -> None:
    _now = current_time(now)
    recommendation_conn.execute(
        """
        UPDATE profile_recommendations
        SET delivery_status = ?,
            delivery_reason = ?,
            active_match_case_id = ?,
            active_case_status = ?,
            cooling_until = ?
        WHERE recommendation_id = ?
        """,
        (
            delivery_status,
            delivery_reason,
            case_id if active else None,
            case_status if active else None,
            format_dt(cooling_until),
            recommendation["recommendation_id"],
        ),
    )
    row = recommendation_conn.execute(
        "SELECT * FROM profile_recommendations WHERE recommendation_id = ?",
        (recommendation["recommendation_id"],),
    ).fetchone()
    rec_row = row_to_dict(row)
    if rec_row:
        # FIX: 防御性处理订阅不存在的情况（孤儿 match case）
        try:
            subscription = get_subscription(recommendation_conn, rec_row["subscription_id"])
        except ValueError as e:
            if "Unknown subscription" in str(e):
                # 订阅已删除，使用空订阅对象跳过事件记录
                subscription = {
                    "subscription_id": rec_row["subscription_id"],
                    "requester_id": rec_row.get("requester_id"),
                    "source": "orphan_subscription",
                    "title": "已删除的订阅",
                }
            else:
                raise
        append_relation_state_revision_event(
            recommendation_conn,
            subscription=subscription,
            recommendation_row=rec_row,
            now=_now,
        )


def create_match_case(
    case_conn,
    *,
    recommendation_conn=None,

    subscription_id: str,
    candidate_id: int,
    now: datetime | None = None,
    initiated_by: str = "requester",
    outreach_channel: str = DEFAULT_OUTREACH_CHANNEL,
    reply_window_hours: int = DEFAULT_REPLY_WINDOW_HOURS,
    request_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    _, rec_conn = _pair(case_conn, recommendation_conn)
    subscription = get_subscription(rec_conn, subscription_id)
    recommendation = get_recommendation(rec_conn, subscription_id, int(candidate_id))
    if not recommendation:
        raise ValueError(f"Unknown recommendation for subscription={subscription_id} candidate_id={candidate_id}")
    if recommendation.get("delivery_status") == "direct_greet_started":
        raise ValueError("Cannot request proxy intro after direct_greet has already started.")
    if recommendation.get("delivery_status") == "escalated_to_case" and not recommendation.get("active_match_case_id"):
        raise ValueError("Candidate already completed the proxy-intro flow.")

    active_case = get_active_match_case_for_recommendation(
        case_conn,
        recommendation["recommendation_id"],
        recommendation_conn=rec_conn,
    )
    if active_case:
        # 案件已存在，返回已存在的案件（实现幂等性，避免重复点击报错）
        return active_case

    latest_case = get_latest_match_case_for_recommendation(
        case_conn,
        recommendation["recommendation_id"],
        recommendation_conn=rec_conn,
    )
    if latest_case and latest_case["case_status"] == "accepted":
        raise ValueError("Candidate already accepted a proxy-intro case.")
    if latest_case and latest_case["case_status"] in {"declined", "timed_out"}:
        cooling_until = parse_dt(latest_case.get("cooling_until"))
        if cooling_until and now < cooling_until:
            raise ValueError("Candidate is still cooling down after the last proxy-intro case.")

    case_id = generate_case_id()
    # 构建候选人（B）的信息摘要，用于存储在案件中
    safe_summary = build_safe_summary(subscription, recommendation)
    # 构建发起方（A）的信息摘要，用于发给被请求方（B）
    requester_summary = build_requester_safe_summary(subscription)
    # 使用发起方的信息构建发给被请求方的消息
    outreach_payload = build_outreach_payload_from_requester(
        requester_summary,
        outreach_channel=outreach_channel,
    )
    reply_deadline_at = now + timedelta(hours=int(reply_window_hours or DEFAULT_REPLY_WINDOW_HOURS))
    requester_profile_snapshot = {
        "self_id": subscription.get("self_id"),
        "self_profile": json_loads(subscription.get("self_profile_json"), {}),
    }
    candidate_snapshot = dict(recommendation.get("latest_payload") or {})

    # 获取 relation_key：优先从 recommendation 获取，否则根据 requester 和 candidate 生成
    relation_key = str(recommendation.get("relation_key") or "").strip()
    if not relation_key:
        # 兜底逻辑：根据 requester 和 candidate 信息生成 relation_key
        from match_domain import matchmaking_relation_key, pool_member_profile_ref
        requester_info = {"source": "her", "self_id": recommendation["requester_id"], "user_key": str(recommendation["requester_id"])}
        candidate_info = {"source": "her", "self_id": recommendation["candidate_id"], "user_key": str(recommendation["candidate_id"])}
        member_low, member_high = sorted([requester_info, candidate_info], key=lambda x: int(x.get("self_id") or 0))
        relation_key = matchmaking_relation_key(member_low, member_high)

    case_conn.execute(
        f"""
        INSERT INTO {_t().cases} (
          case_id,
          subscription_id,
          recommendation_id,
          requester_id,
          candidate_id,
          candidate_name,
          initiated_by,
          case_type,
          case_status,
          outreach_channel,
          safe_summary_json,
          requester_profile_snapshot_json,
          candidate_snapshot_json,
          outreach_payload_json,
          reply_payload_json,
          reply_deadline_at,
          relation_key,
          created_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case_id,
            subscription_id,
            recommendation["recommendation_id"],
            recommendation["requester_id"],
            recommendation["candidate_id"],
            recommendation.get("candidate_name") or "未命名",
            initiated_by,
            CaseType.PROXY_INTRO.value,
            "pending_outreach",
            outreach_channel,
            json_dumps(safe_summary),
            json_dumps(requester_profile_snapshot),
            json_dumps(candidate_snapshot),
            json_dumps({**outreach_payload, "request_payload": request_payload or {}}),
            json_dumps({}),
            format_dt(reply_deadline_at),
            relation_key,
            format_dt(now),
            format_dt(now),
        ),
    )
    _record_case_event(
        case_conn,
        recommendation_conn=recommendation_conn,
        case={
            "case_id": case_id,
            "subscription_id": subscription_id,
            "recommendation_id": recommendation["recommendation_id"],
            "requester_id": recommendation["requester_id"],
            "candidate_id": recommendation["candidate_id"],
        },
        event_type="case_created",
        actor_type=initiated_by,
        from_status=None,
        to_status="pending_outreach",
        now=now,
        payload={"request_payload": request_payload or {}},
    )
    insert_recommendation_action(
        rec_conn,
        subscription=subscription,
        recommendation=recommendation,
        action_type="request_proxy_intro",
        actor_type=initiated_by,
        now=now,
        action_payload={
            "case_id": case_id,
            "outreach_channel": outreach_channel,
            "case_type": CaseType.PROXY_INTRO.value,
        },
    )
    _sync_recommendation_for_case(
        rec_conn,
        recommendation=recommendation,
        case_id=case_id,
        case_status="pending_outreach",
        delivery_status="escalated_to_case",
        delivery_reason="proxy_intro_requested",
        active=True,
        now=now,
    )
    commit_proxy_intro_transaction(case_conn, recommendation_conn)
    funnel_stage(
        system="recommendation",
        stage=RECOMMENDATION_FUNNEL_PROXY_INTRO,
        subscription_id=subscription_id,
        case_id=case_id,
        recommendation_id=int(recommendation["recommendation_id"]),
        candidate_id=int(candidate_id),
        initiated_by=initiated_by,
    )
    return get_match_case(case_conn, case_id, recommendation_conn=recommendation_conn)


def _update_case_status(
    case_conn,
    *,
    recommendation_conn=None,
    case: dict[str, Any],
    new_status: str,
    now: datetime,
    event_type: str,
    actor_type: str,
    close_reason: str | None = None,
    reply_payload: dict[str, Any] | None = None,
    cooling_until: datetime | None = None,
    active_match_case_id: str | None = None,
    active_case_status: str | None = None,
    recommendation_delivery_status: str | None = None,
    recommendation_delivery_reason: str | None = None,
) -> dict[str, Any]:
    _, rec_conn = _pair(case_conn, recommendation_conn)
    reply_payload_json = json_dumps(reply_payload) if reply_payload is not None else None
    case_conn.execute(
        f"""
        UPDATE {_t().cases}
        SET case_status = ?,
            close_reason = COALESCE(?, close_reason),
            reply_payload_json = COALESCE(?, reply_payload_json),
            replied_at = COALESCE(replied_at, ?),
            cooling_until = COALESCE(?, cooling_until),
            updated_at = ?
        WHERE case_id = ?
        """,
        (
            new_status,
            close_reason,
            reply_payload_json,
            format_dt(now),
            format_dt(cooling_until),
            format_dt(now),
            case["case_id"],
        ),
    )
    if recommendation_delivery_status is not None and recommendation_delivery_reason is not None:
        recommendation = get_recommendation(rec_conn, case["subscription_id"], int(case["candidate_id"]))
        if recommendation:
            _sync_recommendation_for_case(
                rec_conn,
                recommendation=recommendation,
                case_id=active_match_case_id,
                case_status=active_case_status or new_status,
                delivery_status=recommendation_delivery_status,
                delivery_reason=recommendation_delivery_reason,
                cooling_until=cooling_until,
                active=bool(active_match_case_id),
                now=now,
            )
    _record_case_event(
        case_conn,
        recommendation_conn=recommendation_conn,
        case=case,
        event_type=event_type,
        actor_type=actor_type,
        from_status=case["case_status"],
        to_status=new_status,
        now=now,
        payload={"close_reason": close_reason, "reply_payload": reply_payload or {}},
    )
    return get_match_case(case_conn, case["case_id"], recommendation_conn=recommendation_conn)


def dispatch_match_case_outreach(
    case_conn,
    *,
    recommendation_conn=None,
    case_id: str,
    now: datetime | None = None,
    provider_message_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    _, rec_conn = _pair(case_conn, recommendation_conn)
    case = get_match_case(case_conn, case_id, recommendation_conn=recommendation_conn)
    if not case:
        raise ValueError(f"Unknown match case: {case_id}")
    # 幂等性检查：如果案件已dispatch（状态不是pending_outreach），直接返回案件
    if case["case_status"] != "pending_outreach":
        return case

    attempts = list_match_case_outreach_attempts(case_conn, case_id)
    attempt_number = len(attempts) + 1
    dispatch_payload = payload or case.get("outreach_payload") or {}
    case_conn.execute(
        f"""
        INSERT INTO {_t().attempts} (
          case_id,
          attempt_number,
          channel,
          delivery_status,
          payload_json,
          provider_message_id,
          sent_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            case_id,
            attempt_number,
            case.get("outreach_channel") or DEFAULT_OUTREACH_CHANNEL,
            "sent",
            json_dumps(dispatch_payload),
            provider_message_id,
            format_dt(now),
        ),
    )
    case_conn.execute(
        f"""
        UPDATE {_t().cases}
        SET case_status = 'awaiting_reply',
            outreach_sent_at = COALESCE(outreach_sent_at, ?),
            updated_at = ?
        WHERE case_id = ?
        """,
        (
            format_dt(now),
            format_dt(now),
            case_id,
        ),
    )
    _record_case_event(
        case_conn,
        recommendation_conn=recommendation_conn,
        case=case,
        event_type="outreach_sent",
        actor_type="system",
        from_status="pending_outreach",
        to_status="awaiting_reply",
        now=now,
        payload=dispatch_payload,
    )
    recommendation = get_recommendation(rec_conn, case["subscription_id"], int(case["candidate_id"]))
    if recommendation:
        _sync_recommendation_for_case(
            rec_conn,
            recommendation=recommendation,
            case_id=case["case_id"],
            case_status="awaiting_reply",
            delivery_status="escalated_to_case",
            delivery_reason="proxy_intro_outreach_sent",
            active=True,
            now=now,
        )
    commit_proxy_intro_transaction(case_conn, recommendation_conn)

    # ✅ 注意：SSE推送通知移到外部调用，确保数据库先写入
    # 不在这里调用 _push_passive_recommendation_notification
    # 由调用方在 _push_proxy_intro_to_discovery_timeline 之后调用

    return get_match_case(case_conn, case_id, recommendation_conn=recommendation_conn)


def _push_case_status_update_notification(
    case: dict[str, Any],
    new_status: str,
    now: datetime,
) -> None:
    """推送案件状态更新通知给发起方（通过SSE）。

    当被推荐方接受/拒绝请求后，通知发起方状态已更新。

    Args:
        case: 案件数据
        new_status: 新状态（accepted/declined）
        now: 当前时间
    """
    import httpx
    from her_env import env_first

    sse_server_url = env_first(
        "SSE_SERVER_URL",
        "http://localhost:8081",
    )

    # 获取发起方的profile_id（需要接收通知）
    requester_profile_id = str(case.get("requester_id") or "")
    if not requester_profile_id:
        logger.warning("[SSE Push] 案件缺少requester_id，无法推送状态更新")
        return

    # 获取被推荐方的profile_id
    candidate_profile_id = str(case.get("candidate_id") or "")
    case_id = str(case.get("case_id") or "")

    try:
        # ✅ 使用新的profile级别推送端点
        push_url = f"{sse_server_url}/internal/push/profile"
        payload = {
            "profile_id": requester_profile_id,  # 推送给发起方
            "event_type": "case_status_update",  # 新事件类型：状态更新
            "case_id": case_id,
            "candidate_id": candidate_profile_id,
            "new_status": new_status,
            "message": f"对方已{'接受' if new_status == 'accepted' else '拒绝'}你的请求",
            "timestamp": now.isoformat(),
        }

        # 同步推送（不阻塞主流程），记录详细日志
        with httpx.Client(timeout=2.0) as client:
            response = client.post(push_url, json=payload)
            if response.status_code == 200:
                result = response.json()
                sent_count = result.get("pushed", 0)
                logger.info(
                    f"[SSE Push] 状态更新通知推送完成: requester={requester_profile_id}, "
                    f"candidate={candidate_profile_id}, case={case_id}, new_status={new_status}, "
                    f"sent_count={sent_count}"
                )
                if sent_count == 0:
                    logger.warning(
                        f"[SSE Push] 发起方不在线，推送失败: requester={requester_profile_id}, "
                        f"可能原因：用户未打开App或SSE连接断开"
                    )
            else:
                logger.warning(
                    f"[SSE Push] 推送请求失败: status={response.status_code}, "
                    f"requester={requester_profile_id}, response={response.text}"
                )
    except Exception as e:
        # 推送失败不影响主流程，只记录日志
        logger.warning(
            f"[SSE Push] 状态更新推送异常: {e}, requester={requester_profile_id}"
        )


def _push_passive_recommendation_notification(
    case: dict[str, Any],
    now: datetime,
) -> None:
    """推送被动推荐通知给被请求方（通过SSE）。

    Args:
        case: 案件数据
        now: 当前时间
    """
    import httpx
    from her_env import env_first

    sse_server_url = env_first(
        "SSE_SERVER_URL",
        "http://localhost:8081",
    )

    # 获取被请求方的profile_id（候选人，需要接收通知）
    # ✅ 统一转换为字符串类型，避免与SSE连接管理的key类型不匹配
    target_profile_id = str(case.get("candidate_id") or "")
    if not target_profile_id:
        return

    # 获取发起方的profile_id（点击"愿意认识你"的用户）
    source_profile_id = str(case.get("requester_id") or "")

    try:
        push_url = f"{sse_server_url}/internal/push/recommendation"
        payload = {
            "profile_id": target_profile_id,  # ✅ 字符串类型，与SSE连接key一致
            "event_type": "passive_recommendation",  # 被动推荐
            "case_id": case.get("case_id"),
            "source_profile_id": source_profile_id,  # ✅ 字符串类型
            "candidate_id": target_profile_id,  # ✅ 字符串类型
            "message": "有人愿意认识你",
            "timestamp": now.isoformat(),
        }

        # ✅ 同步推送（不阻塞主流程），记录详细日志
        with httpx.Client(timeout=2.0) as client:
            response = client.post(push_url, json=payload)
            if response.status_code == 200:
                result = response.json()
                sent_count = result.get("pushed", 0)
                online_sessions = result.get("online_sessions", [])
                logger.info(
                    f"[SSE Push] 被动推荐通知推送完成: target={target_profile_id}, "
                    f"source={source_profile_id}, case={case.get('case_id')}, "
                    f"sent_count={sent_count}, online_sessions={online_sessions}"
                )
                if sent_count == 0:
                    logger.warning(
                        f"[SSE Push] 用户不在线，推送失败: target={target_profile_id}, "
                        f"可能原因：用户未打开Discovery页面或SSE连接断开"
                    )
            else:
                logger.warning(
                    f"[SSE Push] 推送请求失败: status={response.status_code}, "
                    f"target={target_profile_id}, response={response.text}"
                )
    except Exception as e:
        # 推送失败不影响主流程，只记录日志
        logger.warning(
            f"[SSE Push] 推送异常: {e}, target={target_profile_id}"
        )


def dispatch_pending_match_cases(
    case_conn,
    *,
    recommendation_conn=None,
    now: datetime | None = None,
    case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    if case_ids:
        case_ids = list(case_ids)
        placeholders = ", ".join(["?"] * len(case_ids))
        rows = case_conn.execute(
            f"""
            SELECT *
            FROM {_t().cases}
            WHERE case_status = 'pending_outreach'
              AND case_id IN ({placeholders})
            ORDER BY created_at ASC, case_id ASC
            """,
            case_ids,
        ).fetchall()
    else:
        rows = case_conn.execute(
            f"""
            SELECT *
            FROM {_t().cases}
            WHERE case_status = 'pending_outreach'
            ORDER BY created_at ASC, case_id ASC
            """
        ).fetchall()
    cases = [
        inflate_match_case(row_to_dict(row), conn=case_conn, recommendation_conn=recommendation_conn)
        for row in rows
    ]
    dispatched = []
    for case in cases:
        dispatched.append(
            dispatch_match_case_outreach(
                case_conn,
                recommendation_conn=recommendation_conn,
                case_id=case["case_id"],
                now=now,
            )
        )
    return {"dispatched_count": len(dispatched), "cases": dispatched}


def mark_case_as_viewed(
    case_conn,
    *,
    recommendation_conn=None,
    case_id: str,
    now: datetime | None = None,
    view_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """标记被动推荐为已查看状态（从awaiting_reply变为viewed）"""
    now = current_time(now)
    _, rec_conn = _pair(case_conn, recommendation_conn)
    case = get_match_case(case_conn, case_id, recommendation_conn=recommendation_conn)
    if not case:
        raise ValueError(f"Unknown match case: {case_id}")

    # 只有awaiting_reply状态可以标记为viewed
    if case["case_status"] != "awaiting_reply":
        # 已经是viewed、accepted、declined等状态，不需要再次标记
        return case

    # 更新状态为viewed
    updated_case = _update_case_status(
        case_conn,
        recommendation_conn=recommendation_conn,
        case=case,
        new_status="viewed",
        now=now,
        event_type="case_viewed",
        actor_type="candidate",
        reply_payload=view_payload,
    )

    # ✅ 关键修复：commit事务，确保数据库更新生效
    commit_proxy_intro_transaction(case_conn, recommendation_conn)

    return updated_case


def record_match_case_reply(
    case_conn,
    *,
    recommendation_conn=None,
    case_id: str,
    reply_type: str,
    now: datetime | None = None,
    reply_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    _, rec_conn = _pair(case_conn, recommendation_conn)
    case = get_match_case(case_conn, case_id, recommendation_conn=recommendation_conn)
    if not case:
        raise ValueError(f"Unknown match case: {case_id}")
    # ✅ 修改：允许 viewed 状态也能回复（用户查看后仍可决定接受/拒绝）
    if case["case_status"] not in {"awaiting_reply", "viewed"}:
        raise ValueError("Replies can only be recorded when case is awaiting reply or viewed.")

    reply_type = str(reply_type).strip().lower()
    if reply_type not in {"accepted", "declined"}:
        raise ValueError(f"Unsupported reply_type: {reply_type}")

    # FIX: 防御性处理订阅不存在的情况（孤儿 match case）
    # 当订阅被删除后，match case 数据仍可能引用已删除的 subscription_id
    # 用户点击推荐来信卡片回复时，会触发此错误
    # 订阅不存在时，使用空订阅对象（仅用于记录推荐动作）
    try:
        subscription = get_subscription(rec_conn, case["subscription_id"])
    except ValueError as e:
        if "Unknown subscription" in str(e):
            # 订阅已删除，使用空订阅对象（孤儿 case）
            subscription = {
                "subscription_id": case["subscription_id"],
                "requester_id": case.get("requester_id"),
                "source": "orphan_subscription",
                "title": "已删除的订阅",
            }
        else:
            raise

    # FIX: 防御性处理推荐不存在的情况（孤儿 match case）
    # 当订阅被删除后，推荐数据可能也被清理，get_recommendation 可能返回 None
    recommendation = get_recommendation(rec_conn, case["subscription_id"], int(case["candidate_id"]))

    if reply_type == "accepted":
        updated_case = _update_case_status(
            case_conn,
            recommendation_conn=recommendation_conn,
            case=case,
            new_status="accepted",
            now=now,
            event_type="reply_accepted",
            actor_type="candidate",
            reply_payload=reply_payload,
            active_match_case_id=case["case_id"],
            active_case_status="accepted",
            recommendation_delivery_status="escalated_to_case",
            recommendation_delivery_reason="proxy_intro_accepted",
        )
        # FIX: 仅在推荐数据存在时记录推荐动作
        if recommendation:
            insert_recommendation_action(
                rec_conn,
                subscription=subscription,
                recommendation=recommendation,
                action_type="proxy_intro_reply_accepted",
                actor_type="candidate",
                actor_id=str(case["candidate_id"]),
                now=now,
                action_payload=reply_payload or {},
            )
    else:
        cooling_until = now + timedelta(days=DEFAULT_DECLINE_COOLDOWN_DAYS)
        updated_case = _update_case_status(
            case_conn,
            recommendation_conn=recommendation_conn,
            case=case,
            new_status="declined",
            now=now,
            event_type="reply_declined",
            actor_type="candidate",
            reply_payload=reply_payload,
            cooling_until=cooling_until,
            active_case_status=None,
            recommendation_delivery_status="cooled_down",
            recommendation_delivery_reason="proxy_intro_declined",
        )
        # FIX: 仅在推荐数据存在时记录推荐动作
        if recommendation:
            insert_recommendation_action(
                rec_conn,
                subscription=subscription,
                recommendation=recommendation,
                action_type="proxy_intro_reply_declined",
                actor_type="candidate",
                actor_id=str(case["candidate_id"]),
                now=now,
                action_payload=reply_payload or {},
            )
    commit_proxy_intro_transaction(case_conn, recommendation_conn)

    # ✅ 新增：推送状态更新通知给发起方
    _push_case_status_update_notification(
        case=updated_case,
        new_status=reply_type,  # accepted 或 declined
        now=now,
    )

    return updated_case


def close_match_case(
    case_conn,
    *,
    recommendation_conn=None,
    case_id: str,
    close_reason: str = "handoff_completed",
    now: datetime | None = None,
    actor_type: str = "system",
    close_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    _, rec_conn = _pair(case_conn, recommendation_conn)
    case = get_match_case(case_conn, case_id, recommendation_conn=recommendation_conn)
    if not case:
        raise ValueError(f"Unknown match case: {case_id}")
    if case["case_status"] not in {"accepted", "awaiting_reply", "pending_outreach"}:
        raise ValueError("Only open match cases can be closed.")

    # FIX: 防御性处理订阅不存在的情况（孤儿 match case）
    try:
        subscription = get_subscription(rec_conn, case["subscription_id"])
    except ValueError as e:
        if "Unknown subscription" in str(e):
            subscription = {
                "subscription_id": case["subscription_id"],
                "requester_id": case.get("requester_id"),
                "source": "orphan_subscription",
                "title": "已删除的订阅",
            }
        else:
            raise
    recommendation = get_recommendation(rec_conn, case["subscription_id"], int(case["candidate_id"]))
    if close_reason == "handoff_completed":
        delivery_status = "escalated_to_case"
        delivery_reason = "proxy_intro_handoff_completed"
        cooling_until = None
    elif close_reason == "requester_cancelled":
        delivery_status = "saved_by_user"
        delivery_reason = "proxy_intro_requester_cancelled"
        cooling_until = None
    elif close_reason == "delivery_failed":
        delivery_status = "cooled_down"
        delivery_reason = "proxy_intro_delivery_failed"
        cooling_until = now + timedelta(days=DEFAULT_TIMEOUT_COOLDOWN_DAYS)
    elif close_reason == "duplicate_merged":
        delivery_status = "saved_by_user"
        delivery_reason = "proxy_intro_duplicate_merged"
        cooling_until = None
    else:
        delivery_status = "escalated_to_case"
        delivery_reason = close_reason
        cooling_until = None

    case_conn.execute(
        f"""
        UPDATE {_t().cases}
        SET case_status = 'closed',
            close_reason = ?,
            cooling_until = ?,
            updated_at = ?
        WHERE case_id = ?
        """,
        (
            close_reason,
            format_dt(cooling_until),
            format_dt(now),
            case_id,
        ),
    )
    if recommendation:
        _sync_recommendation_for_case(
            rec_conn,
            recommendation=recommendation,
            case_id=None,
            case_status=None,
            delivery_status=delivery_status,
            delivery_reason=delivery_reason,
            cooling_until=cooling_until,
            active=False,
            now=now,
        )
        # FIX: 仅在推荐数据存在时记录推荐动作
        if recommendation:
            insert_recommendation_action(
                rec_conn,
                subscription=subscription,
                recommendation=recommendation,
                action_type=f"proxy_intro_closed_{close_reason}",
                actor_type=actor_type,
                actor_id="system" if actor_type == "system" else str(case["requester_id"]),
                now=now,
                action_payload=close_payload or {},
            )
    _record_case_event(
        case_conn,
        recommendation_conn=recommendation_conn,
        case=case,
        event_type="case_closed",
        actor_type=actor_type,
        from_status=case["case_status"],
        to_status="closed",
        now=now,
        payload=close_payload or {"close_reason": close_reason},
    )
    commit_proxy_intro_transaction(case_conn, recommendation_conn)
    return get_match_case(case_conn, case_id, recommendation_conn=recommendation_conn)


def close_timed_out_match_cases(
    case_conn,
    *,
    recommendation_conn=None,
    now: datetime | None = None,
    case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    if case_ids:
        case_ids = list(case_ids)
        placeholders = ", ".join(["?"] * len(case_ids))
        rows = case_conn.execute(
            f"""
            SELECT *
            FROM {_t().cases}
            WHERE case_status = 'awaiting_reply'
              AND case_id IN ({placeholders})
              AND reply_deadline_at <= ?
            ORDER BY reply_deadline_at ASC, case_id ASC
            """,
            [*case_ids, format_dt(now)],
        ).fetchall()
    else:
        rows = case_conn.execute(
            f"""
            SELECT *
            FROM {_t().cases}
            WHERE case_status = 'awaiting_reply'
              AND reply_deadline_at <= ?
            ORDER BY reply_deadline_at ASC, case_id ASC
            """,
            (format_dt(now),),
        ).fetchall()

    _, rec_conn = _pair(case_conn, recommendation_conn)
    timed_out_cases = []
    for row in rows:
        case = inflate_match_case(
            row_to_dict(row),
            conn=case_conn,
            recommendation_conn=recommendation_conn,
        )
        cooling_until = now + timedelta(days=DEFAULT_TIMEOUT_COOLDOWN_DAYS)
        case_conn.execute(
            f"""
            UPDATE {_t().cases}
            SET case_status = 'timed_out',
                close_reason = 'reply_timeout',
                cooling_until = ?,
                updated_at = ?
            WHERE case_id = ?
            """,
            (
                format_dt(cooling_until),
                format_dt(now),
                case["case_id"],
            ),
        )
        recommendation = get_recommendation(rec_conn, case["subscription_id"], int(case["candidate_id"]))
        if recommendation:
            # FIX: 防御性处理订阅不存在的情况（孤儿 match case）
            try:
                subscription = get_subscription(rec_conn, case["subscription_id"])
            except ValueError as e:
                if "Unknown subscription" in str(e):
                    subscription = {
                        "subscription_id": case["subscription_id"],
                        "requester_id": case.get("requester_id"),
                        "source": "orphan_subscription",
                        "title": "已删除的订阅",
                    }
                else:
                    raise
            _sync_recommendation_for_case(
                rec_conn,
                recommendation=recommendation,
                case_id=None,
                case_status=None,
                delivery_status="cooled_down",
                delivery_reason="proxy_intro_timed_out",
                cooling_until=cooling_until,
                active=False,
                now=now,
            )
            insert_recommendation_action(
                rec_conn,
                subscription=subscription,
                recommendation=recommendation,
                action_type="proxy_intro_timed_out",
                actor_type="system",
                actor_id="system",
                now=now,
                action_payload={"reason": "reply_deadline_elapsed"},
            )
        _record_case_event(
            case_conn,
            recommendation_conn=recommendation_conn,
            case=case,
            event_type="case_timed_out",
            actor_type="system",
            from_status="awaiting_reply",
            to_status="timed_out",
            now=now,
            payload={"reason": "reply_deadline_elapsed"},
        )
        timed_out_cases.append(
            get_match_case(case_conn, case["case_id"], recommendation_conn=recommendation_conn)
        )
    commit_proxy_intro_transaction(case_conn, recommendation_conn)
    return {"timed_out_count": len(timed_out_cases), "cases": timed_out_cases}


def cleanup_orphan_match_cases(conn, *, recommendation_conn=None) -> dict[str, Any]:
    """清理订阅已删除的孤儿 match case。

    当订阅被删除后，match case 数据可能仍然引用已删除的 subscription_id，
    导致用户回复/关闭时出现"Unknown subscription"错误。

    此函数会删除所有引用不存在订阅的 match case。

    Args:
        conn: matchmaking database connection
        recommendation_conn: recommendation database connection (optional)

    Returns:
        dict: {"deleted_case_count": 删除的case数量, "updated_recommendation_count": 更新的推荐数量}
    """
    _, rec_conn = _pair(conn, recommendation_conn)

    # 找出所有孤儿 match case（subscription_id 不在 saved_search_subscriptions 表中）
    orphan_cases = conn.execute(
        f"""
        SELECT case_id, subscription_id, requester_id, candidate_id, case_status
        FROM {_t().cases}
        WHERE subscription_id NOT IN (
            SELECT subscription_id FROM saved_search_subscriptions WHERE status = 'active'
        )
          AND case_status IN ('awaiting_reply', 'viewed', 'accepted', 'pending_outreach')
        """
    ).fetchall()

    deleted_case_count = 0
    updated_recommendation_count = 0

    for row in orphan_cases:
        case = row_to_dict(row)
        case_id = str(case.get("case_id") or "")

        # 关闭孤儿 case（标记为 closed）
        conn.execute(
            f"""
            UPDATE {_t().cases}
            SET case_status = 'closed',
                close_reason = 'orphan_subscription_deleted',
                updated_at = ?
            WHERE case_id = ?
            """,
            (format_dt(current_time()), case_id),
        )
        deleted_case_count += 1

        # 同步更新推荐状态（如果有推荐数据）
        try:
            recommendation = get_recommendation(
                rec_conn,
                str(case.get("subscription_id") or ""),
                int(case.get("candidate_id") or 0),
            )
            if recommendation:
                rec_conn.execute(
                    """
                    UPDATE profile_recommendations
                    SET active_match_case_id = NULL,
                        active_case_status = NULL,
                        delivery_status = 'cooled_down',
                        delivery_reason = 'orphan_subscription_deleted'
                    WHERE recommendation_id = ?
                    """,
                    (int(recommendation.get("recommendation_id") or 0),),
                )
                updated_recommendation_count += 1
        except Exception:
            # 推荐数据不存在时跳过
            pass

    commit_proxy_intro_transaction(conn, rec_conn)

    from observability import metric_gauge
    metric_gauge("matchmaking.cleanup.orphan_cases", deleted_case_count)
    metric_gauge("matchmaking.cleanup.updated_recommendations", updated_recommendation_count)

    return {
        "deleted_case_count": deleted_case_count,
        "updated_recommendation_count": updated_recommendation_count,
    }
