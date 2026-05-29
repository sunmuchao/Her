"""Signaling message handlers for WebRTC."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .room_manager import RoomManager

if TYPE_CHECKING:
    from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)


@dataclass
class SignalingMessage:
    """A signaling message from a client."""

    type: str
    call_id: str
    user_id: str
    payload: dict[str, Any]


class MessageHandler:
    """Handles signaling messages for WebRTC."""

    SUPPORTED_TYPES = {
        "join_room",
        "leave_room",
        "offer",
        "answer",
        "ice_candidate",
        "ping",
        "pong",
    }

    def __init__(self, room_manager: RoomManager) -> None:
        self.room_manager = room_manager

    async def handle(
        self,
        websocket: WebSocketServerProtocol,
        user_id: str,
        raw_message: str,
    ) -> None:
        """Handle a raw message from a WebSocket client."""
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            await self._send_error(websocket, "Invalid JSON format")
            return

        message_type = data.get("type")
        if not message_type:
            await self._send_error(websocket, "Missing message type")
            return

        if message_type not in self.SUPPORTED_TYPES:
            await self._send_error(
                websocket,
                f"Unsupported message type: {message_type}",
            )
            return

        call_id = data.get("call_id", "")
        payload = data.get("payload", {})

        message = SignalingMessage(
            type=message_type,
            call_id=call_id,
            user_id=user_id,
            payload=payload,
        )

        handler = getattr(self, f"_handle_{message_type}", None)
        if handler:
            await handler(websocket, message)
        else:
            logger.warning(
                "No handler for message type: %s",
                message_type,
            )

    async def _handle_join_room(
        self,
        websocket: WebSocketServerProtocol,
        message: SignalingMessage,
    ) -> None:
        """Handle join_room message."""
        call_id = message.call_id
        if not call_id:
            await self._send_error(websocket, "Missing call_id")
            return

        await self.room_manager.join_room(
            call_id=call_id,
            user_id=message.user_id,
            websocket=websocket,
        )

        room = await self.room_manager.get_room(call_id)
        if not room:
            await self._send_error(websocket, "Failed to join room")
            return

        existing_participants = [
            p.user_id for p in room.get_other_participants(message.user_id)
        ]

        await self._send_response(
            websocket,
            {
                "type": "room_joined",
                "call_id": call_id,
                "participants": existing_participants,
            },
        )

        if existing_participants:
            await self.room_manager.broadcast(
                call_id,
                {
                    "type": "user_joined",
                    "call_id": call_id,
                    "user_id": message.user_id,
                },
                exclude_user=message.user_id,
            )

        logger.info(
            "User %s joined room %s with %d existing participants",
            message.user_id,
            call_id,
            len(existing_participants),
        )

    async def _handle_leave_room(
        self,
        websocket: WebSocketServerProtocol,
        message: SignalingMessage,
    ) -> None:
        """Handle leave_room message."""
        room = await self.room_manager.leave_room(message.user_id)

        if room:
            await self.room_manager.broadcast(
                room.call_id,
                {
                    "type": "user_left",
                    "call_id": room.call_id,
                    "user_id": message.user_id,
                },
            )

        await self._send_response(
            websocket,
            {
                "type": "room_left",
                "call_id": message.call_id,
            },
        )

        logger.info("User %s left room %s", message.user_id, message.call_id)

    async def _handle_offer(
        self,
        websocket: WebSocketServerProtocol,
        message: SignalingMessage,
    ) -> None:
        """Handle WebRTC offer SDP."""
        target_user_id = message.payload.get("target_user_id")
        if not target_user_id:
            await self._send_error(websocket, "Missing target_user_id in offer")
            return

        sdp = message.payload.get("sdp")
        if not sdp:
            await self._send_error(websocket, "Missing sdp in offer")
            return

        await self.room_manager.send_to_user(
            target_user_id,
            {
                "type": "offer",
                "call_id": message.call_id,
                "from_user_id": message.user_id,
                "payload": {
                    "sdp": sdp,
                },
            },
        )

        logger.debug(
            "Offer forwarded from %s to %s in room %s",
            message.user_id,
            target_user_id,
            message.call_id,
        )

    async def _handle_answer(
        self,
        websocket: WebSocketServerProtocol,
        message: SignalingMessage,
    ) -> None:
        """Handle WebRTC answer SDP."""
        target_user_id = message.payload.get("target_user_id")
        if not target_user_id:
            await self._send_error(websocket, "Missing target_user_id in answer")
            return

        sdp = message.payload.get("sdp")
        if not sdp:
            await self._send_error(websocket, "Missing sdp in answer")
            return

        await self.room_manager.send_to_user(
            target_user_id,
            {
                "type": "answer",
                "call_id": message.call_id,
                "from_user_id": message.user_id,
                "payload": {
                    "sdp": sdp,
                },
            },
        )

        logger.debug(
            "Answer forwarded from %s to %s in room %s",
            message.user_id,
            target_user_id,
            message.call_id,
        )

    async def _handle_ice_candidate(
        self,
        websocket: WebSocketServerProtocol,
        message: SignalingMessage,
    ) -> None:
        """Handle ICE candidate."""
        target_user_id = message.payload.get("target_user_id")
        if not target_user_id:
            await self._send_error(
                websocket,
                "Missing target_user_id in ice_candidate",
            )
            return

        candidate = message.payload.get("candidate")
        if not candidate:
            await self._send_error(websocket, "Missing candidate in ice_candidate")
            return

        await self.room_manager.send_to_user(
            target_user_id,
            {
                "type": "ice_candidate",
                "call_id": message.call_id,
                "from_user_id": message.user_id,
                "payload": {
                    "candidate": candidate,
                },
            },
        )

        logger.debug(
            "ICE candidate forwarded from %s to %s in room %s",
            message.user_id,
            target_user_id,
            message.call_id,
        )

    async def _handle_ping(
        self,
        websocket: WebSocketServerProtocol,
        message: SignalingMessage,
    ) -> None:
        """Handle ping message."""
        await self._send_response(websocket, {"type": "pong"})

    async def _handle_pong(
        self,
        websocket: WebSocketServerProtocol,
        message: SignalingMessage,
    ) -> None:
        """Handle pong message - no action needed."""
        pass

    async def _send_error(
        self,
        websocket: WebSocketServerProtocol,
        error: str,
    ) -> None:
        """Send an error message to the client."""
        message = json.dumps({
            "type": "error",
            "error": error,
        }, ensure_ascii=False)
        await websocket.send(message)

    async def _send_response(
        self,
        websocket: WebSocketServerProtocol,
        response: dict[str, Any],
    ) -> None:
        """Send a response message to the client."""
        message = json.dumps(response, ensure_ascii=False)
        await websocket.send(message)