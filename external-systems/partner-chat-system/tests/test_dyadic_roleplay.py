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


class DyadicRoleplayRunTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_database(self.conn)
        reset_all_tables(self.conn)
        self.assistant_patcher = patch(
            "chat_system.service.generate_assistant_guidance",
            return_value={
                "current_problem": ["测试问题"],
                "problem_tags": ["topic_dead_end"],
                "avoid": ["不要继续硬追问"],
                "topic_directions": ["周末安排"],
                "easy_question_types": ["低门槛生活问题"],
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
                            "reason": "测试触发救场",
                        },
                        ensure_ascii=False,
                    )
                return json.dumps(
                    {"need_rescue": False, "situation": "none", "reason": "流畅"},
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
        self.assertEqual(len(out["turn_evaluations"]), 3)
        self.assertTrue(
            all(
                (turn.get("assistant_follow_assessment") or {}).get("level") == "not_applicable"
                for turn in out["turn_evaluations"]
            )
        )

    def test_run_proactive_rescue_triggers_assistant(self):
        llm, _orch = self._mock_llm(rescue_on_first=True)
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

        msgs_b = list_messages(self.conn, out["thread_id"], "pb", limit=50)
        authors_sources = [(m["author_id"], m["source"]) for m in msgs_b]
        self.assertTrue(any(a == "assistant" for a, _ in authors_sources))
        self.assertEqual(out["assistant_metrics"]["predicted_rescue_turns"], 1)

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
        self.assertEqual(len(out["proactive_rescue_events"]), 1)
        self.assertEqual(out["turn_evaluations"][1]["rescue_decision_source"], "heuristic")
        self.assertEqual(out["assistant_metrics"]["heuristic_decision_turns"], 2)
        self.assertEqual(out["assistant_metrics"]["llm_decision_turns"], 0)

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
