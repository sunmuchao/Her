"""Central REST dispatch with surface checks (§13.4)."""

from __future__ import annotations

from typing import Any, Protocol

from .auth_routes import dispatch_private_auth_rest
from .bff.candidate_detail import dispatch_candidate_bff
from .bff.search_profiles import rest_search_profiles
from .call_routes import dispatch_call_rest
from .chat_routes import dispatch_chat_rest
from .chat_safety_routes import dispatch_chat_safety_rest
from .collected_routes import dispatch_collected_rest
from .discovery_routes import dispatch_discovery_rest
from .assessment_routes import dispatch_assessment_rest
from .values_auction_routes import dispatch_values_auction_rest
from .http_helpers import _parse_json_body, _read_body
from .ledger_routes import dispatch_ledger_rest
from .matchmaking_routes import dispatch_matchmaking_rest
from .media_routes import dispatch_media_rest
from .ops_routes import dispatch_ops_rest
from .persona_routes import dispatch_persona_rest
from .profile_routes import dispatch_profile_rest
from .proxy_intro_routes import dispatch_proxy_intro_rest
from .recommendation_routes import dispatch_recommendation_rest
from .support_routes import dispatch_support_rest
from .surface_config import gateway_surface, is_rest_path_allowed
from .verification_routes import dispatch_verification_rest


class RestDispatchGateway(Protocol):
    def handle_health(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]: ...


def dispatch_gateway_rest(
    gateway: RestDispatchGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO") or "/"
    path = path.rstrip("/") or "/"

    if not is_rest_path_allowed(path, method):
        return 403, {
            "error": {
                "code": "surface_forbidden",
                "message": f"Route not available on gateway surface {gateway_surface()!r}",
            }
        }

    if path == "/health" and method == "GET":
        return gateway.handle_health(environ)

    if path == "/v1/search/profiles" and method == "POST":
        return rest_search_profiles(gateway, environ, _parse_json_body(_read_body(environ)))

    for dispatcher in (
        dispatch_ops_rest,
        dispatch_assessment_rest,
        dispatch_values_auction_rest,
        dispatch_persona_rest,
        dispatch_candidate_bff,
        dispatch_ledger_rest,
        dispatch_collected_rest,
        dispatch_support_rest,
        dispatch_discovery_rest,
        dispatch_verification_rest,
        dispatch_private_auth_rest,
        dispatch_profile_rest,
        dispatch_proxy_intro_rest,
        dispatch_recommendation_rest,
        dispatch_matchmaking_rest,
        dispatch_chat_rest,
        dispatch_chat_safety_rest,
        dispatch_call_rest,
        dispatch_media_rest,
    ):
        response = dispatcher(gateway, environ, method, path)
        if response is not None:
            return response

    return 404, {"error": {"code": "not_found", "message": f"No route for {method} {path}"}}


__all__ = ["dispatch_gateway_rest"]
