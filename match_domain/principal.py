"""Unified identity vocabulary for §13.3 Principal convergence."""

from __future__ import annotations

from typing import Any

# Canonical field names exposed on Gateway Principal payloads.
FIELD_USER_ID = "user_id"
FIELD_PROFILE_ID = "profile_id"
FIELD_REQUESTER_ID = "requester_id"
FIELD_USER_KEY = "user_key"
FIELD_MEMBER_ID = "member_id"
FIELD_CASE_ID = "case_id"

# End-user profile binding accepts either alias at the Gateway boundary.
PROFILE_ID_FIELD_ALIASES = frozenset({FIELD_PROFILE_ID, FIELD_REQUESTER_ID})


def user_key_from_profile_id(profile_id: int | str | None) -> str | None:
    if profile_id is None:
        return None
    text = str(profile_id).strip()
    return text or None


def profile_ref_from_profile_id(profile_id: int | str | None) -> str | None:
    user_key = user_key_from_profile_id(profile_id)
    if user_key is None:
        return None
    return f"profile:{user_key}"


def coalesce_profile_requester(
    *,
    profile_id: int | str | None = None,
    requester_id: int | str | None = None,
) -> int | None:
    """Return the single canonical profile/requester id when either alias is present."""
    for raw in (profile_id, requester_id):
        if raw is None or raw == "":
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return None


def coalesce_profile_id_param(*raw_values: int | str | None) -> int | str | None:
    """Pick the first non-empty profile id from API query/body aliases (§13.3)."""
    for raw in raw_values:
        if raw is None or raw == "":
            continue
        return raw
    return None


def principal_identity_table() -> list[dict[str, str]]:
    """Human-readable naming table for §13.3 documentation and tooling."""
    return [
        {
            "field": FIELD_USER_ID,
            "scope": "auth",
            "meaning": "Login account id (chat auth session actor_id)",
        },
        {
            "field": FIELD_PROFILE_ID,
            "scope": "profile",
            "meaning": "Canonical dating profile row id; equals requester_id for end users",
        },
        {
            "field": FIELD_REQUESTER_ID,
            "scope": "recommendation",
            "meaning": "Recommendation subscription owner; alias of profile_id at Gateway",
        },
        {
            "field": FIELD_USER_KEY,
            "scope": "persona",
            "meaning": "String profile key for persona memory tables",
        },
        {
            "field": FIELD_MEMBER_ID,
            "scope": "matchmaking",
            "meaning": "Pool member id within a matchmaking case",
        },
        {
            "field": FIELD_CASE_ID,
            "scope": "matchmaking",
            "meaning": "Matchmaking / proxy-intro case id",
        },
    ]


def sync_user_block_from_principal(user: dict[str, Any] | None, principal: dict[str, Any] | None) -> dict[str, Any]:
    """Merge canonical profile/requester ids into auth user payload."""
    merged = dict(user or {})
    if not principal:
        return merged
    profile_id = coalesce_profile_requester(
        profile_id=principal.get(FIELD_PROFILE_ID),
        requester_id=principal.get(FIELD_REQUESTER_ID),
    )
    if profile_id is not None:
        merged[FIELD_PROFILE_ID] = profile_id
        merged[FIELD_REQUESTER_ID] = profile_id
    if principal.get(FIELD_USER_ID):
        merged[FIELD_USER_ID] = principal[FIELD_USER_ID]
    if principal.get(FIELD_USER_KEY):
        merged[FIELD_USER_KEY] = principal[FIELD_USER_KEY]
    return merged


__all__ = [
    "FIELD_CASE_ID",
    "FIELD_MEMBER_ID",
    "FIELD_PROFILE_ID",
    "FIELD_REQUESTER_ID",
    "FIELD_USER_ID",
    "FIELD_USER_KEY",
    "PROFILE_ID_FIELD_ALIASES",
    "coalesce_profile_id_param",
    "coalesce_profile_requester",
    "principal_identity_table",
    "profile_ref_from_profile_id",
    "sync_user_block_from_principal",
    "user_key_from_profile_id",
]
