"""External-system bindings and persistence helpers for discovery service."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import os
from pathlib import Path
from typing import Any, Callable

from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path
from match_domain.criteria_compiler import build_discovery_search_request
from match_domain.criteria_snapshots import save_compiled_snapshot
from match_domain.persona_loader import load_persona_for_discovery
from match_domain.profile_write_guard import is_search_criteria_key, merge_working_criteria, split_persona_patch
from match_domain.search_visibility import search_profiles_with_visibility_gate
from observability import metric_gauge
from partner_search import load_self_profile, search_profiles
from partner_search.personality_traits_reader import (
    load_traits_for_discovery,
    load_traits_for_profiles,
    PersonalityTraitsContext,
)

from .agent_runtime import DiscoveryDecision
from .profile_updates import propose_profile_update as _propose_profile_update_impl
from .service_context import search_error_summary
from .storage import StoredSession


def _env_flag(name: str, *, default: bool = False) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "off", "no"}


def discovery_personality_explanation_enabled() -> bool:
    return _env_flag("HER_DISCOVERY_PERSONALITY_EXPLANATION_ENABLED", default=True)


def discovery_personality_ranking_enabled() -> bool:
    return _env_flag("HER_DISCOVERY_PERSONALITY_RANKING_ENABLED", default=True)


def discovery_personality_card_badges_enabled() -> bool:
    return _env_flag("HER_DISCOVERY_PERSONALITY_CARD_BADGES_ENABLED", default=True)


def _normalized_trait_score(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric > 1.0:
        numeric = numeric / 100.0
    return max(0.0, min(1.0, numeric))


def _safe_top_values(traits: dict[str, Any]) -> list[str]:
    values = (traits.get("values") or {}).get("top_values") or []
    return [str(item).strip() for item in list(values) if str(item or "").strip()]


def _shared_top_values(self_traits: dict[str, Any], candidate_traits: dict[str, Any]) -> list[str]:
    self_values = _safe_top_values(self_traits)
    candidate_set = set(_safe_top_values(candidate_traits))
    return [item for item in self_values if item in candidate_set]


def _values_bonus(self_traits: dict[str, Any], candidate_traits: dict[str, Any]) -> tuple[float, list[str]]:
    shared = _shared_top_values(self_traits, candidate_traits)
    if not shared:
        return (0.0, [])
    self_values = _safe_top_values(self_traits)
    candidate_values = _safe_top_values(candidate_traits)
    max_len = max(1, min(len(self_values), len(candidate_values), 3))
    overlap_ratio = min(len(shared), max_len) / max_len
    return (round(overlap_ratio * 5.0, 2), shared[:3])


def _attachment_bonus(self_traits: dict[str, Any], candidate_traits: dict[str, Any]) -> tuple[float, str | None]:
    self_attachment = dict(self_traits.get("attachment") or {})
    candidate_attachment = dict(candidate_traits.get("attachment") or {})
    self_type = str(self_attachment.get("type_code") or "").strip().lower()
    candidate_type = str(candidate_attachment.get("type_code") or "").strip().lower()
    self_anxiety = _normalized_trait_score(self_attachment.get("anxiety"))
    self_avoidance = _normalized_trait_score(self_attachment.get("avoidance"))
    candidate_anxiety = _normalized_trait_score(candidate_attachment.get("anxiety"))
    candidate_avoidance = _normalized_trait_score(candidate_attachment.get("avoidance"))

    if self_type == "secure" and candidate_type == "secure":
        return (4.0, "双方依恋都偏安全型")

    if (
        self_anxiety is not None
        and candidate_avoidance is not None
        and self_anxiety >= 0.65
        and candidate_avoidance >= 0.65
    ) or (
        candidate_anxiety is not None
        and self_avoidance is not None
        and candidate_anxiety >= 0.65
        and self_avoidance >= 0.65
    ):
        return (-2.0, "依恋推进节奏有追逃风险")

    if self_type == "secure" and candidate_type:
        return (2.0, "你的安全型更能稳住关系节奏")
    if candidate_type == "secure":
        return (2.0, "她的依恋偏安全型，关系推进更稳")
    if self_type and candidate_type:
        return (1.0, "依恋节奏不算高冲突")
    return (0.0, None)


def _temperament_bonus(self_traits: dict[str, Any], candidate_traits: dict[str, Any]) -> tuple[float, str | None]:
    self_big_five = dict((self_traits.get("big_five") or {}).get("scores") or {})
    candidate_big_five = dict((candidate_traits.get("big_five") or {}).get("scores") or {})
    if self_big_five and candidate_big_five:
        compared = 0
        closeness_total = 0.0
        for key in ("openness", "conscientiousness", "agreeableness", "neuroticism", "extraversion"):
            left = _normalized_trait_score(self_big_five.get(key))
            right = _normalized_trait_score(candidate_big_five.get(key))
            if left is None or right is None:
                continue
            compared += 1
            closeness_total += max(0.0, 1.0 - abs(left - right))
        if compared > 0:
            avg = closeness_total / compared
            return (round(avg * 3.0, 2), "大五人格整体节奏接近")

    self_mbti = str((self_traits.get("mbti") or {}).get("type_code") or "").strip().upper()
    candidate_mbti = str((candidate_traits.get("mbti") or {}).get("type_code") or "").strip().upper()
    if self_mbti and candidate_mbti:
        same_prefix = 0
        for left, right in zip(self_mbti, candidate_mbti):
            if left == right:
                same_prefix += 1
            else:
                break
        if same_prefix >= 3:
            return (3.0, f"MBTI 节奏接近（{self_mbti}/{candidate_mbti}）")
        if same_prefix >= 2:
            return (2.0, f"MBTI 有一定接近度（{self_mbti}/{candidate_mbti}）")
        return (1.0, f"MBTI 虽不同型，但相处节奏不算冲突（{self_mbti}/{candidate_mbti}）")
    return (0.0, None)


def _build_personality_reasoning(
    self_traits: dict[str, Any],
    candidate_traits: dict[str, Any],
    *,
    candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_traits = dict(candidate_traits or {})
    if not candidate_traits:
        profile = dict((candidate or {}).get("profile") or {})
        hints: list[str] = []
        if str(profile.get("relationship_goal") or "").strip():
            hints.append("从资料看更偏长期关系")
        if str(profile.get("life_routine") or "").strip():
            hints.append("生活节奏相对稳定")
        if str(profile.get("communication_style") or "").strip():
            hints.append("沟通方式看起来更稳")
        return {
            "used": bool(hints),
            "source": "profile_inference",
            "signals": ["profile"] if hints else [],
            "summary": "，".join(hints[:2]) if hints else "",
            "reasons": hints[:3],
            "confidence": "low" if hints else "none",
        }

    signals: list[str] = []
    reasons: list[str] = []
    source = "candidate_only_traits"
    if self_traits:
        source = "traits_pair"

    values_value, shared_values = _values_bonus(self_traits, candidate_traits)
    if shared_values:
        signals.append("values")
        reasons.append(f"都看重“{'、'.join(shared_values[:2])}”")

    attachment_value, attachment_reason = _attachment_bonus(self_traits, candidate_traits)
    if attachment_reason:
        signals.append("attachment")
        reasons.append(attachment_reason)

    temperament_value, temperament_reason = _temperament_bonus(self_traits, candidate_traits)
    if temperament_reason:
        signals.append("big_five" if "大五" in temperament_reason else "mbti")
        reasons.append(temperament_reason)

    candidate_value_type = str((candidate_traits.get("values") or {}).get("value_type") or "").strip()
    if not reasons and candidate_value_type:
        signals.append("values")
        reasons.append(f"价值观偏{candidate_value_type}，更像认真经营关系的人")

    return {
        "used": bool(reasons),
        "source": source,
        "signals": signals[:3],
        "summary": "，".join(reasons[:2]) if reasons else "",
        "reasons": reasons[:3],
        "confidence": "medium" if reasons else "none",
        "score_components": {
            "values_bonus": values_value,
            "attachment_bonus": attachment_value,
            "temperament_bonus": temperament_value,
        },
    }


def _compute_personality_bonus(
    self_traits: dict[str, Any],
    candidate_traits: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    values_value, shared_values = _values_bonus(self_traits, candidate_traits)
    attachment_value, attachment_reason = _attachment_bonus(self_traits, candidate_traits)
    temperament_value, temperament_reason = _temperament_bonus(self_traits, candidate_traits)
    bonus = max(-3.0, min(12.0, values_value + attachment_value + temperament_value))
    trace = {
        "values_bonus": values_value,
        "attachment_bonus": attachment_value,
        "temperament_bonus": temperament_value,
        "used_dimensions": [
            name
            for name, value in (
                ("values", values_value),
                ("attachment", attachment_value),
                ("temperament", temperament_value),
            )
            if value != 0
        ],
    }
    if shared_values:
        trace["shared_values"] = shared_values[:3]
    if attachment_reason:
        trace["attachment_reason"] = attachment_reason
    if temperament_reason:
        trace["temperament_reason"] = temperament_reason
    return (round(bonus, 2), trace)


def profile_source() -> str:
    for name in (
        "HER_DISCOVERY_PROFILE_SOURCE",
        "PARTNER_SEARCH_MYSQL_SOURCE",
        "PERSONA_MEMORY_MYSQL_SOURCE",
    ):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def persona_memory_source() -> str:
    for name in (
        "PERSONA_MEMORY_MYSQL_SOURCE",
        "HER_DISCOVERY_PROFILE_SOURCE",
        "PARTNER_SEARCH_MYSQL_SOURCE",
    ):
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return ""


def load_requester_profile(
    session: StoredSession,
    *,
    source: str | None = None,
    load_profile: Callable[..., Any] | None = None,
) -> dict[str, Any] | None:
    resolved_source = source if source is not None else profile_source()
    return load_requester_profile_with(
        session,
        source=resolved_source,
        load_profile=load_profile or load_self_profile,
    )


def load_requester_profile_with(
    session: StoredSession,
    *,
    source: str,
    load_profile: Callable[..., Any],
) -> dict[str, Any] | None:
    if not source or session.profile_id <= 0:
        return None
    try:
        profile = load_profile(
            source=source,
            self_id=session.profile_id,
        )
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(profile, dict):
        return None
    return profile


def _search_request_meta(
    session: StoredSession,
    *,
    source: str,
    criteria: dict[str, Any],
    self_profile: dict[str, Any] | None,
    effective_self_id: int | None,
    normalized_limit: int,
    compiled: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "criteria": dict(criteria or {}),
        "self_profile": deepcopy(self_profile),
        "self_id": effective_self_id,
        "requested_self_id": session.profile_id,
        "self_profile_lookup_failed": effective_self_id is None and session.profile_id > 0,
        "table_name": None,
        "photos_table_name": None,
        "limit_count": normalized_limit,
        "compiled": deepcopy(compiled or {}),
        "source_map": deepcopy((compiled or {}).get("source_map") or {}),
    }


def search_partner_candidates(
    session: StoredSession,
    *,
    criteria: dict[str, Any],
    limit: int,
    source: str | None = None,
    load_profile: Callable[..., Any] | None = None,
    search: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return search_partner_candidates_with(
        session,
        criteria=criteria,
        limit=limit,
        source=source if source is not None else profile_source(),
        load_profile=load_profile or load_self_profile,
        search=search or search_profiles,
    )


def search_partner_candidates_with(
    session: StoredSession,
    *,
    criteria: dict[str, Any],
    limit: int,
    source: str,
    load_profile: Callable[..., Any],
    search: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    if not source:
        return {
            "error_code": "search_source_not_configured",
            "has_match": False,
            "result_count": 0,
            "results": [],
            "fallback_results": [],
            "diagnostics": {
                "error": "search_source_not_configured",
            },
        }
    self_profile = load_requester_profile_with(
        session,
        source=source,
        load_profile=load_profile,
    )
    if isinstance(self_profile, dict) and not self_profile:
        self_profile = None
    effective_self_id = session.profile_id if isinstance(self_profile, dict) and self_profile else None
    normalized_limit = max(1, min(int(limit or 5), 10))
    merged_criteria = merge_working_criteria(session.state, criteria)
    session.state["working_criteria"] = {
        key: merged_criteria[key]
        for key in merged_criteria
        if is_search_criteria_key(key)
    }
    persona_row = None
    persona_source = persona_memory_source() or source
    if persona_source:
        try:
            persona_row = load_persona_for_discovery(
                source=persona_source,
                profile_id=session.profile_id,
                requester_id=session.requester_id,
            )
        except Exception:  # noqa: BLE001
            persona_row = None
    compiled_request = build_discovery_search_request(
        source=source,
        profile_row=self_profile,
        persona_row=persona_row,
        criteria_overrides=merged_criteria,
        self_id=effective_self_id,
        limit=normalized_limit,
    )
    compiled = dict(compiled_request.get("compiled") or {})
    request_meta = _search_request_meta(
        session,
        source=source,
        criteria=compiled_request.get("criteria") or {},
        self_profile=compiled_request.get("self_profile"),
        effective_self_id=effective_self_id,
        normalized_limit=normalized_limit,
        compiled=compiled,
    )
    try:
        save_compiled_snapshot(
            compiled,
            scene="discovery_search",
            profile_id=session.profile_id,
            requester_id=session.requester_id,
            user_key=str(session.requester_id),
            discovery_session_id=session.session_id,
        )
        compiled_self_profile = compiled_request.get("self_profile")
        if isinstance(compiled_self_profile, dict) and not compiled_self_profile:
            compiled_self_profile = None
        response = search_profiles_with_visibility_gate(
            search,
            source=source,
            criteria=dict(compiled_request.get("criteria") or {}),
            self_profile=compiled_self_profile,
            self_id=effective_self_id,
            limit=normalized_limit,
            photo_preview_count=3,
            moderation_dsn=os.environ.get("PARTNER_CHAT_DB"),
        )
        response["request_meta"] = request_meta

        explanation_enabled = discovery_personality_explanation_enabled()
        ranking_enabled = discovery_personality_ranking_enabled()

        # === Discovery personality enrichment ===
        user_traits = None
        if persona_source and session.profile_id:
            user_traits = load_traits_for_discovery(
                source=persona_source,
                profile_id=session.profile_id,
                requester_id=session.requester_id,
            )
        user_traits_dict = (
            user_traits.to_dict()
            if user_traits and user_traits.availability.get("overall_completeness", 0) > 0
            else {}
        )

        results = response.get("results") or []
        personality_trace = {
            "self_traits_available": bool(user_traits_dict),
            "candidate_traits_count": 0,
            "ranking_enabled": ranking_enabled,
            "explanation_enabled": explanation_enabled,
            "card_badges_enabled": discovery_personality_card_badges_enabled(),
            "top_candidates_used_personality": [],
            "fallback_explanation_used": False,
        }
        if results and persona_source:
            candidate_ids = []
            for candidate in results:
                candidate_id = candidate.get("id")
                if candidate_id:
                    try:
                        candidate_ids.append(int(candidate_id))
                    except (TypeError, ValueError):
                        pass

            if candidate_ids:
                candidate_traits_map = load_traits_for_profiles(
                    source=persona_source,
                    profile_ids=candidate_ids,
                )

                for candidate in results:
                    candidate_id = candidate.get("id")
                    if candidate_id:
                        traits_ctx = candidate_traits_map.get(int(candidate_id))
                        if traits_ctx and traits_ctx.availability.get("overall_completeness", 0) > 0:
                            candidate["personality_traits"] = traits_ctx.to_dict()
                            candidate["personality_availability"] = traits_ctx.availability
                            personality_trace["candidate_traits_count"] = int(personality_trace["candidate_traits_count"]) + 1

        for index, candidate in enumerate(results):
            candidate_traits = dict(candidate.get("personality_traits") or {})
            reasoning = (
                _build_personality_reasoning(
                    user_traits_dict,
                    candidate_traits,
                    candidate=candidate,
                )
                if explanation_enabled
                else {"used": False, "source": "disabled", "signals": [], "summary": "", "reasons": [], "confidence": "none"}
            )
            candidate["personality_reasoning"] = reasoning
            if reasoning.get("used"):
                personality_trace["top_candidates_used_personality"].append(int(candidate.get("id") or 0))

            base_score = candidate.get("base_score")
            if base_score in (None, ""):
                base_score = candidate.get("score") if candidate.get("score") not in (None, "") else candidate.get("fit_score")
            try:
                candidate["base_score"] = float(base_score or 0.0)
            except (TypeError, ValueError):
                candidate["base_score"] = 0.0

            candidate["personality_bonus"] = 0.0
            candidate["personality_scoring_trace"] = {
                "used_dimensions": [],
                "ranking_enabled": ranking_enabled,
                "explanation_enabled": explanation_enabled,
            }
            if ranking_enabled and user_traits_dict and candidate_traits:
                bonus, scoring_trace = _compute_personality_bonus(user_traits_dict, candidate_traits)
                candidate["personality_bonus"] = bonus
                candidate["personality_scoring_trace"] = {
                    **scoring_trace,
                    "ranking_enabled": True,
                    "base_score": candidate["base_score"],
                }
                candidate["score"] = round(candidate["base_score"] + bonus, 2)
            elif candidate.get("score") in (None, ""):
                candidate["score"] = candidate["base_score"]

            candidate["_discovery_original_index"] = index

        if ranking_enabled and results:
            results.sort(
                key=lambda item: (
                    float(item.get("score") or 0.0),
                    float(item.get("base_score") or 0.0),
                    -int(item.get("_discovery_original_index") or 0),
                ),
                reverse=True,
            )

        for item in results:
            item.pop("_discovery_original_index", None)

        personality_trace["top_candidates_used_personality"] = [
            int(item.get("id") or 0)
            for item in results[:3]
            if dict(item.get("personality_reasoning") or {}).get("used")
        ]
        response["personality_trace"] = personality_trace

        if user_traits_dict:
            response["user_personality_traits"] = user_traits.to_dict()

        return response
    except Exception as exc:  # noqa: BLE001
        return {
            "error_code": "partner_search_failed",
            "has_match": False,
            "result_count": 0,
            "results": [],
            "fallback_results": [],
            "diagnostics": {
                "error": str(exc)[:200],
            },
            "request_meta": request_meta,
        }


def propose_requester_profile_update(
    storage: Any,
    session: StoredSession,
    *,
    patch: dict[str, Any],
    evidence_text: str | None = None,
    load_profile: Callable[..., Any] | None = None,
    source: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    profile_part, _, _ = split_persona_patch(patch)
    if not profile_part:
        return {
            "proposed": False,
            "error_code": "empty_profile_patch",
            "message": "没有需要确认的资料字段。",
        }
    resolved_source = source if source is not None else profile_source()
    current_profile = load_requester_profile_with(
        session,
        source=resolved_source,
        load_profile=load_profile or load_self_profile,
    )
    return _propose_profile_update_impl(
        storage,
        session,
        patch=profile_part,
        evidence_text=evidence_text,
        current_profile=current_profile,
        now=now,
    )


def sync_requester_persona_memory(
    session: StoredSession,
    *,
    patch: dict[str, Any],
    now: datetime | None = None,
    load_persona_memory: Callable[..., dict[str, Any]] | None = None,
    storage: Any | None = None,
    load_profile: Callable[..., Any] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    normalized_patch = dict(patch or {})
    if not normalized_patch:
        return {
            "synced": False,
            "error_code": "empty_persona_patch",
            "message": "没有可写入画像的字段。",
        }

    profile_part, persona_part, search_part = split_persona_patch(normalized_patch)
    profile_proposals: list[dict[str, Any]] = []

    if search_part:
        merged = merge_working_criteria(session.state, search_part)
        session.state["working_criteria"] = {
            key: merged[key] for key in merged if is_search_criteria_key(key)
        }

    if profile_part:
        if storage is None:
            return {
                "synced": False,
                "error_code": "profile_update_requires_confirmation",
                "message": "资料字段变更需要用户确认，当前存储未配置。",
                "profile_fields": sorted(profile_part.keys()),
            }
        proposal = propose_requester_profile_update(
            storage,
            session,
            patch=profile_part,
            load_profile=load_profile,
            source=source,
            now=now,
        )
        if proposal.get("proposed"):
            profile_proposals.append(proposal)
            pending_timeline = list(session.state.get("profile_prompts_for_timeline") or [])
            pending_timeline.append(proposal)
            session.state["profile_prompts_for_timeline"] = pending_timeline

    if not persona_part:
        if profile_proposals:
            return {
                "synced": True,
                "user_key": str(session.requester_id),
                "patch_keys": [],
                "profile_proposals": profile_proposals,
                "persona_synced": False,
            }
        return {
            "synced": False,
            "error_code": "empty_persona_patch",
            "message": "没有可写入偏好画像的字段。",
        }

    persona_source = persona_memory_source()
    if not persona_source:
        return {
            "synced": False,
            "error_code": "persona_memory_source_not_configured",
            "message": "当前没有配置 persona-memory-sync 数据源。",
            "profile_proposals": profile_proposals,
        }
    current = now or datetime.now()
    try:
        upsert_persona_memory = load_persona_memory or load_persona_memory_bindings()
        upsert_result = upsert_persona_memory(
            {
                "source": persona_source,
                "user_key": str(session.requester_id),
                "source_type": "explicit",
                "patch": persona_part,
                "sync_profile": False,
                "conversation_ref": f"discovery/{session.session_id}",
                "basis": "discovery_agent",
            },
            include_normalized_patch=True,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "synced": False,
            "error_code": "persona_memory_sync_failed",
            "message": str(exc)[:200],
            "profile_proposals": profile_proposals,
        }
    session.state["last_persona_sync_at"] = current.isoformat()
    session.state["last_persona_sync_fields"] = sorted(
        str(key).strip() for key in persona_part.keys() if str(key or "").strip()
    )
    return {
        "synced": True,
        "user_key": str(session.requester_id),
        "patch_keys": list(session.state["last_persona_sync_fields"]),
        "upsert": upsert_result,
        "profile_proposals": profile_proposals,
        "persona_synced": True,
    }


def run_discovery_collect_then_search(
    session: StoredSession,
    *,
    persona_patch: dict[str, Any] | None = None,
    criteria: dict[str, Any] | None = None,
    limit: int = 5,
    source: str | None = None,
    load_profile: Callable[..., Any] | None = None,
    search: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Service-layer orchestration: explicit collect first, then compile/search."""
    collect_result = None
    if persona_patch:
        collect_result = sync_requester_persona_memory(session, patch=persona_patch)
        if not collect_result.get("synced"):
            return {
                "orchestration": "collect_failed",
                "collect": collect_result,
                "search": None,
            }
    search_response = search_partner_candidates(
        session,
        criteria=criteria or {},
        limit=limit,
        source=source,
        load_profile=load_profile,
        search=search,
    )
    return {
        "orchestration": "collect_then_search" if persona_patch else "search_only",
        "collect": collect_result,
        "search": search_response,
    }


