#!/usr/bin/env python3

"""Search profile sources for partner candidates.

This module intentionally keeps product workflow concerns out of the matching
engine. The CLI remains available, but the search flow is split into small
helpers so callers can reuse loading, evaluation, and rendering separately.
"""

import argparse as _argparse
import os
import re
import sys

from her_time_utils import coerce_int as as_int, unique_ordered_texts
from mysql_source_config import MYSQL_SCHEMES as MYSQL_SOURCE_SCHEMES
from partner_moderation import overlay_records_with_moderation
from partner_search.search_inputs import (
    KEYWORD_EVIDENCE_FIELDS,
    STRUCTURED_KEYWORD_SIGNAL_RULES,
    TEXTUAL_KEYWORD_SIGNAL_RULES,
    UNKNOWN_VALUES,
    as_lower,
    as_text,
    contains_any_text,
    evaluate_exclusion_keyword,
    field_display_name,
    first_defined,
    habit_requires_acceptance,
    merge_keyword_args,
    merge_keyword_values,
    normalize_acceptance_state,
    normalize_acceptance_strength,
    normalize_bool,
    normalize_strictness_state,
    normalize_whitespace,
    parse_json_object,
    split_evidence_segments,
    split_keywords,
    split_must_have_keywords,
)
from partner_search.search_sources import (
    SearchSourceRuntime,
    attach_photo_previews as _attach_photo_previews,
    build_mysql_prefilter as _build_mysql_prefilter,
    detect_mysql_profile_table as _detect_mysql_profile_table,
    iter_load_source_batches as _iter_load_source_batches,
    load_mysql as _load_mysql,
    load_mysql_photo_previews as _load_mysql_photo_previews,
    load_source as _load_source,
    parse_mysql_source as _parse_mysql_source,
    quote_mysql_ident as _quote_mysql_ident,
    resolve_mysql_columns as _resolve_mysql_columns,
)
from partner_search.search_no_match import (
    SearchNoMatchRuntime,
    build_fallback_candidates as _build_fallback_candidates,
    build_no_match_diagnostics as _build_no_match_diagnostics,
    build_no_match_diagnostics_payload as _build_no_match_diagnostics_payload,
    build_rejection_reason as _build_rejection_reason,
    format_no_match_text as _format_no_match_text,
    format_rejection_reason as _format_rejection_reason,
    parse_rejection_reason as _parse_rejection_reason,
    suggestion_for_rejection as _suggestion_for_rejection,
)
from partner_search.search_matching import (
    SearchMatchingRuntime,
    build_follow_up_questions as _build_follow_up_questions,
    candidate_income_bounds as _candidate_income_bounds,
    children_acceptance_risk_flag as _children_acceptance_risk_flag,
    concession_stack_risk_flag as _concession_stack_risk_flag,
    evaluate_candidate as _evaluate_candidate,
    evaluate_contextual_fit as _evaluate_contextual_fit,
    location_semantics_risk_flags as _location_semantics_risk_flags,
    marital_acceptance_risk_flag as _marital_acceptance_risk_flag,
    missing_field_penalty as _missing_field_penalty,
    reciprocal_city_preference_risk_flag as _reciprocal_city_preference_risk_flag,
    risk_flag_penalty as _risk_flag_penalty,
    self_education_floor_risk_flag as _self_education_floor_risk_flag,
    self_prefers_near_distance as _self_prefers_near_distance,
    self_profile_gap_penalty as _self_profile_gap_penalty,
    soft_preference_risk_flag as _soft_preference_risk_flag,
)
from partner_search.search_profile_context import (
    SearchProfileContextRuntime,
    build_criteria_from_args as _build_criteria_from_args,
    build_self_profile as _build_self_profile,
    build_self_profile_from_args as _build_self_profile_from_args,
    build_self_profile_input_from_args as _build_self_profile_input_from_args,
    normalize_request_criteria as _normalize_request_criteria,
    normalize_self_profile_input as _normalize_self_profile_input,
    resolve_self_profile_record as _resolve_self_profile_record,
)
from partner_search.search_profile_utils import (
    SearchProfileUtilsRuntime,
    as_datetime as _as_datetime,
    build_combined_text as _build_combined_text,
    default_source_help_text as _default_source_help_text,
    education_rank as _education_rank,
    effective_activity_datetime as _effective_activity_datetime,
    effective_activity_info as _effective_activity_info,
    effective_has_children as _effective_has_children,
    format_datetime as _format_datetime,
    get_combined_text_lazy as _get_combined_text_lazy,
    has_explicit_field_value as _has_explicit_field_value,
    is_mysql_source as _is_mysql_source,
    marital_status_match_options as _marital_status_match_options,
    normalize_record as _normalize_record,
    parse_income_range_to_wan as _parse_income_range_to_wan,
    photo_verification_rank as _photo_verification_rank,
    profile_status_rank as _profile_status_rank,
    redact_mysql_source as _redact_mysql_source,
    redact_source_ref as _redact_source_ref,
    verified_rank as _verified_rank,
)
from partner_search.search_ranking import (
    SearchRankingRuntime,
    build_match_result as _build_match_result,
    diversity_job_cluster as _diversity_job_cluster,
    diversity_penalty as _diversity_penalty,
    diversity_signature as _diversity_signature,
    record_ref as _record_ref,
    result_sort_key as _result_sort_key,
    select_diverse_results as _select_diverse_results,
    trim_low_quality_tail as _trim_low_quality_tail,
)
from partner_search.search_reciprocal import (
    SearchReciprocalRuntime,
    evaluate_reciprocal_compatibility as _evaluate_reciprocal_compatibility,
    exact_match as _exact_match,
    income_range_relation as _income_range_relation,
    income_range_overlaps as _income_range_overlaps,
    match_any_exact as _match_any_exact,
    matcher_preference_tags as _matcher_preference_tags,
)
from partner_search.search_trust import (
    SearchTrustRuntime,
    activity_score_info as _activity_score_info,
    build_profile_consistency_flags as _build_profile_consistency_flags,
    build_trust_actions as _build_trust_actions,
    build_trust_caution_items as _build_trust_caution_items,
    build_trust_summary as _build_trust_summary,
    build_verification_items as _build_verification_items,
    format_income_range_text as _format_income_range_text,
    normalize_field_verification_status as _normalize_field_verification_status,
    photo_verification_level as _photo_verification_level,
    photo_verification_level_label as _photo_verification_level_label,
    profile_field_verification_raw_status as _profile_field_verification_raw_status,
    profile_field_verification_status as _profile_field_verification_status,
    verified_level_label as _verified_level_label,
    verified_score_info as _verified_score_info,
)
from partner_search.search_text_signals import (
    SearchTextSignalsRuntime,
    child_or_marital_topic_requested as _child_or_marital_topic_requested,
    collect_keyword_signal_evidence as _collect_keyword_signal_evidence,
    contains_sensitive_note_detail as _contains_sensitive_note_detail,
    extract_keyword_evidence as _extract_keyword_evidence,
    extract_literal_keyword_evidence as _extract_literal_keyword_evidence,
    keyword_matches_record as _keyword_matches_record,
    mask_value as _mask_value,
    redact_sensitive_text as _redact_sensitive_text,
    shorten_text as _shorten_text,
    summarize_notes as _summarize_notes,
    summarize_notes_for_result as _summarize_notes_for_result,
)
from partner_search.search_runtime_helpers import SearchRuntime, SearchRuntimeHelpers
from profile_source_refs import build_source_file_ref as _build_source_file_ref
from profile_source_refs import split_source_file_ref as _split_source_file_ref
from profile_service import (
    detect_profile_table,
    list_profile_columns,
    list_profile_photo_previews,
    list_profiles,
    resolve_profile_source,
)

