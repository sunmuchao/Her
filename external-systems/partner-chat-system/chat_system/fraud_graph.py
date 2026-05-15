"""Hashed entity graph and cluster scoring for deep anti-fraud detection."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from datetime import datetime, timedelta
from typing import Any, Iterable

from her_time_utils import as_text as _as_text, current_time, unique_ordered_texts as _unique_ordered

from partner_moderation import (
    ACTION_FREEZE,
    ACTION_LIMIT_CHAT,
    ACTION_REQUIRE_VERIFICATION,
    ACTION_WARN,
    get_active_moderation_state,
    infer_required_verifications,
    parse_source_ref,
    upsert_moderation_state,
)

from .storage import inflate_json_columns, json_dumps, json_loads, row_to_dict

NETWORK_STATUS_CLEAN = "clean"
NETWORK_STATUS_WATCH = "watch"
NETWORK_STATUS_UNDER_REVIEW = "under_review"
NETWORK_STATUS_ACTION_APPLIED = "action_applied"

ENTITY_TYPE_WEIGHTS = {
    "device_fingerprint": 50,
    "external_contact": 45,
    "payment_handle": 45,
    "avatar_fingerprint": 35,
    "image_fingerprint": 30,
    "ip_address": 25,
    "session_fingerprint": 22,
    "ip_segment": 18,
    "message_pattern": 15,
    "registration_path": 12,
    "user_agent": 10,
    "login_city": 8,
}

NETWORK_REVIEWABLE_ACTIONS = {
    ACTION_REQUIRE_VERIFICATION,
    ACTION_LIMIT_CHAT,
    ACTION_FREEZE,
}

RECENT_SIGNAL_WINDOW_DAYS = 30
ENTITY_RETENTION_DAYS = 90
MAX_LINKED_SUBJECTS = 50
MAX_PROPAGATION_SUBJECTS = 10

CONTACT_MARKER_PATTERNS = (
    ("wechat", re.compile(r"(?:微信|vx|v信|wechat)[号是为:：\s\-]*([a-zA-Z][a-zA-Z0-9_\-]{4,31})", re.IGNORECASE)),
    ("telegram", re.compile(r"(?:telegram|tg)[号是为:：\s\-]*([a-zA-Z0-9_]{3,32})", re.IGNORECASE)),
    ("whatsapp", re.compile(r"(?:whatsapp|wa)[号是为:：\s\-]*([a-zA-Z0-9_]{3,32})", re.IGNORECASE)),
    ("line", re.compile(r"(?:line)[号是为:：\s\-]*([a-zA-Z0-9_]{3,32})", re.IGNORECASE)),
)
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
CN_PHONE_PATTERN = re.compile(r"(?<!\d)1\d{10}(?!\d)")
NORMALIZE_BODY_PATTERN = re.compile(r"[，,。.!！?？:：;；\-_/\\|]+")


def _coerce_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _normalize_message_pattern(body: str) -> str:
    text = _as_text(body).lower()
    if not text:
        return ""
    text = re.sub(r"\d+", "#", text)
    text = re.sub(r"\s+", "", text)
    text = NORMALIZE_BODY_PATTERN.sub("", text)
    return text[:96]


def _hash_token(entity_type: str, raw_value: str) -> str:
    return hashlib.sha256(f"{entity_type}:{raw_value}".encode("utf-8")).hexdigest()


def _entity_hint(entity_type: str, raw_value: str) -> str:
    normalized = _as_text(raw_value)
    if not normalized:
        return ""
    if entity_type == "ip_segment":
        if "." in normalized:
            parts = normalized.split(".")
            if len(parts) >= 3:
                return f"{parts[0]}.{parts[1]}.{parts[2]}.*"
        return "ipv6-segment"
    if entity_type == "external_contact":
        head = normalized.split(":", 1)[0] if ":" in normalized else "contact"
        tail = normalized[-4:] if len(normalized) >= 4 else normalized
        return f"{head}:*{tail}"
    return f"sha:{_hash_token(entity_type, normalized)[:12]}"


def _normalize_ip_segment(raw_ip: str) -> str | None:
    value = _as_text(raw_ip)
    if not value:
        return None
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return None
    if parsed.version == 4:
        network = ipaddress.ip_network(f"{parsed}/24", strict=False)
    else:
        network = ipaddress.ip_network(f"{parsed}/64", strict=False)
    return str(network.network_address)


def _normalize_contact_handle(raw: Any) -> str | None:
    value = _as_text(raw).lower().replace(" ", "")
    if not value:
        return None
    if EMAIL_PATTERN.fullmatch(value):
        return f"email:{value}"
    if CN_PHONE_PATTERN.fullmatch(value):
        return f"phone:{value}"
    if ":" in value:
        head, tail = value.split(":", 1)
        head = head.strip()
        tail = tail.strip()
        if head and tail:
            return f"{head}:{tail}"
    return value


def _extract_contact_handles(*texts: str) -> list[str]:
    found: list[str] = []
    for raw_text in texts:
        text = _as_text(raw_text)
        if not text:
            continue
        for match in EMAIL_PATTERN.findall(text):
            found.append(f"email:{match.lower()}")
        for match in CN_PHONE_PATTERN.findall(text):
            found.append(f"phone:{match}")
        for prefix, pattern in CONTACT_MARKER_PATTERNS:
            for match in pattern.findall(text):
                normalized = _normalize_contact_handle(f"{prefix}:{match}")
                if normalized:
                    found.append(normalized)
    return _unique_ordered(found)


def _risk_sources(evidence: dict[str, Any] | None) -> list[dict[str, Any]]:
    base = _coerce_dict(evidence)
    sources = [base]
    nested = base.get("risk_observation")
    if isinstance(nested, dict):
        sources.append(dict(nested))
    message_meta = base.get("message_metadata")
    if isinstance(message_meta, dict):
        sources.append(dict(message_meta))
        nested_meta = message_meta.get("risk_observation")
        if isinstance(nested_meta, dict):
            sources.append(dict(nested_meta))
    return sources


def _append_entity(
    entity_map: dict[tuple[str, str], dict[str, Any]],
    entity_type: str,
    raw_value: Any,
) -> None:
    normalized = _as_text(raw_value)
    if not normalized:
        return
    hashed = _hash_token(entity_type, normalized)
    key = (entity_type, hashed)
    entity_map.setdefault(
        key,
        {
            "entity_type": entity_type,
            "entity_hash": hashed,
            "entity_key_hint": _entity_hint(entity_type, normalized),
            "entity_weight": int(ENTITY_TYPE_WEIGHTS.get(entity_type, 10)),
        },
    )


def _collect_entity_candidates(
    *,
    evidence: dict[str, Any] | None,
    message_body: str | None,
    signal_codes: Iterable[Any] | None,
) -> list[dict[str, Any]]:
    sources = _risk_sources(evidence)
    signal_code_set = set(_unique_ordered(signal_codes or []))
    entity_map: dict[tuple[str, str], dict[str, Any]] = {}
    text_for_contacts = [_as_text(message_body), _as_text((evidence or {}).get("reason_text"))]

    for source in sources:
        for field_name in ("device_fingerprint", "device_hash", "device_id"):
            _append_entity(entity_map, "device_fingerprint", source.get(field_name))
        for field_name in ("session_fingerprint", "session_id", "session_stability_key"):
            _append_entity(entity_map, "session_fingerprint", source.get(field_name))
        for field_name in ("user_agent", "ua"):
            _append_entity(entity_map, "user_agent", source.get(field_name))
        for field_name in ("registration_path", "signup_channel", "registration_channel"):
            _append_entity(entity_map, "registration_path", source.get(field_name))
        for field_name in ("login_city", "login_location"):
            _append_entity(entity_map, "login_city", source.get(field_name))
        for field_name in ("avatar_fingerprint", "avatar_hash"):
            _append_entity(entity_map, "avatar_fingerprint", source.get(field_name))
        for field_name in ("image_fingerprint", "image_hash"):
            _append_entity(entity_map, "image_fingerprint", source.get(field_name))
        for raw_item in _coerce_list(source.get("image_fingerprints")):
            _append_entity(entity_map, "image_fingerprint", raw_item)
        for field_name in ("payment_handle",):
            _append_entity(entity_map, "payment_handle", source.get(field_name))
        for raw_item in _coerce_list(source.get("payment_handles")):
            _append_entity(entity_map, "payment_handle", raw_item)
        for field_name in ("client_ip", "ip_address", "ip"):
            value = _as_text(source.get(field_name))
            if not value:
                continue
            _append_entity(entity_map, "ip_address", value)
            segment = _normalize_ip_segment(value)
            if segment:
                _append_entity(entity_map, "ip_segment", segment)
        for raw_item in _coerce_list(source.get("external_contacts")):
            normalized = _normalize_contact_handle(raw_item)
            if normalized:
                _append_entity(entity_map, "external_contact", normalized)
        for raw_item in _coerce_list(source.get("contact_handles")):
            normalized = _normalize_contact_handle(raw_item)
            if normalized:
                _append_entity(entity_map, "external_contact", normalized)
        for raw_item in _coerce_list(source.get("contact_variants")):
            normalized = _normalize_contact_handle(raw_item)
            if normalized:
                _append_entity(entity_map, "external_contact", normalized)
        text_for_contacts.append(_as_text(source.get("notes")))
        explicit_pattern = _as_text(source.get("message_pattern") or source.get("template_text"))
        if explicit_pattern:
            _append_entity(entity_map, "message_pattern", explicit_pattern)

    for contact in _extract_contact_handles(*text_for_contacts):
        _append_entity(entity_map, "external_contact", contact)

    normalized_body = _normalize_message_pattern(_as_text(message_body))
    if normalized_body and len(normalized_body) >= 8:
        _append_entity(entity_map, "message_pattern", normalized_body)
    if {"repeated_opening", "high_frequency_outreach"} & signal_code_set and normalized_body:
        _append_entity(entity_map, "message_pattern", normalized_body)

    return list(entity_map.values())


def _inflate_account_link(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(
        row,
        shared_entity_types=("shared_entity_types_json", []),
        shared_signal_codes=("shared_signal_codes_json", []),
        evidence=("evidence_json", {}),
    )


def _inflate_network_profile(row: dict[str, Any] | None) -> dict[str, Any] | None:
    return inflate_json_columns(
        row,
        shared_entity_type_counts=("shared_entity_type_counts_json", {}),
        signal_codes=("signal_codes_json", []),
        evidence=("evidence_json", {}),
    )


def _profile_ref_for_subject(
    conn,
    subject_user_id: str,
    *,
    source_dsn: str | None = None,
    source_table_name: str | None = None,
    profile_id: int | None = None,
) -> tuple[str | None, str | None, int | None]:
    normalized_source, normalized_table = parse_source_ref(source_dsn, source_table_name)
    if normalized_source or normalized_table or profile_id is not None:
        return normalized_source, normalized_table, profile_id
    row = conn.execute(
        """
        SELECT source_dsn, source_table_name, profile_id
        FROM chat_risk_network_profiles
        WHERE subject_user_id = ?
        LIMIT 1
        """,
        (subject_user_id,),
    ).fetchone()
    if row:
        item = row_to_dict(row)
        return item.get("source_dsn"), item.get("source_table_name"), item.get("profile_id")
    row = conn.execute(
        """
        SELECT source_dsn, source_table_name, profile_id
        FROM chat_risk_entity_links
        WHERE subject_user_id = ?
          AND profile_id IS NOT NULL
          AND source_dsn IS NOT NULL
          AND source_table_name IS NOT NULL
        ORDER BY last_seen_at DESC, entity_link_id DESC
        LIMIT 1
        """,
        (subject_user_id,),
    ).fetchone()
    if not row:
        return None, None, None
    item = row_to_dict(row)
    return item.get("source_dsn"), item.get("source_table_name"), item.get("profile_id")


def _recent_subject_signal_codes(conn, subject_user_id: str, *, now: datetime) -> list[str]:
    rows = conn.execute(
        """
        SELECT signal_code
        FROM chat_risk_signals
        WHERE subject_user_id = ?
          AND created_at >= ?
        ORDER BY created_at DESC, signal_id DESC
        LIMIT 200
        """,
        (subject_user_id, now - timedelta(days=RECENT_SIGNAL_WINDOW_DAYS)),
    ).fetchall()
    return _unique_ordered(row_to_dict(row).get("signal_code") for row in rows if row)


def _account_link_rows(conn, subject_user_id: str, *, now: datetime) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
          other.subject_user_id AS linked_user_id,
          other.entity_type,
          other.entity_hash,
          other.entity_key_hint,
          other.entity_weight,
          other.signal_codes_json,
          other.last_seen_at
        FROM chat_risk_entity_links AS mine
        JOIN chat_risk_entity_links AS other
          ON other.entity_type = mine.entity_type
         AND other.entity_hash = mine.entity_hash
        WHERE mine.subject_user_id = ?
          AND other.subject_user_id <> ?
          AND mine.last_seen_at >= ?
          AND other.last_seen_at >= ?
        ORDER BY other.last_seen_at DESC, other.entity_weight DESC
        """,
        (
            subject_user_id,
            subject_user_id,
            now - timedelta(days=ENTITY_RETENTION_DAYS),
            now - timedelta(days=ENTITY_RETENTION_DAYS),
        ),
    ).fetchall()
    aggregated: dict[str, dict[str, Any]] = {}
    moderation_lookup = _active_moderation_action_map(
        conn,
        [_as_text(row_to_dict(row).get("linked_user_id")) for row in rows if row],
    )
    for raw_row in rows:
        row = row_to_dict(raw_row)
        linked_user_id = _as_text(row.get("linked_user_id"))
        if not linked_user_id:
            continue
        bucket = aggregated.setdefault(
            linked_user_id,
            {
                "linked_user_id": linked_user_id,
                "shared_entities": [],
                "shared_entity_types": set(),
                "shared_signal_codes": set(),
                "shared_entity_count": 0,
                "link_score": 0,
                "last_seen_at": row.get("last_seen_at"),
                "linked_active_action": moderation_lookup.get(linked_user_id),
            },
        )
        entity_key = (_as_text(row.get("entity_type")), _as_text(row.get("entity_hash")))
        seen_entity_keys = bucket.setdefault("_seen_entity_keys", set())
        if entity_key in seen_entity_keys:
            continue
        seen_entity_keys.add(entity_key)
        entity_type = _as_text(row.get("entity_type"))
        bucket["shared_entity_types"].add(entity_type)
        bucket["shared_entity_count"] += 1
        bucket["link_score"] += int(row.get("entity_weight") or ENTITY_TYPE_WEIGHTS.get(entity_type, 10))
        bucket["shared_entities"].append(
            {
                "entity_type": entity_type,
                "entity_key_hint": row.get("entity_key_hint"),
                "weight": int(row.get("entity_weight") or ENTITY_TYPE_WEIGHTS.get(entity_type, 10)),
            }
        )
        bucket["shared_signal_codes"].update(json_loads(row.get("signal_codes_json"), []))
        if row.get("last_seen_at") and (bucket.get("last_seen_at") is None or row.get("last_seen_at") > bucket.get("last_seen_at")):
            bucket["last_seen_at"] = row.get("last_seen_at")
    out: list[dict[str, Any]] = []
    for bucket in aggregated.values():
        bucket.pop("_seen_entity_keys", None)
        bucket["shared_entity_types"] = sorted(bucket["shared_entity_types"])
        bucket["shared_signal_codes"] = _unique_ordered(bucket["shared_signal_codes"])
        bucket["shared_entities"] = sorted(
            bucket["shared_entities"],
            key=lambda item: (-int(item.get("weight") or 0), _as_text(item.get("entity_type"))),
        )[:20]
        out.append(bucket)
    out.sort(key=lambda item: (-int(item.get("link_score") or 0), _as_text(item.get("linked_user_id"))))
    return out[:MAX_LINKED_SUBJECTS]


