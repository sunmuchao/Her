"""Isolated faster-whisper worker for live-video speech transcription."""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import ctranslate2
from faster_whisper import WhisperModel


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _whisper_cache_root() -> Path:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_CACHE_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _repo_root() / "tmp" / "verification_models" / "whisper"


def _whisper_device_name() -> str:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_DEVICE") or "").strip().lower()
    if raw:
        if raw == "cuda" and ctranslate2.get_cuda_device_count() <= 0:
            return "cpu"
        return raw
    return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"


def _whisper_compute_type() -> str:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_COMPUTE_TYPE") or "").strip()
    if raw:
        return raw
    return "float16" if ctranslate2.get_cuda_device_count() > 0 else "int8"


def _whisper_model_source() -> tuple[str, bool]:
    raw_dir = str(os.environ.get("HER_VERIFICATION_WHISPER_MODEL_DIR") or "").strip()
    if raw_dir:
        return str(Path(raw_dir).expanduser().resolve()), True
    return _whisper_model_name(), False


def _whisper_model_name() -> str:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_MODEL") or "").strip()
    return raw or "tiny"


def _bounded_score(value: float | int) -> int:
    return max(0, min(int(round(float(value))), 100))


def _segment_confidence(avg_logprob: float | None) -> int:
    if avg_logprob is None:
        return 0
    return _bounded_score(math.exp(float(avg_logprob)) * 100)


def transcribe_audio(audio_path: str | Path) -> dict[str, Any]:
    cache_root = _whisper_cache_root()
    cache_root.mkdir(parents=True, exist_ok=True)
    model_source, local_files_only = _whisper_model_source()
    model = WhisperModel(
        model_source,
        device=_whisper_device_name(),
        compute_type=_whisper_compute_type(),
        download_root=str(cache_root),
        local_files_only=local_files_only,
    )
    language = str(os.environ.get("HER_VERIFICATION_WHISPER_LANGUAGE") or "").strip() or None
    segments_iter, _ = model.transcribe(
        str(Path(audio_path).expanduser().resolve()),
        language=language,
        task="transcribe",
        beam_size=1,
        best_of=1,
        temperature=0.0,
        condition_on_previous_text=False,
        vad_filter=True,
        word_timestamps=False,
    )
    segments: list[dict[str, Any]] = []
    transcript_parts: list[str] = []
    confidence_values: list[int] = []
    for segment in segments_iter:
        text = str(getattr(segment, "text", "") or "").strip()
        if not text:
            continue
        start_ms = max(0, int(round(float(getattr(segment, "start", 0.0)) * 1000)))
        end_ms = max(start_ms, int(round(float(getattr(segment, "end", 0.0)) * 1000)))
        confidence = _segment_confidence(getattr(segment, "avg_logprob", None))
        transcript_parts.append(text)
        confidence_values.append(confidence)
        segments.append(
            {
                "text": text,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "confidence": confidence,
            }
        )
    transcript_text = " ".join(transcript_parts).strip() or None
    started_at = segments[0]["start_ms"] if segments else None
    ended_at = segments[-1]["end_ms"] if segments else None
    audio_duration_ms = ended_at if ended_at is not None else 0
    return {
        "provider": "faster_whisper",
        "model_name": _whisper_model_name(),
        "transcript_text": transcript_text,
        "transcript_segments": segments,
        "transcript_confidence": _bounded_score(sum(confidence_values) / len(confidence_values)) if confidence_values else 0,
        "speech_started_at_ms": started_at,
        "speech_ended_at_ms": ended_at,
        "audio_duration_ms": audio_duration_ms,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m chat_system.live_video_whisper_worker <audio_path>", file=sys.stderr)
        return 2
    result = transcribe_audio(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