argparse = _argparse


FIELD_ALIASES = {
    "id": {"id", "编号"},
    "name": {"name", "姓名", "昵称"},
    "avatar_url": {"avatar_url", "头像", "头像地址"},
    "photo_count": {"photo_count", "照片数", "照片数量"},
    "gender": {"gender", "性别"},
    "age": {"age", "年龄"},
    "city": {"city", "城市", "所在地", "现居地"},
    "district": {"district", "区县", "区域"},
    "hometown": {"hometown", "老家", "籍贯"},
    "settlement_city": {"settlement_city", "定居城市", "长期定居城市"},
    "housing_status": {"housing_status", "住房情况"},
    "car_status": {"car_status", "车辆情况"},
    "height": {"height", "身高"},
    "education": {"education", "学历"},
    "job": {"job", "工作", "职业"},
    "income_range": {"income_range", "收入", "收入范围"},
    "relationship_goal": {"relationship_goal", "目标", "恋爱目标", "婚恋目标", "关系目标"},
    "preferred_age_min": {"preferred_age_min", "择偶年龄下限", "年龄要求下限", "偏好年龄下限", "年龄最小"},
    "preferred_age_max": {"preferred_age_max", "择偶年龄上限", "年龄要求上限", "偏好年龄上限", "年龄最大"},
    "preferred_cities": {"preferred_cities", "择偶城市", "意向城市", "期望城市", "偏好城市"},
    "preferred_height_min": {"preferred_height_min", "择偶身高下限", "身高要求下限", "偏好身高下限", "最低身高"},
    "preferred_height_max": {"preferred_height_max", "择偶身高上限", "身高要求上限", "偏好身高上限", "最高身高"},
    "preferred_age_strictness": {"preferred_age_strictness", "年龄要求严格度", "择偶年龄严格度"},
    "preferred_height_strictness": {"preferred_height_strictness", "身高要求严格度", "择偶身高严格度"},
    "preferred_education_min": {"preferred_education_min", "择偶学历下限", "最低学历", "学历要求"},
    "preferred_education_strictness": {"preferred_education_strictness", "学历要求严格度", "择偶学历严格度"},
    "preferred_income_min_wan": {"preferred_income_min_wan", "择偶收入下限", "收入要求下限", "最低收入"},
    "preferred_income_max_wan": {"preferred_income_max_wan", "择偶收入上限", "收入要求上限", "最高收入"},
    "preferred_income_strictness": {"preferred_income_strictness", "收入要求严格度", "择偶收入严格度"},
    "personality": {"personality", "性格"},
    "values": {"values", "价值观", "消费观"},
    "lifestyle": {"lifestyle", "生活方式", "作息"},
    "hobbies": {"hobbies", "兴趣", "爱好"},
    "life_routine": {"life_routine", "作息类型", "生活节奏"},
    "communication_style": {"communication_style", "沟通风格", "沟通方式"},
    "dating_pace": {"dating_pace", "推进节奏", "相处节奏"},
    "expression_style": {"expression_style", "表达风格", "表达感", "生活感"},
    "relationship_capacity": {"relationship_capacity", "关系投入能力", "关系承接能力"},
    "interaction_comfort": {"interaction_comfort", "相处轻松度", "相处压力", "相处状态"},
    "patience_level": {"patience_level", "耐心程度", "耐心水平"},
    "life_texture": {"life_texture", "生活立体感", "生活层次", "生活感层次"},
    "career_intensity": {"career_intensity", "工作节奏类型", "职业强度", "工作强度"},
    "exercise_habit": {"exercise_habit", "运动习惯", "运动频率"},
    "growth_signal": {"growth_signal", "事业势能", "成长性", "发展势能"},
    "warmth_style": {"warmth_style", "聊天温度", "互动温度", "温度感"},
    "aesthetic_expression": {"aesthetic_expression", "审美表达", "审美感", "内容输出"},
    "conversation_resonance": {
        "conversation_resonance",
        "聊天共鸣",
        "聊天同频感",
        "聊天感觉",
    },
    "personal_presence": {
        "personal_presence",
        "人物感",
        "记忆点",
        "个人辨识度",
    },
    "lightness_humor": {
        "lightness_humor",
        "轻松感",
        "幽默感",
        "聊天轻盈度",
    },
    "consumption_attitude": {
        "consumption_attitude",
        "消费观锚点",
        "消费观类型",
        "花钱观",
    },
    "chat_texture": {
        "chat_texture",
        "聊天质感",
        "聊天趣味",
        "聊天顺滑度",
    },
    "commitment_clarity": {
        "commitment_clarity",
        "进入关系明确度",
        "结婚意愿明确度",
        "长期意图明确度",
    },
    "relationship_execution": {
        "relationship_execution",
        "现实推进方式",
        "关系推进方式",
        "推进执行感",
    },
    "blended_family_readiness": {
        "blended_family_readiness",
        "重组家庭承接度",
        "现实承接度",
        "带娃现实承接度",
    },
    "smoking": {"smoking", "抽烟", "吸烟"},
    "drinking": {"drinking", "喝酒", "饮酒"},
    "long_distance": {"long_distance", "异地", "接受异地"},
    "accept_long_distance": {"accept_long_distance", "是否接受异地", "可否异地"},
    "location_preference_semantics": {
        "location_preference_semantics",
        "位置偏好补充",
        "异地补充说明",
        "位置偏好语义",
    },
    "accept_smoking": {"accept_smoking", "接受抽烟", "接受吸烟", "是否接受抽烟", "是否接受吸烟"},
    "accept_drinking": {"accept_drinking", "接受喝酒", "接受饮酒", "是否接受喝酒", "是否接受饮酒"},
    "accept_marital_status": {"accept_marital_status", "接受婚况", "可接受婚况", "可接受婚姻状态"},
    "accept_marital_status_strength": {
        "accept_marital_status_strength",
        "婚况接受强度",
        "婚史接受强度",
        "婚况接受态度",
    },
    "accept_marital_status_semantics": {
        "accept_marital_status_semantics",
        "婚况接受细语义",
        "婚史接受细语义",
        "婚况接受真实表达",
    },
    "marital_status": {"marital_status", "婚姻状态"},
    "has_children": {"has_children", "有无孩子", "是否有孩子", "是否已育"},
    "children_count": {"children_count", "孩子数量", "子女数量"},
    "children_living_with_self": {"children_living_with_self", "孩子是否同住", "子女是否同住"},
    "want_children": {"want_children", "是否想要孩子", "想要孩子", "生育计划", "孩子计划"},
    "accept_partner_children": {
        "accept_partner_children",
        "接受对方孩子",
        "是否接受对方有孩子",
        "是否接受伴侣有孩子",
    },
    "accept_partner_children_strength": {
        "accept_partner_children_strength",
        "接受孩子强度",
        "对子女接受强度",
        "对子女接受态度",
    },
    "accept_partner_children_semantics": {
        "accept_partner_children_semantics",
        "对子女接受细语义",
        "对子女接受真实表达",
        "对子女接受补充语义",
    },
    "requires_partner_accept_my_children": {
        "requires_partner_accept_my_children",
        "是否要求对方接受其孩子现实",
        "对方是否需要接受其孩子现实",
    },
    "marriage_timeline": {"marriage_timeline", "结婚时间", "结婚计划", "结婚节奏"},
    "family_background": {"family_background", "家庭情况", "家庭背景"},
    "profile_status": {"profile_status", "资料状态", "档案状态"},
    "last_active_at": {"last_active_at", "最近活跃时间", "最后活跃时间"},
    "verified_level": {"verified_level", "认证等级", "认证级别"},
    "photo_verification_level": {"photo_verification_level", "照片核验等级", "照片认证层级", "photo_verified_level"},
    "education_verification_status": {"education_verification_status", "学历认证状态", "education_verified_status"},
    "job_verification_status": {"job_verification_status", "职业认证状态", "job_verified_status"},
    "income_verification_status": {"income_verification_status", "收入认证状态", "income_verified_status"},
    "city_verification_status": {"city_verification_status", "城市认证状态", "city_verified_status"},
    "marital_status_verification_status": {"marital_status_verification_status", "婚况认证状态", "marital_verified_status"},
    "children_verification_status": {"children_verification_status", "子女情况认证状态", "children_verified_status"},
    "relationship_goal_verification_status": {"relationship_goal_verification_status", "结婚意向认证状态", "goal_verified_status"},
    "profile_review_status": {"profile_review_status", "资料复核状态", "profile_consistency_status"},
    "job_change_count_30d": {"job_change_count_30d", "近30天职业修改次数"},
    "city_change_count_30d": {"city_change_count_30d", "近30天城市修改次数"},
    "income_change_count_30d": {"income_change_count_30d", "近30天收入修改次数"},
    "source_channel": {"source_channel", "来源渠道", "来源"},
    "created_at": {"created_at", "创建时间"},
    "updated_at": {"updated_at", "更新时间"},
    "notes": {"notes", "备注", "说明"},
}

