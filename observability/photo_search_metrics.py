"""Photo search observability, bucket strategy, and lightweight reporting."""

from __future__ import annotations

import hashlib
import os
from collections import Counter
from typing import Any, Iterable, Mapping

from . import funnel_stage, metric_gauge


PHOTO_SEARCH_BUCKETS = ("control", "appearance_boost_v1", "trust_bias_v1")

PHOTO_SEARCH_CLIENT_DROP_STAGES = frozenset(
    {
        "client_prepare_failed",
        "client_submit_failed",
        "request_not_entered_gateway",
    }
)
PHOTO_SEARCH_GATEWAY_REJECT_STAGES = frozenset(
    {
        "gateway_rejected",
    }
)
PHOTO_SEARCH_SEARCH_FAILURE_STAGES = frozenset(
    {
        "search_failed",
        "search_runtime_failed",
        "photo_search_unavailable",
    }
)
PHOTO_SEARCH_EMPTY_RESULT_STAGES = frozenset(
    {
        "empty_result",
    }
)
PHOTO_SEARCH_SUCCESS_STAGES = frozenset(
    {
        "results_ready",
        "result_returned",
        "search_completed",
    }
)


def _normalize_entrypoint(item: Mapping[str, Any]) -> str:
    return str(
        item.get("entrypoint")
        or item.get("route_role")
        or item.get("route_kind")
        or "unknown"
    ).strip().lower() or "unknown"


def _normalize_flow_kind(item: Mapping[str, Any]) -> str:
    return str(item.get("flow_kind") or "unknown").strip().lower() or "unknown"