def _active_moderation_action_map(conn, subject_user_ids: Iterable[Any]) -> dict[str, str]:
    normalized = _unique_ordered(subject_user_ids)
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT subject_user_id, applied_action
        FROM account_moderation_states
        WHERE moderation_status = ?
          AND subject_user_id IN ({placeholders})
        ORDER BY updated_at DESC, state_id DESC
        """,
        ("active", *normalized),
    ).fetchall()
    out: dict[str, str] = {}
    for raw_row in rows:
        row = row_to_dict(raw_row)
        subject_user_id = _as_text(row.get("subject_user_id"))
        if subject_user_id and subject_user_id not in out:
            out[subject_user_id] = _as_text(row.get("applied_action"))
    return out


def _network_signal_codes(
    shared_entity_type_counts: dict[str, int],
    connected_subject_count: int,
    high_risk_neighbor_count: int,
    recent_signal_codes: Iterable[Any],
) -> list[str]:
    out: list[str] = []
    mapping = {
        "device_fingerprint": "shared_device_fingerprint",
        "ip_address": "shared_ip_address",
        "ip_segment": "shared_ip_segment",
        "user_agent": "shared_user_agent",
        "registration_path": "shared_registration_path",
        "session_fingerprint": "shared_session_fingerprint",
        "avatar_fingerprint": "shared_avatar_fingerprint",
        "image_fingerprint": "shared_image_fingerprint",
        "external_contact": "shared_external_contact",
        "payment_handle": "shared_payment_handle",
        "message_pattern": "shared_message_pattern",
        "login_city": "shared_login_city",
    }
    for entity_type, signal_code in mapping.items():
        if int(shared_entity_type_counts.get(entity_type) or 0) > 0:
            out.append(signal_code)
    if connected_subject_count >= 2:
        out.append("linked_account_cluster")
    if connected_subject_count >= 3:
        out.append("risk_ring_cluster")
    if high_risk_neighbor_count > 0:
        out.append("linked_to_flagged_account")
    if {"repeated_opening", "high_frequency_outreach"} & set(_unique_ordered(recent_signal_codes)):
        out.append("clustered_outreach_pattern")
    return _unique_ordered(out)


def _risk_score_for_network(
    account_links: list[dict[str, Any]],
    shared_entity_type_counts: dict[str, int],
    high_risk_neighbor_count: int,
    recent_signal_codes: Iterable[Any],
) -> int:
    top_link_score = sum(min(int(item.get("link_score") or 0), 80) for item in account_links[:5])
    connected_subject_count = len(account_links)
    score = top_link_score
    if connected_subject_count >= 2:
        score += 10
    if connected_subject_count >= 3:
        score += 25
    if int(shared_entity_type_counts.get("device_fingerprint") or 0) > 0 and connected_subject_count >= 2:
        score += 25
    if int(shared_entity_type_counts.get("external_contact") or 0) > 0:
        score += 20
    if int(shared_entity_type_counts.get("payment_handle") or 0) > 0:
        score += 20
    if int(shared_entity_type_counts.get("avatar_fingerprint") or 0) > 0 and connected_subject_count >= 2:
        score += 15
    if int(shared_entity_type_counts.get("message_pattern") or 0) > 0 and connected_subject_count >= 2:
        score += 10
    score += min(high_risk_neighbor_count * 20, 60)
    recent = set(_unique_ordered(recent_signal_codes))
    if recent & {"investment", "money_transfer", "off_platform", "fraud_report"}:
        score += 20
    if recent & {"repeated_opening", "high_frequency_outreach", "multi_party_reports"}:
        score += 15
    return min(score, 200)


def _risk_level_from_score(score: int) -> str:
    if score >= 160:
        return "critical"
    if score >= 100:
        return "high"
    if score >= 60:
        return "medium"
    if score >= 30:
        return "low"
    return "minimal"


def _recommended_action_for_network(
    score: int,
    shared_entity_type_counts: dict[str, int],
    connected_subject_count: int,
    high_risk_neighbor_count: int,
) -> str | None:
    if score >= 160 or (
        connected_subject_count >= 3
        and int(shared_entity_type_counts.get("device_fingerprint") or 0) > 0
        and int(shared_entity_type_counts.get("external_contact") or 0) > 0
    ):
        return ACTION_FREEZE
    if score >= 100 or (
        high_risk_neighbor_count > 0 and int(shared_entity_type_counts.get("device_fingerprint") or 0) > 0
    ):
        return ACTION_LIMIT_CHAT
    if score >= 60:
        return ACTION_REQUIRE_VERIFICATION
    if score >= 30:
        return ACTION_WARN
    return None


def _review_status_for_action(action: str | None) -> str:
    if action in NETWORK_REVIEWABLE_ACTIONS:
        return NETWORK_STATUS_ACTION_APPLIED
    if action == ACTION_WARN:
        return NETWORK_STATUS_UNDER_REVIEW
    return NETWORK_STATUS_WATCH


def _network_reason_summary(
    *,
    score: int,
    connected_subject_count: int,
    high_risk_neighbor_count: int,
    shared_entity_type_counts: dict[str, int],
) -> str:
    parts = [f"深度反诈图谱命中，风险分 {score}"]
    if connected_subject_count:
        parts.append(f"关联账号 {connected_subject_count} 个")
    if int(shared_entity_type_counts.get("device_fingerprint") or 0) > 0:
        parts.append("存在共享设备指纹")
    if int(shared_entity_type_counts.get("external_contact") or 0) > 0:
        parts.append("存在共享外部联系方式")
    if int(shared_entity_type_counts.get("message_pattern") or 0) > 0:
        parts.append("存在重复话术模板")
    if high_risk_neighbor_count:
        parts.append(f"已关联高风险账号 {high_risk_neighbor_count} 个")
    return "；".join(parts)


def _upsert_entity_link(
    conn,
    *,
    subject_user_id: str,
    source_dsn: str | None,
    source_table_name: str | None,
    profile_id: int | None,
    thread_id: str | None,
    case_id: str | None,
    risk_case_id: str | None,
    report_id: int | None,
    source_type: str,
    event_type: str,
    entity: dict[str, Any],
    signal_codes: list[str],
    evidence: dict[str, Any],
    now: datetime,
) -> None:
    existing = conn.execute(
        """
        SELECT *
        FROM chat_risk_entity_links
        WHERE subject_user_id = ?
          AND entity_type = ?
          AND entity_hash = ?
        LIMIT 1
        """,
        (subject_user_id, entity["entity_type"], entity["entity_hash"]),
    ).fetchone()
    if existing:
        row = row_to_dict(existing)
        merged_signal_codes = _unique_ordered(json_loads(row.get("signal_codes_json"), []) + list(signal_codes))
        merged_evidence = {**json_loads(row.get("evidence_json"), {}), **dict(evidence or {})}
        conn.execute(
            """
            UPDATE chat_risk_entity_links
            SET source_dsn = COALESCE(?, source_dsn),
                source_table_name = COALESCE(?, source_table_name),
                profile_id = COALESCE(?, profile_id),
                thread_id = COALESCE(?, thread_id),
                case_id = COALESCE(?, case_id),
                risk_case_id = COALESCE(?, risk_case_id),
                report_id = COALESCE(?, report_id),
                source_type = ?,
                event_type = ?,
                entity_key_hint = ?,
                entity_weight = ?,
                signal_codes_json = ?,
                evidence_json = ?,
                last_seen_at = ?,
                occurrence_count = ?
            WHERE entity_link_id = ?
            """,
            (
                source_dsn,
                source_table_name,
                int(profile_id) if profile_id is not None else None,
                thread_id,
                case_id,
                risk_case_id,
                int(report_id) if report_id is not None else None,
                source_type,
                event_type,
                entity.get("entity_key_hint"),
                int(entity.get("entity_weight") or 10),
                json_dumps(merged_signal_codes),
                json_dumps(merged_evidence),
                now,
                int(row.get("occurrence_count") or 0) + 1,
                int(row["entity_link_id"]),
            ),
        )
        return
    conn.execute(
        """
        INSERT INTO chat_risk_entity_links (
          subject_user_id, source_dsn, source_table_name, profile_id,
          thread_id, case_id, risk_case_id, report_id, source_type, event_type,
          entity_type, entity_hash, entity_key_hint, entity_weight,
          signal_codes_json, evidence_json, first_seen_at, last_seen_at, occurrence_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            subject_user_id,
            source_dsn,
            source_table_name,
            int(profile_id) if profile_id is not None else None,
            thread_id,
            case_id,
            risk_case_id,
            int(report_id) if report_id is not None else None,
            source_type,
            event_type,
            entity["entity_type"],
            entity["entity_hash"],
            entity.get("entity_key_hint"),
            int(entity.get("entity_weight") or 10),
            json_dumps(signal_codes),
            json_dumps(dict(evidence or {})),
            now,
            now,
            1,
        ),
    )


