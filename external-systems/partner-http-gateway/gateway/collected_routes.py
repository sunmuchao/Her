"""Profile facts and collected-statement read APIs (§13.1.2).

SECURITY FIX: Strict authentication binding for profile access.

Before: Non-auth_session users (like static tokens) could access arbitrary profiles.
After: /v1/profile/me ONLY returns current user's profile; other profiles require
       explicit staff override roles or must be accessed via legitimate channels
       (discovery session, recommendation, match case).

Key Changes:
1. /v1/profile/me - Strict binding to current user, no query parameter override
2. /v1/persona/collected - Requires ownership verification
"""

from __future__ import annotations

import os
import re
from typing import Any, Protocol

from match_domain.collected_profile import extract_collected_statements, extract_profile_facts
from match_domain.collected_metadata import build_collected_items
from match_domain.persona_loader import load_collected_bundle
from profile_service import get_profile, list_profile_photos

from .http_helpers import _json_safe, _query_dict
from .input_validator import validate_int_id, ValidationError
from .recommendation_access import resolve_optional_profile_id
from .role_sets import STAFF_OVERRIDE_ROLES


class CollectedGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _is_auth_session_end_user(self, actor: Any) -> bool: ...

    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False) -> Any: ...

    def _resolve_int_actor_bound_id(
        self,
        environ: dict[str, Any],
        raw_value: Any,
        *,
        field_name: str,
    ) -> int: ...

    def _get_recommendation_for_actor(
        self,
        environ: dict[str, Any],
        recommendation_id: int,
    ) -> dict[str, Any]: ...

    def _discovery(self) -> Any: ...


def _default_profile_source() -> str:
    for name in (
        "PARTNER_SEARCH_MYSQL_SOURCE",
        "PERSONA_MEMORY_MYSQL_SOURCE",
        "HER_DISCOVERY_PROFILE_SOURCE",
    ):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def _parse_profile_source(source: str) -> tuple[str, str | None]:
    from profile_service import resolve_profile_source

    normalized_source, table_name = resolve_profile_source(source, None)
    return normalized_source or source, table_name


