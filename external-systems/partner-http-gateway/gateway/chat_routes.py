"""Chat-centric HTTP handlers for the gateway."""

from __future__ import annotations

import re
from typing import Any, Protocol

from match_domain import get_trace_id  # noqa: E402

from recommendation_system import (  # type: ignore[import-untyped]
    get_match_case as recommendation_get_match_case,
    list_match_case_events as recommendation_list_match_case_events,
)
from matchmaking_system import (  # type: ignore[import-untyped]
    get_match_case,
    list_match_case_events,
)
from chat_system import (  # type: ignore[import-untyped]
    build_case_conversation_timeline,
    build_chat_timeline,
    create_assistant_case_layout,
    get_conversation,
    get_or_create_thread,
    get_thread,
    get_thread_summary,
    list_case_conversations,
    list_conversation_messages,
    list_messages,
    post_conversation_message,
    post_message,
)
from chat_system.async_tasks import (  # type: ignore[import-untyped]
    JOB_RUN_CHAT_MAINTENANCE,
    enqueue_chat_async_job,
    get_chat_async_job,
    list_chat_async_jobs,
    summarize_chat_async_jobs,
)

from .chat_access import thread_visible_to_requester
from .http_helpers import (
    _augment_chat_message_metadata,
    _extract_client_idempotency_key,
    _json_safe,
    _parse_int,
    _parse_optional_int,
    _parse_json_body,
    _parse_optional_now,
    _payload_without_keys,
    _query_dict,
    _read_body,
)
from .role_sets import INTERNAL_WRITE_ROLES, STAFF_OVERRIDE_ROLES


