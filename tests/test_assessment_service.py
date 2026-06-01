from __future__ import annotations

import types
import sys
from unittest import mock

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
