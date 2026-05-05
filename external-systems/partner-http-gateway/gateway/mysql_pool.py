"""Small bounded connection pool for WSGI handlers (PyMySQL + :class:`~outer_mysql_compat.MySQLCompatConnection`)."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import Any

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
        tables: Callable[[], Sequence[TableDef]],
        *,
        max_size: int = 8,
    ) -> None:
        self._cfg = parse_mysql_dsn(dsn)
        ensure_database(self._cfg)
        raw = mysql_database_connect(self._cfg)
        ensure_schema(raw, tables(), prefix=None, config=self._cfg)
        raw.close()

        self._sem = threading.BoundedSemaphore(max(1, max_size))
        self._lock = threading.Lock()
        self._avail: list[Any] = []

    def acquire(self) -> MySQLCompatConnection:
        self._sem.acquire()
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