def persist_search_run(
    storage: Any,
    increment_metric: Callable[[str], int],
    session: StoredSession,
    *,
    search_response: dict[str, Any],
    now: datetime,
) -> int | None:
    error_summary = search_error_summary(search_response)
    session.state["last_search_result_count"] = int(search_response.get("result_count") or 0)
    session.state["last_search_has_match"] = bool(search_response.get("has_match"))
    if error_summary is None:
        session.state.pop("last_search_error_code", None)
        session.state.pop("last_search_error_message", None)
    else:
        session.state["last_search_error_code"] = str(error_summary.get("error_code") or "")
        session.state["last_search_error_message"] = str(error_summary.get("error") or "")
    request_meta = dict(search_response.get("request_meta") or {})
    source = str(request_meta.get("source") or "").strip()
    if not source:
        session.state.pop("last_search_run_id", None)
        return None
    search_run_id = storage.create_search_run(
        session_id=session.session_id,
        requester_id=session.requester_id,
        profile_id=session.profile_id,
        source=source,
        criteria=dict(request_meta.get("criteria") or {}),
        self_profile=request_meta.get("self_profile"),
        limit_count=int(request_meta.get("limit_count") or 5),
        response=search_response,
        created_at=now,
    )
    session.state["last_search_run_id"] = search_run_id
    increment_metric("search_runs.created")
    metric_gauge(
        "discovery.search_runs.result_count",
        int(search_response.get("result_count") or 0),
        session_id=session.session_id,
        search_run_id=search_run_id,
    )
    return search_run_id


