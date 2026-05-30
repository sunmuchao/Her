"""Small bounded connection pool for WSGI handlers (PyMySQL + :class:`~outer_mysql_compat.MySQLCompatConnection`)."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import Any

from db_migrations import initialize_target_database
from outer_mysql_compat import MySQLCompatConnection
from outer_system_mysql_schema import (
    TableDef,
    ensure_database,
    ensure_schema,
    mysql_database_connect,
    parse_mysql_dsn,
)


class GatewayConnectionPool:
    """One pool per DSN; schema is ensured once at construction."""

    __slots__ = ("_avail", "_cfg", "_lock", "_sem")

    def __init__(
        self,
        dsn: str,
        target: str | Callable[[], Sequence[TableDef]],
        *,
        max_size: int = 8,
    ) -> None:
        self._cfg = parse_mysql_dsn(dsn)
        ensure_database(self._cfg)
        raw = mysql_database_connect(self._cfg)
        try:
            resolved_target = _resolve_target(target)
            if resolved_target is not None:
                initialize_target_database(raw, target=resolved_target, config=self._cfg)
            else:
                ensure_schema(raw, target(), prefix=None, config=self._cfg)
        finally:
            raw.close()

        self._sem = threading.BoundedSemaphore(max(1, max_size))
        self._lock = threading.Lock()
        self._avail: list[Any] = []

    def acquire(self, timeout: float | None = None) -> MySQLCompatConnection:
        """获取数据库连接，支持超时保护

        Args:
            timeout: 最长等待时间（秒），None 表示无限等待

        Raises:
            TimeoutError: 超时未获取到连接
        """
        acquired = self._sem.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(f"数据库连接池等待超时（{timeout}秒）")

        try:
            with self._lock:
                raw = self._avail.pop() if self._avail else mysql_database_connect(self._cfg)
        except Exception:
            self._sem.release()
            raise
        return MySQLCompatConnection(raw, self._cfg)

    def release(self, conn: MySQLCompatConnection) -> None:
        try:
            conn.rollback()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            self._sem.release()
            return
        raw = conn.driver_connection
        with self._lock:
            self._avail.append(raw)
        self._sem.release()


__all__ = ["GatewayConnectionPool"]


def _resolve_target(target: str | Callable[[], Sequence[TableDef]]) -> str | None:
    if isinstance(target, str):
        return target
    mapping = {
        "recommendation_tables": "recommendation",
        "matchmaking_tables": "matchmaking",
        "chat_tables": "chat",
    }
    return mapping.get(getattr(target, "__name__", ""))
