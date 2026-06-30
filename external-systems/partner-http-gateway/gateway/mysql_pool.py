"""Small bounded connection pool for WSGI handlers (PyMySQL + :class:`~outer_mysql_compat.MySQLCompatConnection`)."""

from __future__ import annotations

import threading
from typing import Any

from outer_mysql_compat import MySQLCompatConnection
from outer_system_mysql_schema import (
    mysql_database_connect,
    parse_mysql_dsn,
)


class GatewayConnectionPool:
    """One pool per DSN.

    Gateway startup must not perform schema migrations or DDL. Database
    initialization is owned by bootstrap to avoid concurrent DDL conflicts.
    """

    __slots__ = ("_avail", "_cfg", "_lock", "_sem")

    def __init__(
        self,
        dsn: str,
        target: object,
        *,
        max_size: int = 8,
    ) -> None:
        self._cfg = parse_mysql_dsn(dsn)
        del target
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
                raw = self._unwrap_driver_connection(
                    self._avail.pop() if self._avail else mysql_database_connect(self._cfg)
                )
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
        raw = self._unwrap_driver_connection(conn.driver_connection)
        with self._lock:
            self._avail.append(raw)
        self._sem.release()

    @staticmethod
    def _unwrap_driver_connection(conn: Any) -> Any:
        raw = conn
        seen: set[int] = set()
        while hasattr(raw, "driver_connection"):
            raw_id = id(raw)
            if raw_id in seen:
                break
            seen.add(raw_id)
            raw = raw.driver_connection
        return raw


__all__ = ["GatewayConnectionPool"]
