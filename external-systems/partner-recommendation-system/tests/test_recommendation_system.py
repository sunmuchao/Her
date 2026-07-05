import os
import pathlib
import sys
import unittest
from datetime import datetime
from unittest.mock import patch


SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from recommendation_system import (  # noqa: E402
    DEFAULT_NO_MATCH_OPT_IN_PROMPT,
    list_recommendation_conversion_views_for_subscription,
    connect_db,
    create_subscription,
    deliver_in_app_recommendations,
    get_subscription,
    handle_opt_in_decision,
    initialize_database,
    list_in_app_cards,
    list_recommendations_for_subscription,
    list_search_runs_for_subscription,
    record_recommendation_action,
    record_user_review,
    refresh_due_subscriptions,
    refresh_subscription,
    reset_all_tables,
    run_search_session,
    update_subscription_overrides,
)
from recommendation_system.service import load_requester_profile  # noqa: E402
from recommendation_system.storage import DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN  # noqa: E402

from match_domain import RULE_PROVENANCE_SCHEMA  # noqa: E402


def build_result(
    candidate_id,
    name,
    score,
    city="无锡",
    matched_on=None,
    risk_flags=None,
    reciprocal_on=None,
    follow_up_questions=None,
    missing_fields=None,
    self_profile_gaps=None,
    profile_overrides=None,
    verified_level="photo",
    trust_headline=None,
):
    matched_on = matched_on or ["城市 无锡", "目标 认真恋爱"]
    risk_flags = risk_flags or []
    reciprocal_on = reciprocal_on or []
    if follow_up_questions is None:
        follow_up_questions = ["确认最近的见面频率安排。"] if risk_flags else []
    missing_fields = missing_fields or []
    self_profile_gaps = self_profile_gaps or []
    profile = {
        "age": 28,
        "city": city,
        "job": "产品经理",
        "relationship_goal": "认真恋爱",
        "verified_level": verified_level,
        "photo_count": 4,
    }
    profile.update(profile_overrides or {})
    verified_label = {
        "basic": "基础认证",
        "photo": "照片认证",
        "id": "实名认证",
        "offline": "线下核验",
    }.get(str(profile.get("verified_level") or "").lower())
    return {
        "id": candidate_id,
        "name": name,
        "score": score,
        "fit_score": max(score - 10, 0),
        "confidence_score": 10,
        "risk_score": 0,
        "verified_level": profile.get("verified_level"),
        "verified_label": verified_label,
        "trust_summary": {
            "headline": trust_headline or f"{verified_label}；其余关键信息以资料填写为主：职业、结婚意向",
            "verified_label": verified_label,
            "badges": [verified_label] if verified_label else [],
        },
        "matched_on": matched_on,
        "reciprocal_on": reciprocal_on,
        "missing_fields": missing_fields,
        "self_profile_gaps": self_profile_gaps,
        "risk_flags": risk_flags,
        "match_evidence": [],
        "follow_up_questions": follow_up_questions,
        "photo_preview": [],
        "profile": profile,
    }


def build_persona_profile(**overrides):
    profile = {
        "self_relationship_goal": "认真恋爱",
        "target_gender": "女",
        "target_age_min": 27,
        "target_age_max": 32,
        "target_cities": "苏州,无锡",
        "target_marital_statuses": "未婚,离异无孩",
        "target_accept_partner_children": "不接受",
        "target_accept_partner_children_strength": "hard",
        "target_accept_long_distance": "不接受",
        "target_marriage_timeline": "一年内",
        "must_have_tags": "情绪稳定,愿意沟通",
        "must_not_have_tags": "抽烟",
        "preferred_traits": "有生活感,沟通顺畅",
    }
    profile.update(overrides)
    return profile


def build_synced_requester_profile(**overrides):
    profile = {
        "id": 90001,
        "gender": "男",
        "age": 28,
        "city": "无锡",
        "height": 178,
        "education": "本科",
        "marital_status": "未婚",
        "has_children": 0,
        "relationship_goal": "认真恋爱",
        "preferred_age_min": 27,
        "preferred_age_max": 32,
        "preferred_cities": "苏州,无锡",
        "accept_marital_status": "未婚,离异无孩",
        "accept_marital_status_strength": "hard",
        "accept_partner_children": "不接受",
        "accept_partner_children_strength": "hard",
        "accept_long_distance": "不接受",
        "matcher_preferences": {
            "target_gender": "女",
            "target_cities": ["苏州", "无锡"],
            "must_have_tags": ["情绪稳定", "愿意沟通"],
            "preferred_traits": ["有生活感", "沟通顺畅"],
        },
        "matcher_risks": {
            "must_not_have_tags": ["抽烟"],
        },
    }
    profile.update(overrides)
    return profile


