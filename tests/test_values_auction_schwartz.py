from __future__ import annotations

from assessment.values_auction_lots import calculate_hidden_values
from assessment.values_auction_service import _build_values_auction_profile, generate_match_analysis, validate_bids


def test_schwartz_profile_prefers_conservation_and_self_transcendence() -> None:
    bids = [
        {"lot_id": "soulmate", "chips": 4},
        {"lot_id": "family_health", "chips": 3},
        {"lot_id": "help_many", "chips": 2},
        {"lot_id": "change_world", "chips": 1},
    ]

    hidden_values = calculate_hidden_values(bids)
    assert hidden_values["security"] == 0.36
    assert hidden_values["benevolence"] == 0.35

    profile = _build_values_auction_profile(bids)
    assert profile["schema_version"] == "v2"
    assert profile["value_type"] == "稳定关怀型"
    assert profile["higher_order_values"]["self_transcendence"] == 0.485
    assert profile["higher_order_values"]["conservation"] == 0.48
    assert profile["top_hidden_values"][0]["key"] == "security"
    assert profile["internal_tensions"] == []


def test_match_analysis_detects_structural_tension_between_change_and_security() -> None:
    user_a_bids = [
        {"lot_id": "total_freedom", "title": "想做什么就做什么，没人管", "chips": 5},
        {"lot_id": "financial_freedom", "title": "这辈子都不用再为钱妥协", "chips": 3},
        {"lot_id": "elite_status", "title": "走到哪里都让人高看一眼", "chips": 2},
    ]
    user_b_bids = [
        {"lot_id": "family_health", "title": "全家人健康平安到百岁", "chips": 5},
        {"lot_id": "soulmate", "title": "一个永远不会离开你的人", "chips": 3},
        {"lot_id": "inner_peace", "title": "内心平静，不再焦虑", "chips": 2},
    ]

    user_a_profile = _build_values_auction_profile(user_a_bids)
    user_b_profile = _build_values_auction_profile(user_b_bids)

    session = {
        "user_a_key": "u1",
        "user_b_key": "u2",
        "user_a_result": {
            "bids": user_a_bids,
            "hidden_values": user_a_profile["hidden_values"],
            "higher_order_values": user_a_profile["higher_order_values"],
            "internal_tensions": user_a_profile["internal_tensions"],
            "value_type": user_a_profile["value_type"],
            "top3": user_a_bids,
        },
        "user_b_result": {
            "bids": user_b_bids,
            "hidden_values": user_b_profile["hidden_values"],
            "higher_order_values": user_b_profile["higher_order_values"],
            "internal_tensions": user_b_profile["internal_tensions"],
            "value_type": user_b_profile["value_type"],
            "top3": user_b_bids,
        },
    }

    result = generate_match_analysis(session_id="session-1", session=session)
    match_data = result["match_data"]

    assert match_data["match_type"] == "需要磨合"
    assert match_data["alignment_score"] < 50
    assert match_data["shared_directions"] == []
    assert any(
        (item["left"] == "stimulation" and item["right"] == "security") or
        (item["left"] == "openness_to_change" and item["right"] == "conservation")
        for item in match_data["structural_tensions"]
    )
    assert any(conflict["type"] == "structural_tension" for conflict in match_data["conflicts"])


def test_validate_bids_enforces_integer_unique_and_per_lot_cap() -> None:
    ok, error = validate_bids([
        {"lot_id": "soulmate", "chips": 3},
        {"lot_id": "family_health", "chips": 2},
    ])
    assert ok is True
    assert error == ""

    ok, error = validate_bids([
        {"lot_id": "soulmate", "chips": 4},
    ])
    assert ok is False
    assert "不在有效范围" in error

    ok, error = validate_bids([
        {"lot_id": "soulmate", "chips": 1},
        {"lot_id": "soulmate", "chips": 1},
    ])
    assert ok is False
    assert "重复提交" in error

    ok, error = validate_bids([
        {"lot_id": "soulmate", "chips": 1.5},
    ])
    assert ok is False
    assert "必须为整数" in error
