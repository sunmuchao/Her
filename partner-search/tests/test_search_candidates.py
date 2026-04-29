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
        self.assertIn("性别 女", result["matched_on"])

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

    def test_reciprocal_negotiable_risk_for_children(self):
        candidate = {"accept_partner_children": "可协商"}
        self_profile = {"has_children": 1}
        result = search_candidates.evaluate_reciprocal_compatibility(
            candidate, self_profile
        )
        self.assertIsNotNone(result)
        self.assertIn("对方对子女情况仅可协商", result["risk_flags"])

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

    def test_format_text_redacts_mysql_passwords(self):
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
            ]
        )
        self.assertIn("mysql://user:***@127.0.0.1:3306/her?table=profiles#profiles", text)
        self.assertNotIn("secret", text)
        self.assertIn("微信:ab***45", text)
        self.assertIn("138****5678", text)
        self.assertIn("a***@example.com", text)
        self.assertIn("320311********1234", text)
        self.assertNotIn("abc12345", text)
        self.assertNotIn("13812345678", text)

    def test_redact_sensitive_text_masks_common_contact_fields(self):
        redacted = search_candidates.redact_sensitive_text(
            "手机号 13998761234, 微信号 test_user88, 邮箱 bob@example.com"
        )
        self.assertIn("139****1234", redacted)
        self.assertIn("微信号 te***88", redacted)
        self.assertIn("b***@example.com", redacted)
        self.assertNotIn("13998761234", redacted)
        self.assertNotIn("test_user88", redacted)

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
            ["search_candidates.py", "--gender", "女"],
        ), mock.patch("sys.stdout", new_callable=mock.MagicMock) as mock_stdout:
            search_candidates.main()

        output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        self.assertIn("No matches found.", output)

    def test_main_exits_on_error(self):
        with mock.patch.object(search_candidates, "load_source", side_effect=ValueError("boom")), mock.patch(
            "sys.argv",
            ["search_candidates.py", "--gender", "女"],
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

    def test_main_with_self_id_negotiable_children_risk_visible(self):
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
        self.assertIn("NegotiableA", output)
        self.assertIn("对方对子女情况仅可协商", output)

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


if __name__ == "__main__":
    unittest.main()
