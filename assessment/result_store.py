from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from persona_memory_sync.persona_memory_lib import (
    apply_persona_patch,
    fetch_persona,
    mysql_connect,
    normalize_patch,
    parse_mysql_source,
    quote_mysql_ident,
    release_persona_connection,
)


DEFAULT_PERSONA_TABLE = "user_personas"
DEFAULT_OBSERVATION_TABLE = "user_persona_observations"
DEFAULT_RESULTS_TABLE = "assessment_results"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_json(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        data = json.loads(str(value))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_source(source: str | None) -> tuple[str, str]:
    parsed = parse_mysql_source(source)
    return str(parsed["source"]), str(parsed["table"])


def merge_personality_summary(
    *,
    source: str | None,
    user_key: str,
    summary_key: str,
    summary_payload: dict[str, Any],
    source_type: str = "explicit",
    source_channel: str = "assessment",
    evidence_text: str | None = None,
    conversation_ref: str | None = None,
    persona_table: str = DEFAULT_PERSONA_TABLE,
    observation_table: str = DEFAULT_OBSERVATION_TABLE,
) -> dict[str, Any]:
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            persona = fetch_persona(cursor, persona_table, user_key=user_key) or {}
            traits = _parse_json(persona.get("self_personality_traits_json"))
    finally:
        release_persona_connection(normalized_source, conn)

    traits[summary_key] = summary_payload
    return apply_persona_patch(
        source=normalized_source,
        user_key=user_key,
        source_type=source_type,
        normalized_patch=normalize_patch({"self_personality_traits_json": _json(traits)}),
        persona_table=persona_table,
        observation_table=observation_table,
        evidence_text=evidence_text,
        conversation_ref=conversation_ref,
        apply_scope="persona_only",
        sync_profile=False,
        source_channel=source_channel,
    )


def store_assessment_result(
    *,
    source: str | None,
    user_key: str,
    assessment_id: str,
    assessment_type: str,
    raw_result: dict[str, Any],
    summary: dict[str, Any] | None = None,
    interpretation: dict[str, Any] | None = None,
    result_version: str = "v1",
    source_channel: str = "assessment",
    completed_at: str | None = None,
    results_table: str = DEFAULT_RESULTS_TABLE,
) -> None:
    normalized_source, _ = _resolve_source(source)
    completed_at = completed_at or _now()
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {quote_mysql_ident(results_table)}
                  (user_key, assessment_id, assessment_type, result_version, summary_json,
                   raw_result_json, interpretation_json, source_channel, completed_at, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  user_key = VALUES(user_key),
                  assessment_type = VALUES(assessment_type),
                  result_version = VALUES(result_version),
                  summary_json = VALUES(summary_json),
                  raw_result_json = VALUES(raw_result_json),
                  interpretation_json = COALESCE(VALUES(interpretation_json), interpretation_json),
                  source_channel = VALUES(source_channel),
                  completed_at = VALUES(completed_at)
                """,
                (
                    user_key,
                    assessment_id,
                    assessment_type,
                    result_version,
                    _json(summary) if summary is not None else None,
                    _json(raw_result),
                    _json(interpretation) if interpretation is not None else None,
                    source_channel,
                    completed_at,
                    _now(),
                ),
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)


def update_assessment_interpretation(
    *,
    source: str | None,
    assessment_id: str,
    interpretation: dict[str, Any],
    results_table: str = DEFAULT_RESULTS_TABLE,
) -> None:
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {quote_mysql_ident(results_table)}
                SET interpretation_json = %s
                WHERE assessment_id = %s
                """,
                (_json(interpretation), assessment_id),
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)


def get_latest_assessment_result(
    *,
    source: str | None,
    user_key: str,
    assessment_type: str,
    results_table: str = DEFAULT_RESULTS_TABLE,
) -> dict[str, Any] | None:
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT assessment_id, assessment_type, result_version, summary_json, raw_result_json,
                       interpretation_json, source_channel, completed_at, created_at, user_key
                FROM {quote_mysql_ident(results_table)}
                WHERE user_key = %s
                  AND assessment_type = %s
                ORDER BY completed_at DESC, id DESC
                LIMIT 1
                """,
                (user_key, assessment_type),
            )
            row = cursor.fetchone()
    finally:
        release_persona_connection(normalized_source, conn)
    return _row_to_result(row)


def get_assessment_result(
    *,
    source: str | None,
    assessment_id: str,
    results_table: str = DEFAULT_RESULTS_TABLE,
) -> dict[str, Any] | None:
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT assessment_id, assessment_type, result_version, summary_json, raw_result_json,
                       interpretation_json, source_channel, completed_at, created_at, user_key
                FROM {quote_mysql_ident(results_table)}
                WHERE assessment_id = %s
                LIMIT 1
                """,
                (assessment_id,),
            )
            row = cursor.fetchone()
    finally:
        release_persona_connection(normalized_source, conn)
    return _row_to_result(row)


def _row_to_result(row: Any) -> dict[str, Any] | None:
    if not row:
        return None
    if isinstance(row, dict):
        return {
            "assessment_id": str(row.get("assessment_id") or ""),
            "assessment_type": str(row.get("assessment_type") or ""),
            "result_version": str(row.get("result_version") or ""),
            "summary_json": _parse_json(row.get("summary_json")),
            "raw_result_json": _parse_json(row.get("raw_result_json")),
            "interpretation_json": _parse_json(row.get("interpretation_json")),
            "source_channel": str(row.get("source_channel") or ""),
            "completed_at": str(row.get("completed_at") or ""),
            "created_at": str(row.get("created_at") or ""),
            "user_key": str(row.get("user_key") or ""),
        }
    assessment_id, assessment_type, result_version, summary_json, raw_result_json, interpretation_json, source_channel, completed_at, created_at, user_key = row
    return {
        "assessment_id": str(assessment_id or ""),
        "assessment_type": str(assessment_type or ""),
        "result_version": str(result_version or ""),
        "summary_json": _parse_json(summary_json),
        "raw_result_json": _parse_json(raw_result_json),
        "interpretation_json": _parse_json(interpretation_json),
        "source_channel": str(source_channel or ""),
        "completed_at": str(completed_at or ""),
        "created_at": str(created_at or ""),
        "user_key": str(user_key or ""),
    }
