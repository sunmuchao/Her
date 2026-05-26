"""Recommendation DB commit with relationship-ledger mirroring."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from ._path_bootstrap import ensure_her_repo_on_sys_path  # noqa: E402

ensure_her_repo_on_sys_path(Path(__file__))

from match_domain import (  # noqa: E402
    CaseType,
    build_canonical_event,
    build_subscription_refresh_provenance,
    bundle_recommendation_action_entities,
    correlation_relation_action,
    get_trace_id,
    idempotency_client_relation_action,
    idempotency_relation_action,
    match_events_from_action_rows,
    merge_payload_with_event,
    profile_ref_to_dict,
    recommendation_relation_key,
    recommendation_relation_refs,
    reduce_relation_ledger,
    canonical_case_status_value,
)
from match_domain.gate_runner import evaluate_recommendation_gate, recommendation_row_gate_fields  # noqa: E402
from match_domain.search_visibility import run_partner_search as _run_partner_search  # noqa: E402
from match_domain.snapshot_hash import candidate_snapshot_hash  # noqa: E402
from partner_search import load_self_profile, search_profiles  # noqa: E402
from her_time_utils import bool_to_int, current_time, format_dt, parse_dt  # noqa: E402

from .direct_greet_gate import (
    DEFAULT_MAX_REVIEW_CANDIDATES_PER_REFRESH,
    DEFAULT_MIN_DIRECT_GREET_SCORE,
    DEFAULT_RECOMMENDATION_MODE,
    normalize_recommendation_mode,
    resolve_review_policy,
    review_candidate_for_proactive_delivery,
)
from match_domain.criteria_compiler import build_effective_search_request
from .storage import json_dumps, json_loads, row_to_dict
from relationship_ledger.runtime import (
    LedgerMirrorEntry,
    commit_conn_with_ledger,
    defer_ledger_event,
    try_get_relation_by_key,
)
from observability import (  # noqa: E402
    RECOMMENDATION_FUNNEL_ACTION,
    RECOMMENDATION_FUNNEL_DELIVERED,
    RECOMMENDATION_FUNNEL_PENDING_DELIVERY,
    RECOMMENDATION_FUNNEL_REFRESH,
    RECOMMENDATION_FUNNEL_REVIEW_PENDING,
    alert_signal,
    funnel_stage,
    metric_gauge,
)

SearchRunner = Callable[..., dict[str, Any]]
PersonaResolver = Callable[[dict[str, Any]], Optional[dict[str, Any]]]

def commit_recommendation_transaction(
    conn,
    ledger_mirror: list[LedgerMirrorEntry] | None = None,
) -> None:
    commit_conn_with_ledger(conn, extra_mirror=ledger_mirror)
