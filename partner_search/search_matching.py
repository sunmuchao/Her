"""Core matching and scoring helpers for partner search."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Sequence

from partner_search.search_profile_utils import has_explicit_field_value as _has_explicit_field_value


@dataclass(frozen=True)
class SearchMatchingRuntime:
    as_int: Callable[[Any], int | None]
    as_lower: Callable[[Any], str]
    as_text: Callable[[Any], str]
    contains_any_text: Callable[[Any, Any], bool]
    normalize_bool: Callable[[Any], bool | None]
    normalize_acceptance_state: Callable[[Any], str]
    normalize_strictness_state: Callable[[Any], str]
    normalize_acceptance_strength: Callable[[Any], str]
    split_keywords: Callable[[Any], list[str]]
    unique_ordered: Callable[[Any], list[Any]]
    parse_income_range_to_wan: Callable[[Any], tuple[int | None, int | None]]
    effective_has_children: Callable[[dict[str, Any]], bool | None]
    effective_activity_datetime: Callable[[dict[str, Any]], datetime | None]
    education_rank: Callable[[Any], int | None]
    exact_match: Callable[[Any, Any], bool]
    match_any_exact: Callable[[Any, list[Any]], bool]
    keyword_matches_record: Callable[[dict[str, Any], str], bool]
    extract_keyword_evidence: Callable[[dict[str, Any], str], str | None]
    evaluate_exclusion_keyword: Callable[[dict[str, Any], str], dict[str, Any]]
    evaluate_reciprocal_compatibility: Callable[..., dict[str, Any] | None]
    parse_rejection_reason: Callable[[Any], tuple[str, str]]
    build_rejection_reason: Callable[[Any, Any], str]
    verified_rank: Callable[[Any], int]
    profile_status_rank: Callable[[Any], int]
    photo_verification_level: Callable[[dict[str, Any]], str]
    photo_verification_rank: Callable[[Any], int]
    photo_verification_level_label: Callable[[Any], str]
    build_match_result: Callable[..., dict[str, Any]]
    record_ref: Callable[[dict[str, Any] | None], Any]
    build_profile_consistency_flags: Callable[[dict[str, Any]], list[str]]
    activity_score_info: Callable[[dict[str, Any]], tuple[int, str | None, datetime | None]]
    verified_score_info: Callable[[dict[str, Any]], tuple[int, str, int]]
    summarize_notes_for_result: Callable[..., str | None]
    requires_explicit_marital_acceptance: Callable[[dict[str, Any]], bool]
    requires_explicit_children_acceptance: Callable[[dict[str, Any]], bool]
    marital_status_match_options: Callable[[dict[str, Any]], list[str]]
    text_fields: Sequence[str]
    unknown_values: set[str]
    critical_missing_field_penalties: dict[str, int]
    self_profile_gap_penalties: dict[str, int]
    risk_flag_penalties: dict[str, int]
    relationship_goal_strength_bonus: dict[str, int]
    education_order: dict[str, int]
    busy_job_keywords: set[str]
    creative_job_patterns: Sequence[re.Pattern[str]]
    near_distance_priority_markers: Sequence[str]
    soft_concession_risk_flags: set[str]


def missing_field_penalty(runtime: SearchMatchingRuntime, field: str) -> int:
    return runtime.critical_missing_field_penalties.get(field, 0)


def self_profile_gap_penalty(runtime: SearchMatchingRuntime, field: str) -> int:
    return runtime.self_profile_gap_penalties.get(field, 0)


def risk_flag_penalty(runtime: SearchMatchingRuntime, risk_flag: str) -> int:
    if str(risk_flag).startswith("资料里提到“"):
        return 4
    return runtime.risk_flag_penalties.get(risk_flag, 0)


def location_semantics_risk_flags(
    runtime: SearchMatchingRuntime,
    record: dict[str, Any],
) -> list[str]:
    semantics = runtime.as_text(record.get("location_preference_semantics"))
    if not semantics:
        return []
    if re.search(r"(?:不接受|不考虑|不能接受|不想)[^，。；]{0,8}长期异地", semantics) or re.search(
        r"长期[^，。；]{0,8}异地[^，。；]{0,8}(?:不接受|不考虑|不行|免谈)",
        semantics,
    ):
        return ["对方不接受长期异地，需要确认落地计划"]
    if any(marker in semantics for marker in ("落地计划", "稳定留沪", "双城过渡", "短期异地")):
        return ["异地需要明确落地计划"]
    return []


def soft_preference_risk_flag(
    runtime: SearchMatchingRuntime,
    kind: str,
    strictness_state: str,
) -> str | None:
    del runtime
    if strictness_state == "reference":
        return None
    mapping = {
        "age": "对方年龄要求可能可放宽",
        "height": "对方身高要求可能可放宽",
        "education": "对方学历要求可能可放宽",
        "income": "对方收入要求可能可放宽",
    }
    return mapping.get(kind)


def self_preference_strictness(runtime: SearchMatchingRuntime, value: Any) -> str:
    if value is None or value == "":
        return "soft"
    return runtime.normalize_strictness_state(value)


def self_education_floor_risk_flag(
    runtime: SearchMatchingRuntime,
    self_profile: dict[str, Any],
    record: dict[str, Any],
) -> str | None:
    preferred_min = self_profile.get("preferred_education_min")
    if not preferred_min:
        return None

    required_rank = runtime.education_rank(preferred_min)
    candidate_rank = runtime.education_rank(record.get("education"))
    if required_rank is None or candidate_rank is None:
        return None
    if candidate_rank >= required_rank:
        return None

    strictness = self_preference_strictness(
        runtime,
        self_profile.get("preferred_education_strictness"),
    )
    if strictness == "hard":
        return "education_below_self_preference"
    return "学历没有完全卡进你的底线"


def keyword_requested(
    runtime: SearchMatchingRuntime,
    criteria: dict[str, Any],
    keywords: set[str],
) -> bool:
    joined = " ".join(criteria.get("must_have", []) + criteria.get("prefer", []))
    return runtime.contains_any_text(joined, keywords)


def creative_job_match(runtime: SearchMatchingRuntime, value: Any) -> bool:
    text = runtime.as_text(value)
    if not text:
        return False
    return any(pattern.search(text) for pattern in runtime.creative_job_patterns)


def candidate_income_bounds(
    runtime: SearchMatchingRuntime,
    record: dict[str, Any],
) -> tuple[int | None, int | None]:
    income_min = runtime.as_int(record.get("income_min_wan"))
    income_max = runtime.as_int(record.get("income_max_wan"))
    if income_min is not None or income_max is not None:
        return income_min, income_max
    return runtime.parse_income_range_to_wan(record.get("income_range"))


def marital_acceptance_risk_flag(
    runtime: SearchMatchingRuntime,
    strength: str,
    semantics: Any,
) -> str | None:
    semantics_text = runtime.as_text(semantics)
    if runtime.contains_any_text(semantics_text, {"先聊再判断", "先接触再判断"}):
        return "对方婚史接受需要先聊再判断"
    if runtime.contains_any_text(semantics_text, {"更看具体", "相处质量"}):
        return "对方婚史接受度偏保守"
    if runtime.contains_any_text(semantics_text, {"态度未知"}):
        return "对方婚史接受度未知"
    if strength == "surface":
        return "对方婚史接受需要先聊再判断"
    if strength == "cautious":
        return "对方婚史接受度偏保守"
    if strength == "unknown":
        return "对方婚史接受度未知"
    return None


def children_acceptance_risk_flag(
    runtime: SearchMatchingRuntime,
    state: str,
    strength: str,
    semantics: Any,
) -> str | None:
    semantics_text = runtime.as_text(semantics)
    if runtime.contains_any_text(semantics_text, {"偏低", "偏保留"}):
        return "对方对子女接受度偏低"
    if runtime.contains_any_text(semantics_text, {"不太接受", "非常看具体"}):
        return "对方对子女接受度偏低"
    if runtime.contains_any_text(semantics_text, {"先接触再判断", "先聊再判断", "后续现实情况"}):
        return "对方对子女接受需要先接触再判断"
    if runtime.contains_any_text(semantics_text, {"更看具体"}):
        return "对方对子女接受度偏保守"
    if runtime.contains_any_text(semantics_text, {"态度未知"}):
        return "对方对子女接受度未知"

    if state == "accepted":
        if strength == "cautious":
            return "对方对子女接受度偏保守"
        if strength == "surface":
            return "对方对子女接受需要先接触再判断"
        if strength == "unknown":
            return "对方对子女接受度未知"
        return None

    if state == "negotiable":
        if strength == "cautious":
            return "对方对子女接受度偏低"
        if strength == "surface":
            return "对方对子女接受需要先接触再判断"
        return "对方对子女情况仅可协商"

    if state == "guarded":
        return "对方对子女接受度偏低"

    if state == "unknown":
        return "对方对子女接受度未知"
    return None


def reciprocal_city_preference_risk_flag(
    runtime: SearchMatchingRuntime,
    accept_long_distance_state: str,
    reciprocal_mode: str,
) -> str | None:
    del runtime
    if accept_long_distance_state == "accepted":
        return "对方城市偏好未命中，但资料写了接受异地"
    if accept_long_distance_state in {"negotiable", "guarded"}:
        return "对方城市偏好未命中，异地仅可协商"
    if reciprocal_mode == "fallback" and accept_long_distance_state in {"unknown", "missing"}:
        return "对方城市偏好未命中，异地接受度未知"
    return None


def self_prefers_near_distance(
    runtime: SearchMatchingRuntime,
    self_profile: dict[str, Any] | None,
) -> bool:
    if not self_profile:
        return False
    self_city = runtime.as_text(self_profile.get("city"))
    if not self_city:
        return False

    own_long_distance = runtime.normalize_acceptance_state(
        self_profile.get("accept_long_distance") or self_profile.get("long_distance")
    )
    if own_long_distance in {"rejected", "guarded"}:
        return True

    preferred_cities = runtime.split_keywords(self_profile.get("preferred_cities"))
    if preferred_cities and runtime.match_any_exact(self_city, preferred_cities):
        return True

    location_semantics = runtime.as_text(self_profile.get("location_preference_semantics"))
    return any(marker in location_semantics for marker in runtime.near_distance_priority_markers)


def concession_stack_risk_flag(
    runtime: SearchMatchingRuntime,
    risk_flags: list[str],
) -> str | None:
    concession_count = sum(
        1
        for flag in runtime.unique_ordered(risk_flags)
        if flag in runtime.soft_concession_risk_flags
    )
    if concession_count >= 3:
        return "多项条件需要放宽后才成立"
    return None


def evaluate_contextual_fit(
    runtime: SearchMatchingRuntime,
    record: dict[str, Any],
    criteria: dict[str, Any],
    self_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    self_profile = self_profile or {}
    reasons: list[str] = []
    risk_flags: list[str] = []
    match_evidence: list[str] = []
    score_bonus = 0

    interaction_comfort = record.get("interaction_comfort")
    patience_level = record.get("patience_level")
    life_texture = record.get("life_texture")
    career_intensity = record.get("career_intensity")
    exercise_habit = record.get("exercise_habit")
    growth_signal = record.get("growth_signal")
    warmth_style = record.get("warmth_style")
    aesthetic_expression = record.get("aesthetic_expression")
    conversation_resonance = record.get("conversation_resonance")
    personal_presence = record.get("personal_presence")
    lightness_humor = record.get("lightness_humor")
    consumption_attitude = record.get("consumption_attitude")
    chat_texture = record.get("chat_texture")
    commitment_clarity = record.get("commitment_clarity")
    relationship_execution = record.get("relationship_execution")
    blended_family_readiness = record.get("blended_family_readiness")
    communication_style = record.get("communication_style")
    dating_pace = record.get("dating_pace")
    expression_style = record.get("expression_style")
    notes_and_values = " ".join(
        str(record.get(field) or "") for field in ("notes", "values", "family_background")
    )
    steady_life_profile = (
        runtime.requires_explicit_marital_acceptance(self_profile)
        or runtime.requires_explicit_children_acceptance(self_profile)
        or keyword_requested(
            runtime,
            criteria,
            {"稳定踏实", "生活规律", "省心", "过日子", "相处舒服", "相处轻松", "简单舒服", "不累"},
        )
    )
    cares_about_regular_life = keyword_requested(runtime, criteria, {"生活规律", "生活稳定"})
    wants_proactive_communication = keyword_requested(runtime, criteria, {"主动沟通", "沟通"})
    cares_about_consumption = keyword_requested(
        runtime,
        criteria,
        {"消费观", "消费观正常", "不攀比", "过日子", "务实", "花钱观"},
    )
    cares_about_positive_energy = keyword_requested(runtime, criteria, {"乐观", "爱笑", "松弛"})

    if keyword_requested(runtime, criteria, {"有耐心", "慢热", "沟通", "会接话", "相处", "舒服", "不累"}):
        if interaction_comfort in {"相处轻松", "安静低压", "有边界不拧巴"}:
            reasons.append("相处压力更小")
            score_bonus += 4
            match_evidence.append(f"相处压力更小 <- 相处状态: {interaction_comfort}")
        if patience_level in {"高耐心", "耐心稳定"}:
            reasons.append("耐心更匹配")
            score_bonus += 4
            match_evidence.append(f"耐心更匹配 <- 耐心程度: {patience_level}")
        elif patience_level == "节奏偏快":
            risk_flags.append("相处节奏可能偏赶")
        if expression_style == "理性克制" and communication_style == "理性直接":
            risk_flags.append("相处可能偏冷")
        if warmth_style == "有温度会接话":
            reasons.append("聊天温度更舒服")
            score_bonus += 4
            match_evidence.append(f"聊天温度更舒服 <- 聊天温度: {warmth_style}")
        elif warmth_style == "理性但不冷":
            reasons.append("理性但不冷")
            score_bonus += 3
            match_evidence.append(f"理性但不冷 <- 聊天温度: {warmth_style}")
        elif warmth_style == "偏克制":
            risk_flags.append("聊天温度偏冷")
        if conversation_resonance == "会接话也会接情绪":
            reasons.append("聊天更容易有来有回")
            score_bonus += 4
            match_evidence.append(f"聊天更容易有来有回 <- 聊天共鸣: {conversation_resonance}")

    if keyword_requested(runtime, criteria, {"边界", "边界感", "理性直接"}):
        if interaction_comfort == "有边界不拧巴":
            reasons.append("边界清楚不拧巴")
            score_bonus += 4
            match_evidence.append(f"边界清楚不拧巴 <- 相处状态: {interaction_comfort}")

    if keyword_requested(runtime, criteria, {"生活规律", "爱运动", "健身", "乐观"}):
        if cares_about_regular_life and record.get("life_routine") in {"生活规律", "生活稳定"}:
            reasons.append("生活节奏更稳")
            score_bonus += 3
            match_evidence.append(f"生活节奏更稳 <- 作息类型: {record.get('life_routine')}")
        if exercise_habit == "规律运动":
            reasons.append("运动习惯更匹配")
            score_bonus += 5
            match_evidence.append(f"运动习惯更匹配 <- 运动习惯: {exercise_habit}")
        elif exercise_habit == "轻运动":
            reasons.append("生活状态更合拍")
            score_bonus += 3
            match_evidence.append(f"生活状态更合拍 <- 运动习惯: {exercise_habit}")
        if cares_about_positive_energy:
            if warmth_style == "有温度会接话":
                reasons.append("相处更有正反馈")
                score_bonus += 3
                match_evidence.append(f"相处更有正反馈 <- 聊天温度: {warmth_style}")
            elif warmth_style == "理性但不冷":
                reasons.append("情绪反馈更稳定")
                score_bonus += 2
                match_evidence.append(f"情绪反馈更稳定 <- 聊天温度: {warmth_style}")
            if lightness_humor == "有点幽默不端着":
                reasons.append("相处更有松弛感")
                score_bonus += 4
                match_evidence.append(f"相处更有松弛感 <- 轻松感: {lightness_humor}")
            elif lightness_humor == "稳重有分寸":
                reasons.append("相处更稳定不内耗")
                score_bonus += 2
                match_evidence.append(f"相处更稳定不内耗 <- 轻松感: {lightness_humor}")
            elif lightness_humor == "偏克制":
                risk_flags.append("乐观外放感偏弱")

    self_education_rank = runtime.education_rank(self_profile.get("education"))
    self_income_max = runtime.as_int(self_profile.get("income_max_wan"))
    candidate_education_rank = runtime.education_rank(record.get("education"))
    _, candidate_income_max = candidate_income_bounds(runtime, record)
    high_bar_profile = (
        (self_education_rank is not None and self_education_rank >= runtime.education_order["硕士"])
        or (self_income_max is not None and self_income_max >= 50)
    )
    wants_expressive_resonance = high_bar_profile or keyword_requested(
        runtime,
        criteria,
        {
            "见识",
            "表达",
            "审美",
            "共同兴趣",
            "情绪回应",
            "生活感",
            "会聊天",
            "会接话",
            "接话",
            "人物感",
            "上头",
            "火花",
            "不板正",
            "不端着",
            "聊天趣味",
            "聊天不累",
        },
    )

    if self_education_rank is not None and self_education_rank >= runtime.education_order["硕士"]:
        if candidate_education_rank is not None:
            if candidate_education_rank >= max(runtime.education_order["硕士"], self_education_rank - 1):
                reasons.append("学历层次更接近")
                score_bonus += 5
                match_evidence.append(f"学历层次更接近 <- 学历: {record.get('education')}")
                if (
                    self_education_rank >= runtime.education_order["博士"]
                    and candidate_education_rank >= runtime.education_order["博士"]
                ):
                    reasons.append("认知层次更对位")
                    score_bonus += 4
                    match_evidence.append(f"认知层次更对位 <- 学历: {record.get('education')}")
            elif (
                self_education_rank >= runtime.education_order["博士"]
                and candidate_education_rank <= runtime.education_order["本科"]
            ):
                risk_flags.append("生活阶段可能有落差")

    if self_income_max is not None and self_income_max >= 60 and candidate_income_max is not None:
        if candidate_income_max >= max(32, int(self_income_max * 0.45)):
            reasons.append("生活阶段更接近")
            score_bonus += 6
            match_evidence.append(f"生活阶段更接近 <- 收入范围: {record.get('income_range')}")
        elif candidate_income_max < max(26, int(self_income_max * 0.4)):
            risk_flags.append("生活阶段可能有落差")

    if cares_about_consumption or high_bar_profile:
        if consumption_attitude == "清醒务实":
            reasons.append("过日子观念更稳")
            score_bonus += 5
            match_evidence.append(f"过日子观念更稳 <- 消费观锚点: {consumption_attitude}")
        elif consumption_attitude == "有取舍会生活":
            reasons.append("生活方式更有分寸")
            score_bonus += 4
            match_evidence.append(f"生活方式更有分寸 <- 消费观锚点: {consumption_attitude}")
        elif consumption_attitude == "踏实过日子":
            reasons.append("过日子状态更踏实")
            score_bonus += 3
            match_evidence.append(f"过日子状态更踏实 <- 消费观锚点: {consumption_attitude}")
        elif cares_about_consumption and consumption_attitude == "表达不明显":
            risk_flags.append("消费观还不够具体")

    if wants_expressive_resonance:
        if wants_proactive_communication:
            if communication_style == "主动沟通":
                reasons.append("沟通更主动")
                score_bonus += 4
                match_evidence.append(f"沟通更主动 <- 沟通风格: {communication_style}")
            elif communication_style == "稳定沟通":
                reasons.append("沟通节奏更稳")
                score_bonus += 2
                match_evidence.append(f"沟通节奏更稳 <- 沟通风格: {communication_style}")
            elif communication_style == "慢热少话":
                risk_flags.append("主动沟通感偏弱")
        if warmth_style == "有温度会接话":
            reasons.append("理性之外也有温度")
            score_bonus += 4
            match_evidence.append(f"理性之外也有温度 <- 聊天温度: {warmth_style}")
        elif warmth_style == "理性但不冷":
            reasons.append("理性但不端着")
            score_bonus += 3
            match_evidence.append(f"理性但不端着 <- 聊天温度: {warmth_style}")
        elif warmth_style == "偏克制":
            risk_flags.append("聊天温度偏冷")
        if chat_texture == "有梗也有内容":
            reasons.append("聊天更有趣也更有内容")
            score_bonus += 5
            match_evidence.append(f"聊天更有趣也更有内容 <- 聊天质感: {chat_texture}")
        elif chat_texture == "顺着聊不费劲":
            reasons.append("聊天更顺，不容易累")
            score_bonus += 4
            match_evidence.append(f"聊天更顺，不容易累 <- 聊天质感: {chat_texture}")
        elif chat_texture == "稳重顺聊":
            reasons.append("聊天顺畅不拧巴")
            score_bonus += 3
            match_evidence.append(f"聊天顺畅不拧巴 <- 聊天质感: {chat_texture}")
        elif chat_texture == "偏功能聊天":
            risk_flags.append("聊天还像完成任务")
        if life_texture == "有见识也有生活感":
            reasons.append("资料不只稳，也更有生活感")
            score_bonus += 7
            match_evidence.append(f"资料不只稳，也更有生活感 <- 生活感层次: {life_texture}")
        elif life_texture == "有生活感":
            reasons.append("有生活感")
            score_bonus += 4
            match_evidence.append(f"有生活感 <- 生活感层次: {life_texture}")
        elif life_texture == "简单稳定":
            risk_flags.append("资料偏稳但不够鲜活")
        if aesthetic_expression == "有审美输出":
            reasons.append("更有审美和表达感")
            score_bonus += 6
            match_evidence.append(f"更有审美和表达感 <- 审美表达: {aesthetic_expression}")
        elif aesthetic_expression == "有生活审美":
            reasons.append("审美表达更顺眼")
            score_bonus += 3
            match_evidence.append(f"审美表达更顺眼 <- 审美表达: {aesthetic_expression}")
        elif aesthetic_expression == "普通":
            risk_flags.append("审美表达偏平")
        if conversation_resonance == "能聊想法也能聊日常":
            reasons.append("聊天层次更完整")
            score_bonus += 5
            match_evidence.append(f"聊天层次更完整 <- 聊天共鸣: {conversation_resonance}")
        elif conversation_resonance == "会接话也会接情绪":
            reasons.append("聊天不只对条件，也有情绪接住感")
            score_bonus += 4
            match_evidence.append(f"聊天不只对条件，也有情绪接住感 <- 聊天共鸣: {conversation_resonance}")
        elif conversation_resonance == "偏信息交换":
            risk_flags.append("聊天可能像信息交换")
        if personal_presence == "有记忆点":
            reasons.append("资料辨识度更高")
            score_bonus += 4
            match_evidence.append(f"资料辨识度更高 <- 人物感: {personal_presence}")
        elif personal_presence == "温和耐看":
            reasons.append("人物感更舒服")
            score_bonus += 3
            match_evidence.append(f"人物感更舒服 <- 人物感: {personal_presence}")
        elif personal_presence == "偏平":
            risk_flags.append("人物感偏淡")
        if lightness_humor == "有点幽默不端着":
            reasons.append("互动更轻松")
            score_bonus += 4
            match_evidence.append(f"互动更轻松 <- 轻松感: {lightness_humor}")
        elif lightness_humor == "稳重有分寸":
            reasons.append("稳重但不板正")
            score_bonus += 3
            match_evidence.append(f"稳重但不板正 <- 轻松感: {lightness_humor}")
        elif lightness_humor == "偏克制":
            risk_flags.append("聊天可能偏板正")

    if high_bar_profile or keyword_requested(runtime, criteria, {"成长", "势能", "事业", "大局观", "上进"}):
        if growth_signal == "上升明确":
            reasons.append("成长势能更强")
            score_bonus += 6
            match_evidence.append(f"成长势能更强 <- 事业势能: {growth_signal}")
        elif growth_signal == "平台成熟":
            reasons.append("发展阶段更成熟")
            score_bonus += 4
            match_evidence.append(f"发展阶段更成熟 <- 事业势能: {growth_signal}")
        elif high_bar_profile and growth_signal in {"稳定型", "未知"}:
            risk_flags.append("成长势能偏弱")

    if steady_life_profile:
        if career_intensity == "规律稳定":
            reasons.append("工作节奏更稳")
            score_bonus += 5
            match_evidence.append(f"工作节奏更稳 <- 工作节奏类型: {career_intensity}")
        elif career_intensity == "常规稳定":
            reasons.append("关系投入更省心")
            score_bonus += 3
            match_evidence.append(f"关系投入更省心 <- 工作节奏类型: {career_intensity}")
        elif career_intensity == "高强度但可协调":
            risk_flags.append("工作节奏偏忙，稳定投入要再看")

    self_job = self_profile.get("job")
    if self_job and runtime.contains_any_text(self_job, runtime.busy_job_keywords):
        if communication_style in {"主动沟通", "稳定沟通"} and dating_pace != "慢热推进":
            reasons.append("能配合忙碌节奏")
            score_bonus += 5
            match_evidence.append(
                f"能配合忙碌节奏 <- 沟通风格: {communication_style} | 推进节奏: {dating_pace}"
            )
        if career_intensity == "高强度但可协调":
            reasons.append("也能理解高强度工作")
            score_bonus += 3
            match_evidence.append(f"也能理解高强度工作 <- 工作节奏类型: {career_intensity}")
        elif communication_style == "慢热少话":
            risk_flags.append("忙的时候可能更难推进")

    if wants_expressive_resonance and creative_job_match(runtime, self_job) and creative_job_match(
        runtime,
        record.get("job"),
    ):
        reasons.append("审美和内容语境更接近")
        score_bonus += 6
        match_evidence.append(f"审美和内容语境更接近 <- 职业: {record.get('job')}")

    needs_explicit_family_reality = runtime.requires_explicit_children_acceptance(
        self_profile
    ) or keyword_requested(runtime, criteria, {"接受孩子现实", "孩子现实", "现实承接", "再婚现实"})
    if needs_explicit_family_reality:
        if blended_family_readiness == "已想过现实安排":
            reasons.append("现实安排想得更具体")
            score_bonus += 5
            match_evidence.append(f"现实安排想得更具体 <- 现实承接度: {blended_family_readiness}")
        elif blended_family_readiness == "愿意一起商量":
            reasons.append("现实问题愿意一起商量")
            score_bonus += 2
            match_evidence.append(f"现实问题愿意一起商量 <- 现实承接度: {blended_family_readiness}")
        elif blended_family_readiness in {"仅口头接受", "未知", None, ""}:
            risk_flags.append("重组家庭现实承接仍需确认")
        if runtime.requires_explicit_children_acceptance(self_profile) and runtime.contains_any_text(
            notes_and_values,
            {"婚史", "再婚", "现实安排", "家里相处", "边界", "为什么结束"},
        ):
            reasons.append("复杂现实问题愿意提前讲清")
            score_bonus += 3
            match_evidence.append("复杂现实问题愿意提前讲清 <- 备注/价值观提到了现实安排")

    relationship_goals = set(criteria.get("relationship_goals") or [])
    wants_steady_relationship = (
        "认真恋爱" in relationship_goals
        or "结婚导向" in relationship_goals
        or keyword_requested(runtime, criteria, {"认真相处", "稳定投入关系", "认真推进"})
    )
    wants_clear_long_term = (
        "结婚导向" in relationship_goals
        or keyword_requested(runtime, criteria, {"稳定投入关系", "认真推进", "结婚", "长期"})
        or runtime.as_int(self_profile.get("age")) is not None
        and runtime.as_int(self_profile.get("age")) >= 29
    )
    if wants_steady_relationship and not wants_clear_long_term:
        if commitment_clarity == "明确奔着长期":
            reasons.append("认真相处意愿更明确")
            score_bonus += 4
            match_evidence.append(f"认真相处意愿更明确 <- 长期意图明确度: {commitment_clarity}")
        elif commitment_clarity == "愿意稳定推进":
            reasons.append("认真相处预期更清楚")
            score_bonus += 2
            match_evidence.append(f"认真相处预期更清楚 <- 长期意图明确度: {commitment_clarity}")
        if relationship_execution == "会把安排说清":
            reasons.append("认真相处不拖泥带水")
            score_bonus += 4
            match_evidence.append(f"认真相处不拖泥带水 <- 现实推进方式: {relationship_execution}")
        elif relationship_execution == "稳步推进不拖拉":
            reasons.append("认真相处节奏更稳")
            score_bonus += 2
            match_evidence.append(f"认真相处节奏更稳 <- 现实推进方式: {relationship_execution}")
        elif relationship_execution == "口头长期待验证":
            risk_flags.append("认真相处信号还不够落地")
        elif relationship_execution == "先聊熟再定":
            risk_flags.append("认真相处推进偏慢")
    if wants_clear_long_term:
        if commitment_clarity == "明确奔着长期":
            reasons.append("进入关系意愿更明确")
            score_bonus += 5
            match_evidence.append(f"进入关系意愿更明确 <- 长期意图明确度: {commitment_clarity}")
        elif commitment_clarity == "愿意稳定推进":
            reasons.append("长期推进预期更清楚")
            score_bonus += 3
            match_evidence.append(f"长期推进预期更清楚 <- 长期意图明确度: {commitment_clarity}")
        elif commitment_clarity == "先聊熟再说":
            risk_flags.append("进入关系信号偏弱")
        if relationship_execution == "会把安排说清":
            reasons.append("推进方式更落地")
            score_bonus += 5
            match_evidence.append(f"推进方式更落地 <- 现实推进方式: {relationship_execution}")
        elif relationship_execution == "稳步推进不拖拉":
            reasons.append("推进节奏更踏实")
            score_bonus += 3
            match_evidence.append(f"推进节奏更踏实 <- 现实推进方式: {relationship_execution}")
        elif relationship_execution == "口头长期待验证":
            risk_flags.append("长期意图有，但推进方式还不够落地")
        elif relationship_execution == "先聊熟再定":
            risk_flags.append("推进方式偏慢观察")

    if (
        high_bar_profile
        and conversation_resonance == "能聊想法也能聊日常"
        and personal_presence == "有记忆点"
        and aesthetic_expression in {"有审美输出", "有生活审美"}
    ):
        reasons.append("条件之外，表达层次也更完整")
        score_bonus += 4
        match_evidence.append("条件之外，表达层次也更完整 <- 聊天共鸣/人物感/审美表达组合更完整")
    if (
        high_bar_profile
        and lightness_humor == "有点幽默不端着"
        and conversation_resonance == "能聊想法也能聊日常"
    ):
        reasons.append("互动不容易太板正")
        score_bonus += 3
        match_evidence.append("互动不容易太板正 <- 轻松感/聊天共鸣更完整")

    return {
        "matched_on": reasons,
        "risk_flags": risk_flags,
        "match_evidence": match_evidence,
        "score_bonus": score_bonus,
        "missing_fields": [],
    }


def has_explicit_field_value(
    runtime: SearchMatchingRuntime,
    record: dict[str, Any],
    field: str,
) -> bool:
    return _has_explicit_field_value(runtime, record, field)


def build_follow_up_questions(
    runtime: SearchMatchingRuntime,
    record: dict[str, Any],
    missing_fields: list[str],
    risk_flags: list[str],
    self_profile: dict[str, Any] | None = None,
) -> list[str]:
    questions: list[str] = []
    self_profile = self_profile or {}
    candidate_city = record.get("city")
    self_city = self_profile.get("city")

    for field in runtime.unique_ordered(missing_fields):
        if field == "smoking":
            questions.append("确认是否抽烟，以及频率如何。")
        elif field == "drinking":
            questions.append("确认是否喝酒，以及频率和场景。")
        elif field == "long_distance":
            questions.append("确认是否接受异地，以及多远算异地。")
        elif field == "settlement_city":
            questions.append("确认长期打算定居在哪个城市。")
        elif field == "marital_status":
            questions.append("确认当前婚况是否与你预期一致。")
        elif field == "want_children":
            questions.append("确认未来是否想要孩子，以及时间安排。")
        elif field == "marriage_timeline":
            questions.append("确认结婚节奏，是1年内推进还是合适再定。")
        elif field == "accept_partner_children":
            questions.append("确认是否能长期接受伴侣已有孩子，以及现实安排怎么想。")
        elif field == "accept_partner_children_semantics":
            questions.append("确认对方对子女情况到底是能接受，还是只是态度偏保留。")
        elif field == "accept_marital_status":
            questions.append("确认是否真的接受你的婚史，而不是表面上说可以。")
        elif field == "accept_marital_status_semantics":
            questions.append("确认对方对婚史是明确接受，还是要看具体人和相处质量。")
        elif field == "accept_smoking":
            questions.append("确认是否真的接受伴侣抽烟，而不是先聊着再说。")
        elif field == "accept_drinking":
            questions.append("确认是否真的接受伴侣偶尔喝酒。")
        elif field == "accept_long_distance":
            if self_city and candidate_city and runtime.as_lower(self_city) != runtime.as_lower(candidate_city):
                questions.append("确认异地是否能长期接受，以及见面频率怎么安排。")
        elif field == "life_routine":
            questions.append("确认平时作息到底稳不稳，工作日和周末差别大不大。")
        elif field == "communication_style":
            questions.append("确认沟通频率和方式，遇到问题是当下聊还是闷着。")
        elif field == "dating_pace":
            questions.append("确认推进节奏，是慢热观察型还是想尽快认真推进。")
        elif field == "expression_style":
            questions.append("确认对方是不是会表达、有生活感，聊天会不会太干。")
        elif field == "relationship_capacity":
            questions.append("确认对方现在有没有稳定投入关系的时间和精力。")
        elif field == "interaction_comfort":
            questions.append("确认相处会不会累，遇到分歧时是能聊开还是会绷着。")
        elif field == "patience_level":
            questions.append("确认对方耐心够不够，推进时会不会容易着急。")
        elif field == "life_texture":
            questions.append("确认对方是不是只有稳定条件，还是生活里也有表达和趣味。")
        elif field == "career_intensity":
            questions.append("确认工作节奏到底有多忙，关系里能不能稳定投入。")
        elif field == "exercise_habit":
            questions.append("确认有没有稳定运动或身体管理习惯。")
        elif field == "growth_signal":
            questions.append("确认对方现在是稳定型，还是还在明显上升期。")
        elif field == "warmth_style":
            questions.append("确认聊天有没有温度，还是只是礼貌理性地回复。")
        elif field == "aesthetic_expression":
            questions.append("确认对方是不是有自己的审美和表达，不只是资料写得漂亮。")
        elif field == "blended_family_readiness":
            questions.append("确认对方有没有认真想过离异带娃后的现实安排，而不是只说可以。")
        elif field == "consumption_attitude":
            questions.append("确认对方花钱更看重什么，是清醒务实，还是容易被外在包装带着走。")
        elif field == "chat_texture":
            questions.append("确认对方聊天是顺着聊不费劲，还是容易只剩条件交换。")
        elif field == "relationship_execution":
            questions.append("确认对方认真推进时，会不会把见面节奏、关系预期和现实安排说清。")

    for risk in runtime.unique_ordered(risk_flags):
        if risk == "对方对子女情况仅可协商":
            questions.append("确认对方是能真正接受你有孩子，还是只是暂时不想说死。")
        elif risk == "对方对子女接受度偏低":
            questions.append("确认对方对子女情况是不是现实里会比较难接受，不要只看口头上没拒绝。")
        elif risk == "对方对子女接受需要先接触再判断":
            questions.append("确认对方对子女情况是不是只有接触意愿，真到关系推进时会不会犹豫。")
        elif risk == "对方城市偏好未命中，但资料写了接受异地":
            questions.append("确认城市不是对方的硬门槛，异地或跨城推进在现实里怎么落地。")
        elif risk == "对方城市偏好未命中，异地仅可协商":
            questions.append("确认城市偏好没命中时，对方是不是只是嘴上可协商，现实里会不会很快卡住。")
        elif risk == "对方城市偏好未命中，异地接受度未知":
            questions.append("确认城市偏好没命中的情况下，对方到底能不能接受跨城推进。")
        elif risk == "对方不接受长期异地，需要确认落地计划":
            questions.append("确认对方能接受的是短期过渡，还是只要长期异地就会卡住，以及落地计划怎么定。")
        elif risk == "异地需要明确落地计划":
            questions.append("确认跨城推进有没有明确落地计划，不要只停留在原则上可以。")
        elif risk == "非同城，见面推进成本更高":
            questions.append("确认见面频率、通勤成本和落地安排，不要默认跨城也能自然推进。")
        elif risk == "对方对喝酒仅可协商":
            questions.append("确认偶尔喝酒在对方那里是能接受，还是只是勉强可协商。")
        elif risk == "对方对抽烟仅可协商":
            questions.append("确认抽烟问题是不是对方的硬雷点。")
        elif risk == "对方异地仅可协商":
            questions.append("确认异地推进的底线和可执行方式，不要只停留在口头可协商。")
        elif risk == "90天前活跃":
            questions.append("确认对方现在是否还在认真相亲，以及回复节奏是否稳定。")
        elif risk == "对方年龄要求可能可放宽":
            questions.append("确认年龄差在对方那里到底是不是硬门槛，别一上来就自我淘汰。")
        elif risk == "对方身高要求可能可放宽":
            questions.append("确认身高条件是硬卡，还是聊得来可以放宽。")
        elif risk == "对方学历要求可能可放宽":
            questions.append("确认学历要求是不是死卡，还是更看实际认知和相处。")
        elif risk == "对方收入要求可能可放宽":
            questions.append("确认对方在意的是收入数字，还是更在意生活方式和相处压力。")
        elif risk == "对方婚史接受度偏保守":
            questions.append("确认对方对婚史是长期能接受，还是只是暂时不想说死。")
        elif risk == "对方婚史接受需要先聊再判断":
            questions.append("确认对方对婚史是不是先聊了再说，后面会不会卡在现实接受度上。")
        elif risk == "对方婚史接受度未知":
            questions.append("确认对方对婚史的接受到底有多明确，别只看到可接受范围。")
        elif risk == "对方对子女接受度偏保守":
            questions.append("确认对方能不能长期接受孩子和现实安排，不要只停留在口头上。")
        elif risk == "学历没有完全卡进你的底线":
            questions.append("确认学历底线是不是只作参考，不然明显低于预期的人不该排到前面。")
        elif risk == "生活阶段可能有落差":
            questions.append("确认你们的收入压力、消费方式和长期生活节奏是不是一个频道。")
        elif risk == "资料偏稳但不够鲜活":
            questions.append("确认对方是不是只有条件合适，还是聊天和生活里也真的有感觉。")
        elif risk == "相处可能偏冷":
            questions.append("确认对方理性之外有没有温度，聊天会不会太端着。")
        elif risk == "相处节奏可能偏赶":
            questions.append("确认推进会不会太快，会不会让你有压力。")
        elif risk == "忙的时候可能更难推进":
            questions.append("确认工作忙时的沟通和见面安排能不能稳定下来。")
        elif risk == "工作节奏偏忙，稳定投入要再看":
            questions.append("确认对方工作到底有多忙，周中回复和见面能不能稳定。")
        elif risk == "主动沟通感偏弱":
            questions.append("确认对方是慢热还是低反馈，别聊着聊着只剩你一个人在推进。")
        elif risk == "乐观外放感偏弱":
            questions.append("确认对方是稳定安静型，还是实际相处里会偏闷、偏没劲。")
        elif risk == "消费观还不够具体":
            questions.append("确认对方的消费观到底是清醒务实，还是只是资料里泛泛写正常。")
        elif risk == "聊天还像完成任务":
            questions.append("确认对方聊天是不是容易只讲条件和流程，还是能把话题真正聊活。")
        elif risk == "认真相处信号还不够落地":
            questions.append("确认对方是不是只说想认真相处，还是会真的把见面和节奏往前推。")
        elif risk == "认真相处推进偏慢":
            questions.append("确认对方是稳一点，还是会把认真相处一直拖在观察阶段。")
        elif risk == "长期意图有，但推进方式还不够落地":
            questions.append("确认对方不是只会说想长期，而是真的会把推进节奏和安排说清。")
        elif risk == "多项条件需要放宽后才成立":
            questions.append("确认这段匹配到底是少数几个点不完美，还是很多关键条件都要靠放宽才行。")
        elif risk == "推进方式偏慢观察":
            questions.append("确认对方是慢热但会往前走，还是会一直停在观察阶段。")
        elif risk == "成长势能偏弱":
            questions.append("确认对方接下来几年是继续往上走，还是更偏稳定守成。")
        elif risk == "聊天温度偏冷":
            questions.append("确认对方是不是只在资料里理性，实际聊天会不会太冷。")
        elif risk == "审美表达偏平":
            questions.append("确认对方有没有自己的生活审美和表达，而不是只有基础条件。")
        elif risk == "聊天可能像信息交换":
            questions.append("确认对方聊天是不是只在交换条件和流程，还是能真正聊出共鸣。")
        elif risk == "人物感偏淡":
            questions.append("确认对方除了条件在线，有没有让你记住和想继续了解的点。")
        elif risk == "聊天可能偏板正":
            questions.append("确认对方是不是太稳太克制，实际聊天会不会少一点轻松感和火花。")
        elif risk == "进入关系信号偏弱":
            questions.append("确认对方到底是明确奔着长期来，还是只是先聊着看感觉。")
        elif risk == "重组家庭现实承接仍需确认":
            questions.append("确认对方有没有具体想过孩子、时间和家庭安排，不要只停留在口头接受。")
        elif risk.startswith("资料里提到“"):
            keyword = str(risk).removeprefix("资料里提到“").split("”", 1)[0]
            questions.append(f"确认对方提到“{keyword}”是在表达边界，还是现实里真的会出现这类问题。")

    return runtime.unique_ordered(questions)[:5]


def evaluate_candidate(
    runtime: SearchMatchingRuntime,
    record: dict[str, Any],
    criteria: dict[str, Any],
    diagnostics: bool = False,
    reciprocal_mode: str = "strict",
) -> dict[str, Any] | None:
    def fail(reason: str, detail: Any = None) -> dict[str, Any] | None:
        if not diagnostics:
            return None
        activity_dt = runtime.effective_activity_datetime(record)
        return runtime.build_match_result(
            record=record,
            score=0,
            fit_score=0,
            confidence_score=0,
            risk_score=0,
            matched_on=[],
            reciprocal_on=[],
            missing_fields=[],
            self_profile_gaps=[],
            risk_flags=[],
            match_evidence=[],
            follow_up_questions=[],
            verified_rank=runtime.verified_rank(record.get("verified_level")),
            activity_sort_ts=int(activity_dt.timestamp()) if activity_dt else 0,
            profile_status_rank=runtime.profile_status_rank(record.get("profile_status")),
            matched=False,
            reject_reason=runtime.build_rejection_reason(reason, detail),
        )

    reasons: list[str] = []
    reciprocal_reasons: list[str] = []
    missing_fields: list[str] = []
    risk_flags: list[str] = []
    match_evidence: list[str] = []
    fit_score = 0
    confidence_score = 0

    if runtime.record_ref(record) in criteria.get("exclude_record_refs", set()):
        return fail("exclude_record_ref")
    if runtime.as_int(record.get("id")) in criteria.get("exclude_ids", set()):
        return fail("exclude_id")
    source_channel = runtime.as_lower(record.get("source_channel"))
    if source_channel and source_channel in criteria.get("exclude_source_channels", set()):
        return fail("exclude_source_channel")

    profile_status = record.get("profile_status")
    allowed_statuses = criteria.get("profile_statuses") or ["active"]
    if not profile_status:
        missing_fields.append("profile_status")
    else:
        if not runtime.match_any_exact(profile_status, allowed_statuses):
            return fail("profile_status_mismatch")
        reasons.append(f"状态 {profile_status}")
        confidence_score += 4

    active_at = runtime.effective_activity_datetime(record)
    if criteria.get("active_within_days") is not None:
        if active_at is None:
            missing_fields.append("last_active_at")
            return fail("active_time_missing")
        if active_at < datetime.now() - timedelta(days=criteria["active_within_days"]):
            return fail("active_too_old")

    if criteria.get("verified_level_min"):
        if runtime.verified_rank(record.get("verified_level")) < runtime.verified_rank(
            criteria["verified_level_min"]
        ):
            return fail("verified_below_min")

    if criteria.get("photo_verification_level_min"):
        if runtime.photo_verification_rank(runtime.photo_verification_level(record)) < runtime.photo_verification_rank(
            criteria["photo_verification_level_min"]
        ):
            return fail("photo_verification_below_min")

    age = record.get("age")
    if criteria.get("age_min") is not None:
        if age is None:
            missing_fields.append("age")
        elif age < criteria["age_min"]:
            return fail("age_below_min")
        else:
            reasons.append(f"年龄 {age}")
            fit_score += 15
    if criteria.get("age_max") is not None:
        if age is None:
            if "age" not in missing_fields:
                missing_fields.append("age")
        elif age > criteria["age_max"]:
            return fail("age_above_max")

    height = record.get("height")
    height_reason_added = False
    if criteria.get("height_min") is not None:
        if height is None:
            missing_fields.append("height")
        elif height < criteria["height_min"]:
            return fail("height_below_min")
        else:
            reasons.append(f"身高 {height}cm")
            height_reason_added = True
            fit_score += 5
    if criteria.get("height_max") is not None:
        if height is None:
            if "height" not in missing_fields:
                missing_fields.append("height")
        elif height > criteria["height_max"]:
            return fail("height_above_max")
        elif not height_reason_added:
            reasons.append(f"身高 {height}cm")
            height_reason_added = True

    if criteria.get("gender"):
        gender = runtime.as_lower(record.get("gender"))
        if not gender:
            missing_fields.append("gender")
        elif gender != criteria["gender"]:
            return fail("gender_mismatch")
        else:
            reasons.append(f"性别 {record.get('gender')}")
            fit_score += 10

    if criteria.get("cities"):
        city = runtime.as_lower(record.get("city"))
        if not city:
            missing_fields.append("city")
        elif city not in [runtime.as_lower(item) for item in criteria["cities"]]:
            return fail("city_mismatch")
        else:
            reasons.append(f"城市 {record.get('city')}")
            fit_score += 20

    self_profile = criteria.get("self_profile") or {}
    self_city = self_profile.get("city")
    candidate_city = record.get("city")
    near_distance_priority = self_prefers_near_distance(runtime, self_profile)
    if self_city and candidate_city and runtime.as_lower(self_city) == runtime.as_lower(candidate_city):
        reasons.append("同城")
        fit_score += 8
        if near_distance_priority:
            reasons.append("近距离更省心")
            fit_score += 4
    elif self_city and candidate_city and near_distance_priority:
        risk_flags.append("非同城，见面推进成本更高")

    if criteria.get("districts"):
        district = runtime.as_lower(record.get("district"))
        if not district:
            missing_fields.append("district")
        elif district not in [runtime.as_lower(item) for item in criteria["districts"]]:
            return fail("district_mismatch")
        else:
            reasons.append(f"区域 {record.get('district')}")
            fit_score += 8

    if criteria.get("settlement_cities"):
        settlement_city = runtime.as_lower(record.get("settlement_city"))
        if not settlement_city:
            missing_fields.append("settlement_city")
        elif settlement_city not in [runtime.as_lower(item) for item in criteria["settlement_cities"]]:
            return fail("settlement_city_mismatch")
        else:
            reasons.append(f"定居 {record.get('settlement_city')}")
            fit_score += 8
    elif self_city and record.get("settlement_city") and runtime.as_lower(record.get("settlement_city")) == runtime.as_lower(
        self_city
    ):
        reasons.append("定居与你同城")
        fit_score += 4

    if criteria.get("relationship_goals"):
        goal = runtime.as_lower(record.get("relationship_goal"))
        if not goal:
            missing_fields.append("relationship_goal")
        elif goal not in [runtime.as_lower(item) for item in criteria["relationship_goals"]]:
            return fail("relationship_goal_mismatch")
        else:
            reasons.append(f"目标 {record.get('relationship_goal')}")
            fit_score += 15
            fit_score += runtime.relationship_goal_strength_bonus.get(record.get("relationship_goal"), 0)

    if criteria.get("must_have"):
        for keyword in criteria["must_have"]:
            if not runtime.keyword_matches_record(record, keyword):
                return fail("must_have_missing", keyword)
            reasons.append(f"包含 {keyword}")
            fit_score += 8
            evidence = runtime.extract_keyword_evidence(record, keyword)
            if evidence:
                match_evidence.append(f"{keyword} <- {evidence}")

    if criteria.get("must_not_have"):
        for keyword in criteria["must_not_have"]:
            exclusion = runtime.evaluate_exclusion_keyword(record, keyword)
            if exclusion["blocked"]:
                return fail("must_not_have_hit", keyword)
            if exclusion.get("risk_flag"):
                risk_flags.append(exclusion["risk_flag"])

    matched_prefer_count = 0
    for keyword in criteria.get("prefer", []):
        if runtime.keyword_matches_record(record, keyword):
            reasons.append(f"偏好命中 {keyword}")
            fit_score += 6
            matched_prefer_count += 1
            evidence = runtime.extract_keyword_evidence(record, keyword)
            if evidence:
                match_evidence.append(f"{keyword} <- {evidence}")

    if matched_prefer_count >= 3:
        fit_score += 4
    elif matched_prefer_count >= 2:
        fit_score += 2

    self_education_risk = self_education_floor_risk_flag(
        runtime,
        criteria.get("self_profile") or {},
        record,
    )
    if self_education_risk == "education_below_self_preference":
        return fail("education_below_self_preference")
    if self_education_risk:
        risk_flags.append(self_education_risk)

    if criteria.get("smoking"):
        smoking = runtime.as_lower(record.get("smoking"))
        desired = runtime.as_lower(criteria["smoking"])
        if not smoking:
            missing_fields.append("smoking")
        elif smoking != desired:
            return fail("smoking_mismatch")
        else:
            if desired in {"否", "不抽烟", "不吸烟"}:
                reasons.append("不抽烟")
            else:
                reasons.append(f"抽烟习惯 {record.get('smoking')}")
            fit_score += 8

    if criteria.get("drinking"):
        drinking = runtime.as_lower(record.get("drinking"))
        desired = runtime.as_lower(criteria["drinking"])
        if not drinking:
            missing_fields.append("drinking")
        elif drinking != desired:
            return fail("drinking_mismatch")
        else:
            if desired in {"否", "不喝酒", "不饮酒"}:
                reasons.append("少酒/不喝酒")
            else:
                reasons.append(f"饮酒习惯 {record.get('drinking')}")
            fit_score += 5

    if criteria.get("long_distance"):
        long_distance = runtime.as_lower(record.get("long_distance"))
        desired = runtime.as_lower(criteria["long_distance"])
        if not long_distance:
            missing_fields.append("long_distance")
        elif long_distance != desired:
            return fail("long_distance_mismatch")
        else:
            reasons.append(f"异地态度 {record.get('long_distance')}")
            fit_score += 8

    if criteria.get("housing_statuses"):
        housing_status = record.get("housing_status")
        if not housing_status:
            missing_fields.append("housing_status")
        elif not runtime.match_any_exact(housing_status, criteria["housing_statuses"]):
            return fail("housing_status_mismatch")
        else:
            reasons.append(f"住房 {housing_status}")
            fit_score += 6

    if criteria.get("car_statuses"):
        car_status = record.get("car_status")
        if not car_status:
            missing_fields.append("car_status")
        elif not runtime.match_any_exact(car_status, criteria["car_statuses"]):
            return fail("car_status_mismatch")
        else:
            reasons.append(f"车辆 {car_status}")
            fit_score += 4

    if criteria.get("marital_statuses"):
        marital_status = record.get("marital_status")
        if not marital_status:
            missing_fields.append("marital_status")
        elif not any(
            runtime.match_any_exact(option, criteria["marital_statuses"])
            for option in runtime.marital_status_match_options(
                {"marital_status": marital_status, "has_children": record.get("has_children")}
            )
        ):
            return fail("marital_status_mismatch")
        else:
            reasons.append(f"婚况 {marital_status}")
            fit_score += 10

    if criteria.get("has_children") is not None:
        has_children = runtime.effective_has_children(record)
        if has_children is None:
            missing_fields.append("has_children")
        elif has_children != criteria["has_children"]:
            return fail("has_children_mismatch")
        else:
            reasons.append("子女情况命中")
            fit_score += 10

    if criteria.get("want_children"):
        want_children = record.get("want_children")
        if not want_children:
            missing_fields.append("want_children")
        elif not runtime.exact_match(want_children, criteria["want_children"]):
            return fail("want_children_mismatch")
        else:
            reasons.append(f"生育计划 {want_children}")
            fit_score += 8

    if criteria.get("accept_partner_children"):
        accept_partner_children = record.get("accept_partner_children")
        if not accept_partner_children:
            missing_fields.append("accept_partner_children")
        elif not runtime.exact_match(accept_partner_children, criteria["accept_partner_children"]):
            return fail("accept_partner_children_mismatch")
        else:
            reasons.append(f"接受对方孩子 {accept_partner_children}")
            fit_score += 6

    if criteria.get("accept_marital_status_strength"):
        marital_strength = record.get("accept_marital_status_strength")
        if not marital_strength:
            missing_fields.append("accept_marital_status_strength")
        elif not runtime.exact_match(marital_strength, criteria["accept_marital_status_strength"]):
            return fail("accept_marital_status_strength_mismatch")
        else:
            reasons.append(f"婚史接受真实度 {marital_strength}")
            fit_score += 5

    if criteria.get("accept_partner_children_strength"):
        children_strength = record.get("accept_partner_children_strength")
        if not children_strength:
            missing_fields.append("accept_partner_children_strength")
        elif not runtime.exact_match(children_strength, criteria["accept_partner_children_strength"]):
            return fail("accept_partner_children_strength_mismatch")
        else:
            reasons.append(f"对子女接受真实度 {children_strength}")
            fit_score += 5

    if criteria.get("marriage_timelines"):
        marriage_timeline = record.get("marriage_timeline")
        if not marriage_timeline:
            missing_fields.append("marriage_timeline")
        elif not runtime.match_any_exact(marriage_timeline, criteria["marriage_timelines"]):
            return fail("marriage_timeline_mismatch")
        else:
            reasons.append(f"结婚节奏 {marriage_timeline}")
            fit_score += 8

    if criteria.get("verified_levels"):
        verified_level = record.get("verified_level") or "none"
        if not runtime.match_any_exact(verified_level, criteria["verified_levels"]):
            return fail("verified_level_mismatch")
        reasons.append(f"认证 {verified_level}")
        confidence_score += 4

    if criteria.get("photo_verification_levels"):
        candidate_photo_level = runtime.photo_verification_level(record)
        if not runtime.match_any_exact(candidate_photo_level, criteria["photo_verification_levels"]):
            return fail("photo_verification_level_mismatch")
        reasons.append(f"照片核验 {runtime.photo_verification_level_label(candidate_photo_level)}")
        confidence_score += 3

    if criteria.get("photo_count_min") is not None:
        photo_count = runtime.as_int(record.get("photo_count"))
        if photo_count is None:
            missing_fields.append("photo_count")
        elif photo_count < criteria["photo_count_min"]:
            return fail("photo_count_too_low")
        else:
            reasons.append(f"照片 {photo_count}张")
            confidence_score += min(photo_count, 6)

    if not reasons:
        reasons.append("基础条件未提供，按资料完整度保留")

    reciprocal = runtime.evaluate_reciprocal_compatibility(
        record,
        criteria.get("self_profile"),
        diagnostics=diagnostics,
        reciprocal_mode=reciprocal_mode,
    )
    if reciprocal is None:
        return fail("reciprocal_mismatch")
    if not reciprocal.get("matched", True):
        parsed_reason = runtime.parse_rejection_reason(reciprocal.get("reject_reason"))
        return fail(parsed_reason[0], parsed_reason[1])
    reciprocal_reasons.extend(reciprocal["matched_on"])
    missing_fields.extend(reciprocal["missing_fields"])
    risk_flags.extend(reciprocal["risk_flags"])
    fit_score += reciprocal["score_bonus"]

    contextual_fit = evaluate_contextual_fit(
        runtime,
        record,
        criteria,
        self_profile=criteria.get("self_profile"),
    )
    reasons.extend(contextual_fit["matched_on"])
    missing_fields.extend(contextual_fit["missing_fields"])
    risk_flags.extend(contextual_fit["risk_flags"])
    match_evidence.extend(contextual_fit["match_evidence"])
    fit_score += contextual_fit["score_bonus"]

    stacked_concession_risk = concession_stack_risk_flag(runtime, risk_flags)
    if stacked_concession_risk:
        risk_flags.append(stacked_concession_risk)

    verified_score, verified_label, verified_sort_rank = runtime.verified_score_info(record)
    confidence_score += verified_score
    if verified_sort_rank > 0:
        reasons.append(verified_label)
    else:
        risk_flags.append("未认证")

    activity_bonus, activity_label, activity_dt = runtime.activity_score_info(record)
    confidence_score += activity_bonus
    if activity_label and activity_bonus > 0:
        reasons.append(activity_label)
    elif activity_dt is None:
        risk_flags.append("活跃时间未知")
    elif activity_label:
        risk_flags.append(activity_label)

    completeness = sum(1 for field in runtime.text_fields if record.get(field))
    confidence_score += min(completeness, 10)
    matcher_enrichment_count = sum(
        1 for field in ("matcher_traits", "matcher_preferences", "matcher_risks") if record.get(field)
    )
    if matcher_enrichment_count:
        confidence_score += min(matcher_enrichment_count, 2)

    risk_flags.extend(runtime.build_profile_consistency_flags(record))

    required_known_fields = {
        field
        for field in criteria.get("required_known_fields", [])
        if not str(field).startswith("self_")
    }
    for field in required_known_fields:
        if not has_explicit_field_value(runtime, record, field) and field not in missing_fields:
            missing_fields.append(field)
    failed_required_known = [
        field for field in runtime.unique_ordered(missing_fields) if field in required_known_fields
    ]
    if failed_required_known:
        return fail("required_known_missing", failed_required_known[0])

    all_missing_fields = runtime.unique_ordered(missing_fields)
    self_profile_gaps = [field for field in all_missing_fields if str(field).startswith("self_")]
    candidate_missing_fields = [
        field for field in all_missing_fields if not str(field).startswith("self_")
    ]
    missing_penalty = sum(
        missing_field_penalty(runtime, field) for field in candidate_missing_fields
    )
    self_gap_penalty = sum(
        self_profile_gap_penalty(runtime, field) for field in self_profile_gaps
    )
    risk_score = missing_penalty + sum(
        risk_flag_penalty(runtime, flag) for flag in runtime.unique_ordered(risk_flags)
    ) + self_gap_penalty
    score = fit_score + confidence_score - risk_score

    follow_up_questions = build_follow_up_questions(
        runtime,
        record,
        candidate_missing_fields,
        risk_flags,
        self_profile=criteria.get("self_profile"),
    )

    result = runtime.build_match_result(
        record=record,
        score=score,
        fit_score=fit_score,
        confidence_score=confidence_score,
        risk_score=risk_score,
        matched_on=runtime.unique_ordered(reasons),
        reciprocal_on=runtime.unique_ordered(reciprocal_reasons),
        missing_fields=candidate_missing_fields,
        self_profile_gaps=self_profile_gaps,
        risk_flags=runtime.unique_ordered(risk_flags),
        match_evidence=runtime.unique_ordered(match_evidence),
        follow_up_questions=follow_up_questions,
        verified_rank=verified_sort_rank,
        activity_sort_ts=int(activity_dt.timestamp()) if activity_dt else 0,
        profile_status_rank=runtime.profile_status_rank(profile_status),
        matched=True,
        reject_reason=None,
    )
    result["display_notes"] = runtime.summarize_notes_for_result(
        record,
        criteria,
        criteria.get("self_profile") or {},
    )
    if not diagnostics:
        result.pop("matched", None)
        result.pop("reject_reason", None)
    return result


__all__ = [
    "SearchMatchingRuntime",
    "build_follow_up_questions",
    "candidate_income_bounds",
    "children_acceptance_risk_flag",
    "concession_stack_risk_flag",
    "evaluate_candidate",
    "evaluate_contextual_fit",
    "location_semantics_risk_flags",
    "marital_acceptance_risk_flag",
    "missing_field_penalty",
    "reciprocal_city_preference_risk_flag",
    "risk_flag_penalty",
    "self_education_floor_risk_flag",
    "self_prefers_near_distance",
    "self_profile_gap_penalty",
    "soft_preference_risk_flag",
]
