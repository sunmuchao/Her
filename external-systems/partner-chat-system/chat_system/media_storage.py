"""MinIO media storage service for chat image uploads."""

from __future__ import annotations

import hashlib
import io
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from minio import Minio  # type: ignore[import-untyped]
    from minio.error import S3Error  # type: ignore[import-untyped]
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False
    Minio = None  # type: ignore[assignment,misc]
    S3Error = Exception  # type: ignore[assignment,misc]

LOGGER = logging.getLogger(__name__)

# 安全修复：移除硬编码的默认凭证
# MinIO 凭证必须通过环境变量配置，禁止使用硬编码默认值
DEFAULT_MINIO_ENDPOINT = "127.0.0.1:9000"  # 仅开发环境默认值
DEFAULT_MINIO_BUCKET = "her-media"
DEFAULT_MINIO_SECURE = False

# 安全警告：以下环境变量必须配置
_REQUIRED_MINIO_ENV_VARS = ["MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"]

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/gif": [".gif"],
    "image/webp": [".webp"],
}

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _get_minio_config() -> dict[str, Any]:
    """
    获取 MinIO 配置，要求必须配置凭证环境变量。

    安全修复：移除硬编码默认凭证，强制要求环境变量配置。
    增强：生产环境强制凭证长度检查。
    """
    # 检查必需的环境变量
    missing_vars = []
    for var in _REQUIRED_MINIO_ENV_VARS:
        if not os.environ.get(var):
            missing_vars.append(var)

    if missing_vars:
        raise ValueError(
            f"MinIO credentials not configured: missing environment variables {missing_vars}. "
            f"Please set MINIO_ACCESS_KEY and MINIO_SECRET_KEY before starting the service. "
            f"DO NOT use hardcoded default credentials."
        )

    # 验证凭证强度（生产环境）
    access_key = os.environ.get("MINIO_ACCESS_KEY", "")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "")

    # ✅ 增强：生产环境强制凭证长度检查
    if os.environ.get("HER_PRODUCTION_MODE"):
        # 生产环境：强制强密码
        if len(access_key) < 20:
            raise ValueError(
                "Production mode requires strong MinIO credentials: "
                "MINIO_ACCESS_KEY >= 20 chars. Current length: {len(access_key)}. "
                "Use strong, unique access key for production."
            )
        if len(secret_key) < 40:
            raise ValueError(
                "Production mode requires strong MinIO credentials: "
                "MINIO_SECRET_KEY >= 40 chars. Current length: {len(secret_key)}. "
                "Use strong, unique secret key for production."
            )

    # 检查是否使用开发环境常见的弱凭证
    weak_credentials = {
        "her_minio_admin": "her_minio_password",
        "minioadmin": "minioadmin",
        "admin": "admin",
        "root": "root",
    }
    if access_key in weak_credentials and secret_key == weak_credentials.get(access_key):
        LOGGER.warning(
            f"SECURITY WARNING: Using weak MinIO credentials (access_key='{access_key}'). "
            f"Please use strong credentials in production."
        )
        # 在生产模式下禁止使用弱凭证
        if os.environ.get("HER_PRODUCTION_MODE"):
            raise ValueError(
                f"Production mode rejects weak MinIO credentials. "
                f"Please configure strong MINIO_ACCESS_KEY and MINIO_SECRET_KEY."
            )

    return {
        "endpoint": os.environ.get("MINIO_ENDPOINT", DEFAULT_MINIO_ENDPOINT),
        "access_key": access_key,
        "secret_key": secret_key,
        "bucket": os.environ.get("MINIO_BUCKET", DEFAULT_MINIO_BUCKET),
        "secure": os.environ.get("MINIO_SECURE", "false").lower() in ("true", "1", "yes"),
    }


def _get_minio_client() -> Minio | None:
    if not MINIO_AVAILABLE:
        LOGGER.warning("minio package not installed; media uploads will fail")
        return None
    config = _get_minio_config()
    return Minio(
        config["endpoint"],
        access_key=config["access_key"],
        secret_key=config["secret_key"],
        secure=config["secure"],
    )


def _ensure_bucket_exists(client: Minio, bucket: str) -> None:
    try:
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            LOGGER.info("Created MinIO bucket: %s", bucket)
    except S3Error as e:
        LOGGER.error("Failed to ensure bucket %s exists: %s", bucket, e)
        raise


