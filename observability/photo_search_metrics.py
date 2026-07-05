"""Photo search observability, bucket strategy, and lightweight reporting."""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any, Iterable, Mapping

from . import funnel_stage, metric_gauge


PHOTO_SEARCH_BUCKETS = ("control", "appearance_boost_v1", "trust_bias_v1")


def resolve_photo_search_experiment_bucket(user_key: str | None) -> str:
    normalized = str(user_key or "").strip()
    if not normalized:
        return PHOTO_SEARCH_BUCKETS[0]
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    index = int(digest[:4], 16) % len(PHOTO_SEARCH_BUCKETS)
    return PHOTO_SEARCH_BUCKETS[index]


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


__all__ = [
    "PHOTO_SEARCH_BUCKETS",
    "compare_photo_search_bucket_effect",
    "emit_photo_search_event",
    "resolve_photo_search_experiment_bucket",
    "summarize_photo_search_events",
]