def _refresh_account_links(conn, subject_user_id: str, rows: list[dict[str, Any]], *, now: datetime) -> None:
    existing_rows = conn.execute(
        """
        SELECT *
        FROM chat_risk_account_links
        WHERE subject_user_id = ?
        """,
        (subject_user_id,),
    ).fetchall()
    existing = {
        _as_text(row_to_dict(row).get("linked_user_id")): _inflate_account_link(row_to_dict(row))
        for row in existing_rows
        if row
    }
    conn.execute("DELETE FROM chat_risk_account_links WHERE subject_user_id = ?", (subject_user_id,))
    for row in rows:
        previous = existing.get(_as_text(row.get("linked_user_id"))) or {}
        first_seen_at = previous.get("first_seen_at") or now
        conn.execute(
            """
            INSERT INTO chat_risk_account_links (
              subject_user_id, linked_user_id, shared_entity_types_json,
              shared_signal_codes_json, shared_entity_count, link_score,
              evidence_json, first_seen_at, last_seen_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subject_user_id,
                row.get("linked_user_id"),
                json_dumps(row.get("shared_entity_types") or []),
                json_dumps(row.get("shared_signal_codes") or []),
                int(row.get("shared_entity_count") or 0),
                int(row.get("link_score") or 0),
                json_dumps(
                    {
                        "shared_entities": row.get("shared_entities") or [],
                        "linked_active_action": row.get("linked_active_action"),
                    }
                ),
                first_seen_at,
                row.get("last_seen_at") or now,
                now,
            ),
        )


def _upsert_network_profile(
    conn,
    *,
    subject_user_id: str,
    source_dsn: str | None,
    source_table_name: str | None,
    profile_id: int | None,
    review_status: str,
    graph_risk_score: int,
    risk_level: str,
    connected_subject_count: int,
    high_risk_neighbor_count: int,
    shared_entity_type_counts: dict[str, int],
    signal_codes: list[str],
    recommended_action: str | None,
    applied_action: str | None,
    evidence: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    existing = get_fraud_network_profile(conn, subject_user_id)
    normalized_source, normalized_table = parse_source_ref(source_dsn, source_table_name)
    if existing:
        conn.execute(
            """
            UPDATE chat_risk_network_profiles
            SET source_dsn = COALESCE(?, source_dsn),
                source_table_name = COALESCE(?, source_table_name),
                profile_id = COALESCE(?, profile_id),
                review_status = ?,
                graph_risk_score = ?,
                risk_level = ?,
                connected_subject_count = ?,
                high_risk_neighbor_count = ?,
                shared_entity_type_counts_json = ?,
                signal_codes_json = ?,
                recommended_action = ?,
                applied_action = ?,
                evidence_json = ?,
                last_evaluated_at = ?,
                updated_at = ?
            WHERE subject_user_id = ?
            """,
            (
                normalized_source,
                normalized_table,
                int(profile_id) if profile_id is not None else None,
                review_status,
                int(graph_risk_score),
                risk_level,
                int(connected_subject_count),
                int(high_risk_neighbor_count),
                json_dumps(shared_entity_type_counts),
                json_dumps(signal_codes),
                recommended_action,
                applied_action,
                json_dumps(evidence),
                now,
                now,
                subject_user_id,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO chat_risk_network_profiles (
              subject_user_id, source_dsn, source_table_name, profile_id,
              review_status, graph_risk_score, risk_level, connected_subject_count,
              high_risk_neighbor_count, shared_entity_type_counts_json, signal_codes_json,
              recommended_action, applied_action, evidence_json, last_evaluated_at,
              created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subject_user_id,
                normalized_source,
                normalized_table,
                int(profile_id) if profile_id is not None else None,
                review_status,
                int(graph_risk_score),
                risk_level,
                int(connected_subject_count),
                int(high_risk_neighbor_count),
                json_dumps(shared_entity_type_counts),
                json_dumps(signal_codes),
                recommended_action,
                applied_action,
                json_dumps(evidence),
                now,
                now,
                now,
            ),
        )
    profile = get_fraud_network_profile(conn, subject_user_id)
    assert profile is not None
    return profile


def _network_profiles_by_subject_ids(conn, subject_user_ids: Iterable[Any]) -> dict[str, dict[str, Any]]:
    normalized = _unique_ordered(subject_user_ids)
    if not normalized:
        return {}
    placeholders = ", ".join(["?"] * len(normalized))
    rows = conn.execute(
        f"""
        SELECT *
        FROM chat_risk_network_profiles
        WHERE subject_user_id IN ({placeholders})
        """,
        tuple(normalized),
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = _inflate_network_profile(row_to_dict(row))
        if item and item.get("subject_user_id"):
            out[str(item["subject_user_id"])] = item
    return out


def record_fraud_network_observation(
    conn,
    *,
    subject_user_id: str,
    source_dsn: str | None = None,
    source_table_name: str | None = None,
    profile_id: int | None = None,
    thread_id: str | None = None,
    case_id: str | None = None,
    risk_case_id: str | None = None,
    report_id: int | None = None,
    source_type: str = "system_rule",
    event_type: str = "risk_report",
    signal_codes: Iterable[Any] | None = None,
    evidence: dict[str, Any] | None = None,
    message_body: str | None = None,
    now: datetime | None = None,
    evaluate: bool = True,
) -> dict[str, Any]:
    normalized_user_id = _as_text(subject_user_id)
    if not normalized_user_id:
        raise ValueError("subject_user_id is required")
    ts = current_time(now)
    normalized_source, normalized_table = parse_source_ref(source_dsn, source_table_name)
    normalized_signal_codes = _unique_ordered(signal_codes or [])
    normalized_evidence = dict(evidence or {})
    entities = _collect_entity_candidates(
        evidence=normalized_evidence,
        message_body=message_body,
        signal_codes=normalized_signal_codes,
    )
    for entity in entities:
        _upsert_entity_link(
            conn,
            subject_user_id=normalized_user_id,
            source_dsn=normalized_source,
            source_table_name=normalized_table,
            profile_id=profile_id,
            thread_id=_as_text(thread_id) or None,
            case_id=_as_text(case_id) or None,
            risk_case_id=_as_text(risk_case_id) or None,
            report_id=int(report_id) if report_id is not None else None,
            source_type=_as_text(source_type) or "system_rule",
            event_type=_as_text(event_type) or "risk_report",
            entity=entity,
            signal_codes=normalized_signal_codes,
            evidence=normalized_evidence,
            now=ts,
        )
    network = None
    if evaluate:
        network = evaluate_fraud_network(
            conn,
            normalized_user_id,
            source_dsn=normalized_source,
            source_table_name=normalized_table,
            profile_id=profile_id,
            now=ts,
        )
    return {
        "subject_user_id": normalized_user_id,
        "entity_count": len(entities),
        "entity_types": _unique_ordered(entity.get("entity_type") for entity in entities),
        "network": network,
    }


def evaluate_fraud_network(
    conn,
    subject_user_id: str,
    *,
    source_dsn: str | None = None,
    source_table_name: str | None = None,
    profile_id: int | None = None,
    now: datetime | None = None,
    propagate: bool = True,
) -> dict[str, Any]:
    normalized_user_id = _as_text(subject_user_id)
    if not normalized_user_id:
        raise ValueError("subject_user_id is required")
    ts = current_time(now)
    normalized_source, normalized_table, normalized_profile_id = _profile_ref_for_subject(
        conn,
        normalized_user_id,
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_id=profile_id,
    )
    account_links = _account_link_rows(conn, normalized_user_id, now=ts)
    _refresh_account_links(conn, normalized_user_id, account_links, now=ts)

    shared_entity_type_counts: dict[str, int] = {}
    for link in account_links:
        for entity_type in list(link.get("shared_entity_types") or []):
            shared_entity_type_counts[entity_type] = shared_entity_type_counts.get(entity_type, 0) + 1
    recent_signal_codes = _recent_subject_signal_codes(conn, normalized_user_id, now=ts)
    high_risk_neighbor_count = sum(
        1
        for link in account_links
        if _as_text(link.get("linked_active_action")) in {ACTION_LIMIT_CHAT, ACTION_FREEZE}
    )
    graph_risk_score = _risk_score_for_network(
        account_links,
        shared_entity_type_counts,
        high_risk_neighbor_count,
        recent_signal_codes,
    )
    risk_level = _risk_level_from_score(graph_risk_score)
    recommended_action = _recommended_action_for_network(
        graph_risk_score,
        shared_entity_type_counts,
        len(account_links),
        high_risk_neighbor_count,
    )
    applied_action = recommended_action if recommended_action in NETWORK_REVIEWABLE_ACTIONS else None
    review_status = (
        NETWORK_STATUS_CLEAN
        if not account_links and not recommended_action
        else _review_status_for_action(recommended_action)
    )
    signal_codes = _network_signal_codes(
        shared_entity_type_counts,
        len(account_links),
        high_risk_neighbor_count,
        recent_signal_codes,
    )
    evidence = {
        "linked_user_ids": [item.get("linked_user_id") for item in account_links],
        "top_shared_entities": {
            item["linked_user_id"]: item.get("shared_entities") or []
            for item in account_links[:10]
        },
        "recent_signal_codes": recent_signal_codes,
        "high_risk_neighbor_count": high_risk_neighbor_count,
    }
    _upsert_network_profile(
        conn,
        subject_user_id=normalized_user_id,
        source_dsn=normalized_source,
        source_table_name=normalized_table,
        profile_id=normalized_profile_id,
        review_status=review_status,
        graph_risk_score=graph_risk_score,
        risk_level=risk_level,
        connected_subject_count=len(account_links),
        high_risk_neighbor_count=high_risk_neighbor_count,
        shared_entity_type_counts=shared_entity_type_counts,
        signal_codes=signal_codes,
        recommended_action=recommended_action,
        applied_action=applied_action,
        evidence=evidence,
        now=ts,
    )
    if applied_action:
        required_verifications = _unique_ordered(
            list(infer_required_verifications(signal_codes))
            + ["identity", "live_video"]
        )
        upsert_moderation_state(
            conn,
            subject_user_id=normalized_user_id,
            source_dsn=normalized_source,
            source_table_name=normalized_table,
            profile_id=int(normalized_profile_id) if normalized_profile_id is not None else None,
            action=applied_action,
            reason_code="fraud_graph_cluster",
            reason_summary=_network_reason_summary(
                score=graph_risk_score,
                connected_subject_count=len(account_links),
                high_risk_neighbor_count=high_risk_neighbor_count,
                shared_entity_type_counts=shared_entity_type_counts,
            ),
            required_verifications=required_verifications,
            evidence={
                "fraud_network_score": graph_risk_score,
                "signal_codes": signal_codes,
                "connected_subject_count": len(account_links),
                "high_risk_neighbor_count": high_risk_neighbor_count,
            },
            resolver_id="system:fraud_graph",
            now=ts,
        )
        _upsert_network_profile(
            conn,
            subject_user_id=normalized_user_id,
            source_dsn=normalized_source,
            source_table_name=normalized_table,
            profile_id=normalized_profile_id,
            review_status=NETWORK_STATUS_ACTION_APPLIED,
            graph_risk_score=graph_risk_score,
            risk_level=risk_level,
            connected_subject_count=len(account_links),
            high_risk_neighbor_count=high_risk_neighbor_count,
            shared_entity_type_counts=shared_entity_type_counts,
            signal_codes=signal_codes,
            recommended_action=recommended_action,
            applied_action=applied_action,
            evidence=evidence,
            now=ts,
        )
    if propagate:
        for link in account_links[:MAX_PROPAGATION_SUBJECTS]:
            evaluate_fraud_network(conn, link["linked_user_id"], now=ts, propagate=False)
    return build_fraud_network_overview(conn, normalized_user_id)


def get_fraud_network_profile(conn, subject_user_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT *
        FROM chat_risk_network_profiles
        WHERE subject_user_id = ?
        LIMIT 1
        """,
        (_as_text(subject_user_id),),
    ).fetchone()
    return _inflate_network_profile(row_to_dict(row))