MYSQL_SCHEMES = MYSQL_SOURCE_SCHEMES
DEFAULT_MYSQL_SOURCE = os.environ.get("PARTNER_SEARCH_MYSQL_SOURCE")
DEFAULT_MYSQL_PHOTOS_TABLE = os.environ.get(
    "PARTNER_SEARCH_MYSQL_PHOTOS_TABLE",
    "profile_photos",
)

def normalize_key(key):
    return re.sub(r"[\s\-]+", "_", str(key).strip().lower())


TEXT_FIELDS = [
    "name",
    "city",
    "district",
    "hometown",
    "settlement_city",
    "housing_status",
    "car_status",
    "education",
    "job",
    "income_range",
    "relationship_goal",
    "preferred_cities",
    "preferred_age_strictness",
    "preferred_height_strictness",
    "preferred_education_strictness",
    "preferred_income_strictness",
    "personality",
    "values",
    "lifestyle",
    "hobbies",
    "life_routine",
    "communication_style",
    "dating_pace",
    "expression_style",
    "relationship_capacity",
    "interaction_comfort",
    "patience_level",
    "life_texture",
    "career_intensity",
    "exercise_habit",
    "growth_signal",
    "warmth_style",
    "aesthetic_expression",
    "conversation_resonance",
    "personal_presence",
    "lightness_humor",
    "consumption_attitude",
    "chat_texture",
    "commitment_clarity",
    "relationship_execution",
    "blended_family_readiness",
    "smoking",
    "drinking",
    "long_distance",
    "accept_long_distance",
    "location_preference_semantics",
    "accept_smoking",
    "accept_drinking",
    "accept_marital_status",
    "accept_marital_status_strength",
    "accept_marital_status_semantics",
    "marital_status",
    "want_children",
    "accept_partner_children",
    "accept_partner_children_strength",
    "accept_partner_children_semantics",
    "marriage_timeline",
    "family_background",
    "notes",
    "source_channel",
]

VERIFIED_LEVEL_ORDER = {
    "none": 0,
    "basic": 1,
    "photo": 2,
    "id": 3,
    "offline": 4,
}

PHOTO_VERIFICATION_LEVEL_ORDER = {
    "none": 0,
    "uploaded": 1,
    "human_verified": 2,
    "live_video_verified": 3,
    "offline_verified": 4,
}

# 档案状态优先级排序（简化版：只有3个状态）
PROFILE_STATUS_ORDER = {
    "inactive": 0,  # 最低优先级
    "matched": 1,
    "active": 2,    # 最高优先级
}

EDUCATION_ORDER = {
    "初中": 1,
    "高中": 2,
    "中专": 3,
    "大专": 4,
    "专升本": 5,
    "本科": 6,
    "硕士": 7,
    "博士": 8,
}

BUSY_JOB_KEYWORDS = {"医生", "护士", "审计", "金融", "投行", "新媒体", "课程顾问", "外贸"}

CRITICAL_MISSING_FIELD_PENALTIES = {
    "smoking": 8,
    "drinking": 4,
    "long_distance": 6,
    "marital_status": 7,
    "want_children": 8,
    "accept_partner_children": 10,
    "accept_marital_status": 8,
    "accept_smoking": 5,
    "accept_drinking": 5,
    "accept_long_distance": 7,
    "marriage_timeline": 5,
    "settlement_city": 4,
}

SELF_PROFILE_GAP_PENALTIES = {
    "self_age": 3,
    "self_city": 4,
    "self_height": 4,
    "self_education": 3,
    "self_income_wan": 3,
    "self_marital_status": 4,
    "self_has_children": 5,
    "self_smoking": 2,
    "self_drinking": 2,
}

