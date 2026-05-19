"""WSGI app: REST JSON under /v1/... and JSON-RPC 2.0 under POST /jsonrpc."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
from typing import Any, Callable

from . import _paths  # noqa: F401 — side effect: sys.path
from .chat_jsonrpc import JSONRPC_NOT_HANDLED, handle_chat_jsonrpc
from .http_helpers import (  # noqa: E402
    _demo_asset_file,
    _gateway_error_payload,
    _incoming_trace_id,
    _json_safe,
    _normalize_boolish,
    _parse_json_body,
    _parse_optional_now,
    _query_dict,
    _read_body,
    _read_demo_html,
    _wrap_trace_headers,
)

from match_domain import (  # noqa: E402
    reset_actor_context,
    reset_trace_id,
    set_actor_context,
    set_trace_id,
)
from observability import audit_event, emit_pipeline_record  # noqa: E402

from partner_search import search_profiles as partner_search_profiles  # noqa: E402

from recommendation_system import (  # type: ignore[import-untyped]
    connect_db as recommendation_connect_db,
)
from recommendation_system.storage import (  # type: ignore[import-untyped]
    DEFAULT_RECOMMENDATION_MYSQL_DSN,
)
from matchmaking_system import (  # type: ignore[import-untyped]
    connect_db as matchmaking_connect_db,
)
from matchmaking_system.storage import (  # type: ignore[import-untyped]
    DEFAULT_MATCHMAKING_MYSQL_DSN,
)
from chat_system.storage import (  # type: ignore[import-untyped]
    DEFAULT_CHAT_MYSQL_DSN,
    connect_db as chat_connect_db,
)
from discovery_system import (  # type: ignore[import-untyped]
    create_default_discovery_service,
)

from .access_control import GatewayAccessMixin
from .auth_routes import AuthOtpService, dispatch_public_auth_rest
from .async_jobs import AsyncJobGatewayMixin
from .chat_routes import (
    chat_require_requester as _chat_require_requester,
    dispatch_chat_rest,
    rest_chat_case_conversation_timeline as _rest_chat_case_conversation_timeline,
    rest_chat_create_assistant_layout as _rest_chat_create_assistant_layout,
    rest_chat_create_thread as _rest_chat_create_thread,
    rest_chat_get_conversation as _rest_chat_get_conversation,
    rest_chat_get_summary as _rest_chat_get_summary,
    rest_chat_get_thread as _rest_chat_get_thread,
    rest_chat_list_case_conversations as _rest_chat_list_case_conversations,
    rest_chat_list_conversation_messages as _rest_chat_list_conversation_messages,
    rest_chat_list_messages as _rest_chat_list_messages,
    rest_chat_maintenance_run as _rest_chat_maintenance_run,
    rest_chat_post_conversation_message as _rest_chat_post_conversation_message,
    rest_chat_post_message as _rest_chat_post_message,
    rest_get_chat_job as _rest_get_chat_job,
    rest_list_chat_jobs as _rest_list_chat_jobs,
    rest_timeline as _rest_timeline,
    timeline_payload as _chat_timeline_payload,
)
from .chat_safety_routes import (
    dispatch_chat_safety_rest,
    rest_chat_batch_review_risk_cases as _rest_chat_batch_review_risk_cases,
    rest_chat_evaluate_fraud_network as _rest_chat_evaluate_fraud_network,
    rest_chat_get_fraud_network as _rest_chat_get_fraud_network,
    rest_chat_get_risk_appeal as _rest_chat_get_risk_appeal,
    rest_chat_get_risk_case as _rest_chat_get_risk_case,
    rest_chat_list_fraud_networks as _rest_chat_list_fraud_networks,
    rest_chat_list_meeting_feedback as _rest_chat_list_meeting_feedback,
    rest_chat_list_reports as _rest_chat_list_reports,
    rest_chat_list_risk_appeals as _rest_chat_list_risk_appeals,
    rest_chat_list_risk_cases as _rest_chat_list_risk_cases,
    rest_chat_list_risk_signals as _rest_chat_list_risk_signals,
    rest_chat_record_fraud_network_observation as _rest_chat_record_fraud_network_observation,
    rest_chat_review_risk_appeal as _rest_chat_review_risk_appeal,
    rest_chat_review_risk_case as _rest_chat_review_risk_case,
    rest_chat_risk_dashboard as _rest_chat_risk_dashboard,
    rest_chat_submit_meeting_feedback as _rest_chat_submit_meeting_feedback,
    rest_chat_submit_report as _rest_chat_submit_report,
    rest_chat_submit_risk_appeal as _rest_chat_submit_risk_appeal,
    rest_chat_thread_risk_overview as _rest_chat_thread_risk_overview,
    rest_user_trust_hub as _rest_user_trust_hub,
)
from .discovery_routes import dispatch_discovery_rest
from .identity import (
    GatewayAuthError,
    GatewayPermissionError,
    IdentityResolver,
    set_current_actor,
)
from .matchmaking_routes import (
    dispatch_matchmaking_rest,
    rest_get_matchmaking_job as _rest_get_matchmaking_job,
    rest_list_matchmaking_jobs as _rest_list_matchmaking_jobs,
    rest_mm_build_pairs as _rest_mm_build_pairs,
    rest_mm_close_stale as _rest_mm_close_stale,
    rest_mm_create_member as _rest_mm_create_member,
    rest_mm_dispatch as _rest_mm_dispatch,
    rest_mm_feedback as _rest_mm_feedback,
    rest_mm_get_case as _rest_mm_get_case,
    rest_mm_get_member as _rest_mm_get_member,
    rest_mm_get_pair as _rest_mm_get_pair,
    rest_mm_list_cases as _rest_mm_list_cases,
    rest_mm_list_pairs as _rest_mm_list_pairs,
    rest_mm_open_cases as _rest_mm_open_cases,
    rest_mm_refresh_member as _rest_mm_refresh_member,
    rest_mm_refresh_pool as _rest_mm_refresh_pool,
    rest_mm_reply as _rest_mm_reply,
    rest_mm_set_status as _rest_mm_set_status,
)
from .matchmaking_jsonrpc import JSONRPC_NOT_HANDLED as MATCHMAKING_JSONRPC_NOT_HANDLED, handle_matchmaking_jsonrpc
from .mysql_pool import GatewayConnectionPool
from .profile_jsonrpc import JSONRPC_NOT_HANDLED as PROFILE_JSONRPC_NOT_HANDLED, handle_profile_jsonrpc
from .recommendation_jsonrpc import JSONRPC_NOT_HANDLED as RECOMMENDATION_JSONRPC_NOT_HANDLED, handle_recommendation_jsonrpc
from .request_policy import client_ip, rate_limiter_from_environ
from .verification_jsonrpc import JSONRPC_NOT_HANDLED as VERIFICATION_JSONRPC_NOT_HANDLED, handle_verification_jsonrpc
from .profile_routes import (
    dispatch_profile_rest,
    rest_profile_dispute_field_verification as _rest_profile_dispute_field_verification,
    rest_profile_evaluate_review as _rest_profile_evaluate_review,
    rest_profile_expire_due_field_verifications as _rest_profile_expire_due_field_verifications,
    rest_profile_get_field_verification as _rest_profile_get_field_verification,
    rest_profile_get_photo_risk_run as _rest_profile_get_photo_risk_run,
    rest_profile_get_review_case as _rest_profile_get_review_case,
    rest_profile_get_review_case_appeal as _rest_profile_get_review_case_appeal,
    rest_profile_list_field_verifications as _rest_profile_list_field_verifications,
    rest_profile_list_photo_risk_review_queue as _rest_profile_list_photo_risk_review_queue,
    rest_profile_list_photo_risk_runs as _rest_profile_list_photo_risk_runs,
    rest_profile_list_review_case_appeals as _rest_profile_list_review_case_appeals,
    rest_profile_list_review_cases as _rest_profile_list_review_cases,
    rest_profile_resubmit_field_verification as _rest_profile_resubmit_field_verification,
    rest_profile_review_case as _rest_profile_review_case,
    rest_profile_review_field_verification as _rest_profile_review_field_verification,
    rest_profile_review_review_case_appeal as _rest_profile_review_review_case_appeal,
    rest_profile_submit_field_verification as _rest_profile_submit_field_verification,
    rest_profile_submit_review_case_appeal as _rest_profile_submit_review_case_appeal,
    rest_profile_verification_policies as _rest_profile_verification_policies,
)
from .recommendation_routes import (
    dispatch_recommendation_rest,
    rest_create_subscription as _rest_create_subscription,
    rest_deliver as _rest_deliver,
    rest_get_recommendation_job as _rest_get_recommendation_job,
    rest_get_subscription as _rest_get_subscription,
    rest_list_cards as _rest_list_cards,
    rest_list_recommendation_jobs as _rest_list_recommendation_jobs,
    rest_list_recommendations as _rest_list_recommendations,
    rest_list_runs as _rest_list_runs,
    rest_mark_cards_read as _rest_mark_cards_read,
    rest_patch_overrides as _rest_patch_overrides,
    rest_record_action as _rest_record_action,
    rest_record_review as _rest_record_review,
    rest_refresh_due as _rest_refresh_due,
    rest_refresh_subscription as _rest_refresh_subscription,
)
from .role_sets import (
    INTERNAL_WRITE_ROLES,
)
from .verification_routes import (
    dispatch_verification_rest,
    rest_verification_create_live_challenge as _rest_verification_create_live_challenge,
    rest_verification_get_photo_review_request as _rest_verification_get_photo_review_request,
    rest_verification_get_submission as _rest_verification_get_submission,
    rest_verification_list_notifications as _rest_verification_list_notifications,
    rest_verification_list_photo_review_requests as _rest_verification_list_photo_review_requests,
    rest_verification_list_submissions as _rest_verification_list_submissions,
    rest_verification_request_live_video as _rest_verification_request_live_video,
    rest_verification_resubmit_live_video as _rest_verification_resubmit_live_video,
    rest_verification_review_submission as _rest_verification_review_submission,
    rest_verification_submit_live_video as _rest_verification_submit_live_video,
)

JSON_HEADERS = [("Content-Type", "application/json; charset=utf-8")]
HTML_HEADERS = [("Content-Type", "text/html; charset=utf-8")]
DEMO_HTML_HEADERS = HTML_HEADERS + [("Cache-Control", "no-store")]
LOGGER = logging.getLogger(__name__)


class PartnerGateway(AsyncJobGatewayMixin, GatewayAccessMixin):
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
        self._auth_otp = AuthOtpService()
        self._identity_resolver = IdentityResolver()
        self._rate_limiter = rate_limiter_from_environ()

    def _with_db(
        self,
        pool: GatewayConnectionPool | None,
        connect_db: Callable[[str], Any],
        dsn: str,
        fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        if pool is not None:
            conn = pool.acquire()
            try:
                return fn(conn, *args, **kwargs)
            finally:
                pool.release(conn)
        conn = connect_db(dsn)
        try:
            return fn(conn, *args, **kwargs)
        finally:
            conn.close()

    def _with_rec(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return self._with_db(
            self._rec_pool,
            recommendation_connect_db,
            self._recommendation_dsn,
            fn,
            *args,
            **kwargs,
        )

    def _with_mm(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return self._with_db(
            self._mm_pool,
            matchmaking_connect_db,
            self._matchmaking_dsn,
            fn,
            *args,
            **kwargs,
        )

    def _with_chat(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return self._with_db(
            self._chat_pool,
            chat_connect_db,
            self._chat_dsn,
            fn,
            *args,
            **kwargs,
        )

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

    def rest_get_subscription(self, environ: dict[str, Any], subscription_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_get_subscription(self, environ, subscription_id)

    def rest_create_subscription(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_create_subscription(self, environ, body)

    def rest_patch_overrides(self, environ: dict[str, Any], subscription_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        return _rest_patch_overrides(self, environ, subscription_id, body)

    def rest_refresh_subscription(self, environ: dict[str, Any], subscription_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        return _rest_refresh_subscription(self, environ, subscription_id, body)

    def rest_refresh_due(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_refresh_due(self, environ, body)

    def rest_list_recommendations(self, environ: dict[str, Any], subscription_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_list_recommendations(self, environ, subscription_id)

    def rest_list_runs(self, environ: dict[str, Any], subscription_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_list_runs(self, environ, subscription_id)

    def rest_list_cards(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_list_cards(self, environ)

    def rest_deliver(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_deliver(self, environ, body)

    def rest_get_recommendation_job(self, environ: dict[str, Any], job_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_get_recommendation_job(self, environ, job_id)

    def rest_list_recommendation_jobs(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_list_recommendation_jobs(self, environ)

    def rest_record_action(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_record_action(self, environ, body)

    def rest_record_review(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_record_review(self, environ, body)

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
        return _rest_verification_submit_live_video(self, environ, body)

    def rest_verification_request_live_video(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_verification_request_live_video(self, environ, body)

    def rest_verification_create_live_challenge(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_verification_create_live_challenge(self, environ, body)

    def rest_verification_list_submissions(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_verification_list_submissions(self, environ)

    def rest_verification_list_photo_review_requests(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_verification_list_photo_review_requests(self, environ)

    def rest_verification_get_submission(
        self,
        environ: dict[str, Any],
        submission_id: str,
    ) -> tuple[int, dict[str, Any]]:
        return _rest_verification_get_submission(self, environ, submission_id)

    def rest_verification_get_photo_review_request(
        self,
        environ: dict[str, Any],
        submission_id: str,
    ) -> tuple[int, dict[str, Any]]:
        return _rest_verification_get_photo_review_request(self, environ, submission_id)

    def rest_verification_resubmit_live_video(
        self,
        environ: dict[str, Any],
        submission_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_verification_resubmit_live_video(self, environ, submission_id, body)

    def rest_verification_list_notifications(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_verification_list_notifications(self, environ)

    def rest_verification_review_submission(
        self,
        environ: dict[str, Any],
        submission_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_verification_review_submission(self, environ, submission_id, body)

    def rest_profile_verification_policies(self, _environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_profile_verification_policies(self, _environ)

    def rest_profile_submit_field_verification(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_profile_submit_field_verification(self, environ, body)

    def rest_profile_list_field_verifications(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_profile_list_field_verifications(self, environ)

    def rest_profile_get_field_verification(self, environ: dict[str, Any], submission_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_profile_get_field_verification(self, environ, submission_id)

    def rest_profile_resubmit_field_verification(
        self,
        environ: dict[str, Any],
        submission_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_profile_resubmit_field_verification(self, environ, submission_id, body)

    def rest_profile_dispute_field_verification(
        self,
        environ: dict[str, Any],
        submission_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_profile_dispute_field_verification(self, environ, submission_id, body)

    def rest_profile_review_field_verification(
        self,
        environ: dict[str, Any],
        submission_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_profile_review_field_verification(self, environ, submission_id, body)

    def rest_profile_expire_due_field_verifications(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_profile_expire_due_field_verifications(self, environ, body)

    def rest_profile_evaluate_review(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_profile_evaluate_review(self, environ, body)

    def rest_profile_list_review_cases(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_profile_list_review_cases(self, environ)

    def rest_profile_get_review_case(self, environ: dict[str, Any], profile_review_case_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_profile_get_review_case(self, environ, profile_review_case_id)

    def rest_profile_list_photo_risk_runs(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_profile_list_photo_risk_runs(self, environ)

    def rest_profile_get_photo_risk_run(self, environ: dict[str, Any], score_run_id: int) -> tuple[int, dict[str, Any]]:
        return _rest_profile_get_photo_risk_run(self, environ, score_run_id)

    def rest_profile_list_photo_risk_review_queue(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_profile_list_photo_risk_review_queue(self, environ)

    def rest_profile_review_case(
        self,
        environ: dict[str, Any],
        profile_review_case_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_profile_review_case(self, environ, profile_review_case_id, body)

    def rest_profile_submit_review_case_appeal(
        self,
        environ: dict[str, Any],
        profile_review_case_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_profile_submit_review_case_appeal(self, environ, profile_review_case_id, body)

    def rest_profile_list_review_case_appeals(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_profile_list_review_case_appeals(self, environ)

    def rest_profile_get_review_case_appeal(self, environ: dict[str, Any], appeal_id: int) -> tuple[int, dict[str, Any]]:
        return _rest_profile_get_review_case_appeal(self, environ, appeal_id)

    def rest_profile_review_review_case_appeal(
        self,
        environ: dict[str, Any],
        appeal_id: int,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_profile_review_review_case_appeal(self, environ, appeal_id, body)

    def rest_user_trust_hub(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_user_trust_hub(self, environ)

    def rest_mark_cards_read(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_mark_cards_read(self, _environ, body)

    def rest_mm_create_member(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_mm_create_member(self, environ, body)

    def rest_mm_get_member(self, environ: dict[str, Any], member_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_mm_get_member(self, environ, member_id)

    def rest_mm_set_status(self, environ: dict[str, Any], member_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        return _rest_mm_set_status(self, environ, member_id, body)

    def rest_mm_refresh_member(self, environ: dict[str, Any], member_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        return _rest_mm_refresh_member(self, environ, member_id, body)

    def rest_mm_refresh_pool(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_mm_refresh_pool(self, environ, body)

    def rest_mm_build_pairs(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_mm_build_pairs(self, environ, body)

    def rest_mm_open_cases(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_mm_open_cases(self, environ, body)

    def rest_mm_get_case(self, environ: dict[str, Any], case_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_mm_get_case(self, environ, case_id)

    def rest_mm_list_cases(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_mm_list_cases(self, environ)

    def rest_mm_list_pairs(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_mm_list_pairs(self, environ)

    def rest_mm_get_pair(self, environ: dict[str, Any], pair_key: str) -> tuple[int, dict[str, Any]]:
        return _rest_mm_get_pair(self, environ, pair_key)

    def rest_mm_dispatch(self, environ: dict[str, Any], case_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_mm_dispatch(self, environ, case_id, body)

    def rest_mm_reply(self, environ: dict[str, Any], case_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_mm_reply(self, environ, case_id, body)

    def rest_mm_feedback(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_mm_feedback(self, environ, body)

    def rest_mm_close_stale(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_mm_close_stale(self, environ, body)

    def rest_get_matchmaking_job(self, environ: dict[str, Any], job_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_get_matchmaking_job(self, environ, job_id)

    def rest_list_matchmaking_jobs(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_list_matchmaking_jobs(self, environ)

    def _chat_require_requester(
        self,
        environ: dict[str, Any],
        q: dict[str, str],
        body: dict[str, Any] | None = None,
    ) -> str:
        return _chat_require_requester(self, environ, q, body)

    def rest_chat_create_thread(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_create_thread(self, environ, body)

    def rest_chat_get_thread(self, environ: dict[str, Any], thread_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_chat_get_thread(self, environ, thread_id)

    def rest_chat_list_messages(self, environ: dict[str, Any], thread_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_chat_list_messages(self, environ, thread_id)

    def rest_chat_post_message(self, environ: dict[str, Any], thread_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_post_message(self, environ, thread_id, body)

    def rest_chat_create_assistant_layout(
        self,
        environ: dict[str, Any],
        case_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_create_assistant_layout(self, environ, case_id, body)

    def rest_chat_list_case_conversations(
        self,
        environ: dict[str, Any],
        case_id: str,
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_list_case_conversations(self, environ, case_id)

    def rest_chat_get_conversation(
        self,
        environ: dict[str, Any],
        conversation_id: str,
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_get_conversation(self, environ, conversation_id)

    def rest_chat_list_conversation_messages(
        self,
        environ: dict[str, Any],
        conversation_id: str,
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_list_conversation_messages(self, environ, conversation_id)

    def rest_chat_post_conversation_message(
        self,
        environ: dict[str, Any],
        conversation_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_post_conversation_message(self, environ, conversation_id, body)

    def rest_chat_case_conversation_timeline(
        self,
        environ: dict[str, Any],
        case_id: str,
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_case_conversation_timeline(self, environ, case_id)

    def _timeline_payload(self, case_id: str, viewer_id: str, *, message_limit: int = 50) -> dict[str, Any]:
        return _chat_timeline_payload(self, case_id, viewer_id, message_limit=message_limit)

    def rest_timeline(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_timeline(self, environ)

    def rest_chat_maintenance_run(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_maintenance_run(self, environ, body)

    def rest_get_chat_job(self, environ: dict[str, Any], job_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_get_chat_job(self, environ, job_id)

    def rest_list_chat_jobs(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_list_chat_jobs(self, environ)

    def rest_chat_get_summary(self, environ: dict[str, Any], thread_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_chat_get_summary(self, environ, thread_id)

    def rest_chat_submit_report(self, environ: dict[str, Any], thread_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_submit_report(self, environ, thread_id, body)

    def rest_chat_submit_meeting_feedback(
        self,
        environ: dict[str, Any],
        thread_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_submit_meeting_feedback(self, environ, thread_id, body)

    def rest_chat_list_reports(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_list_reports(self, environ)

    def rest_chat_list_meeting_feedback(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_list_meeting_feedback(self, environ)

    def rest_chat_list_risk_cases(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_list_risk_cases(self, environ)

    def rest_chat_list_risk_signals(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_list_risk_signals(self, environ)

    def rest_chat_record_fraud_network_observation(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_record_fraud_network_observation(self, environ, body)

    def rest_chat_evaluate_fraud_network(
        self,
        environ: dict[str, Any],
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_evaluate_fraud_network(self, environ, body)

    def rest_chat_list_fraud_networks(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_list_fraud_networks(self, environ)

    def rest_chat_get_fraud_network(self, environ: dict[str, Any], subject_user_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_chat_get_fraud_network(self, environ, subject_user_id)

    def rest_chat_get_risk_case(self, environ: dict[str, Any], risk_case_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_chat_get_risk_case(self, environ, risk_case_id)

    def rest_chat_thread_risk_overview(self, environ: dict[str, Any], thread_id: str) -> tuple[int, dict[str, Any]]:
        return _rest_chat_thread_risk_overview(self, environ, thread_id)

    def rest_chat_review_risk_case(
        self,
        environ: dict[str, Any],
        risk_case_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_review_risk_case(self, environ, risk_case_id, body)

    def rest_chat_batch_review_risk_cases(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_batch_review_risk_cases(self, environ, body)

    def rest_chat_submit_risk_appeal(
        self,
        environ: dict[str, Any],
        risk_case_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_submit_risk_appeal(self, environ, risk_case_id, body)

    def rest_chat_list_risk_appeals(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_list_risk_appeals(self, environ)

    def rest_chat_get_risk_appeal(self, environ: dict[str, Any], appeal_id: int) -> tuple[int, dict[str, Any]]:
        return _rest_chat_get_risk_appeal(self, environ, appeal_id)

    def rest_chat_review_risk_appeal(
        self,
        environ: dict[str, Any],
        appeal_id: int,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        return _rest_chat_review_risk_appeal(self, environ, appeal_id, body)

    def rest_chat_risk_dashboard(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return _rest_chat_risk_dashboard(self, environ)

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

        discovery_response = dispatch_discovery_rest(self, environ, method, path)
        if discovery_response is not None:
            return discovery_response

        verification_response = dispatch_verification_rest(self, environ, method, path)
        if verification_response is not None:
            return verification_response
        profile_response = dispatch_profile_rest(self, environ, method, path)
        if profile_response is not None:
            return profile_response
        recommendation_response = dispatch_recommendation_rest(self, environ, method, path)
        if recommendation_response is not None:
            return recommendation_response
        matchmaking_response = dispatch_matchmaking_rest(self, environ, method, path)
        if matchmaking_response is not None:
            return matchmaking_response
        chat_response = dispatch_chat_rest(self, environ, method, path)
        if chat_response is not None:
            return chat_response
        chat_safety_response = dispatch_chat_safety_rest(self, environ, method, path)
        if chat_safety_response is not None:
            return chat_safety_response

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
        handled = handle_verification_jsonrpc(self, environ, method, p)
        if handled is not VERIFICATION_JSONRPC_NOT_HANDLED:
            return handled
        handled = handle_recommendation_jsonrpc(self, environ, method, p)
        if handled is not RECOMMENDATION_JSONRPC_NOT_HANDLED:
            return handled

        handled = handle_matchmaking_jsonrpc(self, environ, method, p)
        if handled is not MATCHMAKING_JSONRPC_NOT_HANDLED:
            return handled

        handled = handle_chat_jsonrpc(self, environ, method, p)
        if handled is not JSONRPC_NOT_HANDLED:
            return handled

        handled = handle_profile_jsonrpc(self, environ, method, p)
        if handled is not PROFILE_JSONRPC_NOT_HANDLED:
            return handled

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

            public_auth_response = dispatch_public_auth_rest(self, environ, method, path.rstrip("/") or "/")
            if public_auth_response is not None:
                if not self._rate_limiter.allow(client_ip(environ)):
                    status_code = 429
                    body = json.dumps(
                        _gateway_error_payload("rate_limited", "Too many requests", trace_id),
                        ensure_ascii=False,
                    ).encode("utf-8")
                    sr("429 Too Many Requests", JSON_HEADERS + [("Content-Length", str(len(body)))])
                    _access_log(status_code)
                    return [body]
                status_code, payload = public_auth_response
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                reason = "OK" if status_code < 400 else "Error"
                sr(f"{status_code} {reason}", JSON_HEADERS + [("Content-Length", str(len(body)))])
                _access_log(status_code)
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
            emit_pipeline_record(
                her_kind="gateway_error",
                trace_id=trace_id,
                http_method=method,
                path=path,
                status_code=500,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            LOGGER.exception("Unhandled gateway error for %s %s trace_id=%s", method, path, trace_id)
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
