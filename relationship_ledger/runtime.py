"""Runtime helpers for cross-system ledger mirroring."""

from __future__ import annotations

from collections.abc import Mapping
import os
from typing import Any

from match_domain import MatchEvent, ProfileRef

from .service import append_event
from .storage import DEFAULT_RELATION_LEDGER_MYSQL_DSN, connect_db, initialize_database


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


__all__ = ["append_event_to_default_ledger"]
