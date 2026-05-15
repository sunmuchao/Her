"""Shared profile detail read model.

This module owns the product-facing capability of loading one profile by id
and returning a canonical detail payload. It reuses the existing profile
normalization and photo/verification helpers from ``partner_search`` without
making profile detail a public responsibility of that package.
"""

from __future__ import annotations

from typing import Any, Sequence

from partner_search import api as search_api
from partner_search import search_candidates as engine
from profile_service import list_profile_photo_sources, resolve_profile_source


def _detail_result_from_record(record: dict[str, Any], *, profile_id: int) -> tuple[dict[str, Any], dict[str, Any]]:
    profile = engine.strip_internal_fields(record)
    result = {
        "id": profile_id,
        "name": profile.get("name") or record.get("name") or "未命名",
        "profile": profile,
        "source_file": record.get("source_file") or "",
    }
    return result, profile


def _detail_payload_from_result(
    result: dict[str, Any],
    *,
    profile: dict[str, Any],
    include_source: bool,
) -> dict[str, Any]:
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
    if not isinstance(source, str):
        return _load_profile_detail_with_engine(
            source=source,
            profile_id=normalized_profile_id,
            table_name=table_name,
            photos_table_name=photos_table_name,
            photo_preview_count=photo_preview_count,
            include_source=include_source,
            moderation_dsn=moderation_dsn,
            include_moderation_blocked=include_moderation_blocked,
        )
    normalized_source, normalized_table = resolve_profile_source(source, table_name)
    if not normalized_source or not normalized_table:
        return _load_profile_detail_with_engine(
            source=source,
            profile_id=normalized_profile_id,
            table_name=table_name,
            photos_table_name=photos_table_name,
            photo_preview_count=photo_preview_count,
            include_source=include_source,
            moderation_dsn=moderation_dsn,
            include_moderation_blocked=include_moderation_blocked,
        )
    try:
        raw_record = search_api.load_source_profile_record(
            source=normalized_source,
            profile_id=normalized_profile_id,
            table_name=normalized_table,
        )
    except ValueError:
        return None
    if raw_record is None:
        return None
    records = engine.overlay_records_with_moderation(
        [raw_record],
        moderation_dsn=moderation_dsn,
        include_blocked=bool(include_moderation_blocked),
    )
    try:
        record = engine.resolve_self_profile_record(normalized_profile_id, records)
    except ValueError:
        return None
    result, profile = _detail_result_from_record(record, profile_id=normalized_profile_id)
    result["photo_preview"] = list_profile_photo_sources(
        source_dsn=normalized_source,
        source_table_name=normalized_table,
        profile_id=normalized_profile_id,
        photos_table_name=photos_table_name,
        limit=engine.as_int(photo_preview_count) or 0,
    )
    return _detail_payload_from_result(
        result,
        profile=profile,
        include_source=include_source,
    )


def _load_profile_detail_with_engine(
    *,
    source: str | Sequence[str] | None,
    profile_id: int,
    table_name: str | None,
    photos_table_name: str | None,
    photo_preview_count: int,
    include_source: bool,
    moderation_dsn: str | None,
    include_moderation_blocked: bool,
) -> dict[str, Any] | None:
    normalized_profile_id = engine.as_int(profile_id)
    assert normalized_profile_id is not None
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

    result, profile = _detail_result_from_record(record, profile_id=normalized_profile_id)
    engine.attach_photo_previews(
        [result],
        engine.as_int(photo_preview_count) or 0,
        photos_table_name=request.get("photos_table_name"),
    )
    return _detail_payload_from_result(
        result,
        profile=profile,
        include_source=include_source,
    )


def _json_safe_value(value: Any) -> Any:
    return engine.json_safe(value)


__all__ = ["load_profile_detail"]