RISK_FLAG_PENALTIES = {
    "对方对子女情况仅可协商": 10,
    "对方对子女接受度偏低": 11,
    "对方对子女接受需要先接触再判断": 10,
    "对方对子女接受度未知": 12,
    "对方城市偏好未命中，但资料写了接受异地": 6,
    "对方城市偏好未命中，异地仅可协商": 10,
    "对方城市偏好未命中，异地接受度未知": 10,
    "对方对抽烟仅可协商": 7,
    "对方对抽烟接受度未知": 9,
    "对方对喝酒仅可协商": 4,
    "对方对喝酒接受度未知": 8,
    "对方异地仅可协商": 7,
    "对方异地接受度未知": 8,
    "对方年龄要求可能可放宽": 7,
    "对方身高要求可能可放宽": 5,
    "对方学历要求可能可放宽": 5,
    "对方收入要求可能可放宽": 6,
    "对方收入预期上限未命中，但不构成硬性淘汰": 3,
    "对方婚史接受度偏保守": 9,
    "对方婚史接受需要先聊再判断": 9,
    "对方婚史接受度未知": 10,
    "对方对子女接受度偏保守": 9,
    "学历没有完全卡进你的底线": 12,
    "对方不接受长期异地，需要确认落地计划": 9,
    "异地需要明确落地计划": 6,
    "非同城，见面推进成本更高": 4,
    "多项条件需要放宽后才成立": 6,
    "生活阶段可能有落差": 8,
    "资料偏稳但不够鲜活": 5,
    "相处可能偏冷": 6,
    "相处节奏可能偏赶": 5,
    "忙的时候可能更难推进": 5,
    "工作节奏偏忙，稳定投入要再看": 5,
    "主动沟通感偏弱": 4,
    "乐观外放感偏弱": 3,
    "消费观还不够具体": 4,
    "聊天还像完成任务": 7,
    "认真相处信号还不够落地": 6,
    "认真相处推进偏慢": 5,
    "长期意图有，但推进方式还不够落地": 9,
    "推进方式偏慢观察": 6,
    "成长势能偏弱": 6,
    "聊天温度偏冷": 5,
    "审美表达偏平": 4,
    "聊天可能像信息交换": 5,
    "人物感偏淡": 4,
    "聊天可能偏板正": 5,
    "进入关系信号偏弱": 9,
    "重组家庭现实承接仍需确认": 6,
    "资料存在待复核或不一致信号": 8,
    "收入声明与职业类型存在明显落差": 12,
    "职业近30天修改较频繁": 8,
    "城市近30天修改较频繁": 6,
    "收入近30天修改较频繁": 8,
    "未认证": 6,
    "活跃时间未知": 4,
    "90天前活跃": 6,
}

CREATIVE_JOB_PATTERNS = (
    re.compile(r"(设计|ui|ux|交互|视觉|插画|动画|品牌|创意|内容|游戏|摄影|导演|编剧)", re.I),
)

DIVERSITY_JOB_PATTERNS = (
    (re.compile(r"(医生|护士|药师|医疗|医院|临床)"), "medical"),
    (re.compile(r"(教师|老师|学校|教育|培训)"), "education"),
    (re.compile(r"(产品|运营|研发|工程师|程序|算法|设计)"), "tech"),
    (re.compile(r"(金融|银行|证券|基金|投行|保险)"), "finance"),
    (re.compile(r"(体制|公务员|事业单位|国企)"), "public-sector"),
)

SIGNAL_FIELD_SPECS = (
    ("life_routine", "作息"),
    ("communication_style", "沟通"),
    ("dating_pace", "节奏"),
    ("career_intensity", "工作节奏"),
    ("consumption_attitude", "消费观"),
    ("commitment_clarity", "长期意图"),
    ("relationship_execution", "推进方式"),
    ("blended_family_readiness", "现实承接"),
    ("growth_signal", "成长"),
    ("interaction_comfort", "相处"),
)

RELATIONSHIP_GOAL_STRENGTH_BONUS = {
    "先接触看看": 0,
    "认真恋爱": 2,
    "结婚导向": 4,
}

NEAR_DISTANCE_PRIORITY_MARKERS = (
    "同城",
    "近距离",
    "通勤",
    "稳定留",
    "落地计划",
    "见面成本不能太高",
    "长期异地不接受",
)

SOFT_CONCESSION_RISK_FLAGS = {
    "对方年龄要求可能可放宽",
    "对方身高要求可能可放宽",
    "对方学历要求可能可放宽",
    "对方收入要求可能可放宽",
    "对方收入预期上限未命中，但不构成硬性淘汰",
    "对方城市偏好未命中，异地仅可协商",
    "对方城市偏好未命中，异地接受度未知",
    "对方异地仅可协商",
    "对方异地接受度未知",
    "对方婚史接受度偏保守",
    "对方婚史接受需要先聊再判断",
    "对方对子女情况仅可协商",
    "对方对子女接受度偏保守",
    "对方对子女接受需要先接触再判断",
    "认真相处信号还不够落地",
    "认真相处推进偏慢",
    "长期意图有，但推进方式还不够落地",
    "推进方式偏慢观察",
}


def build_alias_lookup():
    lookup = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            lookup[normalize_key(alias)] = canonical
    return lookup


ALIAS_LOOKUP = build_alias_lookup()


def is_mysql_source(source):
    return _is_mysql_source(_build_search_profile_utils_runtime(), source)


def redact_mysql_source(source):
    return _redact_mysql_source(_build_search_profile_utils_runtime(), source)


def redact_source_ref(source_ref):
    return _redact_source_ref(_build_search_profile_utils_runtime(), source_ref)


def default_source_help_text():
    return _default_source_help_text(_build_search_profile_utils_runtime())


def as_datetime(value):
    return _as_datetime(value)


def education_rank(value):
    return _education_rank(_build_search_profile_utils_runtime(), value)


def verified_rank(value):
    return _verified_rank(_build_search_profile_utils_runtime(), value)


def photo_verification_rank(value):
    return _photo_verification_rank(_build_search_profile_utils_runtime(), value)


def profile_status_rank(value):
    return _profile_status_rank(_build_search_profile_utils_runtime(), value)


def parse_income_range_to_wan(value):
    return _parse_income_range_to_wan(value)


def effective_has_children(record):
    return _effective_has_children(_build_search_profile_utils_runtime(), record)


def marital_status_match_options(record):
    return _marital_status_match_options(_build_search_profile_utils_runtime(), record)


def effective_activity_datetime(record):
    return _effective_activity_datetime(_build_search_profile_utils_runtime(), record)


def effective_activity_info(record):
    return _effective_activity_info(_build_search_profile_utils_runtime(), record)


def format_datetime(value):
    return _format_datetime(value)


def mask_value(value, left=2, right=2, mask="***"):
    return _mask_value(value, left=left, right=right, mask=mask)


def redact_sensitive_text(value):
    return _redact_sensitive_text(value)


def contains_sensitive_note_detail(value):
    return _contains_sensitive_note_detail(value)


def summarize_notes(value, max_segments=2, max_length=80):
    return _summarize_notes(
        _build_search_text_signals_runtime(),
        value,
        max_segments=max_segments,
        max_length=max_length,
    )


def shorten_text(value, max_length=60):
    return _shorten_text(_build_search_text_signals_runtime(), value, max_length=max_length)


def extract_literal_keyword_evidence(record, keyword):
    return _extract_literal_keyword_evidence(_build_search_text_signals_runtime(), record, keyword)


