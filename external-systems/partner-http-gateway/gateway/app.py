"""WSGI app: REST JSON under /v1/... and JSON-RPC 2.0 under POST /jsonrpc."""

from __future__ import annotations

import json
import mimetypes
import os
import re
from datetime import datetime
from typing import Any, Callable
from urllib.parse import unquote

from . import _paths  # noqa: F401 — side effect: sys.path
from .http_helpers import (  # noqa: E402
    _augment_chat_message_metadata,
    _demo_asset_file,
    _extract_client_idempotency_key,
    _gateway_error_payload,
    _incoming_trace_id,
    _json_safe,
    _normalize_boolish,
    _normalize_optional_now_text,
    _parse_json_body,
    _parse_optional_now,
    _query_dict,
    _read_body,
    _read_demo_html,
    _statuses_from_query,
    _subscription_ids_from_query,
    _wrap_trace_headers,
)

from match_domain import (  # noqa: E402
    get_trace_id,
    reset_actor_context,
    reset_trace_id,
    set_actor_context,
    set_trace_id,
)
from observability import audit_event, emit_pipeline_record  # noqa: E402

from partner_search import search_profiles as partner_search_profiles  # noqa: E402

from recommendation_system import (  # type: ignore[import-untyped]
    connect_db as recommendation_connect_db,
    create_subscription,
    get_match_case as recommendation_get_match_case,
    get_subscription,
    list_in_app_cards,
    list_match_case_events as recommendation_list_match_case_events,
    list_recommendations_for_subscription,
    list_search_runs_for_subscription,
    mark_in_app_cards_read,
    record_recommendation_action,
    record_user_review,
    refresh_subscription,
    update_subscription_overrides,
)
from recommendation_system.async_tasks import (  # type: ignore[import-untyped]
    JOB_DELIVER_IN_APP_RECOMMENDATIONS,
    JOB_REFRESH_DUE_SUBSCRIPTIONS,
    enqueue_recommendation_async_job,
    get_recommendation_async_job,
    list_recommendation_async_jobs,
    summarize_recommendation_async_jobs,
)
from recommendation_system.storage import (  # type: ignore[import-untyped]
    DEFAULT_RECOMMENDATION_MYSQL_DSN,
)
from matchmaking_system import (  # type: ignore[import-untyped]
    connect_db as matchmaking_connect_db,
    create_pool_member,
    dispatch_case_contact,
    get_match_case,
    get_pair,
    get_pool_member,
    list_match_case_events,
    list_match_cases,
    list_pairs,
    record_case_reply,
    record_feedback,
    refresh_pool_member,
    set_pool_member_status,
)
from matchmaking_system.async_tasks import (  # type: ignore[import-untyped]
    JOB_BUILD_MUTUAL_PAIRS,
    JOB_CLOSE_STALE_CASES,
    JOB_OPEN_MATCH_CASES,
    JOB_REFRESH_ACTIVE_POOL,
    enqueue_matchmaking_async_job,
    get_matchmaking_async_job,
    list_matchmaking_async_jobs,
    summarize_matchmaking_async_jobs,
)
from matchmaking_system.storage import (  # type: ignore[import-untyped]
    DEFAULT_MATCHMAKING_MYSQL_DSN,
)
from chat_system import (  # type: ignore[import-untyped]
    batch_review_risk_cases,
    build_risk_case_playback,
    build_risk_weekly_dashboard,
    build_case_conversation_timeline,
    build_fraud_network_overview,
    build_thread_risk_overview,
    build_user_trust_hub,
    create_assistant_case_layout,
    create_live_video_verification_challenge,
    dispute_profile_field_verification,
    evaluate_fraud_network,
    evaluate_profile_consistency,
    expire_due_profile_field_verifications,
    field_verification_policies,
    get_photo_risk_score_run,
    get_fraud_network_profile,
    get_profile_field_verification_submission,
    get_profile_review_case_appeal,
    get_profile_review_case,
    get_risk_appeal,
    build_chat_timeline,
    get_conversation,
    get_or_create_thread,
    list_case_conversations,
    list_conversation_messages,
    list_fraud_network_profiles,
    list_photo_risk_review_queue,
    list_photo_risk_score_runs,
    list_photo_review_requests,
    list_profile_field_verification_submissions,
    list_profile_review_case_appeals,
    list_profile_review_cases,
    list_risk_appeals,
    get_thread,
    get_thread_summary,
    list_member_reports,
    list_meeting_feedback,
    list_messages,
    list_pending_outbox,
    list_risk_cases,
    list_risk_signals,
    list_verification_notifications,
    list_verification_submissions,
    post_message,
    post_conversation_message,
    get_verification_submission,
    request_live_video_verification,
    record_fraud_network_observation,
    resubmit_profile_field_verification,
    resubmit_live_video_verification,
    review_profile_field_verification,
    review_profile_review_case_appeal,
    review_profile_review_case,
    review_risk_appeal,
    review_risk_case,
    review_live_video_verification,
    submit_profile_field_verification,
    submit_profile_review_case_appeal,
    submit_risk_appeal,
    submit_live_video_verification,
    submit_meeting_feedback,
    submit_member_report,
)
from chat_system.async_tasks import (  # type: ignore[import-untyped]
    JOB_RUN_CHAT_MAINTENANCE,
    enqueue_chat_async_job,
    get_chat_async_job,
    list_chat_async_jobs,
    summarize_chat_async_jobs,
)
from chat_system.persona_jobs import process_pending_persona_jobs  # type: ignore[import-untyped]
from chat_system.storage import (  # type: ignore[import-untyped]
    DEFAULT_CHAT_MYSQL_DSN,
    connect_db as chat_connect_db,
)
from discovery_system import (  # type: ignore[import-untyped]
    DiscoveryServiceError,
    create_default_discovery_service,
)

from .async_jobs import AsyncJobGatewayMixin
from .identity import (
    ActorPrincipal,
    GatewayAuthError,
    GatewayPermissionError,
    IdentityResolver,
    ROLE_CUSTOMER_SUPPORT,
    ROLE_OPS_OPERATOR,
    ROLE_PLATFORM_ADMIN,
    ROLE_PROFILE_REVIEWER,
    ROLE_RISK_REVIEWER,
    ROLE_SERVICE_WORKER,
    get_current_actor,
    set_current_actor,
)
from .mysql_pool import GatewayConnectionPool
from .request_policy import client_ip, rate_limiter_from_environ

JSON_HEADERS = [("Content-Type", "application/json; charset=utf-8")]
HTML_HEADERS = [("Content-Type", "text/html; charset=utf-8")]
DEMO_HTML_HEADERS = HTML_HEADERS + [("Cache-Control", "no-store")]

RouteHandler = Callable[..., tuple[int, dict[str, Any]]]

STAFF_OVERRIDE_ROLES = frozenset(
    {
        ROLE_OPS_OPERATOR,
        ROLE_RISK_REVIEWER,
        ROLE_PROFILE_REVIEWER,
        ROLE_CUSTOMER_SUPPORT,
        ROLE_PLATFORM_ADMIN,
        ROLE_SERVICE_WORKER,
    }
)
INTERNAL_WRITE_ROLES = frozenset({ROLE_OPS_OPERATOR, ROLE_PLATFORM_ADMIN, ROLE_SERVICE_WORKER})
VERIFICATION_REVIEW_ROLES = frozenset(
    {
        ROLE_RISK_REVIEWER,
        ROLE_PROFILE_REVIEWER,
        ROLE_PLATFORM_ADMIN,
        ROLE_SERVICE_WORKER,
    }
)
PROFILE_REVIEW_ROLES = frozenset({ROLE_PROFILE_REVIEWER, ROLE_PLATFORM_ADMIN, ROLE_SERVICE_WORKER})
CHAT_RISK_REVIEW_ROLES = frozenset(
    {
        ROLE_RISK_REVIEWER,
        ROLE_CUSTOMER_SUPPORT,
        ROLE_PLATFORM_ADMIN,
        ROLE_SERVICE_WORKER,
    }
)


