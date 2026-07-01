"""SSE connection manager."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aiohttp.web import StreamResponse

logger = logging.getLogger(__name__)


@dataclass
class SSEConnection:
    """SSE connection for a user."""

    user_id: str
    case_id: str
    response: StreamResponse
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    connected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class DiscoverySSEConnection:
    """SSE connection for discovery."""

    profile_id: str
    session_id: str
    response: StreamResponse
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    connected_at: datetime = field(default_factory=datetime.utcnow)


class ConnectionManager:
    """Manage SSE connections for chat message push."""

    def __init__(self) -> None:
        """Initialize connection manager."""
        # case_id -> list of connections (for chat)
        self._connections: dict[str, list[SSEConnection]] = {}
        # user_id -> connection (one user can only have one connection per case)
        self._user_connections: dict[str, SSEConnection] = {}

        # session_id -> list of connections (for discovery) - 新增
        self._discovery_connections: dict[str, list[DiscoverySSEConnection]] = {}
        # profile_id -> connection (one profile can only have one discovery connection) - 新增
        self._profile_connections: dict[str, DiscoverySSEConnection] = {}

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

    async def add_connection(
        self,
        user_id: str,
        case_id: str,
        response: StreamResponse,
    ) -> SSEConnection:
        """Add a new SSE connection.

        Args:
            user_id: User ID
            case_id: Case ID
            response: SSE StreamResponse

        Returns:
            SSEConnection object
        """
        async with self._lock:
            # Remove old connection if exists (handle reconnect)
            if user_id in self._user_connections:
                old_conn = self._user_connections[user_id]
                await self._remove_connection_internal(old_conn)
                logger.info(f"Removed old connection for user {user_id}")

            # Create new connection
            conn = SSEConnection(
                user_id=user_id,
                case_id=case_id,
                response=response,
            )

            # Add to both dictionaries
            self._user_connections[user_id] = conn
            if case_id not in self._connections:
                self._connections[case_id] = []
            self._connections[case_id].append(conn)

            logger.info(
                f"Added connection: user={user_id}, case={case_id}, "
                f"total_connections={len(self._user_connections)}"
            )

            return conn

    async def remove_connection(self, user_id: str) -> None:
        """Remove a connection by user_id.

        Args:
            user_id: User ID
        """
        async with self._lock:
            if user_id in self._user_connections:
                conn = self._user_connections[user_id]
                await self._remove_connection_internal(conn)

    async def _remove_connection_internal(self, conn: SSEConnection) -> None:
        """Internal method to remove connection without lock."""
        self._user_connections.pop(conn.user_id, None)

        if conn.case_id in self._connections:
            self._connections[conn.case_id] = [
                c for c in self._connections[conn.case_id] if c.user_id != conn.user_id
            ]
            # Clean up empty case_id entries
            if not self._connections[conn.case_id]:
                self._connections.pop(conn.case_id, None)

        logger.info(
            f"Removed connection: user={conn.user_id}, case={conn.case_id}, "
            f"remaining={len(self._user_connections)}"
        )

    async def get_case_connections(self, case_id: str) -> list[SSEConnection]:
        """Get all connections for a case.

        Args:
            case_id: Case ID

        Returns:
            List of SSEConnection objects
        """
        async with self._lock:
            return list(self._connections.get(case_id, []))

    async def get_user_connection(self, user_id: str) -> SSEConnection | None:
        """Get connection for a user.

        Args:
            user_id: User ID

        Returns:
            SSEConnection or None if not found
        """
        async with self._lock:
            return self._user_connections.get(user_id)

    async def send_to_user(self, user_id: str, event_type: str, data: dict) -> bool:
        """Send an SSE event to a specific user.

        Args:
            user_id: User ID
            event_type: Event type (e.g., 'message', 'heartbeat')
            data: Event data dictionary

        Returns:
            True if sent successfully, False otherwise
        """
        conn = await self.get_user_connection(user_id)
        if not conn:
            logger.warning(f"No connection found for user {user_id}")
            return False

        try:
            await send_event(conn.response, event_type, data)
            conn.last_heartbeat = datetime.utcnow()
            return True
        except Exception as e:
            logger.error(f"Failed to send to user {user_id}: {e}")
            await self.remove_connection(user_id)
            return False

    async def broadcast_to_case(
        self,
        case_id: str,
        event_type: str,
        data: dict,
        exclude_user: str | None = None,
    ) -> int:
        """Broadcast an SSE event to all users in a case.

        Args:
            case_id: Case ID
            event_type: Event type
            data: Event data dictionary
            exclude_user: User ID to exclude (e.g., message sender)

        Returns:
            Number of successful sends
        """
        connections = await self.get_case_connections(case_id)
        sent_count = 0

        for conn in connections:
            if exclude_user and conn.user_id == exclude_user:
                continue

            try:
                await send_event(conn.response, event_type, data)
                conn.last_heartbeat = datetime.utcnow()
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to broadcast to {conn.user_id}: {e}")
                await self.remove_connection(conn.user_id)

        logger.info(
            f"Broadcast to case {case_id}: sent={sent_count}, "
            f"total={len(connections)}, excluded={exclude_user}"
        )

        return sent_count

    # ========== Discovery SSE methods ==========

    async def add_discovery_connection(
        self,
        profile_id: str,
        session_id: str,
        response: StreamResponse,
    ) -> DiscoverySSEConnection:
        """Add a new Discovery SSE connection.

        Args:
            profile_id: Profile ID
            session_id: Discovery Session ID
            response: SSE StreamResponse

        Returns:
            DiscoverySSEConnection object
        """
        async with self._lock:
            # Remove old connection if exists (handle reconnect)
            if profile_id in self._profile_connections:
                old_conn = self._profile_connections[profile_id]
                await self._remove_discovery_connection_internal(old_conn)
                logger.info(f"[Discovery] Removed old connection for profile {profile_id}")

            # Create new connection
            conn = DiscoverySSEConnection(
                profile_id=profile_id,
                session_id=session_id,
                response=response,
            )

            # Add to both dictionaries
            self._profile_connections[profile_id] = conn
            if session_id not in self._discovery_connections:
                self._discovery_connections[session_id] = []
            self._discovery_connections[session_id].append(conn)

            logger.info(
                f"[Discovery] Added connection: profile={profile_id}, session={session_id}, "
                f"total_connections={len(self._profile_connections)}"
            )

            return conn

    async def remove_discovery_connection(self, profile_id: str) -> None:
        """Remove a Discovery connection by profile_id.

        Args:
            profile_id: Profile ID
        """
        async with self._lock:
            if profile_id in self._profile_connections:
                conn = self._profile_connections[profile_id]
                await self._remove_discovery_connection_internal(conn)

    async def _remove_discovery_connection_internal(self, conn: DiscoverySSEConnection) -> None:
        """Internal method to remove Discovery connection without lock."""
        self._profile_connections.pop(conn.profile_id, None)

        if conn.session_id in self._discovery_connections:
            self._discovery_connections[conn.session_id] = [
                c for c in self._discovery_connections[conn.session_id] if c.profile_id != conn.profile_id
            ]
            # Clean up empty session_id entries
            if not self._discovery_connections[conn.session_id]:
                self._discovery_connections.pop(conn.session_id, None)

        logger.info(
            f"[Discovery] Removed connection: profile={conn.profile_id}, session={conn.session_id}, "
            f"remaining={len(self._profile_connections)}"
        )

    async def get_discovery_session_connections(self, session_id: str) -> list[DiscoverySSEConnection]:
        """Get all connections for a Discovery session.

        Args:
            session_id: Discovery Session ID

        Returns:
            List of DiscoverySSEConnection objects
        """
        async with self._lock:
            return list(self._discovery_connections.get(session_id, []))

    async def broadcast_to_discovery_session(
        self,
        session_id: str,
        event_type: str,
        data: dict,
    ) -> int:
        """Broadcast an SSE event to all profiles in a Discovery session.

        Args:
            session_id: Discovery Session ID
            event_type: Event type
            data: Event data dictionary

        Returns:
            Number of successful sends
        """
        connections = await self.get_discovery_session_connections(session_id)
        sent_count = 0

        for conn in connections:
            try:
                await send_event(conn.response, event_type, data)
                conn.last_heartbeat = datetime.utcnow()
                sent_count += 1
            except Exception as e:
                logger.error(f"[Discovery] Failed to broadcast to {conn.profile_id}: {e}")
                await self.remove_discovery_connection(conn.profile_id)

        logger.info(
            f"[Discovery] Broadcast to session {session_id}: sent={sent_count}, "
            f"total={len(connections)}"
        )

        return sent_count

    async def get_profile_discovery_connections(self, profile_id: str) -> list[DiscoverySSEConnection]:
        """Get all discovery connections for a specific profile.

        Args:
            profile_id: Profile ID

        Returns:
            List of DiscoverySSEConnection objects for this profile
        """
        async with self._lock:
            # 一个profile可能有多个discovery session连接（多标签页）
            conn = self._profile_connections.get(profile_id)
            return [conn] if conn else []

    async def broadcast_to_profile_discovery(
        self,
        profile_id: str,
        event_type: str,
        data: dict,
    ) -> int:
        """Broadcast an SSE event to all discovery connections for a profile.

        推荐卡片推送专用：一个用户可能在多个discovery session中，都要推送

        Args:
            profile_id: Profile ID
            event_type: Event type
            data: Event data dictionary

        Returns:
            Number of successful sends
        """
        connections = await self.get_profile_discovery_connections(profile_id)
        sent_count = 0

        for conn in connections:
            try:
                await send_event(conn.response, event_type, data)
                conn.last_heartbeat = datetime.utcnow()
                sent_count += 1
                logger.info(
                    f"[Recommendation] Pushed to profile={profile_id}, session={conn.session_id}"
                )
            except Exception as e:
                logger.error(f"[Recommendation] Failed to push to {conn.profile_id}: {e}")
                await self.remove_discovery_connection(conn.profile_id)

        logger.info(
            f"[Recommendation] Broadcast to profile {profile_id}: sent={sent_count}, "
            f"total={len(connections)}"
        )

        return sent_count

    def get_stats(self) -> dict:
        """Get connection statistics.

        Returns:
            Dictionary with connection stats
        """
        return {
            "total_connections": len(self._user_connections),
            "total_cases": len(self._connections),
            "connections_per_case": {
                case_id: len(conns)
                for case_id, conns in self._connections.items()
            },
        }


async def send_event(response: StreamResponse, event_type: str, data: dict) -> None:
    """Send an SSE event.

    Args:
        response: StreamResponse object
        event_type: Event type
        data: Event data dictionary
    """
    import json

    event_str = f"event: {event_type}\n"
    event_str += f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    await response.write(event_str.encode("utf-8"))