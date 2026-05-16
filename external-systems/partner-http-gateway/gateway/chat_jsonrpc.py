"""Chat, trust, and timeline JSON-RPC handlers for the gateway."""

from __future__ import annotations

from typing import Any, Protocol

from match_domain import get_trace_id  # noqa: E402

from chat_system import (  # type: ignore[import-untyped]
    batch_review_risk_cases,
    build_case_conversation_timeline,
    build_fraud_network_overview,
    build_risk_case_playback,
    build_risk_weekly_dashboard,
    build_thread_risk_overview,
    build_user_trust_hub,
    create_assistant_case_layout,
    evaluate_fraud_network,
    get_conversation,
    get_or_create_thread,
    get_risk_appeal,
    get_thread,
    list_case_conversations,
    list_conversation_messages,
    list_fraud_network_profiles,
    list_member_reports,
    list_meeting_feedback,
    list_messages,
    list_pending_outbox,
    list_risk_appeals,
    list_risk_cases,
    list_risk_signals,
    post_conversation_message,
    post_message,
    record_fraud_network_observation,
    review_risk_appeal,
    review_risk_case,
    submit_meeting_feedback,
    submit_member_report,
    submit_risk_appeal,
)
from chat_system.async_tasks import (  # type: ignore[import-untyped]
    JOB_RUN_CHAT_MAINTENANCE,
    enqueue_chat_async_job,
    get_chat_async_job,
    list_chat_async_jobs,
    summarize_chat_async_jobs,
)
from chat_system.persona_jobs import process_pending_persona_jobs  # type: ignore[import-untyped]

from .chat_access import thread_visible_to_requester
from .chat_routes import timeline_payload
from .http_helpers import (
    _augment_chat_message_metadata,
    _normalize_boolish,
    _parse_int,
    _parse_optional_int,
    _payload_without_keys,
    _trimmed_client_idempotency_key,
)
from .identity import GatewayPermissionError
from .role_sets import CHAT_RISK_REVIEW_ROLES, INTERNAL_WRITE_ROLES, STAFF_OVERRIDE_ROLES

JSONRPC_NOT_HANDLED = object()


class ChatJsonrpcGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _job_collection_payload(self, target: str, jobs: Any, summary: Any) -> Any: ...

    def _job_payload(self, target: str, job: Any) -> Any: ...

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

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...

    def _with_mm(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...

    def _with_rec(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def _client_msg_kwargs(
    environ: dict[str, Any],
    params: dict[str, Any],
    *,
    augment_metadata: bool,
) -> dict[str, Any]:
    payload = _payload_without_keys(params, {"idempotency_key", "client_idempotency_key"})
    client_key = _trimmed_client_idempotency_key(
        params.get("client_idempotency_key") or params.get("idempotency_key")
    )
    if augment_metadata:
        payload["metadata"] = _augment_chat_message_metadata(environ, payload.get("metadata"))
    if client_key is not None:
        payload["client_msg_id"] = client_key
    return payload


def _chat_maintenance_payload(params: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "persona_limit": _parse_int(params.get("persona_limit"), 20),
        "summary_max_threads": _parse_int(params.get("summary_max_threads"), 30),
    }
    raw_flush = params.get("flush_outbox")
    if isinstance(raw_flush, bool):
        payload["flush_outbox"] = raw_flush
    elif isinstance(raw_flush, str):
        payload["flush_outbox"] = raw_flush.lower() in ("1", "true", "yes")
    return payload


def handle_chat_jsonrpc(
    gateway: ChatJsonrpcGateway,
    environ: dict[str, Any],
    method: str,
    params: dict[str, Any],
) -> Any:
    p = params
    if method == "chat.get_thread":
        requester_id = gateway._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
        thread = gateway._with_chat(get_thread, p["thread_id"])
        if not thread:
            raise ValueError("thread not found")
        if not thread_visible_to_requester(gateway, environ, thread, requester_id):
            raise GatewayPermissionError("requester is not a participant")
        return thread
    if method == "chat.get_or_create_thread":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot create chat threads",
        )
        return gateway._with_chat(get_or_create_thread, **p)
    if method == "chat.list_messages":
        requester_id = gateway._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
        return gateway._with_chat(
            list_messages,
            p["thread_id"],
            requester_id,
            limit=_parse_int(p.get("limit", 50), 50),
            before_message_id=_parse_optional_int(p.get("before_message_id")),
        )
    if method == "chat.post_message":
        payload = _client_msg_kwargs(environ, p, augment_metadata=True)
        thread_id = payload.pop("thread_id")
        author_id = gateway._resolve_actor_bound_id(environ, payload.pop("author_id", None), field_name="author_id")
        body_text = payload.pop("body")
        return gateway._with_chat(post_message, thread_id, author_id, body_text, **payload)
    if method == "chat.create_assistant_layout":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot create assistant layouts",
        )
        return gateway._with_chat(
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
        requester_id = gateway._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
        conversation = gateway._with_chat(get_conversation, p["conversation_id"])
        if not conversation:
            raise ValueError("conversation not found")
        conversations = gateway._with_chat(
            list_case_conversations,
            str(conversation["case_id"]),
            requester_id=requester_id,
        )
        for item in conversations:
            if str(item["conversation_id"]) == str(p["conversation_id"]):
                return item
        raise GatewayPermissionError("requester is not allowed to read this conversation")
    if method == "chat.list_case_conversations":
        requester_id = gateway._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
        return gateway._with_chat(
            list_case_conversations,
            str(p["case_id"]),
            requester_id=requester_id,
        )
    if method == "chat.list_conversation_messages":
        requester_id = gateway._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
        return gateway._with_chat(
            list_conversation_messages,
            p["conversation_id"],
            requester_id,
            limit=_parse_int(p.get("limit", 50), 50),
            before_message_id=_parse_optional_int(p.get("before_message_id")),
        )
    if method == "chat.post_conversation_message":
        payload = _client_msg_kwargs(environ, p, augment_metadata=False)
        conversation_id = payload.pop("conversation_id")
        author_id = gateway._resolve_actor_bound_id(environ, payload.pop("author_id", None), field_name="author_id")
        body_text = payload.pop("body")
        return gateway._with_chat(post_conversation_message, conversation_id, author_id, body_text, **payload)
    if method == "chat.get_case_conversation_timeline":
        requester_id = gateway._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
        return gateway._with_chat(
            build_case_conversation_timeline,
            str(p["case_id"]),
            requester_id,
            message_limit=_parse_int(p.get("message_limit", 50), 50),
        )
    if method == "chat.submit_member_report":
        reporter_id = gateway._resolve_actor_bound_id(environ, p.get("reporter_id"), field_name="reporter_id")
        return gateway._with_chat(
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
        reviewer_id = gateway._resolve_actor_bound_id(environ, p.get("reviewer_id"), field_name="reviewer_id")
        return gateway._with_chat(
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
        gateway._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot list chat reports",
        )
        return gateway._with_chat(
            list_member_reports,
            thread_id=p.get("thread_id"),
            risk_case_id=p.get("risk_case_id"),
            reported_user_id=p.get("reported_user_id"),
            limit=_parse_int(p.get("limit", 100), 100),
        )
    if method == "chat.list_meeting_feedback":
        reviewer_id = p.get("reviewer_id")
        actor = gateway._current_actor(environ)
        if actor is not None and not actor.has_any_role(STAFF_OVERRIDE_ROLES):
            reviewer_id = gateway._resolve_actor_bound_id(environ, reviewer_id, field_name="reviewer_id")
        return gateway._with_chat(
            list_meeting_feedback,
            thread_id=p.get("thread_id"),
            counterpart_user_id=p.get("counterpart_user_id"),
            reviewer_id=reviewer_id,
            limit=_parse_int(p.get("limit", 100), 100),
        )
    if method == "chat.list_risk_cases":
        gateway._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot list chat risk cases",
        )
        return gateway._with_chat(
            list_risk_cases,
            statuses=p.get("statuses"),
            subject_user_id=p.get("subject_user_id"),
            thread_id=p.get("thread_id"),
            limit=_parse_int(p.get("limit", 100), 100),
        )
    if method == "chat.list_risk_signals":
        gateway._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot list chat risk signals",
        )
        return gateway._with_chat(
            list_risk_signals,
            thread_id=p.get("thread_id"),
            subject_user_id=p.get("subject_user_id"),
            signal_code=p.get("signal_code"),
            limit=_parse_int(p.get("limit", 100), 100),
        )
    if method == "chat.record_fraud_network_observation":
        gateway._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
            message="current actor cannot record fraud network observations",
        )
        return gateway._with_chat(
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
        gateway._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
            message="current actor cannot evaluate fraud networks",
        )
        return gateway._with_chat(
            evaluate_fraud_network,
            str(p["subject_user_id"]),
            source_dsn=p.get("source_dsn") or p.get("source"),
            source_table_name=p.get("source_table_name") or p.get("table_name"),
            profile_id=int(p["profile_id"]) if p.get("profile_id") is not None else None,
            now=p.get("now"),
            propagate=_normalize_boolish(p.get("propagate"), default=True),
        )
    if method == "chat.list_fraud_networks":
        gateway._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot list fraud networks",
        )
        return gateway._with_chat(
            list_fraud_network_profiles,
            review_statuses=p.get("review_statuses") or p.get("statuses"),
            subject_user_id=p.get("subject_user_id"),
            minimum_score=int(p["minimum_score"]) if p.get("minimum_score") is not None else None,
            limit=_parse_int(p.get("limit", 100), 100),
        )
    if method == "chat.get_fraud_network":
        gateway._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot inspect fraud networks",
        )
        return gateway._with_chat(build_fraud_network_overview, str(p["subject_user_id"]))
    if method == "chat.get_risk_case":
        gateway._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot inspect chat risk cases",
        )
        return gateway._with_chat(build_risk_case_playback, p["risk_case_id"])
    if method == "chat.review_risk_case":
        resolver_id = gateway._resolve_operator_actor_id(
            environ,
            p.get("resolver_id"),
            field_name="resolver_id",
            roles=CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot review chat risk cases",
        )
        return gateway._with_chat(
            review_risk_case,
            p["risk_case_id"],
            resolver_id,
            status=str(p["status"]),
            applied_action=p.get("applied_action"),
            resolution_note=p.get("resolution_note"),
            now=p.get("now"),
        )
    if method == "chat.get_thread_risk_overview":
        requester_id = gateway._resolve_actor_bound_id(environ, p.get("requester_id"), field_name="requester_id")
        return gateway._with_chat(build_thread_risk_overview, p["thread_id"], requester_id)
    if method == "chat.submit_risk_appeal":
        appellant_id = gateway._resolve_actor_bound_id(environ, p.get("appellant_id"), field_name="appellant_id")
        return gateway._with_chat(
            submit_risk_appeal,
            p["risk_case_id"],
            appellant_id,
            reason_text=str(p["reason_text"]),
            evidence=p.get("evidence"),
            now=p.get("now"),
        )
    if method == "chat.list_risk_appeals":
        gateway._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot list chat risk appeals",
        )
        return gateway._with_chat(
            list_risk_appeals,
            statuses=p.get("statuses"),
            risk_case_id=p.get("risk_case_id"),
            subject_user_id=p.get("subject_user_id"),
            limit=_parse_int(p.get("limit", 100), 100),
        )
    if method == "chat.get_risk_appeal":
        gateway._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot inspect chat risk appeals",
        )
        return gateway._with_chat(get_risk_appeal, int(p["appeal_id"]))
    if method == "chat.review_risk_appeal":
        resolver_id = gateway._resolve_operator_actor_id(
            environ,
            p.get("resolver_id"),
            field_name="resolver_id",
            roles=CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot review chat risk appeals",
        )
        return gateway._with_chat(
            review_risk_appeal,
            int(p["appeal_id"]),
            resolver_id,
            appeal_status=str(p["appeal_status"]),
            resolution_note=p.get("resolution_note"),
            now=p.get("now"),
        )
    if method == "chat.batch_review_risk_cases":
        resolver_id = gateway._resolve_operator_actor_id(
            environ,
            p.get("resolver_id"),
            field_name="resolver_id",
            roles=CHAT_RISK_REVIEW_ROLES,
            message="current actor cannot batch review chat risk cases",
        )
        return gateway._with_chat(
            batch_review_risk_cases,
            risk_case_ids=p.get("risk_case_ids") or [],
            resolver_id=resolver_id,
            status=str(p["status"]),
            applied_action=p.get("applied_action"),
            resolution_note=p.get("resolution_note"),
            now=p.get("now"),
        )
    if method == "chat.get_risk_weekly_dashboard":
        gateway._require_roles(
            environ,
            CHAT_RISK_REVIEW_ROLES | INTERNAL_WRITE_ROLES,
            message="current actor cannot view the risk dashboard",
        )
        return gateway._with_chat(
            build_risk_weekly_dashboard,
            now=p.get("now"),
            days=int(p.get("days", 7)),
        )
    if method == "user.get_trust_hub":
        user_id = gateway._resolve_actor_bound_id(environ, p.get("user_id"), field_name="user_id")
        return gateway._with_chat(
            build_user_trust_hub,
            user_id=user_id,
            profile_id=int(p["profile_id"]) if p.get("profile_id") is not None else None,
            limit=_parse_int(p.get("limit", 20), 20),
        )
    if method == "timeline.get_for_case":
        viewer_id = gateway._resolve_actor_bound_id(environ, p.get("viewer_id"), field_name="viewer_id")
        return timeline_payload(
            gateway,
            str(p["case_id"]),
            viewer_id,
            message_limit=_parse_int(p.get("message_limit", 50), 50),
        )
    if method == "chat.list_pending_outbox":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect chat outbox",
        )
        return gateway._with_chat(list_pending_outbox, limit=_parse_int(p.get("limit", 100), 100))
    if method == "chat.process_persona_jobs":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot process persona jobs",
        )
        return gateway._with_chat(process_pending_persona_jobs, limit=_parse_int(p.get("limit", 20), 20))
    if method == "chat.run_maintenance":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot run chat maintenance",
        )
        actor = gateway._current_actor(environ)
        job = gateway._with_chat(
            enqueue_chat_async_job,
            job_type=JOB_RUN_CHAT_MAINTENANCE,
            payload=_chat_maintenance_payload(p),
            created_by=actor.actor_id if actor is not None else None,
            trace_id=get_trace_id(),
        )
        return gateway._job_payload("chat", job)
    if method == "chat.get_async_job":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect chat jobs",
        )
        job = gateway._with_chat(get_chat_async_job, str(p["job_id"]))
        if not job:
            raise ValueError("job not found")
        return gateway._job_payload("chat", job)
    if method == "chat.list_async_jobs":
        gateway._require_roles(
            environ,
            INTERNAL_WRITE_ROLES,
            message="current actor cannot inspect chat jobs",
        )
        statuses = p.get("statuses")
        if statuses is not None and not isinstance(statuses, list):
            raise ValueError("statuses must be a list")
        jobs = gateway._with_chat(
            list_chat_async_jobs,
            statuses=statuses,
            limit=int(p.get("limit", 50)),
        )
        summary = gateway._with_chat(summarize_chat_async_jobs)
        return gateway._job_collection_payload("chat", jobs, summary)
    return JSONRPC_NOT_HANDLED
