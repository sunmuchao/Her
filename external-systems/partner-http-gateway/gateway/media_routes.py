"""Media upload HTTP handlers for the gateway."""

from __future__ import annotations

import re
from typing import Any, Protocol

from match_domain import get_trace_id  # noqa: E402

from .http_helpers import _json_safe, _read_body


class MediaGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def _parse_multipart_form_data(content_type: str, raw_body: bytes) -> dict[str, Any]:
    boundary_match = re.search(r"boundary=(.+)", content_type)
    if not boundary_match:
        raise ValueError("Missing boundary in multipart content-type")
    boundary = boundary_match.group(1).strip()
    if boundary.startswith('"') and boundary.endswith('"'):
        boundary = boundary[1:-1]
    boundary_bytes = boundary.encode("utf-8")
    delimiter = b"\r\n--" + boundary_bytes + b"\r\n"
    end_delimiter = b"\r\n--" + boundary_bytes + b"--\r\n"
    if raw_body.endswith(end_delimiter):
        raw_body = raw_body[:-len(end_delimiter)]
    elif raw_body.endswith(b"--" + boundary_bytes + b"--"):
        raw_body = raw_body[:-len(b"--" + boundary_bytes + b"--")]
    parts = raw_body.split(delimiter)
    result: dict[str, Any] = {"fields": {}, "files": {}}
    for part in parts:
        if not part.strip():
            continue
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        headers_raw = part[:header_end].decode("utf-8", errors="replace")
        content = part[header_end + 4:]
        if content.endswith(b"\r\n"):
            content = content[:-2]
        headers: dict[str, str] = {}
        for line in headers_raw.split("\r\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.strip().lower()] = value.strip()
        disposition = headers.get("content-disposition", "")
        name_match = re.search(r'name="([^"]+)"', disposition)
        if not name_match:
            continue
        field_name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]+)"', disposition)
        if filename_match:
            filename = filename_match.group(1)
            content_type_header = headers.get("content-type", "application/octet-stream")
            result["files"][field_name] = {
                "filename": filename,
                "content_type": content_type_header,
                "data": content,
            }
        else:
            result["fields"][field_name] = content.decode("utf-8", errors="replace")
    return result


def rest_media_upload(
    gateway: MediaGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    content_type = environ.get("CONTENT_TYPE", "")
    if not content_type.startswith("multipart/form-data"):
        return 400, {
            "error": {"code": "invalid_content_type", "message": "Expected multipart/form-data"},
            "trace_id": get_trace_id(),
        }
    try:
        raw_body = _read_body(environ, max_bytes=20 * 1024 * 1024)
    except ValueError as e:
        return 400, {
            "error": {"code": "body_too_large", "message": str(e)},
            "trace_id": get_trace_id(),
        }
    try:
        form_data = _parse_multipart_form_data(content_type, raw_body)
    except ValueError as e:
        return 400, {
            "error": {"code": "invalid_multipart", "message": str(e)},
            "trace_id": get_trace_id(),
        }
    file_field = form_data["files"].get("file") or form_data["files"].get("image")
    if not file_field:
        return 400, {
            "error": {"code": "missing_file", "message": "No file uploaded in multipart form"},
            "trace_id": get_trace_id(),
        }
    actor = gateway._current_actor(environ)
    if actor is None:
        return 401, {
            "error": {"code": "unauthorized", "message": "Authentication required for media upload"},
            "trace_id": get_trace_id(),
        }
    user_id = str(actor.actor_id)
    filename = file_field["filename"]
    data = file_field["data"]
    metadata_fields = form_data["fields"]
    metadata: dict[str, str] = {}
    if metadata_fields.get("thread_id"):
        metadata["thread_id"] = metadata_fields["thread_id"]
    if metadata_fields.get("conversation_id"):
        metadata["conversation_id"] = metadata_fields["conversation_id"]
    try:
        from chat_system.media_storage import upload_image  # type: ignore[import-untyped]
        result = upload_image(data, filename, user_id, metadata=metadata)
    except ImportError:
        return 500, {
            "error": {"code": "media_storage_unavailable", "message": "Media storage service not configured"},
            "trace_id": get_trace_id(),
        }
    except ValueError as e:
        return 400, {
            "error": {"code": "invalid_image", "message": str(e)},
            "trace_id": get_trace_id(),
        }
    except RuntimeError as e:
        return 500, {
            "error": {"code": "upload_failed", "message": str(e)},
            "trace_id": get_trace_id(),
        }
    return 201, {
        "media_id": result["media_id"],
        "media_url": result["media_url"],
        "metadata": {
            "content_type": result["content_type"],
            "size": result["size"],
            "content_hash": result["content_hash"],
        },
        "trace_id": get_trace_id(),
    }


def rest_media_health(
    gateway: MediaGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        from chat_system.media_storage import check_minio_health  # type: ignore[import-untyped]
        health = check_minio_health()
    except ImportError:
        health = {"available": False, "error": "media_storage module not found"}
    return 200, {**_json_safe(health), "trace_id": get_trace_id()}


def dispatch_media_rest(
    gateway: MediaGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v2/media/upload" and method == "POST":
        return rest_media_upload(gateway, environ)
    if path == "/v2/media/health" and method == "GET":
        return rest_media_health(gateway, environ)
    return None


__all__ = [
    "MediaGateway",
    "rest_media_upload",
    "rest_media_health",
    "dispatch_media_rest",
]