def list_fraud_network_profiles(
    conn,
    *,
    review_statuses: Iterable[Any] | None = None,
    subject_user_id: str | None = None,
    minimum_score: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    normalized_statuses = _unique_ordered(review_statuses or [])
    if normalized_statuses:
        placeholders = ", ".join(["?"] * len(normalized_statuses))
        clauses.append(f"review_status IN ({placeholders})")
        params.extend(normalized_statuses)
    if subject_user_id:
        clauses.append("subject_user_id = ?")
        params.append(_as_text(subject_user_id))
    if minimum_score is not None:
        clauses.append("graph_risk_score >= ?")
        params.append(int(minimum_score))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""
        SELECT *
        FROM chat_risk_network_profiles
        {where}
        ORDER BY graph_risk_score DESC, updated_at DESC
        LIMIT ?
        """,
        tuple(params + [max(1, min(int(limit), 200))]),
    ).fetchall()
    return [_inflate_network_profile(row_to_dict(row)) for row in rows if row]


def list_fraud_network_links(
    conn,
    subject_user_id: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT *
        FROM chat_risk_account_links
        WHERE subject_user_id = ?
        ORDER BY link_score DESC, updated_at DESC
        LIMIT ?
        """,
        (_as_text(subject_user_id), max(1, min(int(limit), 200))),
    ).fetchall()
    return [_inflate_account_link(row_to_dict(row)) for row in rows if row]