def collect_keyword_signal_evidence(record, keyword):
    return _collect_keyword_signal_evidence(_build_search_text_signals_runtime(), record, keyword)


def keyword_matches_record(record, keyword):
    return _keyword_matches_record(_build_search_text_signals_runtime(), record, keyword)


def extract_keyword_evidence(record, keyword):
    return _extract_keyword_evidence(_build_search_text_signals_runtime(), record, keyword)


def missing_field_penalty(field):
    return _missing_field_penalty(_build_search_matching_runtime(), field)


def self_profile_gap_penalty(field):
    return _self_profile_gap_penalty(_build_search_matching_runtime(), field)


def risk_flag_penalty(risk_flag):
    return _risk_flag_penalty(_build_search_matching_runtime(), risk_flag)


def location_semantics_risk_flags(record):
    return _location_semantics_risk_flags(_build_search_matching_runtime(), record)


def soft_preference_risk_flag(kind, strictness_state):
    return _soft_preference_risk_flag(
        _build_search_matching_runtime(),
        kind,
        strictness_state,
    )


def self_preference_strictness(value):
    if value is None or value == "":
        return "soft"
    return normalize_strictness_state(value)


def self_education_floor_risk_flag(self_profile, record):
    return _self_education_floor_risk_flag(
        _build_search_matching_runtime(),
        self_profile,
        record,
    )


def keyword_requested(criteria, keywords):
    joined = " ".join(criteria.get("must_have", []) + criteria.get("prefer", []))
    return contains_any_text(joined, keywords)


def creative_job_match(value):
    text = as_text(value)
    if not text:
        return False
    return any(pattern.search(text) for pattern in CREATIVE_JOB_PATTERNS)


def child_or_marital_topic_requested(criteria, self_profile):
    return _child_or_marital_topic_requested(
        _build_search_text_signals_runtime(),
        criteria,
        self_profile,
    )


def summarize_notes_for_result(record, criteria, self_profile, max_segments=2, max_length=80):
    return _summarize_notes_for_result(
        _build_search_text_signals_runtime(),
        record,
        criteria,
        self_profile,
        max_segments=max_segments,
        max_length=max_length,
    )


def candidate_income_bounds(record):
    return _candidate_income_bounds(_build_search_matching_runtime(), record)


def requires_explicit_marital_acceptance(self_profile):
    status = as_lower(self_profile.get("marital_status"))
    return bool(status and status != "未婚")


def requires_explicit_children_acceptance(self_profile):
    return normalize_bool(self_profile.get("has_children")) is True


def marital_acceptance_risk_flag(strength, semantics):
    return _marital_acceptance_risk_flag(
        _build_search_matching_runtime(),
        strength,
        semantics,
    )


def children_acceptance_risk_flag(state, strength, semantics):
    return _children_acceptance_risk_flag(
        _build_search_matching_runtime(),
        state,
        strength,
        semantics,
    )


def reciprocal_city_preference_risk_flag(accept_long_distance_state, reciprocal_mode):
    return _reciprocal_city_preference_risk_flag(
        _build_search_matching_runtime(),
        accept_long_distance_state,
        reciprocal_mode,
    )


def self_prefers_near_distance(self_profile):
    return _self_prefers_near_distance(
        _build_search_matching_runtime(),
        self_profile,
    )


def concession_stack_risk_flag(risk_flags):
    return _concession_stack_risk_flag(_build_search_matching_runtime(), risk_flags)


def evaluate_contextual_fit(record, criteria, self_profile=None):
    return _evaluate_contextual_fit(
        _build_search_matching_runtime(),
        record,
        criteria,
        self_profile=self_profile,
    )


def has_explicit_field_value(record, field):
    return _has_explicit_field_value(_build_search_profile_utils_runtime(), record, field)


def build_follow_up_questions(record, missing_fields, risk_flags, self_profile=None):
    return _build_follow_up_questions(
        _build_search_matching_runtime(),
        record,
        missing_fields,
        risk_flags,
        self_profile=self_profile,
    )


def normalize_record(raw):
    return _normalize_record(_build_search_profile_utils_runtime(), raw)


def build_source_file_ref(source, table_name=None):
    return _build_source_file_ref(source, table_name)


def split_source_file_ref(source_ref):
    return _split_source_file_ref(source_ref)


def build_combined_text(record):
    return _build_combined_text(_build_search_profile_utils_runtime(), record)


def _build_search_profile_utils_runtime() -> SearchProfileUtilsRuntime:
    return SearchProfileUtilsRuntime(
        mysql_schemes=MYSQL_SCHEMES,
        default_mysql_source=DEFAULT_MYSQL_SOURCE,
        alias_lookup=ALIAS_LOOKUP,
        text_fields=TEXT_FIELDS,
        unknown_values=UNKNOWN_VALUES,
        education_order=EDUCATION_ORDER,
        verified_level_order=VERIFIED_LEVEL_ORDER,
        photo_verification_level_order=PHOTO_VERIFICATION_LEVEL_ORDER,
        profile_status_order=PROFILE_STATUS_ORDER,
        as_lower=as_lower,
        as_text=as_text,
        normalize_bool=normalize_bool,
        normalize_key=normalize_key,
        parse_json_object=parse_json_object,
        unique_ordered=unique_ordered,
        split_source_file_ref=split_source_file_ref,
    )


def _build_search_profile_context_runtime() -> SearchProfileContextRuntime:
    return SearchProfileContextRuntime(
        as_int=as_int,
        as_lower=as_lower,
        as_text=as_text,
        normalize_bool=normalize_bool,
        merge_keyword_args=merge_keyword_args,
        merge_keyword_values=merge_keyword_values,
        split_must_have_keywords=split_must_have_keywords,
        unique_ordered=unique_ordered,
        first_defined=first_defined,
        alias_lookup=ALIAS_LOOKUP,
        normalize_key=normalize_key,
        normalize_record=normalize_record,
        build_combined_text=build_combined_text,
        strip_internal_fields=strip_internal_fields,
        parse_income_range_to_wan=parse_income_range_to_wan,
        redact_source_ref=redact_source_ref,
    )


def _build_search_text_signals_runtime() -> SearchTextSignalsRuntime:
    # 性能优化：使用惰性 combined_text 构建
    profile_utils_runtime = _build_search_profile_utils_runtime()
    return SearchTextSignalsRuntime(
        as_lower=as_lower,
        as_text=as_text,
        contains_any_text=contains_any_text,
        normalize_whitespace=normalize_whitespace,
        split_evidence_segments=split_evidence_segments,
        requires_explicit_children_acceptance=requires_explicit_children_acceptance,
        get_combined_text_lazy=lambda record: _get_combined_text_lazy(profile_utils_runtime, record),
        keyword_evidence_fields=KEYWORD_EVIDENCE_FIELDS,
        structured_keyword_signal_rules=STRUCTURED_KEYWORD_SIGNAL_RULES,
        textual_keyword_signal_rules=TEXTUAL_KEYWORD_SIGNAL_RULES,
    )


