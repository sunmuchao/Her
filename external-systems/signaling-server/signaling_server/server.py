"""WebSocket signaling server for WebRTC."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from typing import TYPE_CHECKING

import websockets
from websockets.server import serve

from .handlers import MessageHandler
from .room_manager import RoomManager

if TYPE_CHECKING:
    from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)


class SignalingServer:
    """WebSocket signaling server for WebRTC."""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8765,
    ) -> None:
        self.host = host
        self.port = port
        self.room_manager = RoomManager()
        self.message_handler = MessageHandler(self.room_manager)
        self._active_connections: dict[str, WebSocketServerProtocol] = {}
        self._server = None

    async def handle_connection(
        self,
        websocket: WebSocketServerProtocol,
    ) -> None:
        """Handle a WebSocket connection."""
        user_id = self._extract_user_id(websocket)
        if not user_id:
            logger.warning("Connection without user_id rejected")
            await websocket.close(code=4000, reason="Missing user_id")
            return

        self._active_connections[user_id] = websocket
        logger.info(
            "User %s connected from %s",
            user_id,
            websocket.remote_address,
        )

        try:
            await self._send_connected(websocket, user_id)

            async for message in websocket:
                await self.message_handler.handle(websocket, user_id, message)

        except websockets.ConnectionClosed:
            logger.info("User %s disconnected", user_id)

        finally:
            await self._cleanup_user(user_id)

    def _extract_user_id(
        self,
        websocket: WebSocketServerProtocol,
    ) -> str | None:
        """Extract user_id from the WebSocket path."""
        path = websocket.request.path
        if not path:
            return None

        parts = path.strip("/").split("/")
        if len(parts) >= 1 and parts[0] == "ws":
            if len(parts) >= 2:
                return parts[1]
        return None

    async def _send_connected(
        self,
        websocket: WebSocketServerProtocol,
        user_id: str,
    ) -> None:
        """Send connection confirmation to the client."""
        import json
        message = json.dumps({
            "type": "connected",
            "user_id": user_id,
        }, ensure_ascii=False)
        await websocket.send(message)

    async def _cleanup_user(self, user_id: str) -> None:
        """Clean up user resources when disconnected."""
        self._active_connections.pop(user_id, None)

        room = await self.room_manager.leave_room(user_id)
        if room:
            await self.room_manager.broadcast(
                room.call_id,
                {
                    "type": "user_left",
                    "call_id": room.call_id,
                    "user_id": user_id,
                },
            )

        logger.info(
            "Cleaned up user %s (rooms: %d, connections: %d)",
            user_id,
            self.room_manager.get_room_count(),
            len(self._active_connections),
        )

    async def start(self) -> None:
        """Start the WebSocket server."""
        logger.info(
            "Starting signaling server on %s:%s",
            self.host,
            self.port,
        )

        async with serve(
            self.handle_connection,
            self.host,
            self.port,
            ping_interval=30,
            ping_timeout=10,
        ) as server:
            self._server = server
            logger.info("Signaling server started successfully")

            await self._shutdown_event.wait()

    def stop(self) -> None:
        """Stop the WebSocket server."""
        logger.info("Stopping signaling server")
        self._shutdown_event.set()

    async def get_stats(self) -> dict:
        """Get server statistics."""
        return {
            "active_connections": len(self._active_connections),
            "active_rooms": self.room_manager.get_room_count(),
            "total_participants": self.room_manager.get_participant_count(),
        }

    _shutdown_event = asyncio.Event()


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="WebSocket signaling server for WebRTC",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to bind to (default: 8765)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )

    server = SignalingServer(host=args.host, port=args.port)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: server._shutdown_event.set(),
        )

    await server.start()


if __name__ == "__main__":
    asyncio.run(main())