class RecommendationSystemTests(unittest.TestCase):
    def setUp(self):
        self._old_relation_ledger_db = os.environ.get("HER_RELATION_LEDGER_DB")
        self._old_relation_ledger_read_mode = os.environ.get("HER_RELATION_LEDGER_READ_MODE")
        os.environ.pop("HER_RELATION_LEDGER_DB", None)
        os.environ.pop("HER_RELATION_LEDGER_READ_MODE", None)
        self.conn = connect_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        initialize_database(self.conn)
        reset_all_tables(self.conn)

    def tearDown(self):
        self.conn.close()
        if self._old_relation_ledger_db is None:
            os.environ.pop("HER_RELATION_LEDGER_DB", None)
        else:
            os.environ["HER_RELATION_LEDGER_DB"] = self._old_relation_ledger_db
        if self._old_relation_ledger_read_mode is None:
            os.environ.pop("HER_RELATION_LEDGER_READ_MODE", None)
        else:
            os.environ["HER_RELATION_LEDGER_READ_MODE"] = self._old_relation_ledger_read_mode

    def create_active_subscription(self, **overrides):
        base = {
            "requester_id": 70001,
            "title": "无锡认真恋爱",
            "source": "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            "criteria": {
                "gender": "女",
                "cities": ["无锡"],
                "relationship_goals": ["认真恋爱", "结婚导向"],
            },
            "self_profile": {"age": 28, "city": "无锡", "height": 178},
            "limit_count": 10,
            "top_k": 5,
            "min_notify_score": 40,
            "daily_notification_cap": 2,
            "quiet_hours_start": 23,
            "quiet_hours_end": 23,
            "refresh_interval_hours": 24,
            "skip_cooldown_days": 30,
            "recommendation_mode": "direct_greet_only",
            "max_review_candidates_per_refresh": 3,
            "min_direct_greet_score": 60,
            "now": datetime(2026, 4, 30, 9, 0, 0),
        }
        base.update(overrides)
        return create_subscription(self.conn, **base)


    def test_refresh_due_subscriptions_queues_new_candidates_and_calls_partner_search(self):
        subscription = self.create_active_subscription()
        called = {}

        def fake_search_runner(**kwargs):
            called.update(kwargs)
            return {
                "results": [
                    build_result(101, "新对象A", 62),
                    build_result(102, "分数偏低", 33),
                ]
            }

        batch = refresh_due_subscriptions(
            self.conn,
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=fake_search_runner,
        )
        summaries = batch["summaries"]

        self.assertEqual(len(summaries), 1)
        self.assertEqual(batch["errors"], [])
        self.assertEqual(called["criteria"]["cities"], ["无锡"])
        self.assertEqual(called["self_profile"]["city"], "无锡")
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(len(recommendations), 2)
        self.assertEqual(recommendations[0]["delivery_status"], "review_pending")
        self.assertEqual(recommendations[1]["delivery_status"], "suppressed")
        self.assertEqual(recommendations[0]["final_review_status"], "direct_greet_ready")
        self.assertEqual(recommendations[0]["user_review_status"], "pending_review")
        self.assertEqual(recommendations[0]["canonical_relation_status"], "recommended")
        self.assertIn("->", recommendations[0]["relation_key"])
        self.assertEqual(recommendations[0]["target_profile_ref"]["profile_id"], 101)

    def test_refresh_subscription_compiles_effective_criteria_from_persona_and_records_run_snapshot(self):
        subscription = self.create_active_subscription(
            self_id=90001,
            self_profile={"age": 28, "city": "无锡", "height": 178},
            criteria={
                "gender": "男",
                "cities": ["无锡"],
                "age_min": 24,
                "age_max": 28,
                "verified_level_min": "photo",
                "photo_count_min": 3,
            },
        )
        called = {}

        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            persona_resolver=lambda _: build_persona_profile(),
            search_runner=lambda **kwargs: called.update(kwargs) or {"results": [build_result(811, "画像候选", 66)]},
        )

        self.assertEqual(called["self_id"], 90001)
        self.assertEqual(called["criteria"]["gender"], "女")
        self.assertEqual(called["criteria"]["cities"], ["苏州", "无锡"])
        self.assertEqual(called["criteria"]["age_min"], 27)
        self.assertEqual(called["criteria"]["age_max"], 32)
        self.assertEqual(called["criteria"]["relationship_goals"], ["认真恋爱", "结婚导向"])
        self.assertEqual(called["criteria"]["must_have"], ["情绪稳定", "愿意沟通"])
        self.assertEqual(called["criteria"]["must_not_have"], ["抽烟"])
        self.assertEqual(called["criteria"]["prefer"], ["有生活感", "沟通顺畅"])
        self.assertEqual(called["criteria"]["marital_statuses"], ["未婚", "离异无孩"])
        self.assertEqual(called["criteria"]["accept_partner_children"], "不接受")
        self.assertEqual(called["criteria"]["long_distance"], "不接受")
        self.assertEqual(called["criteria"]["marriage_timelines"], ["一年内"])
        self.assertEqual(called["criteria"]["verified_level_min"], "photo")
        self.assertEqual(called["criteria"]["photo_count_min"], 3)

        runs = list_search_runs_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["top_candidate_ids"], [811])
        self.assertEqual(runs[0]["effective_criteria"]["cities"], ["苏州", "无锡"])
        self.assertEqual(runs[0]["persona_profile"]["target_age_min"], 27)
        self.assertEqual(runs[0]["search_request"]["self_id"], 90001)
        self.assertEqual(runs[0]["recommendation_status_counts"], runs[0]["status_counts"])
        self.assertEqual(runs[0]["review_status_counts"], runs[0]["review_counts"])
        prov = runs[0]["rule_provenance"]
        self.assertEqual(prov.get("schema"), RULE_PROVENANCE_SCHEMA)
        self.assertIn("partner_search.scoring", prov.get("rule_sets", {}))
        self.assertIn("fingerprints", prov)
        self.assertEqual(prov["fingerprints"]["subscription_id"], subscription["subscription_id"])
        self.assertIn("effective_params", prov)
        self.assertIn("recommendation.direct_greet_gate", prov["effective_params"])
        recs = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["rule_provenance"].get("schema"), RULE_PROVENANCE_SCHEMA)
        self.assertIn("effective_params", recs[0]["rule_provenance"])
        self.assertEqual(recs[0]["recommendation_status"], recs[0]["delivery_status"])
        self.assertEqual(recs[0]["recommendation_phase"], "review_queue")
        self.assertIsNone(recs[0]["case_progress_status"])
        self.assertEqual(recs[0]["recommendation_status_owner"], "recommendation")
        self.assertIsNone(recs[0]["case_progress_owner"])

        conversion_views = list_recommendation_conversion_views_for_subscription(
            self.conn,
            subscription["subscription_id"],
        )
        self.assertEqual(len(conversion_views), 1)
        self.assertEqual(conversion_views[0]["recommendation_status"], "review_pending")
        self.assertEqual(conversion_views[0]["conversion_stage"], "review_queue")
        self.assertEqual(conversion_views[0]["conversion_stage_owner"], "recommendation")
        self.assertEqual(conversion_views[0]["action_count"], 1)
        self.assertEqual(conversion_views[0]["action_types"], ["relation_state_revision"])
        self.assertEqual(conversion_views[0]["case_count"], 0)
        self.assertEqual(conversion_views[0]["timeline"][0]["source"], "recommendation_action")
        self.assertEqual(conversion_views[0]["timeline"][0]["event_type"], "relation_state_revision")

    def test_refresh_subscription_rehydrates_synced_profile_row_into_persona_criteria(self):
        subscription = self.create_active_subscription(
            self_id=90001,
            self_profile={"age": 28, "city": "无锡", "height": 178},
            criteria={
                "gender": "男",
                "cities": ["无锡"],
                "age_min": 24,
                "age_max": 28,
                "marriage_timelines": ["一年内"],
                "verified_level_min": "photo",
                "photo_count_min": 3,
            },
        )
        called = {}

        with patch(
            "recommendation_system.service.load_self_profile",
            return_value=build_synced_requester_profile(),
        ):
            refresh_subscription(
                self.conn,
                subscription["subscription_id"],
                now=datetime(2026, 4, 30, 9, 0, 0),
                search_runner=lambda **kwargs: called.update(kwargs) or {"results": [build_result(812, "同步画像候选", 67)]},
            )

        self.assertEqual(called["criteria"]["gender"], "女")
        self.assertEqual(called["criteria"]["cities"], ["苏州", "无锡"])
        self.assertEqual(called["criteria"]["age_min"], 27)
        self.assertEqual(called["criteria"]["age_max"], 32)
        self.assertEqual(called["criteria"]["relationship_goals"], ["认真恋爱", "结婚导向"])
        self.assertEqual(called["criteria"]["must_have"], ["情绪稳定", "愿意沟通"])
        self.assertEqual(called["criteria"]["must_not_have"], ["抽烟"])
        self.assertEqual(called["criteria"]["prefer"], ["有生活感", "沟通顺畅"])
        self.assertEqual(called["criteria"]["marital_statuses"], ["未婚", "离异无孩"])
        self.assertEqual(called["criteria"]["accept_partner_children"], "不接受")
        self.assertEqual(called["criteria"]["long_distance"], "不接受")
        self.assertEqual(called["criteria"]["marriage_timelines"], ["一年内"])
        self.assertEqual(called["criteria"]["verified_level_min"], "photo")
        self.assertEqual(called["criteria"]["photo_count_min"], 3)
        self.assertEqual(called["self_profile"]["target_age_min"], 27)
        self.assertEqual(called["self_profile"]["must_have_tags"], ["情绪稳定", "愿意沟通"])

        runs = list_search_runs_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["top_candidate_ids"], [812])
        self.assertEqual(runs[0]["persona_profile"]["target_gender"], "女")
        self.assertEqual(runs[0]["persona_profile"]["target_cities"], ["苏州", "无锡"])
        self.assertEqual(runs[0]["effective_criteria"]["marriage_timelines"], ["一年内"])

    def test_load_requester_profile_returns_json_safe_persona_profile(self):
        with patch(
            "recommendation_system.service.load_self_profile",
            return_value={
                "id": 90001,
                "gender": "男",
                "city": "无锡",
                "last_active_at": datetime(2026, 4, 30, 8, 0, 0),
                "matcher_preferences": {"target_gender": "女", "target_cities": ["苏州", "无锡"]},
                "matcher_risks": {"must_not_have_tags": ["抽烟"]},
            },
        ):
            profile = load_requester_profile(
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                self_id=90001,
                table_name="profiles",
                self_profile=None,
            )

        self.assertEqual(profile["target_gender"], "女")
        self.assertEqual(profile["target_cities"], ["苏州", "无锡"])
        self.assertEqual(profile["must_not_have_tags"], ["抽烟"])
        self.assertEqual(profile["last_active_at"], "2026-04-30 08:00:00")

    def test_refresh_subscription_prefers_latest_synced_profile_over_stale_stored_self_profile(self):
        subscription = self.create_active_subscription(
            self_id=90001,
            self_profile={
                "age": 28,
                "city": "无锡",
                "height": 178,
                "target_marital_statuses": ["未婚", "离异无孩"],
                "target_age_min": 24,
                "target_age_max": 36,
            },
            criteria={
                "gender": "男",
                "cities": ["无锡"],
                "age_min": 24,
                "age_max": 28,
            },
        )
        called = {}

        with patch(
            "recommendation_system.service.load_self_profile",
            return_value=build_synced_requester_profile(
                preferred_age_min=31,
                preferred_age_max=37,
                accept_marital_status="未婚",
                matcher_preferences={
                    "target_gender": "女",
                    "target_cities": ["苏州", "无锡"],
                    "target_marital_statuses": ["未婚"],
                    "must_have_tags": ["情绪稳定", "愿意沟通"],
                    "preferred_traits": ["有生活感", "沟通顺畅"],
                },
            ),
        ):
            refresh_subscription(
                self.conn,
                subscription["subscription_id"],
                now=datetime(2026, 4, 30, 9, 0, 0),
                search_runner=lambda **kwargs: called.update(kwargs) or {"results": [build_result(813, "最新画像候选", 67)]},
            )

        self.assertEqual(called["criteria"]["age_min"], 31)
        self.assertEqual(called["criteria"]["age_max"], 37)
        self.assertEqual(called["criteria"]["marital_statuses"], ["未婚"])

    def test_subscription_overrides_win_over_persona_compiled_criteria(self):
        subscription = self.create_active_subscription(
            self_id=90001,
            criteria={"gender": "男", "cities": ["无锡"], "verified_level_min": "photo"},
        )
        update_subscription_overrides(
            self.conn,
            subscription["subscription_id"],
            {"cities": ["上海"], "verified_level_min": "id"},
            now=datetime(2026, 4, 30, 8, 30, 0),
        )
        called = {}

        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            persona_resolver=lambda _: build_persona_profile(target_cities="苏州", target_gender="女"),
            search_runner=lambda **kwargs: called.update(kwargs) or {"results": []},
        )

        self.assertEqual(called["criteria"]["gender"], "女")
        self.assertEqual(called["criteria"]["cities"], ["上海"])
        self.assertEqual(called["criteria"]["verified_level_min"], "id")
        self.assertNotIn("review_policy", called["criteria"])

    def test_review_policy_overrides_drive_gate_without_leaking_into_search_criteria(self):
        subscription = self.create_active_subscription(
            self_id=90001,
            criteria={"gender": "男", "cities": ["无锡"], "verified_level_min": "photo"},
        )
        update_subscription_overrides(
            self.conn,
            subscription["subscription_id"],
            {
                "cities": ["上海"],
                "review_policy": {
                    "min_direct_greet_score": 80,
                    "max_review_candidates_per_refresh": 1,
                    "auto_reject_on_follow_up_questions": False,
                },
            },
            now=datetime(2026, 4, 30, 8, 30, 0),
        )
        called = {}

        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            persona_resolver=lambda _: build_persona_profile(target_cities="苏州", target_gender="女"),
            search_runner=lambda **kwargs: called.update(kwargs) or {"results": [build_result(214, "策略覆盖候选", 66)]},
        )

        self.assertEqual(called["criteria"]["cities"], ["上海"])
        self.assertNotIn("review_policy", called["criteria"])
        recommendation = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]
        self.assertEqual(recommendation["final_review_status"], "save_only")
        self.assertEqual(recommendation["system_review_decision"], "save_only")
        self.assertEqual(recommendation["review_policy"]["min_direct_greet_score"], 80)
        self.assertEqual(recommendation["review_policy"]["max_review_candidates_per_refresh"], 1)
        self.assertFalse(recommendation["review_policy"]["auto_reject_on_follow_up_questions"])
        self.assertEqual(recommendation["review_policy"]["policy_source"], "subscription_overrides.review_policy")
        self.assertEqual(recommendation["review_decision_stage"], "system_decided")
        self.assertFalse(recommendation["requires_user_review"])

        conversion_view = list_recommendation_conversion_views_for_subscription(
            self.conn,
            subscription["subscription_id"],
        )[0]
        self.assertEqual(conversion_view["system_review_decision"], "save_only")
        self.assertEqual(conversion_view["review_policy"]["min_direct_greet_score"], 80)
        self.assertEqual(conversion_view["review_decision_stage"], "system_decided")

    def test_deliver_pending_recommendations_creates_in_app_card(self):
        subscription = self.create_active_subscription()
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(201, "提醒对象", 61)]},
        )
        record_user_review(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=201,
            review_type="direct_greet",
            now=datetime(2026, 4, 30, 9, 30, 0),
            review_payload={"reason": "真实用户愿意主动打招呼"},
        )

        summary = deliver_in_app_recommendations(
            self.conn,
            now=datetime(2026, 4, 30, 10, 0, 0),
        )

        self.assertEqual(summary["delivered_count"], 1)
        cards = list_in_app_cards(self.conn, requester_id=70001)
        self.assertEqual(len(cards), 1)
        self.assertIn("发现新的合适对象", cards[0]["title"])
        self.assertIn("照片认证", cards[0]["subtitle"])
        self.assertIn("可信度：", cards[0]["body"])
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(recommendations[0]["delivery_status"], "delivered")
        self.assertEqual(recommendations[0]["final_review_status"], "direct_greet_ready")
        self.assertEqual(recommendations[0]["user_review_status"], "direct_greet")
        self.assertEqual(recommendations[0]["system_review_decision"], "direct_greet_ready")
        self.assertEqual(recommendations[0]["user_review_decision"], "direct_greet")
        self.assertEqual(recommendations[0]["review_decision_stage"], "user_decided")
        self.assertTrue(recommendations[0]["requires_user_review"])
        self.assertIsNotNone(recommendations[0]["latest_card_id"])

    def test_direct_greet_only_mode_keeps_save_level_candidate_out_of_notifications(self):
        subscription = self.create_active_subscription()
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {
                "results": [
                    build_result(
                        211,
                        "先收藏对象",
                        68,
                        follow_up_questions=["确认见面频率和关系推进节奏。"],
                    )
                ]
            },
        )

        summary = deliver_in_app_recommendations(
            self.conn,
            now=datetime(2026, 4, 30, 10, 0, 0),
        )

        self.assertEqual(summary["delivered_count"], 0)
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(recommendations[0]["delivery_status"], "review_pending")
        self.assertEqual(recommendations[0]["final_review_status"], "save_only")
        self.assertEqual(list_in_app_cards(self.conn, requester_id=70001), [])

    def test_user_review_save_blocks_candidate_even_after_rule_gate_passes(self):
        subscription = self.create_active_subscription()
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(213, "真实用户只会收藏", 66)]},
        )
        review = record_user_review(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=213,
            review_type="save",
            now=datetime(2026, 4, 30, 9, 20, 0),
            review_payload={"reason": "满意，但还不到主动打招呼"},
        )
        self.assertEqual(review["delivery_status"], "saved_by_user")
        self.assertEqual(review["user_review_status"], "save")

        summary = deliver_in_app_recommendations(
            self.conn,
            now=datetime(2026, 4, 30, 10, 0, 0),
        )

        self.assertEqual(summary["delivered_count"], 0)
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(recommendations[0]["final_review_status"], "direct_greet_ready")
        self.assertEqual(recommendations[0]["user_review_status"], "save")
        self.assertEqual(recommendations[0]["delivery_status"], "saved_by_user")

    def test_match_based_mode_can_still_push_candidate_that_is_not_direct_greet_ready(self):
        subscription = self.create_active_subscription(recommendation_mode="match_based")
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {
                "results": [
                    build_result(
                        212,
                        "传统匹配候选",
                        68,
                        follow_up_questions=["确认见面频率和关系推进节奏。"],
                    )
                ]
            },
        )

        summary = deliver_in_app_recommendations(
            self.conn,
            now=datetime(2026, 4, 30, 10, 0, 0),
        )

        self.assertEqual(summary["delivered_count"], 1)
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(recommendations[0]["final_review_status"], "match_ready")
        self.assertEqual(recommendations[0]["delivery_status"], "delivered")

    def test_deliver_in_app_recommendations_reuses_preloaded_rows_for_relation_revision(self):
        subscription = self.create_active_subscription()
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(214, "复用行对象", 69)]},
        )
        record_user_review(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=214,
            review_type="direct_greet",
            now=datetime(2026, 4, 30, 9, 30, 0),
        )

        executed_sql = []
        original_execute = type(self.conn).execute

        def counted_execute(conn, sql, parameters=None):
            executed_sql.append(str(sql))
            return original_execute(conn, sql, parameters)

        with patch.object(
            type(self.conn),
            "execute",
            autospec=True,
            side_effect=counted_execute,
        ):
            summary = deliver_in_app_recommendations(
                self.conn,
                now=datetime(2026, 4, 30, 10, 0, 0),
            )

        self.assertEqual(summary["delivered_count"], 1)
        self.assertFalse(
            any("SELECT * FROM profile_recommendations WHERE recommendation_id = ?" in sql for sql in executed_sql)
        )

    def test_skip_action_applies_cooldown_and_blocks_redelivery_until_expiry(self):
        subscription = self.create_active_subscription(daily_notification_cap=5)
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(301, "冷却对象", 62)]},
        )
        record_user_review(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=301,
            review_type="direct_greet",
            now=datetime(2026, 4, 30, 9, 30, 0),
        )
        deliver_in_app_recommendations(self.conn, now=datetime(2026, 4, 30, 10, 0, 0))
        record_recommendation_action(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=301,
            action_type="skip",
            now=datetime(2026, 4, 30, 11, 0, 0),
        )

        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 5, 1, 12, 0, 0),
            search_runner=lambda **_: {"results": [build_result(301, "冷却对象", 62)]},
        )
        recommendation = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]
        self.assertEqual(recommendation["delivery_status"], "cooled_down")
        self.assertEqual(
            deliver_in_app_recommendations(self.conn, now=datetime(2026, 5, 1, 12, 5, 0))["delivered_count"],
            0,
        )

        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 6, 1, 12, 0, 0),
            search_runner=lambda **_: {"results": [build_result(301, "冷却对象", 65)]},
        )
        recommendation = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]
        self.assertEqual(recommendation["delivery_status"], "pending_delivery")

    def test_save_action_persists_without_cooling_when_candidate_reappears(self):
        subscription = self.create_active_subscription(daily_notification_cap=5)
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(311, "收藏对象", 63)]},
        )
        record_user_review(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=311,
            review_type="direct_greet",
            now=datetime(2026, 4, 30, 9, 30, 0),
        )
        deliver_in_app_recommendations(self.conn, now=datetime(2026, 4, 30, 10, 0, 0))
        record_recommendation_action(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=311,
            action_type="save",
            now=datetime(2026, 4, 30, 11, 0, 0),
        )

        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 5, 1, 12, 0, 0),
            search_runner=lambda **_: {"results": [build_result(311, "收藏对象", 66)]},
        )

        recommendation = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])[0]
        self.assertEqual(recommendation["delivery_status"], "saved_by_user")
        self.assertEqual(recommendation["last_action_type"], "save")
        self.assertIsNone(recommendation["cooling_until"])
        self.assertEqual(
            deliver_in_app_recommendations(self.conn, now=datetime(2026, 5, 1, 12, 5, 0))["delivered_count"],
            0,
        )

    def test_recommendation_actions_forward_to_appearance_feedback_loop(self):
        subscription = self.create_active_subscription(daily_notification_cap=5)
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(318, "反馈对象", 68)]},
        )
        record_user_review(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=318,
            review_type="direct_greet",
            now=datetime(2026, 4, 30, 9, 30, 0),
        )
        deliver_in_app_recommendations(self.conn, now=datetime(2026, 4, 30, 10, 0, 0))

        with patch(
            "recommendation_system.recommendation_rows._record_appearance_feedback_from_recommendation"
        ) as feedback_mock:
            record_recommendation_action(
                self.conn,
                subscription_id=subscription["subscription_id"],
                candidate_id=318,
                action_type="skip",
                now=datetime(2026, 4, 30, 11, 0, 0),
            )

        feedback_mock.assert_called_once()
        self.assertEqual(feedback_mock.call_args.kwargs["event_type"], "skip")
        self.assertEqual(feedback_mock.call_args.kwargs["scene"], "recommendation_action")

    def test_daily_notification_cap_defers_extra_cards(self):
        subscription = self.create_active_subscription(daily_notification_cap=1)
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {
                "results": [
                    build_result(401, "第一位", 66),
                    build_result(402, "第二位", 64),
                ]
            },
        )
        record_user_review(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=401,
            review_type="direct_greet",
            now=datetime(2026, 4, 30, 9, 30, 0),
        )
        record_user_review(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=402,
            review_type="direct_greet",
            now=datetime(2026, 4, 30, 9, 31, 0),
        )

        summary = deliver_in_app_recommendations(self.conn, now=datetime(2026, 4, 30, 10, 0, 0))

        self.assertEqual(summary["delivered_count"], 1)
        self.assertEqual(summary["held_daily_cap"], 1)
        cards = list_in_app_cards(self.conn, requester_id=70001)
        self.assertEqual(len(cards), 1)
        recommendations = list_recommendations_for_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(
            [item["delivery_status"] for item in recommendations],
            ["delivered", "pending_delivery"],
        )

    def test_quiet_hours_hold_delivery(self):
        subscription = self.create_active_subscription(
            quiet_hours_start=0,
            quiet_hours_end=23,
        )
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(501, "静默时段对象", 60)]},
        )
        record_user_review(
            self.conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=501,
            review_type="direct_greet",
            now=datetime(2026, 4, 30, 9, 30, 0),
        )

        summary = deliver_in_app_recommendations(self.conn, now=datetime(2026, 4, 30, 10, 0, 0))

        self.assertEqual(summary["delivered_count"], 0)
        self.assertEqual(summary["held_quiet_hours"], 1)
        self.assertEqual(list_in_app_cards(self.conn, requester_id=70001), [])

    def test_get_subscription_and_refresh_interval_keep_not_due_subscription_idle(self):
        subscription = self.create_active_subscription(refresh_interval_hours=48)
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **_: {"results": [build_result(601, "首次对象", 60)]},
        )

        due = refresh_due_subscriptions(
            self.conn,
            now=datetime(2026, 5, 1, 8, 0, 0),
            search_runner=lambda **_: {"results": [build_result(602, "不该触发", 99)]},
        )

        self.assertEqual(due["summaries"], [])
        self.assertEqual(due["errors"], [])
        loaded = get_subscription(self.conn, subscription["subscription_id"])
        self.assertEqual(loaded["last_result_count"], 1)

    def test_run_search_session_requests_opt_in_prompt_when_no_match(self):
        called = {}

        def fake_search_runner(**kwargs):
            called.update(kwargs)
            return {
                "has_match": False,
                "result_count": 0,
                "results": [],
                "fallback_results": [],
            }

        session = run_search_session(
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女", "cities": ["无锡"]},
            self_profile={"age": 28, "city": "无锡"},
            limit=8,
            search_runner=fake_search_runner,
        )

        self.assertEqual(called["criteria"]["cities"], ["无锡"])
        self.assertEqual(called["limit"], 8)
        self.assertTrue(session["needs_opt_in_prompt"])
        self.assertEqual(session["opt_in_prompt"], DEFAULT_NO_MATCH_OPT_IN_PROMPT)

    def test_run_search_session_skips_opt_in_prompt_when_match_exists(self):
        session = run_search_session(
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女", "cities": ["无锡"]},
            search_runner=lambda **_: {
                "has_match": True,
                "result_count": 1,
                "results": [build_result(701, "已有结果", 61)],
            },
        )

        self.assertFalse(session["needs_opt_in_prompt"])
        self.assertIsNone(session["opt_in_prompt"])
        self.assertEqual(session["result_count"], 1)

    def test_handle_opt_in_decision_creates_subscription_from_original_search_request(self):
        session = run_search_session(
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女", "cities": ["无锡"], "relationship_goals": ["认真恋爱"]},
            self_id=90001,
            table_name="profiles",
            photos_table_name="profile_photos",
            limit=6,
            search_runner=lambda **_: {
                "has_match": False,
                "result_count": 0,
                "results": [],
                "fallback_results": [],
            },
        )

        decision = handle_opt_in_decision(
            self.conn,
            requester_id=70001,
            search_session=session,
            user_opted_in=True,
            title="空结果后继续留意",
        )

        self.assertTrue(decision["created_subscription"])
        subscription = decision["subscription"]
        self.assertEqual(subscription["requester_id"], 70001)
        self.assertEqual(subscription["title"], "空结果后继续留意")
        self.assertEqual(subscription["self_id"], 90001)
        self.assertEqual(subscription["table_name"], "profiles")
        self.assertEqual(subscription["photos_table_name"], "profile_photos")
        self.assertEqual(subscription["limit_count"], 6)

        called = {}
        refresh_subscription(
            self.conn,
            subscription["subscription_id"],
            now=datetime(2026, 4, 30, 9, 0, 0),
            search_runner=lambda **kwargs: called.update(kwargs) or {"results": []},
        )
        self.assertEqual(called["self_id"], 90001)
        self.assertEqual(called["criteria"]["relationship_goals"], ["认真恋爱"])
        self.assertEqual(called["limit"], 6)
        self.assertEqual(subscription["recommendation_mode"], "direct_greet_only")

    def test_handle_opt_in_decision_rejection_creates_no_subscription(self):
        session = run_search_session(
            source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            criteria={"gender": "女"},
            search_runner=lambda **_: {
                "has_match": False,
                "result_count": 0,
                "results": [],
                "fallback_results": [],
            },
        )

        decision = handle_opt_in_decision(
            self.conn,
            requester_id=70001,
            search_session=session,
            user_opted_in=False,
        )

        saved_count = self.conn.execute("SELECT COUNT(*) AS c FROM saved_search_subscriptions").fetchone()["c"]
        self.assertFalse(decision["created_subscription"])
        self.assertIsNone(decision["subscription"])
        self.assertEqual(saved_count, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
