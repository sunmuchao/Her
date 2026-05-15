"""Persona-memory bridge kept separate from profile source access helpers."""

from __future__ import annotations

from typing import Any, Mapping


def apply_persona_patch(request: Any | Mapping[str, Any]) -> dict[str, Any]:
    from persona_memory_sync import upsert_persona_memory

    return upsert_persona_memory(request)


def render_public_profile(request: Any | Mapping[str, Any]) -> dict[str, Any]:
    from persona_memory_sync import api as persona_api
    from persona_memory_sync import persona_memory_engine as persona_engine

    return persona_engine.execute_render_public_profile(persona_api.coerce_render_request(request))


__all__ = [
    "apply_persona_patch",
    "render_public_profile",
]
