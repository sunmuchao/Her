#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from persona_memory_lib import (
    DEFAULT_OBSERVATION_TABLE,
    DEFAULT_PERSONA_TABLE,
    apply_persona_patch as apply_persona_patch_impl,
    normalize_patch,
    parse_mysql_source,
    parse_patch_json,
    render_public_profile_result as render_public_profile_result_impl,
    sync_persona_profile as sync_persona_profile_impl,
)


@dataclass(frozen=True)
class UpsertPersonaMemoryRequest:
    source: Optional[str]
    user_key: str
    source_type: str
    patch: Dict[str, Any]
    persona_table: str = DEFAULT_PERSONA_TABLE
    observation_table: str = DEFAULT_OBSERVATION_TABLE
    profile_table: Optional[str] = None
    confidence_score: Optional[int] = None
    evidence_text: Optional[str] = None
    conversation_ref: Optional[str] = None
    sync_profile: bool = False


@dataclass(frozen=True)
class SyncPersonaProfileRequest:
    source: Optional[str]
    user_key: Optional[str] = None
    profile_id: Optional[int] = None
    persona_table: str = DEFAULT_PERSONA_TABLE
    profile_table: Optional[str] = None


@dataclass(frozen=True)
class RenderPublicProfileRequest:
    source: Optional[str]
    user_key: Optional[str] = None
    profile_id: Optional[int] = None
    persona_table: str = DEFAULT_PERSONA_TABLE
    profile_table: Optional[str] = None
    write_profile: bool = False


def resolve_profile_table(source: Optional[str], profile_table: Optional[str]) -> str:
    if profile_table:
        return profile_table
    return parse_mysql_source(source)["table"]


def execute_upsert_persona_memory(
    request: UpsertPersonaMemoryRequest,
    *,
    include_normalized_patch: bool = False,
) -> Dict[str, Any]:
    normalized_patch = normalize_patch(dict(request.patch))
    result = apply_persona_patch_impl(
        source=request.source,
        user_key=request.user_key,
        source_type=request.source_type,
        normalized_patch=normalized_patch,
        persona_table=request.persona_table,
        observation_table=request.observation_table,
        profile_table=resolve_profile_table(request.source, request.profile_table),
        confidence_score=request.confidence_score,
        evidence_text=request.evidence_text,
        conversation_ref=request.conversation_ref,
        sync_profile=request.sync_profile,
    )
    if not include_normalized_patch:
        return result
    return {
        **result,
        "normalized_patch": normalized_patch,
    }


def execute_sync_persona_profile(request: SyncPersonaProfileRequest) -> Dict[str, Any]:
    return sync_persona_profile_impl(
        source=request.source,
        persona_table=request.persona_table,
        profile_table=resolve_profile_table(request.source, request.profile_table),
        user_key=request.user_key,
        profile_id=request.profile_id,
    )


def execute_render_public_profile(request: RenderPublicProfileRequest) -> Dict[str, Any]:
    return render_public_profile_result_impl(
        source=request.source,
        persona_table=request.persona_table,
        profile_table=resolve_profile_table(request.source, request.profile_table),
        user_key=request.user_key,
        profile_id=request.profile_id,
        write_profile=request.write_profile,
    )


__all__ = [
    "DEFAULT_OBSERVATION_TABLE",
    "DEFAULT_PERSONA_TABLE",
    "RenderPublicProfileRequest",
    "SyncPersonaProfileRequest",
    "UpsertPersonaMemoryRequest",
    "execute_render_public_profile",
    "execute_sync_persona_profile",
    "execute_upsert_persona_memory",
    "parse_patch_json",
    "resolve_profile_table",
]
