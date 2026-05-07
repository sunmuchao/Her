import json
import pathlib
import sys
import unittest
from datetime import datetime
from unittest.mock import patch

_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from chat_system.dyadic_roleplay import (
    _assistant_follow_assessment,
    _assistant_recovery_assessment,
    _graceful_exit_score,
    _naturalness_assessment,
    _next_dyadic_message,
    dyadic_public_transcript,
    parse_int_csv,
    run_dyadic_roleplay,
    strip_json_object,
)
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN, connect_db, initialize_database, reset_all_tables


class DyadicRoleplayUtilTests(unittest.TestCase):
    def test_parse_int_csv(self):
        self.assertEqual(parse_int_csv(""), [])
        self.assertEqual(parse_int_csv("0,2 ,2"), [0, 2])

    def test_strip_json_object(self):
        d = strip_json_object('前缀 ```json\n{"a": 1}\n``` 后缀')
        self.assertEqual(d, {"a": 1})

    def test_dyadic_public_transcript_filters(self):
        conn = connect_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_database(conn)
        reset_all_tables(conn)
        try:
            from chat_system.service import get_or_create_thread, post_message, SRC_USER, VIS_DYADIC, VIS_OWNER_ONLY

            th = get_or_create_thread(
                conn,
                case_id="dt-filter-1",
                relation_key="x|y",
                participant_a_id="x",
                participant_b_id="y",
                now=datetime(2026, 5, 4, 8, 0, 0),
            )
            tid = th["thread_id"]
            post_message(
                conn,
                tid,
                "x",
                "hello",
                visibility=VIS_DYADIC,
                source=SRC_USER,
                now=datetime(2026, 5, 4, 8, 0, 1),
            )
            post_message(
                conn,
                tid,
                "x",
                "secret",
                visibility=VIS_OWNER_ONLY,
                message_recipient_id="x",
                source=SRC_USER,
                now=datetime(2026, 5, 4, 8, 0, 2),
            )
            conn.commit()
            pub = dyadic_public_transcript(conn, tid, "x")
            self.assertIn("hello", pub)
            self.assertNotIn("secret", pub)
        finally:
            conn.close()

    def test_assistant_follow_assessment_returns_structured_evidence_for_repair(self):
        out = _assistant_follow_assessment(
            "我周末一般会找家店坐坐喝咖啡，你一般怎么放松？",
            {
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "strategy_tags": ["switch_topic", "ask_easy_question"],
                "topic_directions": ["周末安排"],
                "easy_question_types": ["低门槛生活问题"],
                "avoid": ["不要继续追着旧话题硬问。"],
                "profile_hooks_used": ["咖啡"],
            },
            assistant_invoked=True,
        )

        self.assertEqual(out["level"], "strong")
        self.assertIn("周末安排", out["evidence"]["matched_topic_directions"])
        self.assertIn("咖啡", out["evidence"]["matched_profile_hooks"])
        self.assertTrue(out["evidence"]["asked_low_bar_question"])
        self.assertEqual(out["evidence"]["avoid_violations"], [])
        self.assertFalse(out["overpush_risk"]["flag"])

    def test_assistant_follow_assessment_ignores_non_repair_guidance(self):
        out = _assistant_follow_assessment(
            "那你收入大概多少呀？方便发张照片吗？",
            {
                "mutual_intent_assessment": "boundary_risk",
                "interaction_mode": "hold",
                "strategy_tags": ["graceful_exit"],
                "why_not_to_push": ["这轮已经碰到边界，不要继续推进敏感话题。"],
                "avoid": ["不要继续往收入和照片上推。"],
                "graceful_exit_plan": ["先轻轻收住，别再继续追问。"],
            },
            assistant_invoked=True,
        )

        self.assertEqual(out["level"], "not_applicable")
        self.assertIn("non_repair_guidance_out_of_scope", out["signals"])
        self.assertEqual(out["evidence"], {})
        self.assertIsNone(out["overpush_risk"])

    def test_assistant_recovery_assessment_uses_three_turn_window(self):
        out = _assistant_recovery_assessment(
            {
                "speaker": "pa",
                "assistant_invoked": True,
                "assistant_guidance": {"interaction_mode": "repair"},
                "assistant_follow_assessment": {"level": "strong"},
                "follow_evidence": {"applied_strategies": ["switch_topic"]},
            },
            [
                {"speaker": "pb", "generated_message": "嗯"},
                {"speaker": "pa", "generated_message": "我最近周末也会找家店坐坐。"},
                {
                    "speaker": "pb",
                    "generated_message": "那你平时会去喝咖啡吗？我最近也在找这种放松方式。",
                },
            ],
        )

        self.assertEqual(out["label"], "improved")
        self.assertEqual(out["window_turns"], 3)
        self.assertEqual(out["counterpart_reply_count"], 2)
        self.assertTrue(out["first_reply_low_energy"])
        self.assertIn("counterpart_kept_conversation_going", out["signals"])
        self.assertIn("new_topic_got_engagement", out["signals"])

    def test_assistant_recovery_assessment_ignores_non_repair_guidance(self):
        out = _assistant_recovery_assessment(
            {
                "speaker": "pa",
                "assistant_invoked": True,
                "assistant_guidance": {"interaction_mode": "probe_lightly"},
                "assistant_follow_assessment": {"level": "strong"},
                "follow_evidence": {"applied_strategies": ["probe_lightly"]},
            },
            [
                {"speaker": "pb", "generated_message": "嗯"},
                {"speaker": "pa", "generated_message": "好的，那先不打扰你。"},
                {"speaker": "pb", "generated_message": "都行"},
            ],
        )

        self.assertEqual(out["label"], "not_applicable")
        self.assertEqual(out["score"], 0)
        self.assertIn("non_repair_guidance_out_of_scope", out["signals"])

    def test_graceful_exit_score_does_not_reward_boundary_reentry(self):
        self.assertIsNone(
            _graceful_exit_score(
                {
                    "interaction_mode": "hold",
                    "generated_message": "那先这样吧，方便发张照片吗？",
                }
            )
        )

    def test_persona_prompt_contains_naturalness_anti_examples(self):
        captured: dict[str, str] = {}

        def llm(messages: list[dict[str, str]]) -> str:
            captured["system"] = messages[0]["content"]
            captured["user"] = messages[-1]["content"]
            return "你好呀"

        out = _next_dyadic_message(
            llm=llm,
            user_id="pa",
            brief="A",
            transcript="pb: 嗯",
        )

        self.assertEqual(out, "你好呀")
        self.assertIn("低质量反例", captured["system"])
        self.assertIn("你是在认可……吗", captured["system"])
        self.assertIn("首先……其次……总之……", captured["system"])
        self.assertIn("不要解释你为什么这样说", captured["user"])
        self.assertIn("一条消息别做太多事", captured["user"])

    def test_naturalness_assessment_penalizes_analytic_and_explanatory_tone(self):
        out = _naturalness_assessment(
            "我理解你的意思是你现在更想慢慢来，我想表达的是这说明你挺看重稳定感的。"
        )

        self.assertLessEqual(out["score"], 2)
        self.assertIn("analytic_phrase:我理解你的意思是", out["flags"])
        self.assertIn("explanatory_phrase:我想表达的是", out["flags"])
        self.assertIn("meta_commentary", out["flags"])

    def test_naturalness_assessment_penalizes_structured_monologue(self):
        out = _naturalness_assessment(
            "首先我觉得你说得挺真诚的，其次我也能理解这个节奏，总之可以慢慢聊。"
        )

        self.assertLessEqual(out["score"], 3)
        self.assertIn("structured_monologue", out["flags"])


class DyadicRoleplayRunTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_database(self.conn)
        reset_all_tables(self.conn)
        self.assistant_patcher = patch(
            "chat_system.service.generate_assistant_guidance",
            return_value={
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "current_problem": ["测试问题"],
                "problem_tags": ["topic_dead_end"],
                "why_not_to_push": [],
                "low_pressure_options": [],
                "avoid": ["不要继续硬追问"],
                "topic_directions": ["周末安排"],
                "easy_question_types": ["低门槛生活问题"],
                "graceful_exit_plan": ["如果对方还是很冷，就先轻轻收住"],
                "strategy_tags": ["switch_topic", "ask_easy_question"],
                "reply_suggestions": ["测试建议"],
                "profile_hooks_used": ["周末会出门走走"],
            },
        )
        self.assistant_patcher.start()

    def tearDown(self):
        self.assistant_patcher.stop()
        self.conn.close()

    def _mock_llm(self, *, rescue_on_first: bool = False):
        orch_calls = {"n": 0}

        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c and "下一位即将发言的用户ID" in user_c:
                orch_calls["n"] += 1
                if rescue_on_first and orch_calls["n"] == 1:
                    return json.dumps(
                        {
                            "need_rescue": True,
                            "situation": "cold",
                            "mutual_intent_assessment": "communication_problem",
                            "interaction_mode": "repair",
                            "rescue_style": "switch_topic",
                            "reason": "测试触发救场",
                        },
                        ensure_ascii=False,
                    )
                return json.dumps(
                    {
                        "need_rescue": False,
                        "situation": "none",
                        "mutual_intent_assessment": "normal",
                        "interaction_mode": "none",
                        "rescue_style": "none",
                        "reason": "流畅",
                    },
                    ensure_ascii=False,
                )
            if "请写出下一条" in user_c:
                return "回合测试消息"
            if "附加任务" in sys_c and "请输出 JSON" in user_c:
                if "「pa」" in sys_c:
                    return json.dumps(
                        {
                            "conversation_satisfied": True,
                            "conversation_score": 4,
                            "assistant_satisfied": True,
                            "assistant_score": 4,
                            "used_assistant": True,
                            "conversation_note": "ok",
                            "assistant_note": "ok",
                        },
                        ensure_ascii=False,
                    )
                return json.dumps(
                    {
                        "conversation_satisfied": False,
                        "conversation_score": 2,
                        "assistant_satisfied": True,
                        "assistant_score": 3,
                        "used_assistant": False,
                        "conversation_note": "一般",
                        "assistant_note": "未用",
                    },
                    ensure_ascii=False,
                )
            return "{}"

        return llm, orch_calls

    def test_run_proactive_no_rescue(self):
        llm, orch = self._mock_llm(rescue_on_first=False)
        with patch("chat_system.dyadic_roleplay.fast_mode_route", return_value=None):
            out = run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-rp-pro",
                relation_key="pa|pb",
                participant_a_id="pa",
                participant_b_id="pb",
                brief_a="A",
                brief_b="B",
                rounds=3,
                llm=llm,
                assistant_mode="proactive",
                base_time=datetime(2026, 5, 4, 9, 0, 0),
                stress_mode="none",
            )
        self.assertEqual(len(out["proactive_rescue_events"]), 0)
        self.assertGreater(orch["n"], 0)
        self.assertTrue(out["evaluation"]["pa"]["conversation_satisfied"])
        self.assertFalse(out["thread_reused"])
        self.assertEqual(out["base_time"], "2026-05-04 09:00:00")
        self.assertEqual(out["stress_mode"], "none")
        self.assertEqual(out["stress_events"], [])
        self.assertIn("assistant_metrics", out)
        self.assertIn("naturalness_metrics", out)
        self.assertIn("roleplay_experiment", out)
        self.assertEqual(out["turn_evaluation_schema_version"], 1)
        self.assertIn("shared", out["turn_evaluation_field_groups"])
        self.assertIn("roleplay", out["turn_evaluation_field_groups"])
        self.assertEqual(len(out["turn_evaluations"]), 3)
        self.assertIn("shared_evaluation", out["turn_evaluations"][0])
        self.assertIn("roleplay_evaluation", out["turn_evaluations"][0])
        self.assertIn("simulated_reply_mode_alignment", out["turn_evaluations"][0]["roleplay_evaluation"])
        self.assertIn("turn_index", out["turn_evaluations"][0])
        self.assertIn("interaction_mode_gold", out["turn_evaluations"][0])
        self.assertIn("interaction_mode_pred", out["turn_evaluations"][0])
        self.assertIn("recovery_score_1to3_turns", out["turn_evaluations"][0])
        self.assertIn("graceful_exit_score", out["turn_evaluations"][0])
        self.assertFalse(out["roleplay_experiment"]["simulated_reply_reads_interaction_mode"])
        self.assertEqual(out["assistant_metrics"]["simulated_reply_mode_prompted_turns"], 0)
        self.assertTrue(
            all(
                (turn.get("assistant_follow_assessment") or {}).get("level") == "not_applicable"
                for turn in out["turn_evaluations"]
            )
        )

    def test_run_proactive_rescue_triggers_assistant(self):
        llm, _orch = self._mock_llm(rescue_on_first=True)
        with patch("chat_system.dyadic_roleplay.fast_mode_route", return_value=None):
            out = run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-rp-rescue",
                relation_key="pa|pb",
                participant_a_id="pa",
                participant_b_id="pb",
                brief_a="A",
                brief_b="B",
                rounds=2,
                llm=llm,
                assistant_mode="proactive",
                base_time=datetime(2026, 5, 4, 9, 0, 0),
                stress_mode="none",
            )
        self.assertEqual(len(out["proactive_rescue_events"]), 1)
        from chat_system.service import list_messages

        invoked_turn = next(turn for turn in out["turn_evaluations"] if turn.get("assistant_invoked"))
        owner_msgs = list_messages(self.conn, out["thread_id"], invoked_turn["speaker"], limit=50)
        authors_sources = [(m["author_id"], m["source"]) for m in owner_msgs]
        self.assertTrue(any(a == "assistant" for a, _ in authors_sources))
        self.assertEqual(out["assistant_metrics"]["predicted_rescue_turns"], 1)
        self.assertIsNotNone(out["assistant_metrics"]["assistant_invoke_avg_ms"])
        self.assertTrue(any("assistant_latency_ms" in turn for turn in out["turn_evaluations"]))
        self.assertEqual(invoked_turn["assistant_mode_compliance"], "compliant")
        self.assertIn(
            "assistant_mode_compliance_details",
            invoked_turn["roleplay_evaluation"],
        )

    def test_run_proactive_t12_hint_events_and_metrics(self):
        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "请写出下一条" in user_c:
                return "我周末一般会去喝咖啡，你平时怎么放松？"
            if "附加任务" in sys_c and "请输出 JSON" in user_c:
                return json.dumps(
                    {
                        "conversation_satisfied": True,
                        "conversation_score": 3,
                        "assistant_satisfied": True,
                        "assistant_score": 3,
                        "used_assistant": True,
                        "conversation_note": "ok",
                        "assistant_note": "ok",
                    },
                    ensure_ascii=False,
                )
            return "{}"

        route_decisions = [
            {
                "need_rescue": True,
                "situation": "stuck",
                "problem_tags": ["topic_dead_end"],
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "rescue_style": "switch_topic",
                "reason": "双方还想聊，但这轮卡住了",
                "decision_source": "heuristic_test",
            },
            {
                "need_rescue": False,
                "situation": "none",
                "problem_tags": [],
                "mutual_intent_assessment": "normal",
                "interaction_mode": "none",
                "rescue_style": "none",
                "reason": "正常",
                "decision_source": "heuristic_test",
            },
            {
                "need_rescue": True,
                "situation": "stuck",
                "problem_tags": ["topic_dead_end"],
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "rescue_style": "switch_topic",
                "reason": "还是卡住",
                "decision_source": "heuristic_test",
            },
            {
                "need_rescue": False,
                "situation": "none",
                "problem_tags": [],
                "mutual_intent_assessment": "normal",
                "interaction_mode": "none",
                "rescue_style": "none",
                "reason": "不属于回温助手职责",
                "decision_source": "heuristic_test",
            },
            {
                "need_rescue": False,
                "situation": "none",
                "problem_tags": [],
                "mutual_intent_assessment": "normal",
                "interaction_mode": "none",
                "rescue_style": "none",
                "reason": "正常",
                "decision_source": "heuristic_test",
            },
            {
                "need_rescue": True,
                "situation": "stuck",
                "problem_tags": ["topic_dead_end"],
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "rescue_style": "switch_topic",
                "reason": "最后一轮又卡住了",
                "decision_source": "heuristic_test",
            },
        ]

        def guidance_for_query(*args, **kwargs):
            return {
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "current_problem": ["这轮接话卡住了。"],
                "problem_tags": ["topic_dead_end"],
                "advice": ["先接住，再换轻一点的话题。"],
                "avoid": ["不要继续追着旧话题硬问。"],
                "topic_directions": ["周末安排"],
                "easy_question_types": ["低门槛生活问题"],
                "rescue_flow": ["先接住", "再换题", "最后轻问一句"],
                "strategy_tags": ["switch_topic", "ask_easy_question"],
            }

        with patch("chat_system.dyadic_roleplay.fast_mode_route", side_effect=route_decisions), patch(
            "chat_system.service.generate_assistant_guidance",
            side_effect=guidance_for_query,
        ):
            out = run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-rp-t12",
                relation_key="pa|pb",
                participant_a_id="pa",
                participant_b_id="pb",
                brief_a="A",
                brief_b="B",
                rounds=6,
                llm=llm,
                assistant_mode="proactive",
                base_time=datetime(2026, 5, 6, 9, 0, 0),
                stress_mode="none",
            )

        self.assertEqual(len(out["proactive_rescue_events"]), 2)
        first_turn = out["turn_evaluations"][0]
        self.assertTrue(first_turn["hint_posted"])
        self.assertEqual(first_turn["trigger_type"], "mode_change")
        self.assertIsNone(first_turn["suppression_reason"])

        third_turn = out["turn_evaluations"][2]
        self.assertFalse(third_turn["hint_posted"])
        self.assertEqual(third_turn["suppression_reason"], "no_new_value_after_strong_follow")

        sixth_turn = out["turn_evaluations"][5]
        self.assertTrue(sixth_turn["hint_posted"])
        self.assertEqual(sixth_turn["hint_trigger_event"]["mode_after"], "repair")
        self.assertIsNone(sixth_turn["suppression_reason"])

        metrics = out["assistant_metrics"]
        self.assertEqual(metrics["hint_candidate_turns"], 6)
        self.assertEqual(metrics["hint_posted_turns"], 2)
        self.assertEqual(metrics["mode_change_hint_turns"], 2)
        self.assertEqual(metrics["duplicate_suppressed_turns"], 1)
        self.assertGreater(metrics["hint_trigger_rate"], 0)
        self.assertGreater(metrics["duplicate_hint_rate"], 0)
        self.assertGreater(metrics["mode_change_hint_rate"], 0)
        self.assertEqual(metrics["repair_intervention_turns"], 2)
        self.assertIn("visible_text_view", metrics)
        self.assertIn("stress_beat_view", metrics)

    def test_roleplay_mode_alignment_experiment_switches_prompt_and_metrics(self):
        repair_hint = {
            "message_id": "asst-repair-alignment",
            "assistant_guidance": {
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "current_problem": ["这轮接话卡住了。"],
                "advice": ["先接住，再换轻一点的话题。"],
                "avoid": ["不要继续追着旧话题硬问。"],
                "topic_directions": ["周末安排"],
                "easy_question_types": ["低门槛生活问题"],
                "rescue_flow": ["先接住", "再换题", "最后轻问一句"],
                "strategy_tags": ["switch_topic", "ask_easy_question"],
            },
            "assistant_profile_context": {},
            "assistant_route_decision": {
                "need_rescue": True,
                "mutual_intent_assessment": "communication_problem",
                "interaction_mode": "repair",
                "rescue_style": "switch_topic",
                "problem_tags": ["topic_dead_end"],
                "reason": "测试 repair 模式提示",
                "decision_source": "test_fixed_turn",
            },
        }

        def build_llm(prompts: list[str]):
            def llm(messages: list[dict[str, str]]) -> str:
                sys_c = messages[0]["content"]
                user_c = messages[-1]["content"]
                if "请写出下一条" in user_c:
                    prompts.append(user_c)
                    if "【仅用于离线 roleplay 评测的额外模式提示】" in user_c and "当前模式：repair" in user_c:
                        return "我周末也会出去走走，你一般怎么放松？"
                    return "嗯"
                if "附加任务" in sys_c and "请输出 JSON" in user_c:
                    return json.dumps(
                        {
                            "conversation_satisfied": True,
                            "conversation_score": 3,
                            "assistant_satisfied": True,
                            "assistant_score": 3,
                            "used_assistant": True,
                            "conversation_note": "ok",
                            "assistant_note": "ok",
                        },
                        ensure_ascii=False,
                    )
                return "{}"

            return llm

        prompts_off: list[str] = []
        with patch("chat_system.dyadic_roleplay.assistant_query", return_value=repair_hint):
            out_off = run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-mode-align-off",
                relation_key="pa|pb",
                participant_a_id="pa",
                participant_b_id="pb",
                brief_a="A",
                brief_b="B",
                rounds=1,
                llm=build_llm(prompts_off),
                assistant_mode="fixed_turns",
                fixed_assistant_turns=[0],
                base_time=datetime(2026, 5, 4, 9, 0, 0),
                stress_mode="none",
                simulate_reply_reads_interaction_mode=False,
            )

        prompts_on: list[str] = []
        with patch("chat_system.dyadic_roleplay.assistant_query", return_value=repair_hint):
            out_on = run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-mode-align-on",
                relation_key="pa|pb",
                participant_a_id="pa",
                participant_b_id="pb",
                brief_a="A",
                brief_b="B",
                rounds=1,
                llm=build_llm(prompts_on),
                assistant_mode="fixed_turns",
                fixed_assistant_turns=[0],
                base_time=datetime(2026, 5, 4, 9, 0, 0),
                stress_mode="none",
                simulate_reply_reads_interaction_mode=True,
            )

        self.assertEqual(len(prompts_off), 1)
        self.assertNotIn("【仅用于离线 roleplay 评测的额外模式提示】", prompts_off[0])
        self.assertFalse(out_off["roleplay_experiment"]["simulated_reply_reads_interaction_mode"])
        self.assertEqual(out_off["assistant_metrics"]["simulated_reply_mode_prompted_turns"], 0)
        self.assertEqual(out_off["assistant_metrics"]["simulated_reply_mode_applicable_turns"], 1)
        self.assertEqual(out_off["assistant_metrics"]["simulated_reply_mode_alignment_rate"], 0.0)
        self.assertFalse(out_off["turn_evaluations"][0]["simulated_reply_mode_prompted"])
        self.assertEqual(
            out_off["turn_evaluations"][0]["simulated_reply_mode_alignment"]["label"],
            "misaligned",
        )

        self.assertEqual(len(prompts_on), 1)
        self.assertIn("【仅用于离线 roleplay 评测的额外模式提示】", prompts_on[0])
        self.assertIn("当前模式：repair", prompts_on[0])
        self.assertTrue(out_on["roleplay_experiment"]["simulated_reply_reads_interaction_mode"])
        self.assertEqual(out_on["assistant_metrics"]["simulated_reply_mode_prompted_turns"], 1)
        self.assertEqual(out_on["assistant_metrics"]["simulated_reply_mode_applicable_turns"], 1)
        self.assertEqual(out_on["assistant_metrics"]["simulated_reply_mode_alignment_rate"], 1.0)
        self.assertEqual(out_on["assistant_metrics"]["simulated_reply_mode_strong_alignment_rate"], 1.0)
        self.assertTrue(out_on["turn_evaluations"][0]["simulated_reply_mode_prompted"])
        self.assertEqual(
            out_on["turn_evaluations"][0]["simulated_reply_mode_alignment"]["label"],
            "aligned",
        )
        self.assertEqual(out_on["roleplay_experiment"]["reply_experiment_mode"], "mode_hint")

    def test_roleplay_controlled_experiment_includes_guided_execution_block(self):
        prompts: list[str] = []

        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "请写出下一条" in user_c:
                prompts.append(user_c)
                return "那这个话题先不展开了，先这样吧。"
            if "附加任务" in sys_c and "请输出 JSON" in user_c:
                return json.dumps(
                    {
                        "conversation_satisfied": True,
                        "conversation_score": 3,
                        "assistant_satisfied": True,
                        "assistant_score": 3,
                        "used_assistant": True,
                        "conversation_note": "ok",
                        "assistant_note": "ok",
                    },
                    ensure_ascii=False,
                )
            return "{}"

        with patch(
            "chat_system.dyadic_roleplay.assistant_query",
            return_value={
                "message_id": "asst-repair-guided",
                "assistant_guidance": {
                    "mutual_intent_assessment": "communication_problem",
                    "interaction_mode": "repair",
                    "current_problem": ["这轮接话卡住了。"],
                    "advice": ["先接住，再换轻一点的话题。"],
                    "avoid": ["不要继续追着旧话题硬问。"],
                    "topic_directions": ["周末安排"],
                    "easy_question_types": ["低门槛生活问题"],
                    "rescue_flow": ["先接住", "再换题", "最后轻问一句"],
                    "strategy_tags": ["switch_topic", "ask_easy_question"],
                },
                "assistant_profile_context": {},
            },
        ):
            out = run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-controlled-mode",
                relation_key="pa|pb",
                participant_a_id="pa",
                participant_b_id="pb",
                brief_a="A",
                brief_b="B",
                rounds=1,
                llm=llm,
                assistant_mode="fixed_turns",
                fixed_assistant_turns=[0],
                base_time=datetime(2026, 5, 4, 9, 0, 0),
                stress_mode="none",
                reply_experiment_mode="controlled",
            )

        self.assertEqual(out["roleplay_experiment"]["reply_experiment_mode"], "controlled")
        self.assertTrue(out["roleplay_experiment"]["simulated_reply_reads_interaction_mode"])
        self.assertEqual(out["turn_evaluations"][0]["reply_experiment_mode"], "controlled")
        self.assertIn("实验模式：controlled", prompts[0])
        self.assertIn("如果 assistant 给了方向", prompts[0])

    def test_fixed_turn_non_repair_guidance_is_scoped_out(self):
        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "请写出下一条" in user_c:
                return "感觉今天有点卡。"
            if "附加任务" in sys_c and "请输出 JSON" in user_c:
                return json.dumps(
                    {
                        "conversation_satisfied": True,
                        "conversation_score": 3,
                        "assistant_satisfied": True,
                        "assistant_score": 3,
                        "used_assistant": True,
                        "conversation_note": "ok",
                        "assistant_note": "ok",
                    },
                    ensure_ascii=False,
                )
            return "{}"

        with patch(
            "chat_system.dyadic_roleplay.assistant_query",
            return_value={
                "message_id": "asst-old-hold-guidance",
                "assistant_guidance": {
                    "mutual_intent_assessment": "boundary_risk",
                    "interaction_mode": "hold",
                    "current_problem": ["这轮已经碰到边界，不适合继续推进。"],
                    "advice": ["这轮先收住，别再往前顶。"],
                    "avoid": ["不要继续追问照片。"],
                    "strategy_tags": ["graceful_exit"],
                },
                "assistant_profile_context": {},
            },
        ):
            out = run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-old-hold-guidance-scoped-out",
                relation_key="pa|pb",
                participant_a_id="pa",
                participant_b_id="pb",
                brief_a="A",
                brief_b="B",
                rounds=1,
                llm=llm,
                assistant_mode="fixed_turns",
                fixed_assistant_turns=[0],
                base_time=datetime(2026, 5, 4, 9, 0, 0),
                stress_mode="none",
            )

        turn = out["turn_evaluations"][0]
        self.assertEqual(turn["interaction_mode"], "none")
        self.assertEqual(turn["mutual_intent_assessment"], "normal")
        self.assertEqual(turn["assistant_mode_compliance"], "drifted")
        self.assertEqual((turn["assistant_follow_assessment"] or {}).get("level"), "not_applicable")
        self.assertEqual(out["assistant_metrics"]["recoverable_intervention_turns"], 0)

    def test_stress_manifestation_and_speaker_state_are_recorded(self):
        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "请写出下一条" in user_c:
                return "家里最近一直催相亲，周末安排也不太好定。"
            if "附加任务" in sys_c and "请输出 JSON" in user_c:
                return json.dumps(
                    {
                        "conversation_satisfied": True,
                        "conversation_score": 3,
                        "assistant_satisfied": True,
                        "assistant_score": 3,
                        "used_assistant": False,
                        "conversation_note": "ok",
                        "assistant_note": "ok",
                    },
                    ensure_ascii=False,
                )
            return "{}"

        out = run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-stress-manifest",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=2,
            llm=llm,
            assistant_mode="none",
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            stress_mode="rotate",
            stress_beat_ids=["family_pressure"],
        )

        first_turn = out["turn_evaluations"][0]
        second_turn = out["turn_evaluations"][1]
        self.assertIn("speaker_state_before", first_turn)
        self.assertIn("speaker_state_after", first_turn)
        self.assertTrue(first_turn["stress_manifestation"]["manifested"])
        self.assertIn("家里", first_turn["stress_manifestation"]["matched_signals"])
        self.assertIn("manifested_stress_gold_decision", second_turn)
        self.assertGreaterEqual(
            (out["assistant_metrics"].get("stress_beat_manifestation_rate") or 0),
            1.0,
        )

    def test_run_fixed_turns(self):
        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c:
                return "{}"
            if "请写出下一条" in user_c:
                return "固定回合消息"
            if "附加任务" in sys_c and "「pa」" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":3,"used_assistant":true,"conversation_note":"","assistant_note":""}'
            if "附加任务" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":3,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            return "{}"

        out = run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-rp-fixed",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=3,
            llm=llm,
            assistant_mode="fixed_turns",
            fixed_assistant_turns=[0],
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            stress_mode="none",
        )
        self.assertEqual(out["fixed_assistant_turns"], [0])
        self.assertEqual(out["proactive_rescue_events"], [])

    def test_stress_rotate_logs_each_turn(self):
        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c:
                return '{"need_rescue":false,"situation":"none","reason":""}'
            if "请写出下一条" in user_c:
                return "压力回合回复"
            if "附加任务" in sys_c and "「pa」" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":3,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            if "附加任务" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":3,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            return "{}"

        out = run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-stress",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=4,
            llm=llm,
            assistant_mode="none",
            stress_mode="rotate",
            stress_seed=1,
            base_time=datetime(2026, 5, 4, 9, 0, 0),
        )
        self.assertEqual(out["stress_mode"], "rotate")
        self.assertEqual(len(out["stress_events"]), 4)
        self.assertIn("beat_id", out["stress_events"][0])
        self.assertIn("severity", out["stress_events"][0])
        self.assertIn("expected_mutual_intent_assessment", out["stress_events"][0])
        self.assertIn("expected_interaction_mode", out["stress_events"][0])
        self.assertIn("expected_mutual_intent_assessment", out["turn_evaluations"][0]["gold_rescue"])
        self.assertIn("expected_interaction_mode", out["turn_evaluations"][0]["gold_rescue"])

    def test_fast_rescue_uses_heuristic_on_cold_reply(self):
        calls = {"orchestrator": 0, "message": 0}

        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c:
                calls["orchestrator"] += 1
                return '{"need_rescue":false,"situation":"none","reason":"不该被调用"}'
            if "请写出下一条" in user_c:
                calls["message"] += 1
                if calls["message"] == 1:
                    return "嗯"
                return "我平时周末会去打羽毛球，你一般怎么放松？"
            if "附加任务" in sys_c and "「pa」" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":4,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            if "附加任务" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":4,"used_assistant":true,"conversation_note":"","assistant_note":""}'
            return "{}"

        out = run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-heuristic-rescue",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=2,
            llm=llm,
            assistant_mode="proactive",
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            stress_mode="none",
        )
        self.assertEqual(calls["orchestrator"], 0)
        self.assertEqual(len(out["proactive_rescue_events"]), 0)
        self.assertEqual(out["turn_evaluations"][1]["rescue_decision_source"], "heuristic_scope_filter")
        self.assertEqual(out["turn_evaluations"][1]["interaction_mode"], "none")
        self.assertEqual(out["turn_evaluations"][1]["mutual_intent_assessment"], "normal")
        self.assertEqual(out["assistant_metrics"]["heuristic_decision_turns"], 2)
        self.assertEqual(out["assistant_metrics"]["llm_decision_turns"], 0)
        self.assertEqual(out["assistant_metrics"]["repair_intervention_turns"], 0)
        self.assertIn("follow_evidence", out["turn_evaluations"][1]["roleplay_evaluation"])
        self.assertIn("overpush_risk", out["turn_evaluations"][1]["roleplay_evaluation"])
        self.assertIsNone(out["turn_evaluations"][1]["follow_level"])
        self.assertEqual(out["assistant_metrics"]["followed_intervention_turns"], 0)
        self.assertEqual(out["assistant_metrics"]["follow_rate"], None)
        self.assertEqual(out["assistant_metrics"]["avoid_violation_turns"], 0)

    def test_heuristic_repair_after_prior_mutual_engagement(self):
        calls = {"orchestrator": 0, "message": 0}

        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c:
                calls["orchestrator"] += 1
                return '{"need_rescue":false,"situation":"none","reason":"不该被调用"}'
            if "请写出下一条" in user_c:
                calls["message"] += 1
                if calls["message"] == 1:
                    return "我周末一般会打羽毛球，你平时怎么放松？"
                if calls["message"] == 2:
                    return "我一般会出去走走，有时找家店坐会儿喝咖啡。"
                if calls["message"] == 3:
                    return "那还挺舒服的，我最近也会这样慢一点。"
                if calls["message"] == 4:
                    return "嗯"
                return "我周末也挺随性的。"
            if "附加任务" in sys_c and "「pa」" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":4,"used_assistant":true,"conversation_note":"","assistant_note":""}'
            if "附加任务" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":4,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            return "{}"

        out = run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-heuristic-repair",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=5,
            llm=llm,
            assistant_mode="proactive",
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            stress_mode="none",
        )
        self.assertEqual(calls["orchestrator"], 0)
        self.assertTrue(out["turn_evaluations"][4]["assistant_invoked"])
        self.assertEqual(out["turn_evaluations"][4]["interaction_mode"], "repair")
        self.assertEqual(
            out["turn_evaluations"][4]["mutual_intent_assessment"],
            "communication_problem",
        )
        self.assertIn(
            "missed_connection",
            (out["turn_evaluations"][4]["rescue_decision"] or {}).get("problem_tags", []),
        )
        self.assertEqual(out["assistant_metrics"]["repair_intervention_turns"], 1)

    def test_heuristic_repair_on_salvageable_awkward_start(self):
        calls = {"orchestrator": 0, "message": 0}

        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c:
                calls["orchestrator"] += 1
                return '{"need_rescue":false,"situation":"none","reason":"不该被调用"}'
            if "请写出下一条" in user_c:
                calls["message"] += 1
                if calls["message"] == 1:
                    return "你好"
                if calls["message"] == 2:
                    return "嗯。你周末都干嘛"
                if calls["message"] == 3:
                    return "睡觉。"
                return "补觉吧，平时太累了。你呢？"
            if "附加任务" in sys_c and "「pa」" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":2,"assistant_satisfied":true,"assistant_score":4,"used_assistant":true,"conversation_note":"","assistant_note":""}'
            if "附加任务" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":2,"assistant_satisfied":true,"assistant_score":4,"used_assistant":true,"conversation_note":"","assistant_note":""}'
            return "{}"

        out = run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-heuristic-awkward-start-repair",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=3,
            llm=llm,
            assistant_mode="proactive",
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            stress_mode="none",
        )
        self.assertEqual(calls["orchestrator"], 0)
        self.assertTrue(out["turn_evaluations"][2]["assistant_invoked"])
        self.assertEqual(out["turn_evaluations"][2]["interaction_mode"], "repair")
        self.assertEqual(
            out["turn_evaluations"][2]["mutual_intent_assessment"],
            "communication_problem",
        )
        self.assertIn(
            "awkward_transition",
            (out["turn_evaluations"][2]["rescue_decision"] or {}).get("problem_tags", []),
        )
        self.assertEqual(out["assistant_metrics"]["repair_intervention_turns"], 1)

    def test_heuristic_skips_repeated_low_interest_out_of_scope(self):
        calls = {"orchestrator": 0, "message": 0}

        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c:
                calls["orchestrator"] += 1
                return '{"need_rescue":false,"situation":"none","reason":"不该被调用"}'
            if "请写出下一条" in user_c:
                calls["message"] += 1
                if calls["message"] == 1:
                    return "你好，我周末一般会出去走走。"
                if calls["message"] == 2:
                    return "嗯"
                if calls["message"] == 3:
                    return "我一般就随便走走，你呢？"
                if calls["message"] == 4:
                    return "都行"
                return "那先这样。"
            if "附加任务" in sys_c and "「pa」" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":2,"assistant_satisfied":true,"assistant_score":3,"used_assistant":true,"conversation_note":"","assistant_note":""}'
            if "附加任务" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":2,"assistant_satisfied":true,"assistant_score":3,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            return "{}"

        out = run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-heuristic-low-interest-scope-filter",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=5,
            llm=llm,
            assistant_mode="proactive",
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            stress_mode="none",
        )
        self.assertEqual(calls["orchestrator"], 0)
        self.assertFalse(out["turn_evaluations"][4]["assistant_invoked"])
        self.assertEqual(out["turn_evaluations"][4]["interaction_mode"], "none")
        self.assertEqual(out["turn_evaluations"][4]["mutual_intent_assessment"], "normal")
        self.assertEqual(out["assistant_metrics"]["repair_intervention_turns"], 1)
        self.assertEqual(out["assistant_metrics"]["overpush_risk_turns"], 0)

    def test_run_survives_message_timeout_with_fallback(self):
        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c:
                return '{"need_rescue":false,"situation":"none","rescue_style":"none","reason":""}'
            if "请写出下一条" in user_c:
                raise TimeoutError("message timeout")
            if "附加任务" in sys_c and "「pa」" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":3,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            if "附加任务" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":3,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            return "{}"

        out = run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-fallback-message",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=1,
            llm=llm,
            assistant_mode="none",
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            stress_mode="none",
        )
        self.assertEqual(out["turn_evaluations"][0]["message_generation_source"], "fallback")
        self.assertIn("message timeout", out["turn_evaluations"][0]["message_generation_error"])
        self.assertTrue(out["turn_evaluations"][0]["generated_message"])
        self.assertEqual(out["assistant_metrics"]["fallback_message_turns"], 1)

    def test_run_reports_naturalness_flags_for_analytic_reply(self):
        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c:
                return '{"need_rescue":false,"situation":"none","reason":""}'
            if "请写出下一条" in user_c:
                return "我理解你的意思是你现在想慢慢来，我想表达的是这样聊会更稳一点。"
            if "附加任务" in sys_c and "「pa」" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":3,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            if "附加任务" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":3,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            return "{}"

        out = run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-naturalness-flags",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=1,
            llm=llm,
            assistant_mode="none",
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            stress_mode="none",
        )

        flagged = out["naturalness_metrics"]["flagged_turns"]
        self.assertEqual(len(flagged), 1)
        self.assertIn("analytic_phrase:我理解你的意思是", flagged[0]["flags"])
        self.assertLessEqual((out["turn_evaluations"][0]["naturalness"] or {}).get("score") or 5, 2)

    def test_fixed_turn_old_hold_guidance_becomes_none_mode(self):
        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c:
                return "{}"
            if "请写出下一条" in user_c:
                return "感觉今天节奏有点慢。"
            if "附加任务" in sys_c and "「pa」" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":4,"used_assistant":true,"conversation_note":"","assistant_note":""}'
            if "附加任务" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":4,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            return "{}"

        with patch(
            "chat_system.dyadic_roleplay.assistant_query",
            return_value={
                "message_id": "asst-hold-1",
                "assistant_guidance": {
                    "mutual_intent_assessment": "interest_low",
                    "interaction_mode": "hold",
                    "strategy_tags": ["graceful_exit"],
                    "why_not_to_push": ["对方当前投入偏低，不要继续往下推。"],
                    "avoid": ["不要继续追问，也不要切回敏感话题。"],
                    "graceful_exit_plan": ["先轻轻收住。"],
                },
                "assistant_profile_context": {},
            },
        ):
            out = run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-fixed-hold-exit",
                relation_key="pa|pb",
                participant_a_id="pa",
                participant_b_id="pb",
                brief_a="A",
                brief_b="B",
                rounds=1,
                llm=llm,
                assistant_mode="fixed_turns",
                fixed_assistant_turns=[0],
                base_time=datetime(2026, 5, 4, 9, 0, 0),
                stress_mode="none",
            )
        self.assertEqual(out["turn_evaluations"][0]["interaction_mode"], "none")
        self.assertEqual(out["turn_evaluations"][0]["assistant_mode_compliance"], "drifted")
        self.assertIsNone(out["turn_evaluations"][0]["graceful_exit_score"])
        self.assertEqual(out["assistant_metrics"]["recoverable_intervention_turns"], 0)

    def test_fixed_turn_old_hold_guidance_still_marks_no_repair_follow(self):
        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c:
                return "{}"
            if "请写出下一条" in user_c:
                return "那你收入大概多少？方便发张照片吗？"
            if "附加任务" in sys_c and "「pa」" in sys_c:
                return '{"conversation_satisfied":false,"conversation_score":2,"assistant_satisfied":false,"assistant_score":1,"used_assistant":true,"conversation_note":"","assistant_note":""}'
            if "附加任务" in sys_c:
                return '{"conversation_satisfied":false,"conversation_score":2,"assistant_satisfied":false,"assistant_score":1,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            return "{}"

        with patch(
            "chat_system.dyadic_roleplay.assistant_query",
            return_value={
                "message_id": "asst-hold-2",
                "assistant_guidance": {
                    "mutual_intent_assessment": "boundary_risk",
                    "interaction_mode": "hold",
                    "strategy_tags": ["graceful_exit"],
                    "why_not_to_push": ["这轮已经碰到边界，不要继续推进敏感话题。"],
                    "avoid": ["不要继续往收入和照片上推。"],
                    "graceful_exit_plan": ["先轻轻收住，别再继续追问。"],
                },
                "assistant_profile_context": {},
            },
        ):
            out = run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-fixed-hold-overpush",
                relation_key="pa|pb",
                participant_a_id="pa",
                participant_b_id="pb",
                brief_a="A",
                brief_b="B",
                rounds=1,
                llm=llm,
                assistant_mode="fixed_turns",
                fixed_assistant_turns=[0],
                base_time=datetime(2026, 5, 4, 9, 0, 0),
                stress_mode="none",
            )

        self.assertEqual(out["turn_evaluations"][0]["interaction_mode"], "none")
        self.assertEqual((out["turn_evaluations"][0]["assistant_follow_assessment"] or {}).get("level"), "not_applicable")
        self.assertEqual(out["assistant_metrics"]["overpush_risk_turns"], 0)
        self.assertIsNone(out["turn_evaluations"][0]["overpush_risk"])

    def test_orchestrator_timeout_falls_back_without_aborting(self):
        calls = {"message": 0}

        def llm(messages: list[dict[str, str]]) -> str:
            sys_c = messages[0]["content"]
            user_c = messages[-1]["content"]
            if "对话调度员" in sys_c:
                raise TimeoutError("orchestrator timeout")
            if "请写出下一条" in user_c:
                calls["message"] += 1
                if calls["message"] == 1:
                    return "工作有点多。"
                return "你好呀"
            if "附加任务" in sys_c and "「pa」" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":3,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            if "附加任务" in sys_c:
                return '{"conversation_satisfied":true,"conversation_score":3,"assistant_satisfied":true,"assistant_score":3,"used_assistant":false,"conversation_note":"","assistant_note":""}'
            return "{}"

        with patch("chat_system.dyadic_roleplay.fast_mode_route", return_value=None):
            out = run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-fallback-orchestrator",
                relation_key="pa|pb",
                participant_a_id="pa",
                participant_b_id="pb",
                brief_a="A",
                brief_b="B",
                rounds=2,
                llm=llm,
                assistant_mode="proactive",
                base_time=datetime(2026, 5, 4, 9, 0, 0),
                stress_mode="none",
        )
        self.assertEqual(out["turn_evaluations"][1]["rescue_decision_source"], "llm_error_fallback")
        self.assertEqual(out["assistant_metrics"]["llm_error_fallback_turns"], 2)

    def test_run_rejects_existing_case_by_default(self):
        llm, _orch = self._mock_llm(rescue_on_first=False)
        run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-rp-existing",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=1,
            llm=llm,
            assistant_mode="none",
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            stress_mode="none",
        )
        with self.assertRaisesRegex(ValueError, "roleplay refuses to append by default"):
            run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-rp-existing",
                relation_key="pa|pb",
                participant_a_id="pa",
                participant_b_id="pb",
                brief_a="A",
                brief_b="B",
                rounds=1,
                llm=llm,
                assistant_mode="none",
                base_time=datetime(2026, 5, 4, 9, 0, 0),
                stress_mode="none",
            )

    def test_run_can_resume_matching_case_explicitly(self):
        llm, _orch = self._mock_llm(rescue_on_first=False)
        out1 = run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-rp-resume",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=1,
            llm=llm,
            assistant_mode="none",
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            stress_mode="none",
        )
        out2 = run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-rp-resume",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=1,
            llm=llm,
            assistant_mode="none",
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            resume_existing=True,
            stress_mode="none",
        )
        self.assertEqual(out1["thread_id"], out2["thread_id"])
        self.assertTrue(out2["thread_reused"])
        self.assertEqual(out2["base_time"], "2026-05-04 09:00:01")

    def test_run_resume_rejects_mismatched_existing_case(self):
        llm, _orch = self._mock_llm(rescue_on_first=False)
        run_dyadic_roleplay(
            self.conn,
            case_id="test-dyadic-rp-mismatch",
            relation_key="pa|pb",
            participant_a_id="pa",
            participant_b_id="pb",
            brief_a="A",
            brief_b="B",
            rounds=1,
            llm=llm,
            assistant_mode="none",
            base_time=datetime(2026, 5, 4, 9, 0, 0),
            stress_mode="none",
        )
        with self.assertRaisesRegex(ValueError, "does not match the requested roleplay participants"):
            run_dyadic_roleplay(
                self.conn,
                case_id="test-dyadic-rp-mismatch",
                relation_key="pa|pc",
                participant_a_id="pa",
                participant_b_id="pc",
                brief_a="A",
                brief_b="C",
                rounds=1,
                llm=llm,
                assistant_mode="none",
                base_time=datetime(2026, 5, 4, 9, 0, 0),
                resume_existing=True,
                stress_mode="none",
            )


if __name__ == "__main__":
    unittest.main()
