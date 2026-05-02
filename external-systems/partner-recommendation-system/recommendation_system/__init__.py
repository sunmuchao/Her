"""External Phase 3 recommendation system built on top of partner-search."""

from .direct_greet_gate import (
    DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH,
    DEFAULT_MIN_DIRECT_GREET_SCORE,
    DEFAULT_RECOMMENDATION_MODE,
)
from .no_match_opt_in import (
    DEFAULT_NO_MATCH_OPT_IN_PROMPT,
    handle_opt_in_decision,
    run_search_session,
    subscribe_after_opt_in,
)
from .service import (
    build_in_app_card,
    create_subscription,
    deliver_in_app_recommendations,
    get_subscription,
    list_in_app_cards,
    list_recommendations_for_subscription,
    record_recommendation_action,
    record_user_review,
    refresh_due_subscriptions,
    refresh_subscription,
)
from .storage import connect_db, initialize_database

__all__ = [
    "DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH",
    "DEFAULT_MIN_DIRECT_GREET_SCORE",
    "DEFAULT_RECOMMENDATION_MODE",
    "DEFAULT_NO_MATCH_OPT_IN_PROMPT",
    "build_in_app_card",
    "connect_db",
    "create_subscription",
    "deliver_in_app_recommendations",
    "get_subscription",
    "handle_opt_in_decision",
    "initialize_database",
    "list_in_app_cards",
    "list_recommendations_for_subscription",
    "record_recommendation_action",
    "record_user_review",
    "refresh_due_subscriptions",
    "refresh_subscription",
    "run_search_session",
    "subscribe_after_opt_in",
]
