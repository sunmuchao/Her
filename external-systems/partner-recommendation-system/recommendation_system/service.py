"""Phase 3 outer-system recommendation workflows built on top of partner-search."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from ._path_bootstrap import ensure_her_repo_on_sys_path  # noqa: E402

ensure_her_repo_on_sys_path(Path(__file__))

from her_time_utils import bool_to_int, current_time, format_dt, parse_dt  # noqa: E402
from partner_search import load_self_profile, search_profiles  # noqa: E402

from .recommendation_search import run_partner_search

from .conversion_views import (
    build_recommendation_conversion_view,
    list_recommendation_conversion_views_for_subscription,
)
from .in_app_delivery import (
    build_in_app_card,
    count_cards_delivered_today,
    day_bounds,
    deliver_in_app_recommendations,
    list_in_app_cards,
    mark_in_app_cards_read,
    recommendation_photo_verification_label,
    recommendation_trust_headline,
    recommendation_verified_label,
    within_quiet_hours,
)
from .recommendation_rows import (
    append_relation_state_revision_event,
    get_recommendation,
    get_recommendation_by_id,
    inflate_recommendation,
    insert_recommendation_action,
    list_recommendation_actions_for_recommendation,
    list_recommendations_for_subscription,
    record_recommendation_action,
    record_user_review,
    upsert_recommendation,
)
from .recommendation_transactions import commit_recommendation_transaction
from .subscriptions import (
    build_initial_request,
    create_subscription,
    generate_card_id,
    generate_subscription_id,
    get_subscription,
    is_subscription_due,
    list_due_subscriptions,
    list_search_runs_for_subscription,
    load_requester_profile,
    load_requester_profile_row,
    load_subscription_search_args,
    normalize_subscription_overrides,
    record_search_run,
    refresh_due_subscriptions,
    refresh_subscription,
    resolve_subscription_compile_inputs,
    resolve_subscription_persona_profile,
    update_subscription_overrides,
)
from relationship_ledger.runtime import LedgerMirrorEntry

SearchRunner = Callable[..., dict[str, Any]]
PersonaResolver = Callable[[dict[str, Any]], Optional[dict[str, Any]]]


__all__ = [
    "LedgerMirrorEntry",
    "PersonaResolver",
    "SearchRunner",
    "append_relation_state_revision_event",
    "bool_to_int",
    "build_in_app_card",
    "build_initial_request",
    "build_recommendation_conversion_view",
    "commit_recommendation_transaction",
    "count_cards_delivered_today",
    "create_subscription",
    "current_time",
    "day_bounds",
    "deliver_in_app_recommendations",
    "format_dt",
    "generate_card_id",
    "generate_subscription_id",
    "get_recommendation",
    "get_recommendation_by_id",
    "get_subscription",
    "inflate_recommendation",
    "insert_recommendation_action",
    "is_subscription_due",
    "list_due_subscriptions",
    "list_in_app_cards",
    "list_recommendation_conversion_views_for_subscription",
    "list_recommendation_actions_for_recommendation",
    "list_recommendations_for_subscription",
    "list_search_runs_for_subscription",
    "load_requester_profile",
    "load_requester_profile_row",
    "load_self_profile",
    "load_subscription_search_args",
    "search_profiles",
    "mark_in_app_cards_read",
    "normalize_subscription_overrides",
    "parse_dt",
    "record_recommendation_action",
    "record_search_run",
    "record_user_review",
    "recommendation_photo_verification_label",
    "recommendation_trust_headline",
    "recommendation_verified_label",
    "refresh_due_subscriptions",
    "refresh_subscription",
    "resolve_subscription_compile_inputs",
    "resolve_subscription_persona_profile",
    "run_partner_search",
    "update_subscription_overrides",
    "upsert_recommendation",
    "within_quiet_hours",
]
