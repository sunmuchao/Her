"""Verification JSON-RPC handlers for the gateway."""

from __future__ import annotations

from typing import Any, Protocol

from chat_system import (  # type: ignore[import-untyped]
    create_live_video_verification_challenge,
    get_verification_submission,
    list_photo_review_requests,
    list_verification_notifications,
    list_verification_submissions,
    request_live_video_verification,
    resubmit_live_video_verification,
    review_live_video_verification,
    submit_live_video_verification,
)

from .role_sets import CHAT_RISK_REVIEW_ROLES, STAFF_OVERRIDE_ROLES, VERIFICATION_REVIEW_ROLES

JSONRPC_NOT_HANDLED = object()


class VerificationJsonrpcGateway(Protocol):
    def _assert_actor_can_access_owner(
        self,
        environ: dict[str, Any],
        owner_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> str: ...

    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _require_roles(
        self,
        environ: dict[str, Any],
        roles: frozenset[str],
        *,
        message: str,
    ) -> Any: ...

    def _resolve_actor_bound_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        allow_override_roles: frozenset[str] = STAFF_OVERRIDE_ROLES,
    ) -> str: ...

    def _resolve_operator_actor_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        roles: frozenset[str],
        message: str,
    ) -> str: ...

    def _resolve_optional_operator_actor_id(
        self,
        environ: dict[str, Any],
        supplied_id: Any,
        *,
        field_name: str,
        roles: frozenset[str],
        message: str,
    ) -> str | None: ...

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def _visible_user_id(
    gateway: VerificationJsonrpcGateway,
    environ: dict[str, Any],
    params: dict[str, Any],
) -> str | None:
    user_id = str(params["user_id"]) if params.get("user_id") is not None else None
    actor = gateway._current_actor(environ)
    if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
        user_id = gateway._resolve_actor_bound_id(environ, user_id, field_name="user_id")
    return user_id


def handle_verification_jsonrpc(
    gateway: VerificationJsonrpcGateway,
    environ: dict[str, Any],
    method: str,
    params: dict[str, Any],
) -> Any:
    if method == "verification.submit_live_video":
        user_id = gateway._resolve_actor_bound_id(environ, params.get("user_id"), field_name="user_id")
        return gateway._with_chat(
            submit_live_video_verification,
            user_id=user_id,
            video_base64=str(params.get("video_base64") or params.get("video_bytes_base64") or ""),
            file_name=str(params.get("file_name") or params.get("filename") or ""),
            submission_id=params.get("submission_id"),
            content_type=params.get("content_type"),
            profile_id=int(params["profile_id"]) if params.get("profile_id") is not None else None,
            source_dsn=params.get("source_dsn") or params.get("source"),
            source_table_name=params.get("source_table_name") or params.get("table_name"),
            challenge_token=params.get("challenge_token"),
            challenge_phrase=params.get("challenge_phrase"),
            metadata=params.get("metadata"),
            now=params.get("now"),
        )
    if method == "verification.request_live_video":
        gateway._require_roles(
            environ,
            VERIFICATION_REVIEW_ROLES | CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot request live video verification",
        )
        return gateway._with_chat(
            request_live_video_verification,
            user_id=str(params["user_id"]),
            profile_id=int(params["profile_id"]) if params.get("profile_id") is not None else None,
            source_dsn=params.get("source_dsn") or params.get("source"),
            source_table_name=params.get("source_table_name") or params.get("table_name"),
            request_source=str(params.get("request_source") or "risk_case_review"),
            request_reason=params.get("request_reason") or params.get("reason_text"),
            signal_codes=params.get("signal_codes") or params.get("reason_codes"),
            risk_case_id=params.get("risk_case_id"),
            report_ids=params.get("report_ids"),
            requested_by=gateway._resolve_optional_operator_actor_id(
                environ,
                params.get("requested_by") or params.get("resolver_id"),
                field_name="requested_by",
                roles=VERIFICATION_REVIEW_ROLES | CHAT_RISK_REVIEW_ROLES,
                message="current actor cannot request live video verification",
            ),
            due_at=params.get("due_at"),
            metadata=params.get("metadata"),
            now=params.get("now"),
        )
    if method == "verification.create_live_challenge":
        user_id = gateway._resolve_actor_bound_id(environ, params.get("user_id"), field_name="user_id")
        return create_live_video_verification_challenge(
            user_id=user_id,
            profile_id=int(params["profile_id"]) if params.get("profile_id") is not None else None,
            challenge_actions=params.get("challenge_actions") or params.get("required_actions"),
            challenge_action_pool=params.get("challenge_action_pool") or params.get("allowed_actions"),
            action_count=int(params.get("action_count", 3)),
            now=params.get("now"),
        )
    if method == "verification.list_submissions":
        return gateway._with_chat(
            list_verification_submissions,
            user_id=_visible_user_id(gateway, environ, params),
            statuses=params.get("statuses") or params.get("status"),
            profile_id=int(params["profile_id"]) if params.get("profile_id") is not None else None,
            limit=int(params.get("limit", 100)),
        )
    if method == "verification.list_photo_review_requests":
        return gateway._with_chat(
            list_photo_review_requests,
            user_id=_visible_user_id(gateway, environ, params),
            statuses=params.get("statuses") or params.get("status"),
            profile_id=int(params["profile_id"]) if params.get("profile_id") is not None else None,
            limit=int(params.get("limit", 100)),
        )
    if method == "verification.get_submission":
        submission = gateway._with_verification(get_verification_submission, str(params["submission_id"]))
        gateway._assert_actor_can_access_owner(environ, (submission or {}).get("user_id"), field_name="user_id")
        return submission
    if method == "verification.list_notifications":
        return gateway._with_chat(
            list_verification_notifications,
            submission_id=str(params["submission_id"]) if params.get("submission_id") is not None else None,
            user_id=_visible_user_id(gateway, environ, params),
            notification_types=params.get("types") or params.get("type"),
            limit=int(params.get("limit", 100)),
        )
    if method == "verification.resubmit_live_video":
        user_id = gateway._resolve_actor_bound_id(environ, params.get("user_id"), field_name="user_id")
        return gateway._with_chat(
            resubmit_live_video_verification,
            str(params["submission_id"]),
            user_id=user_id,
            video_base64=str(params.get("video_base64") or params.get("video_bytes_base64") or ""),
            file_name=str(params.get("file_name") or params.get("filename") or ""),
            content_type=params.get("content_type"),
            challenge_token=params.get("challenge_token"),
            challenge_phrase=params.get("challenge_phrase"),
            metadata=params.get("metadata"),
            now=params.get("now"),
        )
    if method == "verification.review_submission":
        reviewer_id = gateway._resolve_operator_actor_id(
            environ,
            params.get("reviewer_id"),
            field_name="reviewer_id",
            roles=VERIFICATION_REVIEW_ROLES,
            message="current actor cannot review live video submissions",
        )
        return gateway._with_chat(
            review_live_video_verification,
            str(params["submission_id"]),
            reviewer_id,
            decision=str(params["decision"]),
            review_note=params.get("review_note"),
            liveness_result=params.get("liveness_result"),
            face_match_result=params.get("face_match_result"),
            profile_consistency_result=params.get("profile_consistency_result"),
            metadata=params.get("metadata"),
            now=params.get("now"),
        )
    return JSONRPC_NOT_HANDLED
