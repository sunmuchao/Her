from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from match_domain.session_end_processor import (
    SUMMARY_FIELD_KEYS,
    filter_valid_summary_data,
    normalize_quantifiable_patch,
    split_by_quantifiability,
    validate_summary_text,
)


def test_split_by_quantifiability_blocks_structured_fields_from_summaries() -> None:
    summary_data = {
        "mbti_type": "INTJ",
        "income": "年薪20万",
        "city": "苏州",
        "age": "31",
        "partner_expectation": "希望对方情绪稳定、工作别太忙、愿意认真推进关系",
        "emotional_needs": "需要关系里有回应，不喜欢长时间失联",
    }

    quantifiable, non_quantifiable = split_by_quantifiability(summary_data)

    assert {"mbti_type", "income", "city", "age"} <= set(quantifiable.keys())
    assert set(non_quantifiable.keys()) == {"partner_expectation", "emotional_needs"}
    assert set(non_quantifiable.keys()) <= SUMMARY_FIELD_KEYS


def test_validate_summary_text_rejects_generic_summary() -> None:
    assert validate_summary_text("partner_expectation", "希望性格合拍") == "invalid"
    assert validate_summary_text("emotional_needs", "需要安全感") == "invalid"
    assert validate_summary_text("life_attitude", "热爱生活") == "weak"


def test_validate_summary_text_accepts_concrete_summary() -> None:
    assert (
        validate_summary_text(
            "partner_expectation",
            "希望对方情绪稳定、遇事愿意直接沟通、不冷处理问题",
        )
        == "valid"
    )
    assert (
        validate_summary_text(
            "emotional_needs",
            "需要关系里有回应，下班后有时间陪伴，不喜欢长时间失联",
        )
        == "valid"
    )


def test_normalize_quantifiable_patch_maps_fields_to_persona_schema() -> None:
    quantifiable_data = {
        "mbti_type": "infj",
        "city": "无锡",
        "education": "本科",
        "marital_status": "未婚",
        "has_children": "没有孩子",
        "smoking": "不抽烟",
        "drinking": "偶尔喝酒",
        "age": "29",
        "height": "168",
        "income": "15-24万/年",
    }

    normalized = normalize_quantifiable_patch(quantifiable_data)

    assert normalized["self_city"] == "无锡"
    assert normalized["self_education"] == "本科"
    assert normalized["self_marital_status"] == "未婚"
    assert normalized["self_has_children"] == 0
    assert normalized["self_smoking"] == "不抽烟"
    assert normalized["self_drinking"] == "偶尔喝酒"
    assert normalized["self_age"] == 29
    assert normalized["self_height"] == 168
    assert normalized["self_income_wan"] == 15

    traits = json.loads(normalized["self_personality_traits_json"])
    assert traits["mbti"]["type_code"] == "INFJ"


def test_filter_valid_summary_data_rejects_weak_and_invalid_texts() -> None:
    summary_data = {
        "partner_expectation": "希望性格合拍",
        "emotional_needs": "需要关系里有回应，下班后有时间陪伴",
        "life_attitude": "热爱生活",
    }

    valid, rejected = filter_valid_summary_data(summary_data)

    assert valid == {
        "emotional_needs": "需要关系里有回应，下班后有时间陪伴",
    }
    assert rejected == {
        "partner_expectation": "invalid",
        "life_attitude": "weak",
    }


def test_filter_valid_summary_data_normalizes_summary_text_before_saving() -> None:
    summary_data = {
        "partner_expectation": "希望对方性格温柔，有上进心，认真推进关系",
    }

    valid, rejected = filter_valid_summary_data(summary_data)

    assert rejected == {}
    assert valid == {
        "partner_expectation": "希望对方温和，目标感强，关系推进明确，细腻，有耐心，成长驱动强，做事积极，有责任感，不暧昧，持续投入关系，节奏明确",
    }