def load_recommendation_bindings():
    ensure_partner_system_roots_on_sys_path(Path(__file__).resolve().parents[3])
    from recommendation_system import (  # type: ignore[import-untyped]
        connect_db as connect_recommendation_db,
        handle_opt_in_decision,
        initialize_database as initialize_recommendation_database,
    )

    return (
        connect_recommendation_db,
        handle_opt_in_decision,
        initialize_recommendation_database,
    )


def open_recommendation_conn(*, load_bindings: Callable[[], tuple[Any, Any, Any]] | None = None):
    connect_recommendation_db, _, initialize_recommendation_database = (
        load_bindings() if load_bindings is not None else load_recommendation_bindings()
    )
    dsn = str(
        os.environ.get("PARTNER_RECOMMENDATION_DB")
        or "mysql://root@127.0.0.1:3307/her_recommendation"
    ).strip()
    conn = connect_recommendation_db(dsn)
    initialize_recommendation_database(
        conn,
        mode=(os.environ.get("HER_SCHEMA_INIT_MODE") or "").strip() or None,
    )
    return conn


def load_persona_memory_bindings():
    from persona_memory_sync import upsert_persona_memory

    return upsert_persona_memory


def decision_payload(decision: DiscoveryDecision) -> dict[str, Any]:
    return {
        "phase": decision.phase,
        "assistant_message": decision.assistant_message,
        "criteria_labels": list(decision.criteria_labels),
        "suggested_actions": [
            {
                "label": action.label,
                "style": action.style,
                "semantic_payload": deepcopy(action.semantic_payload),
            }
            for action in list(decision.suggested_actions)
        ],
        "result_group_title": decision.result_group_title,
        "selected_candidates": [
            {
                "profile_id": candidate.profile_id,
                "reason_summary": candidate.reason_summary,
            }
            for candidate in list(decision.selected_candidates)
        ],
    }


__all__ = [
    "decision_payload",
    "load_persona_memory_bindings",
    "load_recommendation_bindings",
    "load_requester_profile",
    "open_recommendation_conn",
    "persona_memory_source",
    "persist_search_run",
    "profile_source",
    "propose_requester_profile_update",
    "run_discovery_collect_then_search",
    "search_partner_candidates",
    "sync_requester_persona_memory",
]
