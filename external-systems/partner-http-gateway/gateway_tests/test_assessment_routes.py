from __future__ import annotations

import pathlib
import sys
import types
from unittest import mock


GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from gateway.app import PartnerGateway  # noqa: E402
from gateway_tests.helpers import build_wsgi_env, run_wsgi_json  # noqa: E402


def _gateway() -> PartnerGateway:
    return PartnerGateway(
        recommendation_dsn="mysql://noop",
        matchmaking_dsn="mysql://noop",
        chat_dsn="mysql://noop",
        db_pool_max=0,
    )


def test_assessment_start_route_returns_intro_card() -> None:
    gw = _gateway()
    gw._resolve_end_user_principal = mock.Mock(return_value=types.SimpleNamespace(profile_id=42))  # type: ignore[method-assign]

    with (
        mock.patch("gateway.assessment_routes._default_profile_source", return_value="mysql://root@127.0.0.1:3307/her?table=profiles"),
        mock.patch(
            "gateway.assessment_routes.start_assessment",
            return_value={
                "card_type": "assessment_intro",
                "assessment_type": "mbti_16",
                "assessment_id": "mbti_demo",
                "intro_data": {"title": "MBTI 16型人格测评", "description": "快速看清你的相处风格和关系偏好", "duration": "约5分钟 · 20题", "reward": "匹配质量提升10%"},
            },
        ) as start_mock,
    ):
        status, payload, _headers = run_wsgi_json(
            gw,
            build_wsgi_env("POST", "/v1/assessment/start", {"assessment_type": "mbti_16"}),
        )

    assert "200" in status
    assert payload["card_type"] == "assessment_intro"
    start_mock.assert_called_once_with(
        source="mysql://root@127.0.0.1:3307/her?table=profiles",
        user_key="42",
        assessment_type="mbti_16",
    )


def test_assessment_answer_route_returns_feedback_card() -> None:
    gw = _gateway()
    gw._resolve_end_user_principal = mock.Mock(return_value=types.SimpleNamespace(profile_id=42))  # type: ignore[method-assign]

    with (
        mock.patch("gateway.assessment_routes._default_profile_source", return_value="mysql://root@127.0.0.1:3307/her?table=profiles"),
        mock.patch(
            "gateway.assessment_routes.answer_assessment",
            return_value={
                "card_type": "assessment_feedback",
                "assessment_id": "mbti_demo",
                "feedback_data": {
                    "dimension": "ei",
                    "dimension_name": "外向 E / 内向 I",
                    "score": 75.0,
                    "feedback_text": "你更偏外向，倾向从互动和表达里获取能量。",
                },
                "next_question": {
                    "current_question": 6,
                    "total_questions": 20,
                    "question_text": "你更关注眼前的事实和细节，而不是抽象可能性吗？",
                    "options": [],
                    "progress": 30,
                    "assessment_id": "mbti_demo",
                },
            },
        ) as answer_mock,
    ):
        status, payload, _headers = run_wsgi_json(
            gw,
            build_wsgi_env(
                "POST",
                "/v1/assessment/answer",
                {
                    "assessment_id": "mbti_demo",
                    "question_index": 4,
                    "answer": "A",
                },
            ),
        )

    assert "200" in status
    assert payload["card_type"] == "assessment_feedback"
    assert payload["feedback_data"]["dimension_name"] == "外向 E / 内向 I"
    answer_mock.assert_called_once_with(
        source="mysql://root@127.0.0.1:3307/her?table=profiles",
        assessment_id="mbti_demo",
        question_index=4,
        answer="A",
        user_key="42",
    )


def test_personality_traits_route_reads_assessment_traits() -> None:
    gw = _gateway()
    gw._resolve_end_user_principal = mock.Mock(return_value=None)  # type: ignore[method-assign]

    with (
        mock.patch("gateway.persona_routes._default_profile_source", return_value="mysql://root@127.0.0.1:3307/her?table=profiles"),
        mock.patch(
            "gateway.persona_routes.get_personality_traits",
            return_value={
                "mbti": {"type_code": "ENTJ"},
                "attachment": {},
                "love_language": {},
            },
        ) as traits_mock,
    ):
        status, payload, _headers = run_wsgi_json(
            gw,
            build_wsgi_env("GET", "/v1/persona/personality-traits", query="user_key=108"),
        )

    assert "200" in status
    assert payload["user_key"] == "108"
    assert payload["mbti"]["type_code"] == "ENTJ"
    traits_mock.assert_called_once_with(
        source="mysql://root@127.0.0.1:3307/her?table=profiles",
        user_key="108",
    )
