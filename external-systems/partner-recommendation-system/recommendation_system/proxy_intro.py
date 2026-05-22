"""Phase 4 proxy-introduction workflows layered on top of recommendations."""

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
from observability import RECOMMENDATION_FUNNEL_PROXY_INTRO, funnel_stage  # noqa: E402

from .service import (  # noqa: E402
    append_relation_state_revision_event,
    current_time,
    format_dt,
    get_recommendation,
    get_subscription,
    insert_recommendation_action,
    parse_dt,
)
from .storage import json_dumps, json_loads, row_to_dict


DEFAULT_OUTREACH_CHANNEL = "in_app_proxy_intro"
DEFAULT_REPLY_WINDOW_HOURS = 72
DEFAULT_DECLINE_COOLDOWN_DAYS = 180
DEFAULT_TIMEOUT_COOLDOWN_DAYS = 90

OPEN_CASE_STATUSES = {"pending_outreach", "awaiting_reply", "accepted"}
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


def build_outreach_payload(
    subscription: dict[str, Any],
    safe_summary: dict[str, Any],
    *,
    outreach_channel: str = DEFAULT_OUTREACH_CHANNEL,
) -> dict[str, Any]:
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


def inflate_match_case(case: dict[str, Any] | None, *, conn=None) -> dict[str, Any] | None:
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
    cid = inflated.get("case_id")
    ledger_events = []
    if conn is not None and cid:
        event_rows = list_match_case_events(conn, str(cid))
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


