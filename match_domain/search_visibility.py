"""Search execution with external moderation gate (§13.1.3 phase 3)."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from partner_moderation import overlay_records_with_moderation
from profile_source_refs import build_source_file_ref


def _apply_overlay_to_result_list(
    items: list[dict[str, Any]] | None,
    *,
    moderation_dsn: str | None,
    include_blocked: bool,
) -> list[dict[str, Any]] | None:
    if not items:
        return items
    if not moderation_dsn:
        return list(items)
    return overlay_records_with_moderation(
        list(items),
        moderation_dsn=moderation_dsn,
        include_blocked=include_blocked,
    )


def apply_search_visibility_gate(
    response: Mapping[str, Any],
    *,
    moderation_dsn: str | None,
    include_blocked: bool = False,
) -> dict[str, Any]:
    """Apply moderation overlay post-search instead of inside partner_search."""
    payload = deepcopy(dict(response))
    for key in ("results", "fallback_results"):
        payload[key] = _apply_overlay_to_result_list(
            list(payload.get(key) or []),
            moderation_dsn=moderation_dsn,
            include_blocked=include_blocked,
        )
    if "results" in payload:
        payload["result_count"] = len(payload.get("results") or [])
        payload["has_match"] = payload["result_count"] > 0
    payload["search_gate"] = {
        "moderation_applied_externally": bool(moderation_dsn),
        "include_blocked": include_blocked,
    }
    return payload


def _attach_source_file_to_results(
    response: Mapping[str, Any],
    *,
    source: str | None,
    table_name: str | None,
) -> None:
    if not source:
        return
    source_file = build_source_file_ref(source, table_name)
    if not source_file:
        return
    for key in ("results", "fallback_results"):
        items = response.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and not item.get("source_file"):
                item["source_file"] = source_file


def search_profiles_with_visibility_gate(search_profiles_fn, **kwargs: Any) -> dict[str, Any]:
    """Run partner_search without moderation_dsn; overlay in match_domain."""
    moderation_dsn = kwargs.pop("moderation_dsn", None)
    include_blocked = bool(kwargs.pop("include_moderation_blocked", False))
    source = kwargs.get("source")
    table_name = kwargs.get("table_name")
    kwargs["moderation_dsn"] = None
    kwargs["include_moderation_blocked"] = False
    raw = search_profiles_fn(**kwargs)
    if moderation_dsn:
        _attach_source_file_to_results(raw, source=source, table_name=table_name)
    return apply_search_visibility_gate(
        raw,
        moderation_dsn=moderation_dsn,
        include_blocked=include_blocked,
    )


def run_partner_search(search_profiles_fn, **kwargs: Any) -> dict[str, Any]:
    """Run partner_search with match_domain visibility/moderation overlay."""

    return search_profiles_with_visibility_gate(search_profiles_fn, **kwargs)


__all__ = [
    "apply_search_visibility_gate",
    "run_partner_search",
    "search_profiles_with_visibility_gate",
]
