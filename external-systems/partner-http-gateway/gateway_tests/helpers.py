from __future__ import annotations

import io
import json
from typing import Any

import outer_system_mysql_schema as mysql_schema
from partner_search.search_cache import clear_search_cache


_PROFILE_TABLE_SQL = """
CREATE TABLE `profiles` (
  `id` BIGINT PRIMARY KEY,
  `name` VARCHAR(255),
  `gender` VARCHAR(32),
  `age` INT,
  `city` VARCHAR(64),
  `education` VARCHAR(64),
  `job` VARCHAR(255),
  `income_range` VARCHAR(64),
  `marital_status` VARCHAR(64),
  `has_children` TINYINT(1),
  `relationship_goal` VARCHAR(64),
  `profile_status` VARCHAR(32),
  `verified_level` VARCHAR(32),
  `photo_verification_level` VARCHAR(32),
  `education_verification_status` VARCHAR(32),
  `job_verification_status` VARCHAR(32),
  `income_verification_status` VARCHAR(32),
  `profile_review_status` VARCHAR(32),
  `job_change_count_30d` INT,
  `photo_count` INT,
  `life_routine` VARCHAR(64),
  `communication_style` VARCHAR(64),
  `values` TEXT,
  `notes` TEXT,
  `last_active_at` DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_PROFILE_PHOTO_TABLE_SQL = """
CREATE TABLE `profile_photos` (
  `id` BIGINT PRIMARY KEY AUTO_INCREMENT,
  `profile_id` BIGINT NOT NULL,
  `photo_url` VARCHAR(512) NOT NULL,
  `is_primary` TINYINT(1) DEFAULT 0,
  `sort_order` INT DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_PROFILE_INSERT_SQL = """
INSERT INTO `profiles` (
  `id`,
  `name`,
  `gender`,
  `age`,
  `city`,
  `education`,
  `job`,
  `income_range`,
  `marital_status`,
  `has_children`,
  `relationship_goal`,
  `profile_status`,
  `verified_level`,
  `photo_verification_level`,
  `education_verification_status`,
  `job_verification_status`,
  `income_verification_status`,
  `profile_review_status`,
  `job_change_count_30d`,
  `photo_count`,
  `life_routine`,
  `communication_style`,
  `values`,
  `notes`,
  `last_active_at`
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""


def build_wsgi_env(
    method: str,
    path: str,
    body: dict[str, Any] | bytes | None = None,
    query: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if isinstance(body, bytes):
        payload = body
    else:
        payload = json.dumps(body).encode("utf-8") if body is not None else b""
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query,
        "CONTENT_LENGTH": str(len(payload)),
        "wsgi.input": io.BytesIO(payload),
        "REMOTE_ADDR": "127.0.0.1",
    }
    if extra:
        environ.update(extra)
    return environ


def run_wsgi_json(app: Any, environ: dict[str, Any]) -> tuple[str, dict[str, Any], list[tuple[str, str]]]:
    status = ""
    headers: list[tuple[str, str]] = []

    def start_response(current_status: str, current_headers: list[tuple[str, str]]) -> None:
        nonlocal status, headers
        status = current_status
        headers = current_headers

    output = b"".join(app(environ, start_response))
    payload = json.loads(output.decode("utf-8")) if output else {}
    return status, payload, headers


def call_gateway_json(
    gateway: Any,
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    query: str = "",
    extra: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    status, payload, _headers = run_wsgi_json(
        gateway,
        build_wsgi_env(method, path, body=body, query=query, extra=extra),
    )
    return status, payload


def search_test_config(search_dsn: str) -> Any:
    config = mysql_schema.parse_mysql_dsn(search_dsn)
    mysql_schema.ensure_database(config)
    return config


def open_search_conn(search_config: Any):
    return mysql_schema.mysql_database_connect(search_config)


def ensure_search_schema(search_config: Any) -> None:
    clear_search_cache()
    conn = open_search_conn(search_config)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS `profile_photos`")
            cursor.execute("DROP TABLE IF EXISTS `profiles`")
            cursor.execute(_PROFILE_TABLE_SQL)
            cursor.execute(_PROFILE_PHOTO_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()


def reset_search_rows(search_config: Any) -> None:
    clear_search_cache()
    conn = open_search_conn(search_config)
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM `profile_photos`")
            cursor.execute("DELETE FROM `profiles`")
        conn.commit()
    finally:
        conn.close()


def insert_search_profile(search_config: Any, row: tuple[Any, ...]) -> None:
    clear_search_cache()
    conn = open_search_conn(search_config)
    try:
        with conn.cursor() as cursor:
            cursor.execute(_PROFILE_INSERT_SQL, row)
        conn.commit()
    finally:
        conn.close()


def insert_search_profiles(search_config: Any, rows: list[tuple[Any, ...]]) -> None:
    clear_search_cache()
    conn = open_search_conn(search_config)
    try:
        with conn.cursor() as cursor:
            cursor.executemany(_PROFILE_INSERT_SQL, rows)
        conn.commit()
    finally:
        conn.close()


def auth_headers(token: str | None) -> dict[str, str]:
    if not token:
        return {}
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}
