"""Helpers for live video challenge generation and token decoding."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime
from typing import Any, Callable

CHALLENGE_CAPTURE_MODE_REALTIME = "realtime_challenge"
DEFAULT_CHALLENGE_TTL_SECONDS = 15 * 60
DEFAULT_CHALLENGE_SPOKEN_CODE_LENGTH = 2
LIVE_CHALLENGE_ACTION_LIBRARY = {
    "blink": {"label": "眨眼"},
    "open_mouth": {"label": "张嘴"},
    "turn_left": {"label": "向左转头"},
    "turn_right": {"label": "向右转头"},
    "nod_up": {"label": "抬头"},
}


def _base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _base64url_decode(raw: str) -> bytes:
    text = str(raw or "").strip()
    if not text:
        raise ValueError("challenge token is empty")
    padding = "=" * ((4 - len(text) % 4) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _challenge_secret() -> bytes:
    raw = str(os.environ.get("HER_VERIFICATION_CHALLENGE_SECRET") or "").strip()
    if raw:
        return raw.encode("utf-8")
    return b"her-live-video-challenge-dev-secret"


def _challenge_ttl_seconds() -> int:
    raw = os.environ.get("HER_VERIFICATION_CHALLENGE_TTL_SECONDS", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_CHALLENGE_TTL_SECONDS
    return max(60, min(value, 24 * 60 * 60))


def _generate_challenge_id() -> str:
    return f"vch-{uuid.uuid4().hex[:16]}"


def challenge_phrase(required_actions: list[str], spoken_code: str | None = None) -> str:
    if not required_actions:
        base = "请按提示完成实时活体动作"
    else:
        labels = [LIVE_CHALLENGE_ACTION_LIBRARY[action]["label"] for action in required_actions]
        base = f"请依次完成：{'、'.join(labels)}"
    if spoken_code:
        return f"{base}；并大声读出数字 {spoken_code}"
    return base


def _challenge_prompt_steps(required_actions: list[str], spoken_code: str | None = None) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for action in required_actions:
        label = LIVE_CHALLENGE_ACTION_LIBRARY[action]["label"]
        steps.append(
            {
                "step_index": len(steps) + 1,
                "kind": "action",
                "action_key": action,
                "label": label,
                "instruction": f"请{label}",
            }
        )
    if spoken_code:
        steps.append(
            {
                "step_index": len(steps) + 1,
                "kind": "spoken_code",
                "spoken_code": spoken_code,
                "label": f"数字 {spoken_code}",
                "instruction": f"请大声读出数字 {spoken_code}",
            }
        )
    return steps


def _choose_challenge_spoken_code(*, user_id: str, profile_id: int | None, now: datetime) -> str:
    seed = hashlib.sha256(
        f"{user_id}|{profile_id or ''}|{now.isoformat(sep=' ')}|spoken|{uuid.uuid4().hex}".encode("utf-8")
    ).digest()
    raw = int.from_bytes(seed[:2], "big")
    lower = 10 ** (DEFAULT_CHALLENGE_SPOKEN_CODE_LENGTH - 1)
    upper = (10**DEFAULT_CHALLENGE_SPOKEN_CODE_LENGTH) - 1
    span = max(1, upper - lower + 1)
    return str(lower + (raw % span))


def _choose_default_challenge_actions(
    *,
    user_id: str,
    profile_id: int | None,
    now: datetime,
    action_count: int,
    catalog: list[str] | None = None,
) -> list[str]:
    pool = list(catalog or LIVE_CHALLENGE_ACTION_LIBRARY)
    if not pool:
        return []
    count = max(2, min(int(action_count), min(4, len(pool))))
    seed = hashlib.sha256(
        f"{user_id}|{profile_id or ''}|{now.isoformat(sep=' ')}|{uuid.uuid4().hex}".encode("utf-8")
    ).digest()
    selected: list[str] = []
    cursor = 0
    while pool and len(selected) < count:
        index = seed[cursor % len(seed)] % len(pool)
        selected.append(pool.pop(index))
        cursor += 1
    return selected


def _build_live_challenge_payload(
    *,
    challenge_id: str,
    user_id: str,
    profile_id: int | None,
    required_actions: list[str],
    challenge_text: str,
    spoken_code: str | None,
    prompt_steps: list[dict[str, Any]],
    issued_at: datetime,
    expires_at: datetime,
) -> dict[str, Any]:
    return {
        "version": 1,
        "challenge_id": challenge_id,
        "user_id": str(user_id).strip(),
        "profile_id": int(profile_id) if profile_id is not None else None,
        "required_actions": list(required_actions),
        "challenge_phrase": challenge_text,
        "spoken_code": spoken_code,
        "prompt_steps": prompt_steps,
        "capture_mode": CHALLENGE_CAPTURE_MODE_REALTIME,
        "issued_at": issued_at.isoformat(sep=" "),
        "expires_at": expires_at.isoformat(sep=" "),
    }


def _sign_live_challenge_payload(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    signature = hmac.new(_challenge_secret(), body.encode("utf-8"), hashlib.sha256).digest()
    return f"{_base64url_encode(body.encode('utf-8'))}.{_base64url_encode(signature)}"


def decode_live_challenge_token(
    challenge_token: str,
    *,
    normalize_action_keys: Callable[[Any], list[str]],
) -> dict[str, Any]:
    token = str(challenge_token or "").strip()
    if "." not in token:
        raise ValueError("challenge_token is invalid")
    payload_b64, signature_b64 = token.split(".", 1)
    payload_raw = _base64url_decode(payload_b64)
    actual_signature = _base64url_decode(signature_b64)
    expected_signature = hmac.new(_challenge_secret(), payload_raw, hashlib.sha256).digest()
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise ValueError("challenge_token signature mismatch")
    payload = json.loads(payload_raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("challenge_token payload is invalid")
    payload["required_actions"] = normalize_action_keys(payload.get("required_actions"))
    return payload


def build_live_video_verification_challenge(
    *,
    user_id: str,
    profile_id: int | None,
    required_actions: list[str],
    challenge_action_pool: list[str] | None,
    action_count: int,
    now: datetime,
) -> dict[str, Any]:
    resolved_actions = list(required_actions)
    if not resolved_actions:
        resolved_actions = _choose_default_challenge_actions(
            user_id=user_id,
            profile_id=profile_id,
            now=now,
            action_count=action_count,
            catalog=challenge_action_pool or None,
        )
    spoken_code = _choose_challenge_spoken_code(
        user_id=user_id,
        profile_id=profile_id,
        now=now,
    )
    challenge_id = _generate_challenge_id()
    challenge_text = challenge_phrase(resolved_actions, spoken_code)
    prompt_steps = _challenge_prompt_steps(resolved_actions, spoken_code)
    expires_at = datetime.fromtimestamp(now.replace(microsecond=0).timestamp() + _challenge_ttl_seconds())
    payload = _build_live_challenge_payload(
        challenge_id=challenge_id,
        user_id=user_id,
        profile_id=profile_id,
        required_actions=resolved_actions,
        challenge_text=challenge_text,
        spoken_code=spoken_code,
        prompt_steps=prompt_steps,
        issued_at=now,
        expires_at=expires_at,
    )
    return {
        **payload,
        "challenge_token": _sign_live_challenge_payload(payload),
    }
