"""WSGI app: REST JSON under /v1/... and JSON-RPC 2.0 under POST /jsonrpc."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable


def _load_repo_root_dotenv() -> None:
    """Load monorepo ``Her/.env`` before any imports."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve()
    for p in (here.parent, *here.parents):
        if (p / "match_domain").is_dir() and (p / "pyproject.toml").is_file():
            env_path = p / ".env"
            if env_path.is_file():
                load_dotenv(env_path, override=True)
            return


# 在所有其他导入之前加载 .env
_load_repo_root_dotenv()

from . import _paths  # noqa: F401 — side effect: sys.path
from .access_control import GatewayAccessMixin
from .async_jobs import AsyncJobGatewayMixin
from .auth_routes import (
    AuthOtpService,
    _build_one_tap_login_provider,
    _build_wechat_login_provider,
    dispatch_public_auth_rest,
)
from .http_helpers import (
    _gateway_error_payload,
    _incoming_trace_id,
    _wrap_trace_headers,
)
from .identity import (
    ActorPrincipal,
    GatewayAuthError,
    GatewayPermissionError,
    IdentityResolver,
    set_current_actor,
)
from .jsonrpc_dispatch import dispatch_gateway_jsonrpc
from .mysql_pool import GatewayConnectionPool
from .request_policy import client_ip, rate_limiter_from_environ
from .rest_dispatch import dispatch_gateway_rest
from .surface_config import gateway_surface, jsonrpc_enabled

from match_domain import (
    reset_actor_context,
    reset_trace_id,
    set_actor_context,
    set_trace_id,
)
from observability import audit_event, emit_pipeline_record

from chat_system import get_session_by_access_token  # type: ignore[import-untyped]
from chat_system.storage import (  # type: ignore[import-untyped]
    DEFAULT_CHAT_MYSQL_DSN,
    connect_db as chat_connect_db,
)
from discovery_system import create_default_discovery_service  # type: ignore[import-untyped]
from matchmaking_system import connect_db as matchmaking_connect_db  # type: ignore[import-untyped]
from matchmaking_system.storage import DEFAULT_MATCHMAKING_MYSQL_DSN  # type: ignore[import-untyped]
from recommendation_system import connect_db as recommendation_connect_db  # type: ignore[import-untyped]
from recommendation_system.storage import DEFAULT_RECOMMENDATION_MYSQL_DSN  # type: ignore[import-untyped]
from relationship_ledger import connect_db as relation_ledger_connect_db  # type: ignore[import-untyped]
from relationship_ledger.storage import DEFAULT_RELATION_LEDGER_MYSQL_DSN  # type: ignore[import-untyped]

JSON_HEADERS = [("Content-Type", "application/json; charset=utf-8")]
LOGGER = logging.getLogger(__name__)


