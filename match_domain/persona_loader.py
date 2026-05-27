"""Load collected persona rows and observations for compile/read layers."""

from __future__ import annotations

from typing import Any


def load_persona_row(*, source: str, user_key: str) -> dict[str, Any] | None:
    if not source or not user_key:
        return None
    try:
        from persona_memory_sync.persona_memory_lib import (
            DEFAULT_PERSONA_TABLE,
            fetch_persona,
            mysql_connect,
        )
    except ImportError:
        return None

    conn = mysql_connect(source)
    try:
        with conn.cursor() as cursor:
            row = fetch_persona(cursor, DEFAULT_PERSONA_TABLE, user_key=str(user_key))
            return dict(row) if row else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        conn.close()


def load_persona_observations(*, source: str, user_key: str) -> list[dict[str, Any]]:
    if not source or not user_key:
        return []
    try:
        from persona_memory_sync.persona_memory_lib import (
            DEFAULT_OBSERVATION_TABLE,
            mysql_connect,
            quote_mysql_ident,
        )
    except ImportError:
        return []

    conn = mysql_connect(source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT field_name, field_value, source_type, evidence_text,
                       conversation_ref, source_channel, created_at
                FROM {quote_mysql_ident(DEFAULT_OBSERVATION_TABLE)}
                WHERE user_key = %s
                ORDER BY id ASC
                """,
                (str(user_key),),
            )
            rows = cursor.fetchall() or []
            return [dict(row) for row in rows]
    except Exception:  # noqa: BLE001
        return []
    finally:
        conn.close()


def load_persona_by_profile_id(*, source: str, profile_id: int) -> dict[str, Any] | None:
    if not source or profile_id is None:
        return None
    try:
        from persona_memory_sync.persona_memory_lib import (
            DEFAULT_PERSONA_TABLE,
            mysql_connect,
            quote_mysql_ident,
        )
    except ImportError:
        return None

    conn = mysql_connect(source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT *
                FROM {quote_mysql_ident(DEFAULT_PERSONA_TABLE)}
                WHERE profile_id = %s
                ORDER BY id ASC
                LIMIT 1
                """,
                (int(profile_id),),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        conn.close()


def load_personas_by_profile_ids(
    *,
    source: str,
    profile_ids: list[int],
) -> dict[int, dict[str, Any]]:
    if not source or not profile_ids:
        return {}
    try:
        from persona_memory_sync.persona_memory_lib import (
            DEFAULT_PERSONA_TABLE,
            mysql_connect,
            quote_mysql_ident,
        )
    except ImportError:
        return {}

    placeholders = ", ".join(["%s"] * len(profile_ids))
    conn = mysql_connect(source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT *
                FROM {quote_mysql_ident(DEFAULT_PERSONA_TABLE)}
                WHERE profile_id IN ({placeholders})
                ORDER BY id ASC
                """,
                tuple(int(item) for item in profile_ids),
            )
            rows = cursor.fetchall() or []
            by_profile: dict[int, dict[str, Any]] = {}
            for row in rows:
                profile_id = int(row.get("profile_id") or 0)
                if profile_id and profile_id not in by_profile:
                    by_profile[profile_id] = dict(row)
            return by_profile
    except Exception:  # noqa: BLE001
        return {}
    finally:
        conn.close()


def load_persona_for_discovery(
    *,
    source: str,
    profile_id: int | None = None,
    requester_id: int | None = None,
) -> dict[str, Any] | None:
    if not source:
        return None
    user_keys: list[str] = []
    for raw in (profile_id, requester_id):
        if raw is None:
            continue
        try:
            normalized = int(raw)
        except (TypeError, ValueError):
            continue
        if normalized <= 0:
            continue
        key = str(normalized)
        if key not in user_keys:
            user_keys.append(key)
    for user_key in user_keys:
        row = load_persona_row(source=source, user_key=user_key)
        if row:
            return row
    if profile_id is not None:
        try:
            normalized_profile_id = int(profile_id)
        except (TypeError, ValueError):
            normalized_profile_id = 0
        if normalized_profile_id > 0:
            return load_persona_by_profile_id(source=source, profile_id=normalized_profile_id)
    return None


def load_collected_bundle(*, source: str, user_key: str) -> dict[str, Any]:
    persona = load_persona_row(source=source, user_key=user_key) or {}
    observations = load_persona_observations(source=source, user_key=user_key)
    from match_domain.collected_metadata import build_collected_items

    return {
        "user_key": str(user_key),
        "persona": persona,
        "observations": observations,
        "collected_items": build_collected_items(persona, observations),
    }


__all__ = [
    "load_collected_bundle",
    "load_persona_by_profile_id",
    "load_persona_for_discovery",
    "load_personas_by_profile_ids",
    "load_persona_observations",
    "load_persona_row",
]