class PartnerGateway(AsyncJobGatewayMixin):
    def __init__(
        self,
        *,
        recommendation_dsn: str | None = None,
        matchmaking_dsn: str | None = None,
        chat_dsn: str | None = None,
        db_pool_max: int | None = None,
    ) -> None:
        self._recommendation_dsn = recommendation_dsn or os.environ.get(
            "PARTNER_RECOMMENDATION_DB", DEFAULT_RECOMMENDATION_MYSQL_DSN
        )
        self._matchmaking_dsn = matchmaking_dsn or os.environ.get(
            "PARTNER_MATCHMAKING_DB", DEFAULT_MATCHMAKING_MYSQL_DSN
        )
        self._chat_dsn = chat_dsn or os.environ.get("PARTNER_CHAT_DB", DEFAULT_CHAT_MYSQL_DSN)
        pool_n = db_pool_max if db_pool_max is not None else int(os.environ.get("PARTNER_GATEWAY_DB_POOL_MAX", "0") or "0")
        self._rec_pool: GatewayConnectionPool | None = None
        self._mm_pool: GatewayConnectionPool | None = None
        self._chat_pool: GatewayConnectionPool | None = None
        if pool_n > 0:
            self._rec_pool = GatewayConnectionPool(self._recommendation_dsn, "recommendation", max_size=pool_n)
            self._mm_pool = GatewayConnectionPool(self._matchmaking_dsn, "matchmaking", max_size=pool_n)
            self._chat_pool = GatewayConnectionPool(self._chat_dsn, "chat", max_size=pool_n)
        self._discovery = create_default_discovery_service()
        self._identity_resolver = IdentityResolver()
        self._rate_limiter = rate_limiter_from_environ()

    def _with_rec(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if self._rec_pool is not None:
            conn = self._rec_pool.acquire()
            try:
                return fn(conn, *args, **kwargs)
            finally:
                self._rec_pool.release(conn)
        conn = recommendation_connect_db(self._recommendation_dsn)
        try:
            return fn(conn, *args, **kwargs)
        finally:
            conn.close()

    def _with_mm(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if self._mm_pool is not None:
            conn = self._mm_pool.acquire()
            try:
                return fn(conn, *args, **kwargs)
            finally:
                self._mm_pool.release(conn)
        conn = matchmaking_connect_db(self._matchmaking_dsn)
        try:
            return fn(conn, *args, **kwargs)
        finally:
            conn.close()

    def _with_chat(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        if self._chat_pool is not None:
            conn = self._chat_pool.acquire()
            try:
                return fn(conn, *args, **kwargs)
            finally:
                self._chat_pool.release(conn)
        conn = chat_connect_db(self._chat_dsn)
        try:
            return fn(conn, *args, **kwargs)
        finally:
            conn.close()

    # --- REST ---

    def handle_health(self, _environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return 200, {
            "ok": True,
            "services": ["recommendation", "matchmaking", "chat"],
            "recommendation_db_configured": bool(self._recommendation_dsn),
            "matchmaking_db_configured": bool(self._matchmaking_dsn),
            "chat_db_configured": bool(self._chat_dsn),
            "db_connection_pool": bool(self._rec_pool and self._mm_pool and self._chat_pool),
            "auth_required": self._identity_resolver.required,
            "api_key_required": self._identity_resolver.legacy_api_required,
            "static_token_count": self._identity_resolver.static_token_count,
            "rate_limit_per_minute": int(os.environ.get("PARTNER_GATEWAY_RATE_LIMIT_PER_MINUTE", "600") or "600"),
        }

    def _discovery_error(self, exc: DiscoveryServiceError) -> tuple[int, dict[str, Any]]:
        return exc.status_code, {
            "error": {"code": exc.code, "message": exc.message},
            "error_code": exc.code,
            "error_message": exc.message,
            "retryable": exc.retryable,
            "trace_id": get_trace_id(),
        }

    def rest_discovery_create_session(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        try:
            requester_id = self._resolve_int_actor_bound_id(
                environ,
                body.get("requester_id"),
                field_name="requester_id",
            )
            profile_id = int(body["profile_id"])
            out = self._discovery.create_session(
                requester_id=requester_id,
                profile_id=profile_id,
                now=_parse_optional_now(body),
            )
        except DiscoveryServiceError as exc:
            return self._discovery_error(exc)
        return 201, {**_json_safe(out), "trace_id": get_trace_id()}

    def rest_discovery_process_turn(
        self,
        environ: dict[str, Any],
        session_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        try:
            owner_id = self._discovery.get_session_owner_id(session_id)
            self._assert_actor_can_access_owner(
                environ,
                owner_id,
                field_name="requester_id",
            )
            out = self._discovery.process_turn(
                session_id=session_id,
                user_message_text=body.get("user_message"),
                action_id=body.get("action_id"),
                now=_parse_optional_now(body),
            )
        except DiscoveryServiceError as exc:
            return self._discovery_error(exc)
        return 200, {**_json_safe(out), "trace_id": get_trace_id()}

    def rest_discovery_get_session(
        self,
        environ: dict[str, Any],
        session_id: str,
    ) -> tuple[int, dict[str, Any]]:
        try:
            owner_id = self._discovery.get_session_owner_id(session_id)
            self._assert_actor_can_access_owner(
                environ,
                owner_id,
                field_name="requester_id",
            )
            out = self._discovery.get_session_view(session_id)
        except DiscoveryServiceError as exc:
            return self._discovery_error(exc)
        return 200, {**_json_safe(out), "trace_id": get_trace_id()}

    def rest_discovery_get_profile_detail(
        self,
        environ: dict[str, Any],
        profile_id: str,
    ) -> tuple[int, dict[str, Any]]:
        query = _query_dict(environ)
        session_id = (query.get("session_id") or "").strip() or None
        try:
            if session_id is not None:
                owner_id = self._discovery.get_session_owner_id(session_id)
                self._assert_actor_can_access_owner(
                    environ,
                    owner_id,
                    field_name="requester_id",
                )
            out = self._discovery.get_profile_detail(
                int(profile_id),
                session_id=session_id,
            )
        except DiscoveryServiceError as exc:
            return self._discovery_error(exc)
        return 200, {**_json_safe(out), "trace_id": get_trace_id()}

    def _current_actor(self, environ: dict[str, Any]) -> ActorPrincipal | None:
        return get_current_actor(environ)

    def _audit_permission(
        self,
        environ: dict[str, Any],
        *,
        action: str,
        resource_type: str,
        outcome: str,
        resource_id: Any = None,
        reason: str | None = None,
        impersonated_owner_id: Any = None,
        **extra: Any,
    ) -> None:
        audit_event(
            action=action,
            resource_type=resource_type,
            outcome=outcome,
            resource_id=resource_id,
            reason=reason,
            impersonated_owner_id=impersonated_owner_id,
            http_method=environ.get("REQUEST_METHOD"),
            path=environ.get("PATH_INFO"),
            **extra,
        )

    def _require_roles(
        self,
        environ: dict[str, Any],
        roles: frozenset[str],
        *,
        message: str = "current actor is not allowed to access this route",
    ) -> ActorPrincipal | None:
        actor = self._current_actor(environ)
        if actor is None:
            return None
        if actor.has_any_role(roles):
            self._audit_permission(
                environ,
                action="gateway.role_guard",
                resource_type="route",
                resource_id=environ.get("PATH_INFO"),
                outcome="allowed",
                required_roles=sorted(roles),
            )
            return actor
        self._audit_permission(
            environ,
            action="gateway.role_guard",
            resource_type="route",
            resource_id=environ.get("PATH_INFO"),
            outcome="denied",
            reason=message,
            required_roles=sorted(roles),
        )
        raise GatewayPermissionError(message)

    def _resolve_operator_actor_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        roles: frozenset[str],
        message: str,
    ) -> str:
        supplied_text = str(supplied_id or "").strip()
        actor = self._current_actor(environ)
        if actor is None:
            if not supplied_text:
                raise ValueError(f"{field_name} is required")
            return supplied_text
        if not actor.has_any_role(roles):
            self._audit_permission(
                environ,
                action="gateway.operator_binding",
                resource_type="route",
                resource_id=environ.get("PATH_INFO"),
                outcome="denied",
                reason=message,
                field_name=field_name,
            )
            raise GatewayPermissionError(message)
        if supplied_text and supplied_text != actor.actor_id:
            self._audit_permission(
                environ,
                action="gateway.operator_binding",
                resource_type="route",
                resource_id=environ.get("PATH_INFO"),
                outcome="denied",
                reason=f"{field_name} must match current actor",
                field_name=field_name,
                impersonated_owner_id=supplied_text,
            )
            raise GatewayPermissionError(f"{field_name} must match current actor")
        self._audit_permission(
            environ,
            action="gateway.operator_binding",
            resource_type="route",
            resource_id=environ.get("PATH_INFO"),
            outcome="allowed",
            field_name=field_name,
        )
        return actor.actor_id

    def _resolve_optional_operator_actor_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        roles: frozenset[str],
        message: str,
    ) -> str | None:
        supplied_text = str(supplied_id or "").strip() or None
        actor = self._current_actor(environ)
        if actor is None:
            return supplied_text
        if not actor.has_any_role(roles):
            raise GatewayPermissionError(message)
        if supplied_text and supplied_text != actor.actor_id:
            raise GatewayPermissionError(f"{field_name} must match current actor")
        return actor.actor_id

    def _resolve_actor_bound_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> str:
        supplied_text = str(supplied_id or "").strip()
        actor = self._current_actor(environ)
        if actor is None:
            if not supplied_text:
                raise ValueError(f"{field_name} is required")
            return supplied_text
        if actor.has_any_role(allow_override_roles):
            if supplied_text and supplied_text != actor.actor_id:
                self._audit_permission(
                    environ,
                    action="gateway.staff_override",
                    resource_type="actor_binding",
                    resource_id=field_name,
                    outcome="allowed",
                    impersonated_owner_id=supplied_text,
                )
            return supplied_text or actor.actor_id
        if supplied_text and supplied_text != actor.actor_id:
            self._audit_permission(
                environ,
                action="gateway.owner_binding",
                resource_type="actor_binding",
                resource_id=field_name,
                outcome="denied",
                reason=f"{field_name} does not match current actor",
                impersonated_owner_id=supplied_text,
            )
            raise GatewayPermissionError(f"{field_name} does not match current actor")
        return actor.actor_id

    def _assert_actor_can_access_owner(
        self,
        environ: dict[str, Any],
        owner_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> str:
        owner_text = str(owner_id or "").strip()
        actor = self._current_actor(environ)
        if actor is None or not owner_text or actor.has_any_role(allow_override_roles):
            if (
                actor is not None
                and owner_text
                and actor.has_any_role(allow_override_roles)
                and owner_text != actor.actor_id
            ):
                self._audit_permission(
                    environ,
                    action="gateway.staff_override",
                    resource_type="resource_owner",
                    resource_id=field_name,
                    outcome="allowed",
                    impersonated_owner_id=owner_text,
                )
            return owner_text
        if owner_text != actor.actor_id:
            self._audit_permission(
                environ,
                action="gateway.owner_check",
                resource_type="resource_owner",
                resource_id=field_name,
                outcome="denied",
                reason=f"{field_name} does not match current actor",
                impersonated_owner_id=owner_text,
            )
            raise GatewayPermissionError(f"{field_name} does not match current actor")
        return owner_text

    def _resolve_int_actor_bound_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> int:
        value = self._resolve_actor_bound_id(
            environ,
            supplied_id,
            field_name=field_name,
            allow_override_roles=allow_override_roles,
        )
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name} must be an integer") from exc

    def _get_recommendation_subscription_for_actor(
        self,
        environ: dict[str, Any],
        subscription_id: str,
    ) -> dict[str, Any]:
        subscription = self._with_rec(get_subscription, subscription_id)
        self._assert_actor_can_access_owner(
            environ,
            subscription.get("requester_id"),
            field_name="requester_id",
        )
        return subscription

    def _get_matchmaking_member_for_actor(
        self,
        environ: dict[str, Any],
        member_id: str,
    ) -> dict[str, Any]:
        member = self._with_mm(get_pool_member, member_id)
        self._assert_actor_can_access_owner(
            environ,
            member.get("user_key"),
            field_name="user_key",
        )
        return member

    def _get_matchmaking_case_for_actor(
        self,
        environ: dict[str, Any],
        case_id: str,
    ) -> dict[str, Any]:
        case = self._with_mm(get_match_case, case_id)
        actor = self._current_actor(environ)
        if actor is None or actor.has_any_role(STAFF_OVERRIDE_ROLES):
            if actor is not None and actor.has_any_role(STAFF_OVERRIDE_ROLES):
                member_ids = {
                    str(case.get("first_contact_member_id") or "").strip(),
                    str(case.get("second_contact_member_id") or "").strip(),
                }
                member_ids.discard("")
                owner_keys = sorted(
                    {
                        str(self._with_mm(get_pool_member, member_id).get("user_key") or "").strip()
                        for member_id in member_ids
                    }
                )
                owner_keys = [value for value in owner_keys if value and value != actor.actor_id]
                if owner_keys:
                    self._audit_permission(
                        environ,
                        action="gateway.staff_override",
                        resource_type="matchmaking_case",
                        resource_id=case_id,
                        outcome="allowed",
                        impersonated_owner_id=",".join(owner_keys),
                    )
            return case
        member_ids = {
            str(case.get("first_contact_member_id") or "").strip(),
            str(case.get("second_contact_member_id") or "").strip(),
        }
        member_ids.discard("")
        for member_id in member_ids:
            member = self._with_mm(get_pool_member, member_id)
            if str(member.get("user_key") or "").strip() == actor.actor_id:
                return case
        self._audit_permission(
            environ,
            action="gateway.case_access",
            resource_type="matchmaking_case",
            resource_id=case_id,
            outcome="denied",
            reason="current actor is not a participant in this match case",
        )
        raise GatewayPermissionError("current actor is not allowed to access this match case")

    def rest_get_subscription(self, environ: dict[str, Any], subscription_id: str) -> tuple[int, dict[str, Any]]:
        sub = self._get_recommendation_subscription_for_actor(environ, subscription_id)
        return 200, {"subscription": _json_safe(sub)}

    def rest_create_subscription(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if "requester_id" in kwargs or self._current_actor(environ) is not None:
            kwargs["requester_id"] = self._resolve_int_actor_bound_id(
                environ,
                kwargs.get("requester_id"),
                field_name="requester_id",
            )
        if now is not None:
            kwargs["now"] = now
        sub = self._with_rec(create_subscription, **kwargs)
        return 201, {"subscription": _json_safe(sub)}

    def rest_patch_overrides(self, environ: dict[str, Any], subscription_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        self._get_recommendation_subscription_for_actor(environ, subscription_id)
        now = _parse_optional_now(body)
        overrides = body.get("overrides")
        if overrides is None:
            overrides = {k: v for k, v in body.items() if k not in {"now"}}
        sub = self._with_rec(update_subscription_overrides, subscription_id, overrides, now=now)
        return 200, {"subscription": _json_safe(sub)}

    def rest_refresh_subscription(self, environ: dict[str, Any], subscription_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        self._get_recommendation_subscription_for_actor(environ, subscription_id)
        now = _parse_optional_now(body)
        out = self._with_rec(refresh_subscription, subscription_id, now=now)
        return 200, _json_safe(out)

    def rest_refresh_due(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot refresh due recommendation subscriptions",
        )
        q = _query_dict(environ)
        ids = _subscription_ids_from_query(q) or body.get("subscription_ids")
        if ids is not None and not isinstance(ids, list):
            raise ValueError("subscription_ids must be a list")
        payload: dict[str, Any] = {}
        if ids is not None:
            payload["subscription_ids"] = [str(item) for item in ids]
        now_text = _normalize_optional_now_text(body.get("now") if body.get("now") not in (None, "") else q.get("now"))
        if now_text is not None:
            payload["now"] = now_text
        return self._enqueue_async_job(
            environ,
            target="recommendation",
            with_fn=self._with_rec,
            enqueue_fn=enqueue_recommendation_async_job,
            job_type=JOB_REFRESH_DUE_SUBSCRIPTIONS,
            payload=payload,
        )

    def rest_list_recommendations(self, environ: dict[str, Any], subscription_id: str) -> tuple[int, dict[str, Any]]:
        self._get_recommendation_subscription_for_actor(environ, subscription_id)
        rows = self._with_rec(list_recommendations_for_subscription, subscription_id)
        return 200, {"recommendations": _json_safe(rows)}

    def rest_list_runs(self, environ: dict[str, Any], subscription_id: str) -> tuple[int, dict[str, Any]]:
        self._get_recommendation_subscription_for_actor(environ, subscription_id)
        rows = self._with_rec(list_search_runs_for_subscription, subscription_id)
        return 200, {"runs": _json_safe(rows)}

    def rest_list_cards(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = q.get("requester_id")
        rid = None
        if requester_id not in (None, "") or self._current_actor(environ) is not None:
            rid = self._resolve_int_actor_bound_id(
                environ,
                requester_id,
                field_name="requester_id",
            )
        unread = str(q.get("unread_only", "")).lower() in ("1", "true", "yes")
        cards = self._with_rec(list_in_app_cards, requester_id=rid, unread_only=unread)
        return 200, {"cards": _json_safe(cards)}

    def rest_deliver(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot deliver recommendation cards",
        )
        payload: dict[str, Any] = {}
        now_text = _normalize_optional_now_text(body.get("now"))
        if now_text is not None:
            payload["now"] = now_text
        return self._enqueue_async_job(
            environ,
            target="recommendation",
            with_fn=self._with_rec,
            enqueue_fn=enqueue_recommendation_async_job,
            job_type=JOB_DELIVER_IN_APP_RECOMMENDATIONS,
            payload=payload,
        )

    def rest_get_recommendation_job(self, environ: dict[str, Any], job_id: str) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect recommendation jobs",
        )
        return self._get_async_job(
            target="recommendation",
            with_fn=self._with_rec,
            get_fn=get_recommendation_async_job,
            job_id=job_id,
        )

    def rest_list_recommendation_jobs(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect recommendation jobs",
        )
        return self._list_async_jobs(
            environ,
            target="recommendation",
            with_fn=self._with_rec,
            list_fn=list_recommendation_async_jobs,
            summary_fn=summarize_recommendation_async_jobs,
        )

    def rest_record_action(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        subscription = self._get_recommendation_subscription_for_actor(environ, str(body.get("subscription_id") or ""))
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k not in {"now", "idempotency_key", "client_idempotency_key"}}
        idem = _extract_client_idempotency_key(environ, body)
        if idem:
            kwargs["client_idempotency_key"] = idem
        if now is not None:
            kwargs["now"] = now
        kwargs["subscription_id"] = subscription["subscription_id"]
        actor = self._current_actor(environ)
        if actor is not None:
            kwargs["actor_id"] = actor.actor_id
        rec = self._with_rec(record_recommendation_action, **kwargs)
        out: dict[str, Any] = {"recommendation": _json_safe(rec)}
        if idem:
            out["client_idempotency_key"] = idem
        out["trace_id"] = get_trace_id()
        return 200, out

    def rest_record_review(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        subscription = self._get_recommendation_subscription_for_actor(environ, str(body.get("subscription_id") or ""))
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k not in {"now", "idempotency_key", "client_idempotency_key"}}
        idem = _extract_client_idempotency_key(environ, body)
        if idem:
            kwargs["client_idempotency_key"] = idem
        if now is not None:
            kwargs["now"] = now
        kwargs["subscription_id"] = subscription["subscription_id"]
        actor = self._current_actor(environ)
        if actor is not None:
            kwargs["actor_id"] = actor.actor_id
        rec = self._with_rec(record_user_review, **kwargs)
        out: dict[str, Any] = {"recommendation": _json_safe(rec)}
        if idem:
            out["client_idempotency_key"] = idem
        out["trace_id"] = get_trace_id()
        return 200, out

    def rest_search_profiles(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        source = body.get("source") or body.get("sources")
        if not source:
            raise ValueError("source or sources is required")
        response = partner_search_profiles(
            source=source,
            criteria=body.get("criteria") or {},
            self_profile=body.get("self_profile"),
            self_id=body.get("self_id"),
            table_name=body.get("table_name"),
            photos_table_name=body.get("photos_table_name"),
            limit=int(body.get("limit", 10)),
            photo_preview_count=int(body.get("photo_preview_count", 0)),
            include_source=_normalize_boolish(body.get("include_source"), False),
            include_text=_normalize_boolish(body.get("include_text"), False),
            moderation_dsn=self._chat_dsn,
            include_moderation_blocked=_normalize_boolish(body.get("include_moderation_blocked"), False),
        )
        return 200, _json_safe(response)

    def rest_verification_submit_live_video(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        user_id = self._resolve_actor_bound_id(environ, body.get("user_id"), field_name="user_id")
        submission = self._with_chat(
            submit_live_video_verification,
            user_id=user_id,
            video_base64=str(body.get("video_base64") or body.get("video_bytes_base64") or ""),
            file_name=str(body.get("file_name") or body.get("filename") or ""),
            submission_id=body.get("submission_id"),
            content_type=body.get("content_type"),
            profile_id=int(body["profile_id"]) if body.get("profile_id") is not None else None,
            source_dsn=body.get("source_dsn") or body.get("source"),
            source_table_name=body.get("source_table_name") or body.get("table_name"),
            challenge_token=body.get("challenge_token"),
            challenge_phrase=body.get("challenge_phrase"),
            metadata=body.get("metadata"),
            now=now,
        )
        return 201, {"submission": _json_safe(submission)}

    def rest_verification_request_live_video(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            VERIFICATION_REVIEW_ROLES | CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot request live video verification",
        )
        now = _parse_optional_now(body)
        raw_due_at = body.get("due_at")
        due_at = datetime.fromisoformat(str(raw_due_at)) if raw_due_at else None
        user_id = body.get("user_id")
        if not user_id:
            raise ValueError("user_id is required")
        request = self._with_chat(
            request_live_video_verification,
            user_id=str(user_id),
            profile_id=int(body["profile_id"]) if body.get("profile_id") is not None else None,
            source_dsn=body.get("source_dsn") or body.get("source"),
            source_table_name=body.get("source_table_name") or body.get("table_name"),
            request_source=str(body.get("request_source") or "risk_case_review"),
            request_reason=body.get("request_reason") or body.get("reason_text"),
            signal_codes=body.get("signal_codes") or body.get("reason_codes"),
            risk_case_id=body.get("risk_case_id"),
            report_ids=body.get("report_ids"),
            requested_by=self._resolve_optional_operator_actor_id(
                environ,
                body.get("requested_by") or body.get("resolver_id"),
                field_name="requested_by",
                roles=VERIFICATION_REVIEW_ROLES | CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot request live video verification",
            ),
            due_at=due_at,
            metadata=body.get("metadata"),
            now=now,
        )
        return 201, {"request": _json_safe(request)}

    def rest_verification_create_live_challenge(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        user_id = self._resolve_actor_bound_id(environ, body.get("user_id"), field_name="user_id")
        challenge = create_live_video_verification_challenge(
            user_id=user_id,
            profile_id=int(body["profile_id"]) if body.get("profile_id") is not None else None,
            challenge_actions=body.get("challenge_actions") or body.get("required_actions"),
            challenge_action_pool=body.get("challenge_action_pool") or body.get("allowed_actions"),
            action_count=int(body.get("action_count", 3)),
            now=now,
        )
        return 201, {"challenge": _json_safe(challenge)}

    def rest_verification_list_submissions(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        user_id = q.get("user_id") or None
        actor = self._current_actor(environ)
        if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
            user_id = self._resolve_actor_bound_id(environ, user_id, field_name="user_id")
        limit_raw = q.get("limit") or "100"
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 100
        rows = self._with_chat(
            list_verification_submissions,
            user_id=user_id,
            statuses=_statuses_from_query(q),
            profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
            limit=limit,
        )
        return 200, {"submissions": _json_safe(rows)}

    def rest_verification_list_photo_review_requests(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        user_id = q.get("user_id") or None
        actor = self._current_actor(environ)
        if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
            user_id = self._resolve_actor_bound_id(environ, user_id, field_name="user_id")
        limit_raw = q.get("limit") or "100"
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 100
        rows = self._with_chat(
            list_photo_review_requests,
            user_id=user_id,
            statuses=_statuses_from_query(q),
            profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
            limit=limit,
        )
        return 200, {"requests": _json_safe(rows)}

    def rest_verification_get_submission(
        self,
        environ: dict[str, Any],
        submission_id: str,
    ) -> tuple[int, dict[str, Any]]:
        submission = self._with_chat(get_verification_submission, submission_id)
        if not submission:
            return 404, {"error": {"code": "not_found", "message": "verification submission not found"}}
        self._assert_actor_can_access_owner(environ, submission.get("user_id"), field_name="user_id")
        return 200, {"submission": _json_safe(submission)}

    def rest_verification_get_photo_review_request(
        self,
        environ: dict[str, Any],
        submission_id: str,
    ) -> tuple[int, dict[str, Any]]:
        submission = self._with_chat(get_verification_submission, submission_id)
        if not submission or not (submission.get("photo_review_task") or {}).get("task_kind"):
            return 404, {"error": {"code": "not_found", "message": "photo review request not found"}}
        self._assert_actor_can_access_owner(environ, submission.get("user_id"), field_name="user_id")
        return 200, {"request": _json_safe(submission)}

    def rest_verification_resubmit_live_video(
        self,
        environ: dict[str, Any],
        submission_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        user_id = self._resolve_actor_bound_id(environ, body.get("user_id"), field_name="user_id")
        submission = self._with_chat(
            resubmit_live_video_verification,
            submission_id,
            user_id=user_id,
            video_base64=str(body.get("video_base64") or body.get("video_bytes_base64") or ""),
            file_name=str(body.get("file_name") or body.get("filename") or ""),
            content_type=body.get("content_type"),
            challenge_token=body.get("challenge_token"),
            challenge_phrase=body.get("challenge_phrase"),
            metadata=body.get("metadata"),
            now=now,
        )
        return 200, {"submission": _json_safe(submission)}

    def rest_verification_list_notifications(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        user_id = q.get("user_id") or None
        actor = self._current_actor(environ)
        if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
            user_id = self._resolve_actor_bound_id(environ, user_id, field_name="user_id")
        limit_raw = q.get("limit") or "100"
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 100
        rows = self._with_chat(
            list_verification_notifications,
            submission_id=q.get("submission_id") or None,
            user_id=user_id,
            notification_types=_statuses_from_query(q, key="type"),
            limit=limit,
        )
        return 200, {"notifications": _json_safe(rows)}

    def rest_verification_review_submission(
        self,
        environ: dict[str, Any],
        submission_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        reviewer_id = self._resolve_operator_actor_id(
            environ,
            body.get("reviewer_id"),
            field_name="reviewer_id",
            roles=VERIFICATION_REVIEW_ROLES,
            message="current actor cannot review live video submissions",
        )
        decision = body.get("decision")
        if not decision:
            raise ValueError("decision is required")
        submission = self._with_chat(
            review_live_video_verification,
            submission_id,
            reviewer_id,
            decision=str(decision),
            review_note=body.get("review_note"),
            liveness_result=body.get("liveness_result"),
            face_match_result=body.get("face_match_result"),
            profile_consistency_result=body.get("profile_consistency_result"),
            metadata=body.get("metadata"),
            now=now,
        )
        return 200, {"submission": _json_safe(submission)}

    def rest_profile_verification_policies(self, _environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return 200, {"policies": _json_safe(field_verification_policies())}

    def rest_profile_submit_field_verification(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        for key in ("field_key", "profile_id", "source_dsn"):
            if body.get(key) in (None, ""):
                raise ValueError(f"{key} is required")
        subject_user_id = None
        if body.get("subject_user_id") not in (None, "") or self._current_actor(environ) is not None:
            subject_user_id = self._resolve_actor_bound_id(
                environ,
                body.get("subject_user_id"),
                field_name="subject_user_id",
            )
        submission = self._with_chat(
            submit_profile_field_verification,
            field_key=str(body["field_key"]),
            profile_id=int(body["profile_id"]),
            source_dsn=str(body["source_dsn"]),
            source_table_name=body.get("source_table_name") or body.get("table_name"),
            subject_user_id=subject_user_id,
            declared_value=body.get("declared_value"),
            evidence=body.get("evidence"),
            evidence_type=body.get("evidence_type"),
            evidence_channel=body.get("evidence_channel"),
            required_documents=body.get("required_documents"),
            now=now,
        )
        return 201, {"submission": _json_safe(submission)}

    def rest_profile_list_field_verifications(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        subject_user_id = q.get("subject_user_id") or None
        actor = self._current_actor(environ)
        if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
            subject_user_id = self._resolve_actor_bound_id(environ, subject_user_id, field_name="subject_user_id")
        rows = self._with_chat(
            list_profile_field_verification_submissions,
            field_key=q.get("field_key") or None,
            subject_user_id=subject_user_id,
            profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
            statuses=_statuses_from_query(q),
            dispute_statuses=_statuses_from_query({"status": q.get("dispute_status"), "statuses": q.get("dispute_statuses")}),
            limit=int(q.get("limit", 100)),
        )
        return 200, {"submissions": _json_safe(rows)}

    def rest_profile_get_field_verification(self, environ: dict[str, Any], submission_id: str) -> tuple[int, dict[str, Any]]:
        submission = self._with_chat(get_profile_field_verification_submission, submission_id)
        if not submission:
            return 404, {"error": {"code": "not_found", "message": "profile verification submission not found"}}
        self._assert_actor_can_access_owner(environ, submission.get("subject_user_id"), field_name="subject_user_id")
        return 200, {"submission": _json_safe(submission)}

    def rest_profile_resubmit_field_verification(
        self,
        environ: dict[str, Any],
        submission_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        subject_user_id = None
        if body.get("subject_user_id") not in (None, "") or self._current_actor(environ) is not None:
            subject_user_id = self._resolve_actor_bound_id(
                environ,
                body.get("subject_user_id"),
                field_name="subject_user_id",
            )
        submission = self._with_chat(
            resubmit_profile_field_verification,
            submission_id,
            subject_user_id=subject_user_id,
            declared_value=body.get("declared_value"),
            evidence=body.get("evidence"),
            evidence_type=body.get("evidence_type"),
            evidence_channel=body.get("evidence_channel"),
            required_documents=body.get("required_documents"),
            now=now,
        )
        return 200, {"submission": _json_safe(submission)}

    def rest_profile_dispute_field_verification(
        self,
        environ: dict[str, Any],
        submission_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        if body.get("dispute_reason") in (None, ""):
            raise ValueError("dispute_reason is required")
        subject_user_id = None
        if body.get("subject_user_id") not in (None, "") or self._current_actor(environ) is not None:
            subject_user_id = self._resolve_actor_bound_id(
                environ,
                body.get("subject_user_id"),
                field_name="subject_user_id",
            )
        submission = self._with_chat(
            dispute_profile_field_verification,
            submission_id,
            subject_user_id=subject_user_id,
            dispute_reason=str(body["dispute_reason"]),
            evidence=body.get("evidence"),
            now=now,
        )
        return 200, {"submission": _json_safe(submission)}

    def rest_profile_review_field_verification(
        self,
        environ: dict[str, Any],
        submission_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        reviewer_id = self._resolve_operator_actor_id(
            environ,
            body.get("reviewer_id"),
            field_name="reviewer_id",
            roles=PROFILE_REVIEW_ROLES,
            message="current actor cannot review profile verifications",
        )
        if body.get("decision") in (None, ""):
            raise ValueError("decision is required")
        submission = self._with_chat(
            review_profile_field_verification,
            submission_id,
            reviewer_id,
            decision=str(body["decision"]),
            review_note=body.get("review_note"),
            approved_value=body.get("approved_value"),
            requested_documents=body.get("requested_documents"),
            metadata=body.get("metadata"),
            validity_days=body.get("validity_days"),
            next_review_days=body.get("next_review_days"),
            reverify_strategy=body.get("reverify_strategy"),
            now=now,
        )
        return 200, {"submission": _json_safe(submission)}

    def rest_profile_expire_due_field_verifications(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            PROFILE_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
            message="current actor cannot expire due profile verifications",
        )
        now = _parse_optional_now(body)
        result = self._with_chat(
            expire_due_profile_field_verifications,
            now=now,
            limit=int(body.get("limit", 100)),
        )
        return 200, _json_safe(result)

    def rest_profile_evaluate_review(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            PROFILE_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
            message="current actor cannot evaluate profile review cases",
        )
        now = _parse_optional_now(body)
        for key in ("profile_id", "source_dsn"):
            if body.get(key) in (None, ""):
                raise ValueError(f"{key} is required")
        out = self._with_chat(
            evaluate_profile_consistency,
            profile_id=int(body["profile_id"]),
            source_dsn=str(body["source_dsn"]),
            source_table_name=body.get("source_table_name") or body.get("table_name"),
            subject_user_id=body.get("subject_user_id"),
            now=now,
        )
        return 200, _json_safe(out)

    def rest_profile_list_review_cases(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        subject_user_id = q.get("subject_user_id") or None
        actor = self._current_actor(environ)
        if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
            subject_user_id = self._resolve_actor_bound_id(environ, subject_user_id, field_name="subject_user_id")
        rows = self._with_chat(
            list_profile_review_cases,
            statuses=_statuses_from_query(q),
            profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
            subject_user_id=subject_user_id,
            limit=int(q.get("limit", 100)),
        )
        return 200, {"risk_cases": _json_safe(rows)}

    def rest_profile_get_review_case(self, environ: dict[str, Any], profile_review_case_id: str) -> tuple[int, dict[str, Any]]:
        risk_case = self._with_chat(get_profile_review_case, profile_review_case_id)
        if not risk_case:
            return 404, {"error": {"code": "not_found", "message": "profile review case not found"}}
        self._assert_actor_can_access_owner(environ, risk_case.get("subject_user_id"), field_name="subject_user_id")
        return 200, {"risk_case": _json_safe(risk_case)}

    def rest_profile_list_photo_risk_runs(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        subject_user_id = q.get("subject_user_id") or None
        actor = self._current_actor(environ)
        if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
            subject_user_id = self._resolve_actor_bound_id(environ, subject_user_id, field_name="subject_user_id")
        rows = self._with_chat(
            list_photo_risk_score_runs,
            profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
            subject_user_id=subject_user_id,
            profile_review_case_id=q.get("profile_review_case_id") or None,
            limit=int(q.get("limit", 100)),
        )
        return 200, {"score_runs": _json_safe(rows)}

    def rest_profile_get_photo_risk_run(self, environ: dict[str, Any], score_run_id: int) -> tuple[int, dict[str, Any]]:
        row = self._with_chat(get_photo_risk_score_run, int(score_run_id))
        if not row:
            return 404, {"error": {"code": "not_found", "message": "photo risk score run not found"}}
        self._assert_actor_can_access_owner(environ, row.get("subject_user_id"), field_name="subject_user_id")
        return 200, {"score_run": _json_safe(row)}

    def rest_profile_list_photo_risk_review_queue(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            PROFILE_REVIEW_ROLES,
            message="current actor cannot view the photo risk review queue",
        )
        q = _query_dict(environ)
        rows = self._with_chat(
            list_photo_risk_review_queue,
            statuses=_statuses_from_query(q, key="queue_status"),
            profile_id=int(q["profile_id"]) if q.get("profile_id") is not None else None,
            subject_user_id=q.get("subject_user_id") or None,
            limit=int(q.get("limit", 100)),
        )
        return 200, {"review_queue": _json_safe(rows)}

    def rest_profile_review_case(
        self,
        environ: dict[str, Any],
        profile_review_case_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        resolver_id = self._resolve_operator_actor_id(
            environ,
            body.get("resolver_id"),
            field_name="resolver_id",
            roles=PROFILE_REVIEW_ROLES,
            message="current actor cannot review profile risk cases",
        )
        if body.get("status") in (None, ""):
            raise ValueError("status is required")
        risk_case = self._with_chat(
            review_profile_review_case,
            profile_review_case_id,
            resolver_id,
            status=str(body["status"]),
            applied_action=body.get("applied_action"),
            resolution_note=body.get("resolution_note"),
            now=now,
        )
        return 200, {"risk_case": _json_safe(risk_case)}

    def rest_profile_submit_review_case_appeal(
        self,
        environ: dict[str, Any],
        profile_review_case_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        appellant_id = self._resolve_actor_bound_id(environ, body.get("appellant_id"), field_name="appellant_id")
        if body.get("reason_text") in (None, ""):
            raise ValueError("reason_text is required")
        appeal = self._with_chat(
            submit_profile_review_case_appeal,
            profile_review_case_id,
            appellant_id,
            reason_text=str(body["reason_text"]),
            evidence=body.get("evidence"),
            now=now,
        )
        return 201, {"appeal": _json_safe(appeal)}

    def rest_profile_list_review_case_appeals(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        subject_user_id = q.get("subject_user_id") or None
        actor = self._current_actor(environ)
        if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
            subject_user_id = self._resolve_actor_bound_id(environ, subject_user_id, field_name="subject_user_id")
        rows = self._with_chat(
            list_profile_review_case_appeals,
            statuses=_statuses_from_query(q),
            profile_review_case_id=q.get("profile_review_case_id") or None,
            subject_user_id=subject_user_id,
            limit=int(q.get("limit", 100)),
        )
        return 200, {"appeals": _json_safe(rows)}

    def rest_profile_get_review_case_appeal(self, environ: dict[str, Any], appeal_id: int) -> tuple[int, dict[str, Any]]:
        appeal = self._with_chat(get_profile_review_case_appeal, int(appeal_id))
        if not appeal:
            return 404, {"error": {"code": "not_found", "message": "profile review appeal not found"}}
        self._assert_actor_can_access_owner(environ, appeal.get("subject_user_id"), field_name="subject_user_id")
        return 200, {"appeal": _json_safe(appeal)}

    def rest_profile_review_review_case_appeal(
        self,
        environ: dict[str, Any],
        appeal_id: int,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        resolver_id = self._resolve_operator_actor_id(
            environ,
            body.get("resolver_id"),
            field_name="resolver_id",
            roles=PROFILE_REVIEW_ROLES,
            message="current actor cannot review profile appeals",
        )
        if body.get("appeal_status") in (None, ""):
            raise ValueError("appeal_status is required")
        appeal = self._with_chat(
            review_profile_review_case_appeal,
            int(appeal_id),
            resolver_id,
            appeal_status=str(body["appeal_status"]),
            resolution_note=body.get("resolution_note"),
            now=now,
        )
        return 200, {"appeal": _json_safe(appeal)}

    def rest_user_trust_hub(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        user_id = self._resolve_actor_bound_id(environ, q.get("user_id"), field_name="user_id")
        hub = self._with_chat(
            build_user_trust_hub,
            user_id=user_id,
            profile_id=int(q["profile_id"]) if q.get("profile_id") not in (None, "") else None,
            limit=int(q.get("limit", 20)),
        )
        return 200, {"trust_hub": _json_safe(hub)}

    def rest_mark_cards_read(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        rid = body.get("requester_id")
        rid_int = self._resolve_int_actor_bound_id(
            _environ,
            rid,
            field_name="requester_id",
        )
        card_ids = body.get("card_ids")
        if not isinstance(card_ids, list):
            raise ValueError("card_ids must be a list of card_id strings")
        out = self._with_rec(
            mark_in_app_cards_read,
            requester_id=rid_int,
            card_ids=[str(x) for x in card_ids],
            now=now,
        )
        return 200, {**_json_safe(out), "trace_id": get_trace_id()}

    def rest_mm_create_member(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if "user_key" in kwargs or self._current_actor(environ) is not None:
            kwargs["user_key"] = self._resolve_actor_bound_id(
                environ,
                kwargs.get("user_key"),
                field_name="user_key",
            )
        if now is not None:
            kwargs["now"] = now
        member = self._with_mm(create_pool_member, **kwargs)
        return 201, {"member": _json_safe(member)}

    def rest_mm_get_member(self, environ: dict[str, Any], member_id: str) -> tuple[int, dict[str, Any]]:
        member = self._get_matchmaking_member_for_actor(environ, member_id)
        return 200, {"member": _json_safe(member)}

    def rest_mm_set_status(self, environ: dict[str, Any], member_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        self._get_matchmaking_member_for_actor(environ, member_id)
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if now is not None:
            kwargs["now"] = now
        member = self._with_mm(set_pool_member_status, member_id, **kwargs)
        return 200, {"member": _json_safe(member)}

    def rest_mm_refresh_member(self, environ: dict[str, Any], member_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        self._get_matchmaking_member_for_actor(environ, member_id)
        now = _parse_optional_now(body)
        out = self._with_mm(refresh_pool_member, member_id, now=now)
        return 200, _json_safe(out)

    def rest_mm_refresh_pool(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot refresh the matchmaking pool",
        )
        ids = body.get("member_ids")
        if ids is not None and not isinstance(ids, list):
            raise ValueError("member_ids must be a list")
        payload: dict[str, Any] = {}
        if ids is not None:
            payload["member_ids"] = [str(item) for item in ids]
        now_text = _normalize_optional_now_text(body.get("now"))
        if now_text is not None:
            payload["now"] = now_text
        return self._enqueue_async_job(
            environ,
            target="matchmaking",
            with_fn=self._with_mm,
            enqueue_fn=enqueue_matchmaking_async_job,
            job_type=JOB_REFRESH_ACTIVE_POOL,
            payload=payload,
        )

    def rest_mm_build_pairs(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot build matchmaking pairs",
        )
        payload: dict[str, Any] = {}
        now_text = _normalize_optional_now_text(body.get("now"))
        if now_text is not None:
            payload["now"] = now_text
        return self._enqueue_async_job(
            environ,
            target="matchmaking",
            with_fn=self._with_mm,
            enqueue_fn=enqueue_matchmaking_async_job,
            job_type=JOB_BUILD_MUTUAL_PAIRS,
            payload=payload,
        )

    def rest_mm_open_cases(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot open matchmaking cases",
        )
        payload: dict[str, Any] = {}
        now_text = _normalize_optional_now_text(body.get("now"))
        if now_text is not None:
            payload["now"] = now_text
        raw_case_expires = body.get("case_expires_hours")
        if raw_case_expires is not None:
            payload["case_expires_hours"] = int(raw_case_expires)
        return self._enqueue_async_job(
            environ,
            target="matchmaking",
            with_fn=self._with_mm,
            enqueue_fn=enqueue_matchmaking_async_job,
            job_type=JOB_OPEN_MATCH_CASES,
            payload=payload,
        )

    def rest_mm_get_case(self, environ: dict[str, Any], case_id: str) -> tuple[int, dict[str, Any]]:
        case = self._get_matchmaking_case_for_actor(environ, case_id)
        return 200, {"case": _json_safe(case)}

    def rest_mm_list_cases(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot list matchmaking cases",
        )
        q = _query_dict(environ)
        statuses = _statuses_from_query(q)
        cases = self._with_mm(list_match_cases, statuses=statuses)
        return 200, {"cases": _json_safe(cases)}

    def rest_mm_list_pairs(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot list matchmaking pairs",
        )
        q = _query_dict(environ)
        statuses = _statuses_from_query(q)
        pairs = self._with_mm(list_pairs, statuses=statuses)
        return 200, {"pairs": _json_safe(pairs)}

    def rest_mm_get_pair(self, environ: dict[str, Any], pair_key: str) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect matchmaking pairs",
        )
        pair_key = unquote(pair_key)
        pair = self._with_mm(get_pair, pair_key)
        if not pair:
            return 404, {"error": {"code": "not_found", "message": "pair not found"}}
        return 200, {"pair": _json_safe(pair)}

    def rest_mm_dispatch(self, environ: dict[str, Any], case_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot dispatch matchmaking contacts",
        )
        now = _parse_optional_now(body)
        case = self._with_mm(dispatch_case_contact, case_id, now=now)
        return 200, {"case": _json_safe(case)}

    def rest_mm_reply(self, environ: dict[str, Any], case_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        case = self._get_matchmaking_case_for_actor(environ, case_id)
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        actor = self._current_actor(environ)
        if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
            allowed_member_ids: list[str] = []
            for field_name in ("first_contact_member_id", "second_contact_member_id"):
                member_id = str(case.get(field_name) or "").strip()
                if not member_id:
                    continue
                member = self._with_mm(get_pool_member, member_id)
                if str(member.get("user_key") or "").strip() == actor.actor_id:
                    allowed_member_ids.append(member_id)
            supplied_member_id = str(kwargs.get("member_id") or "").strip()
            if supplied_member_id and supplied_member_id not in allowed_member_ids:
                raise GatewayPermissionError("member_id does not belong to current actor")
            if not supplied_member_id:
                if len(allowed_member_ids) != 1:
                    raise GatewayPermissionError("member_id is required for this actor")
                kwargs["member_id"] = allowed_member_ids[0]
        if now is not None:
            kwargs["now"] = now
        case = self._with_mm(record_case_reply, case_id, **kwargs)
        return 200, {"case": _json_safe(case)}

    def rest_mm_feedback(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if "member_id" in kwargs or self._current_actor(environ) is not None:
            member = self._get_matchmaking_member_for_actor(environ, str(kwargs.get("member_id") or ""))
            kwargs["member_id"] = member["member_id"]
        if now is not None:
            kwargs["now"] = now
        fb = self._with_mm(record_feedback, **kwargs)
        return 200, {"feedback": _json_safe(fb)}

    def rest_mm_close_stale(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot close stale matchmaking cases",
        )
        payload: dict[str, Any] = {}
        now_text = _normalize_optional_now_text(body.get("now"))
        if now_text is not None:
            payload["now"] = now_text
        raw_timeout_days = body.get("timeout_cooling_days")
        if raw_timeout_days is not None:
            payload["timeout_cooling_days"] = int(raw_timeout_days)
        return self._enqueue_async_job(
            environ,
            target="matchmaking",
            with_fn=self._with_mm,
            enqueue_fn=enqueue_matchmaking_async_job,
            job_type=JOB_CLOSE_STALE_CASES,
            payload=payload,
        )

    def rest_get_matchmaking_job(self, environ: dict[str, Any], job_id: str) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect matchmaking jobs",
        )
        return self._get_async_job(
            target="matchmaking",
            with_fn=self._with_mm,
            get_fn=get_matchmaking_async_job,
            job_id=job_id,
        )

    def rest_list_matchmaking_jobs(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect matchmaking jobs",
        )
        return self._list_async_jobs(
            environ,
            target="matchmaking",
            with_fn=self._with_mm,
            list_fn=list_matchmaking_async_jobs,
            summary_fn=summarize_matchmaking_async_jobs,
        )

    def _chat_require_requester(
        self,
        environ: dict[str, Any],
        q: dict[str, str],
        body: dict[str, Any] | None = None,
    ) -> str:
        rid = (q.get("requester_id") or "").strip()
        if not rid and body:
            rid = str(body.get("requester_id") or "").strip()
        return self._resolve_actor_bound_id(environ, rid, field_name="requester_id")

    def rest_chat_create_thread(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot create chat threads",
        )
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if now is not None:
            kwargs["now"] = now
        for key in ("case_id", "relation_key", "participant_a_id", "participant_b_id"):
            if not kwargs.get(key):
                raise ValueError(f"{key} is required")
        thread = self._with_chat(get_or_create_thread, **kwargs)
        return 201, {"thread": _json_safe(thread)}

    def rest_chat_get_thread(self, environ: dict[str, Any], thread_id: str) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = self._chat_require_requester(environ, q)
        thread = self._with_chat(get_thread, thread_id)
        if not thread:
            return 404, {"error": {"code": "not_found", "message": "thread not found"}}
        actor = self._current_actor(environ)
        if requester_id not in (thread["participant_a_id"], thread["participant_b_id"]) and not (
            actor and actor.has_any_role(STAFF_OVERRIDE_ROLES)
        ):
            return 403, {"error": {"code": "forbidden", "message": "requester is not a participant"}}
        return 200, {"thread": _json_safe(thread)}

    def rest_chat_list_messages(self, environ: dict[str, Any], thread_id: str) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = self._chat_require_requester(environ, q)
        limit_raw = q.get("limit") or "50"
        before_raw = q.get("before_message_id")
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 50
        before_id: int | None = None
        if before_raw not in (None, ""):
            try:
                before_id = int(before_raw)
            except ValueError:
                before_id = None
        rows = self._with_chat(
            list_messages, thread_id, requester_id, limit=limit, before_message_id=before_id
        )
        return 200, {"messages": _json_safe(rows)}

    def rest_chat_post_message(self, environ: dict[str, Any], thread_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k not in {"now", "idempotency_key", "client_idempotency_key"}}
        idem = _extract_client_idempotency_key(environ, body)
        kwargs["metadata"] = _augment_chat_message_metadata(environ, kwargs.get("metadata"))
        if idem:
            kwargs["client_msg_id"] = idem
        if now is not None:
            kwargs["now"] = now
        if kwargs.get("body") is None:
            raise ValueError("body is required")
        author_id = self._resolve_actor_bound_id(environ, kwargs.pop("author_id", None), field_name="author_id")
        body_text = kwargs.pop("body")
        msg = self._with_chat(post_message, thread_id, author_id, body_text, **kwargs)
        out: dict[str, Any] = {"message": _json_safe(msg), "trace_id": get_trace_id()}
        if idem:
            out["client_idempotency_key"] = idem
        return 201, out

    def rest_chat_create_assistant_layout(
        self,
        environ: dict[str, Any],
        case_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot create assistant layouts",
        )
        now = _parse_optional_now(body)
        relation_key = body.get("relation_key")
        participant_a_id = body.get("participant_a_id")
        participant_b_id = body.get("participant_b_id")
        agent_id = body.get("agent_id")
        if not relation_key or not participant_a_id or not participant_b_id or not agent_id:
            raise ValueError("relation_key, participant_a_id, participant_b_id, and agent_id are required")
        layout = self._with_chat(
            create_assistant_case_layout,
            case_id=str(case_id),
            relation_key=str(relation_key),
            participant_a_id=str(participant_a_id),
            participant_b_id=str(participant_b_id),
            agent_id=str(agent_id),
            conversation_ids=body.get("conversation_ids"),
            metadata=body.get("metadata"),
            now=now,
        )
        return 201, {"layout": _json_safe(layout), "trace_id": get_trace_id()}

    def rest_chat_list_case_conversations(
        self,
        environ: dict[str, Any],
        case_id: str,
    ) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = self._chat_require_requester(environ, q)
        conversations = self._with_chat(
            list_case_conversations,
            str(case_id),
            requester_id=requester_id,
        )
        return 200, {
            "case_id": case_id,
            "requester_id": requester_id,
            "conversation_count": len(conversations),
            "conversations": _json_safe(conversations),
        }

    def rest_chat_get_conversation(
        self,
        environ: dict[str, Any],
        conversation_id: str,
    ) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = self._chat_require_requester(environ, q)
        conversation = self._with_chat(get_conversation, conversation_id)
        if not conversation:
            return 404, {"error": {"code": "not_found", "message": "conversation not found"}}
        conversations = self._with_chat(
            list_case_conversations,
            str(conversation["case_id"]),
            requester_id=requester_id,
        )
        for item in conversations:
            if str(item["conversation_id"]) == str(conversation_id):
                return 200, {"conversation": _json_safe(item)}
        return 403, {"error": {"code": "forbidden", "message": "requester is not allowed to read this conversation"}}

    def rest_chat_list_conversation_messages(
        self,
        environ: dict[str, Any],
        conversation_id: str,
    ) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = self._chat_require_requester(environ, q)
        limit_raw = q.get("limit") or "50"
        before_raw = q.get("before_message_id")
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 50
        before_id: int | None = None
        if before_raw not in (None, ""):
            try:
                before_id = int(before_raw)
            except ValueError:
                before_id = None
        rows = self._with_chat(
            list_conversation_messages,
            conversation_id,
            requester_id,
            limit=limit,
            before_message_id=before_id,
        )
        return 200, {"messages": _json_safe(rows)}

    def rest_chat_post_conversation_message(
        self,
        environ: dict[str, Any],
        conversation_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k not in {"now", "idempotency_key", "client_idempotency_key"}}
        idem = _extract_client_idempotency_key(environ, body)
        if idem:
            kwargs["client_msg_id"] = idem
        if now is not None:
            kwargs["now"] = now
        if kwargs.get("body") is None:
            raise ValueError("body is required")
        author_id = self._resolve_actor_bound_id(environ, kwargs.pop("author_id", None), field_name="author_id")
        body_text = kwargs.pop("body")
        msg = self._with_chat(post_conversation_message, conversation_id, author_id, body_text, **kwargs)
        out: dict[str, Any] = {"message": _json_safe(msg), "trace_id": get_trace_id()}
        if idem:
            out["client_idempotency_key"] = idem
        return 201, out

    def rest_chat_case_conversation_timeline(
        self,
        environ: dict[str, Any],
        case_id: str,
    ) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = self._chat_require_requester(environ, q)
        limit_raw = q.get("message_limit") or "50"
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 50
        out = self._with_chat(
            build_case_conversation_timeline,
            str(case_id),
            requester_id,
            message_limit=limit,
        )
        return 200, _json_safe(out)

    def _timeline_payload(self, case_id: str, viewer_id: str, *, message_limit: int = 50) -> dict[str, Any]:
        chat_part = self._with_chat(build_chat_timeline, case_id, viewer_id, message_limit=message_limit)
        try:
            case = self._with_mm(get_match_case, case_id)
            evs = self._with_mm(list_match_case_events, case_id)
            mm_part = {"case": _json_safe(case), "events": _json_safe(evs)}
        except ValueError:
            mm_part = {"case": None, "events": []}
        rec_part: dict[str, Any] = {"case": None, "events": []}
        try:
            rc = self._with_rec(recommendation_get_match_case, case_id)
            if rc:
                rev = self._with_rec(recommendation_list_match_case_events, case_id)
                rec_part = {"case": _json_safe(rc), "events": _json_safe(rev)}
        except Exception:
            rec_part = {"case": None, "events": []}
        return {
            "case_id": case_id,
            "viewer_id": viewer_id,
            "chat": _json_safe(chat_part),
            "matchmaking": mm_part,
            "recommendation": rec_part,
        }

    def rest_timeline(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        case_id = (q.get("case_id") or "").strip()
        viewer_id = self._resolve_actor_bound_id(environ, q.get("viewer_id"), field_name="viewer_id")
        if not case_id:
            raise ValueError("case_id is required")
        lim_raw = q.get("message_limit") or "50"
        try:
            mlim = int(lim_raw)
        except ValueError:
            mlim = 50
        return 200, self._timeline_payload(case_id, viewer_id, message_limit=mlim)

    def rest_chat_maintenance_run(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot run chat maintenance",
        )
        po = body.get("persona_limit")
        try:
            plim = int(po) if po is not None else 20
        except (TypeError, ValueError):
            plim = 20
        raw_flush = body.get("flush_outbox")
        flush_opt: bool | None = None
        if isinstance(raw_flush, bool):
            flush_opt = raw_flush
        elif isinstance(raw_flush, str):
            flush_opt = raw_flush.lower() in ("1", "true", "yes")
        sm = body.get("summary_max_threads")
        try:
            smax = int(sm) if sm is not None else 30
        except (TypeError, ValueError):
            smax = 30
        payload: dict[str, Any] = {
            "persona_limit": plim,
            "summary_max_threads": smax,
        }
        if flush_opt is not None:
            payload["flush_outbox"] = flush_opt
        return self._enqueue_async_job(
            environ,
            target="chat",
            with_fn=self._with_chat,
            enqueue_fn=enqueue_chat_async_job,
            job_type=JOB_RUN_CHAT_MAINTENANCE,
            payload=payload,
        )

    def rest_get_chat_job(self, environ: dict[str, Any], job_id: str) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect chat jobs",
        )
        return self._get_async_job(
            target="chat",
            with_fn=self._with_chat,
            get_fn=get_chat_async_job,
            job_id=job_id,
        )

    def rest_list_chat_jobs(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect chat jobs",
        )
        return self._list_async_jobs(
            environ,
            target="chat",
            with_fn=self._with_chat,
            list_fn=list_chat_async_jobs,
            summary_fn=summarize_chat_async_jobs,
        )

    def rest_chat_get_summary(self, environ: dict[str, Any], thread_id: str) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = self._chat_require_requester(environ, q)
        thread = self._with_chat(get_thread, thread_id)
        if not thread:
            return 404, {"error": {"code": "not_found", "message": "thread not found"}}
        actor = self._current_actor(environ)
        if requester_id not in (thread["participant_a_id"], thread["participant_b_id"]) and not (
            actor and actor.has_any_role(STAFF_OVERRIDE_ROLES)
        ):
            return 403, {"error": {"code": "forbidden", "message": "requester is not a participant"}}
        summ = self._with_chat(get_thread_summary, thread_id)
        return 200, {"thread_id": thread_id, "summary": _json_safe(summ)}

    def rest_chat_submit_report(self, environ: dict[str, Any], thread_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        reporter_id = self._resolve_actor_bound_id(environ, body.get("reporter_id"), field_name="reporter_id")
        report_type = body.get("report_type")
        if not report_type:
            raise ValueError("report_type is required")
        out = self._with_chat(
            submit_member_report,
            thread_id,
            reporter_id,
            str(report_type),
            reason_text=body.get("reason_text"),
            message_id=int(body["message_id"]) if body.get("message_id") is not None else None,
            reported_user_id=str(body["reported_user_id"]) if body.get("reported_user_id") is not None else None,
            reported_profile_id=int(body["reported_profile_id"]) if body.get("reported_profile_id") is not None else None,
            reported_source_dsn=body.get("reported_source_dsn") or body.get("source_dsn"),
            reported_source_table_name=body.get("reported_source_table_name") or body.get("source_table_name"),
            evidence=body.get("evidence"),
            now=now,
        )
        return 201, {"report": _json_safe(out.get("report")), "risk_case": _json_safe(out.get("risk_case"))}

    def rest_chat_submit_meeting_feedback(
        self,
        environ: dict[str, Any],
        thread_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        reviewer_id = self._resolve_actor_bound_id(environ, body.get("reviewer_id"), field_name="reviewer_id")
        out = self._with_chat(
            submit_meeting_feedback,
            thread_id,
            reviewer_id,
            counterpart_user_id=str(body["counterpart_user_id"]) if body.get("counterpart_user_id") is not None else None,
            counterpart_profile_id=int(body["counterpart_profile_id"]) if body.get("counterpart_profile_id") is not None else None,
            counterpart_source_dsn=body.get("counterpart_source_dsn") or body.get("source_dsn"),
            counterpart_source_table_name=body.get("counterpart_source_table_name") or body.get("source_table_name"),
            photo_match_status=body.get("photo_match_status") or "unclear",
            profile_consistency_status=body.get("profile_consistency_status") or "unclear",
            income_job_consistency_status=body.get("income_job_consistency_status") or "unclear",
            safety_concern_status=body.get("safety_concern_status") or "none",
            willing_video_status=body.get("willing_video_status") or "unknown",
            willing_offline_status=body.get("willing_offline_status") or "unknown",
            notes=body.get("notes"),
            now=now,
        )
        return 201, _json_safe(out)

    def rest_chat_list_reports(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot list chat reports",
        )
        q = _query_dict(environ)
        limit_raw = q.get("limit") or "100"
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 100
        rows = self._with_chat(
            list_member_reports,
            thread_id=q.get("thread_id") or None,
            risk_case_id=q.get("risk_case_id") or None,
            reported_user_id=q.get("reported_user_id") or None,
            limit=limit,
        )
        return 200, {"reports": _json_safe(rows)}

    def rest_chat_list_meeting_feedback(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        reviewer_id = q.get("reviewer_id") or None
        actor = self._current_actor(environ)
        if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
            reviewer_id = self._resolve_actor_bound_id(environ, reviewer_id, field_name="reviewer_id")
        limit_raw = q.get("limit") or "100"
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 100
        rows = self._with_chat(
            list_meeting_feedback,
            thread_id=q.get("thread_id") or None,
            counterpart_user_id=q.get("counterpart_user_id") or None,
            reviewer_id=reviewer_id,
            limit=limit,
        )
        return 200, {"meeting_feedback": _json_safe(rows)}

    def rest_chat_list_risk_cases(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot list chat risk cases",
        )
        q = _query_dict(environ)
        statuses = _statuses_from_query(q)
        limit_raw = q.get("limit") or "100"
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 100
        rows = self._with_chat(
            list_risk_cases,
            statuses=statuses,
            subject_user_id=q.get("subject_user_id") or None,
            thread_id=q.get("thread_id") or None,
            limit=limit,
        )
        return 200, {"risk_cases": _json_safe(rows)}

    def rest_chat_list_risk_signals(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot list chat risk signals",
        )
        q = _query_dict(environ)
        limit_raw = q.get("limit") or "100"
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 100
        rows = self._with_chat(
            list_risk_signals,
            thread_id=q.get("thread_id") or None,
            subject_user_id=q.get("subject_user_id") or None,
            signal_code=q.get("signal_code") or None,
            limit=limit,
        )
        return 200, {"risk_signals": _json_safe(rows)}

    def rest_chat_record_fraud_network_observation(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
            message="current actor cannot record fraud network observations",
        )
        now = _parse_optional_now(body)
        subject_user_id = body.get("subject_user_id")
        if not subject_user_id:
            raise ValueError("subject_user_id is required")
        out = self._with_chat(
            record_fraud_network_observation,
            subject_user_id=str(subject_user_id),
            source_dsn=body.get("source_dsn") or body.get("source"),
            source_table_name=body.get("source_table_name") or body.get("table_name"),
            profile_id=int(body["profile_id"]) if body.get("profile_id") is not None else None,
            thread_id=body.get("thread_id"),
            case_id=body.get("case_id"),
            risk_case_id=body.get("risk_case_id"),
            report_id=int(body["report_id"]) if body.get("report_id") is not None else None,
            source_type=str(body.get("source_type") or body.get("report_source") or "system_rule"),
            event_type=str(body.get("event_type") or "manual_observation"),
            signal_codes=body.get("signal_codes"),
            evidence=body.get("evidence"),
            message_body=body.get("message_body"),
            now=now,
            evaluate=_normalize_boolish(body.get("evaluate"), default=True),
        )
        return 201, {"observation": _json_safe(out)}

    def rest_chat_evaluate_fraud_network(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
            message="current actor cannot evaluate fraud networks",
        )
        now = _parse_optional_now(body)
        subject_user_id = body.get("subject_user_id")
        if not subject_user_id:
            raise ValueError("subject_user_id is required")
        out = self._with_chat(
            evaluate_fraud_network,
            str(subject_user_id),
            source_dsn=body.get("source_dsn") or body.get("source"),
            source_table_name=body.get("source_table_name") or body.get("table_name"),
            profile_id=int(body["profile_id"]) if body.get("profile_id") is not None else None,
            now=now,
            propagate=_normalize_boolish(body.get("propagate"), default=True),
        )
        return 200, {"fraud_network": _json_safe(out)}

    def rest_chat_list_fraud_networks(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot list fraud networks",
        )
        q = _query_dict(environ)
        limit_raw = q.get("limit") or "100"
        min_score_raw = q.get("minimum_score") or q.get("min_score")
        try:
            limit = int(limit_raw)
        except ValueError:
            limit = 100
        try:
            minimum_score = int(min_score_raw) if min_score_raw not in (None, "") else None
        except ValueError:
            minimum_score = None
        rows = self._with_chat(
            list_fraud_network_profiles,
            review_statuses=_statuses_from_query(q),
            subject_user_id=q.get("subject_user_id") or None,
            minimum_score=minimum_score,
            limit=limit,
        )
        return 200, {"fraud_networks": _json_safe(rows)}

    def rest_chat_get_fraud_network(self, environ: dict[str, Any], subject_user_id: str) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot inspect fraud networks",
        )
        profile = self._with_chat(get_fraud_network_profile, subject_user_id)
        if not profile:
            return 404, {"error": {"code": "not_found", "message": "fraud network not found"}}
        overview = self._with_chat(build_fraud_network_overview, subject_user_id)
        return 200, {"fraud_network": _json_safe(overview)}

    def rest_chat_get_risk_case(self, environ: dict[str, Any], risk_case_id: str) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot inspect chat risk cases",
        )
        try:
            playback = self._with_chat(build_risk_case_playback, risk_case_id)
        except ValueError:
            return 404, {"error": {"code": "not_found", "message": "risk case not found"}}
        return 200, _json_safe(playback)

    def rest_chat_thread_risk_overview(self, environ: dict[str, Any], thread_id: str) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = self._chat_require_requester(environ, q)
        out = self._with_chat(build_thread_risk_overview, thread_id, requester_id)
        return 200, {"risk_overview": _json_safe(out)}

    def rest_chat_review_risk_case(
        self,
        environ: dict[str, Any],
        risk_case_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        resolver_id = self._resolve_operator_actor_id(
            environ,
            body.get("resolver_id"),
            field_name="resolver_id",
            roles=CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot review chat risk cases",
        )
        status = body.get("status")
        if not status:
            raise ValueError("status is required")
        risk_case = self._with_chat(
            review_risk_case,
            risk_case_id,
            resolver_id,
            status=str(status),
            applied_action=body.get("applied_action"),
            resolution_note=body.get("resolution_note"),
            now=now,
        )
        return 200, {"risk_case": _json_safe(risk_case)}

    def rest_chat_batch_review_risk_cases(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        resolver_id = self._resolve_operator_actor_id(
            environ,
            body.get("resolver_id"),
            field_name="resolver_id",
            roles=CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot batch review chat risk cases",
        )
        if body.get("status") in (None, ""):
            raise ValueError("status is required")
        risk_case_ids = body.get("risk_case_ids")
        if not isinstance(risk_case_ids, list):
            raise ValueError("risk_case_ids must be a list")
        out = self._with_chat(
            batch_review_risk_cases,
            risk_case_ids=risk_case_ids,
            resolver_id=resolver_id,
            status=str(body["status"]),
            applied_action=body.get("applied_action"),
            resolution_note=body.get("resolution_note"),
            now=now,
        )
        return 200, _json_safe(out)

    def rest_chat_submit_risk_appeal(
        self,
        environ: dict[str, Any],
        risk_case_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        appellant_id = self._resolve_actor_bound_id(environ, body.get("appellant_id"), field_name="appellant_id")
        if body.get("reason_text") in (None, ""):
            raise ValueError("reason_text is required")
        appeal = self._with_chat(
            submit_risk_appeal,
            risk_case_id,
            appellant_id,
            reason_text=str(body["reason_text"]),
            evidence=body.get("evidence"),
            now=now,
        )
        return 201, {"appeal": _json_safe(appeal)}

    def rest_chat_list_risk_appeals(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot list chat risk appeals",
        )
        q = _query_dict(environ)
        rows = self._with_chat(
            list_risk_appeals,
            statuses=_statuses_from_query(q),
            risk_case_id=q.get("risk_case_id") or None,
            subject_user_id=q.get("subject_user_id") or None,
            limit=int(q.get("limit", 100)),
        )
        return 200, {"appeals": _json_safe(rows)}

    def rest_chat_get_risk_appeal(self, environ: dict[str, Any], appeal_id: int) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot inspect chat risk appeals",
        )
        appeal = self._with_chat(get_risk_appeal, int(appeal_id))
        if not appeal:
            return 404, {"error": {"code": "not_found", "message": "risk appeal not found"}}
        return 200, {"appeal": _json_safe(appeal)}

    def rest_chat_review_risk_appeal(
        self,
        environ: dict[str, Any],
        appeal_id: int,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        resolver_id = self._resolve_operator_actor_id(
            environ,
            body.get("resolver_id"),
            field_name="resolver_id",
            roles=CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot review chat risk appeals",
        )
        if body.get("appeal_status") in (None, ""):
            raise ValueError("appeal_status is required")
        appeal = self._with_chat(
            review_risk_appeal,
            int(appeal_id),
            resolver_id,
            appeal_status=str(body["appeal_status"]),
            resolution_note=body.get("resolution_note"),
            now=now,
        )
        return 200, {"appeal": _json_safe(appeal)}

    def rest_chat_risk_dashboard(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
            message="current actor cannot view the risk dashboard",
        )
        q = _query_dict(environ)
        now = datetime.fromisoformat(q["now"]) if q.get("now") else None
        try:
            days = int(q.get("days", 7))
        except ValueError:
            days = 7
        dashboard = self._with_chat(build_risk_weekly_dashboard, now=now, days=days)
        return 200, {"dashboard": _json_safe(dashboard)}

    def rest_async_job_dashboard(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect the async job dashboard",
        )
        q = _query_dict(environ)
        try:
            limit = int(q.get("limit", 5))
        except ValueError:
            limit = 5
        return 200, self._build_async_job_dashboard(limit=limit)

    def dispatch_rest(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO") or "/"
        path = path.rstrip("/") or "/"

        if path == "/health" and method == "GET":
            return self.handle_health(environ)

        if path == "/v1/search/profiles" and method == "POST":
            return self.rest_search_profiles(environ, _parse_json_body(_read_body(environ)))

        if path == "/v1/ops/async-jobs/dashboard" and method == "GET":
            return self.rest_async_job_dashboard(environ)

        if path == "/v1/discovery/sessions" and method == "POST":
            return self.rest_discovery_create_session(
                environ,
                _parse_json_body(_read_body(environ)),
            )
        m = re.fullmatch(r"/v1/discovery/sessions/([^/]+)/turns", path)
        if m and method == "POST":
            return self.rest_discovery_process_turn(
                environ,
                m.group(1),
                _parse_json_body(_read_body(environ)),
            )
        m = re.fullmatch(r"/v1/discovery/sessions/([^/]+)", path)
        if m and method == "GET":
            return self.rest_discovery_get_session(environ, m.group(1))
        m = re.fullmatch(r"/v1/discovery/profiles/([^/]+)", path)
        if m and method == "GET":
            return self.rest_discovery_get_profile_detail(environ, m.group(1))

        if path == "/v1/verifications/live-video-challenges" and method == "POST":
            return self.rest_verification_create_live_challenge(
                environ,
                _parse_json_body(_read_body(environ)),
            )
        if path == "/v1/verifications/live-video-requests" and method == "POST":
            return self.rest_verification_request_live_video(
                environ,
                _parse_json_body(_read_body(environ)),
            )
        if path == "/v1/verifications/live-video-requests" and method == "GET":
            return self.rest_verification_list_photo_review_requests(environ)
        if path == "/v1/verifications/live-video-submissions" and method == "POST":
            return self.rest_verification_submit_live_video(
                environ,
                _parse_json_body(_read_body(environ, max_bytes=64 * 1024 * 1024)),
            )
        if path == "/v1/verifications/live-video-submissions" and method == "GET":
            return self.rest_verification_list_submissions(environ)
        m = re.fullmatch(r"/v1/verifications/live-video-submissions/([^/]+)/resubmit", path)
        if m and method == "POST":
            return self.rest_verification_resubmit_live_video(
                environ,
                m.group(1),
                _parse_json_body(_read_body(environ, max_bytes=64 * 1024 * 1024)),
            )
        m = re.fullmatch(r"/v1/verifications/live-video-submissions/([^/]+)/review", path)
        if m and method == "POST":
            return self.rest_verification_review_submission(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/verifications/live-video-submissions/([^/]+)", path)
        if m and method == "GET":
            return self.rest_verification_get_submission(environ, m.group(1))
        m = re.fullmatch(r"/v1/verifications/live-video-requests/([^/]+)", path)
        if m and method == "GET":
            return self.rest_verification_get_photo_review_request(environ, m.group(1))
        if path == "/v1/verifications/notifications" and method == "GET":
            return self.rest_verification_list_notifications(environ)
        if path == "/v1/user-center/trust-hub" and method == "GET":
            return self.rest_user_trust_hub(environ)
        if path == "/v1/profile-verifications/policies" and method == "GET":
            return self.rest_profile_verification_policies(environ)
        if path == "/v1/profile-verifications/submissions" and method == "POST":
            return self.rest_profile_submit_field_verification(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/profile-verifications/submissions" and method == "GET":
            return self.rest_profile_list_field_verifications(environ)
        m = re.fullmatch(r"/v1/profile-verifications/submissions/([^/]+)/resubmit", path)
        if m and method == "POST":
            return self.rest_profile_resubmit_field_verification(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/profile-verifications/submissions/([^/]+)/dispute", path)
        if m and method == "POST":
            return self.rest_profile_dispute_field_verification(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/profile-verifications/submissions/([^/]+)/review", path)
        if m and method == "POST":
            return self.rest_profile_review_field_verification(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/profile-verifications/submissions/([^/]+)", path)
        if m and method == "GET":
            return self.rest_profile_get_field_verification(environ, m.group(1))
        if path == "/v1/profile-verifications/expire-due" and method == "POST":
            return self.rest_profile_expire_due_field_verifications(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/profile-review/risk-cases/evaluate" and method == "POST":
            return self.rest_profile_evaluate_review(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/profile-review/risk-cases" and method == "GET":
            return self.rest_profile_list_review_cases(environ)
        if path == "/v1/profile-review/photo-risk/runs" and method == "GET":
            return self.rest_profile_list_photo_risk_runs(environ)
        if path == "/v1/profile-review/photo-risk/review-queue" and method == "GET":
            return self.rest_profile_list_photo_risk_review_queue(environ)
        if path == "/v1/profile-review/appeals" and method == "GET":
            return self.rest_profile_list_review_case_appeals(environ)
        m = re.fullmatch(r"/v1/profile-review/risk-cases/([^/]+)/review", path)
        if m and method == "POST":
            return self.rest_profile_review_case(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/profile-review/risk-cases/([^/]+)/appeals", path)
        if m and method == "POST":
            return self.rest_profile_submit_review_case_appeal(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/profile-review/appeals/([^/]+)/review", path)
        if m and method == "POST":
            return self.rest_profile_review_review_case_appeal(environ, int(m.group(1)), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/profile-review/appeals/([^/]+)", path)
        if m and method == "GET":
            return self.rest_profile_get_review_case_appeal(environ, int(m.group(1)))
        m = re.fullmatch(r"/v1/profile-review/risk-cases/([^/]+)", path)
        if m and method == "GET":
            return self.rest_profile_get_review_case(environ, m.group(1))
        m = re.fullmatch(r"/v1/profile-review/photo-risk/runs/([^/]+)", path)
        if m and method == "GET":
            return self.rest_profile_get_photo_risk_run(environ, int(m.group(1)))

        # /v1/recommendation/...
        m = re.fullmatch(r"/v1/recommendation/subscriptions/([^/]+)", path)
        if m and method == "GET":
            return self.rest_get_subscription(environ, m.group(1))
        if path == "/v1/recommendation/subscriptions" and method == "POST":
            return self.rest_create_subscription(environ, _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/recommendation/subscriptions/([^/]+)/overrides", path)
        if m and method == "PATCH":
            return self.rest_patch_overrides(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/recommendation/subscriptions/([^/]+)/refresh", path)
        if m and method == "POST":
            return self.rest_refresh_subscription(environ, m.group(1), _parse_json_body(_read_body(environ)))
        if path == "/v1/recommendation/subscriptions/refresh-due" and method == "POST":
            return self.rest_refresh_due(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/recommendation/jobs" and method == "GET":
            return self.rest_list_recommendation_jobs(environ)
        m = re.fullmatch(r"/v1/recommendation/jobs/([^/]+)", path)
        if m and method == "GET":
            return self.rest_get_recommendation_job(environ, m.group(1))
        m = re.fullmatch(r"/v1/recommendation/subscriptions/([^/]+)/recommendations", path)
        if m and method == "GET":
            return self.rest_list_recommendations(environ, m.group(1))
        m = re.fullmatch(r"/v1/recommendation/subscriptions/([^/]+)/runs", path)
        if m and method == "GET":
            return self.rest_list_runs(environ, m.group(1))
        if path == "/v1/recommendation/cards/read" and method == "POST":
            return self.rest_mark_cards_read(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/recommendation/cards" and method == "GET":
            return self.rest_list_cards(environ)
        if path == "/v1/recommendation/deliver" and method == "POST":
            return self.rest_deliver(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/recommendation/actions" and method == "POST":
            return self.rest_record_action(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/recommendation/reviews" and method == "POST":
            return self.rest_record_review(environ, _parse_json_body(_read_body(environ)))

        # /v1/matchmaking/...
        if path == "/v1/matchmaking/members" and method == "POST":
            return self.rest_mm_create_member(environ, _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/matchmaking/members/([^/]+)/status", path)
        if m and method == "PATCH":
            return self.rest_mm_set_status(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/matchmaking/members/([^/]+)/refresh", path)
        if m and method == "POST":
            return self.rest_mm_refresh_member(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/matchmaking/members/([^/]+)", path)
        if m and method == "GET":
            return self.rest_mm_get_member(environ, m.group(1))
        if path == "/v1/matchmaking/pool/refresh" and method == "POST":
            return self.rest_mm_refresh_pool(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/matchmaking/jobs" and method == "GET":
            return self.rest_list_matchmaking_jobs(environ)
        m = re.fullmatch(r"/v1/matchmaking/jobs/([^/]+)", path)
        if m and method == "GET":
            return self.rest_get_matchmaking_job(environ, m.group(1))
        if path == "/v1/matchmaking/pairs/build" and method == "POST":
            return self.rest_mm_build_pairs(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/matchmaking/pairs" and method == "GET":
            return self.rest_mm_list_pairs(environ)
        m = re.fullmatch(r"/v1/matchmaking/pairs/(.+)", path)
        if m and method == "GET":
            return self.rest_mm_get_pair(environ, m.group(1))
        if path == "/v1/matchmaking/cases/open" and method == "POST":
            return self.rest_mm_open_cases(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/matchmaking/cases/close-stale" and method == "POST":
            return self.rest_mm_close_stale(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/matchmaking/cases" and method == "GET":
            return self.rest_mm_list_cases(environ)
        m = re.fullmatch(r"/v1/matchmaking/cases/([^/]+)/dispatch", path)
        if m and method == "POST":
            return self.rest_mm_dispatch(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/matchmaking/cases/([^/]+)/reply", path)
        if m and method == "POST":
            return self.rest_mm_reply(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/matchmaking/cases/([^/]+)", path)
        if m and method == "GET":
            return self.rest_mm_get_case(environ, m.group(1))
        if path == "/v1/matchmaking/feedback" and method == "POST":
            return self.rest_mm_feedback(environ, _parse_json_body(_read_body(environ)))

        if path == "/v1/timeline" and method == "GET":
            return self.rest_timeline(environ)

        # /v2/chat/...
        m = re.fullmatch(r"/v2/chat/cases/([^/]+)/assistant-layout", path)
        if m and method == "POST":
            return self.rest_chat_create_assistant_layout(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v2/chat/cases/([^/]+)/conversations", path)
        if m and method == "GET":
            return self.rest_chat_list_case_conversations(environ, m.group(1))
        m = re.fullmatch(r"/v2/chat/cases/([^/]+)/timeline", path)
        if m and method == "GET":
            return self.rest_chat_case_conversation_timeline(environ, m.group(1))
        m = re.fullmatch(r"/v2/chat/conversations/([^/]+)/messages", path)
        if m and method == "POST":
            return self.rest_chat_post_conversation_message(environ, m.group(1), _parse_json_body(_read_body(environ)))
        if m and method == "GET":
            return self.rest_chat_list_conversation_messages(environ, m.group(1))
        m = re.fullmatch(r"/v2/chat/conversations/([^/]+)", path)
        if m and method == "GET":
            return self.rest_chat_get_conversation(environ, m.group(1))

        # /v1/chat/...
        if path == "/v1/chat/maintenance/run" and method == "POST":
            return self.rest_chat_maintenance_run(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/chat/jobs" and method == "GET":
            return self.rest_list_chat_jobs(environ)
        m = re.fullmatch(r"/v1/chat/jobs/([^/]+)", path)
        if m and method == "GET":
            return self.rest_get_chat_job(environ, m.group(1))
        if path == "/v1/chat/threads" and method == "POST":
            return self.rest_chat_create_thread(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/chat/reports" and method == "GET":
            return self.rest_chat_list_reports(environ)
        if path == "/v1/chat/meeting-feedback" and method == "GET":
            return self.rest_chat_list_meeting_feedback(environ)
        if path == "/v1/chat/risk-cases" and method == "GET":
            return self.rest_chat_list_risk_cases(environ)
        if path == "/v1/chat/risk-cases/batch-review" and method == "POST":
            return self.rest_chat_batch_review_risk_cases(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/chat/risk-signals" and method == "GET":
            return self.rest_chat_list_risk_signals(environ)
        if path == "/v1/chat/fraud-networks" and method == "GET":
            return self.rest_chat_list_fraud_networks(environ)
        if path == "/v1/chat/fraud-networks/observations" and method == "POST":
            return self.rest_chat_record_fraud_network_observation(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/chat/fraud-networks/evaluate" and method == "POST":
            return self.rest_chat_evaluate_fraud_network(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/chat/risk-appeals" and method == "GET":
            return self.rest_chat_list_risk_appeals(environ)
        if path == "/v1/chat/risk-dashboard/weekly" and method == "GET":
            return self.rest_chat_risk_dashboard(environ)
        m = re.fullmatch(r"/v1/chat/risk-cases/([^/]+)/review", path)
        if m and method == "POST":
            return self.rest_chat_review_risk_case(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/chat/risk-cases/([^/]+)/appeals", path)
        if m and method == "POST":
            return self.rest_chat_submit_risk_appeal(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/chat/risk-cases/([^/]+)", path)
        if m and method == "GET":
            return self.rest_chat_get_risk_case(environ, m.group(1))
        m = re.fullmatch(r"/v1/chat/risk-appeals/([^/]+)", path)
        if m and method == "GET":
            return self.rest_chat_get_risk_appeal(environ, int(m.group(1)))
        m = re.fullmatch(r"/v1/chat/risk-appeals/([^/]+)/review", path)
        if m and method == "POST":
            return self.rest_chat_review_risk_appeal(environ, int(m.group(1)), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/chat/fraud-networks/([^/]+)", path)
        if m and method == "GET":
            return self.rest_chat_get_fraud_network(environ, unquote(m.group(1)))
        m = re.fullmatch(r"/v1/chat/threads/([^/]+)/risk-overview", path)
        if m and method == "GET":
            return self.rest_chat_thread_risk_overview(environ, m.group(1))
        m = re.fullmatch(r"/v1/chat/threads/([^/]+)/summary", path)
        if m and method == "GET":
            return self.rest_chat_get_summary(environ, m.group(1))
        m = re.fullmatch(r"/v1/chat/threads/([^/]+)/reports", path)
        if m and method == "POST":
            return self.rest_chat_submit_report(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/chat/threads/([^/]+)/meeting-feedback", path)
        if m and method == "POST":
            return self.rest_chat_submit_meeting_feedback(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/chat/threads/([^/]+)/messages", path)
        if m and method == "POST":
            return self.rest_chat_post_message(environ, m.group(1), _parse_json_body(_read_body(environ)))
        if m and method == "GET":
            return self.rest_chat_list_messages(environ, m.group(1))
        m = re.fullmatch(r"/v1/chat/threads/([^/]+)", path)
        if m and method == "GET":
            return self.rest_chat_get_thread(environ, m.group(1))

        return 404, {"error": {"code": "not_found", "message": f"No route for {method} {path}"}}

    # --- JSON-RPC 2.0 ---

    def dispatch_jsonrpc(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            raw = _read_body(environ)
            req = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
            return 400, {"jsonrpc": "2.0", "error": {"code": -32700, "message": str(e)}, "id": None}
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
        p = {k: v for k, v in params.items() if k != "now"}
        if now is not None:
            p["now"] = now

        try:
            result = self._jsonrpc_call(environ, method, p)
        except ValueError as e:
            return 200, {"jsonrpc": "2.0", "error": {"code": -32602, "message": str(e)}, "id": rpc_id}
        except GatewayPermissionError as e:
            return 200, {"jsonrpc": "2.0", "error": {"code": -32001, "message": str(e)}, "id": rpc_id}
        except Exception as e:  # noqa: BLE001 — surface as application error
            return 200, {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}, "id": rpc_id}

        if rpc_id is None:
            return 204, {}
        return 200, {"jsonrpc": "2.0", "result": _json_safe(result), "id": rpc_id}

    def _jsonrpc_call(self, environ: dict[str, Any], method: str, p: dict[str, Any]) -> Any:
        if method == "search.search_profiles":
            return partner_search_profiles(
                source=p.get("source") or p.get("sources"),
                criteria=p.get("criteria") or {},
                self_profile=p.get("self_profile"),
                self_id=p.get("self_id"),
                table_name=p.get("table_name"),
                photos_table_name=p.get("photos_table_name"),
                limit=int(p.get("limit", 10)),
                photo_preview_count=int(p.get("photo_preview_count", 0)),
                include_source=_normalize_boolish(p.get("include_source"), False),
                include_text=_normalize_boolish(p.get("include_text"), False),
                moderation_dsn=self._chat_dsn,
                include_moderation_blocked=_normalize_boolish(p.get("include_moderation_blocked"), False),
            )
        if method == "ops.get_async_job_dashboard":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot inspect the async job dashboard",
            )
            try:
                limit = int(p.get("limit", 5))
            except (TypeError, ValueError):
                limit = 5
            return self._build_async_job_dashboard(limit=limit)
        if method == "verification.submit_live_video":
            user_id = self._resolve_actor_bound_id(environ, p.get("user_id"), field_name="user_id")
            return self._with_chat(
                submit_live_video_verification,
                user_id=user_id,
                video_base64=str(p.get("video_base64") or p.get("video_bytes_base64") or ""),
                file_name=str(p.get("file_name") or p.get("filename") or ""),
                submission_id=p.get("submission_id"),
                content_type=p.get("content_type"),
                profile_id=int(p["profile_id"]) if p.get("profile_id") is not None else None,
                source_dsn=p.get("source_dsn") or p.get("source"),
                source_table_name=p.get("source_table_name") or p.get("table_name"),
                challenge_token=p.get("challenge_token"),
                challenge_phrase=p.get("challenge_phrase"),
                metadata=p.get("metadata"),
                now=p.get("now"),
            )
        if method == "verification.request_live_video":
            self._require_roles(
                environ,
                VERIFICATION_REVIEW_ROLES | CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot request live video verification",
            )
            return self._with_chat(
                request_live_video_verification,
                user_id=str(p["user_id"]),
                profile_id=int(p["profile_id"]) if p.get("profile_id") is not None else None,
                source_dsn=p.get("source_dsn") or p.get("source"),
                source_table_name=p.get("source_table_name") or p.get("table_name"),
                request_source=str(p.get("request_source") or "risk_case_review"),
                request_reason=p.get("request_reason") or p.get("reason_text"),
                signal_codes=p.get("signal_codes") or p.get("reason_codes"),
                risk_case_id=p.get("risk_case_id"),
                report_ids=p.get("report_ids"),
                requested_by=self._resolve_optional_operator_actor_id(
                    environ,
                    p.get("requested_by") or p.get("resolver_id"),
                    field_name="requested_by",
                    roles=VERIFICATION_REVIEW_ROLES | CHAT_RISK_REVIEW_ROLES,
                    message="current actor cannot request live video verification",
                ),
                due_at=p.get("due_at"),
                metadata=p.get("metadata"),
                now=p.get("now"),
            )
        if method == "verification.create_live_challenge":
            user_id = self._resolve_actor_bound_id(environ, p.get("user_id"), field_name="user_id")
            return create_live_video_verification_challenge(
                user_id=user_id,
                profile_id=int(p["profile_id"]) if p.get("profile_id") is not None else None,
                challenge_actions=p.get("challenge_actions") or p.get("required_actions"),
                challenge_action_pool=p.get("challenge_action_pool") or p.get("allowed_actions"),
                action_count=int(p.get("action_count", 3)),
                now=p.get("now"),
            )
        if method == "verification.list_submissions":
            user_id = str(p["user_id"]) if p.get("user_id") is not None else None
            actor = self._current_actor(environ)
            if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
                user_id = self._resolve_actor_bound_id(environ, user_id, field_name="user_id")
            return self._with_chat(
                list_verification_submissions,
                user_id=user_id,
                statuses=p.get("statuses") or p.get("status"),
                profile_id=int(p["profile_id"]) if p.get("profile_id") is not None else None,
                limit=int(p.get("limit", 100)),
            )
        if method == "verification.list_photo_review_requests":
            user_id = str(p["user_id"]) if p.get("user_id") is not None else None
            actor = self._current_actor(environ)
            if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
                user_id = self._resolve_actor_bound_id(environ, user_id, field_name="user_id")
            return self._with_chat(
                list_photo_review_requests,
                user_id=user_id,
                statuses=p.get("statuses") or p.get("status"),
                profile_id=int(p["profile_id"]) if p.get("profile_id") is not None else None,
                limit=int(p.get("limit", 100)),
            )
        if method == "verification.get_submission":
            submission = self._with_chat(get_verification_submission, str(p["submission_id"]))
            self._assert_actor_can_access_owner(environ, (submission or {}).get("user_id"), field_name="user_id")
            return submission
        if method == "verification.list_notifications":
            user_id = str(p["user_id"]) if p.get("user_id") is not None else None
            actor = self._current_actor(environ)
            if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
                user_id = self._resolve_actor_bound_id(environ, user_id, field_name="user_id")
            return self._with_chat(
                list_verification_notifications,
                submission_id=str(p["submission_id"]) if p.get("submission_id") is not None else None,
                user_id=user_id,
                notification_types=p.get("types") or p.get("type"),
                limit=int(p.get("limit", 100)),
            )
        if method == "verification.resubmit_live_video":
            user_id = self._resolve_actor_bound_id(environ, p.get("user_id"), field_name="user_id")
            return self._with_chat(
                resubmit_live_video_verification,
                str(p["submission_id"]),
                user_id=user_id,
                video_base64=str(p.get("video_base64") or p.get("video_bytes_base64") or ""),
                file_name=str(p.get("file_name") or p.get("filename") or ""),
                content_type=p.get("content_type"),
                challenge_token=p.get("challenge_token"),
                challenge_phrase=p.get("challenge_phrase"),
                metadata=p.get("metadata"),
                now=p.get("now"),
            )
        if method == "verification.review_submission":
            reviewer_id = self._resolve_operator_actor_id(
                environ,
                p.get("reviewer_id"),
                field_name="reviewer_id",
                roles=VERIFICATION_REVIEW_ROLES,
                message="current actor cannot review live video submissions",
            )
            return self._with_chat(
                review_live_video_verification,
                str(p["submission_id"]),
                reviewer_id,
                decision=str(p["decision"]),
                review_note=p.get("review_note"),
                liveness_result=p.get("liveness_result"),
                face_match_result=p.get("face_match_result"),
                profile_consistency_result=p.get("profile_consistency_result"),
                metadata=p.get("metadata"),
                now=p.get("now"),
            )
        if method == "recommendation.get_subscription":
            self._get_recommendation_subscription_for_actor(environ, p["subscription_id"])
            return self._with_rec(get_subscription, p["subscription_id"])
        if method == "recommendation.create_subscription":
            p2 = dict(p)
            if p2.get("requester_id") is not None or self._current_actor(environ) is not None:
                p2["requester_id"] = self._resolve_int_actor_bound_id(
                    environ,
                    p2.get("requester_id"),
                    field_name="requester_id",
                )
            return self._with_rec(create_subscription, **p2)
        if method == "recommendation.update_subscription_overrides":
            self._get_recommendation_subscription_for_actor(environ, p["subscription_id"])
            return self._with_rec(update_subscription_overrides, p["subscription_id"], p.get("overrides"), now=p.get("now"))
        if method == "recommendation.refresh_subscription":
            self._get_recommendation_subscription_for_actor(environ, p["subscription_id"])
            return self._with_rec(refresh_subscription, p["subscription_id"], now=p.get("now"))
        if method == "recommendation.refresh_due_subscriptions":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot refresh due recommendation subscriptions",
            )
            ids = p.get("subscription_ids")
            if ids is not None and not isinstance(ids, list):
                raise ValueError("subscription_ids must be a list")
            payload: dict[str, Any] = {}
            if ids is not None:
                payload["subscription_ids"] = [str(item) for item in ids]
            now_text = _normalize_optional_now_text(p.get("now"))
            if now_text is not None:
                payload["now"] = now_text
            actor = self._current_actor(environ)
            job = self._with_rec(
                enqueue_recommendation_async_job,
                job_type=JOB_REFRESH_DUE_SUBSCRIPTIONS,
                payload=payload,
                created_by=actor.actor_id if actor is not None else None,
                trace_id=get_trace_id(),
            )
            return self._job_payload("recommendation", job)
        if method == "recommendation.get_async_job":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot inspect recommendation jobs",
            )
            job = self._with_rec(get_recommendation_async_job, str(p["job_id"]))
            if not job:
                raise ValueError("job not found")
            return self._job_payload("recommendation", job)
        if method == "recommendation.list_async_jobs":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot inspect recommendation jobs",
            )
            statuses = p.get("statuses")
            if statuses is not None and not isinstance(statuses, list):
                raise ValueError("statuses must be a list")
            limit = int(p.get("limit", 50))
            jobs = self._with_rec(list_recommendation_async_jobs, statuses=statuses, limit=limit)
            summary = self._with_rec(summarize_recommendation_async_jobs)
            return self._job_collection_payload("recommendation", jobs, summary)
        if method == "recommendation.list_recommendations_for_subscription":
            self._get_recommendation_subscription_for_actor(environ, p["subscription_id"])
            return self._with_rec(list_recommendations_for_subscription, p["subscription_id"])
        if method == "recommendation.list_search_runs_for_subscription":
            self._get_recommendation_subscription_for_actor(environ, p["subscription_id"])
            return self._with_rec(list_search_runs_for_subscription, p["subscription_id"])
        if method == "recommendation.list_in_app_cards":
            requester_id = p.get("requester_id")
            rid = None
            if requester_id is not None or self._current_actor(environ) is not None:
                rid = self._resolve_int_actor_bound_id(
                    environ,
                    requester_id,
                    field_name="requester_id",
                )
            return self._with_rec(
                list_in_app_cards,
                requester_id=rid,
                unread_only=bool(p.get("unread_only", False)),
            )
        if method == "recommendation.deliver_in_app_recommendations":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot deliver recommendation cards",
            )
            payload: dict[str, Any] = {}
            now_text = _normalize_optional_now_text(p.get("now"))
            if now_text is not None:
                payload["now"] = now_text
            actor = self._current_actor(environ)
            job = self._with_rec(
                enqueue_recommendation_async_job,
                job_type=JOB_DELIVER_IN_APP_RECOMMENDATIONS,
                payload=payload,
                created_by=actor.actor_id if actor is not None else None,
                trace_id=get_trace_id(),
            )
            return self._job_payload("recommendation", job)
        if method == "recommendation.record_recommendation_action":
            p2 = {k: v for k, v in p.items() if k not in {"idempotency_key", "client_idempotency_key"}}
            subscription = self._get_recommendation_subscription_for_actor(environ, str(p2.get("subscription_id") or ""))
            ck = p.get("client_idempotency_key") or p.get("idempotency_key")
            if ck is not None and str(ck).strip():
                p2["client_idempotency_key"] = str(ck).strip()[:191]
            p2["subscription_id"] = subscription["subscription_id"]
            actor = self._current_actor(environ)
            if actor is not None:
                p2["actor_id"] = actor.actor_id
            return self._with_rec(record_recommendation_action, **p2)
        if method == "recommendation.record_user_review":
            p2 = {k: v for k, v in p.items() if k not in {"idempotency_key", "client_idempotency_key"}}
            subscription = self._get_recommendation_subscription_for_actor(environ, str(p2.get("subscription_id") or ""))
            ck = p.get("client_idempotency_key") or p.get("idempotency_key")
            if ck is not None and str(ck).strip():
                p2["client_idempotency_key"] = str(ck).strip()[:191]
            p2["subscription_id"] = subscription["subscription_id"]
            actor = self._current_actor(environ)
            if actor is not None:
                p2["actor_id"] = actor.actor_id
            return self._with_rec(record_user_review, **p2)
        if method == "recommendation.mark_in_app_cards_read":
            rid = self._resolve_int_actor_bound_id(
                environ,
                p.get("requester_id"),
                field_name="requester_id",
            )
            card_ids = p.get("card_ids")
            if not isinstance(card_ids, list):
                raise ValueError("card_ids must be a list")
            return self._with_rec(
                mark_in_app_cards_read,
                requester_id=rid,
                card_ids=[str(x) for x in card_ids],
                now=p.get("now"),
            )

        if method == "matchmaking.create_pool_member":
            p2 = dict(p)
            if p2.get("user_key") is not None or self._current_actor(environ) is not None:
                p2["user_key"] = self._resolve_actor_bound_id(
                    environ,
                    p2.get("user_key"),
                    field_name="user_key",
                )
            return self._with_mm(create_pool_member, **p2)
        if method == "matchmaking.get_pool_member":
            return self._get_matchmaking_member_for_actor(environ, p["member_id"])
        if method == "matchmaking.set_pool_member_status":
            p2 = dict(p)
            mid = p2.pop("member_id")
            self._get_matchmaking_member_for_actor(environ, mid)
            return self._with_mm(set_pool_member_status, mid, **p2)
        if method == "matchmaking.refresh_pool_member":
            self._get_matchmaking_member_for_actor(environ, p["member_id"])
            return self._with_mm(refresh_pool_member, p["member_id"], now=p.get("now"))
        if method == "matchmaking.refresh_active_pool":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot refresh the matchmaking pool",
            )
            ids = p.get("member_ids")
            if ids is not None and not isinstance(ids, list):
                raise ValueError("member_ids must be a list")
            payload: dict[str, Any] = {}
            if ids is not None:
                payload["member_ids"] = [str(item) for item in ids]
            now_text = _normalize_optional_now_text(p.get("now"))
            if now_text is not None:
                payload["now"] = now_text
            actor = self._current_actor(environ)
            job = self._with_mm(
                enqueue_matchmaking_async_job,
                job_type=JOB_REFRESH_ACTIVE_POOL,
                payload=payload,
                created_by=actor.actor_id if actor is not None else None,
                trace_id=get_trace_id(),
            )
            return self._job_payload("matchmaking", job)
        if method == "matchmaking.build_mutual_pairs":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot build matchmaking pairs",
            )
            payload: dict[str, Any] = {}
            now_text = _normalize_optional_now_text(p.get("now"))
            if now_text is not None:
                payload["now"] = now_text
            actor = self._current_actor(environ)
            job = self._with_mm(
                enqueue_matchmaking_async_job,
                job_type=JOB_BUILD_MUTUAL_PAIRS,
                payload=payload,
                created_by=actor.actor_id if actor is not None else None,
                trace_id=get_trace_id(),
            )
            return self._job_payload("matchmaking", job)
        if method == "matchmaking.open_match_cases":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot open matchmaking cases",
            )
            payload: dict[str, Any] = {}
            now_text = _normalize_optional_now_text(p.get("now"))
            if now_text is not None:
                payload["now"] = now_text
            if p.get("case_expires_hours") is not None:
                payload["case_expires_hours"] = int(p["case_expires_hours"])
            actor = self._current_actor(environ)
            job = self._with_mm(
                enqueue_matchmaking_async_job,
                job_type=JOB_OPEN_MATCH_CASES,
                payload=payload,
                created_by=actor.actor_id if actor is not None else None,
                trace_id=get_trace_id(),
            )
            return self._job_payload("matchmaking", job)
        if method == "matchmaking.get_async_job":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot inspect matchmaking jobs",
            )
            job = self._with_mm(get_matchmaking_async_job, str(p["job_id"]))
            if not job:
                raise ValueError("job not found")
            return self._job_payload("matchmaking", job)
        if method == "matchmaking.list_async_jobs":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot inspect matchmaking jobs",
            )
            statuses = p.get("statuses")
            if statuses is not None and not isinstance(statuses, list):
                raise ValueError("statuses must be a list")
            limit = int(p.get("limit", 50))
            jobs = self._with_mm(list_matchmaking_async_jobs, statuses=statuses, limit=limit)
            summary = self._with_mm(summarize_matchmaking_async_jobs)
            return self._job_collection_payload("matchmaking", jobs, summary)
        if method == "matchmaking.get_match_case":
            return self._get_matchmaking_case_for_actor(environ, p["case_id"])
        if method == "matchmaking.list_match_cases":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot list matchmaking cases",
            )
            return self._with_mm(list_match_cases, statuses=p.get("statuses"))
        if method == "matchmaking.list_pairs":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot list matchmaking pairs",
            )
            return self._with_mm(list_pairs, statuses=p.get("statuses"))
        if method == "matchmaking.get_pair":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot inspect matchmaking pairs",
            )
            return self._with_mm(get_pair, p["pair_key"])
        if method == "matchmaking.dispatch_case_contact":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot dispatch matchmaking contacts",
            )
            return self._with_mm(dispatch_case_contact, p["case_id"], now=p.get("now"))
        if method == "matchmaking.record_case_reply":
            p2 = dict(p)
            cid = p2.pop("case_id")
            case = self._get_matchmaking_case_for_actor(environ, cid)
            actor = self._current_actor(environ)
            if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
                allowed_member_ids: list[str] = []
                for field_name in ("first_contact_member_id", "second_contact_member_id"):
                    member_id = str(case.get(field_name) or "").strip()
                    if not member_id:
                        continue
                    member = self._with_mm(get_pool_member, member_id)
                    if str(member.get("user_key") or "").strip() == actor.actor_id:
                        allowed_member_ids.append(member_id)
                supplied_member_id = str(p2.get("member_id") or "").strip()
                if supplied_member_id and supplied_member_id not in allowed_member_ids:
                    raise GatewayPermissionError("member_id does not belong to current actor")
                if not supplied_member_id:
                    if len(allowed_member_ids) != 1:
                        raise GatewayPermissionError("member_id is required for this actor")
                    p2["member_id"] = allowed_member_ids[0]
            return self._with_mm(record_case_reply, cid, **p2)
        if method == "matchmaking.record_feedback":
            p2 = dict(p)
            if p2.get("member_id") is not None or self._current_actor(environ) is not None:
                member = self._get_matchmaking_member_for_actor(environ, str(p2.get("member_id") or ""))
                p2["member_id"] = member["member_id"]
            return self._with_mm(record_feedback, **p2)
        if method == "matchmaking.close_stale_cases":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot close stale matchmaking cases",
            )
            payload: dict[str, Any] = {}
            now_text = _normalize_optional_now_text(p.get("now"))
            if now_text is not None:
                payload["now"] = now_text
            if p.get("timeout_cooling_days") is not None:
                payload["timeout_cooling_days"] = int(p["timeout_cooling_days"])
            actor = self._current_actor(environ)
            job = self._with_mm(
                enqueue_matchmaking_async_job,
                job_type=JOB_CLOSE_STALE_CASES,
                payload=payload,
                created_by=actor.actor_id if actor is not None else None,
                trace_id=get_trace_id(),
            )
            return self._job_payload("matchmaking", job)

        if method == "chat.get_thread":
            requester_id = self._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
            thread = self._with_chat(get_thread, p["thread_id"])
            if not thread:
                raise ValueError("thread not found")
            actor = self._current_actor(environ)
            if requester_id not in (thread["participant_a_id"], thread["participant_b_id"]) and not (
                actor and actor.has_any_role(STAFF_OVERRIDE_ROLES)
            ):
                raise GatewayPermissionError("requester is not a participant")
            return thread
        if method == "chat.get_or_create_thread":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot create chat threads",
            )
            return self._with_chat(get_or_create_thread, **p)
        if method == "chat.list_messages":
            bm = p.get("before_message_id")
            if bm is not None:
                bm = int(bm)
            requester_id = self._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
            return self._with_chat(
                list_messages,
                p["thread_id"],
                requester_id,
                limit=int(p.get("limit", 50)),
                before_message_id=bm,
            )
        if method == "chat.post_message":
            p2 = {k: v for k, v in p.items() if k not in {"idempotency_key", "client_idempotency_key"}}
            ck = p.get("client_idempotency_key") or p.get("idempotency_key")
            p2["metadata"] = _augment_chat_message_metadata(environ, p2.get("metadata"))
            if ck is not None and str(ck).strip():
                p2["client_msg_id"] = str(ck).strip()[:191]
            tid = p2.pop("thread_id")
            author_id = self._resolve_actor_bound_id(environ, p2.pop("author_id", None), field_name="author_id")
            body_text = p2.pop("body")
            return self._with_chat(post_message, tid, author_id, body_text, **p2)
        if method == "chat.create_assistant_layout":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot create assistant layouts",
            )
            return self._with_chat(
                create_assistant_case_layout,
                case_id=str(p["case_id"]),
                relation_key=str(p["relation_key"]),
                participant_a_id=str(p["participant_a_id"]),
                participant_b_id=str(p["participant_b_id"]),
                agent_id=str(p["agent_id"]),
                conversation_ids=p.get("conversation_ids"),
                metadata=p.get("metadata"),
                now=p.get("now"),
            )
        if method == "chat.get_conversation":
            requester_id = self._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
            conversation = self._with_chat(get_conversation, p["conversation_id"])
            if not conversation:
                raise ValueError("conversation not found")
            conversations = self._with_chat(
                list_case_conversations,
                str(conversation["case_id"]),
                requester_id=requester_id,
            )
            for item in conversations:
                if str(item["conversation_id"]) == str(p["conversation_id"]):
                    return item
            raise GatewayPermissionError("requester is not allowed to read this conversation")
        if method == "chat.list_case_conversations":
            requester_id = self._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
            return self._with_chat(
                list_case_conversations,
                str(p["case_id"]),
                requester_id=requester_id,
            )
        if method == "chat.list_conversation_messages":
            bm = p.get("before_message_id")
            if bm is not None:
                bm = int(bm)
            requester_id = self._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
            return self._with_chat(
                list_conversation_messages,
                p["conversation_id"],
                requester_id,
                limit=int(p.get("limit", 50)),
                before_message_id=bm,
            )
        if method == "chat.post_conversation_message":
            p2 = {k: v for k, v in p.items() if k not in {"idempotency_key", "client_idempotency_key"}}
            ck = p.get("client_idempotency_key") or p.get("idempotency_key")
            if ck is not None and str(ck).strip():
                p2["client_msg_id"] = str(ck).strip()[:191]
            cid = p2.pop("conversation_id")
            author_id = self._resolve_actor_bound_id(environ, p2.pop("author_id", None), field_name="author_id")
            body_text = p2.pop("body")
            return self._with_chat(post_conversation_message, cid, author_id, body_text, **p2)
        if method == "chat.get_case_conversation_timeline":
            try:
                mlim = int(p.get("message_limit", 50))
            except (TypeError, ValueError):
                mlim = 50
            requester_id = self._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
            return self._with_chat(
                build_case_conversation_timeline,
                str(p["case_id"]),
                requester_id,
                message_limit=mlim,
            )
        if method == "chat.submit_member_report":
            reporter_id = self._resolve_actor_bound_id(environ, p.get("reporter_id"), field_name="reporter_id")
            return self._with_chat(
                submit_member_report,
                p["thread_id"],
                reporter_id,
                str(p["report_type"]),
                reason_text=p.get("reason_text"),
                message_id=int(p["message_id"]) if p.get("message_id") is not None else None,
                reported_user_id=str(p["reported_user_id"]) if p.get("reported_user_id") is not None else None,
                reported_profile_id=int(p["reported_profile_id"]) if p.get("reported_profile_id") is not None else None,
                reported_source_dsn=p.get("reported_source_dsn") or p.get("source_dsn"),
                reported_source_table_name=p.get("reported_source_table_name") or p.get("source_table_name"),
                evidence=p.get("evidence"),
                now=p.get("now"),
            )
        if method == "chat.submit_meeting_feedback":
            reviewer_id = self._resolve_actor_bound_id(environ, p.get("reviewer_id"), field_name="reviewer_id")
            return self._with_chat(
                submit_meeting_feedback,
                p["thread_id"],
                reviewer_id,
                counterpart_user_id=str(p["counterpart_user_id"]) if p.get("counterpart_user_id") is not None else None,
                counterpart_profile_id=int(p["counterpart_profile_id"]) if p.get("counterpart_profile_id") is not None else None,
                counterpart_source_dsn=p.get("counterpart_source_dsn") or p.get("source_dsn"),
                counterpart_source_table_name=p.get("counterpart_source_table_name") or p.get("source_table_name"),
                photo_match_status=p.get("photo_match_status") or "unclear",
                profile_consistency_status=p.get("profile_consistency_status") or "unclear",
                income_job_consistency_status=p.get("income_job_consistency_status") or "unclear",
                safety_concern_status=p.get("safety_concern_status") or "none",
                willing_video_status=p.get("willing_video_status") or "unknown",
                willing_offline_status=p.get("willing_offline_status") or "unknown",
                notes=p.get("notes"),
                now=p.get("now"),
            )
        if method == "chat.list_member_reports":
            self._require_roles(
                environ,
                CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot list chat reports",
            )
            return self._with_chat(
                list_member_reports,
                thread_id=p.get("thread_id"),
                risk_case_id=p.get("risk_case_id"),
                reported_user_id=p.get("reported_user_id"),
                limit=int(p.get("limit", 100)),
            )
        if method == "chat.list_meeting_feedback":
            reviewer_id = p.get("reviewer_id")
            actor = self._current_actor(environ)
            if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
                reviewer_id = self._resolve_actor_bound_id(environ, reviewer_id, field_name="reviewer_id")
            return self._with_chat(
                list_meeting_feedback,
                thread_id=p.get("thread_id"),
                counterpart_user_id=p.get("counterpart_user_id"),
                reviewer_id=reviewer_id,
                limit=int(p.get("limit", 100)),
            )
        if method == "chat.list_risk_cases":
            self._require_roles(
                environ,
                CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot list chat risk cases",
            )
            return self._with_chat(
                list_risk_cases,
                statuses=p.get("statuses"),
                subject_user_id=p.get("subject_user_id"),
                thread_id=p.get("thread_id"),
                limit=int(p.get("limit", 100)),
            )
        if method == "chat.list_risk_signals":
            self._require_roles(
                environ,
                CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot list chat risk signals",
            )
            return self._with_chat(
                list_risk_signals,
                thread_id=p.get("thread_id"),
                subject_user_id=p.get("subject_user_id"),
                signal_code=p.get("signal_code"),
                limit=int(p.get("limit", 100)),
            )
        if method == "chat.record_fraud_network_observation":
            self._require_roles(
                environ,
                CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
                message="current actor cannot record fraud network observations",
            )
            return self._with_chat(
                record_fraud_network_observation,
                subject_user_id=str(p["subject_user_id"]),
                source_dsn=p.get("source_dsn") or p.get("source"),
                source_table_name=p.get("source_table_name") or p.get("table_name"),
                profile_id=int(p["profile_id"]) if p.get("profile_id") is not None else None,
                thread_id=p.get("thread_id"),
                case_id=p.get("case_id"),
                risk_case_id=p.get("risk_case_id"),
                report_id=int(p["report_id"]) if p.get("report_id") is not None else None,
                source_type=str(p.get("source_type") or p.get("report_source") or "system_rule"),
                event_type=str(p.get("event_type") or "manual_observation"),
                signal_codes=p.get("signal_codes"),
                evidence=p.get("evidence"),
                message_body=p.get("message_body"),
                now=p.get("now"),
                evaluate=_normalize_boolish(p.get("evaluate"), default=True),
            )
        if method == "chat.evaluate_fraud_network":
            self._require_roles(
                environ,
                CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
                message="current actor cannot evaluate fraud networks",
            )
            return self._with_chat(
                evaluate_fraud_network,
                str(p["subject_user_id"]),
                source_dsn=p.get("source_dsn") or p.get("source"),
                source_table_name=p.get("source_table_name") or p.get("table_name"),
                profile_id=int(p["profile_id"]) if p.get("profile_id") is not None else None,
                now=p.get("now"),
                propagate=_normalize_boolish(p.get("propagate"), default=True),
            )
        if method == "chat.list_fraud_networks":
            self._require_roles(
                environ,
                CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot list fraud networks",
            )
            return self._with_chat(
                list_fraud_network_profiles,
                review_statuses=p.get("review_statuses") or p.get("statuses"),
                subject_user_id=p.get("subject_user_id"),
                minimum_score=int(p["minimum_score"]) if p.get("minimum_score") is not None else None,
                limit=int(p.get("limit", 100)),
            )
        if method == "chat.get_fraud_network":
            self._require_roles(
                environ,
                CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot inspect fraud networks",
            )
            return self._with_chat(build_fraud_network_overview, str(p["subject_user_id"]))
        if method == "chat.get_risk_case":
            self._require_roles(
                environ,
                CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot inspect chat risk cases",
            )
            return self._with_chat(build_risk_case_playback, p["risk_case_id"])
        if method == "chat.review_risk_case":
            resolver_id = self._resolve_operator_actor_id(
                environ,
                p.get("resolver_id"),
                field_name="resolver_id",
                roles=CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot review chat risk cases",
            )
            return self._with_chat(
                review_risk_case,
                p["risk_case_id"],
                resolver_id,
                status=str(p["status"]),
                applied_action=p.get("applied_action"),
                resolution_note=p.get("resolution_note"),
                now=p.get("now"),
            )
        if method == "chat.get_thread_risk_overview":
            requester_id = self._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
            return self._with_chat(
                build_thread_risk_overview,
                p["thread_id"],
                requester_id,
            )
        if method == "chat.submit_risk_appeal":
            appellant_id = self._resolve_actor_bound_id(environ, p.get("appellant_id"), field_name="appellant_id")
            return self._with_chat(
                submit_risk_appeal,
                p["risk_case_id"],
                appellant_id,
                reason_text=str(p["reason_text"]),
                evidence=p.get("evidence"),
                now=p.get("now"),
            )
        if method == "chat.list_risk_appeals":
            self._require_roles(
                environ,
                CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot list chat risk appeals",
            )
            return self._with_chat(
                list_risk_appeals,
                statuses=p.get("statuses"),
                risk_case_id=p.get("risk_case_id"),
                subject_user_id=p.get("subject_user_id"),
                limit=int(p.get("limit", 100)),
            )
        if method == "chat.get_risk_appeal":
            self._require_roles(
                environ,
                CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot inspect chat risk appeals",
            )
            return self._with_chat(get_risk_appeal, int(p["appeal_id"]))
        if method == "chat.review_risk_appeal":
            resolver_id = self._resolve_operator_actor_id(
                environ,
                p.get("resolver_id"),
                field_name="resolver_id",
                roles=CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot review chat risk appeals",
            )
            return self._with_chat(
                review_risk_appeal,
                int(p["appeal_id"]),
                resolver_id,
                appeal_status=str(p["appeal_status"]),
                resolution_note=p.get("resolution_note"),
                now=p.get("now"),
            )
        if method == "chat.batch_review_risk_cases":
            resolver_id = self._resolve_operator_actor_id(
                environ,
                p.get("resolver_id"),
                field_name="resolver_id",
                roles=CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot batch review chat risk cases",
            )
            return self._with_chat(
                batch_review_risk_cases,
                risk_case_ids=p.get("risk_case_ids") or [],
                resolver_id=resolver_id,
                status=str(p["status"]),
                applied_action=p.get("applied_action"),
                resolution_note=p.get("resolution_note"),
                now=p.get("now"),
            )
        if method == "chat.get_risk_weekly_dashboard":
            self._require_roles(
                environ,
                CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
                message="current actor cannot view the risk dashboard",
            )
            return self._with_chat(
                build_risk_weekly_dashboard,
                now=p.get("now"),
                days=int(p.get("days", 7)),
            )
        if method == "profile.get_field_verification_policies":
            return field_verification_policies()
        if method == "profile.submit_field_verification":
            if p.get("subject_user_id") is not None or self._current_actor(environ) is not None:
                p = {**p, "subject_user_id": self._resolve_actor_bound_id(
                    environ,
                    p.get("subject_user_id"),
                    field_name="subject_user_id",
                )}
            return self._with_chat(submit_profile_field_verification, **p)
        if method == "profile.list_field_verifications":
            subject_user_id = p.get("subject_user_id")
            actor = self._current_actor(environ)
            if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
                subject_user_id = self._resolve_actor_bound_id(environ, subject_user_id, field_name="subject_user_id")
            p = {**p, "subject_user_id": subject_user_id}
            return self._with_chat(list_profile_field_verification_submissions, **p)
        if method == "profile.get_field_verification":
            submission = self._with_chat(get_profile_field_verification_submission, p["submission_id"])
            self._assert_actor_can_access_owner(environ, (submission or {}).get("subject_user_id"), field_name="subject_user_id")
            return submission
        if method == "profile.resubmit_field_verification":
            submission_id = p.pop("submission_id")
            if p.get("subject_user_id") is not None or self._current_actor(environ) is not None:
                p["subject_user_id"] = self._resolve_actor_bound_id(
                    environ,
                    p.get("subject_user_id"),
                    field_name="subject_user_id",
                )
            return self._with_chat(resubmit_profile_field_verification, submission_id, **p)
        if method == "profile.dispute_field_verification":
            submission_id = p.pop("submission_id")
            if p.get("subject_user_id") is not None or self._current_actor(environ) is not None:
                p["subject_user_id"] = self._resolve_actor_bound_id(
                    environ,
                    p.get("subject_user_id"),
                    field_name="subject_user_id",
                )
            return self._with_chat(dispute_profile_field_verification, submission_id, **p)
        if method == "profile.review_field_verification":
            submission_id = p.pop("submission_id")
            reviewer_id = self._resolve_operator_actor_id(
                environ,
                p.pop("reviewer_id", None),
                field_name="reviewer_id",
                roles=PROFILE_REVIEW_ROLES,
                message="current actor cannot review profile verifications",
            )
            return self._with_chat(review_profile_field_verification, submission_id, reviewer_id, **p)
        if method == "profile.expire_due_field_verifications":
            self._require_roles(
                environ,
                PROFILE_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
                message="current actor cannot expire due profile verifications",
            )
            return self._with_chat(expire_due_profile_field_verifications, **p)
        if method == "profile.evaluate_risk_case":
            self._require_roles(
                environ,
                PROFILE_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
                message="current actor cannot evaluate profile review cases",
            )
            return self._with_chat(evaluate_profile_consistency, **p)
        if method == "profile.list_risk_cases":
            subject_user_id = p.get("subject_user_id")
            actor = self._current_actor(environ)
            if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
                subject_user_id = self._resolve_actor_bound_id(environ, subject_user_id, field_name="subject_user_id")
            p = {**p, "subject_user_id": subject_user_id}
            return self._with_chat(list_profile_review_cases, **p)
        if method == "profile.get_risk_case":
            risk_case = self._with_chat(get_profile_review_case, p["profile_review_case_id"])
            self._assert_actor_can_access_owner(environ, (risk_case or {}).get("subject_user_id"), field_name="subject_user_id")
            return risk_case
        if method == "profile.list_photo_risk_runs":
            subject_user_id = p.get("subject_user_id")
            actor = self._current_actor(environ)
            if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
                subject_user_id = self._resolve_actor_bound_id(environ, subject_user_id, field_name="subject_user_id")
            p = {**p, "subject_user_id": subject_user_id}
            return self._with_chat(list_photo_risk_score_runs, **p)
        if method == "profile.get_photo_risk_run":
            row = self._with_chat(get_photo_risk_score_run, int(p["score_run_id"]))
            self._assert_actor_can_access_owner(environ, (row or {}).get("subject_user_id"), field_name="subject_user_id")
            return row
        if method == "profile.list_photo_risk_review_queue":
            self._require_roles(
                environ,
                PROFILE_REVIEW_ROLES,
                message="current actor cannot view the photo risk review queue",
            )
            return self._with_chat(list_photo_risk_review_queue, **p)
        if method == "profile.review_risk_case":
            profile_review_case_id = p.pop("profile_review_case_id")
            resolver_id = self._resolve_operator_actor_id(
                environ,
                p.pop("resolver_id", None),
                field_name="resolver_id",
                roles=PROFILE_REVIEW_ROLES,
                message="current actor cannot review profile risk cases",
            )
            return self._with_chat(review_profile_review_case, profile_review_case_id, resolver_id, **p)
        if method == "profile.submit_risk_case_appeal":
            profile_review_case_id = p.pop("profile_review_case_id")
            appellant_id = self._resolve_actor_bound_id(
                environ,
                p.pop("appellant_id", None),
                field_name="appellant_id",
            )
            return self._with_chat(submit_profile_review_case_appeal, profile_review_case_id, appellant_id, **p)
        if method == "profile.list_risk_case_appeals":
            subject_user_id = p.get("subject_user_id")
            actor = self._current_actor(environ)
            if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
                subject_user_id = self._resolve_actor_bound_id(environ, subject_user_id, field_name="subject_user_id")
            p = {**p, "subject_user_id": subject_user_id}
            return self._with_chat(list_profile_review_case_appeals, **p)
        if method == "profile.get_risk_case_appeal":
            appeal = self._with_chat(get_profile_review_case_appeal, int(p["appeal_id"]))
            self._assert_actor_can_access_owner(environ, (appeal or {}).get("subject_user_id"), field_name="subject_user_id")
            return appeal
        if method == "profile.review_risk_case_appeal":
            appeal_id = int(p.pop("appeal_id"))
            resolver_id = self._resolve_operator_actor_id(
                environ,
                p.pop("resolver_id", None),
                field_name="resolver_id",
                roles=PROFILE_REVIEW_ROLES,
                message="current actor cannot review profile appeals",
            )
            return self._with_chat(review_profile_review_case_appeal, appeal_id, resolver_id, **p)
        if method == "user.get_trust_hub":
            user_id = self._resolve_actor_bound_id(environ, p.get("user_id"), field_name="user_id")
            return self._with_chat(
                build_user_trust_hub,
                user_id=user_id,
                profile_id=int(p["profile_id"]) if p.get("profile_id") is not None else None,
                limit=int(p.get("limit", 20)),
            )

        if method == "timeline.get_for_case":
            try:
                mlim = int(p.get("message_limit", 50))
            except (TypeError, ValueError):
                mlim = 50
            viewer_id = self._resolve_actor_bound_id(environ, p.get("viewer_id"), field_name="viewer_id")
            return self._timeline_payload(str(p["case_id"]), viewer_id, message_limit=mlim)

        if method == "chat.list_pending_outbox":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot inspect chat outbox",
            )
            try:
                lim = int(p.get("limit", 100))
            except (TypeError, ValueError):
                lim = 100
            return self._with_chat(list_pending_outbox, limit=lim)

        if method == "chat.process_persona_jobs":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot process persona jobs",
            )
            try:
                lim = int(p.get("limit", 20))
            except (TypeError, ValueError):
                lim = 20
            return self._with_chat(process_pending_persona_jobs, limit=lim)

        if method == "chat.run_maintenance":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot run chat maintenance",
            )
            try:
                plim = int(p.get("persona_limit", 20))
            except (TypeError, ValueError):
                plim = 20
            try:
                smax = int(p.get("summary_max_threads", 30))
            except (TypeError, ValueError):
                smax = 30
            rf = p.get("flush_outbox")
            flush_opt: bool | None = None
            if isinstance(rf, bool):
                flush_opt = rf
            elif isinstance(rf, str):
                flush_opt = rf.lower() in ("1", "true", "yes")
            payload: dict[str, Any] = {
                "persona_limit": plim,
                "summary_max_threads": smax,
            }
            if flush_opt is not None:
                payload["flush_outbox"] = flush_opt
            actor = self._current_actor(environ)
            job = self._with_chat(
                enqueue_chat_async_job,
                job_type=JOB_RUN_CHAT_MAINTENANCE,
                payload=payload,
                created_by=actor.actor_id if actor is not None else None,
                trace_id=get_trace_id(),
            )
            return self._job_payload("chat", job)
        if method == "chat.get_async_job":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot inspect chat jobs",
            )
            job = self._with_chat(get_chat_async_job, str(p["job_id"]))
            if not job:
                raise ValueError("job not found")
            return self._job_payload("chat", job)
        if method == "chat.list_async_jobs":
            self._require_roles(
                environ,
                INTERNAL_WRITE_ROLES,
                message="current actor cannot inspect chat jobs",
            )
            statuses = p.get("statuses")
            if statuses is not None and not isinstance(statuses, list):
                raise ValueError("statuses must be a list")
            limit = int(p.get("limit", 50))
            jobs = self._with_chat(list_chat_async_jobs, statuses=statuses, limit=limit)
            summary = self._with_chat(summarize_chat_async_jobs)
            return self._job_collection_payload("chat", jobs, summary)

        raise ValueError(f"Unknown method: {method}")

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        path = environ.get("PATH_INFO") or "/"
        method = environ.get("REQUEST_METHOD", "GET").upper()
        trace_id = _incoming_trace_id(environ)
        token = set_trace_id(trace_id)
        actor_token = set_actor_context(None)
        sr = _wrap_trace_headers(start_response, trace_id)
        status_code = 500

        def _access_log(code: int) -> None:
            emit_pipeline_record(
                her_kind="gateway_access",
                trace_id=trace_id,
                http_method=method,
                path=path,
                status_code=code,
                client_ip=client_ip(environ),
            )

        try:
            if path.rstrip("/") == "/health" and method == "GET":
                payload = self.handle_health(environ)
                body = json.dumps(payload[1], ensure_ascii=False).encode("utf-8")
                sr("200 OK", JSON_HEADERS + [("Content-Length", str(len(body)))])
                _access_log(200)
                return [body]
            demo_html = _read_demo_html(path) if method == "GET" else None
            if demo_html is not None:
                body = demo_html.encode("utf-8")
                sr("200 OK", DEMO_HTML_HEADERS + [("Content-Length", str(len(body)))])
                _access_log(200)
                return [body]
            if path.startswith("/demo/assets/") and method == "GET":
                asset = _demo_asset_file(path[len("/demo/assets/") :])
                if asset is None:
                    status_code = 404
                    body = json.dumps(
                        _gateway_error_payload("not_found", "demo asset not found", trace_id),
                        ensure_ascii=False,
                    ).encode("utf-8")
                    sr("404 Not Found", JSON_HEADERS + [("Content-Length", str(len(body)))])
                    _access_log(status_code)
                    return [body]
                content_type = mimetypes.guess_type(str(asset))[0] or "application/octet-stream"
                if content_type.startswith("text/") or content_type in {"application/javascript", "application/json"}:
                    body = asset.read_text(encoding="utf-8").encode("utf-8")
                    headers = [
                        ("Content-Type", f"{content_type}; charset=utf-8"),
                        ("Cache-Control", "public, max-age=3600"),
                        ("Content-Length", str(len(body))),
                    ]
                else:
                    body = asset.read_bytes()
                    headers = [
                        ("Content-Type", content_type),
                        ("Cache-Control", "public, max-age=3600"),
                        ("Content-Length", str(len(body))),
                    ]
                sr("200 OK", headers)
                _access_log(200)
                return [body]

            actor = self._identity_resolver.resolve(environ)
            set_current_actor(environ, actor)
            actor_token = set_actor_context(
                actor.actor_id if actor is not None else None,
                actor_roles=actor.roles if actor is not None else None,
                auth_source=actor.auth_source if actor is not None else None,
                token_id=actor.token_id if actor is not None else None,
            )
            if not self._rate_limiter.allow(client_ip(environ)):
                status_code = 429
                body = json.dumps(
                    _gateway_error_payload("rate_limited", "Too many requests", trace_id),
                    ensure_ascii=False,
                ).encode("utf-8")
                sr("429 Too Many Requests", JSON_HEADERS + [("Content-Length", str(len(body)))])
                _access_log(status_code)
                return [body]

            if path.rstrip("/") == "/jsonrpc" and method == "POST":
                status_code, payload = self.dispatch_jsonrpc(environ)
                if status_code == 204:
                    sr("204 No Content", [])
                    _access_log(status_code)
                    return [b""]
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                rpc_reason = {200: "OK", 400: "Bad Request"}.get(status_code, "Error")
                sr(
                    f"{status_code} {rpc_reason}",
                    JSON_HEADERS + [("Content-Length", str(len(body)))],
                )
                _access_log(status_code)
                return [body]

            status_code, payload = self.dispatch_rest(environ)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            reason = "OK" if status_code < 400 else ("Not Found" if status_code == 404 else "Error")
            sr(f"{status_code} {reason}", JSON_HEADERS + [("Content-Length", str(len(body)))])
            _access_log(status_code)
            return [body]
        except GatewayAuthError as e:
            status_code = 401
            audit_event(
                action="gateway.request_auth",
                resource_type="http_request",
                resource_id=path,
                outcome="denied",
                reason=str(e),
                http_method=method,
                path=path,
                status_code=status_code,
            )
            body = json.dumps(
                _gateway_error_payload("unauthorized", str(e), trace_id),
                ensure_ascii=False,
            ).encode("utf-8")
            sr("401 Unauthorized", JSON_HEADERS + [("Content-Length", str(len(body)))])
            _access_log(status_code)
            return [body]
        except GatewayPermissionError as e:
            status_code = 403
            audit_event(
                action="gateway.request_permission",
                resource_type="http_request",
                resource_id=path,
                outcome="denied",
                reason=str(e),
                http_method=method,
                path=path,
                status_code=status_code,
            )
            err = {"error": {"code": "forbidden", "message": str(e)}, "trace_id": trace_id}
            body = json.dumps(err, ensure_ascii=False).encode("utf-8")
            sr("403 Forbidden", JSON_HEADERS + [("Content-Length", str(len(body)))])
            _access_log(status_code)
            return [body]
        except ValueError as e:
            status_code = 400
            err = {"error": {"code": "bad_request", "message": str(e)}, "trace_id": trace_id}
            body = json.dumps(err, ensure_ascii=False).encode("utf-8")
            sr("400 Bad Request", JSON_HEADERS + [("Content-Length", str(len(body)))])
            _access_log(status_code)
            return [body]
        except Exception as e:  # noqa: BLE001
            err = {"error": {"code": "internal_error", "message": str(e)}, "trace_id": trace_id}
            body = json.dumps(err, ensure_ascii=False).encode("utf-8")
            sr("500 Internal Server Error", JSON_HEADERS + [("Content-Length", str(len(body)))])
            _access_log(500)
            return [body]
        finally:
            reset_actor_context(actor_token)
            reset_trace_id(token)


_default_gateway = PartnerGateway()
application = _default_gateway


def make_application(
    *,
    recommendation_dsn: str | None = None,
    matchmaking_dsn: str | None = None,
    chat_dsn: str | None = None,
    db_pool_max: int | None = None,
) -> PartnerGateway:
    return PartnerGateway(
        recommendation_dsn=recommendation_dsn,
        matchmaking_dsn=matchmaking_dsn,
        chat_dsn=chat_dsn,
        db_pool_max=db_pool_max,
    )