def _build_search_source_runtime() -> SearchSourceRuntime:
    return SearchSourceRuntime(
        alias_lookup=ALIAS_LOOKUP,
        verified_level_order=VERIFIED_LEVEL_ORDER,
        photo_verification_level_order=PHOTO_VERIFICATION_LEVEL_ORDER,
        default_mysql_photos_table=DEFAULT_MYSQL_PHOTOS_TABLE,
        as_int=as_int,
        as_lower=as_lower,
        as_text=as_text,
        normalize_key=normalize_key,
        verified_rank=verified_rank,
        photo_verification_rank=photo_verification_rank,
        normalize_record=normalize_record,
        build_source_file_ref=build_source_file_ref,
        split_source_file_ref=split_source_file_ref,
        redact_mysql_source=redact_mysql_source,
        resolve_profile_source=resolve_profile_source,
        detect_profile_table=detect_profile_table,
        list_profile_columns=list_profile_columns,
        list_profile_previews=list_profile_photo_previews,
        list_profiles=list_profiles,
        load_mysql_photo_previews_fn=load_mysql_photo_previews,
    )


def _build_search_trust_runtime() -> SearchTrustRuntime:
    return SearchTrustRuntime(
        as_int=as_int,
        as_lower=as_lower,
        as_text=as_text,
        normalize_bool=normalize_bool,
        verified_rank=verified_rank,
        effective_activity_datetime=effective_activity_datetime,
        effective_has_children=effective_has_children,
        parse_income_range_to_wan=parse_income_range_to_wan,
        unique_ordered=unique_ordered,
    )


def _build_search_no_match_runtime() -> SearchNoMatchRuntime:
    return SearchNoMatchRuntime(
        field_display_name=field_display_name,
        unique_ordered=unique_ordered,
        evaluate_candidate=evaluate_candidate,
        result_sort_key=result_sort_key,
        select_diverse_results=select_diverse_results,
        format_text=format_text,
    )


def _build_search_reciprocal_runtime() -> SearchReciprocalRuntime:
    return SearchReciprocalRuntime(
        as_int=as_int,
        as_lower=as_lower,
        as_text=as_text,
        normalize_bool=normalize_bool,
        split_keywords=split_keywords,
        parse_json_object=parse_json_object,
        unique_ordered=unique_ordered,
        build_rejection_reason=build_rejection_reason,
        normalize_strictness_state=normalize_strictness_state,
        soft_preference_risk_flag=soft_preference_risk_flag,
        reciprocal_city_preference_risk_flag=reciprocal_city_preference_risk_flag,
        normalize_acceptance_state=normalize_acceptance_state,
        location_semantics_risk_flags=location_semantics_risk_flags,
        education_rank=education_rank,
        marital_status_match_options=marital_status_match_options,
        normalize_acceptance_strength=normalize_acceptance_strength,
        marital_acceptance_risk_flag=marital_acceptance_risk_flag,
        children_acceptance_risk_flag=children_acceptance_risk_flag,
        habit_requires_acceptance=habit_requires_acceptance,
    )


def _build_search_ranking_runtime() -> SearchRankingRuntime:
    from match_domain.search_scoring_config import build_ranking_rule_params

    ranking_params = build_ranking_rule_params()
    return SearchRankingRuntime(
        as_int=as_int,
        as_text=as_text,
        strip_internal_fields=strip_internal_fields,
        diversity_job_patterns=DIVERSITY_JOB_PATTERNS,
        result_sort_key=result_sort_key,
        diversity_penalty_tiers=ranking_params["diversity_penalty_tiers"],
        score_gap_severe_concession=ranking_params["score_gap_severe_concession"],
        score_gap_high_risk_tail=ranking_params["score_gap_high_risk_tail"],
    )


def _build_search_matching_runtime() -> SearchMatchingRuntime:
    from match_domain.search_scoring_config import build_effective_risk_flag_penalties

    effective_penalties = build_effective_risk_flag_penalties(RISK_FLAG_PENALTIES)
    return SearchMatchingRuntime(
        as_int=as_int,
        as_lower=as_lower,
        as_text=as_text,
        contains_any_text=contains_any_text,
        normalize_bool=normalize_bool,
        normalize_acceptance_state=normalize_acceptance_state,
        normalize_strictness_state=normalize_strictness_state,
        normalize_acceptance_strength=normalize_acceptance_strength,
        split_keywords=split_keywords,
        unique_ordered=unique_ordered,
        parse_income_range_to_wan=parse_income_range_to_wan,
        effective_has_children=effective_has_children,
        effective_activity_datetime=effective_activity_datetime,
        education_rank=education_rank,
        exact_match=exact_match,
        match_any_exact=match_any_exact,
        keyword_matches_record=keyword_matches_record,
        extract_keyword_evidence=extract_keyword_evidence,
        evaluate_exclusion_keyword=evaluate_exclusion_keyword,
        evaluate_reciprocal_compatibility=evaluate_reciprocal_compatibility,
        parse_rejection_reason=parse_rejection_reason,
        build_rejection_reason=build_rejection_reason,
        verified_rank=verified_rank,
        profile_status_rank=profile_status_rank,
        photo_verification_level=photo_verification_level,
        photo_verification_rank=photo_verification_rank,
        photo_verification_level_label=photo_verification_level_label,
        build_match_result=build_match_result,
        record_ref=record_ref,
        build_profile_consistency_flags=build_profile_consistency_flags,
        activity_score_info=activity_score_info,
        verified_score_info=verified_score_info,
        summarize_notes_for_result=summarize_notes_for_result,
        requires_explicit_marital_acceptance=requires_explicit_marital_acceptance,
        requires_explicit_children_acceptance=requires_explicit_children_acceptance,
        marital_status_match_options=marital_status_match_options,
        text_fields=TEXT_FIELDS,
        unknown_values=UNKNOWN_VALUES,
        critical_missing_field_penalties=CRITICAL_MISSING_FIELD_PENALTIES,
        self_profile_gap_penalties=SELF_PROFILE_GAP_PENALTIES,
        risk_flag_penalties=effective_penalties,
        relationship_goal_strength_bonus=RELATIONSHIP_GOAL_STRENGTH_BONUS,
        education_order=EDUCATION_ORDER,
        busy_job_keywords=BUSY_JOB_KEYWORDS,
        creative_job_patterns=CREATIVE_JOB_PATTERNS,
        near_distance_priority_markers=NEAR_DISTANCE_PRIORITY_MARKERS,
        soft_concession_risk_flags=SOFT_CONCESSION_RISK_FLAGS,
    )


def parse_mysql_source(source, table_name=None):
    return _parse_mysql_source(_build_search_source_runtime(), source, table_name=table_name)


def quote_mysql_ident(identifier):
    return _quote_mysql_ident(identifier)


def resolve_mysql_columns(conn, database, table):
    return _resolve_mysql_columns(_build_search_source_runtime(), conn, database, table)


