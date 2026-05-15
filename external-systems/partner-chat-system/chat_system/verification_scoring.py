"""Pure scoring helpers for verification machine review."""

from __future__ import annotations

from typing import Any


def normalize_machine_score(value: Any, default: int) -> int:
    try:
        normalized = int(round(float(value)))
    except (TypeError, ValueError):
        normalized = int(default)
    return max(0, min(normalized, 100))


def score_result(score: int, *, pass_threshold: int = 85, fail_threshold: int = 60) -> str:
    if score >= pass_threshold:
        return "pass"
    if score < fail_threshold:
        return "fail"
    return "unclear"


def derive_action_challenge_score(
    *,
    action_result: dict[str, Any],
    required_actions: list[str],
    completed_actions: set[str],
    action_scores: dict[str, int],
    action_completion_ratio: float,
    face_count_max: int,
    challenge_hint: str,
    default_score: int,
) -> int:
    challenge_score = int(default_score)
    if action_result:
        average_action_score = 0
        if required_actions:
            score_values = [action_scores.get(action, 100 if action in completed_actions else 0) for action in required_actions]
            average_action_score = int(sum(score_values) / len(score_values)) if score_values else 0
        challenge_score = int(round((action_completion_ratio * 70) + (average_action_score * 0.30)))
        if action_result.get("challenge_passed"):
            challenge_score = max(challenge_score, 90)
        if face_count_max > 1:
            challenge_score = max(0, challenge_score - 25)
    elif challenge_hint in {"completed", "pass"}:
        challenge_score = 92
    elif challenge_hint in {"fail", "missing"}:
        challenge_score = 20
    return max(0, min(int(challenge_score), 100))


def apply_speech_review_to_machine_scores(
    *,
    challenge_score: int,
    risk_flags: list[str],
    speech_review: dict[str, Any],
) -> int:
    if not speech_review:
        return challenge_score
    updated = int(challenge_score)
    speech_score = normalize_machine_score(speech_review.get("speech_score"), 0)
    if speech_review.get("speech_result") == "pass":
        updated = max(updated, int(round((updated * 0.60) + (speech_score * 0.40))))
    elif speech_review.get("speech_result") == "unclear":
        updated = min(updated, int(round((updated * 0.80) + (speech_score * 0.20))))
    else:
        updated = min(updated, speech_score)
    for flag in list(speech_review.get("risk_flags") or []):
        if flag not in risk_flags:
            risk_flags.append(flag)
    return max(0, min(updated, 100))
