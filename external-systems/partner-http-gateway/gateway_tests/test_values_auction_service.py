from __future__ import annotations

import json

from assessment import values_auction_service as service


class _FakeCursor:
    def __init__(self, rows: dict[tuple[str, str, str], str]) -> None:
        self._rows = rows
        self._selected: str | None = None

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        normalized = " ".join(query.split()).upper()
        if normalized.startswith("DELETE FROM"):
            user_key, conversation_ref, field_name = (str(params[0]), str(params[1]), str(params[2]))
            self._rows.pop((user_key, conversation_ref, field_name), None)
            self._selected = None
            return

        if normalized.startswith("INSERT INTO"):
            user_key = str(params[0])
            field_name = str(params[1])
            field_value = str(params[2])
            conversation_ref = str(params[6])
            self._rows[(user_key, conversation_ref, field_name)] = field_value
            self._selected = None
            return

        if normalized.startswith("SELECT FIELD_VALUE FROM"):
            user_key, field_name, conversation_ref = (str(params[0]), str(params[1]), str(params[2]))
            self._selected = self._rows.get((user_key, conversation_ref, field_name))
            return

        raise AssertionError(f"Unexpected query: {query}")

    def fetchone(self):
        if self._selected is None:
            return None
        return (self._selected,)


class _FakeConn:
    def __init__(self, rows: dict[tuple[str, str, str], str]) -> None:
        self._rows = rows

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._rows)

    def commit(self) -> None:
        return None


def _install_fakes(monkeypatch, *, last_result: dict | None = None):
    rows: dict[tuple[str, str, str], str] = {}
    conn = _FakeConn(rows)

    monkeypatch.setattr(service, "mysql_connect", lambda source: conn)
    monkeypatch.setattr(service, "release_persona_connection", lambda source, conn: None)
    monkeypatch.setattr(service, "store_assessment_result", lambda **kwargs: None)
    monkeypatch.setattr(service, "merge_personality_summary", lambda **kwargs: None)
    monkeypatch.setattr(service, "update_assessment_interpretation", lambda **kwargs: None)
    monkeypatch.setattr(service, "get_assessment_result", lambda **kwargs: None)
    monkeypatch.setattr(service, "get_last_result", lambda **kwargs: last_result)
    return rows


def test_submit_together_updates_both_participants(monkeypatch):
    rows = _install_fakes(monkeypatch)
    source = "mysql://fake/her?table=user_personas"

    started = service.start_values_auction_together(
        user_key="u1",
        partner_key="u2",
        source=source,
    )
    session_id = started["session_id"]

    bids_a = [
        {"lot_id": "soulmate", "chips": 3},
        {"lot_id": "family_health", "chips": 3},
        {"lot_id": "help_many", "chips": 2},
        {"lot_id": "inner_peace", "chips": 2},
    ]
    bids_b = [
        {"lot_id": "soulmate", "chips": 3},
        {"lot_id": "family_health", "chips": 3},
        {"lot_id": "deep_understanding", "chips": 3},
        {"lot_id": "help_many", "chips": 1},
    ]

    waiting = service.submit_auction_bids_together(
        session_id=session_id,
        user_key="u1",
        bids=bids_a,
        source=source,
    )
    assert waiting["card_type"] == "values_auction_waiting"
    assert waiting["waiting_data"]["your_result"]["value_type"]

    match = service.submit_auction_bids_together(
        session_id=session_id,
        user_key="u2",
        bids=bids_b,
        source=source,
    )
    assert match["card_type"] == "values_match_analysis"
    assert match["match_data"]["schema_version"] == "v2"
    assert isinstance(match["match_data"]["alignment_score"], int)
    assert match["match_data"]["user1"]["higher_order_values"]
    assert match["match_data"]["user2"]["higher_order_values"]

    status_for_u1 = service.check_dual_auction_status(
        session_id=session_id,
        user_key="u1",
        source=source,
    )
    status_for_u2 = service.check_dual_auction_status(
        session_id=session_id,
        user_key="u2",
        source=source,
    )
    assert status_for_u1["status"] == "both_done"
    assert status_for_u2["status"] == "both_done"

    stored_u1 = json.loads(rows[("u1", session_id, service.VALUES_AUCTION_DUAL_SESSION_FIELD)])
    stored_u2 = json.loads(rows[("u2", session_id, service.VALUES_AUCTION_DUAL_SESSION_FIELD)])
    assert stored_u1["user_a_status"] == "done"
    assert stored_u1["user_b_status"] == "done"
    assert stored_u2["user_a_status"] == "done"
    assert stored_u2["user_b_status"] == "done"


