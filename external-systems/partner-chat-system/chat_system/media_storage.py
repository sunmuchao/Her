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

DEFAULT_MINIO_ENDPOINT = "127.0.0.1:9000"
DEFAULT_MINIO_ACCESS_KEY = "her_minio_admin"
DEFAULT_MINIO_SECRET_KEY = "her_minio_password"
DEFAULT_MINIO_BUCKET = "her-media"
DEFAULT_MINIO_SECURE = False

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": [".jpg", ".jpeg"],
    "image/png": [".png"],
    "image/gif": [".gif"],
    "image/webp": [".webp"],
}

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _get_minio_config() -> dict[str, Any]:
    return {
        "endpoint": os.environ.get("MINIO_ENDPOINT", DEFAULT_MINIO_ENDPOINT),
        "access_key": os.environ.get("MINIO_ACCESS_KEY", DEFAULT_MINIO_ACCESS_KEY),
        "secret_key": os.environ.get("MINIO_SECRET_KEY", DEFAULT_MINIO_SECRET_KEY),
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
    client = _get_minio_client()
    if client is None:
        raise RuntimeError("Failed to initialize MinIO client")
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