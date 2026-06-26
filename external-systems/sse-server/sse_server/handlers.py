"""HTTP handlers for SSE server."""

from __future__ import annotations

import asyncio
import json
import logging
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
        """Handle health check request.

        Args:
            request: HTTP request

        Returns:
            JSON response with health status
        """
        return web.json_response({
            "status": "healthy",
            "service": "sse-server",
            "timestamp": datetime.utcnow().isoformat(),
        })


def setup_routes(app: web.Application, handlers: SSEHandlers) -> None:
    """Setup routes for SSE server.

    Args:
        app: aiohttp Application
        handlers: SSEHandlers instance
    """
    # SSE endpoint for frontend
    app.router.add_get(
        "/sse/chat/{caseId}",
        handlers.handle_sse_connection,
    )

    # Internal push endpoint
    app.router.add_post(
        "/internal/push",
        handlers.handle_internal_push,
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