def build_fraud_network_overview(conn, subject_user_id: str) -> dict[str, Any]:
    profile = get_fraud_network_profile(conn, subject_user_id)
    source_dsn, source_table_name, profile_id = _profile_ref_for_subject(conn, _as_text(subject_user_id))
    moderation_state = get_active_moderation_state(
        conn,
        subject_user_id=_as_text(subject_user_id),
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_id=int(profile_id) if profile_id is not None else None,
    )
    account_links = list_fraud_network_links(conn, subject_user_id, limit=MAX_LINKED_SUBJECTS)
    linked_lookup = _network_profiles_by_subject_ids(
        conn,
        [item.get("linked_user_id") for item in account_links],
    )
    for item in account_links:
        linked_user_id = _as_text(item.get("linked_user_id"))
        if linked_user_id in linked_lookup:
            item["linked_network_profile"] = linked_lookup[linked_user_id]
    return {
        "subject_user_id": _as_text(subject_user_id),
        "network_profile": profile,
        "account_links": account_links,
        "moderation_state": moderation_state,
    }


__all__ = [
    "NETWORK_STATUS_ACTION_APPLIED",
    "NETWORK_STATUS_CLEAN",
    "NETWORK_STATUS_UNDER_REVIEW",
    "NETWORK_STATUS_WATCH",
    "build_fraud_network_overview",
    "evaluate_fraud_network",
    "get_fraud_network_profile",
    "list_fraud_network_links",
    "list_fraud_network_profiles",
    "record_fraud_network_observation",
]
