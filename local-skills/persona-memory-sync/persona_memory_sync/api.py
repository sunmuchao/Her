"""Importable Python API for persona-memory-sync."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import persona_memory_engine as engine


UpsertPersonaMemoryRequest = engine.UpsertPersonaMemoryRequest
SyncPersonaProfileRequest = engine.SyncPersonaProfileRequest
RenderPublicProfileRequest = engine.RenderPublicProfileRequest
DEFAULT_PERSONA_TABLE = engine.DEFAULT_PERSONA_TABLE
DEFAULT_OBSERVATION_TABLE = engine.DEFAULT_OBSERVATION_TABLE


def _build_upsert_request(
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
        sync_profile=bool(request.get("sync_profile", False)),
    )


def _build_sync_request(
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


def _build_render_request(
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
        _build_upsert_request(request),
        include_normalized_patch=include_normalized_patch,
    )


def sync_persona_profile(
    request: SyncPersonaProfileRequest | Mapping[str, Any],
) -> dict[str, Any]:
    return engine.execute_sync_persona_profile(_build_sync_request(request))


def render_public_profile(
    request: RenderPublicProfileRequest | Mapping[str, Any],
) -> dict[str, Any]:
    return engine.execute_render_public_profile(_build_render_request(request))


__all__ = [
    "DEFAULT_OBSERVATION_TABLE",
    "DEFAULT_PERSONA_TABLE",
    "RenderPublicProfileRequest",
    "SyncPersonaProfileRequest",
    "UpsertPersonaMemoryRequest",
    "render_public_profile",
    "sync_persona_profile",
    "upsert_persona_memory",
]
