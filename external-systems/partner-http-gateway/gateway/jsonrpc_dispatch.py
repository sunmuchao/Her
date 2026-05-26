"""JSON-RPC dispatch with visibility gate and surface gating (§13.4)."""

from __future__ import annotations

import json
from typing import Any, Protocol

from match_domain.search_self_profile import prepare_gateway_search_body
from match_domain.search_visibility import search_profiles_with_visibility_gate
from partner_search import search_profiles as partner_search_profiles

from .chat_jsonrpc import JSONRPC_NOT_HANDLED, handle_chat_jsonrpc
from .http_helpers import _json_safe, _normalize_boolish, _parse_optional_now, _read_body
from .identity import GatewayPermissionError
from .matchmaking_jsonrpc import JSONRPC_NOT_HANDLED as MATCHMAKING_JSONRPC_NOT_HANDLED, handle_matchmaking_jsonrpc
from .profile_jsonrpc import JSONRPC_NOT_HANDLED as PROFILE_JSONRPC_NOT_HANDLED, handle_profile_jsonrpc
from .profile_source_defaults import default_profile_source
from .recommendation_jsonrpc import JSONRPC_NOT_HANDLED as RECOMMENDATION_JSONRPC_NOT_HANDLED, handle_recommendation_jsonrpc
from .role_sets import INTERNAL_WRITE_ROLES
from .surface_config import is_jsonrpc_allowed
from .verification_jsonrpc import JSONRPC_NOT_HANDLED as VERIFICATION_JSONRPC_NOT_HANDLED, handle_verification_jsonrpc


class JsonrpcGateway(Protocol):
    @property
    def _chat_dsn(self) -> str: ...

    def _require_roles(
        self,
        environ: dict[str, Any],
        roles: frozenset[str],
        *,
        message: str,
    ) -> Any: ...

    def _build_async_job_dashboard(self, *, limit: int) -> dict[str, Any]: ...


def _search_profiles_jsonrpc(gateway: JsonrpcGateway, params: dict[str, Any]) -> dict[str, Any]:
    source = params.get("source") or params.get("sources")
    if not source:
        raise ValueError("source or sources is required")
    if isinstance(source, list):
        source = source[0] if source else None
    try:
        profile_dsn, profile_table = resolve_profile_source(str(source))
    except ValueError:
        profile_dsn, profile_table = default_profile_source()
    prepared = prepare_gateway_search_body(
        params,
        profile_source_dsn=profile_dsn,
        profile_table_name=profile_table,
    )
    kwargs = prepared["search_kwargs"]
    response = search_profiles_with_visibility_gate(
        partner_search_profiles,
        source=kwargs["source"],
        criteria=kwargs["criteria"],
        self_profile=kwargs["self_profile"],
        self_id=kwargs["self_id"],
        table_name=kwargs["table_name"],
        photos_table_name=kwargs["photos_table_name"],
        limit=int(kwargs["limit"]),
        photo_preview_count=int(kwargs["photo_preview_count"]),
        include_source=_normalize_boolish(kwargs.get("include_source"), False),
        include_text=_normalize_boolish(kwargs.get("include_text"), False),
        moderation_dsn=gateway._chat_dsn,
        include_moderation_blocked=_normalize_boolish(kwargs.get("include_moderation_blocked"), False),
    )
    payload = _json_safe(response)
    if prepared.get("deprecation"):
        payload["_deprecation"] = prepared["deprecation"]
    return payload


def jsonrpc_call(gateway: JsonrpcGateway, environ: dict[str, Any], method: str, params: dict[str, Any]) -> Any:
    if method == "search.search_profiles":
        return _search_profiles_jsonrpc(gateway, params)
    if method == "ops.get_async_job_dashboard":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect the async job dashboard",
        )
        try:
            limit = int(params.get("limit", 5))
        except (TypeError, ValueError):
            limit = 5
        return gateway._build_async_job_dashboard(limit=limit)

    handled = handle_verification_jsonrpc(gateway, environ, method, params)
    if handled is not VERIFICATION_JSONRPC_NOT_HANDLED:
        return handled
    handled = handle_recommendation_jsonrpc(gateway, environ, method, params)
    if handled is not RECOMMENDATION_JSONRPC_NOT_HANDLED:
        return handled
    handled = handle_matchmaking_jsonrpc(gateway, environ, method, params)
    if handled is not MATCHMAKING_JSONRPC_NOT_HANDLED:
        return handled
    handled = handle_chat_jsonrpc(gateway, environ, method, params)
    if handled is not JSONRPC_NOT_HANDLED:
        return handled
    handled = handle_profile_jsonrpc(gateway, environ, method, params)
    if handled is not PROFILE_JSONRPC_NOT_HANDLED:
        return handled
    raise ValueError(f"Unknown method: {method}")


def dispatch_gateway_jsonrpc(
    gateway: JsonrpcGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    if not is_jsonrpc_allowed():
        raise GatewayPermissionError("JSON-RPC is disabled on this gateway surface")

    try:
        raw = _read_body(environ)
        req = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        return 400, {"jsonrpc": "2.0", "error": {"code": -32700, "message": str(exc)}, "id": None}
    if not isinstance(req, dict):
        return 400, {"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"}, "id": None}

    rpc_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}
    if not isinstance(method, str):
        return 200, {"jsonrpc": "2.0", "error": {"code": -32600, "message": "method required"}, "id": rpc_id}
    if isinstance(params, list):
        return 200, {
            "jsonrpc": "2.0",
            "error": {"code": -32602, "message": "params must be a JSON object"},
            "id": rpc_id,
        }
    if not isinstance(params, dict):
        params = {}

    now = _parse_optional_now(params)
    payload = {k: v for k, v in params.items() if k != "now"}
    if now is not None:
        payload["now"] = now

    try:
        result = jsonrpc_call(gateway, environ, method, payload)
    except ValueError as exc:
        return 200, {"jsonrpc": "2.0", "error": {"code": -32602, "message": str(exc)}, "id": rpc_id}
    except GatewayPermissionError as exc:
        return 200, {"jsonrpc": "2.0", "error": {"code": -32001, "message": str(exc)}, "id": rpc_id}
    except Exception as exc:  # noqa: BLE001
        return 200, {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(exc)}, "id": rpc_id}

    if rpc_id is None:
        return 204, {}
    return 200, {"jsonrpc": "2.0", "result": _json_safe(result), "id": rpc_id}


__all__ = ["dispatch_gateway_jsonrpc", "jsonrpc_call"]
