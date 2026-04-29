import pathlib
import sys
import types
import unittest
from unittest import mock


SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "search_candidates.py"
)
search_candidates = types.ModuleType("search_candidates")
search_candidates.__file__ = str(SCRIPT_PATH)
exec(compile(SCRIPT_PATH.read_text(encoding="utf-8"), str(SCRIPT_PATH), "exec"), search_candidates.__dict__)


class FakeCursor:
    def __init__(self, table_rows, column_rows):
        self.table_rows = table_rows
        self.column_rows = column_rows
        self.results = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):
        if "FROM information_schema.tables" in query:
            self.results = [{"table_name": table_name} for table_name in self.table_rows]
            return
        if "FROM information_schema.columns" in query:
            table_name = params[1]
            self.results = [
                {"column_name": column_name}
                for column_name in self.column_rows.get(table_name, [])
            ]
            return
        raise AssertionError(f"Unexpected query: {query}")

    def fetchall(self):
        return self.results


class FakeConn:
    def __init__(self, table_rows, column_rows):
        self.table_rows = table_rows
        self.column_rows = column_rows

    def cursor(self):
        return FakeCursor(self.table_rows, self.column_rows)


class SearchCandidatesTests(unittest.TestCase):
    def test_split_keywords_and_merge(self):
        self.assertEqual(
            search_candidates.split_keywords("无锡，滨湖区/情绪稳定"),
            ["无锡", "滨湖区", "情绪稳定"],
        )
        self.assertEqual(
            search_candidates.merge_keyword_args(["无锡,上海", "苏州"]),
            ["无锡", "上海", "苏州"],
        )

    def test_parse_mysql_source_with_query(self):
        parsed = search_candidates.parse_mysql_source(
            "mysql://user:pass@127.0.0.1:3307/her?table=profiles&photos_table=photos"
        )
        self.assertEqual(parsed["host"], "127.0.0.1")
        self.assertEqual(parsed["port"], 3307)
        self.assertEqual(parsed["database"], "her")
        self.assertEqual(parsed["table"], "profiles")
        self.assertEqual(parsed["photos_table"], "photos")

    def test_parse_mysql_source_invalid(self):
        with self.assertRaises(ValueError):
            search_candidates.parse_mysql_source("file:///tmp/profiles.csv")

    def test_build_mysql_prefilter_with_include_ids(self):
        criteria = {
            "gender": "女",
            "age_min": 24,
            "age_max": 30,
            "cities": ["无锡"],
            "profile_statuses": ["active"],
            "verified_level_min": "photo",
        }
        canonical_to_actual = {
            "id": "id",
            "gender": "gender",
            "age": "age",
            "city": "city",
            "profile_status": "profile_status",
            "verified_level": "verified_level",
        }
        where_clause, params = search_candidates.build_mysql_prefilter(
            criteria, canonical_to_actual, include_ids=[90001]
        )
        self.assertIn("WHERE", where_clause)
        self.assertIn("`id` IN", where_clause)
        self.assertIn("photo", params)
        self.assertIn(90001, params)
        self.assertNotIn("LOWER(", where_clause)
        self.assertNotIn("TRIM(", where_clause)

    def test_detect_mysql_profile_table_raises_on_ambiguous_best_match(self):
        conn = FakeConn(
            table_rows=["profiles", "profiles_backup"],
            column_rows={
                "profiles": [
                    "id",
                    "name",
                    "gender",
                    "age",
                    "city",
                    "profile_status",
                    "verified_level",
                ],
                "profiles_backup": [
                    "id",
                    "name",
                    "gender",
                    "age",
                    "city",
                    "profile_status",
                    "verified_level",
                ],
            },
        )

        with self.assertRaises(ValueError) as cm:
            search_candidates.detect_mysql_profile_table(conn, "her")

        self.assertIn("Ambiguous MySQL candidate tables", str(cm.exception))
        self.assertIn("profiles", str(cm.exception))
        self.assertIn("profiles_backup", str(cm.exception))

    def test_build_criteria_from_args(self):
        parser = search_candidates.argparse.ArgumentParser()
        parser.add_argument("--gender")
        parser.add_argument("--age-min", type=int)
        parser.add_argument("--age-max", type=int)
        parser.add_argument("--height-min", type=int)
        parser.add_argument("--height-max", type=int)
        parser.add_argument("--city", action="append")
        parser.add_argument("--district", action="append")
        parser.add_argument("--settlement-city", action="append")
        parser.add_argument("--relationship-goal", action="append")
        parser.add_argument("--must-have", action="append")
        parser.add_argument("--must-not-have", action="append")
        parser.add_argument("--prefer", action="append")
        parser.add_argument("--require-known", action="append")
        parser.add_argument("--smoking")
        parser.add_argument("--drinking")
        parser.add_argument("--long-distance")
        parser.add_argument("--housing-status", action="append")
        parser.add_argument("--car-status", action="append")
        parser.add_argument("--marital-status", action="append")
        parser.add_argument("--has-children", type=int)
        parser.add_argument("--want-children")
        parser.add_argument("--accept-partner-children")
        parser.add_argument("--marriage-timeline", action="append")
        parser.add_argument("--profile-status", action="append")
        parser.add_argument("--active-within-days", type=int)
        parser.add_argument("--verified-level-min")
        parser.add_argument("--verified-level", action="append")
        parser.add_argument("--photo-count-min", type=int)
        parser.add_argument("--exclude-id", action="append", type=int)
        args = parser.parse_args(
            [
                "--gender",
                "女",
                "--age-min",
                "24",
                "--city",
                "无锡,苏州",
                "--must-have",
                "情绪稳定",
                "--require-known",
                "smoking,想要孩子",
                "--profile-status",
                "active,paused",
                "--exclude-id",
                "90001",
            ]
        )
        criteria = search_candidates.build_criteria_from_args(args)
        self.assertEqual(criteria["gender"], "女")
        self.assertEqual(criteria["age_min"], 24)
        self.assertEqual(criteria["cities"], ["无锡", "苏州"])
        self.assertEqual(criteria["must_have"], ["情绪稳定"])
        self.assertEqual(criteria["required_known_fields"], ["smoking", "want_children"])
        self.assertEqual(criteria["profile_statuses"], ["active", "paused"])
        self.assertEqual(criteria["exclude_ids"], {90001})

    def test_evaluate_candidate_positive(self):
        record = {
            "id": 101,
            "name": "A",
            "gender": "女",
            "age": 27,
            "height": 165,
            "city": "无锡",
            "district": "滨湖区",
            "relationship_goal": "认真恋爱",
            "smoking": "否",
            "drinking": "否",
            "marital_status": "未婚",
            "want_children": "想要",
            "accept_partner_children": "接受",
            "housing_status": "已购房",
            "car_status": "有车",
            "profile_status": "active",
            "verified_level": "id",
            "photo_count": 5,
            "personality": "情绪稳定",
            "values": "消费观正常",
            "combined_text": "情绪稳定 消费观正常",
            "last_active_at": "2099-01-01 00:00:00",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "女",
            "age_min": 24,
            "age_max": 30,
            "cities": ["无锡"],
            "must_have": ["情绪稳定"],
            "prefer": ["消费观正常"],
            "profile_statuses": ["active"],
            "verified_level_min": "photo",
            "photo_count_min": 3,
            "exclude_ids": set(),
        }
        result = search_candidates.evaluate_candidate(record, criteria)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 101)
        self.assertGreater(result["score"], 0)
        self.assertEqual(
            result["score"],
            result["fit_score"] + result["confidence_score"] - result["risk_score"],
        )
        self.assertGreater(result["fit_score"], 0)
        self.assertGreater(result["confidence_score"], 0)
        self.assertEqual(result["risk_score"], 0)
        self.assertIn("性别 女", result["matched_on"])
        self.assertIn("消费观正常 <- 价值观: 消费观正常", result["match_evidence"])

    def test_evaluate_candidate_require_known_rejects_missing_field(self):
        record = {
            "id": 104,
            "name": "MissingSmoking",
            "gender": "女",
            "age": 27,
            "city": "无锡",
            "profile_status": "active",
            "verified_level": "photo",
            "combined_text": "认真恋爱",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "女",
            "profile_statuses": ["active"],
            "exclude_ids": set(),
            "required_known_fields": ["smoking"],
        }
        self.assertIsNone(search_candidates.evaluate_candidate(record, criteria))

    def test_evaluate_candidate_generates_follow_up_questions(self):
        record = {
            "id": 105,
            "name": "NeedFollowUp",
            "gender": "女",
            "age": 29,
            "city": "上海",
            "relationship_goal": "认真恋爱",
            "profile_status": "active",
            "verified_level": "photo",
            "notes": "平时作息规律，比较看重相处舒服和沟通顺畅",
            "combined_text": "平时作息规律 比较看重相处舒服和沟通顺畅",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "女",
            "cities": ["上海"],
            "prefer": ["作息规律"],
            "profile_statuses": ["active"],
            "exclude_ids": set(),
            "self_profile": {
                "city": "无锡",
                "drinking": "偶尔",
            },
        }
        result = search_candidates.evaluate_candidate(record, criteria)
        self.assertIsNotNone(result)
        self.assertIn("作息规律 <- 备注: 平时作息规律，比较看重相处舒服和沟通顺畅", result["match_evidence"])
        self.assertIn("确认异地是否能长期接受，以及见面频率怎么安排。", result["follow_up_questions"])
        self.assertIn("确认是否真的接受伴侣偶尔喝酒。", result["follow_up_questions"])

    def test_extract_keyword_evidence_hides_sensitive_segment_details(self):
        record = {
            "notes": "情绪稳定，目前住在滨湖区金融一街88号，就职于无锡某科技公司",
        }
        evidence = search_candidates.extract_keyword_evidence(record, "情绪稳定")
        self.assertEqual(evidence, "备注: 命中关键词，敏感细节已隐藏")

    def test_evaluate_candidate_rejected_by_must_not_have(self):
        record = {
            "id": 102,
            "name": "B",
            "profile_status": "active",
            "verified_level": "photo",
            "combined_text": "抽烟 偶尔喝酒",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "must_not_have": ["抽烟"],
            "profile_statuses": ["active"],
            "exclude_ids": set(),
        }
        self.assertIsNone(search_candidates.evaluate_candidate(record, criteria))

    def test_evaluate_candidate_keeps_missing_profile_status_as_unknown(self):
        record = {
            "id": 103,
            "name": "UnknownStatus",
            "gender": "女",
            "combined_text": "",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "女",
            "profile_statuses": ["active"],
            "exclude_ids": set(),
        }
        result = search_candidates.evaluate_candidate(record, criteria)
        self.assertIsNotNone(result)
        self.assertIn("profile_status", result["missing_fields"])
        self.assertNotIn("状态 active", result["matched_on"])

    def test_reciprocal_rejects_non_matching_city(self):
        candidate = {"preferred_cities": "上海"}
        self_profile = {"city": "无锡"}
        self.assertIsNone(
            search_candidates.evaluate_reciprocal_compatibility(candidate, self_profile)
        )

    def test_reciprocal_negotiable_children_rejects_when_self_has_children(self):
        candidate = {"accept_partner_children": "可协商"}
        self_profile = {"has_children": 1}
        result = search_candidates.evaluate_reciprocal_compatibility(
            candidate, self_profile, diagnostics=True
        )
        self.assertIsNotNone(result)
        self.assertFalse(result["matched"])
        self.assertEqual(
            search_candidates.parse_rejection_reason(result["reject_reason"])[0],
            "reciprocal_children_acceptance_not_strong",
        )

    def test_reciprocal_missing_children_acceptance_called_out(self):
        candidate = {}
        self_profile = {"has_children": 1}
        result = search_candidates.evaluate_reciprocal_compatibility(
            candidate, self_profile
        )
        self.assertIsNotNone(result)
        self.assertIn("accept_partner_children", result["missing_fields"])

    def test_reciprocal_soft_income_preference_becomes_risk(self):
        candidate = {
            "preferred_income_min_wan": 10,
            "preferred_income_max_wan": 30,
            "preferred_income_strictness": "可放宽",
        }
        self_profile = {"income_min_wan": 70, "income_max_wan": 70}
        result = search_candidates.evaluate_reciprocal_compatibility(
            candidate, self_profile
        )
        self.assertIsNotNone(result)
        self.assertIn("对方收入要求可能可放宽", result["risk_flags"])

    def test_reciprocal_children_acceptance_requires_strong_signal_for_parent(self):
        candidate = {
            "accept_partner_children": "接受",
            "accept_partner_children_strength": "谨慎接受",
        }
        self_profile = {"has_children": 1}
        result = search_candidates.evaluate_reciprocal_compatibility(
            candidate, self_profile, diagnostics=True
        )
        self.assertIsNotNone(result)
        self.assertFalse(result["matched"])
        self.assertEqual(
            search_candidates.parse_rejection_reason(result["reject_reason"])[0],
            "reciprocal_children_acceptance_not_strong",
        )

    def test_attach_photo_previews_groups_by_source_and_table(self):
        original_loader = search_candidates.load_mysql_photo_previews
        calls = []

        def fake_loader(source, profile_ids, table_name=None, photos_table_name=None, preview_count=3):
            calls.append((source, tuple(profile_ids), table_name, photos_table_name, preview_count))
            return {pid: [f"https://img/{pid}.jpg"] for pid in profile_ids}

        search_candidates.load_mysql_photo_previews = fake_loader
        try:
            results = [
                {"id": 1, "source_file": "mysql://a/db?table=t1#t1"},
                {"id": 2, "source_file": "mysql://a/db?table=t1#t1"},
                {"id": 3, "source_file": "mysql://b/db?table=t2#t2"},
            ]
            search_candidates.attach_photo_previews(results, preview_count=2)
        finally:
            search_candidates.load_mysql_photo_previews = original_loader

        self.assertEqual(len(calls), 2)
        self.assertEqual(results[0]["photo_preview"], ["https://img/1.jpg"])
        self.assertEqual(results[2]["photo_preview"], ["https://img/3.jpg"])

    def test_format_text_redacts_mysql_passwords_when_source_included(self):
        text = search_candidates.format_text(
            [
                {
                    "id": 1,
                    "name": "Alice",
                    "score": 42,
                    "fit_score": 30,
                    "confidence_score": 18,
                    "risk_score": 6,
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "risk_flags": [],
                    "match_evidence": ["情绪稳定 <- 备注: 情绪稳定，作息规律"],
                    "follow_up_questions": ["确认是否抽烟，以及频率如何。"],
                    "profile": {
                        "age": 28,
                        "city": "无锡",
                        "job": "产品经理",
                        "notes": "微信:abc12345 电话13812345678 邮箱alice@example.com 身份证320311199001011234",
                    },
                    "source_file": "mysql://user:secret@127.0.0.1:3306/her?table=profiles#profiles",
                    "verified_rank": 0,
                    "activity_sort_ts": 0,
                    "profile_status_rank": 0,
                }
            ],
            include_source=True,
        )
        self.assertIn("mysql://user:***@127.0.0.1:3306/her?table=profiles#profiles", text)
        self.assertNotIn("secret", text)
        self.assertIn("scoring: fit=30 | confidence=18 | risk=6", text)
        self.assertIn("match_evidence: 情绪稳定 <- 备注: 情绪稳定，作息规律", text)
        self.assertIn("follow_up_questions: 确认是否抽烟，以及频率如何。", text)
        self.assertIn("notes: 有补充备注，已隐藏敏感细节", text)
        self.assertNotIn("abc12345", text)
        self.assertNotIn("13812345678", text)
        self.assertNotIn("alice@example.com", text)
        self.assertNotIn("320311199001011234", text)

    def test_format_text_omits_source_by_default(self):
        text = search_candidates.format_text(
            [
                {
                    "id": 1,
                    "name": "Alice",
                    "score": 42,
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "risk_flags": [],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "profile": {
                        "age": 28,
                        "city": "无锡",
                        "job": "产品经理",
                    },
                    "source_file": "mysql://user:secret@127.0.0.1:3306/her?table=profiles#profiles",
                    "verified_rank": 0,
                    "activity_sort_ts": 0,
                    "profile_status_rank": 0,
                }
            ]
        )
        self.assertNotIn("mysql://user:***@127.0.0.1:3306/her?table=profiles#profiles", text)
        self.assertNotIn("source:", text)

    def test_format_text_uses_real_activity_field_label(self):
        text = search_candidates.format_text(
            [
                {
                    "id": 1,
                    "name": "Alice",
                    "score": 42,
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "risk_flags": [],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "profile": {
                        "age": 28,
                        "city": "无锡",
                        "job": "产品经理",
                        "created_at": "2026-01-02 03:04:05",
                    },
                    "source_file": "",
                    "verified_rank": 0,
                    "activity_sort_ts": 0,
                    "profile_status_rank": 0,
                }
            ]
        )
        self.assertIn("created_at=2026-01-02 03:04:05", text)
        self.assertNotIn("active_at=", text)

    def test_format_text_shows_vibe_fields_when_present(self):
        text = search_candidates.format_text(
            [
                {
                    "id": 1,
                    "name": "Alice",
                    "score": 42,
                    "fit_score": 24,
                    "confidence_score": 20,
                    "risk_score": 2,
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "risk_flags": [],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "profile": {
                        "age": 28,
                        "city": "无锡",
                        "job": "产品经理",
                        "life_routine": "生活规律",
                        "communication_style": "主动沟通",
                        "dating_pace": "自然推进",
                        "expression_style": "会表达有生活感",
                        "relationship_capacity": "稳定投入关系",
                    },
                    "source_file": "",
                    "verified_rank": 0,
                    "activity_sort_ts": 0,
                    "profile_status_rank": 0,
                }
            ]
        )
        self.assertIn("vibe: 作息=生活规律 | 沟通=主动沟通 | 节奏=自然推进", text)
        self.assertIn("表达=会表达有生活感", text)
        self.assertIn("关系投入=稳定投入关系", text)

    def test_redact_sensitive_text_masks_common_contact_fields(self):
        redacted = search_candidates.redact_sensitive_text(
            "手机号 13998761234, 微信号 test_user88, 邮箱 bob@example.com"
        )
        self.assertIn("139****1234", redacted)
        self.assertIn("微信号 te***88", redacted)
        self.assertIn("b***@example.com", redacted)
        self.assertNotIn("13998761234", redacted)
        self.assertNotIn("test_user88", redacted)

    def test_summarize_notes_keeps_brief_non_sensitive_summary(self):
        summary = search_candidates.summarize_notes("情绪稳定。作息规律。会做饭。")
        self.assertEqual(summary, "情绪稳定；作息规律")

    def test_summarize_notes_hides_sensitive_detail_patterns(self):
        summary = search_candidates.summarize_notes(
            "公司在人民路88号，女儿6岁，就读无锡实验小学，微信未留"
        )
        self.assertEqual(summary, "有补充备注，已隐藏敏感细节")

    def test_main_help_redacts_default_source_password(self):
        original_default = search_candidates.DEFAULT_MYSQL_SOURCE
        search_candidates.DEFAULT_MYSQL_SOURCE = (
            "mysql://user:secret@127.0.0.1:3306/her?table=profiles"
        )
        try:
            with mock.patch("sys.argv", ["search_candidates.py", "--help"]), mock.patch(
                "sys.stdout", new_callable=mock.MagicMock
            ) as mock_stdout:
                with self.assertRaises(SystemExit) as cm:
                    search_candidates.main()
        finally:
            search_candidates.DEFAULT_MYSQL_SOURCE = original_default

        self.assertEqual(cm.exception.code, 0)
        output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        normalized_output = " ".join(output.split())
        self.assertIn("Defaults to PARTNER_SEARCH_MYSQL_SOURCE=", normalized_output)
        self.assertIn("user:***@127.0.0.1:3306/her?table=profiles", normalized_output)
        self.assertNotIn("secret", output)

    def test_main_outputs_ranked_results(self):
        fake_records = [
            {
                "id": 201,
                "name": "C1",
                "gender": "女",
                "age": 27,
                "city": "无锡",
                "profile_status": "active",
                "verified_level": "id",
                "combined_text": "情绪稳定",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
            {
                "id": 202,
                "name": "C2",
                "gender": "女",
                "age": 28,
                "city": "无锡",
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "情绪稳定",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
        ]

        with mock.patch.object(search_candidates, "load_source", return_value=fake_records), mock.patch.object(
            search_candidates, "attach_photo_previews"
        ) as mocked_attach, mock.patch(
            "sys.argv",
            [
                "search_candidates.py",
                "--source",
                "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                "--gender",
                "女",
                "--city",
                "无锡",
                "--must-have",
                "情绪稳定",
                "--limit",
                "2",
            ],
        ), mock.patch("sys.stdout", new_callable=mock.MagicMock) as mock_stdout:
            search_candidates.main()

        output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        self.assertIn("1. C1", output)
        self.assertIn("2. C2", output)
        mocked_attach.assert_called_once()

    def test_main_outputs_no_matches(self):
        with mock.patch.object(search_candidates, "load_source", return_value=[]), mock.patch(
            "sys.argv",
            [
                "search_candidates.py",
                "--source",
                "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                "--gender",
                "女",
            ],
        ), mock.patch("sys.stdout", new_callable=mock.MagicMock) as mock_stdout:
            search_candidates.main()

        output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        self.assertIn("No matches found.", output)
        self.assertIn("pool_summary: scanned=0 | passed=0", output)

    def test_build_no_match_diagnostics_reports_top_reason(self):
        records = [
            {
                "id": 701,
                "name": "CityA",
                "gender": "女",
                "age": 27,
                "city": "无锡",
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "情绪稳定",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
            {
                "id": 702,
                "name": "CityB",
                "gender": "女",
                "age": 28,
                "city": "苏州",
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "情绪稳定",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
        ]
        criteria = {
            "gender": "女",
            "cities": ["上海"],
            "profile_statuses": ["active"],
            "exclude_ids": set(),
        }

        diagnostics = search_candidates.build_no_match_diagnostics(records, criteria)

        self.assertEqual(diagnostics["scanned_count"], 2)
        self.assertEqual(diagnostics["passed_count"], 0)
        self.assertEqual(diagnostics["top_reasons"][0]["reason"], "city_mismatch")
        self.assertEqual(diagnostics["top_reasons"][0]["count"], 2)
        self.assertIn("放宽地域条件", diagnostics["relax_suggestions"][0])

    def test_main_outputs_no_match_diagnostics_when_records_exist(self):
        fake_records = [
            {
                "id": 801,
                "name": "WrongCity",
                "gender": "女",
                "age": 27,
                "city": "无锡",
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "情绪稳定",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            }
        ]

        with mock.patch.object(search_candidates, "load_source", return_value=fake_records), mock.patch(
            "sys.argv",
            [
                "search_candidates.py",
                "--source",
                "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                "--gender",
                "女",
                "--city",
                "上海",
            ],
        ), mock.patch("sys.stdout", new_callable=mock.MagicMock) as mock_stdout:
            search_candidates.main()

        output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        self.assertIn("No matches found.", output)
        self.assertIn("pool_summary: scanned=1 | passed=0", output)
        self.assertIn("why_no_match: 城市不在要求范围 x1", output)
        self.assertIn("relax_suggestions: 放宽地域条件", output)

    def test_main_errors_when_no_source_configured(self):
        original_default = search_candidates.DEFAULT_MYSQL_SOURCE
        search_candidates.DEFAULT_MYSQL_SOURCE = None
        try:
            with mock.patch("sys.argv", ["search_candidates.py", "--gender", "女"]), mock.patch(
                "sys.stderr", new_callable=mock.MagicMock
            ) as mock_stderr:
                with self.assertRaises(SystemExit) as cm:
                    search_candidates.main()
        finally:
            search_candidates.DEFAULT_MYSQL_SOURCE = original_default

        self.assertEqual(cm.exception.code, 1)
        err_output = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        self.assertIn("No profile source configured.", err_output)
        self.assertIn("PARTNER_SEARCH_MYSQL_SOURCE", err_output)

    def test_main_exits_on_error(self):
        with mock.patch.object(search_candidates, "load_source", side_effect=ValueError("boom")), mock.patch(
            "sys.argv",
            [
                "search_candidates.py",
                "--source",
                "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                "--gender",
                "女",
            ],
        ), mock.patch("sys.stderr", new_callable=mock.MagicMock) as mock_stderr:
            with self.assertRaises(SystemExit) as cm:
                search_candidates.main()

        self.assertEqual(cm.exception.code, 1)
        err_output = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
        self.assertIn("ERROR: boom", err_output)

    def test_main_with_self_id_filters_self_and_reciprocal_mismatch(self):
        fake_records = [
            {
                "id": 90001,
                "name": "SELF",
                "gender": "男",
                "age": 28,
                "height": 178,
                "city": "无锡",
                "education": "本科",
                "income_range": "30-40万",
                "marital_status": "未婚",
                "has_children": 0,
                "profile_status": "active",
                "verified_level": "id",
                "combined_text": "本人资料",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
            {
                "id": 301,
                "name": "MatchA",
                "gender": "女",
                "age": 27,
                "city": "无锡",
                "preferred_cities": "无锡",
                "preferred_age_min": 26,
                "preferred_age_max": 32,
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "认真恋爱",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
            {
                "id": 302,
                "name": "MismatchCity",
                "gender": "女",
                "age": 27,
                "city": "无锡",
                "preferred_cities": "上海",
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "认真恋爱",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
        ]

        with mock.patch.object(search_candidates, "load_source", return_value=fake_records), mock.patch.object(
            search_candidates, "attach_photo_previews"
        ), mock.patch(
            "sys.argv",
            [
                "search_candidates.py",
                "--source",
                "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                "--self-id",
                "90001",
                "--gender",
                "女",
                "--city",
                "无锡",
                "--limit",
                "10",
            ],
        ), mock.patch("sys.stdout", new_callable=mock.MagicMock) as mock_stdout:
            search_candidates.main()

        output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        self.assertIn("MatchA", output)
        self.assertNotIn("SELF", output)
        self.assertNotIn("MismatchCity", output)

    def test_main_with_self_id_negotiable_children_now_filtered_out(self):
        fake_records = [
            {
                "id": 90001,
                "name": "SELF",
                "gender": "男",
                "age": 30,
                "city": "无锡",
                "has_children": 1,
                "marital_status": "离异",
                "profile_status": "active",
                "verified_level": "id",
                "combined_text": "本人资料",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
            {
                "id": 401,
                "name": "NegotiableA",
                "gender": "女",
                "age": 29,
                "city": "无锡",
                "accept_partner_children": "可协商",
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "认真恋爱",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
        ]

        with mock.patch.object(search_candidates, "load_source", return_value=fake_records), mock.patch.object(
            search_candidates, "attach_photo_previews"
        ), mock.patch(
            "sys.argv",
            [
                "search_candidates.py",
                "--source",
                "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                "--self-id",
                "90001",
                "--gender",
                "女",
                "--city",
                "无锡",
            ],
        ), mock.patch("sys.stdout", new_callable=mock.MagicMock) as mock_stdout:
            search_candidates.main()

        output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        self.assertIn("No matches found.", output)
        self.assertIn("对方对你的孩子不是明确接受", output)

    def test_main_with_active_within_days_filters_old_activity(self):
        fake_records = [
            {
                "id": 501,
                "name": "TooOld",
                "gender": "女",
                "age": 26,
                "city": "无锡",
                "profile_status": "active",
                "verified_level": "id",
                "combined_text": "情绪稳定",
                "last_active_at": "2020-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            }
        ]

        with mock.patch.object(search_candidates, "load_source", return_value=fake_records), mock.patch.object(
            search_candidates, "attach_photo_previews"
        ), mock.patch(
            "sys.argv",
            [
                "search_candidates.py",
                "--source",
                "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                "--gender",
                "女",
                "--city",
                "无锡",
                "--active-within-days",
                "30",
            ],
        ), mock.patch("sys.stdout", new_callable=mock.MagicMock) as mock_stdout:
            search_candidates.main()

        output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        self.assertIn("No matches found.", output)

    def test_build_self_profile_from_args_self_id_missing_raises(self):
        parser = search_candidates.argparse.ArgumentParser()
        parser.add_argument("--self-id", type=int)
        parser.add_argument("--self-age", type=int)
        parser.add_argument("--self-city")
        parser.add_argument("--self-height", type=int)
        parser.add_argument("--self-education")
        parser.add_argument("--self-income-wan", type=int)
        parser.add_argument("--self-marital-status")
        parser.add_argument("--self-has-children", type=int)
        parser.add_argument("--self-smoking")
        parser.add_argument("--self-drinking")
        args = parser.parse_args(["--self-id", "99999"])
        with self.assertRaises(ValueError):
            search_candidates.build_self_profile_from_args(args, records=[])

    def test_build_self_profile_from_args_self_id_ambiguous_across_sources_raises(self):
        parser = search_candidates.argparse.ArgumentParser()
        parser.add_argument("--self-id", type=int)
        parser.add_argument("--self-age", type=int)
        parser.add_argument("--self-city")
        parser.add_argument("--self-height", type=int)
        parser.add_argument("--self-education")
        parser.add_argument("--self-income-wan", type=int)
        parser.add_argument("--self-marital-status")
        parser.add_argument("--self-has-children", type=int)
        parser.add_argument("--self-smoking")
        parser.add_argument("--self-drinking")
        args = parser.parse_args(["--self-id", "90001"])
        records = [
            {"id": 90001, "source_file": "mysql://a/db?table=profiles#profiles"},
            {"id": 90001, "source_file": "mysql://b/db?table=profiles#profiles"},
        ]

        with self.assertRaises(ValueError) as cm:
            search_candidates.build_self_profile_from_args(args, records=records)

        self.assertIn("ambiguous across multiple sources", str(cm.exception))

    def test_evaluate_candidate_only_excludes_exact_self_record_ref(self):
        criteria = {
            "gender": "女",
            "profile_statuses": ["active"],
            "exclude_ids": set(),
            "exclude_record_refs": {
                (90001, "mysql://root@127.0.0.1:3307/her?table=profiles#profiles")
            },
        }
        record = {
            "id": 90001,
            "name": "OtherSourceUser",
            "gender": "女",
            "profile_status": "active",
            "verified_level": "photo",
            "combined_text": "",
            "source_file": "mysql://other/db?table=profiles#profiles",
        }
        result = search_candidates.evaluate_candidate(record, criteria)
        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 90001)


if __name__ == "__main__":
    unittest.main()
