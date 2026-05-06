"""Trend state and proactive hint trigger rules for chat assistant hints."""

from __future__ import annotations

from typing import Any

TREND_STATE_SCHEMA_VERSION = 1
TREND_MODES = ("normal", "repair", "probe_lightly", "hold")
_MODE_SET = frozenset(TREND_MODES)
_DUPLICATE_SUPPRESSION_REASONS = frozenset(
    {
        "waiting_for_user_action",
        "cooldown_active",
        "same_mode_no_new_value",
        "hold_repeat_suppressed",
        "no_new_value_after_strong_follow",
    }
)


def _trend_mode(interaction_mode: Any) -> str:
    mode = str(interaction_mode or "").strip().lower()
    if mode in {"repair", "probe_lightly", "hold"}:
        return mode
    return "normal"


def _to_clean_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif value in (None, ""):
        items = []
    else:
        items = [value]
    out: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in out:
            continue
        out.append(text)
    return out


def _risk_flags(decision: dict[str, Any], current_mode: str) -> list[str]:
    mutual = str((decision or {}).get("mutual_intent_assessment") or "").strip().lower()
    situation = str((decision or {}).get("situation") or "").strip().lower()
    problem_tags = _to_clean_list((decision or {}).get("problem_tags"))
    flags: list[str] = []
    if current_mode == "repair":
        flags.append("repair_needed")
    elif current_mode == "probe_lightly":
        flags.append("interest_unclear")
    elif current_mode == "hold":
        flags.append("hold_needed")
    if mutual == "boundary_risk" or situation == "boundary" or "boundary_risk" in problem_tags:
        flags.append("boundary_risk")
    elif mutual == "interest_low":
        flags.append("interest_low")
    elif mutual == "interest_unclear":
        flags.append("interest_unclear")
    if any(tag in problem_tags for tag in ("low_energy", "closed_reply")):
        flags.append("low_energy")
    if any(tag in problem_tags for tag in ("topic_dead_end", "awkward_transition", "misread")):
        flags.append("topic_dead_end")
    if situation in {"rude", "awkward", "stuck", "off_topic"}:
        flags.append(situation)
    out: list[str] = []
    for flag in flags:
        if flag and flag not in out:
            out.append(flag)
    return out


def _risk_level(current_mode: str, risk_flags: list[str]) -> int:
    level = 0
    if current_mode == "repair":
        level = 1
    elif current_mode == "probe_lightly":
        level = 2
    elif current_mode == "hold":
        level = 3
    if "interest_low" in risk_flags:
        level = max(level, 3)
    if "boundary_risk" in risk_flags:
        level = max(level, 4)
    if "low_energy" in risk_flags and current_mode == "probe_lightly":
        level = max(level, 2)
    return level


def _cooldown_turns(current_mode: str) -> int:
    if current_mode == "repair":
        return 2
    if current_mode == "probe_lightly":
        return 4
    if current_mode == "hold":
        return 6
    return 0


def normalize_trend_state(state: dict[str, Any] | None) -> dict[str, Any]:
    payload = state if isinstance(state, dict) else {}
    current_mode = _trend_mode(payload.get("current_mode"))
    previous_mode = _trend_mode(payload.get("previous_mode"))
    risk_flags = _to_clean_list(payload.get("risk_flags"))
    out = {
        "schema_version": TREND_STATE_SCHEMA_VERSION,
        "current_mode": current_mode,
        "previous_mode": previous_mode,
        "same_mode_turns": max(0, int(payload.get("same_mode_turns") or 0)),
        "unresolved_turns": max(0, int(payload.get("unresolved_turns") or 0)),
        "risk_flags": risk_flags,
        "risk_level": max(0, int(payload.get("risk_level") or 0)),
        "previous_risk_level": max(0, int(payload.get("previous_risk_level") or 0)),
        "last_hint_turn": payload.get("last_hint_turn"),
        "last_hint_mode": _trend_mode(payload.get("last_hint_mode")),
        "last_hint_reason": str(payload.get("last_hint_reason") or "").strip() or None,
        "last_hint_trigger_type": str(payload.get("last_hint_trigger_type") or "").strip() or None,
        "last_hint_follow_level": str(payload.get("last_hint_follow_level") or "").strip() or None,
        "has_user_acted_since_last_hint": bool(payload.get("has_user_acted_since_last_hint")),
        "cooldown_until_turn": int(payload.get("cooldown_until_turn") or 0),
        "last_hint_actor_turn_count": int(payload.get("last_hint_actor_turn_count") or 0),
        "current_turn_index": max(0, int(payload.get("current_turn_index") or 0)),
        "current_actor_turn_count": max(0, int(payload.get("current_actor_turn_count") or 0)),
    }
    if current_mode not in _MODE_SET:
        out["current_mode"] = "normal"
    if previous_mode not in _MODE_SET:
        out["previous_mode"] = "normal"
    if out["last_hint_mode"] == "normal":
        out["last_hint_mode"] = None
    if out["last_hint_turn"] is None:
        out["cooldown_until_turn"] = 0
        out["last_hint_actor_turn_count"] = 0
        out["has_user_acted_since_last_hint"] = False
    return out


