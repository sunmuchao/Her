"""WSGI app: REST JSON under /v1/... and JSON-RPC 2.0 under POST /jsonrpc."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from typing import Any, Callable
from urllib.parse import parse_qs, unquote

from . import _paths  # noqa: F401 — side effect: sys.path

from match_domain import get_trace_id, new_trace_id, reset_trace_id, set_trace_id  # noqa: E402
from observability import emit_pipeline_record  # noqa: E402
from outer_system_mysql_schema import chat_tables, matchmaking_tables, recommendation_tables  # noqa: E402
from skill_runtime import ensure_partner_search_skill_on_path  # noqa: E402

ensure_partner_search_skill_on_path()
from partner_search import search_profiles as partner_search_profiles  # noqa: E402

from recommendation_system import (  # type: ignore[import-untyped]
    connect_db as recommendation_connect_db,
    create_subscription,
    deliver_in_app_recommendations,
    get_match_case as recommendation_get_match_case,
    get_subscription,
    list_in_app_cards,
    list_match_case_events as recommendation_list_match_case_events,
    list_recommendations_for_subscription,
    list_search_runs_for_subscription,
    mark_in_app_cards_read,
    record_recommendation_action,
    record_user_review,
    refresh_due_subscriptions,
    refresh_subscription,
    update_subscription_overrides,
)
from recommendation_system.storage import (  # type: ignore[import-untyped]
    DEFAULT_RECOMMENDATION_MYSQL_DSN,
)
from matchmaking_system import (  # type: ignore[import-untyped]
    build_mutual_pairs,
    close_stale_cases,
    connect_db as matchmaking_connect_db,
    create_pool_member,
    dispatch_case_contact,
    get_match_case,
    get_pair,
    get_pool_member,
    list_match_case_events,
    list_match_cases,
    list_pairs,
    open_match_cases,
    record_case_reply,
    record_feedback,
    refresh_active_pool,
    refresh_pool_member,
    set_pool_member_status,
)
from matchmaking_system.storage import (  # type: ignore[import-untyped]
    DEFAULT_MATCHMAKING_MYSQL_DSN,
)
from chat_system import (  # type: ignore[import-untyped]
    adopt_draft,
    assistant_query,
    build_thread_risk_overview,
    build_chat_timeline,
    get_risk_case,
    get_or_create_thread,
    get_thread,
    get_thread_summary,
    list_member_reports,
    list_meeting_feedback,
    list_messages,
    list_pending_outbox,
    list_risk_cases,
    list_risk_signals,
    post_message,
    review_risk_case,
    run_chat_maintenance,
    submit_meeting_feedback,
    submit_member_report,
)
from chat_system.persona_jobs import (  # type: ignore[import-untyped]
    list_pending_persona_jobs,
    process_pending_persona_jobs,
)
from chat_system.storage import (  # type: ignore[import-untyped]
    DEFAULT_CHAT_MYSQL_DSN,
    connect_db as chat_connect_db,
)

from .mysql_pool import GatewayConnectionPool
from .request_policy import ApiKeyGuard, client_ip, rate_limiter_from_environ

JSON_HEADERS = [("Content-Type", "application/json; charset=utf-8")]

RouteHandler = Callable[..., tuple[int, dict[str, Any]]]


def _incoming_trace_id(environ: dict[str, Any]) -> str:
    raw = (
        (environ.get("HTTP_X_TRACE_ID") or "").strip()
        or (environ.get("HTTP_X_REQUEST_ID") or "").strip()
    )
    if raw and len(raw) <= 128:
        return raw
    return new_trace_id()


def _wrap_trace_headers(base: Callable[..., Any], trace_id: str) -> Callable[..., Any]:
    def sr(status: str, response_headers: list[tuple[str, str]], exc_info: Any = None) -> Any:
        merged = list(response_headers)
        if not any(h[0].lower() == "x-trace-id" for h in merged):
            merged.append(("X-Trace-ID", trace_id))
        # Some test doubles only implement the 2-arg WSGI ``start_response`` signature.
        if exc_info is not None:
            return base(status, merged, exc_info)
        return base(status, merged)

    return sr


def _extract_client_idempotency_key(environ: dict[str, Any], body: dict[str, Any]) -> str | None:
    h = (environ.get("HTTP_IDEMPOTENCY_KEY") or "").strip()
    if h:
        return h[:191]
    v = body.get("client_idempotency_key") if isinstance(body, dict) else None
    if v is None and isinstance(body, dict):
        v = body.get("idempotency_key")
    if v is not None and str(v).strip():
        return str(v).strip()[:191]
    return None


def _gateway_error_payload(code: str, message: str, trace_id: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}, "trace_id": trace_id}


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    return value


def _read_body(environ: dict[str, Any], max_bytes: int = 8 * 1024 * 1024) -> bytes:
    try:
        size = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        size = 0
    if size > max_bytes:
        raise ValueError("Request body too large")
    stream = environ["wsgi.input"]
    return stream.read(size) if size else stream.read()


def _parse_json_body(raw: bytes) -> dict[str, Any]:
    if not raw:
        return {}
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def _parse_optional_now(params: dict[str, Any]) -> datetime | None:
    raw = params.get("now")
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(str(raw))


def _query_dict(environ: dict[str, Any]) -> dict[str, str]:
    qs = environ.get("QUERY_STRING") or ""
    parsed = parse_qs(qs, keep_blank_values=True)
    return {k: v[-1] if v else "" for k, v in parsed.items()}


def _normalize_boolish(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _subscription_ids_from_query(q: dict[str, str]) -> list[str] | None:
    raw = q.get("subscription_ids") or q.get("ids")
    if not raw:
        return None
    return [s.strip() for s in raw.split(",") if s.strip()]


def _statuses_from_query(q: dict[str, str], key: str = "status") -> list[str] | None:
    raw = q.get(key) or q.get("statuses")
    if not raw:
        return None
    return [s.strip() for s in raw.split(",") if s.strip()]


class PartnerGateway:
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
            self._rec_pool = GatewayConnectionPool(self._recommendation_dsn, recommendation_tables, max_size=pool_n)
            self._mm_pool = GatewayConnectionPool(self._matchmaking_dsn, matchmaking_tables, max_size=pool_n)
            self._chat_pool = GatewayConnectionPool(self._chat_dsn, chat_tables, max_size=pool_n)
        self._api_guard = ApiKeyGuard()
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
            "api_key_required": self._api_guard.required,
            "rate_limit_per_minute": int(os.environ.get("PARTNER_GATEWAY_RATE_LIMIT_PER_MINUTE", "600") or "600"),
        }

    def rest_get_subscription(self, _environ: dict[str, Any], subscription_id: str) -> tuple[int, dict[str, Any]]:
        sub = self._with_rec(get_subscription, subscription_id)
        return 200, {"subscription": _json_safe(sub)}

    def rest_create_subscription(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if now is not None:
            kwargs["now"] = now
        sub = self._with_rec(create_subscription, **kwargs)
        return 201, {"subscription": _json_safe(sub)}

    def rest_patch_overrides(self, _environ: dict[str, Any], subscription_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        now = _parse_optional_now(body)
        overrides = body.get("overrides")
        if overrides is None:
            overrides = {k: v for k, v in body.items() if k not in {"now"}}
        sub = self._with_rec(update_subscription_overrides, subscription_id, overrides, now=now)
        return 200, {"subscription": _json_safe(sub)}

    def rest_refresh_subscription(self, _environ: dict[str, Any], subscription_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        now = _parse_optional_now(body)
        out = self._with_rec(refresh_subscription, subscription_id, now=now)
        return 200, _json_safe(out)

    def rest_refresh_due(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        ids = _subscription_ids_from_query(q) or body.get("subscription_ids")
        now = _parse_optional_now(body)
        if now is None and q.get("now"):
            now = datetime.fromisoformat(q["now"])
        out = self._with_rec(refresh_due_subscriptions, now=now, subscription_ids=ids)
        return 200, {"summaries": _json_safe(out.get("summaries", [])), "errors": _json_safe(out.get("errors", []))}

    def rest_list_recommendations(self, _environ: dict[str, Any], subscription_id: str) -> tuple[int, dict[str, Any]]:
        rows = self._with_rec(list_recommendations_for_subscription, subscription_id)
        return 200, {"recommendations": _json_safe(rows)}

    def rest_list_runs(self, _environ: dict[str, Any], subscription_id: str) -> tuple[int, dict[str, Any]]:
        rows = self._with_rec(list_search_runs_for_subscription, subscription_id)
        return 200, {"runs": _json_safe(rows)}

    def rest_list_cards(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = q.get("requester_id")
        rid = int(requester_id) if requester_id else None
        unread = str(q.get("unread_only", "")).lower() in ("1", "true", "yes")
        cards = self._with_rec(list_in_app_cards, requester_id=rid, unread_only=unread)
        return 200, {"cards": _json_safe(cards)}

    def rest_deliver(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        out = self._with_rec(deliver_in_app_recommendations, now=now)
        return 200, _json_safe(out)

    def rest_record_action(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k not in {"now", "idempotency_key", "client_idempotency_key"}}
        idem = _extract_client_idempotency_key(environ, body)
        if idem:
            kwargs["client_idempotency_key"] = idem
        if now is not None:
            kwargs["now"] = now
        rec = self._with_rec(record_recommendation_action, **kwargs)
        out: dict[str, Any] = {"recommendation": _json_safe(rec)}
        if idem:
            out["client_idempotency_key"] = idem
        out["trace_id"] = get_trace_id()
        return 200, out

    def rest_record_review(self, environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k not in {"now", "idempotency_key", "client_idempotency_key"}}
        idem = _extract_client_idempotency_key(environ, body)
        if idem:
            kwargs["client_idempotency_key"] = idem
        if now is not None:
            kwargs["now"] = now
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
        )
        return 200, _json_safe(response)

    def rest_mark_cards_read(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        rid = body.get("requester_id")
        if rid is None:
            raise ValueError("requester_id is required")
        card_ids = body.get("card_ids")
        if not isinstance(card_ids, list):
            raise ValueError("card_ids must be a list of card_id strings")
        out = self._with_rec(
            mark_in_app_cards_read,
            requester_id=int(rid),
            card_ids=[str(x) for x in card_ids],
            now=now,
        )
        return 200, {**_json_safe(out), "trace_id": get_trace_id()}

    def rest_mm_create_member(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if now is not None:
            kwargs["now"] = now
        member = self._with_mm(create_pool_member, **kwargs)
        return 201, {"member": _json_safe(member)}

    def rest_mm_get_member(self, _environ: dict[str, Any], member_id: str) -> tuple[int, dict[str, Any]]:
        member = self._with_mm(get_pool_member, member_id)
        return 200, {"member": _json_safe(member)}

    def rest_mm_set_status(self, _environ: dict[str, Any], member_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if now is not None:
            kwargs["now"] = now
        member = self._with_mm(set_pool_member_status, member_id, **kwargs)
        return 200, {"member": _json_safe(member)}

    def rest_mm_refresh_member(self, _environ: dict[str, Any], member_id: str, body: dict[str, Any]) -> tuple[
        int, dict[str, Any]
    ]:
        now = _parse_optional_now(body)
        out = self._with_mm(refresh_pool_member, member_id, now=now)
        return 200, _json_safe(out)

    def rest_mm_refresh_pool(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        ids = body.get("member_ids")
        out = self._with_mm(refresh_active_pool, now=now, member_ids=ids)
        return 200, {"summaries": _json_safe(out)}

    def rest_mm_build_pairs(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        pairs = self._with_mm(build_mutual_pairs, now=now)
        return 200, {"pairs": _json_safe(pairs)}

    def rest_mm_open_cases(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if now is not None:
            kwargs["now"] = now
        cases = self._with_mm(open_match_cases, **kwargs)
        return 200, {"cases": _json_safe(cases)}

    def rest_mm_get_case(self, _environ: dict[str, Any], case_id: str) -> tuple[int, dict[str, Any]]:
        case = self._with_mm(get_match_case, case_id)
        return 200, {"case": _json_safe(case)}

    def rest_mm_list_cases(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        statuses = _statuses_from_query(q)
        cases = self._with_mm(list_match_cases, statuses=statuses)
        return 200, {"cases": _json_safe(cases)}

    def rest_mm_list_pairs(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        statuses = _statuses_from_query(q)
        pairs = self._with_mm(list_pairs, statuses=statuses)
        return 200, {"pairs": _json_safe(pairs)}

    def rest_mm_get_pair(self, _environ: dict[str, Any], pair_key: str) -> tuple[int, dict[str, Any]]:
        pair_key = unquote(pair_key)
        pair = self._with_mm(get_pair, pair_key)
        if not pair:
            return 404, {"error": {"code": "not_found", "message": "pair not found"}}
        return 200, {"pair": _json_safe(pair)}

    def rest_mm_dispatch(self, _environ: dict[str, Any], case_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        case = self._with_mm(dispatch_case_contact, case_id, now=now)
        return 200, {"case": _json_safe(case)}

    def rest_mm_reply(self, _environ: dict[str, Any], case_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if now is not None:
            kwargs["now"] = now
        case = self._with_mm(record_case_reply, case_id, **kwargs)
        return 200, {"case": _json_safe(case)}

    def rest_mm_feedback(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if now is not None:
            kwargs["now"] = now
        fb = self._with_mm(record_feedback, **kwargs)
        return 200, {"feedback": _json_safe(fb)}

    def rest_mm_close_stale(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        kwargs = {k: v for k, v in body.items() if k != "now"}
        if now is not None:
            kwargs["now"] = now
        out = self._with_mm(close_stale_cases, **kwargs)
        return 200, _json_safe(out)

    def _chat_require_requester(self, q: dict[str, str], body: dict[str, Any] | None = None) -> str:
        rid = (q.get("requester_id") or "").strip()
        if not rid and body:
            rid = str(body.get("requester_id") or "").strip()
        if not rid:
            raise ValueError("requester_id is required")
        return rid

    def rest_chat_create_thread(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
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
        requester_id = self._chat_require_requester(q)
        thread = self._with_chat(get_thread, thread_id)
        if not thread:
            return 404, {"error": {"code": "not_found", "message": "thread not found"}}
        if requester_id not in (thread["participant_a_id"], thread["participant_b_id"]):
            return 403, {"error": {"code": "forbidden", "message": "requester is not a participant"}}
        return 200, {"thread": _json_safe(thread)}

    def rest_chat_list_messages(self, environ: dict[str, Any], thread_id: str) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = self._chat_require_requester(q)
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
        if idem:
            kwargs["client_msg_id"] = idem
        if now is not None:
            kwargs["now"] = now
        if not kwargs.get("author_id") or kwargs.get("body") is None:
            raise ValueError("author_id and body are required")
        author_id = str(kwargs.pop("author_id"))
        body_text = kwargs.pop("body")
        msg = self._with_chat(post_message, thread_id, author_id, body_text, **kwargs)
        out: dict[str, Any] = {"message": _json_safe(msg), "trace_id": get_trace_id()}
        if idem:
            out["client_idempotency_key"] = idem
        return 201, out

    def rest_chat_assistant_query(self, _environ: dict[str, Any], thread_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        user_id = body.get("user_id")
        query_text = body.get("query_text")
        if not user_id or query_text is None:
            raise ValueError("user_id and query_text are required")
        msg = self._with_chat(assistant_query, thread_id, str(user_id), str(query_text), now=now)
        return 200, {"message": _json_safe(msg), "trace_id": get_trace_id()}

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
        viewer_id = (q.get("viewer_id") or "").strip()
        if not case_id or not viewer_id:
            raise ValueError("case_id and viewer_id are required")
        lim_raw = q.get("message_limit") or "50"
        try:
            mlim = int(lim_raw)
        except ValueError:
            mlim = 50
        return 200, self._timeline_payload(case_id, viewer_id, message_limit=mlim)

    def rest_chat_maintenance_run(self, _environ: dict[str, Any], body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
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
        out = self._with_chat(
            run_chat_maintenance,
            persona_limit=plim,
            flush_outbox=flush_opt,
            summary_max_threads=smax,
        )
        return 200, _json_safe(out)

    def rest_chat_get_summary(self, environ: dict[str, Any], thread_id: str) -> tuple[int, dict[str, Any]]:
        q = _query_dict(environ)
        requester_id = self._chat_require_requester(q)
        thread = self._with_chat(get_thread, thread_id)
        if not thread:
            return 404, {"error": {"code": "not_found", "message": "thread not found"}}
        if requester_id not in (thread["participant_a_id"], thread["participant_b_id"]):
            return 403, {"error": {"code": "forbidden", "message": "requester is not a participant"}}
        summ = self._with_chat(get_thread_summary, thread_id)
        return 200, {"thread_id": thread_id, "summary": _json_safe(summ)}

    def rest_chat_adopt_draft(self, environ: dict[str, Any], thread_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        idem = _extract_client_idempotency_key(environ, body)
        draft_id = body.get("draft_message_id")
        adopter = body.get("adopter_user_id")
        if draft_id is None or not adopter:
            raise ValueError("draft_message_id and adopter_user_id are required")
        msg = self._with_chat(
            adopt_draft,
            thread_id,
            int(draft_id),
            str(adopter),
            body_override=body.get("body_override"),
            client_msg_id=idem,
            now=now,
        )
        out: dict[str, Any] = {"message": _json_safe(msg), "trace_id": get_trace_id()}
        if idem:
            out["client_idempotency_key"] = idem
        return 201, out

    def rest_chat_submit_report(self, _environ: dict[str, Any], thread_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        reporter_id = body.get("reporter_id")
        report_type = body.get("report_type")
        if not reporter_id or not report_type:
            raise ValueError("reporter_id and report_type are required")
        out = self._with_chat(
            submit_member_report,
            thread_id,
            str(reporter_id),
            str(report_type),
            reason_text=body.get("reason_text"),
            message_id=int(body["message_id"]) if body.get("message_id") is not None else None,
            reported_user_id=str(body["reported_user_id"]) if body.get("reported_user_id") is not None else None,
            now=now,
        )
        return 201, {"report": _json_safe(out.get("report")), "risk_case": _json_safe(out.get("risk_case"))}

    def rest_chat_list_reports(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
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

    def rest_chat_list_risk_cases(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
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

    def rest_chat_get_risk_case(self, _environ: dict[str, Any], risk_case_id: str) -> tuple[int, dict[str, Any]]:
        risk_case = self._with_chat(get_risk_case, risk_case_id)
        if not risk_case:
            return 404, {"error": {"code": "not_found", "message": "risk case not found"}}
        reports = self._with_chat(list_member_reports, risk_case_id=risk_case_id, limit=100)
        return 200, {"risk_case": _json_safe(risk_case), "reports": _json_safe(reports)}

    def rest_chat_review_risk_case(
        self,
        _environ: dict[str, Any],
        risk_case_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        now = _parse_optional_now(body)
        resolver_id = body.get("resolver_id")
        status = body.get("status")
        if not resolver_id or not status:
            raise ValueError("resolver_id and status are required")
        risk_case = self._with_chat(
            review_risk_case,
            risk_case_id,
            str(resolver_id),
            status=str(status),
            applied_action=body.get("applied_action"),
            resolution_note=body.get("resolution_note"),
            now=now,
        )
        return 200, {"risk_case": _json_safe(risk_case)}

    def dispatch_rest(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO") or "/"
        path = path.rstrip("/") or "/"

        if path == "/health" and method == "GET":
            return self.handle_health(environ)

        if path == "/v1/search/profiles" and method == "POST":
            return self.rest_search_profiles(environ, _parse_json_body(_read_body(environ)))

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

        # /v1/chat/...
        if path == "/v1/chat/maintenance/run" and method == "POST":
            return self.rest_chat_maintenance_run(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/chat/threads" and method == "POST":
            return self.rest_chat_create_thread(environ, _parse_json_body(_read_body(environ)))
        if path == "/v1/chat/reports" and method == "GET":
            return self.rest_chat_list_reports(environ)
        if path == "/v1/chat/risk-cases" and method == "GET":
            return self.rest_chat_list_risk_cases(environ)
        m = re.fullmatch(r"/v1/chat/risk-cases/([^/]+)/review", path)
        if m and method == "POST":
            return self.rest_chat_review_risk_case(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/chat/risk-cases/([^/]+)", path)
        if m and method == "GET":
            return self.rest_chat_get_risk_case(environ, m.group(1))
        m = re.fullmatch(r"/v1/chat/threads/([^/]+)/summary", path)
        if m and method == "GET":
            return self.rest_chat_get_summary(environ, m.group(1))
        m = re.fullmatch(r"/v1/chat/threads/([^/]+)/messages/adopt-draft", path)
        if m and method == "POST":
            return self.rest_chat_adopt_draft(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/chat/threads/([^/]+)/reports", path)
        if m and method == "POST":
            return self.rest_chat_submit_report(environ, m.group(1), _parse_json_body(_read_body(environ)))
        m = re.fullmatch(r"/v1/chat/threads/([^/]+)/assistant/query", path)
        if m and method == "POST":
            return self.rest_chat_assistant_query(environ, m.group(1), _parse_json_body(_read_body(environ)))
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
            result = self._jsonrpc_call(method, p)
        except ValueError as e:
            return 200, {"jsonrpc": "2.0", "error": {"code": -32602, "message": str(e)}, "id": rpc_id}
        except Exception as e:  # noqa: BLE001 — surface as application error
            return 200, {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}, "id": rpc_id}

        if rpc_id is None:
            return 204, {}
        return 200, {"jsonrpc": "2.0", "result": _json_safe(result), "id": rpc_id}

    def _jsonrpc_call(self, method: str, p: dict[str, Any]) -> Any:
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
            )
        if method == "recommendation.get_subscription":
            return self._with_rec(get_subscription, p["subscription_id"])
        if method == "recommendation.create_subscription":
            return self._with_rec(create_subscription, **p)
        if method == "recommendation.update_subscription_overrides":
            return self._with_rec(update_subscription_overrides, p["subscription_id"], p.get("overrides"), now=p.get("now"))
        if method == "recommendation.refresh_subscription":
            return self._with_rec(refresh_subscription, p["subscription_id"], now=p.get("now"))
        if method == "recommendation.refresh_due_subscriptions":
            return self._with_rec(
                refresh_due_subscriptions,
                now=p.get("now"),
                subscription_ids=p.get("subscription_ids"),
            )
        if method == "recommendation.list_recommendations_for_subscription":
            return self._with_rec(list_recommendations_for_subscription, p["subscription_id"])
        if method == "recommendation.list_search_runs_for_subscription":
            return self._with_rec(list_search_runs_for_subscription, p["subscription_id"])
        if method == "recommendation.list_in_app_cards":
            return self._with_rec(
                list_in_app_cards,
                requester_id=p.get("requester_id"),
                unread_only=bool(p.get("unread_only", False)),
            )
        if method == "recommendation.deliver_in_app_recommendations":
            return self._with_rec(deliver_in_app_recommendations, now=p.get("now"))
        if method == "recommendation.record_recommendation_action":
            p2 = {k: v for k, v in p.items() if k not in {"idempotency_key", "client_idempotency_key"}}
            ck = p.get("client_idempotency_key") or p.get("idempotency_key")
            if ck is not None and str(ck).strip():
                p2["client_idempotency_key"] = str(ck).strip()[:191]
            return self._with_rec(record_recommendation_action, **p2)
        if method == "recommendation.record_user_review":
            p2 = {k: v for k, v in p.items() if k not in {"idempotency_key", "client_idempotency_key"}}
            ck = p.get("client_idempotency_key") or p.get("idempotency_key")
            if ck is not None and str(ck).strip():
                p2["client_idempotency_key"] = str(ck).strip()[:191]
            return self._with_rec(record_user_review, **p2)
        if method == "recommendation.mark_in_app_cards_read":
            rid = p.get("requester_id")
            if rid is None:
                raise ValueError("requester_id is required")
            card_ids = p.get("card_ids")
            if not isinstance(card_ids, list):
                raise ValueError("card_ids must be a list")
            return self._with_rec(
                mark_in_app_cards_read,
                requester_id=int(rid),
                card_ids=[str(x) for x in card_ids],
                now=p.get("now"),
            )

        if method == "matchmaking.create_pool_member":
            return self._with_mm(create_pool_member, **p)
        if method == "matchmaking.get_pool_member":
            return self._with_mm(get_pool_member, p["member_id"])
        if method == "matchmaking.set_pool_member_status":
            mid = p.pop("member_id")
            return self._with_mm(set_pool_member_status, mid, **p)
        if method == "matchmaking.refresh_pool_member":
            return self._with_mm(refresh_pool_member, p["member_id"], now=p.get("now"))
        if method == "matchmaking.refresh_active_pool":
            return self._with_mm(refresh_active_pool, now=p.get("now"), member_ids=p.get("member_ids"))
        if method == "matchmaking.build_mutual_pairs":
            return self._with_mm(build_mutual_pairs, now=p.get("now"))
        if method == "matchmaking.open_match_cases":
            return self._with_mm(
                open_match_cases,
                now=p.get("now"),
                case_expires_hours=int(p.get("case_expires_hours", 72)),
            )
        if method == "matchmaking.get_match_case":
            return self._with_mm(get_match_case, p["case_id"])
        if method == "matchmaking.list_match_cases":
            return self._with_mm(list_match_cases, statuses=p.get("statuses"))
        if method == "matchmaking.list_pairs":
            return self._with_mm(list_pairs, statuses=p.get("statuses"))
        if method == "matchmaking.get_pair":
            return self._with_mm(get_pair, p["pair_key"])
        if method == "matchmaking.dispatch_case_contact":
            return self._with_mm(dispatch_case_contact, p["case_id"], now=p.get("now"))
        if method == "matchmaking.record_case_reply":
            cid = p.pop("case_id")
            return self._with_mm(record_case_reply, cid, **p)
        if method == "matchmaking.record_feedback":
            return self._with_mm(record_feedback, **p)
        if method == "matchmaking.close_stale_cases":
            return self._with_mm(close_stale_cases, now=p.get("now"), timeout_cooling_days=int(p.get("timeout_cooling_days", 30)))

        if method == "chat.get_thread":
            return self._with_chat(get_thread, p["thread_id"])
        if method == "chat.get_or_create_thread":
            return self._with_chat(get_or_create_thread, **p)
        if method == "chat.list_messages":
            bm = p.get("before_message_id")
            if bm is not None:
                bm = int(bm)
            return self._with_chat(
                list_messages,
                p["thread_id"],
                p["requester_id"],
                limit=int(p.get("limit", 50)),
                before_message_id=bm,
            )
        if method == "chat.post_message":
            p2 = {k: v for k, v in p.items() if k not in {"idempotency_key", "client_idempotency_key"}}
            ck = p.get("client_idempotency_key") or p.get("idempotency_key")
            if ck is not None and str(ck).strip():
                p2["client_msg_id"] = str(ck).strip()[:191]
            tid = p2.pop("thread_id")
            author_id = str(p2.pop("author_id"))
            body_text = p2.pop("body")
            return self._with_chat(post_message, tid, author_id, body_text, **p2)
        if method == "chat.assistant_query":
            qt = p.get("query_text")
            if qt is None:
                qt = p.get("query", "")
            return self._with_chat(
                assistant_query, p["thread_id"], str(p["user_id"]), str(qt), now=p.get("now")
            )
        if method == "chat.adopt_draft":
            ck = p.get("client_idempotency_key") or p.get("idempotency_key")
            cmid = str(ck).strip()[:191] if ck is not None and str(ck).strip() else None
            return self._with_chat(
                adopt_draft,
                p["thread_id"],
                int(p["draft_message_id"]),
                str(p["adopter_user_id"]),
                body_override=p.get("body_override"),
                client_msg_id=cmid,
                now=p.get("now"),
            )
        if method == "chat.submit_member_report":
            return self._with_chat(
                submit_member_report,
                p["thread_id"],
                str(p["reporter_id"]),
                str(p["report_type"]),
                reason_text=p.get("reason_text"),
                message_id=int(p["message_id"]) if p.get("message_id") is not None else None,
                reported_user_id=str(p["reported_user_id"]) if p.get("reported_user_id") is not None else None,
                now=p.get("now"),
            )
        if method == "chat.list_member_reports":
            return self._with_chat(
                list_member_reports,
                thread_id=p.get("thread_id"),
                risk_case_id=p.get("risk_case_id"),
                reported_user_id=p.get("reported_user_id"),
                limit=int(p.get("limit", 100)),
            )
        if method == "chat.list_risk_cases":
            return self._with_chat(
                list_risk_cases,
                statuses=p.get("statuses"),
                subject_user_id=p.get("subject_user_id"),
                thread_id=p.get("thread_id"),
                limit=int(p.get("limit", 100)),
            )
        if method == "chat.get_risk_case":
            risk_case = self._with_chat(get_risk_case, p["risk_case_id"])
            if not risk_case:
                return None
            return {
                "risk_case": risk_case,
                "reports": self._with_chat(list_member_reports, risk_case_id=p["risk_case_id"], limit=int(p.get("limit", 100))),
            }
        if method == "chat.review_risk_case":
            return self._with_chat(
                review_risk_case,
                p["risk_case_id"],
                str(p["resolver_id"]),
                status=str(p["status"]),
                applied_action=p.get("applied_action"),
                resolution_note=p.get("resolution_note"),
                now=p.get("now"),
            )

        if method == "timeline.get_for_case":
            try:
                mlim = int(p.get("message_limit", 50))
            except (TypeError, ValueError):
                mlim = 50
            return self._timeline_payload(str(p["case_id"]), str(p["viewer_id"]), message_limit=mlim)

        if method == "chat.list_pending_outbox":
            try:
                lim = int(p.get("limit", 100))
            except (TypeError, ValueError):
                lim = 100
            return self._with_chat(list_pending_outbox, limit=lim)

        if method == "chat.process_persona_jobs":
            try:
                lim = int(p.get("limit", 20))
            except (TypeError, ValueError):
                lim = 20
            return self._with_chat(process_pending_persona_jobs, limit=lim)

        if method == "chat.run_maintenance":
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
            return self._with_chat(
                run_chat_maintenance,
                persona_limit=plim,
                flush_outbox=flush_opt,
                summary_max_threads=smax,
            )

        raise ValueError(f"Unknown method: {method}")

    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        path = environ.get("PATH_INFO") or "/"
        method = environ.get("REQUEST_METHOD", "GET").upper()
        trace_id = _incoming_trace_id(environ)
        token = set_trace_id(trace_id)
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
            if not self._api_guard.allows(environ):
                status_code = 401
                body = json.dumps(
                    _gateway_error_payload("unauthorized", "Invalid or missing API key", trace_id),
                    ensure_ascii=False,
                ).encode("utf-8")
                sr("401 Unauthorized", JSON_HEADERS + [("Content-Length", str(len(body)))])
                _access_log(status_code)
                return [body]
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
