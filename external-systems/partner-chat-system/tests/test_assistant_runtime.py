import os
import pathlib
import sys
import types
import unittest
from typing import Optional
from unittest.mock import patch


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system.assistant_runtime import MatchmakerRunInput, _apply_runtime_policy, _compact_profile, run_matchmaker_agent  # noqa: E402


def _make_run_input(
    latest_body: str = "她是不是变冷了？",
    *,
    reason: str = "user_message",
    session_state: Optional[dict] = None,
    trigger_channel_key: Optional[str] = None,
    trigger_author_id: Optional[str] = None,
) -> MatchmakerRunInput:
    recent_messages = []
    if reason != "opening_probe":
        channel_key = trigger_channel_key or ("assistant_dm_a" if reason != "silence_probe" else "main_group")
        author_id = trigger_author_id or ("user-a" if channel_key != "assistant_dm_b" else "user-b")
        recent_messages = [
            {
                "message_id": 178,
                "channel_key": channel_key,
                "author_id": author_id,
                "source": "user",
                "body": latest_body,
                "created_at": "2026-05-09 19:32:10",
            }
        ]
    return MatchmakerRunInput(
        case_id="case-runtime-1",
        session={
            "session_id": "ags-runtime-1",
            "participant_a_id": "user-a",
            "participant_b_id": "user-b",
            "agent_participant_id": "agent-c",
            "status": "open",
            "state": session_state or {},
        },
        task={
            "task_id": 101,
            "case_id": "case-runtime-1",
            "trigger_message_id": 0 if reason == "opening_probe" else 178,
            "trigger_author_id": (
                ""
                if reason == "opening_probe"
                else (
                    trigger_author_id
                    or ("user-a" if (trigger_channel_key or "assistant_dm_a") != "assistant_dm_b" else "user-b")
                )
            ),
            "trigger_channel_key": (
                "main_group"
                if reason in {"silence_probe", "opening_probe"}
                else (trigger_channel_key or "assistant_dm_a")
            ),
            "reason": (
                reason
                if reason in {"silence_probe", "opening_probe", "post_chat_followup_a", "post_chat_followup_b", "post_chat_review"}
                else "user_message"
            ),
            "attempt_count": 1,
            "created_at": "2026-05-09 19:33:00",
            "started_at": "2026-05-09 19:33:00",
        },
        bootstrap={
            "recent_messages": recent_messages,
            "conversations": [],
        },
        profile_snapshots={
            "participant_a": {
                "participant_id": "user-a",
                "role": "participant_a",
                "profile": {
                    "name": "沈既白",
                    "city": "上海",
                    "job": "产品经理",
                    "personality": "稳定, 真诚",
                    "values": "看重稳定, 认真相处",
                    "notes": "会照顾日常",
                    "hobbies": "阅读, 咖啡",
                },
            },
            "participant_b": {
                "participant_id": "user-b",
                "role": "participant_b",
                "profile": {
                    "name": "高佳晨",
                    "city": "上海",
                    "job": "医生",
                    "personality": "耐心, 边界",
                    "values": "看重真诚, 长期",
                    "notes": "会照顾日常",
                    "hobbies": "咖啡, 瑜伽",
                },
            },
        },
        get_recent_case_messages=lambda **kwargs: recent_messages,
        search_case_history=lambda **kwargs: recent_messages,
        get_message_window=lambda **kwargs: recent_messages,
        get_case_conversations=lambda: [],
        get_profile_snapshot=lambda participant_id: {"participant_id": participant_id, "profile": {}},
        get_agent_session_state=lambda: {},
    )


def _fake_agents_module(*, exception_to_raise: Exception):
    module = types.ModuleType("agents")

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class FakeAgentOutputSchema:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class FakeRunner:
        @staticmethod
        def run_sync(agent, input):
            raise exception_to_raise

    def function_tool(fn):
        return fn

    module.Agent = FakeAgent
    module.AgentOutputSchema = FakeAgentOutputSchema
    module.Runner = FakeRunner
    module.function_tool = function_tool
    return module


