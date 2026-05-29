"""Room management for WebRTC signaling server."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)


@dataclass
class Participant:
    """A participant in a call room."""

    user_id: str
    websocket: WebSocketServerProtocol
    joined_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Room:
    """A call room for WebRTC signaling."""

    call_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    participants: dict[str, Participant] = field(default_factory=dict)

    def add_participant(self, participant: Participant) -> None:
        """Add a participant to the room."""
        self.participants[participant.user_id] = participant
        logger.info(
            "Participant %s joined room %s",
            participant.user_id,
            self.call_id,
        )

    def remove_participant(self, user_id: str) -> Participant | None:
        """Remove a participant from the room."""
        participant = self.participants.pop(user_id, None)
        if participant:
            logger.info(
                "Participant %s left room %s",
                user_id,
                self.call_id,
            )
        return participant

    def get_other_participants(self, user_id: str) -> list[Participant]:
        """Get all participants except the specified user."""
        return [
            p for p in self.participants.values()
            if p.user_id != user_id
        ]

    def is_empty(self) -> bool:
        """Check if the room is empty."""
        return len(self.participants) == 0


class RoomManager:
    """Manages call rooms for signaling."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._user_rooms: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def create_room(self, call_id: str) -> Room:
        """Create a new room."""
        async with self._lock:
            if call_id in self._rooms:
                logger.warning("Room %s already exists", call_id)
                return self._rooms[call_id]

            room = Room(call_id=call_id)
            self._rooms[call_id] = room
            logger.info("Created room %s", call_id)
            return room

    async def get_or_create_room(self, call_id: str) -> Room:
        """Get an existing room or create a new one."""
        async with self._lock:
            if call_id not in self._rooms:
                room = Room(call_id=call_id)
                self._rooms[call_id] = room
                logger.info("Created room %s", call_id)
            return self._rooms[call_id]

    async def get_room(self, call_id: str) -> Room | None:
        """Get a room by call_id."""
        async with self._lock:
            return self._rooms.get(call_id)

    async def join_room(
        self,
        call_id: str,
        user_id: str,
        websocket: WebSocketServerProtocol,
    ) -> Room:
        """Add a user to a room."""
        room = await self.get_or_create_room(call_id)

        async with self._lock:
            participant = Participant(
                user_id=user_id,
                websocket=websocket,
            )
            room.add_participant(participant)
            self._user_rooms[user_id] = call_id

        return room

    async def leave_room(self, user_id: str) -> Room | None:
        """Remove a user from their current room."""
        async with self._lock:
            call_id = self._user_rooms.pop(user_id, None)
            if not call_id:
                return None

            room = self._rooms.get(call_id)
            if room:
                room.remove_participant(user_id)
                if room.is_empty():
                    del self._rooms[call_id]
                    logger.info("Removed empty room %s", call_id)

            return room

    async def get_user_room(self, user_id: str) -> Room | None:
        """Get the room a user is currently in."""
        async with self._lock:
            call_id = self._user_rooms.get(user_id)
            if call_id:
                return self._rooms.get(call_id)
            return None

    async def broadcast(
        self,
        call_id: str,
        message: dict,
        exclude_user: str | None = None,
    ) -> int:
        """Broadcast a message to all participants in a room.

        Returns the number of recipients.
        """
        room = await self.get_room(call_id)
        if not room:
            logger.warning("Room %s not found for broadcast", call_id)
            return 0

        recipients = room.participants.values()
        if exclude_user:
            recipients = [p for p in recipients if p.user_id != exclude_user]

        message_str = _serialize_message(message)
        sent_count = 0

        for participant in recipients:
            try:
                await participant.websocket.send(message_str)
                sent_count += 1
            except Exception:
                logger.exception(
                    "Failed to send message to %s in room %s",
                    participant.user_id,
                    call_id,
                )

        return sent_count

    async def send_to_user(
        self,
        user_id: str,
        message: dict,
    ) -> bool:
        """Send a message to a specific user."""
        room = await self.get_user_room(user_id)
        if not room:
            logger.warning("User %s not in any room", user_id)
            return False

        participant = room.participants.get(user_id)
        if not participant:
            logger.warning("Participant %s not found in room", user_id)
            return False

        try:
            await participant.websocket.send(_serialize_message(message))
            return True
        except Exception:
            logger.exception("Failed to send message to %s", user_id)
            return False

    def get_room_count(self) -> int:
        """Get the total number of active rooms."""
        return len(self._rooms)

    def get_participant_count(self) -> int:
        """Get the total number of participants across all rooms."""
        return sum(len(r.participants) for r in self._rooms.values())


def _serialize_message(message: dict) -> str:
    """Serialize a message dict to JSON string."""
    import json
    return json.dumps(message, ensure_ascii=False)