def advance_trend_state(
    previous_state: dict[str, Any] | None,
    route_decision: dict[str, Any] | None,
    *,
    turn_index: int,
    actor_turn_count: int,
    follow_level: str | None = None,
) -> dict[str, Any]:
    prev = normalize_trend_state(previous_state)
    current_mode = _trend_mode((route_decision or {}).get("interaction_mode"))
    previous_mode = str(prev.get("current_mode") or "normal")
    same_mode_turns = prev["same_mode_turns"] + 1 if current_mode == previous_mode else 1
    if current_mode == "normal":
        unresolved_turns = 0
    elif current_mode == previous_mode and previous_mode != "normal":
        unresolved_turns = prev["unresolved_turns"] + 1
    else:
        unresolved_turns = 1
    risk_flags = _risk_flags(route_decision or {}, current_mode)
    risk_level = _risk_level(current_mode, risk_flags)
    has_user_acted_since_last_hint = bool(
        prev.get("last_hint_turn") is not None
        and actor_turn_count > int(prev.get("last_hint_actor_turn_count") or 0)
    )
    last_hint_follow_level = prev.get("last_hint_follow_level")
    if has_user_acted_since_last_hint and follow_level:
        last_hint_follow_level = str(follow_level)
    return {
        **prev,
        "schema_version": TREND_STATE_SCHEMA_VERSION,
        "current_mode": current_mode,
        "previous_mode": previous_mode,
        "same_mode_turns": same_mode_turns,
        "unresolved_turns": unresolved_turns,
        "risk_flags": risk_flags,
        "risk_level": risk_level,
        "previous_risk_level": prev["risk_level"],
        "has_user_acted_since_last_hint": has_user_acted_since_last_hint,
        "current_turn_index": int(turn_index),
        "current_actor_turn_count": int(actor_turn_count),
        "last_hint_follow_level": last_hint_follow_level,
    }


def decide_hint_trigger(
    state: dict[str, Any] | None,
    *,
    speaker: str,
    reason: str = "",
) -> dict[str, Any]:
    cur = normalize_trend_state(state)
    mode_before = str(cur.get("previous_mode") or "normal")
    mode_after = str(cur.get("current_mode") or "normal")
    last_hint_turn = cur.get("last_hint_turn")
    last_gap = (
        None
        if last_hint_turn is None
        else max(0, int(cur["current_turn_index"]) - int(last_hint_turn))
    )
    risk_flags = list(cur.get("risk_flags") or [])
    risk_upgraded = bool(
        cur["risk_level"] > cur["previous_risk_level"]
        or any(flag not in set(cur.get("risk_flags") or []) for flag in ())
    )
    event = {
        "turn_index": int(cur["current_turn_index"]),
        "speaker": str(speaker or ""),
        "mode_before": mode_before,
        "mode_after": mode_after,
        "trigger_type": None,
        "suppression_reason": None,
        "hint_posted": False,
        "risk_flags": risk_flags,
        "last_hint_turn_gap": last_gap,
        "same_mode_turns": int(cur["same_mode_turns"]),
        "unresolved_turns": int(cur["unresolved_turns"]),
        "has_user_acted_since_last_hint": bool(cur["has_user_acted_since_last_hint"]),
        "cooldown_until_turn": int(cur["cooldown_until_turn"]),
        "risk_level": int(cur["risk_level"]),
        "reason": str(reason or "").strip() or None,
    }
    if mode_after == "normal":
        event["suppression_reason"] = "normal_mode"
        return event
    if last_hint_turn is None:
        event["hint_posted"] = True
        if mode_before == "normal":
            event["trigger_type"] = "mode_change"
        else:
            event["trigger_type"] = "first_entry"
        return event
    if mode_after != str(cur.get("last_hint_mode") or "normal"):
        event["hint_posted"] = True
        event["trigger_type"] = "mode_change"
        return event
    if not bool(cur["has_user_acted_since_last_hint"]):
        event["suppression_reason"] = "waiting_for_user_action"
        return event
    if risk_upgraded:
        event["hint_posted"] = True
        event["trigger_type"] = "risk_upgrade"
        return event
    if int(cur["current_turn_index"]) <= int(cur["cooldown_until_turn"]):
        event["suppression_reason"] = "cooldown_active"
        return event
    if mode_after == "hold":
        event["suppression_reason"] = "hold_repeat_suppressed"
        return event
    if str(cur.get("last_hint_follow_level") or "") == "strong" and int(cur["unresolved_turns"]) < 3:
        event["suppression_reason"] = "no_new_value_after_strong_follow"
        return event
    retry_threshold = 2 if mode_after == "repair" else 3
    if int(cur["unresolved_turns"]) >= retry_threshold:
        event["hint_posted"] = True
        event["trigger_type"] = "unresolved_retry"
        return event
    event["suppression_reason"] = "same_mode_no_new_value"
    return event


def apply_hint_event(state: dict[str, Any] | None, event: dict[str, Any] | None) -> dict[str, Any]:
    cur = normalize_trend_state(state)
    payload = event if isinstance(event, dict) else {}
    if not bool(payload.get("hint_posted")):
        return cur
    current_mode = str(cur.get("current_mode") or "normal")
    return {
        **cur,
        "last_hint_turn": int(cur["current_turn_index"]),
        "last_hint_mode": current_mode,
        "last_hint_reason": str(payload.get("reason") or "").strip() or None,
        "last_hint_trigger_type": str(payload.get("trigger_type") or "").strip() or None,
        "has_user_acted_since_last_hint": False,
        "cooldown_until_turn": int(cur["current_turn_index"]) + _cooldown_turns(current_mode),
        "last_hint_actor_turn_count": int(cur["current_actor_turn_count"]),
    }


def is_duplicate_suppression_reason(reason: Any) -> bool:
    return str(reason or "").strip() in _DUPLICATE_SUPPRESSION_REASONS


__all__ = [
    "TREND_MODES",
    "TREND_STATE_SCHEMA_VERSION",
    "advance_trend_state",
    "apply_hint_event",
    "decide_hint_trigger",
    "is_duplicate_suppression_reason",
    "normalize_trend_state",
]
