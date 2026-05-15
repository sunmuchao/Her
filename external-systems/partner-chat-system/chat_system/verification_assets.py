"""Helpers for verification video asset decoding and storage."""

from __future__ import annotations

import base64
import hashlib
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
ALLOWED_FALLBACK_CONTENT_TYPES = {"application/octet-stream"}


def storage_root() -> Path:
    raw = os.environ.get("HER_VERIFICATION_STORAGE_DIR")
    if raw:
        return Path(raw).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / "tmp" / "verification_uploads"


def max_video_bytes() -> int:
    raw = os.environ.get("HER_VERIFICATION_MAX_BYTES", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = 32 * 1024 * 1024
    return max(value, 1024 * 1024)


def sanitize_file_name(file_name: str | None) -> str:
    base = Path(str(file_name or "live-video-upload.bin")).name
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", base).strip("._")
    return cleaned or "live-video-upload.bin"


def strip_data_url_prefix(payload: str) -> tuple[str, str | None]:
    raw = str(payload or "").strip()
    if raw.startswith("data:") and "," in raw:
        header, encoded = raw.rsplit(",", 1)
        media_type = header[5:].split(";", 1)[0].strip() or None
        return encoded, media_type
    return raw, None


def decode_video_bytes(video_base64: str) -> tuple[bytes, str | None]:
    encoded, inferred_content_type = strip_data_url_prefix(video_base64)
    compact = "".join(encoded.split())
    if not compact:
        raise ValueError("video_base64 is required")
    try:
        video_bytes = base64.b64decode(compact, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("video_base64 must be valid base64 content") from exc
    if not video_bytes:
        raise ValueError("video_base64 decoded to an empty file")
    size_limit = max_video_bytes()
    if len(video_bytes) > size_limit:
        raise ValueError(f"video file exceeds {size_limit} bytes")
    return video_bytes, inferred_content_type


def validate_video_metadata(file_name: str, content_type: str | None) -> str:
    normalized = str(content_type or "").strip().lower()
    suffix = Path(file_name).suffix.lower()
    if normalized:
        if normalized.startswith("video/") or normalized in ALLOWED_FALLBACK_CONTENT_TYPES:
            return normalized
        raise ValueError("content_type must be a video/* value")
    if suffix in ALLOWED_VIDEO_EXTENSIONS:
        return {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".m4v": "video/x-m4v",
            ".webm": "video/webm",
            ".mkv": "video/x-matroska",
        }.get(suffix, "application/octet-stream")
    raise ValueError("content_type is required when filename has no recognized video extension")


def build_storage_key(submission_id: str, file_name: str, *, attempt: int, now: datetime) -> str:
    suffix = Path(file_name).suffix or ".bin"
    stem = Path(file_name).stem[:40] or "video"
    safe_stem = re.sub(r"[^0-9A-Za-z._-]+", "_", stem).strip("._") or "video"
    token = uuid.uuid4().hex[:10]
    return f"{submission_id}/attempt-{attempt:02d}-{now.strftime('%Y%m%d%H%M%S')}-{token}-{safe_stem}{suffix}"


def write_video_asset(
    submission_id: str,
    *,
    attempt: int,
    file_name: str,
    content_type: str,
    video_bytes: bytes,
    now: datetime,
) -> dict[str, Any]:
    root = storage_root()
    root.mkdir(parents=True, exist_ok=True)
    storage_key = build_storage_key(submission_id, file_name, attempt=attempt, now=now)
    destination = root / storage_key
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(video_bytes)
    return {
        "storage_key": storage_key,
        "original_file_name": file_name,
        "content_type": content_type,
        "file_size_bytes": len(video_bytes),
        "sha256_hex": hashlib.sha256(video_bytes).hexdigest(),
    }


def remove_stored_asset(storage_key: str | None) -> None:
    if not storage_key:
        return
    path = storage_root() / str(storage_key)
    try:
        path.unlink(missing_ok=True)
    except TypeError:  # pragma: no cover - Python < 3.8 compatibility safeguard
        if path.exists():
            path.unlink()
    parent = path.parent
    root = storage_root()
    while parent != root and parent.exists():
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
