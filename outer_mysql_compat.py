"""MySQL connection wrapper: **always use ``?`` placeholders** in SQL strings.

They are translated to PyMySQL ``%s`` in :meth:`MySQLCompatConnection.execute` (naïve
``str.replace``). Do **not** pass raw ``%s`` in SQL that will be doubled or mis-parsed;
use only this wrapper for parameterized queries against outer-system code.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Iterable, Mapping


class _CursorResult:
    __slots__ = ("_cursor",)

    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return int(self._cursor.rowcount or 0)

    def fetchone(self) -> Mapping[str, Any] | None:
        row = self._cursor.fetchone()
        return _normalize_row(row)

    def fetchall(self) -> list[Mapping[str, Any]]:
        rows = self._cursor.fetchall()
        return [_normalize_row(r) for r in rows]


def _normalize_row(row: Any) -> Mapping[str, Any] | None:
    if row is None:
        return None
    if not isinstance(row, dict):
        raise TypeError("Expected dict row from PyMySQL DictCursor")
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, datetime):
            out[key] = value.replace(microsecond=0).isoformat(sep=" ")
        elif isinstance(value, date):
            out[key] = value.isoformat()
        elif isinstance(value, bytes):
            out[key] = value.decode("utf-8", errors="replace")
        else:
            out[key] = value
    return out


class MySQLCompatConnection:
    """Thin facade: `execute` maps `?` → `%s`, returns a result with `fetchone` / `fetchall`; plus `commit`, `rollback`, `close`."""

    __slots__ = ("_conn", "config", "_lastrowid", "dsn")

    def __init__(self, pymysql_conn: Any, config: dict[str, Any], *, dsn: str | None = None) -> None:
        self._conn = pymysql_conn
        self.config = config
        self._lastrowid = 0
        self.dsn = str(dsn).strip() if dsn else None

    def execute(self, sql: str, parameters: Iterable[Any] | None = None) -> _CursorResult:
        mysql_sql = sql.replace("?", "%s")
        params = tuple(parameters or ())
        cur = self._conn.cursor()
        cur.execute(mysql_sql, params)
        self._lastrowid = int(cur.lastrowid or 0)
        return _CursorResult(cur)

    @property
    def lastrowid(self) -> int:
        return self._lastrowid

    @property
    def driver_connection(self) -> Any:
        """Underlying PyMySQL connection (for connection pooling release only)."""

        return self._conn

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


from decimal import Decimal


class DecimalEncoder(json.JSONEncoder):
    """自定义JSON编码器，支持Decimal类型"""

    def default(self, obj):
        """处理无法直接序列化的类型"""
        if isinstance(obj, Decimal):
            # Decimal转换为float或int，避免精度丢失
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        # 其他类型调用父类的default方法
        return super().default(obj)


def json_dumps(value: Any) -> str:
    """JSON for persisted outer-system columns (sorted keys, UTF-8, ``None`` → ``{}``).

    支持Decimal类型的序列化。
    """

    payload: Any = {} if value is None else value
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, cls=DecimalEncoder)


def json_loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    return json.loads(value)


def row_to_dict(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def connect_mysql_repo_db(dsn: str, *, subsystem_name: str) -> MySQLCompatConnection:
    """Open a :class:`MySQLCompatConnection` after ``ensure_database`` (outer systems)."""

    if not str(dsn).lower().startswith("mysql://"):
        raise ValueError(
            f"{subsystem_name} storage requires a MySQL DSN, e.g. "
            "mysql://user:pass@127.0.0.1:3307/database"
        )
    import outer_system_mysql_schema as _schema  # noqa: PLC0415

    config = _schema.parse_mysql_dsn(str(dsn))
    _schema.ensure_database(config)
    raw = _schema.mysql_database_connect(config)
    return MySQLCompatConnection(raw, config, dsn=str(dsn))
