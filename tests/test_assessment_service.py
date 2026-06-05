from __future__ import annotations

import json
import types
import sys
from unittest import mock

from assessment import attachment_service, big_five_service, sternberg_service
from assessment.love_style_generator import get_xiaoya_message
from assessment.service import add_xiaoya_message_to_discovery_session


class _FakeStorage:
    def __init__(self) -> None:
        self._ids = {
            "assessment": 0,
            "msg-a": 0,
        }
        self.saved_session = None

    def next_item_id(self, prefix: str) -> str:
        self._ids[prefix] = self._ids.get(prefix, 0) + 1
        return f"{prefix}-{self._ids[prefix]}"

    def save_session(self, session) -> None:
        self.saved_session = session


class _FakeDiscoveryService:
    def __init__(self) -> None:
        self.storage = _FakeStorage()
        self.session = types.SimpleNamespace(session_id="session-1", view={"timeline": []})

    def _require_session(self, session_id: str):
        assert session_id == "session-1"
        return self.session


def test_add_xiaoya_message_to_discovery_session_appends_result_before_message() -> None:
    fake_service = _FakeDiscoveryService()
    fake_discovery_module = types.SimpleNamespace(create_default_discovery_service=mock.Mock(return_value=fake_service))
    fake_view_models_module = types.SimpleNamespace(
        assistant_message=lambda item_id, body, *, created_at=None: {
            "item_type": "assistant_message",
            "item_id": item_id,
            "body": body,
            "created_at": created_at,
        },
        assessment_result=lambda item_id, card, *, created_at=None: {
            "item_type": "assessment_result",
            "item_id": item_id,
            "card": card,
            "created_at": created_at,
        },
    )

    with mock.patch(
        "assessment.service._resolve_source",
        return_value=("mysql://discovery", "user_persona_observations"),
    ), mock.patch.dict(
        sys.modules,
        {
            "discovery_system": fake_discovery_module,
            "discovery_system.view_models": fake_view_models_module,
        },
    ):
        result = add_xiaoya_message_to_discovery_session(
            discovery_source="mysql://discovery",
            session_id="session-1",
            user_key="42",
            message="亲爱的，你的测试结果出来啦！",
            result_data={
                "assessment_id": "mbti_demo",
                "type_code": "INTJ",
                "labels": ["理性"],
                "scores": {"ei": 20},
            },
        )

    assert result["success"] is True
    timeline = fake_service.session.view["timeline"]
    assert [item["item_type"] for item in timeline] == ["assessment_result", "assistant_message"]
    assert timeline[0]["card"]["result_data"]["type_code"] == "INTJ"
    assert timeline[1]["body"] == "亲爱的，你的测试结果出来啦！"
    assert fake_service.storage.saved_session is fake_service.session


def test_mbti_xiaoya_message_uses_official_preference_structure() -> None:
    message = get_xiaoya_message(
        "INTJ",
        {"ei": 20, "sn": 35, "tf": 80, "jp": 75},
    )

    assert "**INTJ**" in message["identity"]
    assert "==重点是==" in message["identity"]
    assert "再往下说一点" in message["quirk"]
    assert "如果再往前多说一步" in message["suggestion"]
    assert "我下一条还能继续陪你拆" in message["suggestion"]


class _SqlFormattingCursor:
    def __init__(self, row: tuple[str, str] | tuple[str, str, str] | None) -> None:
        self._row = row
        self.last_query: str | None = None
        self.last_params: tuple[object, ...] | None = None

    def __enter__(self) -> _SqlFormattingCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        # Simulate PyMySQL-style interpolation enough to catch bare % regressions.
        query % params
        self.last_query = query
        self.last_params = params

    def fetchone(self):
        return self._row


class _SqlFormattingConn:
    def __init__(self, row: tuple[str, str] | tuple[str, str, str] | None) -> None:
        self.cursor_instance = _SqlFormattingCursor(row)

    def cursor(self) -> _SqlFormattingCursor:
        return self.cursor_instance


def test_get_big_five_xiaoya_message_escapes_like_percent(monkeypatch) -> None:
    payload = json.dumps({"message": "big five", "read": False}, ensure_ascii=False)
    conn = _SqlFormattingConn((payload, "big_five_20260604"))

    monkeypatch.setattr(big_five_service, "_resolve_source", lambda source: ("mysql://fake/db", "user_persona_observations"))
    monkeypatch.setattr(big_five_service, "mysql_connect", lambda source: conn)
    monkeypatch.setattr(big_five_service, "release_persona_connection", lambda source, conn: None)

    result = big_five_service.get_big_five_xiaoya_message(source="mysql://fake", user_key="u1")

    assert result == {
        "has_message": True,
        "message": "big five",
        "assessment_id": "big_five_20260604",
    }
    assert "conversation_ref LIKE %s" in (conn.cursor_instance.last_query or "")
    assert conn.cursor_instance.last_params == ("u1", "assessment.xiaoya_message", "big_five_%")


def test_get_attachment_xiaoya_message_escapes_like_percent(monkeypatch) -> None:
    payload = json.dumps({"message": "attachment", "read": False}, ensure_ascii=False)
    conn = _SqlFormattingConn((payload, "attachment_20260604", "2026-06-04 12:00:00"))

    monkeypatch.setattr(attachment_service, "_resolve_source", lambda source: ("mysql://fake/db", "user_persona_observations"))
    monkeypatch.setattr(attachment_service, "mysql_connect", lambda source: conn)
    monkeypatch.setattr(attachment_service, "release_persona_connection", lambda source, conn: None)

    result = attachment_service.get_attachment_xiaoya_message(source="mysql://fake", user_key="u1")

    assert result == {
        "has_message": True,
        "message": "attachment",
        "assessment_id": "attachment_20260604",
    }
    assert "LIKE 'attachment_%%'" in (conn.cursor_instance.last_query or "")


def test_get_sternberg_xiaoya_message_escapes_like_percent(monkeypatch) -> None:
    payload = json.dumps({"message": "sternberg", "read": False}, ensure_ascii=False)
    conn = _SqlFormattingConn((payload, "sternberg_20260604"))

    monkeypatch.setattr(sternberg_service, "_resolve_source", lambda source: ("mysql://fake/db", "user_persona_observations"))
    monkeypatch.setattr(sternberg_service, "mysql_connect", lambda source: conn)
    monkeypatch.setattr(sternberg_service, "release_persona_connection", lambda source, conn: None)

    result = sternberg_service.get_sternberg_xiaoya_message(source="mysql://fake", user_key="u1")

    assert result == {
        "has_message": True,
        "message": "sternberg",
        "assessment_id": "sternberg_20260604",
    }
    assert "conversation_ref LIKE %s" in (conn.cursor_instance.last_query or "")
    assert conn.cursor_instance.last_params == ("u1", "assessment.xiaoya_message", "sternberg_%")
