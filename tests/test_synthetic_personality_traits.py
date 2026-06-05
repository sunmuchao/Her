from __future__ import annotations

from persona_memory_sync.synthetic_personality_traits import build_synthetic_personality_traits


def test_build_synthetic_personality_traits_is_deterministic_and_compact() -> None:
    record = {
        "id": 42,
        "personality": "情绪稳定,真诚,善沟通",
        "values": "消费观正常,重视家庭,愿意共同经营生活",
        "lifestyle": "生活规律,规律作息,喜欢做饭",
        "relationship_goal": "结婚导向",
        "want_children": "想要",
        "age": 30,
        "job": "教师",
        "updated_at": "2026-06-05 12:00:00",
    }

    first = build_synthetic_personality_traits(record, identity="42")
    second = build_synthetic_personality_traits(record, identity="42")

    assert first == second
    assert set(first.keys()) == {"mbti", "attachment", "big_five", "sternberg", "values"}
    assert "labels" not in first["mbti"]
    assert "dimension_rows" not in first["mbti"]
    assert first["values"]["top_values"]
    assert isinstance(first["attachment"]["anxiety"], float)