def build_mysql_prefilter(criteria, canonical_to_actual, include_ids=None, include_ids_mode="or"):
    return _build_mysql_prefilter(
        _build_search_source_runtime(),
        criteria,
        canonical_to_actual,
        include_ids=include_ids,
        include_ids_mode=include_ids_mode,
    )


def load_mysql(source, table_name=None, criteria=None, include_ids=None, include_ids_mode="or"):
    return _load_mysql(
        _build_search_source_runtime(),
        source,
        table_name=table_name,
        criteria=criteria,
        include_ids=include_ids,
        include_ids_mode=include_ids_mode,
    )


def load_mysql_photo_previews(source, profile_ids, table_name=None, photos_table_name=None, preview_count=3):
    return _load_mysql_photo_previews(
        _build_search_source_runtime(),
        source,
        profile_ids,
        table_name=table_name,
        photos_table_name=photos_table_name,
        preview_count=preview_count,
    )


def detect_mysql_profile_table(conn, database):
    return _detect_mysql_profile_table(_build_search_source_runtime(), conn, database)


def load_source(source, table_name=None, criteria=None, include_ids=None, include_ids_mode="or"):
    return _load_source(
        _build_search_source_runtime(),
        source,
        is_mysql_source=is_mysql_source,
        table_name=table_name,
        criteria=criteria,
        include_ids=include_ids,
        include_ids_mode=include_ids_mode,
    )


def iter_load_source_batches(source, table_name=None, criteria=None, include_ids=None, include_ids_mode="or"):
    return _iter_load_source_batches(
        _build_search_source_runtime(),
        source,
        is_mysql_source=is_mysql_source,
        table_name=table_name,
        criteria=criteria,
        include_ids=include_ids,
        include_ids_mode=include_ids_mode,
    )


def build_criteria_from_args(args):
    return _build_criteria_from_args(_build_search_profile_context_runtime(), args)


def normalize_request_criteria(criteria):
    return _normalize_request_criteria(_build_search_profile_context_runtime(), criteria)


def resolve_self_profile_record(self_id, records):
    return _resolve_self_profile_record(_build_search_profile_context_runtime(), self_id, records)


def normalize_self_profile_input(profile):
    return _normalize_self_profile_input(_build_search_profile_context_runtime(), profile)


def build_self_profile(records, self_id=None, profile_input=None):
    return _build_self_profile(
        _build_search_profile_context_runtime(),
        records,
        self_id=self_id,
        profile_input=profile_input,
    )


def build_self_profile_input_from_args(args):
    return _build_self_profile_input_from_args(args)


def build_self_profile_from_args(args, records):
    return _build_self_profile_from_args(_build_search_profile_context_runtime(), args, records)


def exact_match(value, expected):
    return _exact_match(_build_search_reciprocal_runtime(), value, expected)


def match_any_exact(value, candidates):
    return _match_any_exact(_build_search_reciprocal_runtime(), value, candidates)


def income_range_overlaps(min_value, max_value, required_min, required_max):
    return _income_range_overlaps(min_value, max_value, required_min, required_max)


def income_range_relation(min_value, max_value, required_min, required_max):
    return _income_range_relation(min_value, max_value, required_min, required_max)


def activity_score_info(record):
    return _activity_score_info(_build_search_trust_runtime(), record)


def verified_score_info(record):
    return _verified_score_info(_build_search_trust_runtime(), record)


def verified_level_label(value):
    return _verified_level_label(_build_search_trust_runtime(), value)


def photo_verification_level(profile):
    return _photo_verification_level(_build_search_trust_runtime(), profile)


def photo_verification_level_label(value):
    return _photo_verification_level_label(_build_search_trust_runtime(), value)


def normalize_field_verification_status(value, fallback="self_reported"):
    return _normalize_field_verification_status(
        _build_search_trust_runtime(),
        value,
        fallback=fallback,
    )


def profile_field_verification_raw_status(profile, field_key):
    return _profile_field_verification_raw_status(
        _build_search_trust_runtime(),
        profile,
        field_key,
    )


def profile_field_verification_status(profile, field_key, fallback="self_reported"):
    return _profile_field_verification_status(
        _build_search_trust_runtime(),
        profile,
        field_key,
        fallback=fallback,
    )


def format_income_range_text(record):
    return _format_income_range_text(_build_search_trust_runtime(), record)


def build_profile_consistency_flags(profile):
    return _build_profile_consistency_flags(_build_search_trust_runtime(), profile)


def build_verification_items(profile):
    return _build_verification_items(_build_search_trust_runtime(), profile)


def build_trust_caution_items(profile, verification_items=None):
    return _build_trust_caution_items(
        _build_search_trust_runtime(),
        profile,
        verification_items=verification_items,
    )


def build_trust_actions(profile, verification_items=None, caution_items=None):
    return _build_trust_actions(
        _build_search_trust_runtime(),
        profile,
        verification_items=verification_items,
        caution_items=caution_items,
    )


def build_trust_summary(profile, verification_items=None):
    return _build_trust_summary(
        _build_search_trust_runtime(),
        profile,
        verification_items=verification_items,
    )


def build_rejection_reason(code, detail=None):
    return _build_rejection_reason(code, detail=detail)


def parse_rejection_reason(reason):
    return _parse_rejection_reason(reason)


def format_rejection_reason(reason):
    return _format_rejection_reason(_build_search_no_match_runtime(), reason)


def suggestion_for_rejection(reason):
    return _suggestion_for_rejection(_build_search_no_match_runtime(), reason)


def build_no_match_diagnostics(records, criteria):
    return _build_no_match_diagnostics(
        _build_search_no_match_runtime(),
        records,
        criteria,
    )


def build_no_match_diagnostics_payload(
    scanned_count,
    passed_count,
    usable_count,
    top_reasons,
    relax_suggestions,
):
    return _build_no_match_diagnostics_payload(
        scanned_count=scanned_count,
        passed_count=passed_count,
        usable_count=usable_count,
        top_reasons=top_reasons,
        relax_suggestions=relax_suggestions,
    )


def build_fallback_candidates(records, criteria, limit=3):
    return _build_fallback_candidates(
        _build_search_no_match_runtime(),
        records,
        criteria,
        limit=limit,
    )


def format_no_match_text(diagnostics, fallback_results=None):
    return _format_no_match_text(
        _build_search_no_match_runtime(),
        diagnostics,
        fallback_results=fallback_results,
    )


def matcher_preference_tags(record):
    return _matcher_preference_tags(_build_search_reciprocal_runtime(), record)


def evaluate_reciprocal_compatibility(record, self_profile, diagnostics=False, reciprocal_mode="strict"):
    return _evaluate_reciprocal_compatibility(
        _build_search_reciprocal_runtime(),
        record,
        self_profile,
        diagnostics=diagnostics,
        reciprocal_mode=reciprocal_mode,
    )


def evaluate_candidate(record, criteria, diagnostics=False, reciprocal_mode="strict"):
    return _evaluate_candidate(
        _build_search_matching_runtime(),
        record,
        criteria,
        diagnostics=diagnostics,
        reciprocal_mode=reciprocal_mode,
    )


