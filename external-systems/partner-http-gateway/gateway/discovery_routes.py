"""Discovery-specific HTTP handlers for the gateway.

SECURITY FIX: Added path parameter validation using input_validator.

Changes:
1. All path parameters {session_id} now validated before processing
2. Validation prevents injection attacks on session IDs
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Protocol, Sequence

from discovery_system import DiscoveryServiceError  # type: ignore[import-untyped]
from match_domain import (  # noqa: E402
    PhotoPreferenceIntent,
    build_photo_recommendation_explanation,
    detect_photo_preference_intent,
    execute_photo_preference_search,
    get_trace_id,
)
from match_domain.principal import coalesce_profile_id_param
from profile_service import list_profiles

from .http_helpers import (  # noqa: E402
    _json_safe,
    _parse_json_body,
    _parse_optional_int,
    _parse_optional_now,
    _query_dict,
    _read_body,
)
from .input_validator import validate_id, ValidationError
from .profile_source_defaults import default_profile_source


class DiscoveryGateway(Protocol):
    _discovery: Any

    def _resolve_int_actor_bound_id(
        self,
        environ: dict[str, Any],
        raw_value: Any,
        *,
        field_name: str,
    ) -> int: ...

    def _assert_actor_can_access_owner(
        self,
        environ: dict[str, Any],
        owner_id: int,
        *,
        field_name: str,
    ) -> None: ...


def _photo_search_error(message: str, *, code: str = "bad_request") -> tuple[int, dict[str, Any]]:
    return 400, {
        "error": {"code": code, "message": message},
        "trace_id": get_trace_id(),
    }


def _pick_first_non_empty(row: dict[str, Any], field_names: tuple[str, ...]) -> Any:
    for field_name in field_names:
        value = row.get(field_name)
        if isinstance(value, str):
            if value.strip():
                return value.strip()
            continue
        if value is not None:
            return value
    return None


def _pick_profile_image(row: dict[str, Any]) -> str | None:
    direct = _pick_first_non_empty(
        row,
        (
            "avatar_url",
            "photo_url",
            "cover_url",
            "image_url",
            "head_img",
            "headimgurl",
        ),
    )
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    return None


def _build_photo_search_preview(
    *,
    ranked_result: dict[str, Any],
    profile_row: dict[str, Any] | None,
    intent: PhotoPreferenceIntent,
) -> dict[str, Any]:
    profile = dict(profile_row or {})
    explanation = build_photo_recommendation_explanation(
        intent=intent,
        candidate_row={
            **profile,
            **ranked_result,
        },
    )
    reasoning = dict(explanation.get("appearance_reasoning") or {})
    highlights = [
        str(item).strip()
        for item in list(reasoning.get("highlights") or [])
        if str(item).strip()
    ]
    verified_level = str(
        profile.get("verified_level")
        or profile.get("profile_verified_level")
        or ""
    ).strip()
    return {
        "id": str(ranked_result.get("profile_id") or profile.get("id") or ""),
        "name": str(
            _pick_first_non_empty(profile, ("display_name", "name", "nickname")) or "候选人"
        ),
        "age": _pick_first_non_empty(profile, ("age", "self_age")),
        "city": _pick_first_non_empty(profile, ("city", "self_city", "current_city")),
        "occupation": _pick_first_non_empty(profile, ("job", "occupation", "self_job")),
        "education": _pick_first_non_empty(profile, ("education", "self_education")),
        "verified": bool(verified_level and verified_level not in {"none", "unknown"}),
        "matchScore": ranked_result.get("final_score") or ranked_result.get("base_score"),
        "image": _pick_profile_image(profile),
        "matchReason": str(reasoning.get("summary") or "").strip() or None,
        "matchHighlights": highlights[:4],
        "appearanceSummary": ranked_result.get("appearance_summary"),
        "photoBonus": ranked_result.get("photo_bonus"),
        "baseScore": ranked_result.get("base_score"),
    }


def _normalize_photo_search_hard_filters(body: Mapping[str, Any]) -> dict[str, Any]:
    raw = body.get("hard_filters")
    if not isinstance(raw, Mapping):
        return {}
    normalized: dict[str, Any] = {}
    age_min = _parse_optional_int(raw.get("age_min"))
    age_max = _parse_optional_int(raw.get("age_max"))
    if age_min is not None and age_min > 0:
        normalized["age_min"] = age_min
    if age_max is not None and age_max > 0:
        normalized["age_max"] = age_max
    raw_cities = raw.get("cities") or raw.get("city")
    cities: list[str] = []
    if isinstance(raw_cities, str):
        cities = [item.strip() for item in raw_cities.split(",") if item.strip()]
    elif isinstance(raw_cities, Sequence):
        cities = [str(item).strip() for item in raw_cities if str(item).strip()]
    if cities:
        normalized["cities"] = cities
    if bool(raw.get("verified_only")):
        normalized["verified_only"] = True
    return normalized


def _profile_matches_photo_search_hard_filters(
    *,
    profile_row: Mapping[str, Any] | None,
    hard_filters: Mapping[str, Any] | None,
) -> bool:
    profile = dict(profile_row or {})
    filters = dict(hard_filters or {})
    if not filters:
        return True
    if not profile:
        return False
    age_value = _pick_first_non_empty(profile, ("age", "self_age"))
    if filters.get("age_min") is not None:
        try:
            if int(age_value) < int(filters["age_min"]):
                return False
        except (TypeError, ValueError):
            return False
    if filters.get("age_max") is not None:
        try:
            if int(age_value) > int(filters["age_max"]):
                return False
        except (TypeError, ValueError):
            return False
    cities = {
        str(item).strip().lower()
        for item in list(filters.get("cities") or [])
        if str(item).strip()
    }
    if cities:
        city_value = str(_pick_first_non_empty(profile, ("city", "self_city", "current_city")) or "").strip().lower()
        if not city_value or city_value not in cities:
            return False
    if bool(filters.get("verified_only")):
        verified_level = str(
            profile.get("verified_level")
            or profile.get("profile_verified_level")
            or ""
        ).strip().lower()
        if verified_level in {"", "none", "unknown"}:
            return False
    return True


def _build_discovery_photo_search_card(preview: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(preview or {})
    highlights = [
        str(item).strip()
        for item in list(payload.get("matchHighlights") or [])
        if str(item).strip()
    ]
    return {
        "profile_id": int(payload.get("id") or 0),
        "title": str(payload.get("name") or "候选人"),
        "subtitle": str(payload.get("city") or payload.get("occupation") or "").strip() or None,
        "cover_image_url": str(payload.get("image") or "").strip() or None,
        "match_score": payload.get("matchScore"),
        "reason_summary": str(payload.get("matchReason") or "").strip() or None,
        "match_highlights": highlights[:4],
    }


def _append_photo_search_to_discovery_session(
    *,
    discovery_service: Any,
    session_id: str,
    mode: str,
    query_text: str,
    image_source: str,
    result_previews: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    from datetime import datetime
    from discovery_system.view_models import assistant_message, result_group, user_message

    session = discovery_service._require_session(session_id)
    now = datetime.now()
    summary_text = (
        f"我按“{query_text}”帮你找了一轮。"
        if mode == "celebrity"
        else (
            "我按这张脸帮你找了一轮。"
            if mode == "face"
            else (
                "我先综合这张图里的脸和整体感觉帮你找了一轮。"
                if mode == "hybrid"
                else "我按这张图的整体感觉帮你找了一轮。"
            )
        )
    )
    timeline = list(session.view.get("timeline") or [])
    user_text = (
        f"像 {query_text}"
        if mode == "celebrity"
        else query_text or (
            "找像这张脸"
            if mode == "face"
            else "帮我看看这张图适合找什么人"
            if mode == "hybrid"
            else "找这种感觉"
        )
    )
    user_metadata = None
    if image_source:
        user_metadata = {
            "media_type": "image",
            "media_url": image_source,
        }
    timeline.append(
        user_message(
            discovery_service.storage.next_item_id("msg-u"),
            user_text,
            created_at=now,
            metadata=user_metadata,
        )
    )
    timeline.append(
        assistant_message(
            discovery_service.storage.next_item_id("msg-a"),
            summary_text,
            created_at=now,
        )
    )
    cards = [
        _build_discovery_photo_search_card(item)
        for item in list(result_previews or [])
        if int(item.get("id") or 0) > 0
    ]
    if cards:
        title = (
            f"像 {query_text}"
            if mode == "celebrity"
            else ("像这张脸" if mode == "face" else "自动理解这张图" if mode == "hybrid" else "这种感觉")
        )
        timeline.append(
            result_group(
                discovery_service.storage.next_item_id("result-group"),
                title,
                cards,
            )
        )
    session.view["timeline"] = timeline
    session.updated_at = now
    discovery_service.storage.save_session(session)
    return {
        "success": True,
        "session_id": session_id,
        "timeline_count": len(timeline),
        "appended_result_count": len(cards),
    }


def _load_profile_rows_by_ids(
    *,
    source_dsn: str,
    source_table_name: str,
    profile_ids: list[int],
) -> dict[int, dict[str, Any]]:
    normalized_ids = [int(profile_id) for profile_id in profile_ids if int(profile_id) > 0]
    if not normalized_ids:
        return {}
    placeholders = ", ".join("?" for _ in normalized_ids)
    rows = list_profiles(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        where_clause=f"`id` IN ({placeholders})",
        params=tuple(normalized_ids),
    )
    return {
        int(row.get("id")): dict(row)
        for row in rows
        if int(row.get("id") or 0) > 0
    }


def rest_discovery_photo_search(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    profile_id = gateway._resolve_int_actor_bound_id(
        environ,
        coalesce_profile_id_param(body.get("profile_id"), body.get("requester_id")),
        field_name="profile_id",
    )
    mode = str(body.get("mode") or "").strip().lower()
    image_source = str(body.get("image_source") or "").strip()
    query_text = str(body.get("query_text") or "").strip()
    celebrity_name = str(body.get("celebrity_name") or "").strip()
    session_id = str(body.get("session_id") or "").strip()
    if mode not in {"face", "style", "celebrity", "auto", ""}:
        return _photo_search_error("mode must be one of: auto, face, style, celebrity")
    if mode in {"face", "style"} and not image_source:
        return _photo_search_error("image_source is required for face/style photo search")
    if mode == "celebrity" and not (celebrity_name or query_text):
        return _photo_search_error("celebrity_name or query_text is required for celebrity search")
    if mode in {"auto", ""} and not (image_source or query_text or celebrity_name):
        return _photo_search_error("image_source or query_text is required for auto photo search")
    try:
        source_dsn, source_table_name = default_profile_source()
    except ValueError as exc:
        return _photo_search_error(str(exc), code="profile_source_missing")

    raw_filters = body.get("attribute_filters")
    attribute_filters = raw_filters if isinstance(raw_filters, dict) else {}
    hard_filters = _normalize_photo_search_hard_filters(body)
    if mode == "face":
        intent = PhotoPreferenceIntent(
            intent_type="face_similarity_search",
            mode="face",
            query_text=query_text or "像这张脸",
            attribute_filters=attribute_filters,
            hard_filters=hard_filters,
            raw_text=query_text or "像这张脸",
        )
    elif mode == "celebrity":
        normalized_name = celebrity_name or query_text
        intent = PhotoPreferenceIntent(
            intent_type="celebrity_face_search",
            mode="celebrity",
            query_text=normalized_name,
            celebrity_name=normalized_name,
            attribute_filters=attribute_filters,
            hard_filters=hard_filters,
            raw_text=normalized_name,
        )
    elif mode == "style":
        intent = PhotoPreferenceIntent(
            intent_type="style_similarity_search",
            mode="style",
            query_text=query_text or "这种感觉",
            attribute_filters=attribute_filters,
            hard_filters=hard_filters,
            raw_text=query_text or "这种感觉",
        )
    else:
        intent = detect_photo_preference_intent(
            query_text or celebrity_name,
            image_source=image_source or None,
        )
        intent = PhotoPreferenceIntent(
            intent_type=intent.intent_type,
            mode=intent.mode,
            query_text=intent.query_text,
            attribute_filters=intent.attribute_filters,
            hard_filters=hard_filters,
            celebrity_name=intent.celebrity_name,
            raw_text=intent.raw_text,
            confidence=intent.confidence,
            routing_reasons=intent.routing_reasons,
            image_understanding=intent.image_understanding,
        )

    top_k = max(1, min(int(body.get("top_k") or 12), 30))
    result = execute_photo_preference_search(
        source_dsn=source_dsn,
        requester_user_key=str(profile_id),
        intent=intent,
        image_source=image_source or None,
        requester_profile_id=profile_id,
        top_k=top_k,
    )
    ranked_results = [
        dict(item)
        for item in list(result.get("results") or [])
        if int(item.get("profile_id") or 0) > 0
    ]
    profile_map = _load_profile_rows_by_ids(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_ids=[int(item["profile_id"]) for item in ranked_results],
    )
    filtered_ranked_results = [
        item
        for item in ranked_results
        if _profile_matches_photo_search_hard_filters(
            profile_row=profile_map.get(int(item["profile_id"])),
            hard_filters=hard_filters,
        )
    ]
    previews = [
        _build_photo_search_preview(
            ranked_result=item,
            profile_row=profile_map.get(int(item["profile_id"])),
            intent=intent,
        )
        for item in filtered_ranked_results
    ]
    session_sync: dict[str, Any] | None = None
    if session_id:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        session_sync = _append_photo_search_to_discovery_session(
            discovery_service=gateway._discovery,
            session_id=session_id,
            mode=intent.mode,
            query_text=query_text or celebrity_name or intent.query_text,
            image_source=image_source,
            result_previews=previews,
        )
    return 200, {
        "trace_id": get_trace_id(),
        "task": {
            "status": "succeeded" if result.get("saved") else "failed",
            "stage": "results_ready" if result.get("saved") else "search_failed",
        },
        "intent": {
            "mode": intent.mode,
            "intent_type": intent.intent_type,
            "query_text": intent.query_text,
            "celebrity_name": intent.celebrity_name,
            "attribute_filters": dict(intent.attribute_filters),
            "hard_filters": dict(intent.hard_filters),
            "confidence": round(float(intent.confidence or 0.0), 4),
            "routing_reasons": list(intent.routing_reasons),
            "image_understanding": dict(intent.image_understanding),
        },
        "result_count": len(previews),
        "search_type": result.get("search_type") or intent.intent_type,
        "query_text": query_text,
        "image_source_present": bool(image_source),
        "results": previews,
        "session_sync": session_sync,
    }


def _discovery_error(exc: DiscoveryServiceError) -> tuple[int, dict[str, Any]]:
    return exc.status_code, {
        "error": {"code": exc.code, "message": exc.message},
        "error_code": exc.code,
        "error_message": exc.message,
        "retryable": exc.retryable,
        "trace_id": get_trace_id(),
    }


def rest_discovery_create_session(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        profile_id = gateway._resolve_int_actor_bound_id(
            environ,
            coalesce_profile_id_param(body.get("profile_id"), body.get("requester_id")),
            field_name="profile_id",
        )
        out = gateway._discovery.create_session(
            requester_id=profile_id,
            profile_id=profile_id,
            now=_parse_optional_now(body),
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 201, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_list_sessions(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """获取用户的 Discovery 会话列表。"""
    try:
        query = _query_dict(environ)
        profile_id = gateway._resolve_int_actor_bound_id(
            environ,
            coalesce_profile_id_param(query.get("profile_id"), query.get("requester_id")),
            field_name="profile_id",
        )
        limit = int(query.get("limit", "20") or "20")
        if limit < 1 or limit > 100:
            limit = 20
        out = gateway._discovery.list_sessions(
            profile_id=profile_id,
            limit=limit,
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_process_turn(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.process_turn(
            session_id=session_id,
            user_message_text=body.get("user_message"),
            action_id=body.get("action_id"),
            now=_parse_optional_now(body),
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_get_session(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.get_session_view(session_id)
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_express_interest(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    candidate_id: int,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.express_interest(
            session_id,
            candidate_id=candidate_id,
            now=_parse_optional_now(body),
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_quick_pass(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    candidate_id: int,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.record_quick_pass(
            session_id,
            candidate_id=candidate_id,
            now=_parse_optional_now(body),
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_explicit_dislike(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    candidate_id: int,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.record_explicit_dislike(
            session_id,
            candidate_id=candidate_id,
            now=_parse_optional_now(body),
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_candidate_telemetry(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    candidate_id: int,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.record_candidate_telemetry(
            session_id,
            candidate_id=candidate_id,
            telemetry=body.get("telemetry") if isinstance(body.get("telemetry"), dict) else body,
            now=_parse_optional_now(body),
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def dispatch_discovery_rest(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    """Discovery REST 路由分发 - 带路径参数验证

    SECURITY: 所有路径参数 {session_id} 先验证格式，防止注入攻击
    """
    def _validate_session_id(raw_id: str) -> tuple[str | None, dict[str, Any] | None]:
        """验证 session_id 格式，返回 (safe_id, error_response)"""
        try:
            return validate_id(raw_id, "session_id"), None
        except ValidationError as e:
            return None, {
                "error": {"code": "invalid_session_id", "message": str(e)},
                "trace_id": get_trace_id(),
            }

    if path == "/v1/discovery/sessions" and method == "POST":
        return rest_discovery_create_session(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )

    if path == "/v1/discovery/sessions" and method == "GET":
        return rest_discovery_list_sessions(gateway, environ)

    if path == "/v1/discovery/photo-search" and method == "POST":
        return rest_discovery_photo_search(
            gateway,
            environ,
            _parse_json_body(_read_body(environ)),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/turns", path)
    if match and method == "POST":
        safe_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        return rest_discovery_process_turn(
            gateway,
            environ,
            safe_id,
            _parse_json_body(_read_body(environ)),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/candidates/(\d+)/express-interest", path)
    if match and method == "POST":
        safe_session_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        # candidate_id 是整数，额外验证
        try:
            candidate_id = int(match.group(2))
            if candidate_id <= 0 or candidate_id > 10**9:
                return 400, {
                    "error": {"code": "invalid_candidate_id", "message": "candidate_id must be between 1 and 10^9"},
                    "trace_id": get_trace_id(),
                }
        except ValueError:
            return 400, {
                "error": {"code": "invalid_candidate_id", "message": "candidate_id must be an integer"},
                "trace_id": get_trace_id(),
            }
        return rest_discovery_express_interest(
            gateway,
            environ,
            safe_session_id,
            candidate_id,
            _parse_json_body(_read_body(environ)),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/candidates/(\d+)/quick-pass", path)
    if match and method == "POST":
        safe_session_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        try:
            candidate_id = int(match.group(2))
            if candidate_id <= 0 or candidate_id > 10**9:
                return 400, {
                    "error": {"code": "invalid_candidate_id", "message": "candidate_id must be between 1 and 10^9"},
                    "trace_id": get_trace_id(),
                }
        except ValueError:
            return 400, {
                "error": {"code": "invalid_candidate_id", "message": "candidate_id must be an integer"},
                "trace_id": get_trace_id(),
            }
        return rest_discovery_quick_pass(
            gateway,
            environ,
            safe_session_id,
            candidate_id,
            _parse_json_body(_read_body(environ)),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/candidates/(\d+)/explicit-dislike", path)
    if match and method == "POST":
        safe_session_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        try:
            candidate_id = int(match.group(2))
            if candidate_id <= 0 or candidate_id > 10**9:
                return 400, {
                    "error": {"code": "invalid_candidate_id", "message": "candidate_id must be between 1 and 10^9"},
                    "trace_id": get_trace_id(),
                }
        except ValueError:
            return 400, {
                "error": {"code": "invalid_candidate_id", "message": "candidate_id must be an integer"},
                "trace_id": get_trace_id(),
            }
        return rest_discovery_explicit_dislike(
            gateway,
            environ,
            safe_session_id,
            candidate_id,
            _parse_json_body(_read_body(environ)),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/candidates/(\d+)/telemetry", path)
    if match and method == "POST":
        safe_session_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        try:
            candidate_id = int(match.group(2))
            if candidate_id <= 0 or candidate_id > 10**9:
                return 400, {
                    "error": {"code": "invalid_candidate_id", "message": "candidate_id must be between 1 and 10^9"},
                    "trace_id": get_trace_id(),
                }
        except ValueError:
            return 400, {
                "error": {"code": "invalid_candidate_id", "message": "candidate_id must be an integer"},
                "trace_id": get_trace_id(),
            }
        return rest_discovery_candidate_telemetry(
            gateway,
            environ,
            safe_session_id,
            candidate_id,
            _parse_json_body(_read_body(environ)),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)", path)
    if match and method == "GET":
        safe_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        return rest_discovery_get_session(gateway, environ, safe_id)

    match = re.fullmatch(
        r"/v1/discovery/sessions/([^/]+)/profile-updates/([^/]+)/confirm",
        path,
    )
    if match and method == "POST":
        safe_session_id, error1 = _validate_session_id(match.group(1))
        if error1:
            return 400, error1
        safe_request_id, error2 = _validate_session_id(match.group(2))  # request_id 格式类似 session_id
        if error2:
            return 400, error2
        return rest_discovery_confirm_profile_update(
            gateway,
            environ,
            safe_session_id,
            safe_request_id,
        )

    match = re.fullmatch(
        r"/v1/discovery/sessions/([^/]+)/profile-updates/([^/]+)/reject",
        path,
    )
    if match and method == "POST":
        safe_session_id, error1 = _validate_session_id(match.group(1))
        if error1:
            return 400, error1
        safe_request_id, error2 = _validate_session_id(match.group(2))
        if error2:
            return 400, error2
        return rest_discovery_reject_profile_update(
            gateway,
            environ,
            safe_session_id,
            safe_request_id,
        )

    # 反馈收集路由
    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/feedback", path)
    if match and method == "POST":
        safe_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        return rest_discovery_submit_feedback(
            gateway,
            environ,
            safe_id,
            _parse_json_body(_read_body(environ)),
        )

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/feedback/skip", path)
    if match and method == "POST":
        safe_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        return rest_discovery_skip_feedback(gateway, environ, safe_id)

    match = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/feedback/options", path)
    if match and method == "GET":
        safe_id, error = _validate_session_id(match.group(1))
        if error:
            return 400, error
        return rest_discovery_get_feedback_options(gateway, environ, safe_id)

    return None


def rest_discovery_confirm_profile_update(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    request_id: str,
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.confirm_profile_update(session_id, request_id)
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_reject_profile_update(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    request_id: str,
) -> tuple[int, dict[str, Any]]:
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.reject_profile_update(session_id, request_id)
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


# ========== 新增：反馈收集API handler ==========

def rest_discovery_submit_feedback(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    """提交拒绝反馈。"""
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.submit_rejection_feedback(
            session_id=session_id,
            feedback_text=body.get("feedback_text", ""),
            feedback_type=body.get("feedback_type"),
            feedback_detail=body.get("feedback_detail"),
            rejected_candidate_ids=body.get("rejected_candidate_ids"),
            is_secondary=body.get("is_secondary", False),
            primary_feedback_id=body.get("primary_feedback_id"),
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_skip_feedback(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
) -> tuple[int, dict[str, Any]]:
    """跳过反馈。"""
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        out = gateway._discovery.skip_rejection_feedback(session_id=session_id)
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}


def rest_discovery_get_feedback_options(
    gateway: DiscoveryGateway,
    environ: dict[str, Any],
    session_id: str,
) -> tuple[int, dict[str, Any]]:
    """获取反馈选项列表。"""
    try:
        owner_id = gateway._discovery.get_session_owner_id(session_id)
        gateway._assert_actor_can_access_owner(
            environ,
            owner_id,
            field_name="profile_id",
        )
        # 从query参数获取secondary相关参数
        query = _query_dict(environ)
        include_secondary = query.get("include_secondary", "false").lower() == "true"
        primary_option = query.get("primary_option")

        out = gateway._discovery.get_feedback_options(
            session_id=session_id,
            include_secondary=include_secondary,
            primary_option=primary_option,
        )
    except DiscoveryServiceError as exc:
        return _discovery_error(exc)
    return 200, {**_json_safe(out), "trace_id": get_trace_id()}
