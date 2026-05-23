import pathlib
import sys
import unittest
import os
from datetime import datetime


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from matchmaking_system import (  # noqa: E402
    build_mutual_pairs,
    close_stale_cases,
    connect_db,
    create_pool_member,
    dispatch_case_contact,
    get_match_case,
    get_pair,
    get_pool_member,
    initialize_database,
    list_pending_outbox,
    list_feedback_events,
    list_match_case_events,
    list_match_cases,
    list_pairs,
    open_match_cases,
    record_case_reply,
    record_feedback,
    refresh_active_pool,
    reset_all_tables,
    run_matchmaking_outbox_worker,
    set_pool_member_status,
)
from matchmaking_system.storage import DEFAULT_MATCHMAKING_TEST_MYSQL_DSN  # noqa: E402
from relationship_ledger import (  # noqa: E402
    connect_db as connect_ledger_db,
    get_relation_by_key,
    initialize_database as initialize_ledger_db,
    reset_all_tables as reset_ledger_tables,
)
from relationship_ledger.storage import DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN  # noqa: E402


def build_result(candidate_id, name, score, *, city="无锡", risk_flags=None, follow_up_questions=None):
    return {
        "id": candidate_id,
        "name": name,
        "score": score,
        "fit_score": max(score - 8, 0),
        "confidence_score": 10,
        "risk_score": 0,
        "matched_on": ["同城", "目标一致"],
        "reciprocal_on": ["偏好匹配"],
        "missing_fields": [],
        "self_profile_gaps": [],
        "risk_flags": risk_flags or [],
        "match_evidence": [],
        "follow_up_questions": follow_up_questions or [],
        "photo_preview": [],
        "source": "mysql://user:***@127.0.0.1:3306/her?table=profiles#profiles",
        "profile": {
            "age": 29,
            "city": city,
            "job": "产品经理",
            "relationship_goal": "认真恋爱",
        },
    }


