"""In-app recommendation card listing, marking read, and delivery batching."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Iterable

from her_time_utils import current_time, format_dt
from observability import RECOMMENDATION_FUNNEL_DELIVERED, funnel_stage, metric_gauge

from .storage import json_dumps, json_loads, row_to_dict


def list_in_app_cards(conn, requester_id: int | None = None, unread_only: bool = False) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if requester_id is not None:
        clauses.append("c.requester_id = ?")
        params.append(requester_id)
    if unread_only:
        clauses.append("c.card_status = 'unread'")
    clauses.append("(r.recommendation_id IS NULL OR (r.delivery_status != 'escalated_to_case' AND COALESCE(r.active_match_case_id, '') = ''))")
    where_clause = ""
    if clauses:
        where_clause = "WHERE " + " AND ".join(clauses)
    rows = conn.execute(
        f"""
        SELECT c.*
        FROM in_app_recommendation_cards AS c
        LEFT JOIN profile_recommendations AS r
          ON r.recommendation_id = c.recommendation_id
        {where_clause}
        ORDER BY c.delivered_at DESC, c.card_id DESC
        """,
        params,
    ).fetchall()
    cards = []
    for row in rows:
        card = row_to_dict(row)
        card["payload"] = json_loads(card.pop("payload_json"), {})
        cards.append(card)
    return cards


def mark_in_app_cards_read(
    conn,
    *,
    requester_id: int,
    card_ids: list[str],
    now: datetime | None = None,
) -> dict[str, Any]:
    from .recommendation_transactions import commit_recommendation_transaction

    now = current_time(now)
    ts = format_dt(now)
    updated = 0
    for raw in card_ids:
        cid = str(raw).strip()
        if not cid:
            continue
        res = conn.execute(
            """
            UPDATE in_app_recommendation_cards
            SET card_status = 'read', read_at = ?
            WHERE card_id = ? AND requester_id = ?
            """,
            (ts, cid, int(requester_id)),
        )
        updated += res.rowcount
    commit_recommendation_transaction(conn)
    return {"updated_count": updated, "requester_id": int(requester_id)}


def within_quiet_hours(now: datetime, quiet_hours_start: int, quiet_hours_end: int) -> bool:
    if quiet_hours_start == quiet_hours_end:
        return False
    if quiet_hours_start < quiet_hours_end:
        return quiet_hours_start <= now.hour < quiet_hours_end
    return now.hour >= quiet_hours_start or now.hour < quiet_hours_end


def day_bounds(now: datetime) -> tuple[datetime, datetime]:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start, day_start + timedelta(days=1)


def count_cards_delivered_today(conn, requester_id: int, now: datetime) -> int:
    return count_cards_delivered_today_by_requesters(conn, [requester_id], now=now).get(
        int(requester_id),
        0,
    )


def count_cards_delivered_today_by_requesters(
    conn,
    requester_ids: Iterable[int],
    *,
    now: datetime,
) -> dict[int, int]:
    normalized = [int(item) for item in requester_ids]
    if not normalized:
        return {}
    day_start, day_end = day_bounds(now)
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT requester_id, COUNT(*) AS delivered_count
        FROM in_app_recommendation_cards
        WHERE requester_id IN ({placeholders})
          AND delivered_at >= ?
          AND delivered_at < ?
        GROUP BY requester_id
        """,
        [*normalized, format_dt(day_start), format_dt(day_end)],
    ).fetchall()
    counts = {requester_id: 0 for requester_id in normalized}
    for row in rows:
        counts[int(row["requester_id"])] = int(row["delivered_count"])
    return counts


def recommendation_verified_label(payload: dict[str, Any], profile: dict[str, Any]) -> str | None:
    from match_domain.trust_summary import build_trust_summary

    trust = build_trust_summary(profile, payload=payload)
    if trust.verified_label:
        return trust.verified_label
    label = payload.get("verified_label")
    if label:
        return str(label)
    return None


def recommendation_photo_verification_label(payload: dict[str, Any], profile: dict[str, Any]) -> str | None:
    from match_domain.trust_summary import build_trust_summary

    trust = build_trust_summary(profile, payload=payload)
    if trust.photo_verification_label:
        return trust.photo_verification_label
    label = payload.get("photo_verification_label")
    if label:
        return str(label)
    return None


