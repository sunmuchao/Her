"""Shared profile detail read model.

This module owns the product-facing capability of loading one profile by id
and returning a canonical detail payload. It reuses the existing profile
normalization and photo/verification helpers from ``partner_search`` without
making profile detail a public responsibility of that package.
"""

from __future__ import annotations

from typing import Any, Sequence

from partner_search import search_candidates as engine


def load_profile_detail(
    *,
    source: str | Sequence[str] | None,
    profile_id: int,
    table_name: str | None = None,
    photos_table_name: str | None = None,
    photo_preview_count: int = 6,
    include_source: bool = False,
    moderation_dsn: str | None = None,
    include_moderation_blocked: bool = False,
) -> dict[str, Any] | None:
    normalized_profile_id = engine.as_int(profile_id)
    if normalized_profile_id is None or normalized_profile_id <= 0:
        return None

    request = engine.build_search_request(
        source=source,
        table_name=table_name,
        photos_table_name=photos_table_name,
        criteria={},
        self_id=normalized_profile_id,
        photo_preview_count=photo_preview_count,
        moderation_dsn=moderation_dsn,
        include_moderation_blocked=include_moderation_blocked,
    )
    sources = engine.resolve_request_sources(request)
    raw_records: list[dict[str, Any]] = []
    for source_item in sources:
        raw_records.extend(
            engine.load_source(
                source_item,
                table_name=request.get("table_name"),
                criteria=request.get("criteria"),
                include_ids=[normalized_profile_id],
                include_ids_mode="only",
            )
        )

    records = engine.overlay_records_with_moderation(
        raw_records,
        moderation_dsn=request.get("moderation_dsn"),
        include_blocked=bool(request.get("include_moderation_blocked")),
    )
    try:
        record = engine.resolve_self_profile_record(normalized_profile_id, records)
    except ValueError:
        return None

    profile = engine.strip_internal_fields(record)
    result = {
        "id": normalized_profile_id,
        "name": profile.get("name") or record.get("name") or "未命名",
        "profile": profile,
        "source_file": record.get("source_file") or "",
    }
    engine.attach_photo_previews(
        [result],
        engine.as_int(photo_preview_count) or 0,
        photos_table_name=request.get("photos_table_name"),
    )
    payload = engine.build_structured_result_payload(
        result,
        include_source=include_source,
    )
    payload["notes_summary"] = engine.summarize_notes(
        profile.get("notes"),
        max_segments=4,
        max_length=240,
    )
    return _json_safe_value(payload)


def _json_safe_value(value: Any) -> Any:
    return engine.json_safe(value)


__all__ = ["load_profile_detail"]