def build_match_result(
    record,
    score,
    fit_score,
    confidence_score,
    risk_score,
    matched_on,
    reciprocal_on,
    missing_fields,
    self_profile_gaps,
    risk_flags,
    match_evidence,
    follow_up_questions,
    verified_rank,
    activity_sort_ts,
    profile_status_rank,
    matched=True,
    reject_reason=None,
    match_tier="strict",
    compatibility_flags=None,
):
    return _build_match_result(
        _build_search_ranking_runtime(),
        record=record,
        score=score,
        fit_score=fit_score,
        confidence_score=confidence_score,
        risk_score=risk_score,
        matched_on=matched_on,
        reciprocal_on=reciprocal_on,
        missing_fields=missing_fields,
        self_profile_gaps=self_profile_gaps,
        risk_flags=risk_flags,
        match_evidence=match_evidence,
        follow_up_questions=follow_up_questions,
        verified_rank=verified_rank,
        activity_sort_ts=activity_sort_ts,
        profile_status_rank=profile_status_rank,
        matched=matched,
        reject_reason=reject_reason,
        match_tier=match_tier,
        compatibility_flags=compatibility_flags,
    )


def unique_ordered(items):
    return unique_ordered_texts(items)


def strip_internal_fields(record):
    cleaned = {}
    for key, value in record.items():
        if key in {"combined_text", "source_file"}:
            continue
        cleaned[key] = value
    return cleaned


def record_ref(record):
    return _record_ref(_build_search_ranking_runtime(), record)


def result_sort_key(result):
    return _result_sort_key(result)


def diversity_job_cluster(job):
    return _diversity_job_cluster(_build_search_ranking_runtime(), job)


def diversity_signature(result):
    return _diversity_signature(_build_search_ranking_runtime(), result)


def diversity_penalty(candidate, selected):
    return _diversity_penalty(_build_search_ranking_runtime(), candidate, selected)


def trim_low_quality_tail(results):
    return _trim_low_quality_tail(_build_search_ranking_runtime(), results)


def select_diverse_results(results, limit):
    return _select_diverse_results(_build_search_ranking_runtime(), results, limit)


def attach_photo_previews(results, preview_count, photos_table_name=None):
    return _attach_photo_previews(
        _build_search_source_runtime(),
        results,
        preview_count,
        photos_table_name=photos_table_name,
    )


_search_runtime_helpers = SearchRuntimeHelpers(
    SearchRuntime(
        signal_field_specs=SIGNAL_FIELD_SPECS,
        default_mysql_source=DEFAULT_MYSQL_SOURCE,
        as_int=as_int,
        default_source_help_text=default_source_help_text,
        normalize_request_criteria=normalize_request_criteria,
        normalize_self_profile_input=normalize_self_profile_input,
        build_criteria_from_args=build_criteria_from_args,
        build_self_profile_input_from_args=build_self_profile_input_from_args,
        load_source=lambda *args, **kwargs: load_source(*args, **kwargs),
        iter_source_batches=lambda *args, **kwargs: iter_load_source_batches(*args, **kwargs),
        overlay_records_with_moderation=overlay_records_with_moderation,
        evaluate_candidate=evaluate_candidate,
        result_sort_key=result_sort_key,
        select_diverse_results=select_diverse_results,
        build_self_profile=build_self_profile,
        record_ref=record_ref,
        build_fallback_candidates=build_fallback_candidates,
        build_no_match_diagnostics=build_no_match_diagnostics,
        attach_photo_previews=lambda *args, **kwargs: attach_photo_previews(*args, **kwargs),
        effective_activity_info=effective_activity_info,
        effective_activity_datetime=effective_activity_datetime,
        format_datetime=format_datetime,
        build_trust_summary=build_trust_summary,
        summarize_notes=summarize_notes,
        build_verification_items=build_verification_items,
        activity_score_info=activity_score_info,
        redact_source_ref=redact_source_ref,
        format_no_match_text=format_no_match_text,
    )
)

summarize_signal_parts = _search_runtime_helpers.summarize_signal_parts
format_result_headline = _search_runtime_helpers.format_result_headline
format_result_scoring_line = _search_runtime_helpers.format_result_scoring_line
build_result_meta_parts = _search_runtime_helpers.build_result_meta_parts
append_labeled_line = _search_runtime_helpers.append_labeled_line
append_joined_line = _search_runtime_helpers.append_joined_line
append_result_detail_lines = _search_runtime_helpers.append_result_detail_lines
format_result_block = _search_runtime_helpers.format_result_block
format_text = _search_runtime_helpers.format_text
register_argument_specs = _search_runtime_helpers.register_argument_specs
build_source_argument_specs = _search_runtime_helpers.build_source_argument_specs
add_source_arguments = _search_runtime_helpers.add_source_arguments
add_profile_filter_arguments = _search_runtime_helpers.add_profile_filter_arguments
add_quality_arguments = _search_runtime_helpers.add_quality_arguments
add_self_profile_arguments = _search_runtime_helpers.add_self_profile_arguments
add_output_arguments = _search_runtime_helpers.add_output_arguments
build_parser = _search_runtime_helpers.build_parser
build_search_request = _search_runtime_helpers.build_search_request
build_cli_self_profile_input = _search_runtime_helpers.build_cli_self_profile_input
build_search_request_from_args = _search_runtime_helpers.build_search_request_from_args
resolve_request_sources = _search_runtime_helpers.resolve_request_sources
resolve_sources = _search_runtime_helpers.resolve_sources
collect_source_records_for_request = _search_runtime_helpers.collect_source_records_for_request
collect_source_records = _search_runtime_helpers.collect_source_records
evaluate_records = _search_runtime_helpers.evaluate_records
apply_request_self_profile_context = _search_runtime_helpers.apply_request_self_profile_context
apply_self_profile_context = _search_runtime_helpers.apply_self_profile_context
build_search_run = _search_runtime_helpers.build_search_run
populate_no_match_details = _search_runtime_helpers.populate_no_match_details
prepare_search_request_context = _search_runtime_helpers.prepare_search_request_context
prepare_search_context = _search_runtime_helpers.prepare_search_context
execute_search_request = _search_runtime_helpers.execute_search_request
execute_search = _search_runtime_helpers.execute_search
json_safe = _search_runtime_helpers.json_safe
build_structured_result_payload = _search_runtime_helpers.build_structured_result_payload
build_pool_summary = _search_runtime_helpers.build_pool_summary
build_structured_search_response = _search_runtime_helpers.build_structured_search_response
render_search_json = _search_runtime_helpers.render_search_json
render_search_output = _search_runtime_helpers.render_search_output


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        search_run = execute_search(args)
        if args.output_format == "json":
            print(
                render_search_json(
                    search_run,
                    include_source=args.show_source,
                )
            )
        else:
            print(render_search_output(search_run, include_source=args.show_source))
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
