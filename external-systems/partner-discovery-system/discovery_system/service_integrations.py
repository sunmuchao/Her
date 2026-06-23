"""External-system bindings and persistence helpers for discovery service."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Callable

_logger = logging.getLogger(__name__)

from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path
from match_domain.criteria_compiler import build_discovery_search_request
from match_domain.criteria_snapshots import save_compiled_snapshot
from match_domain.persona_loader import load_persona_for_discovery
from match_domain.profile_write_guard import is_search_criteria_key, merge_working_criteria, split_persona_patch
from match_domain.search_visibility import search_profiles_with_visibility_gate
from observability import metric_gauge
from partner_search import load_self_profile, search_profiles
from partner_search.personality_traits_reader import (
    build_traits_context_from_persona_row,
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


def _compose_reasoning_summary(reasons: list[str]) -> str:
    clean = [str(item).strip("，。 ") for item in reasons if str(item or "").strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]
    if len(clean) == 2:
        return f"{clean[0]}，{clean[1]}"
    return f"{clean[0]}，{clean[1]}，整体会更顺"


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
        return (4.0, "依恋都偏安全型，相处会更稳")

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
        return (-2.0, "依恋节奏容易一追一逃")

    if self_type == "secure" and candidate_type:
        return (2.0, "你的节奏更稳，比较能兜住关系")
    if candidate_type == "secure":
        return (2.0, "她的关系节奏偏稳，不容易忽冷忽热")
    if self_type and candidate_type:
        return (1.0, "依恋节奏不算拧巴")
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
            return (round(avg * 3.0, 2), "性格节奏比较接近")

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
            return (3.0, f"MBTI 节奏很接近（{self_mbti}/{candidate_mbti}）")
        if same_prefix >= 2:
            return (2.0, f"MBTI 有一定同频感（{self_mbti}/{candidate_mbti}）")
        return (1.0, f"MBTI 虽不同型，但相处节奏不冲突（{self_mbti}/{candidate_mbti}）")
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
            hints.append("从资料看更像认真奔着长期去的")
        if str(profile.get("life_routine") or "").strip():
            hints.append("生活节奏比较稳")
        if str(profile.get("communication_style") or "").strip():
            hints.append("沟通方式看起来比较舒服")
        return {
            "used": bool(hints),
            "source": "profile_inference",
            "signals": ["profile"] if hints else [],
            "summary": _compose_reasoning_summary(hints[:2]) if hints else "",
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
        reasons.append(f"都看重“{'、'.join(shared_values[:2])}”这类长期稳定的东西")

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
        reasons.append(f"价值观偏{candidate_value_type}，看起来更像会认真经营关系的人")

    return {
        "used": bool(reasons),
        "source": source,
        "signals": signals[:3],
        "summary": _compose_reasoning_summary(reasons[:2]) if reasons else "",
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


def _build_candidate_context(candidate: dict[str, Any]) -> dict[str, Any]:
    traits = dict(candidate.get("personality_traits") or {})
    summary = dict(candidate.get("summary") or {})
    availability = dict(candidate.get("personality_availability") or {})

    has_traits = bool(traits) and float(availability.get("overall_completeness") or 0) > 0
    has_summary = bool(summary)
    missing_dimensions: list[str] = []

    if not has_traits:
        missing_dimensions.append("traits")
    if not has_summary:
        missing_dimensions.append("summary")
    if has_traits and not dict(traits.get("values") or {}):
        missing_dimensions.append("values")
    if has_traits and not dict(traits.get("attachment") or {}):
        missing_dimensions.append("attachment")
    if has_traits and not dict(traits.get("big_five") or {}):
        missing_dimensions.append("big_five")
    if has_summary and not str(summary.get("emotional_needs") or "").strip():
        missing_dimensions.append("emotional_needs")

    if has_traits and has_summary:
        evidence_level = "high"
        reason_mode = "rich_reasoning"
    elif has_traits or has_summary:
        evidence_level = "medium"
        reason_mode = "limited_reasoning"
    else:
        evidence_level = "low"
        reason_mode = "profile_only"

    allowed_reason_sources = ["profile"]
    if has_traits:
        allowed_reason_sources.append("personality_traits")
    if has_summary:
        allowed_reason_sources.append("summary")

    return {
        "has_traits": has_traits,
        "has_summary": has_summary,
        "evidence_level": evidence_level,
        "reason_mode": reason_mode,
        "allowed_reason_sources": allowed_reason_sources,
        "missing_dimensions": missing_dimensions,
    }


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
    personality_match: dict[str, Any] = {},  # ← 新增参数：性格匹配条件
    limit: int,
    source: str | None = None,
    load_profile: Callable[..., Any] | None = None,
    search: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """搜索候选人（支持性格向量筛选）

    Args:
        session: 会话对象
        criteria: 结构化查询条件（硬约束：性别、年龄、城市）
        personality_match: 性格匹配条件（软约束：向量筛选）
            示例：
            {
                "match_traits": ["外向", "温柔"],
                "similarity_threshold": 0.75
            }
            - match_traits: 想要匹配的性格特质列表
            - similarity_threshold: 相似度阈值（0.0-1.0，默认0.75）
        limit: 结果数量限制
        source: 数据源
        load_profile: 加载用户profile的函数
        search: 搜索执行函数

    Returns:
        搜索结果，包含候选人列表 + 摘要信息 + 筛选统计
    """
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 转换 personality_match 为 vector_filter_json
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    vector_filter_json = None
    if personality_match:
        match_traits = personality_match.get("match_traits") or []
        similarity_threshold = float(personality_match.get("similarity_threshold") or 0.75)

        if match_traits:
            # 构建 vector_filter_json 格式
            vector_filter_json = {
                "include": {
                    "personality_traits": {
                        "text": "、".join(match_traits),  # 用逗号连接多个特质
                        "similarity_threshold": similarity_threshold
                    }
                }
            }
            _logger.info(
                "【性格匹配转换】personality_match=%s → vector_filter_json=%s",
                personality_match,
                vector_filter_json
            )

    return search_partner_candidates_with(
        session,
        criteria=criteria,
        limit=limit,
        source=source if source is not None else profile_source(),
        load_profile=load_profile or load_self_profile,
        search=search or search_profiles,
        vector_filter_json=vector_filter_json,  # ← 传递转换后的参数
    )


def search_partner_candidates_with(
    session: StoredSession,
    *,
    criteria: dict[str, Any],
    limit: int,
    source: str,
    load_profile: Callable[..., Any],
    search: Callable[..., dict[str, Any]],
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 新增参数：向量筛选条件（支持排除和包含）
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    vector_filter_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # ✅ 可观测性增强：入口日志
    _logger.info(
        "【搜索开始】session_id=%s criteria=%s limit=%s",
        session.session_id,
        json.dumps(criteria, ensure_ascii=False)[:200],
        limit,
    )

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
    persona_row = None
    persona_source = persona_memory_source() or source
    with ThreadPoolExecutor(max_workers=2) as executor:
        self_profile_future = executor.submit(
            load_requester_profile_with,
            session,
            source=source,
            load_profile=load_profile,
        )
        persona_future = (
            executor.submit(
                load_persona_for_discovery,
                source=persona_source,
                profile_id=session.profile_id,
                requester_id=session.requester_id,
            )
            if persona_source
            else None
        )
        try:
            self_profile = self_profile_future.result()
        except Exception:  # noqa: BLE001
            self_profile = None
        if persona_future is not None:
            try:
                persona_row = persona_future.result()
            except Exception:  # noqa: BLE001
                persona_row = None

    # ✅ 可观测性增强：并行加载结果日志
    _logger.info(
        "【用户数据加载】session_id=%s profile_id=%s has_self_profile=%s has_persona=%s",
        session.session_id,
        session.profile_id,
        bool(self_profile),
        bool(persona_row),
    )

    if isinstance(self_profile, dict) and not self_profile:
        self_profile = None
    effective_self_id = session.profile_id if isinstance(self_profile, dict) and self_profile else None

    # ✅ 可观测性增强：用户资料详情日志
    if self_profile:
        _logger.info(
            "【用户资料详情】session_id=%s age=%s city=%s gender=%s",
            session.session_id,
            self_profile.get("age"),
            self_profile.get("city"),
            self_profile.get("gender"),
        )

    # ✅ Agent Native 改进：移除重复校验
    # limit 应该在 Tool 层（最外层）校验，Service Integrations 层不再重复校验
    # 方案C：两阶段搜索策略
    # - 第一阶段：数据库搜索，不限制数量（传入更大的搜索limit）
    # - 第二阶段：向量筛选后，再截断为用户要求的limit
    final_limit = int(limit or 5)  # 用户最终要求的返回数量
    search_limit = max(final_limit, 50)  # 第一阶段搜索数量（至少50个，避免向量筛选后结果为空）
    merged_criteria = merge_working_criteria(session.state, criteria)
    if session.state.pop("pending_refresh", False):
        refresh_exclude_ids = {
            int(candidate_id)
            for candidate_id in list(session.state.get("last_shown_candidate_ids") or [])
            if int(candidate_id) > 0
        }
        if refresh_exclude_ids:
            existing_exclude_ids = merged_criteria.get("exclude_ids")
            normalized_exclude_ids: set[int] = set()
            if isinstance(existing_exclude_ids, (list, tuple, set)):
                for candidate_id in existing_exclude_ids:
                    try:
                        normalized_exclude_ids.add(int(candidate_id))
                    except (TypeError, ValueError):
                        continue
            elif existing_exclude_ids not in (None, ""):
                try:
                    normalized_exclude_ids.add(int(existing_exclude_ids))
                except (TypeError, ValueError):
                    pass
            merged_criteria["exclude_ids"] = normalized_exclude_ids | refresh_exclude_ids
            _logger.info(
                "【换一批排除注入】session_id=%s exclude_ids=%s",
                session.session_id,
                sorted(merged_criteria["exclude_ids"]),
            )
    session.state["working_criteria"] = {
        key: merged_criteria[key]
        for key in merged_criteria
        if is_search_criteria_key(key)
    }
    compiled_request = build_discovery_search_request(
        source=source,
        profile_row=self_profile,
        persona_row=persona_row,
        criteria_overrides=merged_criteria,
        self_id=effective_self_id,
        limit=search_limit,  # ✅ 方案C：第一阶段搜索数量（至少50）
    )
    compiled = dict(compiled_request.get("compiled") or {})
    request_meta = _search_request_meta(
        session,
        source=source,
        criteria=compiled_request.get("criteria") or {},
        self_profile=compiled_request.get("self_profile"),
        effective_self_id=effective_self_id,
        normalized_limit=search_limit,  # ✅ 方案C：第一阶段搜索数量
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

        # ✅ 可观测性增强：外部调用日志（搜索开始）
        search_start_time = time.time()
        _logger.info(
            "【搜索执行开始】session_id=%s criteria_keys=%s limit=%s",
            session.session_id,
            list(compiled_request.get("criteria") or {}.keys()),
            limit,
        )

        response = search_profiles_with_visibility_gate(
            search,
            source=source,
            criteria=dict(compiled_request.get("criteria") or {}),
            self_profile=compiled_self_profile,
            self_id=effective_self_id,
            limit=search_limit,  # ✅ 方案C：第一阶段搜索数量（至少50）
            photo_preview_count=3,
            moderation_dsn=os.environ.get("PARTNER_CHAT_DB"),
        )

        # ✅ 可观测性增强：外部调用日志（搜索完成）
        search_elapsed_ms = round((time.time() - search_start_time) * 1000, 2)
        _logger.info(
            "【搜索执行完成】session_id=%s result_count=%s has_match=%s elapsed_ms=%s",
            session.session_id,
            response.get("result_count"),
            response.get("has_match"),
            search_elapsed_ms,
        )

        response["request_meta"] = request_meta

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 新增：向量筛选（支持排除和包含）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        if vector_filter_json:
            results_before_filter = response.get("results") or []
            candidate_ids_before_filter = []
            for candidate in results_before_filter:
                candidate_id = candidate.get("id")
                if candidate_id:
                    try:
                        candidate_ids_before_filter.append(int(candidate_id))
                    except (TypeError, ValueError):
                        pass

            if candidate_ids_before_filter:
                import asyncio
                from match_domain.vector_filter import vector_filter_candidates

                _logger.info(
                    "【向量筛选开始】session_id=%s candidate_count=%s filter_config=%s",
                    session.session_id,
                    len(candidate_ids_before_filter),
                    vector_filter_json,
                )

                # 在同步函数中调用异步代码
                try:
                    excluded_ids, included_ids, filter_trace = asyncio.run(
                        vector_filter_candidates(
                            vector_filter_json=vector_filter_json,
                            candidate_ids=candidate_ids_before_filter,
                            user_id=session.requester_id,
                        )
                    )

                    # 过滤结果
                    filtered_results = []
                    for candidate in results_before_filter:
                        candidate_id = candidate.get("id")
                        if candidate_id:
                            try:
                                if int(candidate_id) in included_ids and int(candidate_id) not in excluded_ids:
                                    filtered_results.append(candidate)
                            except (TypeError, ValueError):
                                pass

                    response["results"] = filtered_results
                    response["result_count"] = len(filtered_results)
                    response["has_match"] = bool(filtered_results)
                    response["vector_filter_trace"] = filter_trace

                    _logger.info(
                        "【向量筛选完成】session_id=%s before_count=%s after_count=%s excluded=%s",
                        session.session_id,
                        len(results_before_filter),
                        len(filtered_results),
                        len(excluded_ids),
                    )

                except Exception as exc:
                    _logger.error(
                        "【向量筛选失败】session_id=%s error=%s",
                        session.session_id,
                        str(exc)[:200],
                    )
                    # 失败时保留原始结果
                    response["vector_filter_trace"] = {
                        "error": str(exc)[:200],
                        "mode": "failed",
                    }

        # ✅ Agent Native 改进：移除性格特质增强逻辑的环境变量检查
        # 这些环境变量控制的是 Tool 层的性格增强逻辑（已移除）
        # Agent 层会自主决定是否使用性格特质数据，不需要环境变量控制

        # === Discovery personality enrichment ===
        user_traits = None
        if persona_source and session.profile_id and persona_row:
            user_traits = build_traits_context_from_persona_row(
                persona_row,
                profile_id=session.profile_id,
            )
        elif persona_source and session.profile_id:
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

        # ✅ 方案C：第三阶段截断
        # 第一阶段搜索了search_limit（至少50）个候选人
        # 第二阶段向量筛选后可能剩10-20个
        # 第三阶段截断为用户要求的final_limit（如5个）
        before_truncation_count = len(results)
        if before_truncation_count > final_limit:
            results = results[:final_limit]
            response["results"] = results
            response["result_count"] = len(results)
            _logger.info(
                "【最终截断】session_id=%s before_count=%s final_count=%s",
                session.session_id,
                before_truncation_count,
                final_limit,
            )

        # ✅ Agent Native 改进：简化 personality_trace
        # 只保留原始数据统计，移除性格增强相关的统计
        personality_trace = {
            "self_traits_available": bool(user_traits_dict),
            "candidate_traits_count": 0,
            "agent_native_mode": True,
            "note": "性格特质数据已返回，Agent 自主决定如何使用",
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

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 新增：批量加载完整摘要信息（供 Agent 判断）
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        results = response.get("results") or []
        if results:
            import asyncio
            from match_domain.summary_loader import build_summary_meta, load_complete_summaries_batch

            _logger.info(
                "【摘要加载开始】session_id=%s candidate_count=%s",
                session.session_id,
                len(results),
            )

            candidate_ids: list[int] = []
            for candidate in results:
                candidate_id = candidate.get("id")
                if candidate_id:
                    try:
                        candidate_ids.append(int(candidate_id))
                    except (TypeError, ValueError):
                        pass

            summaries_by_candidate: dict[int, dict[str, str]] = {}
            if candidate_ids:
                try:
                    summaries_by_candidate = asyncio.run(
                        load_complete_summaries_batch(user_ids=candidate_ids)
                    )
                except Exception as exc:
                    _logger.warning(
                        "【批量摘要加载失败】session_id=%s error=%s",
                        session.session_id,
                        str(exc)[:100],
                    )

            summary_loaded_count = 0
            for candidate in results:
                candidate_id = candidate.get("id")
                resolved_candidate_id: int | None = None
                if candidate_id:
                    try:
                        resolved_candidate_id = int(candidate_id)
                    except (TypeError, ValueError):
                        resolved_candidate_id = None
                summary_dict = summaries_by_candidate.get(resolved_candidate_id or -1) or {}
                if summary_dict:
                    candidate["summary"] = summary_dict
                    candidate["summary_meta"] = build_summary_meta(summary_dict)
                    summary_loaded_count += 1
                candidate["candidate_context"] = _build_candidate_context(candidate)

            personality_trace["summary_loaded_count"] = summary_loaded_count

            _logger.info(
                "【摘要加载完成】session_id=%s loaded_count=%s",
                session.session_id,
                summary_loaded_count,
            )
        else:
            for candidate in results:
                candidate["candidate_context"] = _build_candidate_context(candidate)

        # ✅ Agent Native 改进：移除性格特质增强逻辑
        # Tool 层只返回原始性格特质数据，Agent 自主决定如何使用
        # - 是否生成性格推荐理由？
        # - 是否根据性格匹配度排序？
        # - 这些决策在 Agent 层（Prompt）表达，不在 Tool 层硬编码

        # 保留 personality_trace 用于可观测性，但简化内容
        personality_trace["agent_native_mode"] = True
        personality_trace["note"] = "性格特质数据已返回，Agent 自主决定如何使用"
        response["personality_trace"] = personality_trace

        if user_traits_dict:
            response["user_personality_traits"] = user_traits.to_dict()

        # ✅ 可观测性增强：返回日志
        _logger.info(
            "【搜索返回】session_id=%s results_count=%s personality_traits_count=%s user_traits_available=%s",
            session.session_id,
            len(response.get("results") or []),
            personality_trace.get("candidate_traits_count"),
            bool(user_traits_dict),
        )

        return response
    except Exception as exc:  # noqa: BLE001
        # ✅ 可观测性增强：错误日志
        _logger.error(
            "【搜索失败】session_id=%s error=%s",
            session.session_id,
            str(exc)[:200],
        )
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


# def propose_requester_profile_update(
#     storage: Any,
#     session: StoredSession,
#     *,
#     patch: dict[str, Any],
#     evidence_text: str | None = None,
#     load_profile: Callable[..., Any] | None = None,
#     source: str | None = None,
#     now: datetime | None = None,
# ) -> dict[str, Any]:
#     profile_part, _, _ = split_persona_patch(patch)
#     if not profile_part:
#         return {
#             "proposed": False,
#             "error_code": "empty_profile_patch",
#             "message": "没有需要确认的资料字段。",
#         }
#     resolved_source = source if source is not None else profile_source()
#     current_profile = load_requester_profile_with(
#         session,
#         source=resolved_source,
#         load_profile=load_profile or load_self_profile,
#     )
#     return _propose_profile_update_impl(
#         storage,
#         session,
#         patch=profile_part,
#         evidence_text=evidence_text,
#         current_profile=current_profile,
#         now=now,
#     )


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
    """硬禁用：不执行任何写入逻辑

    禁用原因：验证方案文档的"不插手"理想设计是否可行

    禁用效果：
    - ✅ 不写入 working_criteria（search_part）
    - ✅ 不写入 user_personas（persona_part）
    - ✅ 不写入 profile_proposals（profile_part）
    - ✅ 完全不插手实时对话阶段

    验证目标：
    - Agent 自己是否能记住搜索条件？
    - 搜索结果是否仍然正确？
    - 会话结束后的画像沉淀是否正常？

    测试方式：真实前端测试，观察 Agent 行为和搜索结果
    """
    _logger.info("【硬禁用】sync_requester_persona_memory 已禁用，不执行任何写入逻辑")

    # 硬禁用：直接返回，不执行任何逻辑
    return {
        "synced": False,
        "error_code": "disabled_for_testing",
        "message": "硬禁用：验证方案文档的'不插手'理想设计",
        "test_mode": True,
        "user_key": str(session.requester_id),
        "session_id": session.session_id,
        "patch_received": dict(patch or {}),
    }
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


def suggest_assessment_with(
    profile_id: int,
    assessment_type: str,
    *,
    source: str | None = None,
) -> dict[str, Any]:
    """检查用户测评状态，返回引导卡片或性格信息。

    参数：
    - profile_id: 用户profile ID
    - assessment_type: 测评类型（mbti_16, attachment_style, big_five）
    - source: 数据源 DSN（可选，默认使用 persona_memory_source()）

    返回：
    - 已完成：返回用户性格类型信息
    - 未完成：返回测评引导卡片
    """
    # 1. 查询用户的性格特质
    resolved_source = source if source is not None else persona_memory_source()
    traits = load_traits_for_discovery(
        source=resolved_source,
        profile_id=profile_id,
    )

    # 2. 将 PersonalityTraitsContext 对象转换为字典
    #    （load_traits_for_discovery 返回的是对象，需要调用 .to_dict() 转换为字典）
    traits_dict = traits.to_dict() if traits else {}

    # 3. 检查是否已完成指定类型的测评
    if assessment_type == "mbti_16":
        mbti_type = str((traits_dict.get("mbti") or {}).get("type_code") or "").strip().upper()
        if mbti_type:
            # 已完成：返回性格信息
            return {
                "completed": True,
                "assessment_type": "mbti_16",
                "type_code": mbti_type,
                "summary": f"你是{mbti_type}型",
                "dimension_scores": dict((traits_dict.get("mbti") or {}).get("scores") or {}),
            }
        else:
            # 未完成：返回引导卡片
            return {
                "completed": False,
                "suggest": True,
                "assessment_type": "mbti_16",
                "card": {
                    "card_type": "assessment_suggest",
                    "assessment_type": "mbti_16",
                    "title": "MBTI性格测试",
                    "description": "了解你的性格类型，让匹配更精准",
                    "duration": "约5分钟",
                    "reward": "匹配准确度提升",
                    "action_label": "开始测评",
                    "action_id": "start_mbti_assessment",
                },
            }

    elif assessment_type == "attachment_style":
        attachment_type = str((traits_dict.get("attachment") or {}).get("type_code") or "").strip().lower()
        if attachment_type:
            return {
                "completed": True,
                "assessment_type": "attachment_style",
                "type_code": attachment_type,
                "summary": f"你的依恋风格是{attachment_type}型",
            }
        else:
            return {
                "completed": False,
                "suggest": True,
                "assessment_type": "attachment_style",
                "card": {
                    "card_type": "assessment_suggest",
                    "assessment_type": "attachment_style",
                    "title": "依恋风格测试",
                    "description": "了解你在亲密关系中的依恋模式",
                    "duration": "约3分钟",
                    "reward": "关系匹配更精准",
                    "action_label": "开始测评",
                    "action_id": "start_attachment_assessment",
                },
            }

    elif assessment_type == "big_five":
        big_five_data = dict(traits_dict.get("big_five") or {})
        scores = dict(big_five_data.get("scores") or {})

        # 检查是否有大五人格数据（至少3个维度有分数）
        valid_dimensions = 0
        for key in ("openness", "conscientiousness", "agreeableness", "neuroticism", "extraversion"):
            if _normalized_trait_score(scores.get(key)) is not None:
                valid_dimensions += 1

        if valid_dimensions >= 3:
            # 已完成：返回大五人格信息
            # 构建性格描述
            descriptions = []
            openness = _normalized_trait_score(scores.get("openness"))
            conscientiousness = _normalized_trait_score(scores.get("conscientiousness"))
            agreeableness = _normalized_trait_score(scores.get("agreeableness"))
            neuroticism = _normalized_trait_score(scores.get("neuroticism"))
            extraversion = _normalized_trait_score(scores.get("extraversion"))

            if openness is not None and openness >= 0.6:
                descriptions.append("开放性较高")
            if conscientiousness is not None and conscientiousness >= 0.6:
                descriptions.append("尽责性较高")
            if agreeableness is not None and agreeableness >= 0.6:
                descriptions.append("宜人性较高")
            if neuroticism is not None and neuroticism >= 0.6:
                descriptions.append("情绪敏感度较高")
            if extraversion is not None and extraversion >= 0.6:
                descriptions.append("外向性较高")

            summary = "你的性格特点：" + "、".join(descriptions[:3]) if descriptions else "你已完成大五人格测评"

            return {
                "completed": True,
                "assessment_type": "big_five",
                "summary": summary,
                "dimension_scores": scores,
                "dominant_traits": descriptions[:3],
            }
        else:
            # 未完成：返回引导卡片
            return {
                "completed": False,
                "suggest": True,
                "assessment_type": "big_five",
                "card": {
                    "card_type": "assessment_suggest",
                    "assessment_type": "big_five",
                    "title": "大五人格测试",
                    "description": "了解你的性格结构，让匹配更科学",
                    "duration": "约8分钟",
                    "reward": "性格匹配准确度提升",
                    "action_label": "开始测评",
                    "action_id": "start_big_five_assessment",
                },
            }

    # 硬约束：测评类型有效性校验
    supported_types = {"mbti_16", "attachment_style", "big_five"}
    if assessment_type not in supported_types:
        return {
            "completed": False,
            "suggest": False,
            "error": f"不支持的测评类型：{assessment_type}",
            "supported_types": list(supported_types),
        }

    # 默认返回：不支持的测评类型（兜底）
    return {"completed": False, "suggest": False}


__all__ = [
    "decision_payload",
    "load_persona_memory_bindings",
    "load_recommendation_bindings",
    "load_requester_profile",
    "open_recommendation_conn",
    "persona_memory_source",
    "persist_search_run",
    "profile_source",
    # "propose_requester_profile_update",  # 已注释：暂时禁用此工具
    "run_discovery_collect_then_search",
    "search_partner_candidates",
    "sync_requester_persona_memory",
    "suggest_assessment",
]