def recommendation_trust_headline(payload: dict[str, Any], profile: dict[str, Any]) -> str | None:
    from match_domain.trust_summary import build_trust_summary

    trust = build_trust_summary(profile, payload=payload)
    if trust.headline:
        return trust.headline
    return recommendation_verified_label(payload, profile)


def build_in_app_card(recommendation: dict[str, Any], subscription_title: str) -> dict[str, Any]:
    payload = recommendation.get("latest_payload") or {}
    profile = payload.get("profile") or {}
    matched_on = payload.get("matched_on") or []
    risk_flags = payload.get("risk_flags") or []
    follow_up_questions = payload.get("follow_up_questions") or []
    caution_items = payload.get("caution_items") or []
    trust_actions = payload.get("trust_actions") or []
    trust_headline = recommendation_trust_headline(payload, profile)
    verified_label = recommendation_verified_label(payload, profile)
    photo_label = recommendation_photo_verification_label(payload, profile)

    title = f"发现新的合适对象：{payload.get('name') or recommendation.get('candidate_name')}"
    subtitle_parts = [
        subscription_title,
        f"score={payload.get('score', recommendation.get('score', 0))}",
        f"{profile.get('age', '未知')}岁",
        profile.get("city") or "城市未知",
    ]
    if profile.get("job"):
        subtitle_parts.append(profile.get("job"))
    if photo_label:
        subtitle_parts.append(photo_label)
    if verified_label:
        subtitle_parts.append(verified_label)

    body_lines = []
    if trust_headline:
        body_lines.append("可信度：" + trust_headline)
    if caution_items:
        body_lines.append("谨慎点：" + "；".join(str(item) for item in caution_items[:2]))
    if matched_on:
        body_lines.append("匹配点：" + "；".join(matched_on[:3]))
    if risk_flags:
        body_lines.append("风险点：" + "；".join(risk_flags[:2]))
    if follow_up_questions:
        body_lines.append("建议确认：" + "；".join(follow_up_questions[:2]))
    if trust_actions:
        body_lines.append("建议先做：" + "；".join(str(item) for item in trust_actions[:2]))
    if not body_lines:
        body_lines.append("命中了订阅条件，建议进入资料页继续确认。")

    return {
        "card_type": "partner_recommendation",
        "title": title,
        "subtitle": " | ".join(str(part) for part in subtitle_parts if part),
        "body": "\n".join(body_lines),
        "cta_actions": [
            {"id": "save", "label": "先收藏"},
            {"id": "skip", "label": "先跳过"},
        ],
        "result_snapshot": payload,
        "rule_provenance": recommendation.get("rule_provenance") or {},
    }


def _row_within_quiet_hours(row_dict: dict[str, Any], now: datetime) -> bool:
    return within_quiet_hours(
        now,
        int(row_dict["quiet_hours_start"]),
        int(row_dict["quiet_hours_end"]),
    )


