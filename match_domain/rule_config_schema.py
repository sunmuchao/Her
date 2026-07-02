"""Parameter schemas and code defaults for configurable rule slices (§13.5)."""

from __future__ import annotations

import os
from typing import Any

SLICE_RECOMMENDATION_DIRECT_GREET_GATE = "recommendation.direct_greet_gate"
SLICE_RECOMMENDATION_DELIVERY = "recommendation.delivery"
SLICE_RECOMMENDATION_REVIEW_POLICY = "recommendation.review_policy"
SLICE_PARTNER_SEARCH_SCORING = "partner_search.scoring"
SLICE_PARTNER_SEARCH_RANKING = "partner_search.ranking"
SLICE_RECOMMENDATION_CRITERIA = "recommendation.criteria_compiler"
SLICE_PARTNER_SEARCH_RECIPROCAL = "partner_search.reciprocal"
SLICE_CHAT_ASSISTANT_COOLDOWN = "chat.assistant_cooldown"
SLICE_VERIFICATION_AUTO_TRIAGE = "verification.auto_triage"
SLICE_VERIFICATION_THRESHOLDS = "verification.thresholds"

ALL_RULE_SLICES = (
    SLICE_RECOMMENDATION_DIRECT_GREET_GATE,
    SLICE_RECOMMENDATION_DELIVERY,
    SLICE_RECOMMENDATION_REVIEW_POLICY,
    SLICE_PARTNER_SEARCH_SCORING,
    SLICE_PARTNER_SEARCH_RANKING,
    SLICE_RECOMMENDATION_CRITERIA,
    SLICE_PARTNER_SEARCH_RECIPROCAL,
    SLICE_CHAT_ASSISTANT_COOLDOWN,
    SLICE_VERIFICATION_AUTO_TRIAGE,
    SLICE_VERIFICATION_THRESHOLDS,
)

DEFAULT_CHAT_COOLDOWN_SECONDS: dict[str, int] = {
    "default": 60,
    "post_chat_followup": 300,
    "heuristic_fallback": 120,
    "opening_probe_profile_intro": 120,
    "pace_mismatch": 60,
    "silence_probe_conservative_noop": 0,
    "opening_probe_conservative_noop": 0,
}
DEFAULT_POST_CHAT_COOLDOWN_FLOOR = 1800

