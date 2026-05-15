"""Importable Python API for persona-memory-sync."""

from __future__ import annotations

from typing import Any, Mapping

from . import persona_memory_engine as engine


UpsertPersonaMemoryRequest = engine.UpsertPersonaMemoryRequest
SyncPersonaProfileRequest = engine.SyncPersonaProfileRequest
RenderPublicProfileRequest = engine.RenderPublicProfileRequest
DEFAULT_PERSONA_TABLE = engine.DEFAULT_PERSONA_TABLE
DEFAULT_OBSERVATION_TABLE = engine.DEFAULT_OBSERVATION_TABLE
render_public_profile_via_service = engine.execute_render_public_profile


def coerce_upsert_request(
    request: UpsertPersonaMemoryRequest | Mapping[str, Any],
) -> UpsertPersonaMemoryRequest:
    if isinstance(request, UpsertPersonaMemoryRequest):
        return request
    return UpsertPersonaMemoryRequest(
        source=request.get("source"),
        user_key=request["user_key"],
        source_type=request["source_type"],
        patch=dict(request.get("patch") or {}),
        persona_table=request.get("persona_table", DEFAULT_PERSONA_TABLE),
        observation_table=request.get("observation_table", DEFAULT_OBSERVATION_TABLE),
        profile_table=request.get("profile_table"),
        confidence_score=request.get("confidence_score"),
        evidence_text=request.get("evidence_text"),
        conversation_ref=request.get("conversation_ref"),
        basis=request.get("basis"),
        apply_scope=request.get("apply_scope"),
        sync_profile=bool(request.get("sync_profile", False)),
    )


def coerce_sync_request(
    request: SyncPersonaProfileRequest | Mapping[str, Any],
) -> SyncPersonaProfileRequest:
    if isinstance(request, SyncPersonaProfileRequest):
        return request
    return SyncPersonaProfileRequest(
        source=request.get("source"),
        user_key=request.get("user_key"),
        profile_id=request.get("profile_id"),
        persona_table=request.get("persona_table", DEFAULT_PERSONA_TABLE),
        profile_table=request.get("profile_table"),
    )


def coerce_render_request(
    request: RenderPublicProfileRequest | Mapping[str, Any],
) -> RenderPublicProfileRequest:
    if isinstance(request, RenderPublicProfileRequest):
        return request
    return RenderPublicProfileRequest(
        source=request.get("source"),
        user_key=request.get("user_key"),
        profile_id=request.get("profile_id"),
        persona_table=request.get("persona_table", DEFAULT_PERSONA_TABLE),
        profile_table=request.get("profile_table"),
        write_profile=bool(request.get("write_profile", False)),
    )


def upsert_persona_memory(
    request: UpsertPersonaMemoryRequest | Mapping[str, Any],
    *,
    include_normalized_patch: bool = False,
) -> dict[str, Any]:
    return engine.execute_upsert_persona_memory(
        coerce_upsert_request(request),
        include_normalized_patch=include_normalized_patch,
    )


def sync_persona_profile(
    request: SyncPersonaProfileRequest | Mapping[str, Any],
) -> dict[str, Any]:
    return engine.execute_sync_persona_profile(coerce_sync_request(request))


def render_public_profile(
    request: RenderPublicProfileRequest | Mapping[str, Any],
) -> dict[str, Any]:
    return render_public_profile_via_service(coerce_render_request(request))


# Backward-compatible aliases for older internal callers.
_build_upsert_request = coerce_upsert_request
_build_sync_request = coerce_sync_request
_build_render_request = coerce_render_request


__all__ = [
    "coerce_render_request",
    "coerce_sync_request",
    "coerce_upsert_request",
    "DEFAULT_OBSERVATION_TABLE",
    "DEFAULT_PERSONA_TABLE",
    "RenderPublicProfileRequest",
    "SyncPersonaProfileRequest",
    "UpsertPersonaMemoryRequest",
    "render_public_profile",
    "sync_persona_profile",
    "upsert_persona_memory",
]