class AssistantRuntimeTests(unittest.TestCase):
    def _run_with_exception(
        self,
        exc: Exception,
        latest_body: str = "她是不是变冷了？",
        *,
        reason: str = "user_message",
    ) -> dict:
        fake_agents = _fake_agents_module(exception_to_raise=exc)
        run_input = _make_run_input(latest_body=latest_body, reason=reason)
        with patch.dict(sys.modules, {"agents": fake_agents}):
            with patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "test-key",
                    "HER_CHAT_AGENT_RUNTIME": "agents_sdk",
                },
                clear=False,
            ):
                with patch("chat_system.assistant_runtime._configure_agents_sdk_provider", return_value=None):
                    return run_matchmaker_agent(run_input)

    def test_run_matchmaker_agent_recovers_fenced_json_exception(self):
        exc = Exception(
            'Invalid JSON when parsing ```json\n'
            '{\n'
            '  "should_reply": true,\n'
            '  "target_channel_key": "assistant_dm_a",\n'
            '  "reply_body": "她回复挺正常的，第一次接触都这样，别多想。",\n'
            '  "reason_codes": ["user_request", "early_stage_nervous"],\n'
            '  "state_patch": {},\n'
            '  "cooldown_seconds": 120\n'
            '}\n'
            '``` for TypeAdapter(MatchmakerDecision)'
        )

        decision = self._run_with_exception(exc)

        self.assertEqual(decision["target_channel_key"], "assistant_dm_a")
        self.assertEqual(decision["reply_body"], "她回复挺正常的，第一次接触都这样，别多想。")
        self.assertEqual(decision["reason_codes"], ["user_request", "early_stage_nervous"])
        self.assertEqual(decision["cooldown_seconds"], 120)

    def test_run_matchmaker_agent_recovers_broken_reply_body_quotes(self):
        exc = Exception(
            'Invalid JSON when parsing ```json\n'
            '{\n'
            '  "should_reply": true,\n'
            '  "target_channel_key": "assistant_dm_b",\n'
            '  "reply_body": "节奏差确实有，但还没到要放弃的程度。他的表达虽然有情绪，但他在问你"还能修吗"，而不是让你来哄——这个区别很重要。你现在要做的是：不当情绪垃圾桶，但也别直接收线。",\n'
            '  "reason_codes": ["attachment_style_mismatch", "continue_observing"],\n'
            '  "state_patch": {},\n'
            '  "cooldown_seconds": 60\n'
            '}\n'
            '``` for TypeAdapter(MatchmakerDecision)'
        )

        decision = self._run_with_exception(exc, latest_body="我们是不是节奏差得有点多了，还要不要继续往下看？")

        self.assertEqual(decision["target_channel_key"], "assistant_dm_b")
        self.assertIn('他在问你"还能修吗"', decision["reply_body"])
        self.assertEqual(decision["reason_codes"], ["attachment_style_mismatch", "continue_observing"])
        self.assertEqual(decision["cooldown_seconds"], 60)

    def test_run_matchmaker_agent_falls_back_when_exception_unrecoverable(self):
        exc = Exception("provider exploded before any structured payload was available")

        decision = self._run_with_exception(exc, latest_body="她是不是在降温，不太回我了？")

        self.assertTrue(decision["should_reply"])
        self.assertIn("structured_output_runtime_failed", decision["reason_codes"])
        self.assertEqual(decision["state_patch"]["runtime_fallback"], "structured_output_runtime_failed")
        self.assertIn("runtime_fallback_error", decision["state_patch"])
        self.assertTrue(str(decision["reply_body"]).strip())

    def test_run_matchmaker_agent_silence_probe_fallback_stays_quiet(self):
        exc = Exception("provider exploded before any structured payload was available")

        decision = self._run_with_exception(
            exc,
            latest_body="嗯，算是吧。",
            reason="silence_probe",
        )

        self.assertFalse(decision["should_reply"])
        self.assertEqual(decision["target_channel_key"], None)
        self.assertEqual(decision["reply_body"], None)
        self.assertIn("silence_probe_conservative_noop", decision["reason_codes"])
        self.assertFalse(decision["public_followup"]["active"])
        self.assertEqual(decision["public_followup"]["mode"], "silence")

    def test_run_matchmaker_agent_opening_probe_fallback_introduces_both_sides(self):
        exc = Exception("provider exploded before any structured payload was available")

        decision = self._run_with_exception(
            exc,
            latest_body="",
            reason="opening_probe",
        )

        self.assertTrue(decision["should_reply"])
        self.assertEqual(decision["target_channel_key"], "main_group")
        self.assertIn("我先帮两位搭个话", decision["reply_body"])
        self.assertIn("一位现在在上海做产品经理", decision["reply_body"])
        self.assertIn("另一位现在在上海做医生", decision["reply_body"])
        self.assertNotIn("沈既白", decision["reply_body"])
        self.assertNotIn("高佳晨", decision["reply_body"])
        self.assertIn("相处节奏拿捏得挺稳", decision["reply_body"])
        self.assertNotIn("阅读", decision["reply_body"])
        self.assertNotIn("咖啡", decision["reply_body"])
        self.assertNotIn("瑜伽", decision["reply_body"])
        self.assertIn("opening_probe_profile_intro", decision["reason_codes"])
        self.assertTrue(decision["public_followup"]["active"])
        self.assertEqual(decision["public_followup"]["mode"], "opening")

    def test_compact_profile_drops_internal_fields(self):
        compact = _compact_profile(
            {
                "id": 1,
                "name": "公开名",
                "city": "上海",
                "job": "产品经理",
                "personality": "稳定",
                "values": "真诚",
                "notes": "会照顾日常",
                "hobbies": "阅读, 咖啡",
                "lifestyle": "早睡早起",
                "public_display_name": "不该保留",
                "public_job": "不该保留",
            }
        )

        self.assertEqual(
            compact,
            {
                "id": 1,
                "name": "公开名",
                "city": "上海",
                "job": "产品经理",
                "personality": "稳定",
                "values": "真诚",
                "notes": "会照顾日常",
            },
        )

    def test_post_chat_followup_reason_asks_private_first_impression(self):
        run_input = _make_run_input(reason="post_chat_followup_a")

        decision = run_matchmaker_agent(run_input)

        self.assertTrue(decision["should_reply"])
        self.assertEqual(decision["target_channel_key"], "assistant_dm_a")
        self.assertIn("第一", decision["reply_body"])
        self.assertEqual(decision["state_patch"]["followup_a_status"], "sent")
        self.assertIn("post_chat_followup", decision["reason_codes"])

    def test_post_chat_feedback_turn_is_left_to_agent(self):
        run_input = _make_run_input(
            latest_body="人感觉还可以，不过我现在没有特别强的感觉，有点拿不准。",
            session_state={"phase": "post_chat_followup", "followup_a_status": "sent"},
            trigger_channel_key="assistant_dm_a",
        )

        with patch(
            "chat_system.assistant_runtime._run_with_agents_sdk",
            return_value={
                "should_reply": True,
                "target_channel_key": "assistant_dm_a",
                "reply_body": "你现在拿不准很正常，不等于不合适。要是不排斥，可以再看他情绪稳不稳、会不会认真接你的话、生活节奏和三观是不是合拍，再决定也不迟。",
                "reason_codes": ["post_chat_followup", "hesitation_guided"],
                "state_patch": {
                    "followup_a_status": "completed",
                    "followup_a_guidance": "observation_axes",
                    "followup_a_observation_axes": ["emotion_stability", "response_quality", "values_fit"],
                },
                "cooldown_seconds": 300,
            },
        ):
            decision = run_matchmaker_agent(run_input)

        self.assertTrue(decision["should_reply"])
        self.assertEqual(decision["target_channel_key"], "assistant_dm_a")
        self.assertIn("拿不准很正常", decision["reply_body"])
        self.assertEqual(decision["state_patch"]["followup_a_status"], "completed")
        self.assertEqual(decision["state_patch"]["followup_a_guidance"], "observation_axes")

    def test_post_chat_feedback_completion_state_can_be_set_by_agent(self):
        run_input = _make_run_input(
            latest_body="我觉得他整体挺稳的，聊着也舒服，可以继续了解看看。",
            session_state={
                "phase": "post_chat_followup",
                "followup_a_status": "sent",
                "followup_b_status": "user_initiated",
            },
            trigger_channel_key="assistant_dm_a",
        )

        with patch(
            "chat_system.assistant_runtime._run_with_agents_sdk",
            return_value={
                "should_reply": True,
                "target_channel_key": "assistant_dm_a",
                "reply_body": "收到，这个反馈我记下了。你这边是愿意继续了解的，那就顺着自然节奏往下走就行。",
                "reason_codes": ["post_chat_followup", "feedback_captured"],
                "state_patch": {
                    "followup_a_status": "completed",
                    "phase": "post_chat_completed",
                },
                "cooldown_seconds": 300,
            },
        ):
            decision = run_matchmaker_agent(run_input)

        self.assertTrue(decision["should_reply"])
        self.assertEqual(decision["target_channel_key"], "assistant_dm_a")
        self.assertIn("反馈我记下了", decision["reply_body"])
        self.assertEqual(decision["state_patch"]["followup_a_status"], "completed")
        self.assertEqual(decision["state_patch"]["phase"], "post_chat_completed")

    def test_post_chat_feedback_can_return_persona_updates(self):
        run_input = _make_run_input(
            latest_body="我自己还是会希望关系前期别收得太紧，生活里保留一点弹性。",
            session_state={
                "phase": "post_chat_followup",
                "followup_b_status": "sent",
            },
            trigger_channel_key="assistant_dm_b",
            trigger_author_id="user-b",
        )

        with patch(
            "chat_system.assistant_runtime._run_with_agents_sdk",
            return_value={
                "should_reply": True,
                "target_channel_key": "assistant_dm_b",
                "reply_body": "我明白，你更在意的是相处节奏别一下子收得太紧，这个我记下了。",
                "reason_codes": ["post_chat_followup", "match_direction_review"],
                "state_patch": {
                    "followup_b_status": "completed",
                    "followup_b_signal_summary": "更在意生活弹性，关系前期不喜欢太快收紧",
                },
                "cooldown_seconds": 300,
                "persona_updates": [
                    {
                        "subject_user_id": "user-b",
                        "source_type": "explicit",
                        "basis": "self_statement",
                        "apply_scope": "persona_only",
                        "patch": {
                            "self_job": "财务报表相关工作",
                            "persona_summary_internal": "生活节奏偏规律。",
                        },
                        "evidence_summary": "B 在聊后复盘时明确自述自己做财务报表相关工作，生活节奏偏规律。",
                    },
                    {
                        "subject_user_id": "user-b",
                        "source_type": "strong_inference",
                        "basis": "stable_inference",
                        "apply_scope": "persona_only",
                        "patch": {
                            "preferred_traits": ["生活有弹性"],
                            "disliked_traits": ["关系前期过早收紧"],
                            "preference_summary_internal": "更适合生活节奏有弹性、关系前期不压得太紧的对象。",
                        },
                        "evidence_summary": "聊后复盘里，B 连续两次明确表达希望生活保留弹性，不喜欢关系前期收得太紧。",
                    }
                ],
            },
        ):
            decision = run_matchmaker_agent(run_input)

        self.assertEqual(len(decision["persona_updates"]), 2)
        self.assertEqual(decision["persona_updates"][0]["subject_user_id"], "user-b")
        self.assertEqual(decision["persona_updates"][0]["source_type"], "explicit")
        self.assertEqual(decision["persona_updates"][0]["basis"], "self_statement")
        self.assertEqual(decision["persona_updates"][0]["apply_scope"], "persona_only")
        self.assertIn("self_job", decision["persona_updates"][0]["patch"])
        self.assertEqual(decision["persona_updates"][1]["source_type"], "strong_inference")
        self.assertEqual(decision["persona_updates"][1]["basis"], "stable_inference")
        self.assertEqual(decision["persona_updates"][1]["apply_scope"], "persona_only")
        self.assertIn("preferred_traits", decision["persona_updates"][1]["patch"])

    def test_persona_updates_are_stripped_during_live_chat(self):
        run_input = _make_run_input(
            latest_body="她刚才说自己喜欢稳定一点的生活。",
            session_state={"phase": "active"},
            trigger_channel_key="main_group",
        )

        decision = _apply_runtime_policy(
            run_input,
            {
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["observe_only"],
                "state_patch": {},
                "cooldown_seconds": 0,
                "persona_updates": [
                    {
                        "subject_user_id": "user-a",
                        "source_type": "weak_inference",
                        "patch": {
                            "preferred_traits": ["规律稳定"],
                            "preference_summary_internal": "更喜欢规律稳定的生活状态。",
                        },
                        "evidence_summary": "主群里刚聊到稳定生活。",
                    }
                ],
            },
        )

        self.assertEqual(decision["persona_updates"], [])
        self.assertIn("persona_updates_deferred_until_post_chat", decision["reason_codes"])

    def test_public_followup_turn_defaults_to_closing_when_agent_stays_quiet(self):
        run_input = _make_run_input(
            latest_body="我最近也挺忙的，周末可能就想休息一下。",
            session_state={"public_followup_active": True, "public_followup_mode": "silence"},
            trigger_channel_key="main_group",
        )

        decision = _apply_runtime_policy(
            run_input,
            {
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["observe_only"],
                "state_patch": {"relationship_stage": "monitoring"},
                "cooldown_seconds": 0,
            },
        )

        self.assertFalse(decision["public_followup"]["active"])
        self.assertEqual(decision["public_followup"]["mode"], "silence")

    def test_public_followup_turn_can_keep_observing_without_reply(self):
        run_input = _make_run_input(
            latest_body="我平时会去咖啡店坐坐，感觉这个话题还能再看看。",
            session_state={"public_followup_active": True, "public_followup_mode": "opening"},
            trigger_channel_key="main_group",
        )

        decision = _apply_runtime_policy(
            run_input,
            {
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["observe_only"],
                "state_patch": {"relationship_stage": "opening"},
                "cooldown_seconds": 0,
                "public_followup": {"active": True},
            },
        )

        self.assertTrue(decision["public_followup"]["active"])
        self.assertEqual(decision["public_followup"]["mode"], "opening")

    def test_public_followup_turn_preserves_existing_mode_when_agent_returns_wrong_one(self):
        run_input = _make_run_input(
            latest_body="我最近一次比较放松是下班后去买杯咖啡，慢慢走回家。",
            session_state={"public_followup_active": True, "public_followup_mode": "silence"},
            trigger_channel_key="main_group",
        )

        decision = _apply_runtime_policy(
            run_input,
            {
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["normal_rhythm", "awaiting_response"],
                "state_patch": {},
                "cooldown_seconds": 0,
                "public_followup": {"active": True, "mode": "opening"},
            },
        )

        self.assertTrue(decision["public_followup"]["active"])
        self.assertEqual(decision["public_followup"]["mode"], "silence")

    def test_post_chat_feedback_allows_n_persona_updates_for_same_subject(self):
        run_input = _make_run_input(
            latest_body="我做财务，也比较规律，不太接受长期异地。",
            session_state={
                "phase": "post_chat_followup",
                "followup_b_status": "sent",
            },
            trigger_channel_key="assistant_dm_b",
            trigger_author_id="user-b",
        )

        with patch(
            "chat_system.assistant_runtime._run_with_agents_sdk",
            return_value={
                "should_reply": True,
                "target_channel_key": "assistant_dm_b",
                "reply_body": "我先记下这些关键信号。",
                "reason_codes": ["post_chat_followup", "persona_capture"],
                "state_patch": {
                    "followup_b_status": "completed",
                    "phase": "post_chat_completed",
                },
                "cooldown_seconds": 300,
                "persona_updates": [
                    {
                        "subject_user_id": "user-b",
                        "source_type": "explicit",
                        "basis": "self_statement",
                        "apply_scope": "persona_only",
                        "patch": {"self_job": "财务相关工作"},
                        "evidence_summary": "用户明确说自己做财务相关工作。",
                    },
                    {
                        "subject_user_id": "user-b",
                        "source_type": "explicit",
                        "basis": "self_statement",
                        "apply_scope": "persona_only",
                        "patch": {"persona_summary_internal": "生活节奏偏规律。"},
                        "evidence_summary": "用户明确说自己平时生活比较规律。",
                    },
                    {
                        "subject_user_id": "user-b",
                        "source_type": "explicit",
                        "basis": "self_statement",
                        "apply_scope": "persona_only",
                        "patch": {"target_accept_long_distance": "不接受"},
                        "evidence_summary": "用户明确说自己不太接受长期异地。",
                    },
                ],
            },
        ):
            decision = run_matchmaker_agent(run_input)

        self.assertEqual(len(decision["persona_updates"]), 3)
        self.assertEqual(
            [item["patch"] for item in decision["persona_updates"]],
            [
                {"self_job": "财务相关工作"},
                {"persona_summary_internal": "生活节奏偏规律。"},
                {"target_accept_long_distance": "不接受"},
            ],
        )

    def test_silence_probe_natural_end_marks_post_chat_ready(self):
        run_input = _make_run_input(
            latest_body="好，改天聊，晚点休息。",
            reason="silence_probe",
        )

        decision = _apply_runtime_policy(
            run_input,
            {
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["natural_ending", "mutual_closure"],
                "state_patch": {},
                "cooldown_seconds": 0,
            },
        )

        self.assertFalse(decision["should_reply"])
        self.assertEqual(decision["state_patch"]["phase"], "post_chat_ready")
        self.assertEqual(decision["state_patch"]["chat_end_message_id"], 178)
        self.assertEqual(decision["state_patch"]["chat_end_at"], "2026-05-09 19:32:10")
        self.assertGreaterEqual(decision["cooldown_seconds"], 1800)
        self.assertFalse(decision["public_followup"]["active"])
        self.assertEqual(decision["public_followup"]["mode"], "silence")


if __name__ == "__main__":
    unittest.main()