def test_reuse_together_updates_both_participants(monkeypatch):
    last_result = {
        "schema_version": "v2",
        "value_type": "稳定关怀型",
        "hidden_values": {
            "security": 0.36,
            "benevolence": 0.35,
            "tradition": 0.12,
            "universalism": 0.1,
            "achievement": 0.04,
        },
        "higher_order_values": {
            "conservation": 0.48,
            "self_transcendence": 0.45,
            "self_enhancement": 0.04,
        },
        "internal_tensions": [],
        "bids": [
            {"lot_id": "soulmate", "title": "一个永远不会离开你的人", "chips": 4},
            {"lot_id": "family_health", "title": "全家人健康平安到百岁", "chips": 3},
            {"lot_id": "help_many", "title": "默默帮助很多人", "chips": 3},
        ],
        "top3": [
            {"lot_id": "soulmate", "title": "一个永远不会离开你的人", "chips": 4},
            {"lot_id": "family_health", "title": "全家人健康平安到百岁", "chips": 3},
            {"lot_id": "help_many", "title": "默默帮助很多人", "chips": 3},
        ],
    }
    rows = _install_fakes(monkeypatch, last_result=last_result)
    source = "mysql://fake/her?table=user_personas"

    started = service.start_values_auction_together(
        user_key="u1",
        partner_key="u2",
        source=source,
    )
    session_id = started["session_id"]

    waiting = service.reuse_last_result_together(
        session_id=session_id,
        user_key="u1",
        source=source,
    )
    assert waiting["card_type"] == "values_auction_waiting"
    assert waiting["waiting_data"]["your_result"]["value_type"] == "稳定关怀型"

    match = service.reuse_last_result_together(
        session_id=session_id,
        user_key="u2",
        source=source,
    )
    assert match["card_type"] == "values_match_analysis"
    assert match["match_data"]["schema_version"] == "v2"
    assert match["match_data"]["user1"]["higher_order_values"]
    assert match["match_data"]["user2"]["higher_order_values"]

    status_for_u1 = service.check_dual_auction_status(
        session_id=session_id,
        user_key="u1",
        source=source,
    )
    status_for_u2 = service.check_dual_auction_status(
        session_id=session_id,
        user_key="u2",
        source=source,
    )
    assert status_for_u1["status"] == "both_done"
    assert status_for_u2["status"] == "both_done"


def test_submit_single_returns_v2_profile_fields(monkeypatch):
    rows = _install_fakes(monkeypatch)
    source = "mysql://fake/her?table=user_personas"

    result = service.submit_auction_bids(
        assessment_id="assessment-1",
        user_key="u1",
        bids=[
            {"lot_id": "soulmate", "chips": 3},
            {"lot_id": "family_health", "chips": 3},
            {"lot_id": "help_many", "chips": 2},
            {"lot_id": "change_world", "chips": 2},
        ],
        source=source,
    )

    assert result["card_type"] == "values_auction_result"
    result_data = result["result_data"]
    assert result_data["schema_version"] == "v2"
    assert result_data["schwartz_values"]["security"] == 0.315
    assert result_data["higher_order_values"]["conservation"] == 0.435
    assert result_data["higher_order_values"]["self_transcendence"] == 0.495
    assert result_data["value_type"] == "稳定关怀型"
    assert result_data["top_hidden_values"][0]["key"] == "security"
    assert "底层价值排序" not in result.get("xiaoya_message", "")

    stored = json.loads(rows[("u1", "assessment-1", service.VALUES_AUCTION_RESULT_FIELD)])
    assert stored["schema_version"] == "v2"
    assert stored["higher_order_values"]["self_transcendence"] == 0.495


def test_generate_interpretation_includes_higher_order_analysis(monkeypatch):
    values_auction_result = {
        "assessment_id": "assessment-2",
        "schema_version": "v2",
        "value_type": "稳定关怀型",
        "hidden_values": {
            "security": 0.36,
            "benevolence": 0.35,
            "tradition": 0.12,
            "universalism": 0.1,
            "achievement": 0.04,
        },
        "top_hidden_values": [
            {"key": "security", "weight": 0.36},
            {"key": "benevolence", "weight": 0.35},
            {"key": "tradition", "weight": 0.12},
        ],
        "higher_order_values": {
            "self_transcendence": 0.485,
            "conservation": 0.48,
            "self_enhancement": 0.04,
        },
        "internal_tensions": [],
        "top3": [
            {"lot_id": "soulmate", "title": "一个永远不会离开你的人", "chips": 4, "interpretation": "你想要的是稳定投入、彼此照顾、关系里不反复试探。"},
            {"lot_id": "family_health", "title": "全家人健康平安到百岁", "chips": 3, "interpretation": "你很重视生活底盘稳不稳，也很看重家庭责任感。"},
        ],
    }
    rows = _install_fakes(monkeypatch)
    source = "mysql://fake/her?table=user_personas"
    monkeypatch.setattr(
        service,
        "get_assessment_result",
        lambda **kwargs: {
            "assessment_id": "assessment-2",
            "assessment_type": service.ASSESSMENT_TYPE_VALUES_AUCTION,
            "user_key": "u1",
            "raw_result_json": values_auction_result,
        },
    )

    card = service.generate_ai_interpretation(
        assessment_id="assessment-2",
        user_key="u1",
        source=source,
    )

    assert card["card_type"] == "values_auction_interpretation"
    interpretation = card["interpretation_data"]
    assert interpretation["higher_order_analysis"][0]["key"] == "self_transcendence"
    assert interpretation["top3_analysis"][0]["trait_name"] == "一个永远不会离开你的人"
    stored = json.loads(rows[("u1", "assessment-2", service.VALUES_AUCTION_INTERPRETATION_FIELD)])
    assert stored["higher_order_analysis"][0]["label"]
