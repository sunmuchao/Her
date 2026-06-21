from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from match_domain.retrieval_text_normalizer import (
    normalize_query_text,
    normalize_summary_text,
    route_query_vector_types,
)


def test_normalize_summary_text_rewrites_partner_expectation_synonyms() -> None:
    normalized = normalize_summary_text(
        "partner_expectation",
        "希望对方性格温柔，有上进心，认真推进关系，不要太卷",
    )

    assert normalized.normalized_text == "希望对方温和，目标感强，关系推进明确，排斥高压内卷"
    assert "成长驱动强" in normalized.retrieval_text
    assert "不暧昧" in normalized.retrieval_text
    assert "tag:温和型" in normalized.retrieval_text
    assert "tag:目标感" in normalized.retrieval_text
    assert "tag:关系推进明确" in normalized.retrieval_text
    assert "温柔->温和" in normalized.applied_rules
    assert "有上进心->目标感强" in normalized.applied_rules


def test_normalize_query_text_rewrites_abstract_terms() -> None:
    normalized = normalize_query_text("我希望找一个性格温柔，有上进心的")

    assert normalized.normalized_text == "我希望找一个温和，目标感强的"
    assert normalized.route_vector_types[:3] == [
        "partner_personality_preference",
        "partner_expectation",
        "personality_traits",
    ]
    assert "成长驱动强" in normalized.retrieval_text
    assert "有责任感" in normalized.retrieval_text
    assert "tag:温和型" in normalized.semantic_tags
    assert "tag:目标感" in normalized.semantic_tags


def test_normalize_query_text_expands_relationship_pacing_terms() -> None:
    normalized = normalize_query_text("我喜欢慢热，真诚，认真推进关系的")

    assert "关系推进明确" in normalized.normalized_text
    assert "不暧昧" in normalized.retrieval_text
    assert "持续投入关系" in normalized.retrieval_text
    assert "tag:慢热真诚" in normalized.semantic_tags
    assert "tag:关系推进明确" in normalized.semantic_tags


def test_route_query_vector_types_for_emotional_needs() -> None:
    routes = route_query_vector_types("我需要对方及时回复，事事有回应，不冷处理")

    assert routes[:2] == ["emotional_needs", "partner_expectation"]


def test_route_query_vector_types_for_life_attitude() -> None:
    routes = route_query_vector_types("我希望对方生活规律，不要太卷")

    assert routes[:2] == ["partner_lifestyle_preference", "life_attitude"]


def test_route_query_vector_types_for_relationship_pacing_prefers_new_facet() -> None:
    routes = route_query_vector_types("我喜欢慢热，真诚，认真推进关系的")

    assert routes[:2] == ["partner_relationship_pacing", "emotional_needs"]