def _detect_content_type(data: bytes, filename: str) -> str | None:
    ext = Path(filename).suffix.lower()
    for content_type, extensions in ALLOWED_IMAGE_TYPES.items():
        if ext in extensions:
            return content_type
    if len(data) >= 8:
        if data[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        if data[:2] == b'\xff\xd8':
            return "image/jpeg"
        if data[:6] in (b'GIF87a', b'GIF89a'):
            return "image/gif"
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
            return "image/webp"
    return None


def _validate_image(data: bytes, filename: str) -> str:
    if len(data) > MAX_IMAGE_SIZE_BYTES:
        raise ValueError(f"Image size {len(data)} exceeds maximum {MAX_IMAGE_SIZE_BYTES} bytes")
    content_type = _detect_content_type(data, filename)
    if content_type is None:
        raise ValueError(f"Unsupported image type for file: {filename}")
    return content_type


def _generate_object_key(user_id: str, content_type: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    uuid_hex = uuid.uuid4().hex[:8]
    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
        "image/webp": ".webp",
    }
    ext = ext_map.get(content_type, ".jpg")
    return f"chat/{user_id}/{ts}_{uuid_hex}{ext}"


def upload_image(
    data: bytes,
    filename: str,
    user_id: str,
    *,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not MINIO_AVAILABLE:
        raise RuntimeError("MinIO client not available; install minio package")

    # Quick health check before attempting upload
    config = _get_minio_config()
    endpoint = config["endpoint"]
    try:
        import socket
        host, port_str = endpoint.split(":")
        port = int(port_str)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            if sock.connect_ex((host, port)) != 0:
                raise RuntimeError(
                    f"MinIO service unavailable at {endpoint}. "
                    f"Start it with: docker compose up -d minio"
                )
    except (ValueError, OSError) as e:
        LOGGER.warning("MinIO endpoint check failed: %s", e)

    client = _get_minio_client()
    if client is None:
        raise RuntimeError(
            f"Failed to initialize MinIO client for endpoint {endpoint}. "
            f"Check if MinIO is running: docker compose up -d minio"
        )
    config = _get_minio_config()
    bucket = config["bucket"]
    _ensure_bucket_exists(client, bucket)
    content_type = _validate_image(data, filename)
    object_key = _generate_object_key(user_id, content_type)
    size = len(data)
    content_hash = hashlib.sha256(data).hexdigest()
    minio_metadata = {
        "user-id": user_id,
        "original-filename": filename,
        "content-hash": content_hash,
        "uploaded-at": datetime.now(timezone.utc).isoformat(),
    }
    if metadata:
        for k, v in metadata.items():
            if v is not None:
                minio_metadata[k] = str(v)
    client.put_object(
        bucket,
        object_key,
        io.BytesIO(data),
        size,
        content_type=content_type,
        metadata=minio_metadata,
    )
    endpoint = config["endpoint"]
    secure = config["secure"]
    protocol = "https" if secure else "http"
    media_url = f"{protocol}://{endpoint}/{bucket}/{object_key}"
    return {
        "media_id": object_key,
        "media_url": media_url,
        "content_type": content_type,
        "size": size,
        "content_hash": content_hash,
        "bucket": bucket,
        "object_key": object_key,
    }


def upload_audio(
    data: bytes,
    filename: str,
    user_id: str,
    *,
    metadata: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Upload audio file to MinIO storage.

    Args:
        data: Audio bytes (MP3/WAV format)
        filename: Original filename
        user_id: User ID for storage path
        metadata: Additional metadata (tts_engine, voice, etc.)

    Returns:
        dict with media_id, media_url, content_type, size, duration_ms, format

    Raises:
        RuntimeError: If MinIO unavailable or upload fails
    """
    if not MINIO_AVAILABLE:
        raise RuntimeError("MinIO client not available; install minio package")

    # Quick health check before attempting upload
    config = _get_minio_config()
    endpoint = config["endpoint"]
    try:
        import socket
        host, port_str = endpoint.split(":")
        port = int(port_str)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            if sock.connect_ex((host, port)) != 0:
                raise RuntimeError(
                    f"MinIO service unavailable at {endpoint}. "
                    f"Start it with: docker compose up -d minio"
                )
    except (ValueError, OSError) as e:
        LOGGER.warning("MinIO endpoint check failed: %s", e)

    client = _get_minio_client()
    if client is None:
        raise RuntimeError(
            f"Failed to initialize MinIO client for endpoint {endpoint}. "
            f"Check if MinIO is running: docker compose up -d minio"
        )
    config = _get_minio_config()
    bucket = config["bucket"]
    _ensure_bucket_exists(client, bucket)

    # Detect audio format from magic number or filename
    content_type = None
    audio_format = None

    # MP3 magic number
    if data[:3] == b"ID3" or data[:2] == b"\xFF\xFB" or data[:2] == b"\xFF\xFA":
        content_type = "audio/mpeg"
        audio_format = "mp3"
    # WAV magic number
    elif data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        content_type = "audio/wav"
        audio_format = "wav"
    # Default from filename extension
    else:
        ext = filename.lower().split(".")[-1] if "." in filename else "mp3"
        if ext == "mp3" or ext == "mpeg":
            content_type = "audio/mpeg"
            audio_format = "mp3"
        elif ext == "wav":
            content_type = "audio/wav"
            audio_format = "wav"
        elif ext == "ogg":
            content_type = "audio/ogg"
            audio_format = "ogg"
        elif ext == "m4a" or ext == "mp4":
            content_type = "audio/mp4"
            audio_format = "m4a"
        else:
            content_type = "audio/mpeg"  # Default to MP3
            audio_format = "mp3"

    object_key = _generate_object_key(user_id, content_type)
    size = len(data)
    content_hash = hashlib.sha256(data).hexdigest()

    minio_metadata = {
        "user-id": user_id,
        "original-filename": filename,
        "content-hash": content_hash,
        "uploaded-at": datetime.now(timezone.utc).isoformat(),
        "audio-format": audio_format,
    }
    if metadata:
        for k, v in metadata.items():
            if v is not None:
                minio_metadata[k] = str(v)

    client.put_object(
        bucket,
        object_key,
        io.BytesIO(data),
        size,
        content_type=content_type,
        metadata=minio_metadata,
    )

    endpoint = config["endpoint"]
    secure = config["secure"]
    protocol = "https" if secure else "http"
    media_url = f"{protocol}://{endpoint}/{bucket}/{object_key}"

    # Calculate duration (optional, requires pydub)
    duration_ms = None
    try:
        from pydub import AudioSegment
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=f".{audio_format}", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        audio_segment = AudioSegment.from_file(tmp_path, format=audio_format)
        duration_ms = len(audio_segment)
        os.unlink(tmp_path)
    except ImportError:
        LOGGER.warning("pydub not available; cannot calculate audio duration")
    except Exception as e:
        LOGGER.warning(f"Failed to calculate audio duration: {e}")

    return {
        "media_id": object_key,
        "media_url": media_url,
        "content_type": content_type,
        "size": size,
        "content_hash": content_hash,
        "bucket": bucket,
        "object_key": object_key,
        "duration_ms": duration_ms,
        "format": audio_format,
    }


def get_media_url(object_key: str) -> str | None:
    config = _get_minio_config()
    endpoint = config["endpoint"]
    secure = config["secure"]
    bucket = config["bucket"]
    protocol = "https" if secure else "http"
    return f"{protocol}://{endpoint}/{bucket}/{object_key}"


def delete_media(object_key: str) -> bool:
    if not MINIO_AVAILABLE:
        LOGGER.warning("MinIO not available; cannot delete media")
        return False
    client = _get_minio_client()
    if client is None:
        return False
    config = _get_minio_config()
    bucket = config["bucket"]
    try:
        client.remove_object(bucket, object_key)
        LOGGER.info("Deleted media object: %s", object_key)
        return True
    except S3Error as e:
        LOGGER.error("Failed to delete media %s: %s", object_key, e)
        return False


def check_minio_health() -> dict[str, Any]:
    result = {
        "available": MINIO_AVAILABLE,
        "endpoint": _get_minio_config()["endpoint"],
        "bucket": _get_minio_config()["bucket"],
        "connected": False,
        "bucket_exists": False,
    }
    if not MINIO_AVAILABLE:
        return result
    client = _get_minio_client()
    if client is None:
        return result
    result["connected"] = True
    config = _get_minio_config()
    try:
        result["bucket_exists"] = client.bucket_exists(config["bucket"])
    except S3Error:
        pass
    return result