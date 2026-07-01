"""HTTP handlers for SSE server."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime

from aiohttp import web

from .connection_manager import ConnectionManager, send_event
from .config import config

logger = logging.getLogger(__name__)


class SSEHandlers:
    """HTTP handlers for SSE server."""

    def __init__(self, connection_manager: ConnectionManager) -> None:
        """Initialize handlers.

        Args:
            connection_manager: Connection manager instance
        """
        self.connection_manager = connection_manager
        self._start_time = time.time()

    async def handle_sse_connection(self, request: web.Request) -> web.StreamResponse:
        """Handle SSE connection from frontend.

        Args:
            request: HTTP request

        Returns:
            StreamResponse for SSE
        """
        case_id = request.match_info.get("caseId")
        user_id = request.query.get("participant_id")

        if not case_id or not user_id:
            return web.json_response(
                {"error": "Missing caseId or participant_id"},
                status=400,
            )

        # Check max connections
        stats = self.connection_manager.get_stats()
        if stats["total_connections"] >= config.MAX_CONNECTIONS:
            return web.json_response(
                {"error": "Maximum connections reached"},
                status=503,
            )

        logger.info(f"SSE connection request: user={user_id}, case={case_id}")

        # Create SSE response with CORS headers
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable Nginx buffering
                # CORS headers for cross-origin EventSource connection
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            },
        )
        await response.prepare(request)

        # Register connection
        await self.connection_manager.add_connection(user_id, case_id, response)

        # Send connection confirmation
        await send_event(response, "connected", {
            "user_id": user_id,
            "case_id": case_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Heartbeat loop
        try:
            while True:
                await asyncio.sleep(config.HEARTBEAT_INTERVAL)
                try:
                    await send_event(response, "heartbeat", {
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    logger.debug(f"Heartbeat sent to user {user_id}")
                except Exception as e:
                    logger.error(f"Heartbeat failed for user {user_id}: {e}")
                    break
        except asyncio.CancelledError:
            # Client disconnected
            logger.info(f"Client disconnected: user={user_id}")
        finally:
            await self.connection_manager.remove_connection(user_id)

        return response

    async def handle_internal_push(self, request: web.Request) -> web.Response:
        """Handle internal push request from chat system.

        Args:
            request: HTTP request with message payload

        Returns:
            JSON response with push result
        """
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        # Validate required fields
        required_fields = ["case_id", "message_id", "author_id", "body"]
        for field in required_fields:
            if field not in data:
                return web.json_response(
                    {"error": f"Missing required field: {field}"},
                    status=400,
                )

        case_id = data.get("case_id")
        author_id = data.get("author_id")
        message_id = data.get("message_id")

        logger.info(
            f"Push request: case={case_id}, message={message_id}, author={author_id}"
        )

        # Broadcast message to all connections in this case
        sent_count = await self.connection_manager.broadcast_to_case(
            case_id,
            "message",
            {
                "type": "new_message",
                "message_id": message_id,
                "conversation_id": data.get("conversation_id"),
                "author_id": author_id,
                "body": data.get("body"),
                "source": data.get("source"),
                "channel_key": data.get("channel_key"),
                "created_at": datetime.utcnow().isoformat(),
            },
            exclude_user=author_id,  # Don't send to the author
        )

        # Get online/offline user stats
        connections = await self.connection_manager.get_case_connections(case_id)
        online_users = [c.user_id for c in connections if c.user_id != author_id]

        return web.json_response({
            "success": True,
            "pushed": sent_count,
            "online_users": online_users,
            "message_id": message_id,
        })

    async def handle_internal_push_discovery(self, request: web.Request) -> web.Response:
        """Handle internal push request from discovery system.

        Args:
            request: HTTP request with message payload

        Returns:
            JSON response with push result
        """
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        # Validate required fields
        required_fields = ["session_id", "profile_id", "event_type"]
        for field in required_fields:
            if field not in data:
                return web.json_response(
                    {"error": f"Missing required field: {field}"},
                    status=400,
                )

        session_id = data.get("session_id")
        profile_id = data.get("profile_id")
        event_type = data.get("event_type")

        logger.info(
            f"[Discovery SSE Push] session={session_id}, profile={profile_id}, event={event_type}"
        )

        # Broadcast message to all connections for this profile
        sent_count = await self.connection_manager.broadcast_to_discovery_session(
            session_id,
            "message",
            {
                "type": event_type,
                "session_id": session_id,
                "profile_id": profile_id,
                "search_run_id": data.get("search_run_id"),
                "timestamp": data.get("timestamp"),
            },
        )

        # Get online/offline user stats
        connections = await self.connection_manager.get_discovery_session_connections(session_id)
        online_profiles = [c.profile_id for c in connections]

        return web.json_response({
            "success": True,
            "pushed": sent_count,
            "online_profiles": online_profiles,
            "session_id": session_id,
        })

    async def handle_internal_push_recommendation(self, request: web.Request) -> web.Response:
        """Handle internal push request for recommendation cards.

        支持两种推荐类型：
        1. passive_recommendation: 别人点击"愿意认识你"
        2. active_recommendation: 系统主动推荐

        Args:
            request: HTTP request with message payload

        Returns:
            JSON response with push result
        """
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        # Validate required fields
        required_fields = ["profile_id", "event_type"]
        for field in required_fields:
            if field not in data:
                return web.json_response(
                    {"error": f"Missing required field: {field}"},
                    status=400,
                )

        profile_id = data.get("profile_id")
        event_type = data.get("event_type")  # passive_recommendation | active_recommendation

        logger.info(
            f"[Recommendation SSE Push] profile={profile_id}, event={event_type}"
        )

        # Broadcast to all discovery sessions for this profile
        # (用户可能在多个discovery session中，都要推送)
        sent_count = await self.connection_manager.broadcast_to_profile_discovery(
            profile_id,
            "message",
            {
                "type": "new_recommendation",
                "event_type": event_type,
                "profile_id": profile_id,
                "case_id": data.get("case_id"),
                "recommendation_id": data.get("recommendation_id"),
                "candidate_id": data.get("candidate_id"),
                "source_profile_id": data.get("source_profile_id"),  # 被动推荐：发起人
                "message": data.get("message"),
                "timestamp": data.get("timestamp"),
            },
        )

        # Get online/offline stats
        connections = await self.connection_manager.get_profile_discovery_connections(profile_id)
        online_sessions = [c.session_id for c in connections]

        return web.json_response({
            "success": True,
            "pushed": sent_count,
            "online_sessions": online_sessions,
            "profile_id": profile_id,
        })

    async def handle_sse_connection_discovery(self, request: web.StreamResponse) -> web.StreamResponse:
        """Handle SSE connection from frontend for Discovery.

        Args:
            request: HTTP request

        Returns:
            StreamResponse for SSE
        """
        session_id = request.match_info.get("sessionId")
        profile_id = request.query.get("profile_id")

        if not session_id or not profile_id:
            return web.json_response(
                {"error": "Missing sessionId or profile_id"},
                status=400,
            )

        # Check max connections
        stats = self.connection_manager.get_stats()
        if stats["total_connections"] >= config.MAX_CONNECTIONS:
            return web.json_response(
                {"error": "Maximum connections reached"},
                status=503,
            )

        logger.info(f"[Discovery SSE] Connection request: profile={profile_id}, session={session_id}")

        # Create SSE response with CORS headers
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable Nginx buffering
                # CORS headers for cross-origin EventSource connection
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type, Authorization",
            },
        )
        await response.prepare(request)

        # Register connection
        await self.connection_manager.add_discovery_connection(profile_id, session_id, response)

        # Send connection confirmation
        await send_event(response, "connected", {
            "profile_id": profile_id,
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Heartbeat loop
        try:
            while True:
                await asyncio.sleep(config.HEARTBEAT_INTERVAL)
                try:
                    await send_event(response, "heartbeat", {
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    logger.debug(f"[Discovery SSE] Heartbeat sent to profile {profile_id}")
                except Exception as e:
                    logger.error(f"[Discovery SSE] Heartbeat failed for profile {profile_id}: {e}")
                    break
        except asyncio.CancelledError:
            # Client disconnected
            logger.info(f"[Discovery SSE] Client disconnected: profile={profile_id}")
        finally:
            await self.connection_manager.remove_discovery_connection(profile_id)

        return response

    async def handle_stats(self, request: web.Request) -> web.Response:
        """Handle stats request.

        Args:
            request: HTTP request

        Returns:
            JSON response with connection stats
        """
        stats = self.connection_manager.get_stats()
        return web.json_response(stats)

    async def handle_health(self, request: web.Request) -> web.Response:
        """Handle health check request - 增强版详细状态.

        Args:
            request: HTTP request

        Returns:
            JSON response with health status
        """
        checks = {}

        # 检查 Redis 连接（如果配置了）
        redis_host = os.environ.get("REDIS_HOST")
        if redis_host:
            try:
                import redis
                start = time.time()
                port = int(os.environ.get("REDIS_PORT", 6379))
                password_file = os.environ.get("REDIS_PASSWORD_FILE")
                password = os.environ.get("REDIS_PASSWORD")

                if password_file:
                    try:
                        with open(password_file) as f:
                            password = f.read().strip()
                    except Exception as e:
                        checks["redis"] = {"status": "secrets_read_error", "error": str(e)}
                        password = None

                if checks.get("redis", {}).get("status") != "secrets_read_error":
                    client = redis.Redis(
                        host=redis_host,
                        port=port,
                        password=password,
                        socket_connect_timeout=2,
                    )
                    client.ping()
                    latency = (time.time() - start) * 1000
                    checks["redis"] = {"status": "healthy", "latency_ms": round(latency, 2)}
            except ModuleNotFoundError as e:
                checks["redis"] = {"status": "not_installed", "error": str(e)}
            except Exception as e:
                logger.warning(f"Redis health check failed: {e}")
                checks["redis"] = {"status": "unhealthy", "error": str(e)}
        else:
            checks["redis"] = {"status": "not_configured"}

        # 获取连接数统计
        stats = self.connection_manager.get_stats()

        # 判断整体健康状态
        all_healthy = all(
            check.get("status") in ("healthy", "not_configured", "not_installed")
            for check in checks.values()
        )

        # 如果连接数超过80%容量，标记为 degraded
        max_connections = config.MAX_CONNECTIONS
        current_connections = stats["total_connections"]
        if current_connections >= max_connections * 0.8:
            all_healthy = False

        return web.json_response({
            "status": "healthy" if all_healthy else "degraded",
            "service": "sse-server",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": time.time() - getattr(self, "_start_time", time.time()),
            "checks": checks,
            "connections": {
                "current": current_connections,
                "max": max_connections,
                "usage_percent": round(current_connections / max_connections * 100, 2),
            },
            "config": {
                "host": config.HOST,
                "port": config.PORT,
                "heartbeat_interval": config.HEARTBEAT_INTERVAL,
            },
        })

    async def handle_metrics(self, request: web.Request) -> web.Response:
        """Expose lightweight Prometheus metrics without extra runtime wiring."""
        stats = self.connection_manager.get_stats()
        max_connections = config.MAX_CONNECTIONS
        current_connections = stats["total_connections"]
        usage_ratio = (current_connections / max_connections) if max_connections else 0.0

        payload = "\n".join([
            "# HELP sse_server_connections_current Current SSE connections.",
            "# TYPE sse_server_connections_current gauge",
            f"sse_server_connections_current {current_connections}",
            "# HELP sse_server_connections_max Configured maximum SSE connections.",
            "# TYPE sse_server_connections_max gauge",
            f"sse_server_connections_max {max_connections}",
            "# HELP sse_server_connection_usage_ratio Current SSE connection usage ratio.",
            "# TYPE sse_server_connection_usage_ratio gauge",
            f"sse_server_connection_usage_ratio {usage_ratio:.6f}",
            "",
        ])
        return web.Response(
            body=payload.encode("utf-8"),
            headers={"Content-Type": "text/plain; version=0.0.4; charset=utf-8"},
        )


def setup_routes(app: web.Application, handlers: SSEHandlers) -> None:
    """Setup routes for SSE server.

    Args:
        app: aiohttp Application
        handlers: SSEHandlers instance
    """
    # SSE endpoint for frontend (chat)
    app.router.add_get(
        "/sse/chat/{caseId}",
        handlers.handle_sse_connection,
    )

    # SSE endpoint for frontend (discovery) - 新增
    app.router.add_get(
        "/sse/discovery/{sessionId}",
        handlers.handle_sse_connection_discovery,
    )

    # Internal push endpoint (chat)
    app.router.add_post(
        "/internal/push",
        handlers.handle_internal_push,
    )

    # Internal push endpoint (discovery candidates ready) - 新增
    app.router.add_post(
        "/internal/push/discovery",
        handlers.handle_internal_push_discovery,
    )

    # Internal push endpoint (recommendation cards) - 新增（被动推荐 + 主动推荐）
    app.router.add_post(
        "/internal/push/recommendation",
        handlers.handle_internal_push_recommendation,
    )

    # Stats endpoint
    app.router.add_get(
        "/internal/stats",
        handlers.handle_stats,
    )

    # Health check
    app.router.add_get(
        "/health",
        handlers.handle_health,
    )

    # Prometheus metrics
    app.router.add_get(
        "/metrics",
        handlers.handle_metrics,
    )
