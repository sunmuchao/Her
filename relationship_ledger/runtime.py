"""Runtime helpers for cross-system ledger mirroring."""

from __future__ import annotations

from collections.abc import Mapping
import os
from typing import Any, TypedDict

from match_domain import MatchEvent, ProfileRef

from .service import append_event, get_relation_by_key
from .storage import DEFAULT_RELATION_LEDGER_MYSQL_DSN, connect_db, initialize_database


class LedgerMirrorEntry(TypedDict, total=False):
    event: MatchEvent
    relation_key: str
    owner_profile_ref: ProfileRef | Mapping[str, Any] | None
    target_profile_ref: ProfileRef | Mapping[str, Any] | None
    case_id: str | None
    case_type: str | None


def ledger_read_mode() -> str:
    configured = os.environ.get("HER_RELATION_LEDGER_DB") or DEFAULT_RELATION_LEDGER_MYSQL_DSN
    if not configured:
        return "legacy_fallback"
    return os.environ.get("HER_RELATION_LEDGER_READ_MODE", "ledger_primary").strip() or "ledger_primary"


def ledger_reads_require_primary() -> bool:
    return ledger_read_mode() == "ledger_primary"


def ledger_allow_legacy_fallback() -> bool:
    if not ledger_reads_require_primary():
        return True
    raw = os.environ.get("HER_ALLOW_LEGACY_TIMELINE_FALLBACK", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


_CONN_LEDGER_MIRRORS: dict[int, list[LedgerMirrorEntry]] = {}


def ledger_mirror_for_conn(conn: Any) -> list[LedgerMirrorEntry]:
    key = id(conn)
    mirror = _CONN_LEDGER_MIRRORS.get(key)
    if mirror is None:
        mirror = []
        _CONN_LEDGER_MIRRORS[key] = mirror
    return mirror


def defer_ledger_event(conn: Any, entry: LedgerMirrorEntry) -> None:
    ledger_mirror_for_conn(conn).append(entry)


def commit_conn_with_ledger(
    conn: Any,
    *,
    extra_mirror: list[LedgerMirrorEntry] | None = None,
) -> None:
    conn.commit()
    key = id(conn)
    entries = list(_CONN_LEDGER_MIRRORS.pop(key, []))
    if extra_mirror:
        entries.extend(extra_mirror)
    flush_ledger_mirror(entries)


def append_event_to_default_ledger(
    *,
    event: MatchEvent,
    relation_key: str,
    owner_profile_ref: ProfileRef | Mapping[str, Any] | None = None,
    target_profile_ref: ProfileRef | Mapping[str, Any] | None = None,
    case_id: str | None = None,
    case_type: str | None = None,
    dsn: str | None = None,
) -> dict[str, Any]:
    resolved_dsn = dsn or os.environ.get("HER_RELATION_LEDGER_DB") or DEFAULT_RELATION_LEDGER_MYSQL_DSN
    conn = connect_db(resolved_dsn)
    try:
        initialize_database(conn)
        return append_event(
            conn,
            event=event,
            relation_key=relation_key,
            owner_profile_ref=owner_profile_ref,
            target_profile_ref=target_profile_ref,
            case_id=case_id,
            case_type=case_type,
        )
    finally:
        conn.close()


def try_get_relation_by_key(
    relation_key: str,
    *,
    dsn: str | None = None,
) -> dict[str, Any] | None:
    relation_key = str(relation_key or "").strip()
    if not relation_key:
        return None
    resolved_dsn = dsn or os.environ.get("HER_RELATION_LEDGER_DB")
    if not resolved_dsn:
        return None
    conn = connect_db(resolved_dsn)
    try:
        initialize_database(conn)
        return get_relation_by_key(conn, relation_key)
    finally:
        conn.close()


def flush_ledger_mirror(entries: list[LedgerMirrorEntry] | None) -> list[dict[str, Any]]:
    if not entries:
        return []
    results: list[dict[str, Any]] = []
    for entry in entries:
        results.append(
            append_event_to_default_ledger(
                event=entry["event"],
                relation_key=str(entry["relation_key"]),
                owner_profile_ref=entry.get("owner_profile_ref"),
                target_profile_ref=entry.get("target_profile_ref"),
                case_id=entry.get("case_id"),
                case_type=entry.get("case_type"),
            )
        )
    return results


__all__ = [
    "LedgerMirrorEntry",
    "append_event_to_default_ledger",
    "commit_conn_with_ledger",
    "defer_ledger_event",
    "flush_ledger_mirror",
    "ledger_allow_legacy_fallback",
    "ledger_mirror_for_conn",
    "ledger_read_mode",
    "ledger_reads_require_primary",
    "try_get_relation_by_key",
]
