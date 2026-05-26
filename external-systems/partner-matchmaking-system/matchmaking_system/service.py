"""Phase 5 matchmaking workflows built on top of partner-search and persona-memory-sync."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from ._path_bootstrap import ensure_her_repo_on_sys_path

ensure_her_repo_on_sys_path(Path(__file__))

from profile_service import apply_persona_patch  # noqa: E402
from her_time_utils import current_time, format_dt, parse_dt  # noqa: E402

from .matchmaking_search import run_partner_search
from .matchmaking_cases import (
    close_stale_cases,
    dispatch_case_contact,
    get_match_case,
    open_match_cases,
    record_case_reply,
    record_feedback,
    revalidate_member_matches,
)
from .matchmaking_inflate import (
    ACTIVE_MEMBER_STATUS,
    FINAL_CASE_STATUSES,
    OPEN_CASE_STATUSES,
    inflate_case,
    inflate_edge,
    inflate_feedback,
    inflate_pair,
    inflate_pool_member,
    member_is_available,
)
from .pairs import (
    build_mutual_pairs,
    get_edge,
    get_pair,
    list_active_edges,
    list_match_case_events,
    list_match_cases,
    list_pairs,
)
from .pool_members import (
    create_pool_member,
    find_pool_member_by_source_profile,
    get_pool_member,
    get_pool_member_by_user_key,
    list_active_pool_members,
    list_due_pool_members,
    list_pool_members,
    refresh_active_pool,
    refresh_pool_member,
    set_pool_member_status,
)

SearchRunner = Callable[..., dict[str, Any]]
PersonaSyncRunner = Callable[[Mapping[str, Any]], dict[str, Any]]

sync_persona_memory = apply_persona_patch

__all__ = [
    "ACTIVE_MEMBER_STATUS",
    "FINAL_CASE_STATUSES",
    "OPEN_CASE_STATUSES",
    "PersonaSyncRunner",
    "SearchRunner",
    "build_mutual_pairs",
    "close_stale_cases",
    "create_pool_member",
    "current_time",
    "dispatch_case_contact",
    "format_dt",
    "get_edge",
    "get_match_case",
    "get_pair",
    "get_pool_member",
    "get_pool_member_by_user_key",
    "list_active_edges",
    "list_active_pool_members",
    "list_due_pool_members",
    "list_match_case_events",
    "list_match_cases",
    "list_pairs",
    "list_pool_members",
    "open_match_cases",
    "parse_dt",
    "record_case_reply",
    "record_feedback",
    "refresh_active_pool",
    "refresh_pool_member",
    "revalidate_member_matches",
    "run_partner_search",
    "set_pool_member_status",
    "sync_persona_memory",
]
