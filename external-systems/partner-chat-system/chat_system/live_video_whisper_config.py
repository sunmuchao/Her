"""Shared faster-whisper environment parsing for live-video analysis."""

from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def whisper_cache_root() -> Path:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_CACHE_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _repo_root() / "tmp" / "verification_models" / "whisper"


def whisper_device_name(*, cuda_available: bool) -> str:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_DEVICE") or "").strip().lower()
    if raw:
        if raw == "cuda" and not cuda_available:
            return "cpu"
        return raw
    return "cuda" if cuda_available else "cpu"


def whisper_compute_type(*, cuda_available: bool) -> str:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_COMPUTE_TYPE") or "").strip()
    if raw:
        return raw
    return "float16" if cuda_available else "int8"


def whisper_model_source() -> tuple[str, bool]:
    raw_dir = str(os.environ.get("HER_VERIFICATION_WHISPER_MODEL_DIR") or "").strip()
    if raw_dir:
        return str(Path(raw_dir).expanduser().resolve()), True
    return whisper_model_name(), False


def whisper_model_name() -> str:
    raw = str(os.environ.get("HER_VERIFICATION_WHISPER_MODEL") or "").strip()
    return raw or "tiny"