class ChatGateway(Protocol):
    def _current_actor(self, environ: dict[str, Any]) -> Any: ...

    def _enqueue_async_job(
        self,
        environ: dict[str, Any],
        *,
        target: str,
        with_fn: Any,
        enqueue_fn: Any,
        job_type: str,
        payload: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]: ...

    def _get_async_job(
        self,
        *,
        target: str,
        with_fn: Any,
        get_fn: Any,
        job_id: str,
    ) -> tuple[int, dict[str, Any]]: ...

    def _list_async_jobs(
        self,
        environ: dict[str, Any],
        *,
        target: str,
        with_fn: Any,
        list_fn: Any,
        summary_fn: Any,
    ) -> tuple[int, dict[str, Any]]: ...

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

    def _with_chat(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...

    def _with_mm(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...

    def _with_rec(self, fn: Any, *args: Any, **kwargs: Any) -> Any: ...


def chat_require_requester(
    gateway: ChatGateway,
    environ: dict[str, Any],
    q: dict[str, str],
    body: dict[str, Any] | None = None,
) -> str:
    requester_id = (q.get("requester_id") or "").strip()
    if not requester_id and body:
        requester_id = str(body.get("requester_id") or "").strip()
    return gateway._resolve_actor_bound_id(environ, requester_id, field_name="requester_id")


def _load_requester_thread(
    gateway: ChatGateway,
    environ: dict[str, Any],
    thread_id: str,
) -> tuple[str, dict[str, Any] | None]:
    requester_id = chat_require_requester(gateway, environ, _query_dict(environ))
    thread = gateway._with_chat(get_thread, thread_id)
    return requester_id, thread


def _message_page_params(q: dict[str, str]) -> tuple[int, int | None]:
    return _parse_int(q.get("limit") or "50", 50), _parse_optional_int(q.get("before_message_id"))


def _post_chat_message(
    gateway: ChatGateway,
    environ: dict[str, Any],
    target_id: str,
    body: dict[str, Any],
    *,
    post_fn: Any,
    augment_metadata: bool,
) -> tuple[int, dict[str, Any]]:
    now = _parse_optional_now(body)
    kwargs = _payload_without_keys(body, {"now", "idempotency_key", "client_idempotency_key"})
    idem = _extract_client_idempotency_key(environ, body)
    if augment_metadata:
        kwargs["metadata"] = _augment_chat_message_metadata(environ, kwargs.get("metadata"))
    if idem:
        kwargs["client_msg_id"] = idem
    if now is not None:
        kwargs["now"] = now
    if kwargs.get("body") is None:
        raise ValueError("body is required")
    author_id = gateway._resolve_actor_bound_id(
        environ,
        kwargs.pop("author_id", None),
        field_name="author_id",
    )
    body_text = kwargs.pop("body")
    msg = gateway._with_chat(post_fn, target_id, author_id, body_text, **kwargs)
    out: dict[str, Any] = {"message": _json_safe(msg), "trace_id": get_trace_id()}
    if idem:
        out["client_idempotency_key"] = idem
    return 201, out


def timeline_payload(
    gateway: ChatGateway,
    case_id: str,
    viewer_id: str,
    *,
    message_limit: int = 50,
) -> dict[str, Any]:
    chat_part = gateway._with_chat(build_chat_timeline, case_id, viewer_id, message_limit=message_limit)
    try:
        case = gateway._with_mm(get_match_case, case_id)
        events = gateway._with_mm(list_match_case_events, case_id)
        mm_part = {"case": _json_safe(case), "events": _json_safe(events)}
    except ValueError:
        mm_part = {"case": None, "events": []}
    rec_part: dict[str, Any] = {"case": None, "events": []}
    try:
        rec_case = gateway._with_rec(recommendation_get_match_case, case_id)
        if rec_case:
            rec_events = gateway._with_rec(recommendation_list_match_case_events, case_id)
            rec_part = {"case": _json_safe(rec_case), "events": _json_safe(rec_events)}
    except Exception:
        rec_part = {"case": None, "events": []}
    return {
        "case_id": case_id,
        "viewer_id": viewer_id,
        "chat": _json_safe(chat_part),
        "matchmaking": mm_part,
        "recommendation": rec_part,
    }


def rest_chat_create_thread(
    gateway: ChatGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot create chat threads",
    )
    now = _parse_optional_now(body)
    kwargs = {key: value for key, value in body.items() if key != "now"}
    if now is not None:
        kwargs["now"] = now
    for key in ("case_id", "relation_key", "participant_a_id", "participant_b_id"):
        if not kwargs.get(key):
            raise ValueError(f"{key} is required")
    thread = gateway._with_chat(get_or_create_thread, **kwargs)
    return 201, {"thread": _json_safe(thread)}


def rest_chat_get_thread(
    gateway: ChatGateway,
    environ: dict[str, Any],
    thread_id: str,
) -> tuple[int, dict[str, Any]]:
    requester_id, thread = _load_requester_thread(gateway, environ, thread_id)
    if not thread:
        return 404, {"error": {"code": "not_found", "message": "thread not found"}}
    if not thread_visible_to_requester(gateway, environ, thread, requester_id):
        return 403, {"error": {"code": "forbidden", "message": "requester is not a participant"}}
    return 200, {"thread": _json_safe(thread)}


def rest_chat_list_messages(
    gateway: ChatGateway,
    environ: dict[str, Any],
    thread_id: str,
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    requester_id = chat_require_requester(gateway, environ, q)
    limit, before_message_id = _message_page_params(q)
    rows = gateway._with_chat(
        list_messages,
        thread_id,
        requester_id,
        limit=limit,
        before_message_id=before_message_id,
    )
    return 200, {"messages": _json_safe(rows)}


def rest_chat_post_message(
    gateway: ChatGateway,
    environ: dict[str, Any],
    thread_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    return _post_chat_message(
        gateway,
        environ,
        thread_id,
        body,
        post_fn=post_message,
        augment_metadata=True,
    )


def rest_chat_create_assistant_layout(
    gateway: ChatGateway,
    environ: dict[str, Any],
    case_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
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
    layout = gateway._with_chat(
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
    gateway: ChatGateway,
    environ: dict[str, Any],
    case_id: str,
) -> tuple[int, dict[str, Any]]:
    requester_id = chat_require_requester(gateway, environ, _query_dict(environ))
    conversations = gateway._with_chat(
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
    gateway: ChatGateway,
    environ: dict[str, Any],
    conversation_id: str,
) -> tuple[int, dict[str, Any]]:
    requester_id = chat_require_requester(gateway, environ, _query_dict(environ))
    conversation = gateway._with_chat(get_conversation, conversation_id)
    if not conversation:
        return 404, {"error": {"code": "not_found", "message": "conversation not found"}}
    conversations = gateway._with_chat(
        list_case_conversations,
        str(conversation["case_id"]),
        requester_id=requester_id,
    )
    for item in conversations:
        if str(item["conversation_id"]) == str(conversation_id):
            return 200, {"conversation": _json_safe(item)}
    return 403, {"error": {"code": "forbidden", "message": "requester is not allowed to read this conversation"}}


def rest_chat_list_conversation_messages(
    gateway: ChatGateway,
    environ: dict[str, Any],
    conversation_id: str,
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    requester_id = chat_require_requester(gateway, environ, q)
    limit, before_message_id = _message_page_params(q)
    rows = gateway._with_chat(
        list_conversation_messages,
        conversation_id,
        requester_id,
        limit=limit,
        before_message_id=before_message_id,
    )
    return 200, {"messages": _json_safe(rows)}


def rest_chat_post_conversation_message(
    gateway: ChatGateway,
    environ: dict[str, Any],
    conversation_id: str,
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    return _post_chat_message(
        gateway,
        environ,
        conversation_id,
        body,
        post_fn=post_conversation_message,
        augment_metadata=False,
    )


def rest_chat_case_conversation_timeline(
    gateway: ChatGateway,
    environ: dict[str, Any],
    case_id: str,
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    requester_id = chat_require_requester(gateway, environ, q)
    out = gateway._with_chat(
        build_case_conversation_timeline,
        str(case_id),
        requester_id,
        message_limit=_parse_int(q.get("message_limit") or "50", 50),
    )
    return 200, _json_safe(out)


def rest_timeline(
    gateway: ChatGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    q = _query_dict(environ)
    case_id = (q.get("case_id") or "").strip()
    viewer_id = gateway._resolve_actor_bound_id(environ, q.get("viewer_id"), field_name="viewer_id")
    if not case_id:
        raise ValueError("case_id is required")
    return 200, timeline_payload(
        gateway,
        case_id,
        viewer_id,
        message_limit=_parse_int(q.get("message_limit") or "50", 50),
    )


def rest_chat_maintenance_run(
    gateway: ChatGateway,
    environ: dict[str, Any],
    body: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot run chat maintenance",
    )
    payload: dict[str, Any] = {
        "persona_limit": _parse_int(body.get("persona_limit"), 20),
        "summary_max_threads": _parse_int(body.get("summary_max_threads"), 30),
    }
    raw_flush = body.get("flush_outbox")
    if isinstance(raw_flush, bool):
        payload["flush_outbox"] = raw_flush
    elif isinstance(raw_flush, str):
        payload["flush_outbox"] = raw_flush.lower() in ("1", "true", "yes")
    return gateway._enqueue_async_job(
        environ,
        target="chat",
        with_fn=gateway._with_chat,
        enqueue_fn=enqueue_chat_async_job,
        job_type=JOB_RUN_CHAT_MAINTENANCE,
        payload=payload,
    )


def rest_get_chat_job(
    gateway: ChatGateway,
    environ: dict[str, Any],
    job_id: str,
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot inspect chat jobs",
    )
    return gateway._get_async_job(
        target="chat",
        with_fn=gateway._with_chat,
        get_fn=get_chat_async_job,
        job_id=job_id,
    )


def rest_list_chat_jobs(
    gateway: ChatGateway,
    environ: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    gateway._require_roles(
        environ,
        INTERNAL_WRITE_ROLES,
        message="current actor cannot inspect chat jobs",
    )
    return gateway._list_async_jobs(
        environ,
        target="chat",
        with_fn=gateway._with_chat,
        list_fn=list_chat_async_jobs,
        summary_fn=summarize_chat_async_jobs,
    )


def rest_chat_get_summary(
    gateway: ChatGateway,
    environ: dict[str, Any],
    thread_id: str,
) -> tuple[int, dict[str, Any]]:
    requester_id, thread = _load_requester_thread(gateway, environ, thread_id)
    if not thread:
        return 404, {"error": {"code": "not_found", "message": "thread not found"}}
    if not thread_visible_to_requester(gateway, environ, thread, requester_id):
        return 403, {"error": {"code": "forbidden", "message": "requester is not a participant"}}
    summary = gateway._with_chat(get_thread_summary, thread_id)
    return 200, {"thread_id": thread_id, "summary": _json_safe(summary)}


def dispatch_chat_rest(
    gateway: ChatGateway,
    environ: dict[str, Any],
    method: str,
    path: str,
) -> tuple[int, dict[str, Any]] | None:
    if path == "/v1/timeline" and method == "GET":
        return rest_timeline(gateway, environ)
    match = re.fullmatch(r"/v2/chat/cases/([^/]+)/assistant-layout", path)
    if match and method == "POST":
        return rest_chat_create_assistant_layout(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    match = re.fullmatch(r"/v2/chat/cases/([^/]+)/conversations", path)
    if match and method == "GET":
        return rest_chat_list_case_conversations(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v2/chat/cases/([^/]+)/timeline", path)
    if match and method == "GET":
        return rest_chat_case_conversation_timeline(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v2/chat/conversations/([^/]+)/messages", path)
    if match and method == "POST":
        return rest_chat_post_conversation_message(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    if match and method == "GET":
        return rest_chat_list_conversation_messages(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v2/chat/conversations/([^/]+)", path)
    if match and method == "GET":
        return rest_chat_get_conversation(gateway, environ, match.group(1))
    if path == "/v1/chat/maintenance/run" and method == "POST":
        return rest_chat_maintenance_run(gateway, environ, _parse_json_body(_read_body(environ)))
    if path == "/v1/chat/jobs" and method == "GET":
        return rest_list_chat_jobs(gateway, environ)
    match = re.fullmatch(r"/v1/chat/jobs/([^/]+)", path)
    if match and method == "GET":
        return rest_get_chat_job(gateway, environ, match.group(1))
    if path == "/v1/chat/threads" and method == "POST":
        return rest_chat_create_thread(gateway, environ, _parse_json_body(_read_body(environ)))
    match = re.fullmatch(r"/v1/chat/threads/([^/]+)/summary", path)
    if match and method == "GET":
        return rest_chat_get_summary(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v1/chat/threads/([^/]+)/messages", path)
    if match and method == "POST":
        return rest_chat_post_message(
            gateway,
            environ,
            match.group(1),
            _parse_json_body(_read_body(environ)),
        )
    if match and method == "GET":
        return rest_chat_list_messages(gateway, environ, match.group(1))
    match = re.fullmatch(r"/v1/chat/threads/([^/]+)", path)
    if match and method == "GET":
        return rest_chat_get_thread(gateway, environ, match.group(1))
    return None
