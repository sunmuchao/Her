"""Thread-local rule resolution context for partner_search (§13.5)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Any, Iterator


@dataclass
class SearchRuleContext:
    experiment_bucket: str | None = None
    profile_id: int | None = None
    conn: Any = None


_search_rule_ctx: ContextVar[SearchRuleContext | None] = ContextVar("search_rule_ctx", default=None)


def get_search_rule_context() -> SearchRuleContext | None:
    return _search_rule_ctx.get()


@contextmanager
def search_rule_context(
    *,
    experiment_bucket: str | None = None,
    profile_id: int | None = None,
    conn: Any = None,
    rule_resolution: dict[str, Any] | None = None,
) -> Iterator[SearchRuleContext | None]:
    if rule_resolution:
        experiment_bucket = rule_resolution.get("experiment_bucket") or experiment_bucket
        profile_id = rule_resolution.get("profile_id") or profile_id
        conn = rule_resolution.get("conn") or conn
    if experiment_bucket is None and profile_id is None and conn is None:
        yield None
        return
    ctx = SearchRuleContext(
        experiment_bucket=str(experiment_bucket).strip() if experiment_bucket else None,
        profile_id=int(profile_id) if profile_id not in {None, ""} else None,
        conn=conn,
    )
    token: Token = _search_rule_ctx.set(ctx)
    try:
        yield ctx
    finally:
        _search_rule_ctx.reset(token)


__all__ = [
    "SearchRuleContext",
    "get_search_rule_context",
    "search_rule_context",
]