def rest_profile_me(gateway: CollectedGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Get CURRENT USER's profile facts.

    SECURITY REQUIREMENT:
    - This endpoint is named "/v1/profile/me" which semantically means "MY profile"
    - It MUST ONLY return the profile of the authenticated user
    - Query parameter profile_id override is STRICTLY FORBIDDEN for auth_session users
    - Staff override roles can access other profiles (audited)

    Attack Prevention:
    - Prevents static token abuse to access arbitrary profiles
    - Prevents query parameter injection for IDOR
    """
    q = _query_dict(environ)
    actor = gateway._current_actor(environ)

    # Step 1: Authentication required
    if actor is None:
        return 401, {
            "error": {
                "code": "unauthorized",
                "message": "Authentication required. This endpoint only returns your own profile.",
            }
        }

    profile_id: int | None = None
    access_method = None

    # Step 2: For auth_session end users, STRICTLY bind to their profile_id
    if gateway._is_auth_session_end_user(actor):
        resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
        if resolved is None or resolved.profile_id is None:
            return 400, {
                "error": {
                    "code": "profile_not_found",
                    "message": "Your account does not have a profile yet. Please complete onboarding first.",
                }
            }
        profile_id = int(resolved.profile_id)
        access_method = "auth_session_binding"

        # SECURITY: Block query parameter override for auth_session users
        query_profile_id = q.get("profile_id")
        if query_profile_id is not None and str(query_profile_id).strip():
            # Log potential attack
            from observability import audit_event
            audit_event(
                action="gateway.profile_me_idor_attempt",
                resource_type="profile",
                resource_id=str(query_profile_id),
                outcome="blocked",
                reason="auth_session_user_attempted_query_param_override",
                actor_id=actor.actor_id,
                bound_profile_id=profile_id,
                requested_profile_id=query_profile_id,
                http_method=environ.get("REQUEST_METHOD"),
                path=environ.get("PATH_INFO"),
            )
            # Return error explaining the semantic
            return 400, {
                "error": {
                    "code": "invalid_request",
                    "message": "This endpoint (/v1/profile/me) returns YOUR profile only. "
                    "Query parameter profile_id is not accepted for authenticated sessions. "
                    "To access other profiles, use appropriate channels (discovery, recommendation) "
                    "or request staff access.",
                }
            }

    # Step 3: For non-auth_session users (staff tokens, etc.), allow query param with role check
    else:
        query_profile_id = q.get("profile_id")
        if query_profile_id is not None and str(query_profile_id).strip():
            # Validate format
            try:
                requested_id = validate_int_id(query_profile_id, "profile_id")
            except ValidationError as e:
                return 400, {"error": {"code": "invalid_request", "message": str(e)}}

            # Check staff override role
            if actor.has_any_role(STAFF_OVERRIDE_ROLES):
                profile_id = requested_id
                access_method = "staff_override"
                # Audit staff access
                from observability import audit_event
                audit_event(
                    action="gateway.profile_me_staff_override",
                    resource_type="profile",
                    resource_id=str(profile_id),
                    outcome="allowed",
                    reason="staff_override_access",
                    actor_id=actor.actor_id,
                    actor_roles=list(actor.roles),
                    http_method=environ.get("REQUEST_METHOD"),
                    path=environ.get("PATH_INFO"),
                )
            else:
                # Non-staff static token cannot access arbitrary profiles via /v1/profile/me
                return 403, {
                    "error": {
                        "code": "forbidden",
                        "message": "You are not authorized to access arbitrary profiles. "
                        "This endpoint returns your bound profile only.",
                    }
                }
        else:
            # No query param, try to get bound profile_id
            try:
                resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
                if resolved is not None and resolved.profile_id is not None:
                    profile_id = int(resolved.profile_id)
                    access_method = "resolved_binding"
            except Exception:
                profile_id = None

    if profile_id is None:
        return 400, {
            "error": {
                "code": "invalid_request",
                "message": "Could not determine your profile_id. Please complete profile setup.",
            }
        }

    # Step 4: Fetch profile data
    source = (q.get("source") or _default_profile_source()).strip()
    if not source:
        return 503, {"error": {"code": "profile_source_not_configured", "message": "profile source is not configured"}}
    normalized_source, table_name = _parse_profile_source(source)

    try:
        row = get_profile(
            source_dsn=normalized_source,
            source_table_name=table_name or "profiles",
            profile_id=int(profile_id),
        )
        if not row:
            return 404, {"error": {"code": "not_found", "message": "profile not found"}}

        # 查询照片数据
        photos = []
        try:
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"[rest_profile_me] 开始查询照片: source_dsn={normalized_source}, table_name={table_name}, profile_id={profile_id}")
            photos = list_profile_photos(
                source_dsn=normalized_source,
                source_table_name=table_name or "profiles",
                profile_id=int(profile_id),
                photos_table_name="profile_photos",
            )
            logger.info(f"[rest_profile_me] 照片查询完成: photos_count={len(photos)}, photos={[p.get('photo_url') for p in photos]}")
        except Exception as photo_error:
            # 照片查询失败不影响主流程，记录日志
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to query photos for profile_id={profile_id}: {photo_error}"
            )

        return 200, {
            "profile_id": int(profile_id),
            "profile_facts": _json_safe(extract_profile_facts(row)),
            "photos": [photo.get("photo_source") for photo in photos if photo.get("photo_source")],
            "access_method": access_method,  # Include for transparency
        }
    except TimeoutError as e:
        return 503, {"error": {"code": "db_timeout", "message": f"数据库连接超时: {str(e)}"}}
    except Exception as e:
        return 500, {"error": {"code": "internal_error", "message": str(e)}}


def rest_persona_collected(gateway: CollectedGateway, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Get collected statements for a profile.

    SECURITY REQUIREMENT:
    - Auth_session users: Only access their own profile
    - Staff override: Can access any profile (audited)
    """
    q = _query_dict(environ)

    # Get actor
    actor = gateway._current_actor(environ)
    if actor is None:
        return 401, {
            "error": {
                "code": "unauthorized",
                "message": "Authentication required.",
            }
        }

    # Resolve profile_id with ownership check
    profile_id = None
    access_method = None

    # For auth_session end users, bind to their profile
    if gateway._is_auth_session_end_user(actor):
        resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
        if resolved is not None and resolved.profile_id is not None:
            profile_id = int(resolved.profile_id)
            access_method = "auth_session_binding"

            # SECURITY: Block query parameter override
            query_profile_id = q.get("profile_id")
            if query_profile_id is not None and str(query_profile_id).strip():
                try:
                    requested = validate_int_id(query_profile_id, "profile_id")
                except ValidationError:
                    requested = None
                if requested is not None and requested != profile_id:
                    # Log IDOR attempt
                    from observability import audit_event
                    audit_event(
                        action="gateway.persona_idor_attempt",
                        resource_type="persona",
                        resource_id=str(requested),
                        outcome="blocked",
                        reason="auth_session_user_attempted_query_param_override",
                        actor_id=actor.actor_id,
                        http_method=environ.get("REQUEST_METHOD"),
                        path=environ.get("PATH_INFO"),
                    )
                    return 403, {
                        "error": {
                            "code": "forbidden",
                            "message": "You can only access your own persona data.",
                        }
                    }
    else:
        # Non-auth_session users: require staff role for arbitrary profile access
        profile_id = resolve_optional_profile_id(
            gateway,
            environ,
            q.get("profile_id"),
            raw_requester_id=q.get("requester_id"),
            raw_user_key=q.get("user_key"),
            treat_empty_as_missing=True,
        )
        if profile_id is not None:
            if actor.has_any_role(STAFF_OVERRIDE_ROLES):
                access_method = "staff_override"
            else:
                return 403, {
                    "error": {
                        "code": "forbidden",
                        "message": "Non-auth_session users need staff override role to access persona data.",
                    }
                }

    if profile_id is None:
        return 400, {"error": {"code": "invalid_request", "message": "profile_id is required"}}

    source = (q.get("source") or _default_profile_source()).strip()
    if not source:
        return 503, {"error": {"code": "persona_source_not_configured", "message": "persona source is not configured"}}

    try:
        bundle = load_collected_bundle(source=source, user_key=str(profile_id))
        persona = bundle.get("persona") or {}
        collected_items = bundle.get("collected_items") or build_collected_items(
            persona,
            bundle.get("observations") or [],
        )
        flat_statements = extract_collected_statements(persona)
        return 200, {
            "profile_id": int(profile_id),
            "user_key": str(profile_id),
            "collected_statements": _json_safe(flat_statements),
            "collected_items": _json_safe(collected_items),
            "access_method": access_method,
        }
    except TimeoutError as e:
        return 503, {"error": {"code": "db_timeout", "message": f"数据库连接超时: {str(e)}"}}
    except Exception as e:
        return 500, {"error": {"code": "internal_error", "message": str(e)}}


def rest_profile_update_photos_with_face_check(
    gateway: CollectedGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """Update profile photos with face check against video anchor.

    SECURITY REQUIREMENT:
    - Auth_session users: Only update their own profile
    - Staff override: Can update any profile (audited)

    Flow:
    1. User uploads new photos
    2. System checks if user has verified_face_anchor (from live video verification)
    3. If anchor exists, check face similarity: new photo face vs video face
    4. If similarity >= threshold (0.363), save photos
    5. If verification_status was "rejected", auto-approve verification
    """
    import logging
    logger = logging.getLogger(__name__)

    from .http_helpers import _parse_json_body, _read_body
    from profile_service import update_profile_photos_with_face_check  # type: ignore[import-untyped]

    # Parse request body
    body = _parse_json_body(_read_body(environ))
    logger.info(f"[rest_profile_update_photos_with_face_check] 请求体: {body}")
    logger.info(f"[rest_profile_update_photos_with_face_check] photos参数: {body.get('photos')}, 类型: {type(body.get('photos'))}, 长度: {len(body.get('photos', []))}")

    # Get actor
    actor = gateway._current_actor(environ)
    logger.info(f"[rest_profile_update_photos_with_face_check] actor: {actor.actor_id if actor else None}, is_auth_session: {gateway._is_auth_session_end_user(actor) if actor else False}")

    if actor is None:
        logger.warning("[rest_profile_update_photos_with_face_check] 返回401: actor为空")
        return 401, {
            "error": {
                "code": "unauthorized",
                "message": "Authentication required.",
            }
        }

    # Resolve profile_id with ownership check
    profile_id = None
    access_method = None

    # For auth_session end users, bind to their profile
    if gateway._is_auth_session_end_user(actor):
        resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
        logger.info(f"[rest_profile_update_photos_with_face_check] resolved对象: {resolved}, profile_id: {resolved.profile_id if resolved else None}")
        if resolved is not None and resolved.profile_id is not None:
            profile_id = int(resolved.profile_id)
            access_method = "auth_session_binding"
            logger.info(f"[rest_profile_update_photos_with_face_check] profile_id解析成功: {profile_id}")

            # SECURITY: Block body parameter override
            body_profile_id = body.get("profile_id")
            if body_profile_id is not None:
                try:
                    requested = int(body_profile_id)
                except (ValueError, TypeError):
                    requested = None
                if requested is not None and requested != profile_id:
                    # Log IDOR attempt
                    from observability import audit_event
                    audit_event(
                        action="gateway.photos_update_idor_attempt",
                        resource_type="profile",
                        resource_id=str(requested),
                        outcome="blocked",
                        reason="auth_session_user_attempted_body_param_override",
                        actor_id=actor.actor_id,
                        http_method=environ.get("REQUEST_METHOD"),
                        path=environ.get("PATH_INFO"),
                    )
                    return 403, {
                        "error": {
                            "code": "forbidden",
                            "message": "You can only update your own profile photos.",
                        }
                    }
    else:
        # Non-auth_session users: require staff role for arbitrary profile access
        body_profile_id = body.get("profile_id")
        if body_profile_id is not None:
            try:
                profile_id = int(body_profile_id)
            except (ValueError, TypeError):
                return 400, {"error": {"code": "invalid_request", "message": "Invalid profile_id format"}}
            if actor.has_any_role(STAFF_OVERRIDE_ROLES):
                access_method = "staff_override"
                # Audit staff access
                from observability import audit_event
                audit_event(
                    action="gateway.photos_update_staff_override",
                    resource_type="profile",
                    resource_id=str(profile_id),
                    outcome="allowed",
                    reason="staff_override_access",
                    actor_id=actor.actor_id,
                    actor_roles=list(actor.roles),
                    http_method=environ.get("REQUEST_METHOD"),
                    path=environ.get("PATH_INFO"),
                )
            else:
                return 403, {
                    "error": {
                        "code": "forbidden",
                        "message": "Non-auth_session users need staff override role to update profile photos.",
                    }
                }

    if profile_id is None:
        logger.warning("[rest_profile_update_photos_with_face_check] 返回400: profile_id为空")
        return 400, {"error": {"code": "invalid_request", "message": "profile_id is required"}}

    logger.info(f"[rest_profile_update_photos_with_face_check] 最终profile_id: {profile_id}")

    # Validate photos parameter
    photos = body.get("photos")
    if not photos or not isinstance(photos, list):
        logger.warning(f"[rest_profile_update_photos_with_face_check] 返回400: photos参数无效, photos={photos}, type={type(photos)}")
        return 400, {"error": {"code": "invalid_request", "message": "photos must be a non-empty array"}}
    if len(photos) > 6:
        logger.warning(f"[rest_profile_update_photos_with_face_check] 返回400: photos数量超限, len={len(photos)}")
        return 400, {"error": {"code": "invalid_request", "message": "Maximum 6 photos allowed"}}

    logger.info(f"[rest_profile_update_photos_with_face_check] photos验证通过: {photos}")

    # Get source
    q = _query_dict(environ)
    source = (q.get("source") or body.get("source") or _default_profile_source()).strip()
    if not source:
        return 503, {"error": {"code": "profile_source_not_configured", "message": "profile source is not configured"}}

    normalized_source, table_name = _parse_profile_source(source)

    try:
        # Call backend function
        result = update_profile_photos_with_face_check(
            source_dsn=normalized_source,
            profile_id=profile_id,
            new_photos=photos,
            source_table_name=table_name or "profiles",
            verification_status=body.get("verification_status"),
        )

        # Add access_method for transparency
        result["access_method"] = access_method

        # Determine HTTP status
        if result.get("success"):
            return 200, _json_safe(result)
        else:
            return 400, _json_safe(result)

    except TimeoutError as e:
        return 503, {"error": {"code": "db_timeout", "message": f"数据库连接超时: {str(e)}"}}
    except Exception as e:
        return 500, {"error": {"code": "internal_error", "message": str(e)}}


def dispatch_collected_rest(
    gateway: CollectedGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v1/profile/me" and method == "GET":
        return rest_profile_me(gateway, environ)
    if path == "/v1/persona/collected" and method == "GET":
        return rest_persona_collected(gateway, environ)
    if path == "/v1/profile/photos/update-with-face-check" and method == "POST":
        return rest_profile_update_photos_with_face_check(gateway, environ)
    return None


__all__ = [
    "dispatch_collected_rest",
    "rest_persona_collected",
    "rest_profile_me",
    "rest_profile_update_photos_with_face_check",
]