DEFAULT_RECOMMENDATION_MODE = "direct_greet_only"
DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH = 3
DEFAULT_MIN_DIRECT_GREET_SCORE = 60
DEFAULT_MIN_NOTIFY_SCORE = 40
DEFAULT_DAILY_NOTIFICATION_CAP = 2
DEFAULT_QUIET_HOURS_START = 22
DEFAULT_QUIET_HOURS_END = 9
DEFAULT_SKIP_COOLDOWN_DAYS = 30
DEFAULT_PENALTY_TIER_NEGOTIABLE = 7
DEFAULT_PENALTY_TIER_UNKNOWN = 10
DEFAULT_PENALTY_TIER_CONSERVATIVE = 9


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw in {None, ""}:
        return default
    return int(raw)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw in {None, ""}:
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def code_defaults_for_slice(slice_id: str) -> dict[str, Any]:
    if slice_id == SLICE_RECOMMENDATION_DIRECT_GREET_GATE:
        return {
            "recommendation_mode": os.environ.get("HER_RECOMMENDATION_MODE") or DEFAULT_RECOMMENDATION_MODE,
            "max_review_candidates_per_refresh": _env_int(
                "HER_RECOMMENDATION_MAX_REVIEW_CANDIDATES_PER_REFRESH",
                DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH,
            ),
            "min_direct_greet_score": _env_int(
                "HER_RECOMMENDATION_MIN_DIRECT_GREET_SCORE",
                DEFAULT_MIN_DIRECT_GREET_SCORE,
            ),
            "auto_reject_on_follow_up_questions": _env_bool(
                "HER_RECOMMENDATION_AUTO_REJECT_ON_FOLLOW_UP_QUESTIONS",
                True,
            ),
            "auto_reject_on_risk_flags": _env_bool(
                "HER_RECOMMENDATION_AUTO_REJECT_ON_RISK_FLAGS",
                True,
            ),
        }
    if slice_id == SLICE_RECOMMENDATION_DELIVERY:
        return {
            "min_notify_score": DEFAULT_MIN_NOTIFY_SCORE,
            "daily_notification_cap": DEFAULT_DAILY_NOTIFICATION_CAP,
            "quiet_hours_start": DEFAULT_QUIET_HOURS_START,
            "quiet_hours_end": DEFAULT_QUIET_HOURS_END,
            "skip_cooldown_days": DEFAULT_SKIP_COOLDOWN_DAYS,
        }
    if slice_id == SLICE_RECOMMENDATION_REVIEW_POLICY:
        return {
            "require_user_review": _env_bool("HER_REQUIRE_USER_REVIEW", True),
            "auto_deliver_on_system_pass": _env_bool("HER_AUTO_DELIVER_ON_SYSTEM_PASS", True),
            "direct_greet_requires_review": _env_bool("HER_DIRECT_GREET_REQUIRES_REVIEW", False),
        }
    if slice_id == SLICE_PARTNER_SEARCH_SCORING:
        return {
            "penalty_tier.negotiable": DEFAULT_PENALTY_TIER_NEGOTIABLE,
            "penalty_tier.unknown": DEFAULT_PENALTY_TIER_UNKNOWN,
            "penalty_tier.conservative": DEFAULT_PENALTY_TIER_CONSERVATIVE,
        }
    if slice_id == SLICE_PARTNER_SEARCH_RANKING:
        return {
            "diversity_penalty_tiers": [6, 4, 2],
            "score_gap_severe_concession": 20,
            "score_gap_high_risk_tail": 25,
        }
    if slice_id == SLICE_CHAT_ASSISTANT_COOLDOWN:
        return {
            "default_seconds": 60,
            "post_chat_ready_floor_seconds": DEFAULT_POST_CHAT_COOLDOWN_FLOOR,
            "reason_code_seconds": dict(DEFAULT_CHAT_COOLDOWN_SECONDS),
        }
    if slice_id == SLICE_VERIFICATION_AUTO_TRIAGE:
        return {
            "enabled": _env_bool("HER_VERIFICATION_AUTO_TRIAGE", True),
        }
    if slice_id == SLICE_VERIFICATION_THRESHOLDS:
        return {
            # 活体检测阈值
            "liveness_score_min": _env_int("HER_VERIFICATION_LIVENESS_MIN", 85),
            "liveness_score_fail": _env_int("HER_VERIFICATION_LIVENESS_FAIL", 60),

            # 人脸匹配阈值
            "face_match_score_min": _env_int("HER_VERIFICATION_FACE_MATCH_MIN", 85),
            "face_match_score_fail": _env_int("HER_VERIFICATION_FACE_MATCH_FAIL", 40),

            # 动作挑战阈值
            "challenge_score_min": _env_int("HER_VERIFICATION_CHALLENGE_MIN", 80),
            "challenge_score_fail": _env_int("HER_VERIFICATION_CHALLENGE_FAIL", 60),

            # 语音口令匹配
            "speech_code_match_required": _env_bool("HER_VERIFICATION_SPEECH_CODE_REQUIRED", True),

            # 风险检测阈值
            "deepfake_risk_threshold": _env_int("HER_VERIFICATION_DEEPFAKE_THRESHOLD", 85),
            "deepfake_risk_medium": _env_int("HER_VERIFICATION_DEEPFAKE_MEDIUM", 60),

            "replay_attack_threshold": _env_int("HER_VERIFICATION_REPLAY_THRESHOLD", 85),
            "replay_attack_medium": _env_int("HER_VERIFICATION_REPLAY_MEDIUM", 60),

            "spoofing_risk_threshold": _env_int("HER_VERIFICATION_SPOOFING_THRESHOLD", 85),
            "spoofing_risk_medium": _env_int("HER_VERIFICATION_SPOOFING_MEDIUM", 60),

            "photo_edit_risk_threshold": _env_int("HER_VERIFICATION_PHOTO_EDIT_THRESHOLD", 85),
            "photo_edit_risk_medium": _env_int("HER_VERIFICATION_PHOTO_EDIT_MEDIUM", 60),

            # 自动审核策略
            "auto_approve_enabled": _env_bool("HER_VERIFICATION_AUTO_APPROVE_ENABLED", True),
            "auto_approve_strict_mode": _env_bool("HER_VERIFICATION_AUTO_APPROVE_STRICT", True),
        }
    return {}


__all__ = [
    "ALL_RULE_SLICES",
    "DEFAULT_DAILY_NOTIFICATION_CAP",
    "DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH",
    "DEFAULT_MIN_DIRECT_GREET_SCORE",
    "DEFAULT_MIN_NOTIFY_SCORE",
    "DEFAULT_QUIET_HOURS_END",
    "DEFAULT_QUIET_HOURS_START",
    "DEFAULT_RECOMMENDATION_MODE",
    "DEFAULT_SKIP_COOLDOWN_DAYS",
    "DEFAULT_CHAT_COOLDOWN_SECONDS",
    "DEFAULT_POST_CHAT_COOLDOWN_FLOOR",
    "SLICE_CHAT_ASSISTANT_COOLDOWN",
    "SLICE_PARTNER_SEARCH_RANKING",
    "SLICE_PARTNER_SEARCH_SCORING",
    "SLICE_RECOMMENDATION_DELIVERY",
    "SLICE_RECOMMENDATION_DIRECT_GREET_GATE",
    "SLICE_RECOMMENDATION_REVIEW_POLICY",
    "SLICE_VERIFICATION_AUTO_TRIAGE",
    "SLICE_VERIFICATION_THRESHOLDS",
    SLICE_PARTNER_SEARCH_RECIPROCAL,
    SLICE_RECOMMENDATION_CRITERIA,
    "code_defaults_for_slice",
]
