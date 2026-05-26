"""Normalize domain-specific status strings onto canonical match_domain vocabulary."""

from __future__ import annotations

from .model import CaseStatus

# Proxy-intro DB statuses that differ from canonical CaseStatus values.
_CASE_STATUS_ALIASES: dict[str, str] = {
    "pending_outreach": CaseStatus.PENDING_CONTACT.value,
}


def canonical_case_status_value(raw_status: str | None) -> str | None:
    if raw_status is None:
        return None
    normalized = str(raw_status).strip()
    if not normalized:
        return None
    return _CASE_STATUS_ALIASES.get(normalized, normalized)


def is_open_case_status(raw_status: str | None) -> bool:
    canonical = canonical_case_status_value(raw_status)
    return canonical in {
        CaseStatus.PENDING_CONTACT.value,
        CaseStatus.AWAITING_REPLY.value,
        CaseStatus.ACCEPTED.value,
        "pending_outreach",
    }


__all__ = ["canonical_case_status_value", "is_open_case_status"]
