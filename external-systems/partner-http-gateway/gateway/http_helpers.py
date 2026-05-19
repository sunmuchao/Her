"""Reusable HTTP/request helpers for the partner gateway."""

from __future__ import annotations

from collections.abc import Mapping
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs

from her_json_utils import json_safe

from . import _paths  # noqa: F401 - side effect: sys.path

from match_domain import new_trace_id  # noqa: E402

from .request_policy import client_ip

DEMO_ASSET_ROOT = Path(__file__).with_name("demo_assets")
DEMO_HTML_FILES = {
    "/demo/live-video-verification": Path(__file__).with_name("live_video_verification_demo.html"),
    "/demo/auth": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "auth-entry.html",
    "/demo/auth/code": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "auth-code.html",
    "/demo/auth/onboarding/basic": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "auth-onboarding-basic.html",
    "/demo/auth/onboarding/profile": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "auth-onboarding-profile.html",
    "/demo/auth/onboarding/trust": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "auth-onboarding-trust.html",
    "/demo/search": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "search.html",
    "/demo/discovery": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "discovery.html",
    "/demo/discovery/profile-detail": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "profile-detail.html",
    "/demo/recommendations": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "recommendations.html",
    "/demo/chat": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "chat.html",
    "/demo/chat/report": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "chat-report.html",
    "/demo/chat/meeting-feedback": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "chat-meeting-feedback.html",
    "/demo/chat/risk-sidebar": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "chat-risk-sidebar.html",
    "/demo/trust": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "trust.html",
    "/demo/trust/task": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "trust-task.html",
    "/demo/trust/appeals": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "trust-appeals.html",
    "/demo/me": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "me.html",
    "/demo/me/profile": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "me-profile.html",
    "/demo/me/preferences": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "me-preferences.html",
    "/demo/me/history": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "me-history.html",
    "/demo/notifications": _paths._REPO_ROOT / "docs" / "frontend-prototypes" / "notifications.html",
}

DEMO_RUNTIME_TAG = '<script defer src="/demo/assets/her-demo/prototypes.js"></script>'


def _incoming_trace_id(environ: dict[str, Any]) -> str:
    raw = (
        (environ.get("HTTP_X_TRACE_ID") or "").strip()
        or (environ.get("HTTP_X_REQUEST_ID") or "").strip()
    )
    if raw and len(raw) <= 128:
        return raw
    return new_trace_id()


def _wrap_trace_headers(base: Callable[..., Any], trace_id: str) -> Callable[..., Any]:
    def sr(status: str, response_headers: list[tuple[str, str]], exc_info: Any = None) -> Any:
        merged = list(response_headers)
        if not any(h[0].lower() == "x-trace-id" for h in merged):
            merged.append(("X-Trace-ID", trace_id))
        # Some test doubles only implement the 2-arg WSGI ``start_response`` signature.
        if exc_info is not None:
            return base(status, merged, exc_info)
        return base(status, merged)

    return sr


def _extract_client_idempotency_key(environ: dict[str, Any], body: dict[str, Any]) -> str | None:
    header_value = (environ.get("HTTP_IDEMPOTENCY_KEY") or "").strip()
    if header_value:
        return header_value[:191]
    body_value = body.get("client_idempotency_key")
    if body_value is None and isinstance(body, dict):
        body_value = body.get("idempotency_key")
    return _trimmed_client_idempotency_key(body_value)


def _trimmed_client_idempotency_key(value: Any) -> str | None:
    if value is not None and str(value).strip():
        return str(value).strip()[:191]
    return None


def _payload_without_keys(
    params: Mapping[str, Any],
    excluded_keys: set[str] | frozenset[str],
) -> dict[str, Any]:
    return {key: value for key, value in params.items() if key not in excluded_keys}


def _gateway_error_payload(code: str, message: str, trace_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}, "trace_id": trace_id}


def _normalize_demo_html_path(path: str) -> str:
    return str(path or "/").rstrip("/") or "/"


def _demo_html_file(path: str) -> Path | None:
    return DEMO_HTML_FILES.get(_normalize_demo_html_path(path))


def _inject_demo_runtime(path: str, html: str) -> str:
    normalized = _normalize_demo_html_path(path)
    if normalized == "/demo/live-video-verification" or DEMO_RUNTIME_TAG in html:
        return html
    if "</body>" in html:
        return html.replace("</body>", f"  {DEMO_RUNTIME_TAG}\n  </body>", 1)
    return f"{html}\n{DEMO_RUNTIME_TAG}\n"


def _read_demo_html(path: str) -> str | None:
    demo_file = _demo_html_file(path)
    if demo_file is None:
        return None
    html = demo_file.read_text(encoding="utf-8")
    return _inject_demo_runtime(path, html)


def _demo_asset_file(asset_path: str) -> Path | None:
    cleaned = str(asset_path or "").lstrip("/")
    if not cleaned:
        return None
    target = (DEMO_ASSET_ROOT / cleaned).resolve()
    root = DEMO_ASSET_ROOT.resolve()
    if target != root and root not in target.parents:
        return None
    if not target.is_file():
        return None
    return target


def _json_safe(value: Any) -> Any:
    return json_safe(value)


def _read_body(environ: dict[str, Any], max_bytes: int = 8 * 1024 * 1024) -> bytes:
    try:
        size = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        size = 0
    if size > max_bytes:
        raise ValueError("Request body too large")
    stream = environ["wsgi.input"]
    return stream.read(size) if size else stream.read()


def _parse_json_body(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def _parse_optional_now(params: dict[str, Any]) -> datetime | None:
    raw = params.get("now")
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(str(raw))


def _normalize_optional_now_text(raw: Any) -> str | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.replace(microsecond=0).isoformat(sep=" ")
    return datetime.fromisoformat(str(raw)).replace(microsecond=0).isoformat(sep=" ")


def _query_dict(environ: dict[str, Any]) -> dict[str, str]:
    parsed = parse_qs(environ.get("QUERY_STRING") or "", keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _normalize_boolish(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _subscription_ids_from_query(q: dict[str, str]) -> list[str] | None:
    raw = q.get("subscription_ids") or q.get("ids")
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def _parse_int(raw_value: Any, default: int) -> int:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return default


def _parse_optional_int(raw_value: Any) -> int | None:
    if raw_value in (None, ""):
        return None
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _statuses_from_query(q: dict[str, str], key: str = "status") -> list[str] | None:
    raw = q.get(key) or q.get("statuses")
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def _augment_chat_message_metadata(environ: dict[str, Any], metadata: Any) -> dict[str, Any] | None:
    payload = dict(metadata) if isinstance(metadata, dict) else {}
    risk_observation = dict(payload.get("risk_observation") or {})
    remote_ip = client_ip(environ)
    if remote_ip and remote_ip != "0.0.0.0":
        risk_observation.setdefault("client_ip", remote_ip)
    user_agent = (environ.get("HTTP_USER_AGENT") or "").strip()
    if user_agent:
        risk_observation.setdefault("user_agent", user_agent[:512])
    if risk_observation:
        payload["risk_observation"] = risk_observation
    return payload or None