class PartnerGateway(AsyncJobGatewayMixin, GatewayAccessMixin):
    def __init__(
        self,
        *,
        recommendation_dsn: str | None = None,
        matchmaking_dsn: str | None = None,
        chat_dsn: str | None = None,
        relation_ledger_dsn: str | None = None,
        db_pool_max: int | None = None,
    ) -> None:
        self._recommendation_dsn = recommendation_dsn or os.environ.get(
            "PARTNER_RECOMMENDATION_DB", DEFAULT_RECOMMENDATION_MYSQL_DSN
        )
        self._matchmaking_dsn = matchmaking_dsn or os.environ.get(
            "PARTNER_MATCHMAKING_DB", DEFAULT_MATCHMAKING_MYSQL_DSN
        )
        self._chat_dsn = chat_dsn or os.environ.get("PARTNER_CHAT_DB", DEFAULT_CHAT_MYSQL_DSN)
        self._relation_ledger_dsn = relation_ledger_dsn or os.environ.get(
            "HER_RELATION_LEDGER_DB", DEFAULT_RELATION_LEDGER_MYSQL_DSN
        )
        pool_n = db_pool_max if db_pool_max is not None else int(os.environ.get("PARTNER_GATEWAY_DB_POOL_MAX", "0") or "0")
        self._rec_pool: GatewayConnectionPool | None = None
        self._mm_pool: GatewayConnectionPool | None = None
        self._chat_pool: GatewayConnectionPool | None = None
        self._ledger_pool: GatewayConnectionPool | None = None
        if pool_n > 0:
            self._rec_pool = GatewayConnectionPool(self._recommendation_dsn, "recommendation", max_size=pool_n)
            self._mm_pool = GatewayConnectionPool(self._matchmaking_dsn, "matchmaking", max_size=pool_n)
            self._chat_pool = GatewayConnectionPool(self._chat_dsn, "chat", max_size=pool_n)
            self._ledger_pool = GatewayConnectionPool(self._relation_ledger_dsn, "relationship_ledger", max_size=pool_n)
        self._discovery = create_default_discovery_service()
        self._auth_otp = AuthOtpService(chat_executor=self._with_chat)
        self._wechat_login_provider = _build_wechat_login_provider()
        self._one_tap_login_provider = _build_one_tap_login_provider()
        self._identity_resolver = IdentityResolver(session_resolver=self._resolve_auth_session_principal)
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
        # 数据库连接超时保护：最长等待 10 秒
        DB_TIMEOUT = 10.0

        if pool is not None:
            conn = pool.acquire(timeout=DB_TIMEOUT)
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

    def _with_ledger(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return self._with_db(
            self._ledger_pool,
            relation_ledger_connect_db,
            self._relation_ledger_dsn,
            fn,
            *args,
            **kwargs,
        )

    def _with_proxy_intro(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        from match_domain.proxy_intro_storage import use_matchmaking_storage

        if not use_matchmaking_storage():
            return self._with_rec(fn, *args, **kwargs)

        def _dual(mm_conn: Any) -> Any:
            if self._rec_pool is not None:
                rec_conn = self._rec_pool.acquire()
                try:
                    return fn(mm_conn, *args, recommendation_conn=rec_conn, **kwargs)
                finally:
                    self._rec_pool.release(rec_conn)
            rec_conn = recommendation_connect_db(self._recommendation_dsn)
            try:
                return fn(mm_conn, *args, recommendation_conn=rec_conn, **kwargs)
            finally:
                rec_conn.close()

        return self._with_mm(_dual)

    def _resolve_auth_session_principal(self, token: str):
        try:
            resolved = self._with_chat(get_session_by_access_token, token)
        except Exception:
            return None
        if not resolved:
            return None
        user = resolved.get("user") or {}
        session = resolved.get("session") or {}
        user_id = str(user.get("user_id") or "").strip()
        session_id = str(session.get("session_id") or "").strip()
        if not user_id or not session_id:
            return None
        return ActorPrincipal(
            actor_id=user_id,
            roles=frozenset({"end_user"}),
            token_id=session_id,
            auth_source="auth_session",
        )

    def handle_health(self, _environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return 200, {
            "ok": True,
            "surface": gateway_surface(),
            "jsonrpc_enabled": jsonrpc_enabled(),
            "services": ["recommendation", "matchmaking", "chat"],
            "recommendation_db_configured": bool(self._recommendation_dsn),
            "matchmaking_db_configured": bool(self._matchmaking_dsn),
            "chat_db_configured": bool(self._chat_dsn),
            "relation_ledger_db_configured": bool(self._relation_ledger_dsn),
            "db_connection_pool": bool(self._rec_pool and self._mm_pool and self._chat_pool and self._ledger_pool),
            "auth_required": self._identity_resolver.required,
            "api_key_required": self._identity_resolver.legacy_api_required,
            "static_token_count": self._identity_resolver.static_token_count,
            "rate_limit_per_minute": int(os.environ.get("PARTNER_GATEWAY_RATE_LIMIT_PER_MINUTE", "600") or "600"),
        }

    def dispatch_rest(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return dispatch_gateway_rest(self, environ)

    def dispatch_jsonrpc(self, environ: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return dispatch_gateway_jsonrpc(self, environ)

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
