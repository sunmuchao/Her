"""Helpers for speech challenge normalization and transcript parsing."""

from __future__ import annotations

import re
from typing import Any

from her_time_utils import as_text as _as_text

CHINESE_DIGIT_MAP = {
    "零": "0",
    "〇": "0",
    "○": "0",
    "洞": "0",
    "一": "1",
    "幺": "1",
    "二": "2",
    "两": "2",
    "三": "3",
    "四": "4",
    "五": "5",
    "六": "6",
    "七": "7",
    "八": "8",
    "九": "9",
}


def normalize_percent_score(value: Any, default: int) -> int:
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return int(default)
    if 0 <= normalized <= 1:
        normalized *= 100
    return max(0, min(int(round(normalized)), 100))


def _normalize_spoken_digits(text: Any) -> str:
    raw = _as_text(text)
    if not raw:
        return ""
    digits: list[str] = []
    for char in raw:
        if char.isdigit():
            digits.append(char)
        elif char in CHINESE_DIGIT_MAP:
            digits.append(CHINESE_DIGIT_MAP[char])
    return "".join(digits)


def transcript_excerpt(text: Any, *, limit: int = 36) -> str | None:
    raw = _as_text(text)
    if not raw:
        return None
    compact = re.sub(r"\s+", " ", raw)
    if len(compact) <= limit:
        return compact
    return f"{compact[:limit].rstrip()}..."


def normalize_speech_challenge_result(metadata: dict[str, Any]) -> dict[str, Any]:
    raw = metadata.get("speech_challenge_result") or metadata.get("speech_result")
    if not isinstance(raw, dict):
        return {}
    out = dict(raw)
    transcript_text = _as_text(
        out.get("transcript_text")
        or out.get("transcript")
        or out.get("recognized_text")
        or out.get("text")
    )
    segments: list[dict[str, Any]] = []
    raw_segments = out.get("transcript_segments") or out.get("segments")
    if isinstance(raw_segments, list):
        for segment in raw_segments:
            if not isinstance(segment, dict):
                continue
            normalized: dict[str, Any] = {}
            segment_text = _as_text(
                segment.get("text") or segment.get("transcript") or segment.get("recognized_text")
            )
            if segment_text:
                normalized["text"] = segment_text
            for key in ("start_ms", "end_ms"):
                raw_value = segment.get(key)
                if raw_value is None:
                    continue
                try:
                    normalized[key] = max(0, int(raw_value))
                except (TypeError, ValueError):
                    continue
            if "confidence" in segment:
                normalized["confidence"] = normalize_percent_score(segment.get("confidence"), 0)
            if normalized:
                segments.append(normalized)
    if not transcript_text and segments:
        transcript_text = " ".join(_as_text(item.get("text")) for item in segments if _as_text(item.get("text")))
    out["provider"] = _as_text(out.get("provider") or out.get("source") or out.get("engine")) or None
    out["transcript_text"] = transcript_text or None
    out["transcript_segments"] = segments
    if "transcript_confidence" in out:
        out["transcript_confidence"] = normalize_percent_score(out.get("transcript_confidence"), 0)
    elif "confidence" in out:
        out["transcript_confidence"] = normalize_percent_score(out.get("confidence"), 0)
    recognized_digits = _normalize_spoken_digits(transcript_text)
    out["recognized_digits"] = recognized_digits or None
    for key in ("speech_started_at_ms", "speech_ended_at_ms", "audio_duration_ms"):
        raw_value = out.get(key)
        if raw_value is None:
            continue
        try:
            out[key] = max(0, int(raw_value))
        except (TypeError, ValueError):
            out.pop(key, None)
    if "audio_video_sync_score" in out:
        out["audio_video_sync_score"] = normalize_percent_score(out.get("audio_video_sync_score"), 0)
    raw_match = out.get("code_match")
    if raw_match is not None:
        if isinstance(raw_match, str):
            out["code_match"] = raw_match.strip().lower() in {"1", "true", "yes", "on"}
        else:
            out["code_match"] = bool(raw_match)
    return out
