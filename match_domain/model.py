"""Canonical domain objects for unified recommendation and matchmaking states."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping


class RelationStatus(str, Enum):
    NEW = "new"
    RECOMMENDED = "recommended"
    SAVED = "saved"
    SKIPPED = "skipped"
    COOLING = "cooling"
    DIRECT_GREET_STARTED = "direct_greet_started"
    DIRECT_GREETED = "direct_greet_started"
    PROXY_INTRO_ACTIVE = "proxy_intro_active"
    MATCHED = "matched"
    CLOSED = "closed"


class PairStatus(str, Enum):
    ELIGIBLE = "eligible"
    BELOW_THRESHOLD = "below_threshold"
    BLOCKED = "blocked"
    COOLING = "cooling"
    CASE_OPENED = "case_opened"
    MUTUAL_ACCEPT = "mutual_accept"
    NEEDS_REVALIDATION = "needs_revalidation"
    STALE = "stale"


class CaseType(str, Enum):
    PROXY_INTRO = "proxy_intro"
    MATCHMAKING = "matchmaking"


class CaseStatus(str, Enum):
    PENDING_CONTACT = "pending_contact"
    AWAITING_REPLY = "awaiting_reply"  # 未查看状态（新信）
    VIEWED = "viewed"  # 已查看状态（已打开但未决定）✅ 新增
    ACCEPTED = "accepted"
    DECLINED = "declined"
    TIMED_OUT = "timed_out"
    CLOSED = "closed"


@dataclass(frozen=True)
class ProfileRef:
    source: str
    profile_id: int | None = None
    user_key: str | None = None

    def __post_init__(self) -> None:
        if not self.source:
            raise ValueError("ProfileRef.source is required.")
        if self.profile_id is None and not self.user_key:
            raise ValueError("ProfileRef requires profile_id or user_key.")

    @property
    def stable_key(self) -> str:
        if self.profile_id is not None:
            return f"{self.source}#profile:{int(self.profile_id)}"
        return f"{self.source}#user:{self.user_key}"


def relation_key(owner: ProfileRef, target: ProfileRef) -> str:
    return f"{owner.stable_key}->{target.stable_key}"


def pair_key(left: ProfileRef, right: ProfileRef) -> str:
    low, high = sorted([left.stable_key, right.stable_key])
    return f"{low}<->{high}"


@dataclass(frozen=True)
class MatchEvent:
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    actor_type: str
    actor_id: str
    source_service: str
    correlation_id: str
    occurred_at: datetime
    payload: Mapping[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    version: int = 1
    trace_id: str | None = None

    def __post_init__(self) -> None:
        required = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "source_service": self.source_service,
            "correlation_id": self.correlation_id,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"MatchEvent missing required fields: {', '.join(missing)}")

    def to_dict(self) -> dict[str, Any]:
        out = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "source_service": self.source_service,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "occurred_at": self.occurred_at.isoformat(sep=" "),
            "payload": dict(self.payload),
            "version": self.version,
        }
        if self.trace_id:
            out["trace_id"] = self.trace_id
        return out
