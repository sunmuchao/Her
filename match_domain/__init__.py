"""Shared domain vocabulary for relationship-ledger migration."""

from .model import (
    CaseStatus,
    CaseType,
    MatchEvent,
    PairStatus,
    ProfileRef,
    RelationStatus,
    pair_key,
    relation_key,
)

__all__ = [
    "CaseStatus",
    "CaseType",
    "MatchEvent",
    "PairStatus",
    "ProfileRef",
    "RelationStatus",
    "pair_key",
    "relation_key",
]