def get_match_case(conn, case_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM match_cases WHERE case_id = ?", (case_id,)).fetchone()
    return inflate_match_case(row_to_dict(row), conn=conn)


def list_match_cases_for_subscription(conn, subscription_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM match_cases
        WHERE subscription_id = ?
        ORDER BY created_at DESC, case_id DESC
        """,
        (subscription_id,),
    ).fetchall()
    return [inflate_match_case(row_to_dict(row), conn=conn) for row in rows]


def list_match_case_events(conn, case_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM match_case_events
        WHERE case_id = ?
        ORDER BY occurred_at ASC, event_id ASC
        """,
        (case_id,),
    ).fetchall()
    return [inflate_match_case_event(row_to_dict(row)) for row in rows]


def list_match_case_outreach_attempts(conn, case_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM match_case_outreach_attempts
        WHERE case_id = ?
        ORDER BY sent_at ASC, attempt_id ASC
        """,
        (case_id,),
    ).fetchall()
    return [inflate_match_case_attempt(row_to_dict(row)) for row in rows]


def list_match_cases_for_recommendation(conn, recommendation_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM match_cases
        WHERE recommendation_id = ?
        ORDER BY created_at DESC, case_id DESC
        """,
        (recommendation_id,),
    ).fetchall()
    return [inflate_match_case(row_to_dict(row), conn=conn) for row in rows]


def get_latest_match_case_for_recommendation(conn, recommendation_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM match_cases
        WHERE recommendation_id = ?
        ORDER BY created_at DESC, case_id DESC
        LIMIT 1
        """,
        (recommendation_id,),
    ).fetchone()
    return inflate_match_case(row_to_dict(row), conn=conn)


def get_active_match_case_for_recommendation(conn, recommendation_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM match_cases
        WHERE recommendation_id = ?
          AND case_status IN ('pending_outreach', 'awaiting_reply', 'accepted')
        ORDER BY created_at DESC, case_id DESC
        LIMIT 1
        """,
        (recommendation_id,),
    ).fetchone()
    return inflate_match_case(row_to_dict(row), conn=conn)


def _record_case_event(
    conn,
    *,
    case: dict[str, Any],
    event_type: str,
    actor_type: str,
    from_status: str | None,
    to_status: str | None,
    now: datetime,
    payload: dict[str, Any] | None = None,
) -> None:
    event = build_case_aggregate_event(
        event_type=event_type,
        case_id=str(case["case_id"]),
        case_type=CaseType.PROXY_INTRO,
        source_service="recommendation-system",
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
    conn.execute(
        """
        INSERT INTO match_case_events (
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
        conn,
        event=event,
        source_row_table="match_case_events",
        source_row_id=conn.lastrowid or None,
        created_at_str=occurred_str,
    )


def _sync_recommendation_for_case(
    conn,
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
    conn.execute(
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
    row = conn.execute(
        "SELECT * FROM profile_recommendations WHERE recommendation_id = ?",
        (recommendation["recommendation_id"],),
    ).fetchone()
    rec_row = row_to_dict(row)
    if rec_row:
        subscription = get_subscription(conn, rec_row["subscription_id"])
        append_relation_state_revision_event(
            conn,
            subscription=subscription,
            recommendation_row=rec_row,
            now=_now,
        )


def create_match_case(
    conn,
    *,
    subscription_id: str,
    candidate_id: int,
    now: datetime | None = None,
    initiated_by: str = "requester",
    outreach_channel: str = DEFAULT_OUTREACH_CHANNEL,
    reply_window_hours: int = DEFAULT_REPLY_WINDOW_HOURS,
    request_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    subscription = get_subscription(conn, subscription_id)
    recommendation = get_recommendation(conn, subscription_id, int(candidate_id))
    if not recommendation:
        raise ValueError(f"Unknown recommendation for subscription={subscription_id} candidate_id={candidate_id}")
    if recommendation.get("delivery_status") in {"direct_greeted", "direct_greet_started"}:
        raise ValueError("Cannot request proxy intro after direct_greet has already started.")
    if recommendation.get("delivery_status") == "escalated_to_case" and not recommendation.get("active_match_case_id"):
        raise ValueError("Candidate already completed the proxy-intro flow.")

    active_case = get_active_match_case_for_recommendation(conn, recommendation["recommendation_id"])
    if active_case:
        raise ValueError(f"Candidate already has an active match case: {active_case['case_id']}")

    latest_case = get_latest_match_case_for_recommendation(conn, recommendation["recommendation_id"])
    if latest_case and latest_case["case_status"] == "accepted":
        raise ValueError("Candidate already accepted a proxy-intro case.")
    if latest_case and latest_case["case_status"] in {"declined", "timed_out"}:
        cooling_until = parse_dt(latest_case.get("cooling_until"))
        if cooling_until and now < cooling_until:
            raise ValueError("Candidate is still cooling down after the last proxy-intro case.")

    case_id = generate_case_id()
    safe_summary = build_safe_summary(subscription, recommendation)
    outreach_payload = build_outreach_payload(
        subscription,
        safe_summary,
        outreach_channel=outreach_channel,
    )
    reply_deadline_at = now + timedelta(hours=int(reply_window_hours or DEFAULT_REPLY_WINDOW_HOURS))
    requester_profile_snapshot = {
        "self_id": subscription.get("self_id"),
        "self_profile": json_loads(subscription.get("self_profile_json"), {}),
    }
    candidate_snapshot = dict(recommendation.get("latest_payload") or {})

    conn.execute(
        """
        INSERT INTO match_cases (
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
          created_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            format_dt(now),
            format_dt(now),
        ),
    )
    _record_case_event(
        conn,
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
        conn,
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
        conn,
        recommendation=recommendation,
        case_id=case_id,
        case_status="pending_outreach",
        delivery_status="escalated_to_case",
        delivery_reason="proxy_intro_requested",
        active=True,
        now=now,
    )
    conn.commit()
    funnel_stage(
        system="recommendation",
        stage=RECOMMENDATION_FUNNEL_PROXY_INTRO,
        subscription_id=subscription_id,
        case_id=case_id,
        recommendation_id=int(recommendation["recommendation_id"]),
        candidate_id=int(candidate_id),
        initiated_by=initiated_by,
    )
    return get_match_case(conn, case_id)


def _update_case_status(
    conn,
    *,
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
    reply_payload_json = json_dumps(reply_payload) if reply_payload is not None else None
    conn.execute(
        """
        UPDATE match_cases
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
        recommendation = get_recommendation(conn, case["subscription_id"], int(case["candidate_id"]))
        if recommendation:
            _sync_recommendation_for_case(
                conn,
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
        conn,
        case=case,
        event_type=event_type,
        actor_type=actor_type,
        from_status=case["case_status"],
        to_status=new_status,
        now=now,
        payload={"close_reason": close_reason, "reply_payload": reply_payload or {}},
    )
    return get_match_case(conn, case["case_id"])


def dispatch_match_case_outreach(
    conn,
    *,
    case_id: str,
    now: datetime | None = None,
    provider_message_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    case = get_match_case(conn, case_id)
    if not case:
        raise ValueError(f"Unknown match case: {case_id}")
    if case["case_status"] != "pending_outreach":
        raise ValueError("Only pending_outreach cases can be dispatched.")

    attempts = list_match_case_outreach_attempts(conn, case_id)
    attempt_number = len(attempts) + 1
    dispatch_payload = payload or case.get("outreach_payload") or {}
    conn.execute(
        """
        INSERT INTO match_case_outreach_attempts (
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
    conn.execute(
        """
        UPDATE match_cases
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
        conn,
        case=case,
        event_type="outreach_sent",
        actor_type="system",
        from_status="pending_outreach",
        to_status="awaiting_reply",
        now=now,
        payload=dispatch_payload,
    )
    recommendation = get_recommendation(conn, case["subscription_id"], int(case["candidate_id"]))
    if recommendation:
        _sync_recommendation_for_case(
            conn,
            recommendation=recommendation,
            case_id=case["case_id"],
            case_status="awaiting_reply",
            delivery_status="escalated_to_case",
            delivery_reason="proxy_intro_outreach_sent",
            active=True,
            now=now,
        )
    conn.commit()
    return get_match_case(conn, case_id)


def dispatch_pending_match_cases(
    conn,
    *,
    now: datetime | None = None,
    case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    if case_ids:
        case_ids = list(case_ids)
        placeholders = ", ".join(["?"] * len(case_ids))
        rows = conn.execute(
            f"""
            SELECT *
            FROM match_cases
            WHERE case_status = 'pending_outreach'
              AND case_id IN ({placeholders})
            ORDER BY created_at ASC, case_id ASC
            """,
            case_ids,
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM match_cases
            WHERE case_status = 'pending_outreach'
            ORDER BY created_at ASC, case_id ASC
            """
        ).fetchall()
    cases = [inflate_match_case(row_to_dict(row), conn=conn) for row in rows]
    dispatched = []
    for case in cases:
        dispatched.append(dispatch_match_case_outreach(conn, case_id=case["case_id"], now=now))
    return {"dispatched_count": len(dispatched), "cases": dispatched}


def record_match_case_reply(
    conn,
    *,
    case_id: str,
    reply_type: str,
    now: datetime | None = None,
    reply_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    case = get_match_case(conn, case_id)
    if not case:
        raise ValueError(f"Unknown match case: {case_id}")
    if case["case_status"] != "awaiting_reply":
        raise ValueError("Replies can only be recorded after outreach is awaiting reply.")

    reply_type = str(reply_type).strip().lower()
    if reply_type not in {"accepted", "declined"}:
        raise ValueError(f"Unsupported reply_type: {reply_type}")
    subscription = get_subscription(conn, case["subscription_id"])
    recommendation = get_recommendation(conn, case["subscription_id"], int(case["candidate_id"]))

    if reply_type == "accepted":
        updated_case = _update_case_status(
            conn,
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
        insert_recommendation_action(
            conn,
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
            conn,
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
        insert_recommendation_action(
            conn,
            subscription=subscription,
            recommendation=recommendation,
            action_type="proxy_intro_reply_declined",
            actor_type="candidate",
            actor_id=str(case["candidate_id"]),
            now=now,
            action_payload=reply_payload or {},
        )
    conn.commit()
    return updated_case


def close_match_case(
    conn,
    *,
    case_id: str,
    close_reason: str = "handoff_completed",
    now: datetime | None = None,
    actor_type: str = "system",
    close_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    case = get_match_case(conn, case_id)
    if not case:
        raise ValueError(f"Unknown match case: {case_id}")
    if case["case_status"] not in {"accepted", "awaiting_reply", "pending_outreach"}:
        raise ValueError("Only open match cases can be closed.")

    subscription = get_subscription(conn, case["subscription_id"])
    recommendation = get_recommendation(conn, case["subscription_id"], int(case["candidate_id"]))
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

    conn.execute(
        """
        UPDATE match_cases
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
            conn,
            recommendation=recommendation,
            case_id=None,
            case_status=None,
            delivery_status=delivery_status,
            delivery_reason=delivery_reason,
            cooling_until=cooling_until,
            active=False,
            now=now,
        )
        insert_recommendation_action(
            conn,
            subscription=subscription,
            recommendation=recommendation,
            action_type=f"proxy_intro_closed_{close_reason}",
            actor_type=actor_type,
            actor_id="system" if actor_type == "system" else str(case["requester_id"]),
            now=now,
            action_payload=close_payload or {},
        )
    _record_case_event(
        conn,
        case=case,
        event_type="case_closed",
        actor_type=actor_type,
        from_status=case["case_status"],
        to_status="closed",
        now=now,
        payload=close_payload or {"close_reason": close_reason},
    )
    conn.commit()
    return get_match_case(conn, case_id)


def close_timed_out_match_cases(
    conn,
    *,
    now: datetime | None = None,
    case_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    now = current_time(now)
    if case_ids:
        case_ids = list(case_ids)
        placeholders = ", ".join(["?"] * len(case_ids))
        rows = conn.execute(
            f"""
            SELECT *
            FROM match_cases
            WHERE case_status = 'awaiting_reply'
              AND case_id IN ({placeholders})
              AND reply_deadline_at <= ?
            ORDER BY reply_deadline_at ASC, case_id ASC
            """,
            [*case_ids, format_dt(now)],
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM match_cases
            WHERE case_status = 'awaiting_reply'
              AND reply_deadline_at <= ?
            ORDER BY reply_deadline_at ASC, case_id ASC
            """,
            (format_dt(now),),
        ).fetchall()

    timed_out_cases = []
    for row in rows:
        case = inflate_match_case(row_to_dict(row), conn=conn)
        cooling_until = now + timedelta(days=DEFAULT_TIMEOUT_COOLDOWN_DAYS)
        conn.execute(
            """
            UPDATE match_cases
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
        recommendation = get_recommendation(conn, case["subscription_id"], int(case["candidate_id"]))
        if recommendation:
            subscription = get_subscription(conn, case["subscription_id"])
            _sync_recommendation_for_case(
                conn,
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
                conn,
                subscription=subscription,
                recommendation=recommendation,
                action_type="proxy_intro_timed_out",
                actor_type="system",
                actor_id="system",
                now=now,
                action_payload={"reason": "reply_deadline_elapsed"},
            )
        _record_case_event(
            conn,
            case=case,
            event_type="case_timed_out",
            actor_type="system",
            from_status="awaiting_reply",
            to_status="timed_out",
            now=now,
            payload={"reason": "reply_deadline_elapsed"},
        )
        timed_out_cases.append(get_match_case(conn, case["case_id"]))
    conn.commit()
    return {"timed_out_count": len(timed_out_cases), "cases": timed_out_cases}
