"""Stable reason-code registry for gate / delivery / chat audit (§13.5)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ReasonCodeEntry:
    code: str
    domain: str
    severity: str
    human_label: str
    param_keys: tuple[str, ...] = ()
    legacy_aliases: tuple[str, ...] = ()


REASON_CODE_REGISTRY: dict[str, ReasonCodeEntry] = {
    "gate:score_below_threshold": ReasonCodeEntry(
        code="gate:score_below_threshold",
        domain="recommendation",
        severity="hold",
        human_label="综合评分未达到主动打招呼阈值",
        param_keys=("min_direct_greet_score", "review_score"),
        legacy_aliases=("not_compelling_enough_for_direct_greet",),
    ),
    "gate:risk_flags_manual_review": ReasonCodeEntry(
        code="gate:risk_flags_manual_review",
        domain="recommendation",
        severity="hold",
        human_label="存在风险标记，需人工复核",
        param_keys=("auto_reject_on_risk_flags",),
        legacy_aliases=("risk_flags_require_manual_review",),
    ),
    "gate:follow_up_questions_manual_review": ReasonCodeEntry(
        code="gate:follow_up_questions_manual_review",
        domain="recommendation",
        severity="hold",
        human_label="存在待确认问题，需人工复核",
        param_keys=("auto_reject_on_follow_up_questions",),
        legacy_aliases=("follow_up_questions_require_manual_review",),
    ),
    "gate:missing_information_manual_review": ReasonCodeEntry(
        code="gate:missing_information_manual_review",
        domain="recommendation",
        severity="hold",
        human_label="资料或自身画像信息不足，需人工复核",
        legacy_aliases=("missing_information_requires_manual_review",),
    ),
    "gate:preferences_not_met": ReasonCodeEntry(
        code="gate:preferences_not_met",
        domain="recommendation",
        severity="reject",
        human_label="未满足 direct greet 硬性偏好",
        legacy_aliases=("direct_greet_preferences_not_met",),
    ),
    "gate:outside_review_pool": ReasonCodeEntry(
        code="gate:outside_review_pool",
        domain="recommendation",
        severity="hold",
        human_label="超出本轮审核池容量",
        param_keys=("max_review_candidates_per_refresh", "review_rank"),
        legacy_aliases=("outside_review_pool",),
    ),
    "gate:direct_greet_passed": ReasonCodeEntry(
        code="gate:direct_greet_passed",
        domain="recommendation",
        severity="info",
        human_label="通过 direct greet gate",
        legacy_aliases=("direct_greet_gate_passed",),
    ),
    "gate:match_based_mode": ReasonCodeEntry(
        code="gate:match_based_mode",
        domain="recommendation",
        severity="info",
        human_label="match_based 模式直接就绪",
        legacy_aliases=("match_based_mode",),
    ),
    "gate:review_deferred": ReasonCodeEntry(
        code="gate:review_deferred",
        domain="recommendation",
        severity="hold",
        human_label="审核延后",
        legacy_aliases=("review_deferred",),
    ),
    "delivery:quiet_hours": ReasonCodeEntry(
        code="delivery:quiet_hours",
        domain="recommendation",
        severity="hold",
        human_label="静默时段暂缓投递",
        param_keys=("quiet_hours_start", "quiet_hours_end"),
    ),
    "delivery:daily_cap": ReasonCodeEntry(
        code="delivery:daily_cap",
        domain="recommendation",
        severity="hold",
        human_label="已达当日通知上限",
        param_keys=("daily_notification_cap",),
    ),
    "moderation:needs_review": ReasonCodeEntry(
        code="moderation:needs_review",
        domain="moderation",
        severity="hold",
        human_label="资料待审核",
    ),
    "chat:post_chat_followup": ReasonCodeEntry(
        code="chat:post_chat_followup",
        domain="chat",
        severity="info",
        human_label="聊天后跟进询问",
        param_keys=("default_seconds",),
        legacy_aliases=("post_chat_followup",),
    ),
    "chat:pace_mismatch": ReasonCodeEntry(
        code="chat:pace_mismatch",
        domain="chat",
        severity="info",
        human_label="聊天节奏不匹配",
        param_keys=("default_seconds",),
        legacy_aliases=("pace_mismatch",),
    ),
    "chat:heuristic_fallback": ReasonCodeEntry(
        code="chat:heuristic_fallback",
        domain="chat",
        severity="info",
        human_label="助手启发式回退",
        legacy_aliases=("heuristic_fallback",),
    ),
}


_LEGACY_ALIAS_INDEX: dict[str, str] = {}
for entry in REASON_CODE_REGISTRY.values():
    for alias in entry.legacy_aliases:
        _LEGACY_ALIAS_INDEX[alias] = entry.code
    _LEGACY_ALIAS_INDEX[entry.code] = entry.code


def normalize_reason_code(raw: Any) -> str | None:
    normalized = str(raw or "").strip()
    if not normalized:
        return None
    if normalized in REASON_CODE_REGISTRY:
        return normalized
    if normalized in _LEGACY_ALIAS_INDEX:
        return _LEGACY_ALIAS_INDEX[normalized]
    if normalized.startswith("moderation:"):
        return normalized
    if normalized.startswith("risk:"):
        return normalized
    if normalized.startswith("blocked_by:"):
        return normalized
    return normalized


def normalize_reason_codes(codes: list[Any] | None) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in codes or []:
        code = normalize_reason_code(raw)
        if not code or code in seen:
            continue
        seen.add(code)
        ordered.append(code)
    return ordered


def reason_codes_from_final_review(final_review: Mapping[str, Any]) -> list[str]:
    reason = str(final_review.get("reason") or final_review.get("status") or "").strip()
    codes = normalize_reason_codes([reason] if reason else [])
    payload = final_review.get("payload") or {}
    blocked_by = payload.get("blocked_by")
    if blocked_by:
        codes = normalize_reason_codes(codes + [f"blocked_by:{blocked_by}"])
    for item in payload.get("requirement_failures") or []:
        codes = normalize_reason_codes(codes + [str(item)])
    return codes


def describe_reason_code(code: str) -> dict[str, Any]:
    entry = REASON_CODE_REGISTRY.get(code)
    if entry is not None:
        return {
            "code": entry.code,
            "domain": entry.domain,
            "severity": entry.severity,
            "human_label": entry.human_label,
            "param_keys": list(entry.param_keys),
        }
    return {"code": code, "domain": "unknown", "severity": "info", "human_label": code, "param_keys": []}


__all__ = [
    "REASON_CODE_REGISTRY",
    "ReasonCodeEntry",
    "describe_reason_code",
    "normalize_reason_code",
    "normalize_reason_codes",
    "reason_codes_from_final_review",
]
