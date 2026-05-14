import json
import os
import types
import unittest
from datetime import datetime
import pathlib
import sys
from unittest.mock import patch

SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system import (  # noqa: E402
    build_case_conversation_timeline,
    close_idle_agent_sessions,
    create_assistant_case_layout,
    get_agent_session_by_case,
    list_case_conversations,
    list_conversation_messages,
    list_agent_tasks,
    post_conversation_message,
    run_chat_maintenance,
)
from chat_system.outbox_consumer import consume_chat_outbox_batch  # noqa: E402
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN, connect_db, initialize_database, reset_all_tables  # noqa: E402


class ChatConversationTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_database(self.conn)
        reset_all_tables(self.conn)

    def tearDown(self):
        self.conn.close()

    def _create_layout(self):
        return create_assistant_case_layout(
            self.conn,
            case_id="case-conv-1",
            relation_key="rel-conv-1",
            participant_a_id="user-a",
            participant_b_id="user-b",
            agent_id="agent-c",
            now=datetime(2026, 5, 8, 21, 0, 0),
        )

    def test_assistant_layout_visibility_and_message_flow(self):
        layout = self._create_layout()
        self.assertEqual(layout["conversation_count"], 3)

        by_role = {
            item["metadata"]["layout_role"]: item
            for item in layout["conversations"]
        }
        main = by_role["main_group"]
        dm_a = by_role["assistant_dm_a"]
        dm_b = by_role["assistant_dm_b"]

        visible_a = list_case_conversations(self.conn, "case-conv-1", requester_id="user-a")
        self.assertEqual(
            {item["metadata"]["layout_role"] for item in visible_a},
            {"main_group", "assistant_dm_a"},
        )
        visible_b = list_case_conversations(self.conn, "case-conv-1", requester_id="user-b")
        self.assertEqual(
            {item["metadata"]["layout_role"] for item in visible_b},
            {"main_group", "assistant_dm_b"},
        )
        visible_c = list_case_conversations(self.conn, "case-conv-1", requester_id="agent-c")
        self.assertEqual(
            {item["metadata"]["layout_role"] for item in visible_c},
            {"main_group", "assistant_dm_a", "assistant_dm_b"},
        )

        msg1 = post_conversation_message(
            self.conn,
            main["conversation_id"],
            "user-a",
            "你好，我们先随便聊聊周末安排吧。",
            now=datetime(2026, 5, 8, 21, 1, 0),
        )
        msg2 = post_conversation_message(
            self.conn,
            main["conversation_id"],
            "agent-c",
            "你们可以先从轻松话题开始。",
            source="agent",
            now=datetime(2026, 5, 8, 21, 2, 0),
        )
        self.assertEqual(msg1["source"], "user")
        self.assertEqual(msg2["source"], "agent")

        post_conversation_message(
            self.conn,
            dm_a["conversation_id"],
            "agent-c",
            "你可以先问她周末一般怎么安排。",
            source="agent",
            client_msg_id="dm-a-1",
            now=datetime(2026, 5, 8, 21, 3, 0),
        )
        post_conversation_message(
            self.conn,
            dm_b["conversation_id"],
            "agent-c",
            "你可以顺着运动和咖啡这些话题回应。",
            source="agent",
            now=datetime(2026, 5, 8, 21, 4, 0),
        )

        main_msgs_for_b = list_conversation_messages(
            self.conn,
            main["conversation_id"],
            "user-b",
            limit=20,
        )
        self.assertEqual([row["author_id"] for row in main_msgs_for_b], ["user-a", "agent-c"])

        dm_a_msgs_for_a = list_conversation_messages(
            self.conn,
            dm_a["conversation_id"],
            "user-a",
            limit=20,
        )
        self.assertEqual(len(dm_a_msgs_for_a), 1)
        self.assertEqual(dm_a_msgs_for_a[0]["author_id"], "agent-c")

        with self.assertRaisesRegex(ValueError, "not allowed to read"):
            list_conversation_messages(self.conn, dm_b["conversation_id"], "user-a", limit=20)
        with self.assertRaisesRegex(ValueError, "not allowed to send"):
            post_conversation_message(self.conn, dm_b["conversation_id"], "user-a", "我不该看到这里")

        timeline_for_a = build_case_conversation_timeline(
            self.conn,
            "case-conv-1",
            "user-a",
            message_limit=20,
        )
        self.assertEqual(timeline_for_a["conversation_count"], 2)
        self.assertEqual(
            {item["conversation"]["metadata"]["layout_role"] for item in timeline_for_a["conversations"]},
            {"main_group", "assistant_dm_a"},
        )

    def test_layout_and_message_idempotency(self):
        layout1 = self._create_layout()
        layout2 = self._create_layout()
        by_role_1 = {
            item["metadata"]["layout_role"]: item["conversation_id"]
            for item in layout1["conversations"]
        }
        by_role_2 = {
            item["metadata"]["layout_role"]: item["conversation_id"]
            for item in layout2["conversations"]
        }
        self.assertEqual(by_role_1, by_role_2)

        dm_a = next(
            item for item in layout1["conversations"]
            if item["metadata"]["layout_role"] == "assistant_dm_a"
        )
        m1 = post_conversation_message(
            self.conn,
            dm_a["conversation_id"],
            "agent-c",
            "重复投递只该有一条。",
            source="agent",
            client_msg_id="same-msg-1",
        )
        m2 = post_conversation_message(
            self.conn,
            dm_a["conversation_id"],
            "agent-c",
            "重复投递只该有一条。",
            source="agent",
            client_msg_id="same-msg-1",
        )
        self.assertEqual(m1["message_id"], m2["message_id"])

    def test_layout_accepts_fixed_conversation_ids(self):
        layout = create_assistant_case_layout(
            self.conn,
            case_id="case-fixed-ids",
            relation_key="rel-fixed-ids",
            participant_a_id="user-a",
            participant_b_id="user-b",
            agent_id="agent-c",
            conversation_ids={
                "main_group": "cvt-main-fixed-001",
                "assistant_dm_a": "cvt-dma-fixed-001",
                "assistant_dm_b": "cvt-dmb-fixed-001",
            },
            now=datetime(2026, 5, 8, 21, 10, 0),
        )
        by_role = {
            item["metadata"]["layout_role"]: item["conversation_id"]
            for item in layout["conversations"]
        }
        self.assertEqual(by_role["main_group"], "cvt-main-fixed-001")
        self.assertEqual(by_role["assistant_dm_a"], "cvt-dma-fixed-001")
        self.assertEqual(by_role["assistant_dm_b"], "cvt-dmb-fixed-001")

    def test_public_user_message_updates_matchmaker_session_without_task(self):
        layout = self._create_layout()
        main = next(
            item for item in layout["conversations"]
            if item["metadata"]["layout_role"] == "main_group"
        )
        self.assertIsNone(get_agent_session_by_case(self.conn, "case-conv-1"))

        msg = post_conversation_message(
            self.conn,
            main["conversation_id"],
            "user-a",
            "刚认识，先从周末安排聊起。",
            now=datetime(2026, 5, 8, 21, 11, 0),
        )
        out = consume_chat_outbox_batch(
            self.conn,
            limit=50,
            now=datetime(2026, 5, 8, 21, 12, 0),
        )
        session = get_agent_session_by_case(self.conn, "case-conv-1")
        tasks = list_agent_tasks(self.conn, case_id="case-conv-1")

        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session["triggered_by_message_id"], msg["message_id"])
        self.assertEqual(session["status"], "open")
        self.assertEqual(session["last_seen_message_id"], msg["message_id"])
        self.assertIsNotNone(session["last_user_message_at"])
        self.assertEqual(tasks, [])
        self.assertEqual(out["agent_tasks_enqueued"], 0)

    def test_public_user_message_creates_task_when_public_followup_is_active(self):
        layout = self._create_layout()
        main = next(
            item for item in layout["conversations"]
            if item["metadata"]["layout_role"] == "main_group"
        )

        first_msg = post_conversation_message(
            self.conn,
            main["conversation_id"],
            "user-a",
            "刚认识，先从周末安排聊起。",
            now=datetime(2026, 5, 8, 21, 11, 0),
        )
        consume_chat_outbox_batch(
            self.conn,
            limit=50,
            now=datetime(2026, 5, 8, 21, 12, 0),
        )
        session = get_agent_session_by_case(self.conn, "case-conv-1")
        self.assertIsNotNone(session)
        assert session is not None
        self.conn.execute(
            """
            UPDATE chat_agent_sessions
            SET state_json = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(
                    {
                        "public_followup_active": True,
                        "public_followup_mode": "opening",
                    }
                ),
                session["session_id"],
            ),
        )
        self.conn.commit()

        second_msg = post_conversation_message(
            self.conn,
            main["conversation_id"],
            "user-b",
            "我平时在医院上班，作息不太固定。",
            now=datetime(2026, 5, 8, 21, 12, 20),
        )
        out = consume_chat_outbox_batch(
            self.conn,
            limit=50,
            now=datetime(2026, 5, 8, 21, 12, 30),
        )

        tasks = list_agent_tasks(self.conn, case_id="case-conv-1")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["trigger_message_id"], int(second_msg["message_id"]))
        self.assertEqual(tasks[0]["reason"], "user_message")
        self.assertEqual(first_msg["message_id"] < second_msg["message_id"], True)
        self.assertEqual(out["agent_tasks_enqueued"], 1)

    def test_private_user_message_creates_matchmaker_session_and_task(self):
        layout = self._create_layout()
        dm_a = next(
            item for item in layout["conversations"]
            if item["metadata"]["layout_role"] == "assistant_dm_a"
        )
        self.assertIsNone(get_agent_session_by_case(self.conn, "case-conv-1"))

        msg = post_conversation_message(
            self.conn,
            dm_a["conversation_id"],
            "user-a",
            "她这样回我，下一句怎么接更自然？",
            now=datetime(2026, 5, 8, 21, 11, 0),
        )
        out = consume_chat_outbox_batch(
            self.conn,
            limit=50,
            now=datetime(2026, 5, 8, 21, 12, 0),
        )
        session = get_agent_session_by_case(self.conn, "case-conv-1")
        tasks = list_agent_tasks(self.conn, case_id="case-conv-1")

        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session["triggered_by_message_id"], msg["message_id"])
        self.assertEqual(session["status"], "open")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["status"], "pending")
        self.assertEqual(tasks[0]["trigger_message_id"], msg["message_id"])
        self.assertEqual(out["agent_tasks_enqueued"], 1)

    def test_live_chat_keyword_message_does_not_enqueue_persona_job(self):
        layout = self._create_layout()
        main = next(
            item for item in layout["conversations"]
            if item["metadata"]["layout_role"] == "main_group"
        )
        post_conversation_message(
            self.conn,
            main["conversation_id"],
            "user-a",
            "我在杭州工作，也认真考虑结婚，不过刚认识还是想先自然聊聊。",
            now=datetime(2026, 5, 8, 21, 12, 0),
        )

        cur = self.conn.execute("SELECT COUNT(*) AS c FROM persona_sync_jobs")
        self.assertEqual(int(cur.fetchone()["c"]), 0)

        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["observe_only"],
                "state_patch": {},
                "cooldown_seconds": 0,
            },
        ):
            run_chat_maintenance(
                self.conn,
                persona_limit=10,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 12, 30),
            )

        cur = self.conn.execute("SELECT COUNT(*) AS c FROM persona_sync_jobs")
        self.assertEqual(int(cur.fetchone()["c"]), 0)

    def test_agent_and_system_messages_do_not_create_matchmaker_tasks(self):
        layout = self._create_layout()
        by_role = {
            item["metadata"]["layout_role"]: item
            for item in layout["conversations"]
        }
        post_conversation_message(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "agent-c",
            "这是红娘给 A 的私聊建议。",
            source="agent",
            now=datetime(2026, 5, 8, 21, 13, 0),
        )
        post_conversation_message(
            self.conn,
            by_role["main_group"]["conversation_id"],
            "system-bot",
            "系统提示：今晚消息同步完成。",
            source="system",
            now=datetime(2026, 5, 8, 21, 14, 0),
        )

        out = consume_chat_outbox_batch(
            self.conn,
            limit=50,
            now=datetime(2026, 5, 8, 21, 15, 0),
        )
        self.assertIsNone(get_agent_session_by_case(self.conn, "case-conv-1"))
        self.assertEqual(list_agent_tasks(self.conn, case_id="case-conv-1"), [])
        self.assertEqual(out["agent_tasks_enqueued"], 0)

    def test_matchmaker_task_dedupes_when_same_outbox_row_replayed(self):
        layout = self._create_layout()
        dm_a = next(
            item for item in layout["conversations"]
            if item["metadata"]["layout_role"] == "assistant_dm_a"
        )
        msg = post_conversation_message(
            self.conn,
            dm_a["conversation_id"],
            "user-a",
            "她这样回我，下一句怎么接更自然？",
            now=datetime(2026, 5, 8, 21, 16, 0),
        )
        consume_chat_outbox_batch(
            self.conn,
            limit=50,
            now=datetime(2026, 5, 8, 21, 17, 0),
        )
        self.conn.execute(
            """
            UPDATE outbox_events
            SET publish_status = 'pending', published_at = NULL
            WHERE source_row_table = 'chat_conversation_messages' AND source_row_id = ?
            """,
            (int(msg["message_id"]),),
        )
        self.conn.commit()
        consume_chat_outbox_batch(
            self.conn,
            limit=50,
            now=datetime(2026, 5, 8, 21, 18, 0),
        )
        tasks = list_agent_tasks(self.conn, case_id="case-conv-1")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["trigger_message_id"], msg["message_id"])

    def test_maintenance_processes_matchmaker_task_without_self_trigger(self):
        layout = self._create_layout()
        by_role = {
            item["metadata"]["layout_role"]: item
            for item in layout["conversations"]
        }
        post_conversation_message(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "user-a",
            "她回复有点慢，我怕节奏冷掉。",
            now=datetime(2026, 5, 8, 21, 19, 0),
        )

        def fake_runtime(run_input):
            recent = run_input.get_recent_case_messages(limit=10)
            history = run_input.search_case_history(query="慢", limit=10)
            self.assertEqual(recent[-1]["source"], "user")
            self.assertGreaterEqual(len(history), 1)
            return {
                "should_reply": True,
                "target_channel_key": "assistant_dm_a",
                "reply_body": "先别追问态度，先发一条低压力消息确认她是不是这两天忙。",
                "reason_codes": ["history_checked", "pace_mismatch"],
                "state_patch": {"relationship_stage": "warming"},
                "cooldown_seconds": 90,
            }

        with patch("chat_system.assistant_orchestrator.run_matchmaker_agent", side_effect=fake_runtime):
            out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 19, 30),
            )

        self.assertEqual(out["assistant"]["completed"], 1)
        self.assertEqual(out["assistant"]["failed"], 0)
        tasks = list_agent_tasks(self.conn, case_id="case-conv-1")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["status"], "completed")
        self.assertEqual(tasks[0]["result"]["reason_codes"], ["history_checked", "pace_mismatch"])

        dm_a_messages = list_conversation_messages(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "user-a",
            limit=20,
        )
        self.assertEqual(len(dm_a_messages), 2)
        self.assertEqual(dm_a_messages[-1]["author_id"], "agent-c")
        self.assertEqual(dm_a_messages[-1]["source"], "agent")

        session = get_agent_session_by_case(self.conn, "case-conv-1")
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session["state"]["relationship_stage"], "warming")
        self.assertEqual(session["state"]["last_reason_codes"], ["history_checked", "pace_mismatch"])

        consume_chat_outbox_batch(
            self.conn,
            limit=50,
            now=datetime(2026, 5, 8, 21, 20, 0),
        )
        tasks_after = list_agent_tasks(self.conn, case_id="case-conv-1")
        self.assertEqual(len(tasks_after), 1)
        self.assertEqual(tasks_after[0]["status"], "completed")

    def test_maintenance_coalesces_multiple_private_tasks_same_side(self):
        layout = self._create_layout()
        by_role = {
            item["metadata"]["layout_role"]: item
            for item in layout["conversations"]
        }
        first_dm_a = post_conversation_message(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "user-a",
            "她这样回我，下一句怎么接更自然？",
            now=datetime(2026, 5, 8, 21, 19, 10),
        )
        second_dm_a = post_conversation_message(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "user-a",
            "她刚又补了一句，这一轮我该怎么顺着接？",
            now=datetime(2026, 5, 8, 21, 19, 20),
        )

        runtime_calls: list[int] = []

        def fake_runtime(run_input):
            runtime_calls.append(int(run_input.task["trigger_message_id"]))
            return {
                "should_reply": True,
                "target_channel_key": "assistant_dm_a",
                "reply_body": "顺着她刚才反问的点接下去。",
                "reason_codes": ["explicit_dm_selected"],
                "state_patch": {"relationship_stage": "starting"},
                "cooldown_seconds": 300,
            }

        with patch("chat_system.assistant_orchestrator.run_matchmaker_agent", side_effect=fake_runtime):
            out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 19, 30),
            )

        self.assertEqual(runtime_calls, [int(second_dm_a["message_id"])])
        self.assertEqual(out["assistant"]["replies_posted"], 1)

        tasks = {
            int(item["trigger_message_id"]): item
            for item in list_agent_tasks(self.conn, case_id="case-conv-1")
        }
        self.assertEqual(
            out["assistant"]["skipped_task_ids"],
            [int(tasks[int(first_dm_a["message_id"])]["task_id"])],
        )
        self.assertEqual(
            tasks[int(first_dm_a["message_id"])]["result"]["reason_codes"],
            ["superseded_by_newer_trigger"],
        )
        self.assertEqual(
            tasks[int(second_dm_a["message_id"])]["result"]["reason_codes"],
            ["explicit_dm_selected"],
        )

        dm_a_messages = list_conversation_messages(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "user-a",
            limit=20,
        )
        self.assertEqual(len(dm_a_messages), 3)
        self.assertEqual(dm_a_messages[-1]["source"], "agent")

    def test_private_trigger_still_runs_during_active_cooldown(self):
        layout = self._create_layout()
        by_role = {
            item["metadata"]["layout_role"]: item
            for item in layout["conversations"]
        }
        first_msg = post_conversation_message(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "user-a",
            "她回得慢，我有点慌。",
            now=datetime(2026, 5, 8, 21, 20, 0),
        )

        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": True,
                "target_channel_key": "assistant_dm_a",
                "reply_body": "先别追着问，等她这一轮忙完。",
                "reason_codes": ["cooldown_seed"],
                "state_patch": {"relationship_stage": "warming"},
                "cooldown_seconds": 300,
            },
        ):
            first_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 20, 10),
            )

        self.assertEqual(first_out["assistant"]["replies_posted"], 1)

        second_msg = post_conversation_message(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "user-a",
            "她刚又回了一句，我这一轮该不该追问？",
            now=datetime(2026, 5, 8, 21, 21, 0),
        )
        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": True,
                "target_channel_key": "assistant_dm_a",
                "reply_body": "这一轮先别追问态度，顺着她刚才给的信息轻轻接一下。",
                "reason_codes": ["cooldown_bypassed_private_dm"],
                "state_patch": {"relationship_stage": "warming"},
                "cooldown_seconds": 300,
            },
        ):
            second_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 21, 5),
            )

        self.assertEqual(second_out["assistant"]["failed"], 0)
        self.assertEqual(second_out["assistant"]["replies_posted"], 1)

        tasks = {
            int(item["trigger_message_id"]): item
            for item in list_agent_tasks(self.conn, case_id="case-conv-1")
        }
        self.assertEqual(second_out["assistant"]["skipped_task_ids"], [])
        self.assertEqual(tasks[int(first_msg["message_id"])]["result"]["reason_codes"], ["cooldown_seed"])
        self.assertEqual(
            tasks[int(second_msg["message_id"])]["result"]["reason_codes"],
            ["cooldown_bypassed_private_dm"],
        )

    def test_opening_probe_can_proactively_introduce_both_sides(self):
        layout = self._create_layout()
        by_role = {
            item["metadata"]["layout_role"]: item
            for item in layout["conversations"]
        }

        def fake_runtime(run_input):
            self.assertEqual(run_input.task["reason"], "opening_probe")
            self.assertEqual(run_input.bootstrap["recent_messages"], [])
            return {
                "should_reply": True,
                "target_channel_key": "main_group",
                "reply_body": "我先帮两位起个头。user-a 在上海做产品，user-b 在上海做医生，你们可以先聊聊各自周末怎么放松。",
                "reason_codes": ["opening_probe", "profile_intro"],
                "state_patch": {"relationship_stage": "opening"},
                "cooldown_seconds": 60,
                "public_followup": {"active": True, "mode": "opening"},
            }

        with patch("chat_system.assistant_orchestrator.run_matchmaker_agent", side_effect=fake_runtime):
            out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=False,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 0, 40),
            )

        self.assertEqual(out["assistant_triggers"]["opening_probe"]["enqueued"], 1)
        self.assertEqual(out["assistant_triggers"]["silence_probe"]["enqueued"], 0)
        self.assertEqual(out["assistant"]["replies_posted"], 1)

        session = get_agent_session_by_case(self.conn, "case-conv-1")
        self.assertIsNotNone(session)
        assert session is not None
        self.assertIsNone(session["triggered_by_message_id"])
        self.assertIsNone(session["last_user_message_at"])
        self.assertTrue(session["state"]["public_followup_active"])
        self.assertEqual(session["state"]["public_followup_mode"], "opening")

        tasks = list_agent_tasks(self.conn, case_id="case-conv-1")
        opening_tasks = [item for item in tasks if item["reason"] == "opening_probe"]
        self.assertEqual(len(opening_tasks), 1)
        self.assertEqual(opening_tasks[0]["result"]["target_channel_key"], "main_group")

        main_group_messages = list_conversation_messages(
            self.conn,
            by_role["main_group"]["conversation_id"],
            "user-a",
            limit=20,
        )
        self.assertEqual(len(main_group_messages), 1)
        self.assertEqual(main_group_messages[0]["author_id"], "agent-c")
        self.assertIn("我先帮两位起个头", main_group_messages[0]["body"])

    def test_opening_probe_followup_runs_on_new_public_message_until_agent_closes_it(self):
        layout = self._create_layout()
        by_role = {
            item["metadata"]["layout_role"]: item
            for item in layout["conversations"]
        }
        runtime_calls: list[tuple[str, int]] = []

        def fake_runtime(run_input):
            runtime_calls.append((str(run_input.task["reason"]), int(run_input.task["trigger_message_id"])))
            if run_input.task["reason"] == "opening_probe":
                return {
                    "should_reply": True,
                    "target_channel_key": "main_group",
                    "reply_body": "我先帮两位起个头。你们可以先聊聊各自周末怎么放松。",
                    "reason_codes": ["opening_probe", "profile_intro"],
                    "state_patch": {"relationship_stage": "opening"},
                    "cooldown_seconds": 60,
                    "public_followup": {"active": True, "mode": "opening"},
                }
            return {
                "should_reply": True,
                "target_channel_key": "main_group",
                "reply_body": "如果第一句还没接上，也可以先聊聊最近下班后最能让自己放松的一件小事。",
                "reason_codes": ["opening_followup", "second_followup"],
                "state_patch": {"relationship_stage": "opening"},
                "cooldown_seconds": 60,
                "public_followup": {"active": False, "mode": "opening"},
            }

        with patch("chat_system.assistant_orchestrator.run_matchmaker_agent", side_effect=fake_runtime):
            first_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=False,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 0, 40),
            )
            followup_msg = post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-a",
                "我周末一般会找家安静的咖啡店坐坐。",
                now=datetime(2026, 5, 8, 21, 0, 50),
            )
            second_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 0, 55),
            )
            third_msg = post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-b",
                "我下班后一般会去散步或者回家休息。",
                now=datetime(2026, 5, 8, 21, 1, 0),
            )
            third_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 1, 5),
            )

        self.assertEqual(first_out["assistant_triggers"]["opening_probe"]["enqueued"], 1)
        self.assertEqual(first_out["assistant"]["replies_posted"], 1)
        self.assertEqual(second_out["assistant"]["replies_posted"], 1)
        self.assertEqual(second_out["outbox_consume"]["agent_tasks_enqueued"], 1)
        self.assertEqual(third_out["assistant"]["replies_posted"], 0)
        self.assertEqual(third_out["outbox_consume"]["agent_tasks_enqueued"], 0)

        main_group_messages = list_conversation_messages(
            self.conn,
            by_role["main_group"]["conversation_id"],
            "user-a",
            limit=20,
        )
        self.assertEqual(len(main_group_messages), 4)
        self.assertEqual(main_group_messages[0]["source"], "agent")
        self.assertEqual(main_group_messages[2]["source"], "agent")
        self.assertEqual(runtime_calls, [("opening_probe", 0), ("user_message", int(followup_msg["message_id"]))])

        tasks = list_agent_tasks(self.conn, case_id="case-conv-1")
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["reason"], "opening_probe")
        self.assertEqual(tasks[0]["trigger_message_id"], 0)
        self.assertEqual(tasks[1]["reason"], "user_message")
        self.assertEqual(tasks[1]["trigger_message_id"], int(followup_msg["message_id"]))
        self.assertLess(int(followup_msg["message_id"]), int(third_msg["message_id"]))

        session = get_agent_session_by_case(self.conn, "case-conv-1")
        self.assertIsNotNone(session)
        assert session is not None
        self.assertFalse(session["state"]["public_followup_active"])

    def test_silence_probe_can_proactively_post_public_rescue(self):
        layout = self._create_layout()
        by_role = {
            item["metadata"]["layout_role"]: item
            for item in layout["conversations"]
        }

        def fake_runtime(run_input):
            if run_input.task["reason"] == "silence_probe":
                return {
                    "should_reply": True,
                    "target_channel_key": "main_group",
                    "reply_body": "你们刚都提到工作节奏忙，那下班后一般都靠什么让自己切换一下？",
                    "reason_codes": ["silence_probe", "public_rescue"],
                    "state_patch": {"relationship_stage": "cooling"},
                    "cooldown_seconds": 120,
                    "public_followup": {"active": True, "mode": "silence"},
                }
            return {
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["observe_only"],
                "state_patch": {"relationship_stage": "starting"},
                "cooldown_seconds": 0,
            }

        with patch("chat_system.assistant_orchestrator.run_matchmaker_agent", side_effect=fake_runtime):
            post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-a",
                "你好呀，刚看到消息来打个招呼。",
                now=datetime(2026, 5, 8, 21, 30, 0),
            )
            run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 30, 5),
            )
            post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-b",
                "你好，我平时在医院上班。",
                now=datetime(2026, 5, 8, 21, 30, 25),
            )
            run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 30, 30),
            )
            post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-a",
                "那工作节奏应该还挺紧的。",
                now=datetime(2026, 5, 8, 21, 30, 50),
            )
            run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 30, 55),
            )
            post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-b",
                "嗯，算是吧。",
                now=datetime(2026, 5, 8, 21, 31, 10),
            )
            run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 31, 15),
            )

            out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=False,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 32, 5),
            )

        self.assertEqual(out["assistant_triggers"]["enqueued"], 1)
        self.assertEqual(out["assistant"]["replies_posted"], 1)

        tasks = list_agent_tasks(self.conn, case_id="case-conv-1")
        silence_tasks = [item for item in tasks if item["reason"] == "silence_probe"]
        self.assertEqual(len(tasks), 1)
        self.assertEqual(len(silence_tasks), 1)
        self.assertEqual(silence_tasks[0]["result"]["reason_codes"], ["silence_probe", "public_rescue"])

        main_group_messages = list_conversation_messages(
            self.conn,
            by_role["main_group"]["conversation_id"],
            "user-a",
            limit=20,
        )
        self.assertEqual(main_group_messages[-1]["author_id"], "agent-c")
        self.assertEqual(
            main_group_messages[-1]["body"],
            "你们刚都提到工作节奏忙，那下班后一般都靠什么让自己切换一下？",
        )
        session = get_agent_session_by_case(self.conn, "case-conv-1")
        self.assertIsNotNone(session)
        assert session is not None
        self.assertTrue(session["state"]["public_followup_active"])
        self.assertEqual(session["state"]["public_followup_mode"], "silence")

    def test_silence_probe_followup_runs_on_new_public_message_until_agent_closes_it(self):
        layout = self._create_layout()
        by_role = {
            item["metadata"]["layout_role"]: item
            for item in layout["conversations"]
        }
        runtime_calls: list[tuple[str, int]] = []

        def fake_runtime(run_input):
            runtime_calls.append((str(run_input.task["reason"]), int(run_input.task["trigger_message_id"])))
            if run_input.task["reason"] == "silence_probe":
                return {
                    "should_reply": True,
                    "target_channel_key": "main_group",
                    "reply_body": "你们刚都提到最近忙，那下班后一般都靠什么切换一下状态？",
                    "reason_codes": ["silence_probe", "first_rescue"],
                    "state_patch": {"relationship_stage": "cooling"},
                    "cooldown_seconds": 120,
                    "public_followup": {"active": True, "mode": "silence"},
                }
            return {
                "should_reply": True,
                "target_channel_key": "main_group",
                "reply_body": "要是这个话头还没接住，也可以聊聊最近一件让自己放松下来的小事。",
                "reason_codes": ["silence_followup", "second_rescue"],
                "state_patch": {"relationship_stage": "cooling"},
                "cooldown_seconds": 120,
                "public_followup": {"active": False, "mode": "silence"},
            }

        with patch("chat_system.assistant_orchestrator.run_matchmaker_agent", side_effect=fake_runtime):
            post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-a",
                "你好呀，先来打个招呼。",
                now=datetime(2026, 5, 8, 21, 30, 0),
            )
            run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 30, 5),
            )
            post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-b",
                "你好，我平时在医院上班。",
                now=datetime(2026, 5, 8, 21, 30, 20),
            )
            run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 30, 25),
            )

            first_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=False,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 31, 10),
            )
            followup_msg = post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-a",
                "我下班后会去跑跑步，不然很难切换出来。",
                now=datetime(2026, 5, 8, 21, 31, 20),
            )
            second_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 31, 25),
            )
            third_msg = post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-b",
                "我一般就回家待着，话也不太多。",
                now=datetime(2026, 5, 8, 21, 31, 30),
            )
            third_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 31, 35),
            )

        self.assertEqual(first_out["assistant_triggers"]["silence_probe"]["enqueued"], 1)
        self.assertEqual(first_out["assistant"]["replies_posted"], 1)
        self.assertEqual(second_out["assistant"]["replies_posted"], 1)
        self.assertEqual(second_out["outbox_consume"]["agent_tasks_enqueued"], 1)
        self.assertEqual(third_out["assistant"]["replies_posted"], 0)
        self.assertEqual(third_out["outbox_consume"]["agent_tasks_enqueued"], 0)

        main_group_messages = list_conversation_messages(
            self.conn,
            by_role["main_group"]["conversation_id"],
            "user-a",
            limit=20,
        )
        self.assertEqual(len(main_group_messages), 6)
        self.assertEqual(main_group_messages[2]["source"], "agent")
        self.assertEqual(main_group_messages[4]["source"], "agent")
        self.assertEqual(runtime_calls, [("silence_probe", int(main_group_messages[1]["message_id"])), ("user_message", int(followup_msg["message_id"]))])

        tasks = list_agent_tasks(self.conn, case_id="case-conv-1")
        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0]["reason"], "silence_probe")
        self.assertEqual(tasks[0]["trigger_message_id"], int(main_group_messages[1]["message_id"]))
        self.assertEqual(tasks[1]["reason"], "user_message")
        self.assertEqual(tasks[1]["trigger_message_id"], int(followup_msg["message_id"]))
        self.assertLess(int(followup_msg["message_id"]), int(third_msg["message_id"]))

        session = get_agent_session_by_case(self.conn, "case-conv-1")
        self.assertIsNotNone(session)
        assert session is not None
        self.assertFalse(session["state"]["public_followup_active"])

    def test_silence_probe_is_not_blocked_by_active_cooldown(self):
        layout = self._create_layout()
        by_role = {
            item["metadata"]["layout_role"]: item
            for item in layout["conversations"]
        }

        def fake_runtime(run_input):
            if run_input.task["reason"] == "silence_probe":
                return {
                    "should_reply": True,
                    "target_channel_key": "main_group",
                    "reply_body": "你们都提到最近忙，要不要聊聊各自下班后最能回血的一件小事？",
                    "reason_codes": ["silence_probe", "cooldown_bypassed_public_rescue"],
                    "state_patch": {"relationship_stage": "cooling"},
                    "cooldown_seconds": 60,
                }
            return {
                "should_reply": True,
                "target_channel_key": "assistant_dm_b",
                "reply_body": "你可以先简单回个招呼，再说说自己的工作状态。",
                "reason_codes": ["initial_private_nudge"],
                "state_patch": {"relationship_stage": "starting"},
                "cooldown_seconds": 600,
            }

        with patch("chat_system.assistant_orchestrator.run_matchmaker_agent", side_effect=fake_runtime):
            post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-a",
                "你好呀，先来打个招呼。",
                now=datetime(2026, 5, 8, 21, 40, 0),
            )
            first_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 40, 5),
            )
            self.assertEqual(first_out["assistant"]["replies_posted"], 0)

            post_conversation_message(
                self.conn,
                by_role["assistant_dm_b"]["conversation_id"],
                "user-b",
                "我刚开始有点不知道怎么接，能不能给我个方向？",
                now=datetime(2026, 5, 8, 21, 40, 10),
            )
            dm_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 40, 15),
            )
            self.assertEqual(dm_out["assistant"]["replies_posted"], 1)

            post_conversation_message(
                self.conn,
                by_role["main_group"]["conversation_id"],
                "user-b",
                "你好，我在医院这边工作。",
                now=datetime(2026, 5, 8, 21, 40, 20),
            )
            second_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 40, 25),
            )
            self.assertEqual(second_out["assistant"]["replies_posted"], 0)

            out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=False,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 41, 10),
            )

        self.assertEqual(out["assistant_triggers"]["enqueued"], 1)
        self.assertEqual(out["assistant"]["replies_posted"], 1)
        tasks = list_agent_tasks(self.conn, case_id="case-conv-1")
        silence_tasks = [item for item in tasks if item["reason"] == "silence_probe"]
        self.assertEqual(len(silence_tasks), 1)
        self.assertEqual(
            silence_tasks[0]["result"]["reason_codes"],
            ["silence_probe", "cooldown_bypassed_public_rescue"],
        )

    def test_post_chat_followup_reaches_both_sides_after_ready_window(self):
        layout = self._create_layout()
        by_role = {item["metadata"]["layout_role"]: item for item in layout["conversations"]}
        main_group = by_role["main_group"]

        post_conversation_message(
            self.conn,
            main_group["conversation_id"],
            "user-a",
            "今天聊得挺舒服的，我先去忙一下。",
            now=datetime(2026, 5, 8, 21, 50, 0),
        )
        end_b = post_conversation_message(
            self.conn,
            main_group["conversation_id"],
            "user-b",
            "好呀，改天再聊。",
            now=datetime(2026, 5, 8, 21, 50, 20),
        )

        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["observe_only"],
                "state_patch": {},
                "cooldown_seconds": 0,
            },
        ):
            run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                assistant_post_chat_seconds=600,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 50, 30),
            )

        session = get_agent_session_by_case(self.conn, "case-conv-1")
        self.assertIsNotNone(session)
        assert session is not None
        self.conn.execute(
            """
            UPDATE chat_agent_sessions
            SET state_json = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(
                    {
                        "phase": "post_chat_ready",
                        "chat_end_at": "2026-05-08 21:50:20",
                        "chat_end_message_id": int(end_b["message_id"]),
                        "chat_end_reason": ["natural_ending", "mutual_closure"],
                    }
                ),
                session["session_id"],
            ),
        )
        self.conn.commit()

        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": True,
                "target_channel_key": "assistant_dm_a",
                "reply_body": "这轮聊下来，你对高佳晨第一感觉怎么样？最加分的一点是什么？",
                "reason_codes": ["post_chat_review", "contact_both_sides"],
                "state_patch": {
                    "phase": "post_chat_followup",
                    "post_chat_review_status": "completed",
                    "post_chat_review_contacted_side": "a",
                    "followup_a_status": "sent",
                    "followup_b_status": "sent",
                },
                "cooldown_seconds": 300,
                "additional_actions": [
                    {
                        "target_channel_key": "assistant_dm_b",
                        "reply_body": "这轮聊下来，你对他第一感觉怎么样？最加分的一点是什么？",
                    }
                ],
            },
        ):
            out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                assistant_post_chat_seconds=600,
                flush_outbox=False,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 22, 1, 0),
            )

        self.assertEqual(out["assistant_triggers"]["post_chat_followup"]["enqueued"], 1)
        self.assertEqual(out["assistant"]["replies_posted"], 2)

        dm_a_messages = list_conversation_messages(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "user-a",
            limit=20,
        )
        dm_b_messages = list_conversation_messages(
            self.conn,
            by_role["assistant_dm_b"]["conversation_id"],
            "user-b",
            limit=20,
        )
        self.assertEqual(len(dm_a_messages), 1)
        self.assertEqual(len(dm_b_messages), 1)
        self.assertIn("第一感觉", dm_a_messages[0]["body"])
        self.assertIn("第一感觉", dm_b_messages[0]["body"])

        updated_session = get_agent_session_by_case(self.conn, "case-conv-1")
        assert updated_session is not None
        self.assertEqual(updated_session["state"]["followup_a_status"], "sent")
        self.assertEqual(updated_session["state"]["followup_b_status"], "sent")
        self.assertEqual(updated_session["state"]["phase"], "post_chat_followup")

    def test_post_chat_review_can_update_persona_without_private_followup(self):
        layout = self._create_layout()
        by_role = {item["metadata"]["layout_role"]: item for item in layout["conversations"]}
        main_group = by_role["main_group"]

        timeline = [
            ("user-a", "我平时节奏比较规律，忙完就想早点回家休息。", datetime(2026, 5, 8, 21, 50, 0)),
            ("user-b", "我工作会有点临时变动，休息时更想出去透透气，不太喜欢日子收得太紧。", datetime(2026, 5, 8, 21, 50, 20)),
            ("user-a", "能理解，今天先这样，改天有空再聊。", datetime(2026, 5, 8, 21, 50, 40)),
        ]
        for author_id, body, when in timeline:
            post_conversation_message(
                self.conn,
                main_group["conversation_id"],
                author_id,
                body,
                now=when,
            )

        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["observe_only"],
                "state_patch": {},
                "cooldown_seconds": 0,
            },
        ):
            run_chat_maintenance(
                self.conn,
                persona_limit=10,
                assistant_limit=10,
                assistant_post_chat_seconds=600,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 50, 50),
            )

        cur = self.conn.execute("SELECT COUNT(*) AS c FROM persona_sync_jobs")
        self.assertEqual(int(cur.fetchone()["c"]), 0)

        session = get_agent_session_by_case(self.conn, "case-conv-1")
        self.assertIsNotNone(session)
        assert session is not None
        last_message = list_conversation_messages(
            self.conn,
            main_group["conversation_id"],
            "user-a",
            limit=10,
        )[-1]
        self.conn.execute(
            """
            UPDATE chat_agent_sessions
            SET state_json = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(
                    {
                        "phase": "post_chat_ready",
                        "chat_end_at": "2026-05-08 21:50:40",
                        "chat_end_message_id": int(last_message["message_id"]),
                        "chat_end_reason": ["natural_ending", "mutual_closure"],
                    }
                ),
                session["session_id"],
            ),
        )
        self.conn.commit()

        upsert_calls: list[dict] = []
        fake_persona_module = types.ModuleType("persona_memory_sync")

        def _fake_upsert_persona_memory(request):
            upsert_calls.append(dict(request))
            return {"ok": True, "user_key": request["user_key"], "applied_patch": dict(request["patch"])}

        fake_persona_module.upsert_persona_memory = _fake_upsert_persona_memory

        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["post_chat_review", "history_only_persona_review"],
                "state_patch": {
                    "phase": "post_chat_followup",
                    "post_chat_review_status": "completed",
                    "chat_quality_assessment": "主群里已经自然暴露出生活节奏差异。",
                },
                "cooldown_seconds": 0,
                "persona_updates": [
                    {
                        "subject_user_id": "user-b",
                        "source_type": "weak_inference",
                        "patch": {
                            "preferred_traits": ["生活有弹性"],
                            "disliked_traits": ["关系前期过早收紧"],
                            "preference_summary_internal": "从整段聊天看，更适合生活节奏有弹性、关系前期不压得太紧的对象。",
                        },
                        "evidence_summary": "主群整段聊天里，B 明确表达休息时想出去透气，不喜欢日子收得太紧。",
                    }
                ],
            },
        ):
            with patch.dict(sys.modules, {"persona_memory_sync": fake_persona_module}):
                with patch.dict(
                    os.environ,
                    {"HER_CHAT_PERSONA_MYSQL_SOURCE": "mysql://root@127.0.0.1:3307/her?table=profiles"},
                    clear=False,
                ):
                    out = run_chat_maintenance(
                        self.conn,
                        persona_limit=10,
                        assistant_limit=10,
                        assistant_post_chat_seconds=600,
                        flush_outbox=False,
                        summary_max_threads=0,
                        now=datetime(2026, 5, 8, 22, 1, 0),
                    )

        self.assertEqual(out["assistant_triggers"]["post_chat_followup"]["enqueued"], 1)
        self.assertEqual(out["assistant"]["completed"], 1)
        self.assertEqual(out["assistant"]["replies_posted"], 0)
        self.assertEqual(out["persona"]["applied"], 1)
        self.assertEqual(len(upsert_calls), 1)
        self.assertEqual(upsert_calls[0]["user_key"], "user-b")
        self.assertEqual(upsert_calls[0]["source_type"], "weak_inference")

        dm_a_messages = list_conversation_messages(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "user-a",
            limit=20,
        )
        dm_b_messages = list_conversation_messages(
            self.conn,
            by_role["assistant_dm_b"]["conversation_id"],
            "user-b",
            limit=20,
        )
        self.assertEqual(dm_a_messages, [])
        self.assertEqual(dm_b_messages, [])

    def test_post_chat_followup_skips_side_with_proactive_dm_feedback(self):
        layout = self._create_layout()
        by_role = {item["metadata"]["layout_role"]: item for item in layout["conversations"]}
        main_group = by_role["main_group"]

        post_conversation_message(
            self.conn,
            main_group["conversation_id"],
            "user-a",
            "今天先这样吧，我这边去忙了。",
            now=datetime(2026, 5, 8, 22, 10, 0),
        )
        end_b = post_conversation_message(
            self.conn,
            main_group["conversation_id"],
            "user-b",
            "好，改天聊。",
            now=datetime(2026, 5, 8, 22, 10, 20),
        )

        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["observe_only"],
                "state_patch": {},
                "cooldown_seconds": 0,
            },
        ):
            run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                assistant_post_chat_seconds=600,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 22, 10, 30),
            )

        session = get_agent_session_by_case(self.conn, "case-conv-1")
        self.assertIsNotNone(session)
        assert session is not None
        self.conn.execute(
            """
            UPDATE chat_agent_sessions
            SET state_json = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(
                    {
                        "phase": "post_chat_ready",
                        "chat_end_at": "2026-05-08 22:10:20",
                        "chat_end_message_id": int(end_b["message_id"]),
                        "chat_end_reason": ["natural_ending", "mutual_closure"],
                    }
                ),
                session["session_id"],
            ),
        )
        self.conn.commit()

        post_conversation_message(
            self.conn,
            by_role["assistant_dm_b"]["conversation_id"],
            "user-b",
            "我觉得他整体挺稳的，聊着也舒服，可以继续了解看看。",
            now=datetime(2026, 5, 8, 22, 15, 0),
        )
        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": True,
                "target_channel_key": "assistant_dm_b",
                "reply_body": "收到，这个反馈我记下了。你这边整体是正向的，后面顺着自然节奏再看看就行。",
                "reason_codes": ["post_chat_followup", "feedback_captured"],
                "state_patch": {
                    "post_chat_review_status": "completed",
                    "followup_b_status": "user_initiated",
                    "followup_b_feedback_level": "clear",
                    "followup_a_status": "sent",
                    "phase": "post_chat_followup",
                },
                "cooldown_seconds": 300,
                "additional_actions": [
                    {
                        "target_channel_key": "assistant_dm_a",
                        "reply_body": "这轮聊下来，你对她第一感觉怎么样？如果只说直觉，最加分的一点是什么？",
                    }
                ],
            },
        ):
            first_out = run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                assistant_post_chat_seconds=600,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 22, 15, 10),
            )
        self.assertEqual(first_out["assistant"]["replies_posted"], 2)

        second_out = run_chat_maintenance(
            self.conn,
            persona_limit=0,
            assistant_limit=10,
            assistant_post_chat_seconds=600,
            flush_outbox=False,
            summary_max_threads=0,
            now=datetime(2026, 5, 8, 22, 21, 0),
        )

        self.assertEqual(second_out["assistant_triggers"]["post_chat_followup"]["enqueued"], 0)

        dm_a_messages = list_conversation_messages(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "user-a",
            limit=20,
        )
        dm_b_messages = list_conversation_messages(
            self.conn,
            by_role["assistant_dm_b"]["conversation_id"],
            "user-b",
            limit=20,
        )
        self.assertEqual(len(dm_a_messages), 1)
        self.assertEqual(len(dm_b_messages), 2)
        self.assertIn("第一感觉", dm_a_messages[0]["body"])
        self.assertIn("反馈我记下了", dm_b_messages[-1]["body"])

        updated_session = get_agent_session_by_case(self.conn, "case-conv-1")
        assert updated_session is not None
        self.assertEqual(updated_session["state"]["followup_a_status"], "sent")
        self.assertEqual(updated_session["state"]["followup_b_status"], "user_initiated")

    def test_post_chat_followup_is_cancelled_when_main_group_resumes(self):
        layout = self._create_layout()
        by_role = {item["metadata"]["layout_role"]: item for item in layout["conversations"]}
        main_group = by_role["main_group"]

        post_conversation_message(
            self.conn,
            main_group["conversation_id"],
            "user-a",
            "那今天先这样。",
            now=datetime(2026, 5, 8, 22, 30, 0),
        )
        end_b = post_conversation_message(
            self.conn,
            main_group["conversation_id"],
            "user-b",
            "好，改天继续聊。",
            now=datetime(2026, 5, 8, 22, 30, 20),
        )

        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["observe_only"],
                "state_patch": {},
                "cooldown_seconds": 0,
            },
        ):
            run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                assistant_post_chat_seconds=600,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 22, 30, 30),
            )

        session = get_agent_session_by_case(self.conn, "case-conv-1")
        self.assertIsNotNone(session)
        assert session is not None
        self.conn.execute(
            """
            UPDATE chat_agent_sessions
            SET state_json = ?
            WHERE session_id = ?
            """,
            (
                json.dumps(
                    {
                        "phase": "post_chat_ready",
                        "chat_end_at": "2026-05-08 22:30:20",
                        "chat_end_message_id": int(end_b["message_id"]),
                        "chat_end_reason": ["natural_ending", "mutual_closure"],
                    }
                ),
                session["session_id"],
            ),
        )
        self.conn.commit()

        post_conversation_message(
            self.conn,
            main_group["conversation_id"],
            "user-a",
            "对了，刚想起来问一句，你平时会自己做饭吗？",
            now=datetime(2026, 5, 8, 22, 33, 0),
        )
        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["observe_only"],
                "state_patch": {},
                "cooldown_seconds": 0,
            },
        ):
            run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                assistant_post_chat_seconds=600,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 22, 33, 10),
            )

        out = run_chat_maintenance(
            self.conn,
            persona_limit=0,
            assistant_limit=10,
            assistant_post_chat_seconds=600,
            flush_outbox=False,
            summary_max_threads=0,
            now=datetime(2026, 5, 8, 22, 41, 0),
        )

        self.assertEqual(out["assistant_triggers"]["post_chat_followup"]["enqueued"], 0)
        updated_session = get_agent_session_by_case(self.conn, "case-conv-1")
        assert updated_session is not None
        self.assertEqual(updated_session["state"]["phase"], "active")

        dm_a_messages = list_conversation_messages(
            self.conn,
            by_role["assistant_dm_a"]["conversation_id"],
            "user-a",
            limit=20,
        )
        dm_b_messages = list_conversation_messages(
            self.conn,
            by_role["assistant_dm_b"]["conversation_id"],
            "user-b",
            limit=20,
        )
        self.assertEqual(dm_a_messages, [])
        self.assertEqual(dm_b_messages, [])

    def test_post_chat_persona_update_is_enqueued_and_processed(self):
        layout = self._create_layout()
        by_role = {item["metadata"]["layout_role"]: item for item in layout["conversations"]}

        post_conversation_message(
            self.conn,
            by_role["assistant_dm_b"]["conversation_id"],
            "user-b",
            "我还是会更希望生活里保留一点弹性，关系前期别一下子收得太紧。",
            now=datetime(2026, 5, 8, 22, 45, 0),
        )

        upsert_calls: list[dict] = []
        fake_persona_module = types.ModuleType("persona_memory_sync")

        def _fake_upsert_persona_memory(request):
            upsert_calls.append(dict(request))
            return {"ok": True, "user_key": request["user_key"], "applied_patch": dict(request["patch"])}

        fake_persona_module.upsert_persona_memory = _fake_upsert_persona_memory

        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": True,
                "target_channel_key": "assistant_dm_b",
                "reply_body": "我记下了，你更在意的是节奏别太紧、生活里保留一点弹性。",
                "reason_codes": ["post_chat_followup", "match_direction_review"],
                "state_patch": {
                    "phase": "post_chat_followup",
                    "followup_b_status": "completed",
                    "followup_b_signal_summary": "更在意生活弹性，关系前期不喜欢太快收紧",
                },
                "cooldown_seconds": 300,
                "persona_updates": [
                    {
                        "subject_user_id": "user-b",
                        "source_type": "explicit",
                        "basis": "self_statement",
                        "apply_scope": "observation_only",
                        "patch": {
                            "persona_summary_internal": "工作节奏波动较多，生活里更需要留一点弹性空间。",
                        },
                        "evidence_summary": "聊后反馈里，B 明确提到自己的工作安排经常会有临时变化。",
                    },
                    {
                        "subject_user_id": "user-b",
                        "source_type": "strong_inference",
                        "basis": "stable_inference",
                        "apply_scope": "persona_only",
                        "patch": {
                            "preferred_traits": ["生活有弹性"],
                            "disliked_traits": ["关系前期过早收紧"],
                            "preference_summary_internal": "更适合节奏自然、有弹性的关系，不喜欢刚开始就把相处压得太紧。",
                        },
                        "evidence_summary": "聊后反馈里，B 明确表达希望生活保留弹性，关系前期别太快收紧。",
                    }
                ],
            },
        ):
            with patch.dict(
                sys.modules,
                {"persona_memory_sync": fake_persona_module},
            ):
                with patch.dict(
                    os.environ,
                    {"HER_CHAT_PERSONA_MYSQL_SOURCE": "mysql://root@127.0.0.1:3307/her?table=profiles"},
                    clear=False,
                ):
                    out = run_chat_maintenance(
                        self.conn,
                        persona_limit=10,
                        assistant_limit=10,
                        flush_outbox=True,
                        summary_max_threads=0,
                        now=datetime(2026, 5, 8, 22, 45, 10),
                    )

        self.assertEqual(out["assistant"]["completed"], 1, out["assistant"])
        self.assertEqual(out["persona"]["applied"], 2, out["persona"])
        self.assertEqual(len(upsert_calls), 2)
        self.assertEqual(upsert_calls[0]["user_key"], "user-b")
        self.assertEqual(upsert_calls[0]["source_type"], "explicit")
        self.assertEqual(upsert_calls[0]["apply_scope"], "observation_only")
        self.assertFalse(upsert_calls[0]["sync_profile"])
        self.assertIn("persona_summary_internal", upsert_calls[0]["patch"])
        self.assertEqual(upsert_calls[1]["source_type"], "strong_inference")
        self.assertEqual(upsert_calls[1]["apply_scope"], "persona_only")
        self.assertFalse(upsert_calls[1]["sync_profile"])
        self.assertIn("preferred_traits", upsert_calls[1]["patch"])

        rows = self.conn.execute(
            "SELECT status, patch_json, evidence_json FROM persona_sync_jobs ORDER BY job_id ASC"
        ).fetchall()
        self.assertEqual(len(rows), 2)
        first_row = rows[0]
        second_row = rows[1]
        self.assertEqual(first_row["status"], "applied")
        self.assertEqual(second_row["status"], "applied")
        self.assertIn("persona_summary_internal", json.loads(first_row["patch_json"]))
        self.assertIn("preferred_traits", json.loads(second_row["patch_json"]))
        self.assertIn("assistant_post_chat_review", first_row["evidence_json"])
        self.assertIn("assistant_post_chat_review", second_row["evidence_json"])

    def test_idle_matchmaker_session_can_be_closed(self):
        layout = self._create_layout()
        main = next(
            item for item in layout["conversations"]
            if item["metadata"]["layout_role"] == "main_group"
        )
        post_conversation_message(
            self.conn,
            main["conversation_id"],
            "user-b",
            "今天先简单认识一下。",
            now=datetime(2026, 5, 8, 21, 21, 0),
        )

        with patch(
            "chat_system.assistant_orchestrator.run_matchmaker_agent",
            return_value={
                "should_reply": False,
                "target_channel_key": None,
                "reply_body": None,
                "reason_codes": ["observe_only"],
                "state_patch": {"relationship_stage": "starting"},
                "cooldown_seconds": 0,
            },
        ):
            run_chat_maintenance(
                self.conn,
                persona_limit=0,
                assistant_limit=10,
                flush_outbox=True,
                summary_max_threads=0,
                now=datetime(2026, 5, 8, 21, 21, 30),
            )

        closed = close_idle_agent_sessions(
            self.conn,
            idle_seconds=1800,
            now=datetime(2026, 5, 8, 22, 0, 0),
        )
        self.conn.commit()
        session = get_agent_session_by_case(self.conn, "case-conv-1")
        self.assertEqual(closed, 1)
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session["status"], "closed")
        self.assertEqual(session["close_reason"], "idle_timeout")


if __name__ == "__main__":
    unittest.main()