def _event_bool(item: Mapping[str, Any], key: str) -> bool:
    return bool(item.get(key))


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def normalize_photo_search_rollout(
    rollout: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    raw = dict(rollout or {})
    if not raw:
        return {bucket: 1 / len(PHOTO_SEARCH_BUCKETS) for bucket in PHOTO_SEARCH_BUCKETS}
    normalized: dict[str, float] = {}
    total = 0.0
    for bucket in PHOTO_SEARCH_BUCKETS:
        weight = max(0.0, float(raw.get(bucket) or 0.0))
        normalized[bucket] = weight
        total += weight
    if total <= 0:
        return {bucket: 1 / len(PHOTO_SEARCH_BUCKETS) for bucket in PHOTO_SEARCH_BUCKETS}
    return {bucket: round(weight / total, 6) for bucket, weight in normalized.items()}


def photo_search_rollout_from_env() -> dict[str, float]:
    raw = str(os.environ.get("HER_PHOTO_SEARCH_ROLLOUT") or "").strip()
    if not raw:
        return normalize_photo_search_rollout()
    parsed: dict[str, float] = {}
    for segment in raw.split(","):
        key, _, value = segment.partition(":")
        bucket = key.strip()
        if bucket not in PHOTO_SEARCH_BUCKETS:
            continue
        try:
            parsed[bucket] = float(value.strip() or 0.0)
        except ValueError:
            continue
    return normalize_photo_search_rollout(parsed)


def resolve_photo_search_experiment_bucket(
    user_key: str | None,
    *,
    rollout: Mapping[str, Any] | None = None,
    forced_bucket: str | None = None,
) -> str:
    forced = str(forced_bucket or os.environ.get("HER_PHOTO_SEARCH_FORCE_BUCKET") or "").strip()
    if forced in PHOTO_SEARCH_BUCKETS:
        return forced
    normalized = str(user_key or "").strip()
    if not normalized:
        return PHOTO_SEARCH_BUCKETS[0]
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    bucket_weights = normalize_photo_search_rollout(rollout or photo_search_rollout_from_env())
    point = (int(digest[:8], 16) % 10000) / 10000
    cumulative = 0.0
    for bucket in PHOTO_SEARCH_BUCKETS:
        cumulative += float(bucket_weights.get(bucket) or 0.0)
        if point <= cumulative:
            return bucket
    return PHOTO_SEARCH_BUCKETS[-1]


def emit_photo_search_event(
    *,
    user_key: str,
    search_type: str,
    stage: str,
    result_count: int | None = None,
    latency_ms: int | None = None,
    experiment_bucket: str | None = None,
    success: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    bucket = experiment_bucket or resolve_photo_search_experiment_bucket(user_key)
    funnel_stage(
        system="photo_search",
        stage=stage,
        search_type=search_type,
        user_key=user_key,
        result_count=result_count,
        latency_ms=latency_ms,
        experiment_bucket=bucket,
        success=success,
        **extra,
    )
    metric_gauge(
        "photo_search.result_count",
        int(result_count or 0),
        search_type=search_type,
        experiment_bucket=bucket,
        success=success,
    )
    if latency_ms is not None:
        metric_gauge(
            "photo_search.latency_ms",
            int(latency_ms),
            search_type=search_type,
            experiment_bucket=bucket,
            success=success,
        )
    return {
        "emitted": True,
        "search_type": search_type,
        "stage": stage,
        "experiment_bucket": bucket,
    }


def summarize_photo_search_events(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item) for item in list(events or []) if isinstance(item, Mapping)]
    total = len(rows)
    by_type = Counter(str(item.get("search_type") or "unknown") for item in rows)
    by_bucket = Counter(str(item.get("experiment_bucket") or "control") for item in rows)
    success_count = sum(1 for item in rows if bool(item.get("success", True)))
    latencies = [int(item.get("latency_ms") or 0) for item in rows if int(item.get("latency_ms") or 0) > 0]
    results = [int(item.get("result_count") or 0) for item in rows]
    return {
        "total_events": total,
        "success_rate": round((success_count / total), 4) if total else 0.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
        "avg_result_count": round(sum(results) / len(results), 2) if results else 0.0,
        "by_search_type": dict(by_type),
        "by_experiment_bucket": dict(by_bucket),
    }


def _normalized_stage(item: Mapping[str, Any]) -> str:
    return str(item.get("stage") or item.get("funnel_stage") or "unknown").strip().lower()


def _event_result_count(item: Mapping[str, Any]) -> int:
    try:
        return int(item.get("result_count") or 0)
    except (TypeError, ValueError):
        return 0


def classify_photo_search_event(item: Mapping[str, Any]) -> str:
    stage = _normalized_stage(item)
    success = bool(item.get("success", True))
    result_count = _event_result_count(item)

    if stage in PHOTO_SEARCH_CLIENT_DROP_STAGES:
        return "request_not_entered_gateway"
    if stage in PHOTO_SEARCH_GATEWAY_REJECT_STAGES:
        return "gateway_rejected"
    if stage in PHOTO_SEARCH_SEARCH_FAILURE_STAGES:
        return "search_failed"
    if stage in PHOTO_SEARCH_EMPTY_RESULT_STAGES:
        return "search_empty"
    if not success and stage.startswith("gateway_"):
        return "gateway_rejected"
    if not success:
        return "search_failed"
    if result_count <= 0 and stage in {"search_completed", "results_ready", "result_returned"}:
        return "search_empty"
    return "search_succeeded"


def build_photo_search_funnel(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item) for item in list(events or []) if isinstance(item, Mapping)]
    categories = Counter(classify_photo_search_event(item) for item in rows)
    total = len(rows)
    labeled_total = sum(categories.values())

    def _rate(value: int) -> float:
        return round(value / labeled_total, 4) if labeled_total else 0.0

    return {
        "total_events": total,
        "request_not_entered_gateway": categories.get("request_not_entered_gateway", 0),
        "gateway_rejected": categories.get("gateway_rejected", 0),
        "search_failed": categories.get("search_failed", 0),
        "search_empty": categories.get("search_empty", 0),
        "search_succeeded": categories.get("search_succeeded", 0),
        "rates": {
            "request_not_entered_gateway": _rate(categories.get("request_not_entered_gateway", 0)),
            "gateway_rejected": _rate(categories.get("gateway_rejected", 0)),
            "search_failed": _rate(categories.get("search_failed", 0)),
            "search_empty": _rate(categories.get("search_empty", 0)),
            "search_succeeded": _rate(categories.get("search_succeeded", 0)),
        },
    }


