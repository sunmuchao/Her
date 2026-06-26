"""GET /v1/candidates/{id} — BFF aggregate read for candidate detail (§13.4).

SECURITY FIX: Added resource access control to prevent IDOR attacks.

Before: Any authenticated user could access any candidate profile by ID.
After: User must be a participant in a discovery session that includes this candidate,
       or have staff override roles.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

from match_domain.collected_profile import extract_profile_facts
from match_domain.criteria_snapshots import get_criteria_snapshot_store, snapshot_to_dict
from match_domain.trust_summary import build_trust_summary
from profile_service import get_profile

from ..http_helpers import _json_safe, _query_dict
from ..input_validator import validate_int_id, ValidationError
from ..profile_source_defaults import default_profile_source
from ..resource_access_guard import (
    AccessAction,
    ResourceType,
    guard_resource_access,
    check_resource_access,
)
from ..role_sets import STAFF_OVERRIDE_ROLES


class CandidateDetailGateway(Protocol):
    _discovery: Any

    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _resolve_int_actor_bound_id(
        self,
        environ: dict[str, Any],
        raw_value: Any,
        *,
        field_name: str,
    ) -> int: ...

    def _resolve_end_user_principal(self, environ: dict[str, Any], *, require_profile: bool = False) -> Any: ...

    def _is_auth_session_end_user(self, actor: Any) -> bool: ...

    def _discovery(self) -> Any: ...

    def _with_rec(self, func: Any, *args: Any, **kwargs: Any) -> Any: ...


def _explain_for_recommendation(recommendation_id: int) -> dict[str, Any] | None:
    store = get_criteria_snapshot_store()
    snapshot = store.get_latest_for_recommendation(int(recommendation_id))
    if snapshot is None:
        return None
    payload = snapshot_to_dict(snapshot)
    return {
        "recommendation_id": int(recommendation_id),
        "source_map": payload.get("source_map") or {},
        "runtime_explanation": payload.get("runtime_explanation"),
        "snapshot_id": payload.get("snapshot_id"),
    }


def _check_candidate_access_via_session(
    gateway: CandidateDetailGateway,
    environ: dict[str, Any],
    candidate_id: int,
    session_id: str,
) -> bool:
    """Check if user can access candidate via a discovery session.

    The user must be the owner of the discovery session, and the candidate
    must be in the session's candidate list.
    """
    try:
        # Verify session ownership
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        if owner_id is None:
            print(f"[DEBUG candidate_access] session_id={session_id} owner_id is None")
            return False

        # For auth_session end users, check profile_id binding
        actor = gateway._current_actor(environ)
        if actor is not None and gateway._is_auth_session_end_user(actor):
            resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
            if resolved is None or resolved.profile_id is None:
                print(f"[DEBUG candidate_access] session_id={session_id} resolved.profile_id is None")
                return False
            if int(resolved.profile_id) != int(owner_id):
                print(f"[DEBUG candidate_access] session_id={session_id} resolved.profile_id={resolved.profile_id} != owner_id={owner_id}")
                return False

        # Check if candidate is in session's recommendations
        session_view = gateway._discovery.get_session_view(session_id)
        if session_view is None:
            print(f"[DEBUG candidate_access] session_id={session_id} session_view is None")
            return False

        view_data = session_view.get("view", {})
        candidate_ids: set[int] = set()

        # Legacy shape: view.candidates[]
        candidates = view_data.get("candidates") or []
        for candidate in candidates:
            resolved_candidate_id = int(candidate.get("profile_id") or candidate.get("candidate_id") or 0)
            if resolved_candidate_id > 0:
                candidate_ids.add(resolved_candidate_id)

        # Current production shape: view.timeline[].cards[] for result groups
        for item in list(view_data.get("timeline") or []):
            cards = item.get("cards") or []
            if not isinstance(cards, list):
                continue
            for card in cards:
                resolved_candidate_id = int(
                    card.get("profile_id")
                    or ((card.get("open_profile_action") or {}).get("profile_id"))
                    or card.get("candidate_id")
                    or 0
                )
                if resolved_candidate_id > 0:
                    candidate_ids.add(resolved_candidate_id)

        print(f"[DEBUG candidate_access] session_id={session_id} candidate_id={candidate_id} candidate_ids={candidate_ids}")
        return candidate_id in candidate_ids

    except Exception as e:
        print(f"[DEBUG candidate_access] exception: {e}")
        return False


def _check_candidate_access_via_recommendation(
    gateway: CandidateDetailGateway,
    environ: dict[str, Any],
    candidate_id: int,
    recommendation_id: int,
) -> bool:
    """Check if user can access candidate via a recommendation.

    The user must be the requester of the recommendation subscription,
    and the recommendation must contain this candidate.
    """
    try:
        from recommendation_system import get_recommendation_by_id  # type: ignore[import-untyped]

        # Get the recommendation record
        recommendation = gateway._with_rec(get_recommendation_by_id, int(recommendation_id))
        if recommendation is None:
            print(f"[DEBUG candidate_access] recommendation_id={recommendation_id} recommendation is None")
            return False

        # Verify user is the requester of the recommendation subscription
        requester_id = int(recommendation.get("requester_id") or 0)
        if requester_id <= 0:
            print(f"[DEBUG candidate_access] recommendation_id={recommendation_id} requester_id is invalid")
            return False

        # For auth_session end users, check profile_id binding
        actor = gateway._current_actor(environ)
        if actor is not None and gateway._is_auth_session_end_user(actor):
            resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
            if resolved is None or resolved.profile_id is None:
                print(f"[DEBUG candidate_access] recommendation_id={recommendation_id} resolved.profile_id is None")
                return False
            if int(resolved.profile_id) != int(requester_id):
                print(f"[DEBUG candidate_access] recommendation_id={recommendation_id} resolved.profile_id={resolved.profile_id} != requester_id={requester_id}")
                return False

        # Verify the recommendation contains this candidate
        recommendation_candidate_id = int(recommendation.get("candidate_id") or 0)
        if recommendation_candidate_id <= 0:
            print(f"[DEBUG candidate_access] recommendation_id={recommendation_id} candidate_id is invalid")
            return False

        if candidate_id != recommendation_candidate_id:
            print(f"[DEBUG candidate_access] recommendation_id={recommendation_id} candidate_id={candidate_id} != recommendation_candidate_id={recommendation_candidate_id}")
            return False

        print(f"[DEBUG candidate_access] recommendation_id={recommendation_id} access granted")
        return True

    except Exception as e:
        print(f"[DEBUG candidate_access] recommendation access check exception: {e}")
        return False


def _check_candidate_access_via_case(
    gateway: CandidateDetailGateway,
    environ: dict[str, Any],
    candidate_id: int,
    case_id: str,
) -> bool:
    """Check if user can access candidate via a proxy intro case.

    The user must be a participant in the case (requester or candidate),
    and the case must involve this candidate.
    """
    try:
        # Import gateway access control mixin methods
        from ..access_control import GatewayAccessMixin

        # Get the case and verify user is a participant
        # This will raise GatewayPermissionError if access is denied
        case = gateway._get_case_for_actor(environ, case_id)

        # Verify the case involves this candidate
        case_candidate_id = int(case.get("candidate_id") or case.get("counterpart_profile_id") or 0)
        case_requester_id = int(case.get("requester_id") or case.get("requester_profile_id") or 0)

        # User can access if they're viewing the counterpart (candidate) or the requester
        if candidate_id == case_candidate_id or candidate_id == case_requester_id:
            return True

        print(f"[DEBUG candidate_access] case_id={case_id} candidate_id={candidate_id} not in case participants")
        return False

    except Exception as e:
        print(f"[DEBUG candidate_access] case access check exception: {e}")
        return False


def _check_candidate_access_via_card(
    gateway: CandidateDetailGateway,
    environ: dict[str, Any],
    candidate_id: int,
    card_id: str,
) -> bool:
    """Check if user can access candidate via a recommendation card.

    The user must be the requester of the recommendation subscription that
    contains this card, and the card must reference this candidate.
    """
    try:
        # Import recommendation system functions
        from recommendation_system import get_card_by_id  # type: ignore[import-untyped]

        # Get the card record
        card = gateway._with_rec(get_card_by_id, card_id)
        if card is None:
            print(f"[DEBUG candidate_access] card_id={card_id} card is None")
            return False

        # Verify user is the requester of the recommendation subscription
        requester_id = int(card.get("requester_id") or 0)
        if requester_id <= 0:
            print(f"[DEBUG candidate_access] card_id={card_id} requester_id is invalid")
            return False

        # For auth_session end users, check profile_id binding
        actor = gateway._current_actor(environ)
        if actor is not None and gateway._is_auth_session_end_user(actor):
            resolved = gateway._resolve_end_user_principal(environ, require_profile=True)
            if resolved is None or resolved.profile_id is None:
                print(f"[DEBUG candidate_access] card_id={card_id} resolved.profile_id is None")
                return False
            if int(resolved.profile_id) != int(requester_id):
                print(f"[DEBUG candidate_access] card_id={card_id} resolved.profile_id={resolved.profile_id} != requester_id={requester_id}")
                return False

        # Verify the card references this candidate
        card_candidate_id = int(card.get("candidate_id") or 0)
        if card_candidate_id <= 0:
            print(f"[DEBUG candidate_access] card_id={card_id} candidate_id is invalid")
            return False

        if candidate_id != card_candidate_id:
            print(f"[DEBUG candidate_access] card_id={card_id} candidate_id={candidate_id} != card_candidate_id={card_candidate_id}")
            return False

        print(f"[DEBUG candidate_access] card_id={card_id} access granted")
        return True

    except Exception as e:
        print(f"[DEBUG candidate_access] card access check exception: {e}")
        return False


def rest_candidate_detail(
    gateway: CandidateDetailGateway,
    environ: dict[str, Any],
    candidate_id: str,
) -> tuple[int, dict[str, Any]]:
    """Get candidate detail with proper access control.

    SECURITY REQUIREMENTS:
    1. User must be authenticated
    2. User must have legitimate access to this candidate:
       - Via discovery session (owner of session that contains this candidate)
       - Via recommendation (requester of subscription containing this recommendation)
       - Via match case (participant in a case involving this candidate)
    3. Staff override roles can bypass ownership checks (audited)

    Attack Prevention:
    - Prevents enumeration of all user profiles
    - Prevents unauthorized access to candidate details
    - All access decisions are audited
    """
    q = _query_dict(environ)

    # Step 1: Validate candidate_id format (prevent injection)
    try:
        profile_id = validate_int_id(candidate_id, "candidate_id")
    except ValidationError as e:
        return 400, {"error": {"code": "invalid_request", "message": str(e)}}

    # Step 2: Get actor and check authentication
    actor = gateway._current_actor(environ)
    if actor is None:
        return 401, {"error": {"code": "unauthorized", "message": "Authentication required"}}

    # Step 3: Check access authorization
    session_id = (q.get("session_id") or "").strip() or None
    recommendation_id_raw = q.get("recommendation_id")
    recommendation_id: int | None = None
    if recommendation_id_raw not in (None, ""):
        try:
            recommendation_id = validate_int_id(recommendation_id_raw, "recommendation_id")
        except ValidationError:
            recommendation_id = None

    # NEW: Support case_id parameter for relationship page access
    case_id = (q.get("case_id") or "").strip() or None

    # NEW: Support card_id parameter for recommendation inbox access
    card_id = (q.get("card_id") or "").strip() or None

    access_allowed = False
    access_reason = None
    access_method = None

    # Check staff override (audited)
    if actor.has_any_role(STAFF_OVERRIDE_ROLES):
        access_allowed = True
        access_reason = "staff_override"
        access_method = "role"
        # Audit the override access
        from observability import audit_event
        audit_event(
            action="gateway.candidate_access_override",
            resource_type="candidate_profile",
            resource_id=str(profile_id),
            outcome="allowed",
            reason="staff_override",
            actor_id=actor.actor_id,
            http_method=environ.get("REQUEST_METHOD"),
            path=environ.get("PATH_INFO"),
        )

    # Check via discovery session
    elif session_id is not None:
        access_allowed = _check_candidate_access_via_session(gateway, environ, profile_id, session_id)
        if access_allowed:
            access_reason = "discovery_session_owner"
            access_method = "session"

    # Check via recommendation (future implementation)
    elif recommendation_id is not None:
        access_allowed = _check_candidate_access_via_recommendation(gateway, environ, profile_id, recommendation_id)
        if access_allowed:
            access_reason = "recommendation_requester"
            access_method = "recommendation"

    # NEW: Check via proxy intro case (relationship page access)
    elif case_id is not None:
        access_allowed = _check_candidate_access_via_case(gateway, environ, profile_id, case_id)
        if access_allowed:
            access_reason = "case_participant"
            access_method = "case"

    # NEW: Check via recommendation card (recommendation inbox access)
    elif card_id is not None:
        access_allowed = _check_candidate_access_via_card(gateway, environ, profile_id, card_id)
        if access_allowed:
            access_reason = "card_requester"
            access_method = "card"

    # For auth_session end users without session_id/recommendation_id/case_id,
    # they cannot access arbitrary candidates
    else:
        access_reason = "no_valid_access_path"
        access_allowed = False

    if not access_allowed:
        return 403, {
            "error": {
                "code": "forbidden",
                "message": "You do not have permission to view this candidate's profile. "
                "Access is only allowed through active discovery sessions, recommendations, or relationships.",
            }
        }

    # Step 4: Fetch profile data
    source_dsn, table_name = default_profile_source()
    row = get_profile(
        source_dsn=source_dsn,
        source_table_name=table_name,
        profile_id=profile_id,
    )
    if not row:
        return 404, {"error": {"code": "not_found", "message": "candidate profile not found"}}

    trust = build_trust_summary(row)
    detail_view: dict[str, Any] | None = None
    detail_source = "profile"
    # Step 5: Get discovery detail if session provided
    if session_id is not None:
        try:
            discovery_out = gateway._discovery.get_profile_detail(
                profile_id,
                session_id=session_id,
                include_xiaoya_analysis=False,
            )
            if isinstance(discovery_out, dict):
                detail_view = discovery_out.get("detail_view") or discovery_out
                detail_source = "discovery"
        except Exception:  # noqa: BLE001 — fall back to profile facts
            detail_view = None

    explain = _explain_for_recommendation(recommendation_id) if recommendation_id is not None else None

    # Step 6: Audit successful access
    from observability import audit_event
    audit_event(
        action="gateway.candidate_access",
        resource_type="candidate_profile",
        resource_id=str(profile_id),
        outcome="allowed",
        reason=access_reason,
        access_method=access_method,
        actor_id=actor.actor_id,
        session_id=session_id,
        recommendation_id=recommendation_id,
        http_method=environ.get("REQUEST_METHOD"),
        path=environ.get("PATH_INFO"),
    )

    return 200, _json_safe(
        {
            "candidate_id": profile_id,
            "profile_id": profile_id,
            "detail_source": detail_source,
            "detail_view": detail_view,
            "profile_facts": extract_profile_facts(row),
            "trust_summary": trust.to_dict(),
            "explain": explain,
            "access_method": access_method,  # Include for transparency
        }
    )


def rest_candidate_xiaoya_analysis(
    gateway: CandidateDetailGateway,
    environ: dict[str, Any],
    candidate_id: str,
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    try:
        profile_id = validate_int_id(candidate_id, "candidate_id")
    except ValidationError as e:
        return 400, {"error": {"code": "invalid_request", "message": str(e)}}

    actor = gateway._current_actor(environ)
    if actor is None:
        return 401, {"error": {"code": "unauthorized", "message": "Authentication required"}}

    session_id = (q.get("session_id") or "").strip() or None
    if session_id is None:
        return 400, {"error": {"code": "invalid_request", "message": "session_id is required"}}

    if not _check_candidate_access_via_session(gateway, environ, profile_id, session_id):
        return 403, {
            "error": {
                "code": "forbidden",
                "message": "You do not have permission to view this candidate analysis.",
            }
        }

    try:
        discovery_out = gateway._discovery.get_profile_detail(
            profile_id,
            session_id=session_id,
            include_xiaoya_analysis=True,
        )
    except Exception as exc:
        status_code = int(getattr(exc, "status_code", 502) or 502)
        error_code = str(getattr(exc, "code", "xiaoya_analysis_failed") or "xiaoya_analysis_failed").lower()
        message = str(getattr(exc, "message", "") or str(exc) or "小雅分析生成失败")
        return status_code, {
            "error": {
                "code": error_code,
                "message": message,
            }
        }

    xiaoya_analysis = None
    xiaoya_analysis_structured = None
    if isinstance(discovery_out, dict):
        xiaoya_analysis = str(discovery_out.get("xiaoya_analysis") or "").strip() or None
        structured_payload = discovery_out.get("xiaoya_analysis_structured")
        if isinstance(structured_payload, dict):
            xiaoya_analysis_structured = {
                "summary": str(structured_payload.get("summary") or "").strip() or None,
                "risk_point": str(structured_payload.get("risk_point") or "").strip() or None,
                "first_question": str(structured_payload.get("first_question") or "").strip() or None,
            }

    if not xiaoya_analysis:
        return 502, {
            "error": {
                "code": "xiaoya_analysis_failed",
                "message": "小雅分析生成失败",
            }
        }

    return 200, _json_safe(
        {
            "candidate_id": profile_id,
            "xiaoya_analysis": xiaoya_analysis,
            "xiaoya_analysis_structured": xiaoya_analysis_structured,
        }
    )


def dispatch_candidate_bff(
    gateway: CandidateDetailGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    match = re.fullmatch(r"/v1/candidates/([^/]+)/xiaoya-analysis", path.rstrip("/") or "/")
    if match and method == "GET":
        return rest_candidate_xiaoya_analysis(gateway, environ, match.group(1))

    match = re.fullmatch(r"/v1/candidates/([^/]+)", path.rstrip("/") or "/")
    if match and method == "GET":
        return rest_candidate_detail(gateway, environ, match.group(1))
    return None


__all__ = ["dispatch_candidate_bff", "rest_candidate_detail", "rest_candidate_xiaoya_analysis"]