def deliver_in_app_recommendations(conn, *, now: datetime | None = None) -> dict[str, Any]:
    from .recommendation_rows import (
        append_relation_state_revision_event,
        inflate_recommendation,
        list_recommendation_actions_for_recommendations,
    )
    from .recommendation_transactions import commit_recommendation_transaction
    from .subscriptions import generate_card_id

    now = current_time(now)
    rows = conn.execute(
        """
        SELECT
          r.*,
          s.title AS subscription_title,
          s.source,
          s.self_id,
          s.daily_notification_cap,
          s.quiet_hours_start,
          s.quiet_hours_end,
          s.subscription_overrides_json
        FROM profile_recommendations AS r
        JOIN saved_search_subscriptions AS s
          ON s.subscription_id = r.subscription_id
        WHERE r.delivery_status = 'pending_delivery'
          AND s.status = 'active'
          AND s.is_still_searching = 1
        ORDER BY r.requester_id ASC, r.score DESC, r.first_seen_at ASC
        """
    ).fetchall()

    row_dicts = [row_to_dict(raw_row) for raw_row in rows]
    recommendation_ids = [
        int(row_dict["recommendation_id"])
        for row_dict in row_dicts
        if row_dict.get("recommendation_id") is not None
    ]
    actions_by_recommendation_id = list_recommendation_actions_for_recommendations(
        conn,
        recommendation_ids,
    )
    requester_ids = {
        int(row_dict["requester_id"])
        for row_dict in row_dicts
        if row_dict.get("requester_id") is not None
    }
    delivered_today_cache = count_cards_delivered_today_by_requesters(
        conn,
        requester_ids,
        now=now,
    )

    delivered_count = 0
    held_quiet_hours = 0
    held_daily_cap = 0

    for row_dict in row_dicts:
        requester_id = int(row_dict["requester_id"])
        if _row_within_quiet_hours(row_dict, now):
            held_quiet_hours += 1
            continue

        delivered_today = delivered_today_cache.get(requester_id, 0)
        if delivered_today >= int(row_dict["daily_notification_cap"]):
            held_daily_cap += 1
            delivered_today_cache[requester_id] = delivered_today
            continue

        recommendation = inflate_recommendation(
            row_dict,
            conn=conn,
            preloaded_action_rows=actions_by_recommendation_id.get(
                int(row_dict["recommendation_id"]),
            ),
        )
        card = build_in_app_card(recommendation, recommendation["subscription_title"])
        card_id = generate_card_id()
        conn.execute(
            """
            INSERT INTO in_app_recommendation_cards (
              card_id,
              subscription_id,
              recommendation_id,
              requester_id,
              candidate_id,
              card_status,
              title,
              subtitle,
              body,
              payload_json,
              created_at,
              delivered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card_id,
                recommendation["subscription_id"],
                recommendation["recommendation_id"],
                requester_id,
                recommendation["candidate_id"],
                "unread",
                card["title"],
                card["subtitle"],
                card["body"],
                json_dumps(card),
                format_dt(now),
                format_dt(now),
            ),
        )
        conn.execute(
            """
            UPDATE profile_recommendations
            SET delivery_status = 'delivered',
                delivery_reason = 'in_app_card_created',
                notified_at = ?,
                latest_card_id = ?
            WHERE recommendation_id = ?
            """,
            (format_dt(now), card_id, recommendation["recommendation_id"]),
        )
        subscription_view = {
            "subscription_id": row_dict["subscription_id"],
            "requester_id": row_dict["requester_id"],
            "source": row_dict["source"],
            "self_id": row_dict.get("self_id"),
        }
        relation_state_row = dict(row_dict)
        relation_state_row["delivery_status"] = "delivered"
        relation_state_row["delivery_reason"] = "in_app_card_created"
        relation_state_row["notified_at"] = format_dt(now)
        relation_state_row["latest_card_id"] = card_id
        if relation_state_row:
            append_relation_state_revision_event(
                conn,
                subscription=subscription_view,
                recommendation_row=relation_state_row,
                now=now,
            )
        delivered_today_cache[requester_id] = delivered_today + 1
        delivered_count += 1
        funnel_stage(
            system="recommendation",
            stage=RECOMMENDATION_FUNNEL_DELIVERED,
            subscription_id=recommendation["subscription_id"],
            recommendation_id=int(recommendation["recommendation_id"]),
            candidate_id=int(recommendation["candidate_id"]),
            card_id=card_id,
        )

    commit_recommendation_transaction(conn)
    metric_gauge("recommendation.deliver.delivered_count", delivered_count)
    metric_gauge("recommendation.deliver.held_quiet_hours", held_quiet_hours)
    metric_gauge("recommendation.deliver.held_daily_cap", held_daily_cap)
    return {
        "delivered_count": delivered_count,
        "held_quiet_hours": held_quiet_hours,
        "held_daily_cap": held_daily_cap,
    }


__all__ = [
    "build_in_app_card",
    "count_cards_delivered_today",
    "count_cards_delivered_today_by_requesters",
    "day_bounds",
    "deliver_in_app_recommendations",
    "list_in_app_cards",
    "mark_in_app_cards_read",
    "recommendation_photo_verification_label",
    "recommendation_trust_headline",
    "recommendation_verified_label",
    "within_quiet_hours",
]