def compare_photo_search_bucket_effect(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in list(events or []):
        payload = dict(item)
        bucket = str(payload.get("experiment_bucket") or "control")
        grouped.setdefault(bucket, []).append(payload)
    comparisons: list[dict[str, Any]] = []
    for bucket, rows in grouped.items():
        summary = summarize_photo_search_events(rows)
        comparisons.append(
            {
                "experiment_bucket": bucket,
                "event_count": summary["total_events"],
                "success_rate": summary["success_rate"],
                "avg_latency_ms": summary["avg_latency_ms"],
                "avg_result_count": summary["avg_result_count"],
            }
        )
    comparisons.sort(key=lambda item: item["experiment_bucket"])
    return comparisons


def build_photo_search_route_comparison(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in list(events or []):
        payload = dict(item)
        key = _normalize_entrypoint(payload)
        grouped.setdefault(key, []).append(payload)

    comparison: list[dict[str, Any]] = []
    for entrypoint, rows in sorted(grouped.items()):
        success_events = [
            row for row in rows if _normalized_stage(row) in PHOTO_SEARCH_SUCCESS_STAGES
        ]
        success_count = sum(
            1
            for row in success_events
            if bool(row.get("success", True)) and _event_result_count(row) > 0
        )
        empty_count = sum(
            1
            for row in rows
            if classify_photo_search_event(row) == "search_empty"
        )
        comparison.append(
            {
                "entrypoint": entrypoint,
                "event_count": len(rows),
                "success_count": success_count,
                "empty_count": empty_count,
                "success_rate": _rate(success_count, len(success_events)),
                "empty_rate": _rate(empty_count, len(rows)),
            }
        )
    return comparison


def build_photo_search_shadow_compare(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [
        dict(item)
        for item in list(events or [])
        if isinstance(item, Mapping) and _normalized_stage(item).startswith("shadow_compare")
    ]
    compare_rows = [row for row in rows if _normalized_stage(row) == "shadow_compare"]
    failed_rows = [row for row in rows if _normalized_stage(row) == "shadow_compare_failed"]
    diff_rows = [row for row in compare_rows if bool(row.get("shadow_diff_detected"))]
    overlap_counts = [int(row.get("shadow_overlap_count") or 0) for row in compare_rows]
    return {
        "enabled_event_count": len(compare_rows),
        "failed_event_count": len(failed_rows),
        "diff_event_count": len(diff_rows),
        "diff_rate": _rate(len(diff_rows), len(compare_rows)),
        "avg_overlap_count": round(sum(overlap_counts) / len(overlap_counts), 2) if overlap_counts else 0.0,
        "primary_modes": dict(Counter(str(row.get("primary_mode") or "unknown") for row in compare_rows)),
        "baseline_modes": dict(Counter(str(row.get("baseline_mode") or "unknown") for row in compare_rows)),
    }


def build_photo_search_migration_progress(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item) for item in list(events or []) if isinstance(item, Mapping)]
    legacy_rows = [row for row in rows if _normalize_entrypoint(row) == "legacy_photo_search_route"]
    unified_rows = [row for row in rows if _normalize_entrypoint(row) == "unified_discovery_turn"]
    legacy_forward_success = [
        row
        for row in legacy_rows
        if _normalized_stage(row) in PHOTO_SEARCH_SUCCESS_STAGES and bool(row.get("success", True))
    ]
    return {
        "legacy_route_call_count": len(legacy_rows),
        "unified_turn_call_count": len(unified_rows),
        "legacy_route_success_rate": _rate(len(legacy_forward_success), len(legacy_rows)),
        "legacy_route_retired": len(legacy_rows) == 0,
        "shadow_compare": build_photo_search_shadow_compare(rows),
    }


def build_photo_search_key_metrics(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item) for item in list(events or []) if isinstance(item, Mapping)]
    success_events = [row for row in rows if _normalized_stage(row) in PHOTO_SEARCH_SUCCESS_STAGES]
    image_turn_events = [row for row in rows if _event_bool(row, "has_image")]
    image_turn_success = [
        row for row in success_events if _event_bool(row, "has_image") and _event_result_count(row) > 0
    ]
    reused_reference_events = [row for row in rows if _event_bool(row, "reused_reference_image")]
    reused_reference_success = [
        row for row in success_events if _event_bool(row, "reused_reference_image") and _event_result_count(row) > 0
    ]
    refinement_events = [row for row in rows if _event_bool(row, "is_refinement")]
    refinement_success = [
        row for row in success_events if _event_bool(row, "is_refinement") and _event_result_count(row) > 0
    ]
    first_turn_events = [row for row in rows if _event_bool(row, "is_first_visual_turn")]
    first_turn_success = [
        row for row in success_events if _event_bool(row, "is_first_visual_turn") and _event_result_count(row) > 0
    ]
    no_result_events = [row for row in rows if classify_photo_search_event(row) == "search_empty"]
    no_result_followups = [row for row in rows if _event_bool(row, "follows_empty_result")]

    return {
        "image_turn_success_rate": {
            "numerator": len(image_turn_success),
            "denominator": len(image_turn_events),
            "rate": _rate(len(image_turn_success), len(image_turn_events)),
        },
        "reuse_reference_success_rate": {
            "numerator": len(reused_reference_success),
            "denominator": len(reused_reference_events),
            "rate": _rate(len(reused_reference_success), len(reused_reference_events)),
        },
        "refinement_success_rate": {
            "numerator": len(refinement_success),
            "denominator": len(refinement_events),
            "rate": _rate(len(refinement_success), len(refinement_events)),
        },
        "first_turn_result_rate": {
            "numerator": len(first_turn_success),
            "denominator": len(first_turn_events),
            "rate": _rate(len(first_turn_success), len(first_turn_events)),
        },
        "empty_result_followup_rate": {
            "numerator": len(no_result_followups),
            "denominator": len(no_result_events),
            "rate": _rate(len(no_result_followups), len(no_result_events)),
        },
    }


def build_photo_search_switchpoints() -> dict[str, Any]:
    return {
        "current_primary_entrypoint": "/v1/discovery/turns",
        "legacy_compat_entrypoint": "/v1/discovery/photo-search",
        "legacy_route_retired": True,
        "future_rollout_toggle": {
            "gateway_route_layer": "rest_discovery_multimodal_turn",
            "legacy_route_layer": "410_gone",
            "agent_decision_layer": "DiscoveryService.process_multimodal_turn -> _run_photo_search_turn",
        },
        "gray_release_enabled": False,
    }


def build_photo_search_dashboard(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(item) for item in list(events or []) if isinstance(item, Mapping)]
    summary = summarize_photo_search_events(rows)
    funnel = build_photo_search_funnel(rows)
    by_stage = Counter(str(item.get("stage") or "unknown") for item in rows)
    by_type_stage = Counter(
        (
            str(item.get("search_type") or "unknown"),
            str(item.get("stage") or "unknown"),
        )
        for item in rows
    )
    return {
        "summary": summary,
        "funnel": funnel,
        "key_metrics": build_photo_search_key_metrics(rows),
        "route_comparison": build_photo_search_route_comparison(rows),
        "migration_progress": build_photo_search_migration_progress(rows),
        "shadow_compare": build_photo_search_shadow_compare(rows),
        "switchpoints": build_photo_search_switchpoints(),
        "bucket_comparison": compare_photo_search_bucket_effect(rows),
        "by_stage": dict(by_stage),
        "by_search_type_stage": [
            {
                "search_type": search_type,
                "stage": stage,
                "count": count,
            }
            for (search_type, stage), count in sorted(by_type_stage.items())
        ],
    }


__all__ = [
    "PHOTO_SEARCH_BUCKETS",
    "build_photo_search_dashboard",
    "build_photo_search_funnel",
    "build_photo_search_key_metrics",
    "build_photo_search_migration_progress",
    "build_photo_search_route_comparison",
    "build_photo_search_shadow_compare",
    "build_photo_search_switchpoints",
    "classify_photo_search_event",
    "compare_photo_search_bucket_effect",
    "emit_photo_search_event",
    "normalize_photo_search_rollout",
    "photo_search_rollout_from_env",
    "resolve_photo_search_experiment_bucket",
    "summarize_photo_search_events",
]