class MatchmakingSystemTests(unittest.TestCase):
    def setUp(self):
        self._old_relation_ledger_db = os.environ.get("HER_RELATION_LEDGER_DB")
        os.environ["HER_RELATION_LEDGER_DB"] = DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN
        self.conn = connect_db(DEFAULT_MATCHMAKING_TEST_MYSQL_DSN)
        initialize_database(self.conn)
        reset_all_tables(self.conn)
        self.ledger_conn = connect_ledger_db(DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN)
        initialize_ledger_db(self.ledger_conn)
        reset_ledger_tables(self.ledger_conn)
        self.source = "mysql://user:pass@127.0.0.1:3306/her?table=profiles"

    def tearDown(self):
        self.conn.close()
        self.ledger_conn.close()
        if self._old_relation_ledger_db is None:
            os.environ.pop("HER_RELATION_LEDGER_DB", None)
        else:
            os.environ["HER_RELATION_LEDGER_DB"] = self._old_relation_ledger_db

    def load_relation(self, relation_key: str):
        self.ledger_conn.close()
        self.ledger_conn = connect_ledger_db(DEFAULT_RELATION_LEDGER_TEST_MYSQL_DSN)
        return get_relation_by_key(self.ledger_conn, relation_key)

    def create_member(self, user_key, self_id, **overrides):
        base = {
            "user_key": user_key,
            "source": self.source,
            "self_id": self_id,
            "search_criteria": {
                "gender": "女" if self_id == 1001 else "男",
                "cities": ["无锡"],
                "relationship_goals": ["认真恋爱", "结婚导向"],
            },
            "self_profile": {
                "age": 29 if self_id == 1001 else 28,
                "city": "无锡",
                "height": 170,
            },
            "min_pair_score": 80,
            "limit_count": 5,
            "refresh_interval_hours": 24,
            "now": datetime(2026, 5, 2, 9, 0, 0),
        }
        base.update(overrides)
        return create_pool_member(self.conn, **base)

    def test_refresh_pool_builds_mutual_pairs_and_runs_case_flow(self):
        member_a = self.create_member("user-a", 1001)
        member_b = self.create_member("user-b", 1002)

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 92)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 88)]}
            return {"results": []}

        refresh_summaries = refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        self.assertEqual(len(refresh_summaries), 2)

        pairs = build_mutual_pairs(
            self.conn,
            now=datetime(2026, 5, 2, 9, 5, 0),
        )
        self.assertEqual(len(pairs), 1)
        pair = pairs[0]
        self.assertEqual(pair["pair_status"], "eligible")
        self.assertEqual(pair["pair_score"], 88)
        self.assertEqual(pair["canonical_pair_status"], "eligible")
        self.assertIn("<->", pair["canonical_pair_key"])
        relation = self.load_relation(pair["canonical_pair_key"])
        self.assertIsNotNone(relation)
        self.assertEqual(relation["relation_status"], "matched")
        self.assertEqual(relation["current_phase"], "matched")

        cases = open_match_cases(
            self.conn,
            now=datetime(2026, 5, 2, 9, 10, 0),
        )
        self.assertEqual(len(cases), 1)
        case = cases[0]
        self.assertEqual(case["status"], "pending_first_contact")
        self.assertEqual(case["case_type"], "matchmaking")
        self.assertEqual(case["canonical_case_status"], "pending_contact")
        relation = self.load_relation(pair["canonical_pair_key"])
        self.assertIsNotNone(relation)
        self.assertEqual(relation["active_case_id"], case["case_id"])
        self.assertEqual(relation["current_phase"], "case_active")
        self.assertIn("pair_case_opened", {event["event_type"] for event in relation["events"]})

        case = dispatch_case_contact(
            self.conn,
            case["case_id"],
            now=datetime(2026, 5, 2, 9, 11, 0),
        )
        self.assertEqual(case["status"], "awaiting_first_reply")

        case = record_case_reply(
            self.conn,
            case["case_id"],
            member_id=case["first_contact_member_id"],
            reply_type="accept",
            now=datetime(2026, 5, 2, 9, 12, 0),
        )
        self.assertEqual(case["status"], "pending_second_contact")

        case = dispatch_case_contact(
            self.conn,
            case["case_id"],
            now=datetime(2026, 5, 2, 9, 13, 0),
        )
        self.assertEqual(case["status"], "awaiting_second_reply")

        case = record_case_reply(
            self.conn,
            case["case_id"],
            member_id=case["second_contact_member_id"],
            reply_type="accept",
            now=datetime(2026, 5, 2, 9, 14, 0),
        )
        self.assertEqual(case["status"], "mutual_accept")

        pair = get_pair(self.conn, pair["pair_key"])
        self.assertEqual(pair["pair_status"], "mutual_accept")
        relation = self.load_relation(pair["canonical_pair_key"])
        self.assertIsNotNone(relation)
        self.assertEqual(relation["relation_status"], "matched")
        self.assertIn("pair_mutual_accept", {event["event_type"] for event in relation["events"]})
        events = list_match_case_events(self.conn, case["case_id"])
        self.assertEqual(
            [event["event_type"] for event in events],
            [
                "case_created",
                "first_contact_sent",
                "first_reply_accepted",
                "second_contact_sent",
                "second_reply_accepted",
            ],
        )
        self.assertEqual(events[0]["payload"]["canonical_event"]["payload"]["case_type"], "matchmaking")

        all_cases = list_match_cases(self.conn)
        self.assertEqual(len(all_cases), 1)
        self.assertEqual(all_cases[0]["status"], "mutual_accept")

        self.assertEqual(get_pool_member(self.conn, member_a["member_id"])["needs_refresh"], 0)
        self.assertEqual(get_pool_member(self.conn, member_b["member_id"])["needs_refresh"], 0)

    def test_outbox_worker_consumes_match_case_events(self):
        self.create_member("user-a", 1001)
        self.create_member("user-b", 1002)

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 92)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 88)]}
            return {"results": []}

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        build_mutual_pairs(self.conn, now=datetime(2026, 5, 2, 9, 5, 0))
        cases = open_match_cases(self.conn, now=datetime(2026, 5, 2, 9, 10, 0))

        self.assertEqual(len(cases), 1)
        self.assertGreaterEqual(len(list_pending_outbox(self.conn, limit=20)), 1)
        result = run_matchmaking_outbox_worker(
            self.conn,
            limit=20,
            max_batches=2,
            now=datetime(2026, 5, 2, 9, 10, 30),
        )

        self.assertGreaterEqual(result["totals"]["marked_published"], 1)
        self.assertEqual(len(list_pending_outbox(self.conn, limit=20, now=datetime(2026, 5, 2, 9, 10, 31))), 0)

    def test_feedback_auto_syncs_persona_and_marks_pairs_for_revalidation(self):
        member_a = self.create_member("user-a", 1001)
        member_b = self.create_member("user-b", 1002)

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 90)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 91)]}
            return {"results": []}

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        pair = build_mutual_pairs(
            self.conn,
            now=datetime(2026, 5, 2, 9, 5, 0),
        )[0]
        case = open_match_cases(
            self.conn,
            now=datetime(2026, 5, 2, 9, 10, 0),
        )[0]

        persona_calls = []

        def fake_persona_sync_runner(request):
            persona_calls.append(dict(request))
            return {"updated": True, "patch": request["patch"]}

        feedback = record_feedback(
            self.conn,
            member_id=member_a["member_id"],
            feedback_kind="long_term_preference",
            feedback_type="reject_long_distance",
            feedback_text="异地不想聊",
            persona_patch={"accept_long_distance": "否"},
            now=datetime(2026, 5, 2, 9, 20, 0),
            persona_sync_runner=fake_persona_sync_runner,
        )

        self.assertEqual(len(persona_calls), 1)
        self.assertEqual(persona_calls[0]["user_key"], "user-a")
        self.assertEqual(persona_calls[0]["patch"], {"accept_long_distance": "否"})
        self.assertTrue(feedback["synced_to_persona_memory"])

        updated_member = get_pool_member(self.conn, member_a["member_id"])
        self.assertEqual(updated_member["needs_refresh"], 1)
        refreshed_member_b = get_pool_member(self.conn, member_b["member_id"])
        self.assertEqual(refreshed_member_b["needs_refresh"], 1)

        pair = get_pair(self.conn, pair["pair_key"])
        self.assertEqual(pair["pair_status"], "needs_revalidation")

        case = get_match_case(self.conn, case["case_id"])
        self.assertEqual(case["status"], "closed")
        self.assertEqual(case["closed_reason"], "member_feedback_requires_revalidation")

        refresh_summaries = refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 30, 0),
            search_runner=fake_search_runner,
        )
        self.assertEqual(len(refresh_summaries), 2)
        rebuilt_pair = build_mutual_pairs(
            self.conn,
            now=datetime(2026, 5, 2, 9, 35, 0),
        )[0]
        self.assertEqual(rebuilt_pair["pair_status"], "eligible")

        feedback_events = list_feedback_events(self.conn, member_a["member_id"])
        self.assertEqual(len(feedback_events), 1)
        self.assertEqual(feedback_events[0]["feedback_type"], "reject_long_distance")
        self.assertEqual(
            feedback_events[0]["raw_payload"]["canonical_event"]["aggregate_type"],
            "member_feedback",
        )

    def test_paused_member_does_not_generate_eligible_pair(self):
        self.create_member("user-a", 1001)
        member_b = self.create_member(
            "user-b",
            1002,
            status="paused_serious_chat",
            is_still_searching=False,
        )

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 95)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 95)]}
            return {"results": []}

        refresh_summaries = refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        self.assertEqual(len(refresh_summaries), 1)

        pairs = build_mutual_pairs(
            self.conn,
            now=datetime(2026, 5, 2, 9, 5, 0),
        )
        self.assertEqual(pairs, [])
        self.assertEqual(list_pairs(self.conn), [])

        updated_member_b = get_pool_member(self.conn, member_b["member_id"])
        self.assertEqual(updated_member_b["status"], "paused_serious_chat")

    def test_decline_puts_pair_into_cooling(self):
        self.create_member("user-a", 1001)
        self.create_member("user-b", 1002)

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 90)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 90)]}
            return {"results": []}

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        pair = build_mutual_pairs(self.conn, now=datetime(2026, 5, 2, 9, 5, 0))[0]
        case = open_match_cases(self.conn, now=datetime(2026, 5, 2, 9, 10, 0))[0]
        case = dispatch_case_contact(
            self.conn,
            case["case_id"],
            now=datetime(2026, 5, 2, 9, 11, 0),
        )
        case = record_case_reply(
            self.conn,
            case["case_id"],
            member_id=case["first_contact_member_id"],
            reply_type="decline",
            now=datetime(2026, 5, 2, 9, 12, 0),
        )
        self.assertEqual(case["status"], "declined")

        pair = get_pair(self.conn, pair["pair_key"])
        self.assertEqual(pair["pair_status"], "cooling")
        self.assertEqual(pair["block_reason"], "first_contact_decline")

    def test_pair_cooling_stays_sticky_until_expiry_then_reopens(self):
        self.create_member("user-a", 1001)
        self.create_member("user-b", 1002)

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 90)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 90)]}
            return {"results": []}

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        pair = build_mutual_pairs(self.conn, now=datetime(2026, 5, 2, 9, 5, 0))[0]
        case = open_match_cases(self.conn, now=datetime(2026, 5, 2, 9, 10, 0))[0]
        case = dispatch_case_contact(
            self.conn,
            case["case_id"],
            now=datetime(2026, 5, 2, 9, 11, 0),
        )
        record_case_reply(
            self.conn,
            case["case_id"],
            member_id=case["first_contact_member_id"],
            reply_type="decline",
            now=datetime(2026, 5, 2, 9, 12, 0),
        )

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 10, 0, 0),
            search_runner=fake_search_runner,
        )
        rebuilt = build_mutual_pairs(self.conn, now=datetime(2026, 5, 2, 10, 5, 0))[0]
        self.assertEqual(rebuilt["pair_key"], pair["pair_key"])
        self.assertEqual(rebuilt["pair_status"], "cooling")

        self.conn.execute(
            "UPDATE matchmaking_pairs SET cooling_until = ? WHERE pair_key = ?",
            ("2026-05-02 09:00:00", pair["pair_key"]),
        )
        self.conn.commit()

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 4, 10, 0, 0),
            search_runner=fake_search_runner,
        )
        reopened = build_mutual_pairs(self.conn, now=datetime(2026, 5, 4, 10, 5, 0))[0]
        self.assertEqual(reopened["pair_status"], "eligible")

    def test_close_stale_cases_marks_timeout(self):
        self.create_member("user-a", 1001)
        self.create_member("user-b", 1002)

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 90)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 90)]}
            return {"results": []}

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        build_mutual_pairs(self.conn, now=datetime(2026, 5, 2, 9, 5, 0))
        case = open_match_cases(self.conn, now=datetime(2026, 5, 2, 9, 10, 0))[0]
        dispatch_case_contact(
            self.conn,
            case["case_id"],
            now=datetime(2026, 5, 2, 9, 11, 0),
        )
        self.conn.execute(
            "UPDATE match_cases SET expires_at = ? WHERE case_id = ?",
            ("2026-05-01 09:00:00", case["case_id"]),
        )
        self.conn.commit()

        summary = close_stale_cases(
            self.conn,
            now=datetime(2026, 5, 2, 10, 0, 0),
        )
        self.assertEqual(summary["closed_count"], 1)
        closed = get_match_case(self.conn, case["case_id"])
        self.assertEqual(closed["status"], "timed_out")

    def test_mutual_accept_stays_sticky_after_refresh_rebuild(self):
        self.create_member("user-a", 1001)
        self.create_member("user-b", 1002)

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 92)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 91)]}
            return {"results": []}

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        pair = build_mutual_pairs(self.conn, now=datetime(2026, 5, 2, 9, 5, 0))[0]
        case = open_match_cases(self.conn, now=datetime(2026, 5, 2, 9, 10, 0))[0]
        case = dispatch_case_contact(
            self.conn,
            case["case_id"],
            now=datetime(2026, 5, 2, 9, 11, 0),
        )
        case = record_case_reply(
            self.conn,
            case["case_id"],
            member_id=case["first_contact_member_id"],
            reply_type="accept",
            now=datetime(2026, 5, 2, 9, 12, 0),
        )
        case = dispatch_case_contact(
            self.conn,
            case["case_id"],
            now=datetime(2026, 5, 2, 9, 13, 0),
        )
        record_case_reply(
            self.conn,
            case["case_id"],
            member_id=case["second_contact_member_id"],
            reply_type="accept",
            now=datetime(2026, 5, 2, 9, 14, 0),
        )

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 3, 10, 0, 0),
            search_runner=fake_search_runner,
        )
        rebuilt_pair = build_mutual_pairs(
            self.conn,
            now=datetime(2026, 5, 3, 10, 5, 0),
        )[0]
        self.assertEqual(rebuilt_pair["pair_key"], pair["pair_key"])
        self.assertEqual(rebuilt_pair["pair_status"], "mutual_accept")
        self.assertEqual(open_match_cases(self.conn, now=datetime(2026, 5, 3, 10, 10, 0)), [])

    def test_missing_reciprocal_edge_downgrades_pair_to_stale(self):
        member_a = self.create_member("user-a", 1001)
        self.create_member("user-b", 1002)

        def initial_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 90)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 90)]}
            return {"results": []}

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=initial_search_runner,
        )
        pair = build_mutual_pairs(self.conn, now=datetime(2026, 5, 2, 9, 5, 0))[0]

        self.conn.execute(
            "UPDATE matchmaking_pool_members SET needs_refresh = 1 WHERE member_id = ?",
            (member_a["member_id"],),
        )
        self.conn.commit()

        def followup_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": []}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 90)]}
            return {"results": []}

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 30, 0),
            search_runner=followup_search_runner,
            member_ids=[member_a["member_id"]],
        )
        build_mutual_pairs(self.conn, now=datetime(2026, 5, 2, 9, 35, 0))

        stale_pair = get_pair(self.conn, pair["pair_key"])
        self.assertEqual(stale_pair["pair_status"], "stale")
        self.assertEqual(stale_pair["block_reason"], "reciprocal_edge_missing")

    def test_paused_member_invalidates_existing_eligible_pair(self):
        self.create_member("user-a", 1001)
        member_b = self.create_member("user-b", 1002)

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 93)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 92)]}
            return {"results": []}

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        pair = build_mutual_pairs(self.conn, now=datetime(2026, 5, 2, 9, 5, 0))[0]
        self.assertEqual(pair["pair_status"], "eligible")

        set_pool_member_status(
            self.conn,
            member_b["member_id"],
            status="paused_serious_chat",
            is_still_searching=False,
            reason="already_chatting",
            now=datetime(2026, 5, 2, 9, 6, 0),
        )

        updated_pair = get_pair(self.conn, pair["pair_key"])
        self.assertEqual(updated_pair["pair_status"], "needs_revalidation")
        self.assertEqual(open_match_cases(self.conn, now=datetime(2026, 5, 2, 9, 10, 0)), [])
        self.assertEqual(list_match_cases(self.conn), [])

    def test_feedback_can_pause_member_without_persona_sync_and_close_open_case(self):
        self.create_member("user-a", 1001)
        member_b = self.create_member("user-b", 1002)

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 93)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 92)]}
            return {"results": []}

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        pair = build_mutual_pairs(self.conn, now=datetime(2026, 5, 2, 9, 5, 0))[0]
        case = open_match_cases(self.conn, now=datetime(2026, 5, 2, 9, 10, 0))[0]

        feedback = record_feedback(
            self.conn,
            member_id=member_b["member_id"],
            feedback_kind="relationship_status",
            feedback_type="already_chatting",
            feedback_text="已经在认真聊了，先暂停系统撮合",
            new_status="paused_serious_chat",
            now=datetime(2026, 5, 2, 9, 20, 0),
        )

        self.assertFalse(feedback["synced_to_persona_memory"])
        self.assertEqual(get_pool_member(self.conn, member_b["member_id"])["status"], "paused_serious_chat")

        updated_pair = get_pair(self.conn, pair["pair_key"])
        self.assertEqual(updated_pair["pair_status"], "needs_revalidation")

        closed_case = get_match_case(self.conn, case["case_id"])
        self.assertEqual(closed_case["status"], "closed")
        self.assertEqual(closed_case["closed_reason"], "member_feedback_requires_revalidation")

    def test_daily_case_cap_zero_blocks_new_cases(self):
        self.create_member("user-a", 1001, daily_case_cap=0)
        self.create_member("user-b", 1002)

        def fake_search_runner(**kwargs):
            self_id = kwargs.get("self_id")
            if self_id == 1001:
                return {"results": [build_result(1002, "小张", 90)]}
            if self_id == 1002:
                return {"results": [build_result(1001, "小李", 90)]}
            return {"results": []}

        refresh_active_pool(
            self.conn,
            now=datetime(2026, 5, 2, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        pair = build_mutual_pairs(self.conn, now=datetime(2026, 5, 2, 9, 5, 0))[0]
        self.assertEqual(open_match_cases(self.conn, now=datetime(2026, 5, 2, 9, 10, 0)), [])
        self.assertEqual(get_pair(self.conn, pair["pair_key"])["pair_status"], "eligible")
        self.assertEqual(list_match_cases(self.conn), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
