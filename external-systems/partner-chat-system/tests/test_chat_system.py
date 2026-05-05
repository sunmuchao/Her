import os
import pathlib
import sys
import unittest
from datetime import datetime


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system import (  # noqa: E402
    adopt_draft,
    assistant_query,
    get_or_create_thread,
    get_thread,
    list_messages,
    post_message,
)
from chat_system.outbox_admin import list_pending_outbox  # noqa: E402
from chat_system.persona_jobs import list_pending_persona_jobs, process_pending_persona_jobs  # noqa: E402
from chat_system.service import ASSISTANT_AUTHOR_ID, SRC_AGENT_DRAFT, VIS_DYADIC, VIS_OWNER_ONLY  # noqa: E402
from chat_system.storage import DEFAULT_CHAT_TEST_MYSQL_DSN, connect_db, initialize_database, reset_all_tables  # noqa: E402


class ChatSystemTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("HER_CHAT_ASSISTANT_BASE_URL", None)
        os.environ.pop("OPENAI_BASE_URL", None)
        self.conn = connect_db(DEFAULT_CHAT_TEST_MYSQL_DSN)
        initialize_database(self.conn)
        reset_all_tables(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_thread_create_idempotent_and_messages(self):
        t1 = get_or_create_thread(
            self.conn,
            case_id="case-1",
            relation_key="rel-a|b",
            participant_a_id="user-a",
            participant_b_id="user-b",
            metadata={"source": "test"},
            now=datetime(2026, 5, 4, 10, 0, 0),
        )
        t2 = get_or_create_thread(
            self.conn,
            case_id="case-1",
            relation_key="rel-a|b",
            participant_a_id="user-a",
            participant_b_id="user-b",
            now=datetime(2026, 5, 4, 10, 1, 0),
        )
        self.assertEqual(t1["thread_id"], t2["thread_id"])

        post_message(
            self.conn,
            t1["thread_id"],
            "user-a",
            "hello b",
            visibility=VIS_DYADIC,
            now=datetime(2026, 5, 4, 10, 2, 0),
        )
        a_msgs = list_messages(self.conn, t1["thread_id"], "user-a")
        b_msgs = list_messages(self.conn, t1["thread_id"], "user-b")
        self.assertEqual(len(a_msgs), 1)
        self.assertEqual(len(b_msgs), 1)
        self.assertEqual(a_msgs[0]["body"], "hello b")

        post_message(
            self.conn,
            t1["thread_id"],
            "user-a",
            "note to self",
            visibility=VIS_OWNER_ONLY,
            message_recipient_id="user-a",
            now=datetime(2026, 5, 4, 10, 3, 0),
        )
        a_all = list_messages(self.conn, t1["thread_id"], "user-a")
        b_only = list_messages(self.conn, t1["thread_id"], "user-b")
        self.assertEqual(len(a_all), 2)
        self.assertEqual(len(b_only), 1)

    def test_client_msg_idempotent(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-idem",
            relation_key="r1",
            participant_a_id="u1",
            participant_b_id="u2",
        )
        m1 = post_message(
            self.conn,
            th["thread_id"],
            "u1",
            "x",
            client_msg_id="idem-1",
        )
        m2 = post_message(
            self.conn,
            th["thread_id"],
            "u1",
            "x",
            client_msg_id="idem-1",
        )
        self.assertEqual(m1["message_id"], m2["message_id"])

    def test_assistant_query_and_adopt(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-asst",
            relation_key="r2",
            participant_a_id="alice",
            participant_b_id="bob",
        )
        draft = assistant_query(self.conn, th["thread_id"], "alice", "怎么回复他？")

        self.assertEqual(draft["author_id"], ASSISTANT_AUTHOR_ID)
        self.assertEqual(draft["source"], SRC_AGENT_DRAFT)
        self.assertEqual(draft["message_recipient_id"], "alice")
        self.assertIn("当前问题：", draft["body"])
        self.assertIn("回复建议：", draft["body"])
        self.assertNotIn("采纳草稿", draft["body"])

        alice_view = list_messages(self.conn, th["thread_id"], "alice")
        bob_view = list_messages(self.conn, th["thread_id"], "bob")
        self.assertGreaterEqual(len(alice_view), 1)
        self.assertEqual(len(bob_view), 0)

        sent = adopt_draft(
            self.conn,
            th["thread_id"],
            int(draft["message_id"]),
            "alice",
            body_override="你好，很高兴认识你。",
        )
        self.assertEqual(sent["visibility"], VIS_DYADIC)

        both = list_messages(self.conn, th["thread_id"], "bob")
        self.assertTrue(any(m["body"] == "你好，很高兴认识你。" for m in both))

    def test_adopt_draft_requires_user_override(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-asst-override",
            relation_key="r2b",
            participant_a_id="alice",
            participant_b_id="bob",
        )
        draft = assistant_query(self.conn, th["thread_id"], "alice", "怎么接话？")

        with self.assertRaisesRegex(ValueError, "body_override is required"):
            adopt_draft(
                self.conn,
                th["thread_id"],
                int(draft["message_id"]),
                "alice",
            )
        with self.assertRaisesRegex(ValueError, "must be user-edited"):
            adopt_draft(
                self.conn,
                th["thread_id"],
                int(draft["message_id"]),
                "alice",
                body_override=str(draft["body"]),
            )

    def test_get_thread(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-gt",
            relation_key="r3",
            participant_a_id="a",
            participant_b_id="b",
        )
        row = get_thread(self.conn, th["thread_id"])
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["case_id"], "case-gt")
        self.assertEqual(row["metadata"], {})

    def test_outbox_rows_on_thread_and_message(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-ob",
            relation_key="rob",
            participant_a_id="oa",
            participant_b_id="ob",
        )
        c1 = self.conn.execute("SELECT COUNT(*) AS c FROM outbox_events", ()).fetchone()
        self.assertGreaterEqual(int(c1["c"]), 1)
        post_message(self.conn, th["thread_id"], "oa", "ping", visibility=VIS_DYADIC)
        c2 = self.conn.execute("SELECT COUNT(*) AS c FROM outbox_events", ()).fetchone()
        self.assertGreaterEqual(int(c2["c"]), 2)
        pending = list_pending_outbox(self.conn, limit=50)
        self.assertGreaterEqual(len(pending), 2)

    def test_persona_job_heuristic_and_process(self):
        th = get_or_create_thread(
            self.conn,
            case_id="case-pj",
            relation_key="rpj",
            participant_a_id="pa",
            participant_b_id="pb",
        )
        post_message(
            self.conn,
            th["thread_id"],
            "pa",
            "我在杭州工作，岗位是产品经理",
            visibility=VIS_DYADIC,
        )
        jobs = list_pending_persona_jobs(self.conn)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["status"], "pending")
        out = process_pending_persona_jobs(self.conn, limit=10)
        self.assertGreaterEqual(out["examined"], 1)
        self.assertGreaterEqual(out["needs_review"], 1)
        cur = self.conn.execute(
            "SELECT status FROM persona_sync_jobs WHERE job_id = ?",
            (int(jobs[0]["job_id"]),),
        )
        st = cur.fetchone()
        self.assertIsNotNone(st)
        assert st is not None
        self.assertEqual(st["status"], "needs_review")

    def test_outbox_consume_clears_pending(self):
        from chat_system.outbox_consumer import consume_chat_outbox_batch

        th = get_or_create_thread(
            self.conn,
            case_id="case-oc",
            relation_key="roc",
            participant_a_id="x",
            participant_b_id="y",
        )
        post_message(self.conn, th["thread_id"], "x", "one", visibility=VIS_DYADIC)
        self.assertGreaterEqual(len(list_pending_outbox(self.conn)), 1)
        out = consume_chat_outbox_batch(self.conn, limit=50)
        self.assertGreaterEqual(out["marked_published"], 1)
        self.assertEqual(len(list_pending_outbox(self.conn)), 0)

    def test_maintenance_refreshes_summary(self):
        from chat_system.maintenance import run_chat_maintenance
        from chat_system.summaries import get_thread_summary

        th = get_or_create_thread(
            self.conn,
            case_id="case-sum",
            relation_key="rsum",
            participant_a_id="sa",
            participant_b_id="sb",
        )
        post_message(self.conn, th["thread_id"], "sa", "hello summary line", visibility=VIS_DYADIC)
        run_chat_maintenance(self.conn, persona_limit=0, flush_outbox=False)
        s = get_thread_summary(self.conn, th["thread_id"])
        self.assertIsNotNone(s)
        assert s is not None
        self.assertIn("hello summary line", s["summary_text"])


if __name__ == "__main__":
    unittest.main()
