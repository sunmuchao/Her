"""ID and key helpers for matchmaking pool/case entities."""

from __future__ import annotations

import uuid


def generate_member_id() -> str:
    return f"pool-{uuid.uuid4().hex[:12]}"


def generate_case_id() -> str:
    return f"case-{uuid.uuid4().hex[:12]}"


def generate_feedback_id() -> str:
    return f"feedback-{uuid.uuid4().hex[:12]}"


def pair_key_for(member_a_id: str, member_b_id: str) -> str:
    low_id, high_id = sorted([str(member_a_id), str(member_b_id)])
    return f"{low_id}:{high_id}"


__all__ = [
    "generate_case_id",
    "generate_feedback_id",
    "generate_member_id",
    "pair_key_for",
]
