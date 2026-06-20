import unittest
from unittest import mock

import partner_search.search_candidates as search_candidates


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

    def test_load_mysql_reads_profiles_via_profile_service(self):
        with (
            mock.patch.object(search_candidates, "detect_profile_table", side_effect=AssertionError("should not detect table")),
            mock.patch.object(search_candidates, "list_profile_columns", return_value=["id", "name", "gender", "profile_status"]),
            mock.patch.object(
                search_candidates,
                "list_profiles",
                return_value=[{"id": 101, "name": "Alice", "gender": "女", "profile_status": "active"}],
            ) as mocked_list_profiles,
        ):
            rows = search_candidates.load_mysql(
                "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                criteria={"gender": "女"},
                include_ids=[101],
            )

        self.assertEqual(rows[0]["id"], 101)
        self.assertEqual(rows[0]["source_file"], "mysql://user:pass@127.0.0.1:3306/her?table=profiles#profiles")
        kwargs = mocked_list_profiles.call_args.kwargs
        self.assertEqual(kwargs["source_table_name"], "profiles")
        self.assertIn("WHERE", kwargs["where_clause"])
        self.assertIn("?", kwargs["where_clause"])
        self.assertNotIn("%s", kwargs["where_clause"])
        self.assertIn(101, kwargs["params"])

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
        parser.add_argument("--exclude-source-channel", action="append")
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
                "--must-have",
                "已购房",
                "--require-known",
                "smoking,想要孩子",
                "--profile-status",
                "active,paused",
                "--exclude-id",
                "90001",
                "--exclude-source-channel",
                "persona-memory-sync",
            ]
        )
        criteria = search_candidates.build_criteria_from_args(args)
        self.assertEqual(criteria["gender"], "女")
        self.assertEqual(criteria["age_min"], 24)
        self.assertEqual(criteria["cities"], ["无锡", "苏州"])
        self.assertEqual(criteria["must_have"], ["已购房"])
        self.assertIn("情绪稳定", criteria["prefer"])
        self.assertEqual(criteria["required_known_fields"], ["smoking", "want_children"])
        self.assertEqual(criteria["profile_statuses"], ["active", "paused"])
        self.assertEqual(criteria["exclude_ids"], {90001})
        self.assertEqual(criteria["exclude_source_channels"], {"persona-memory-sync"})

    def test_build_criteria_from_args_softens_additional_relationship_keywords(self):
        args = search_candidates.argparse.Namespace(
            gender=None,
            age_min=None,
            age_max=None,
            height_min=None,
            height_max=None,
            city=None,
            district=None,
            settlement_city=None,
            relationship_goal=None,
            must_have=["性格稳定", "不暧昧"],
            must_not_have=None,
            prefer=None,
            smoking=None,
            drinking=None,
            long_distance=None,
            housing_status=None,
            car_status=None,
            marital_status=None,
            has_children=None,
            want_children=None,
            accept_partner_children=None,
            accept_marital_status_strength=None,
            accept_partner_children_strength=None,
            marriage_timeline=None,
            profile_status=None,
            active_within_days=None,
            verified_level_min=None,
            verified_level=None,
            photo_count_min=None,
            require_known=None,
            exclude_id=None,
            exclude_source_channel=None,
        )

        criteria = search_candidates.build_criteria_from_args(args)

        self.assertNotIn("must_have", criteria)
        self.assertIn("性格稳定", criteria["prefer"])
        self.assertIn("不暧昧", criteria["prefer"])

    def test_build_mysql_prefilter_supports_excluding_source_channel(self):
        criteria = {
            "gender": "女",
            "profile_statuses": ["active"],
            "exclude_source_channels": {"persona-memory-sync"},
        }
        canonical_to_actual = {
            "gender": "gender",
            "profile_status": "profile_status",
            "source_channel": "source_channel",
        }

        where_clause, params = search_candidates.build_mysql_prefilter(criteria, canonical_to_actual)

        self.assertIn("`source_channel`", where_clause)
        self.assertIn("NOT IN", where_clause)
        self.assertIn("persona-memory-sync", params)

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
        self.assertEqual(
            result["score"],
            result["fit_score"] + result["confidence_score"] - result["risk_score"],
        )
        self.assertTrue(
            {
                "id",
                "name",
                "score",
                "fit_score",
                "confidence_score",
                "risk_score",
                "matched_on",
                "reciprocal_on",
                "missing_fields",
                "self_profile_gaps",
                "risk_flags",
                "match_evidence",
                "follow_up_questions",
                "profile",
                "source_file",
                "verified_rank",
                "activity_sort_ts",
                "profile_status_rank",
            }.issubset(result.keys())
        )
        self.assertGreater(result["fit_score"], 0)
        self.assertGreater(result["confidence_score"], 0)
        self.assertEqual(result["risk_score"], 0)
        self.assertIn("性别 女", result["matched_on"])
        self.assertIn("消费观正常 <- 价值观: 消费观正常", result["match_evidence"])

    def test_evaluate_candidate_rejects_excluded_source_channel(self):
        record = {
            "id": 101,
            "name": "测试用户",
            "gender": "女",
            "age": 27,
            "city": "无锡",
            "profile_status": "active",
            "source_channel": "persona-memory-sync",
        }
        criteria = {
            "gender": "女",
            "exclude_ids": set(),
            "exclude_source_channels": {"persona-memory-sync"},
        }

        result = search_candidates.evaluate_candidate(record, criteria, diagnostics=True)

        self.assertFalse(result["matched"])
        self.assertEqual(result["reject_reason"], "exclude_source_channel")
        self.assertEqual(result["id"], 101)
        self.assertEqual(result["name"], "测试用户")

    def test_evaluate_candidate_surfaces_habit_matches_when_requested(self):
        record = {
            "id": 102,
            "name": "HabitFit",
            "gender": "女",
            "age": 27,
            "city": "无锡",
            "smoking": "否",
            "drinking": "否",
            "profile_status": "active",
            "verified_level": "photo",
            "combined_text": "认真恋爱",
            "last_active_at": "2099-01-01 00:00:00",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "女",
            "cities": ["无锡"],
            "smoking": "否",
            "drinking": "否",
            "profile_statuses": ["active"],
            "exclude_ids": set(),
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNotNone(result)
        self.assertIn("不抽烟", result["matched_on"])
        self.assertIn("少酒/不喝酒", result["matched_on"])

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

    def test_keyword_matches_record_accepts_structured_emotional_stability_signals(self):
        record = {
            "interaction_comfort": "安静低压",
            "patience_level": "高耐心",
            "warmth_style": "理性但不冷",
            "combined_text": "认真恋爱 稳定投入关系",
        }

        self.assertTrue(search_candidates.keyword_matches_record(record, "情绪稳定"))
        self.assertEqual(
            search_candidates.extract_keyword_evidence(record, "情绪稳定"),
            "结构化信号: 相处状态=安静低压；耐心程度=高耐心；聊天温度=理性但不冷",
        )

    def test_evaluate_candidate_accepts_structured_emotional_stability_without_literal_keyword(self):
        record = {
            "id": 106,
            "name": "StructuredStable",
            "gender": "男",
            "age": 34,
            "city": "上海",
            "settlement_city": "上海",
            "relationship_goal": "结婚导向",
            "smoking": "否",
            "drinking": "否",
            "long_distance": "不接受",
            "profile_status": "active",
            "verified_level": "id",
            "photo_count": 6,
            "interaction_comfort": "有边界不拧巴",
            "patience_level": "高耐心",
            "warmth_style": "有温度会接话",
            "combined_text": "结婚导向 上海 定居上海 不接受异地 不抽烟不喝酒",
            "last_active_at": "2099-01-01 00:00:00",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "男",
            "age_min": 32,
            "age_max": 38,
            "cities": ["上海"],
            "settlement_cities": ["上海"],
            "relationship_goals": ["结婚导向"],
            "must_have": ["情绪稳定"],
            "smoking": "否",
            "drinking": "否",
            "long_distance": "不接受",
            "profile_statuses": ["active"],
            "verified_level_min": "photo",
            "photo_count_min": 4,
            "exclude_ids": set(),
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNotNone(result)
        self.assertIn("包含 情绪稳定", result["matched_on"])
        self.assertIn(
            "情绪稳定 <- 结构化信号: 相处状态=有边界不拧巴；耐心程度=高耐心；聊天温度=有温度会接话",
            result["match_evidence"],
        )

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

    def test_evaluate_candidate_does_not_reject_non_smoker_for_smoking_keyword(self):
        record = {
            "id": 107,
            "name": "NoSmoking",
            "profile_status": "active",
            "verified_level": "photo",
            "smoking": "否",
            "combined_text": "不抽烟，生活规律",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "must_not_have": ["抽烟"],
            "profile_statuses": ["active"],
            "exclude_ids": set(),
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNotNone(result)
        self.assertNotIn("资料里提到“抽烟”，需要确认具体语境", result["risk_flags"])

    def test_evaluate_candidate_does_not_reject_soft_negative_keyword_when_it_is_boundary(self):
        record = {
            "id": 108,
            "name": "NoDrama",
            "profile_status": "active",
            "verified_level": "photo",
            "notes": "不喜欢关系里来回拉扯，希望相处简单直接。",
            "combined_text": "不喜欢关系里来回拉扯 希望相处简单直接",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "must_not_have": ["拉扯"],
            "profile_statuses": ["active"],
            "exclude_ids": set(),
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNotNone(result)
        self.assertNotIn("资料里提到“拉扯”，需要确认具体语境", result["risk_flags"])

    def test_evaluate_candidate_soft_negative_keyword_ambiguous_mention_becomes_risk(self):
        record = {
            "id": 109,
            "name": "AmbiguousDrama",
            "profile_status": "active",
            "verified_level": "photo",
            "notes": "之前经历过一段很拉扯的关系，现在更想稳定。",
            "combined_text": "之前经历过一段很拉扯的关系 现在更想稳定",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "must_not_have": ["拉扯"],
            "profile_statuses": ["active"],
            "exclude_ids": set(),
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNotNone(result)
        self.assertIn("资料里提到“拉扯”，需要确认具体语境", result["risk_flags"])

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
        # 状态未知时不应在matched_on中添加状态信息
        self.assertNotIn("状态 活跃", result["matched_on"])

    def test_evaluate_candidate_keeps_near_age_outside_range(self):
        record = {
            "id": 104,
            "name": "NearAge",
            "gender": "女",
            "age": 27,
            "city": "无锡",
            "profile_status": "active",
            "verified_level": "photo",
            "combined_text": "",
            "last_active_at": "2099-01-01 00:00:00",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "女",
            "age_min": 28,
            "age_max": 32,
            "profile_statuses": ["active"],
            "exclude_ids": set(),
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNotNone(result)
        self.assertIn("年龄 27（接近你的要求）", result["matched_on"])
        self.assertIn("年龄略偏离理想区间，但仍然接近", result["risk_flags"])

    def test_evaluate_candidate_rejects_far_age_outside_range(self):
        record = {
            "id": 105,
            "name": "FarAge",
            "gender": "女",
            "age": 22,
            "city": "无锡",
            "profile_status": "active",
            "verified_level": "photo",
            "combined_text": "",
            "last_active_at": "2099-01-01 00:00:00",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "女",
            "age_min": 28,
            "age_max": 32,
            "profile_statuses": ["active"],
            "exclude_ids": set(),
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNone(result)

    def test_evaluate_candidate_keeps_near_height_outside_range(self):
        record = {
            "id": 106,
            "name": "NearHeight",
            "gender": "女",
            "age": 28,
            "height": 173,
            "city": "无锡",
            "profile_status": "active",
            "verified_level": "photo",
            "combined_text": "",
            "last_active_at": "2099-01-01 00:00:00",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "女",
            "height_min": 175,
            "height_max": 180,
            "profile_statuses": ["active"],
            "exclude_ids": set(),
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNotNone(result)
        self.assertIn("身高 173cm（接近你的要求）", result["matched_on"])
        self.assertIn("身高略偏离理想区间，但仍然接近", result["risk_flags"])

    def test_evaluate_candidate_rejects_far_height_outside_range(self):
        record = {
            "id": 107,
            "name": "FarHeight",
            "gender": "女",
            "age": 28,
            "height": 165,
            "city": "无锡",
            "profile_status": "active",
            "verified_level": "photo",
            "combined_text": "",
            "last_active_at": "2099-01-01 00:00:00",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "女",
            "height_min": 175,
            "height_max": 180,
            "profile_statuses": ["active"],
            "exclude_ids": set(),
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNone(result)

    def test_reciprocal_rejects_non_matching_city(self):
        candidate = {"preferred_cities": "上海"}
        self_profile = {"city": "无锡"}
        self.assertIsNone(
            search_candidates.evaluate_reciprocal_compatibility(candidate, self_profile)
        )

    def test_reciprocal_city_preference_softens_when_accepts_long_distance(self):
        candidate = {
            "preferred_cities": "上海",
            "accept_long_distance": "接受",
            "location_preference_semantics": "短期异地可了解，但需要明确落地计划；不接受长期异地",
        }
        self_profile = {"city": "无锡"}

        result = search_candidates.evaluate_reciprocal_compatibility(candidate, self_profile)

        self.assertIsNotNone(result)
        self.assertIn("对方城市偏好未命中，但资料写了接受异地", result["risk_flags"])
        self.assertIn("对方不接受长期异地，需要确认落地计划", result["risk_flags"])

    def test_evaluate_candidate_prefers_same_city_when_near_distance_is_priority(self):
        base_record = {
            "gender": "女",
            "profile_status": "active",
            "verified_level": "photo",
            "last_active_at": "2099-01-01 00:00:00",
            "combined_text": "",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            "relationship_goal": "结婚导向",
            "marital_status": "未婚",
            "photo_count": 4,
            "age": 31,
            "height": 165,
            "accept_long_distance": "接受",
        }
        same_city = dict(base_record, id=211, name="SameCity", city="宁波")
        cross_city = dict(base_record, id=212, name="CrossCity", city="杭州")
        criteria = {
            "gender": "女",
            "profile_statuses": ["active"],
            "relationship_goals": ["结婚导向"],
            "exclude_ids": set(),
            "self_profile": {
                "city": "宁波",
                "accept_long_distance": "不接受",
                "preferred_cities": "宁波,杭州",
            },
        }

        same_result = search_candidates.evaluate_candidate(same_city, criteria)
        cross_result = search_candidates.evaluate_candidate(cross_city, criteria)

        self.assertIsNotNone(same_result)
        self.assertIsNotNone(cross_result)
        self.assertIn("近距离更省心", same_result["matched_on"])
        self.assertIn("非同城，见面推进成本更高", cross_result["risk_flags"])
        self.assertGreater(same_result["score"], cross_result["score"])

    def test_reciprocal_negotiable_children_becomes_risk_when_self_has_children(self):
        candidate = {
            "accept_partner_children": "可协商",
            "accept_partner_children_strength": "短期可聊",
            "accept_partner_children_semantics": "可以先接触再判断",
        }
        self_profile = {"has_children": 1}
        result = search_candidates.evaluate_reciprocal_compatibility(
            candidate, self_profile, diagnostics=True
        )
        self.assertIsNotNone(result)
        self.assertTrue(result["matched"])
        self.assertIn(
            "对方对子女接受需要先接触再判断",
            result["risk_flags"],
        )

    def test_reciprocal_guarded_children_state_becomes_low_acceptance_risk(self):
        candidate = {
            "accept_partner_children": "现阶段不太接受",
            "accept_partner_children_strength": "谨慎接受",
            "accept_partner_children_semantics": "现阶段不太接受",
        }
        self_profile = {"has_children": 1}
        result = search_candidates.evaluate_reciprocal_compatibility(
            candidate, self_profile, diagnostics=True
        )
        self.assertIsNotNone(result)
        self.assertTrue(result["matched"])
        self.assertIn(
            "对方对子女接受度偏低",
            result["risk_flags"],
        )

    def test_reciprocal_missing_children_acceptance_called_out(self):
        candidate = {}
        self_profile = {"has_children": 1}
        result = search_candidates.evaluate_reciprocal_compatibility(
            candidate, self_profile
        )
        self.assertIsNotNone(result)
        self.assertIn("accept_partner_children", result["missing_fields"])

    def test_contextual_fit_does_not_force_family_reality_language_for_divorced_without_children(self):
        result = search_candidates.evaluate_contextual_fit(
            {
                "blended_family_readiness": "已想过现实安排",
                "accept_marital_status_strength": "明确接受",
                "notes": "愿意一起把现实安排说清楚",
            },
            {"prefer": ["真诚", "愿意沟通"], "must_have": []},
            self_profile={"marital_status": "离异", "has_children": 0},
        )
        self.assertNotIn("现实安排想得更具体", result["matched_on"])

    def test_contextual_fit_rewards_shared_creative_domain_for_expressive_profile(self):
        result = search_candidates.evaluate_contextual_fit(
            {
                "job": "品牌设计师",
            },
            {
                "prefer": ["有一点审美", "共同兴趣", "有情绪回应"],
                "must_have": [],
            },
            self_profile={"job": "游戏UI设计管理岗"},
        )
        self.assertIn("审美和内容语境更接近", result["matched_on"])

    def test_summarize_notes_for_result_filters_unrequested_child_topic(self):
        summary = search_candidates.summarize_notes_for_result(
            {"notes": "不要孩子这件事已经想清楚；平时沟通顺畅，比较有边界感。"},
            {"prefer": ["情绪稳定"], "must_have": [], "must_not_have": [], "relationship_goals": []},
            {"marital_status": "未婚", "has_children": 0},
        )
        self.assertEqual(summary, "平时沟通顺畅，比较有边界感")

    def test_append_result_detail_lines_respects_explicit_filtered_notes(self):
        lines = []
        search_candidates.append_result_detail_lines(
            lines,
            {
                "matched_on": [],
                "reciprocal_on": [],
                "missing_fields": [],
                "risk_flags": [],
                "match_evidence": [],
                "follow_up_questions": [],
                "display_notes": None,
            },
            {"notes": "不要孩子这件事已经想清楚"},
        )
        self.assertFalse(any(line.startswith("   notes:") for line in lines))

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
        self.assertIn(
            "对方收入预期上限未命中，但不构成硬性淘汰",
            result["risk_flags"],
        )

    def test_reciprocal_income_above_max_is_not_hard_rejected(self):
        candidate = {
            "preferred_income_min_wan": 30,
            "preferred_income_max_wan": 50,
            "preferred_income_strictness": "硬性",
        }
        self_profile = {"income_min_wan": 100, "income_max_wan": 100}

        result = search_candidates.evaluate_reciprocal_compatibility(candidate, self_profile)

        self.assertIsNotNone(result)
        self.assertTrue(result["matched"])
        self.assertIn(
            "对方收入预期上限未命中，但不构成硬性淘汰",
            result["risk_flags"],
        )

    def test_reciprocal_income_below_min_still_rejects_when_hard(self):
        candidate = {
            "preferred_income_min_wan": 30,
            "preferred_income_max_wan": 50,
            "preferred_income_strictness": "硬性",
        }
        self_profile = {"income_min_wan": 20, "income_max_wan": 20}

        result = search_candidates.evaluate_reciprocal_compatibility(candidate, self_profile)

        self.assertIsNone(result)

    def test_reciprocal_income_empty_strictness_defaults_to_soft(self):
        candidate = {
            "preferred_income_min_wan": 30,
            "preferred_income_max_wan": 50,
        }
        self_profile = {"income_min_wan": 20, "income_max_wan": 20}

        result = search_candidates.evaluate_reciprocal_compatibility(candidate, self_profile)

        self.assertIsNotNone(result)
        self.assertTrue(result["matched"])
        self.assertIn("对方收入要求可能可放宽", result["risk_flags"])

    def test_reciprocal_children_acceptance_cautious_signal_becomes_risk(self):
        candidate = {
            "accept_partner_children": "接受",
            "accept_partner_children_strength": "谨慎接受",
        }
        self_profile = {"has_children": 1}
        result = search_candidates.evaluate_reciprocal_compatibility(
            candidate, self_profile, diagnostics=True
        )
        self.assertIsNotNone(result)
        self.assertTrue(result["matched"])
        self.assertIn(
            "对方对子女接受度偏保守",
            result["risk_flags"],
        )

    def test_build_follow_up_questions_supports_children_semantic_risk(self):
        questions = search_candidates.build_follow_up_questions(
            {},
            [],
            ["对方对子女接受度偏低"],
        )
        self.assertTrue(any("对子女情况" in item for item in questions))

    def test_reciprocal_marital_acceptance_surface_signal_becomes_risk(self):
        candidate = {
            "accept_marital_status": "未婚,离异未育,离异已育",
            "accept_marital_status_strength": "短期可聊",
            "accept_marital_status_semantics": "能先聊，但还要再判断",
        }
        self_profile = {"marital_status": "离异未育"}
        result = search_candidates.evaluate_reciprocal_compatibility(
            candidate, self_profile, diagnostics=True
        )
        self.assertIsNotNone(result)
        self.assertTrue(result["matched"])
        self.assertIn(
            "对方婚史接受需要先聊再判断",
            result["risk_flags"],
        )

    def test_reciprocal_marital_acceptance_matches_plain_divorce_with_children_state(self):
        candidate = {
            "accept_marital_status": "未婚,离异已育",
            "accept_marital_status_strength": "明确接受",
        }
        self_profile = {"marital_status": "离异", "has_children": 1}

        result = search_candidates.evaluate_reciprocal_compatibility(candidate, self_profile)

        self.assertIsNotNone(result)
        self.assertIn("对方可接受婚况命中", result["matched_on"])

    def test_evaluate_candidate_children_semantics_affect_ranking(self):
        base_record = {
            "gender": "女",
            "profile_status": "active",
            "verified_level": "photo",
            "last_active_at": "2099-01-01 00:00:00",
            "combined_text": "",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        lower_acceptance = dict(
            base_record,
            id=201,
            name="LowAcceptance",
            accept_partner_children="可协商",
            accept_partner_children_strength="谨慎接受",
            accept_partner_children_semantics="现阶段接受度偏低，需结合具体情况判断",
        )
        softer_acceptance = dict(
            base_record,
            id=202,
            name="SurfaceAcceptance",
            accept_partner_children="可协商",
            accept_partner_children_strength="短期可聊",
            accept_partner_children_semantics="可以先接触再判断",
        )
        criteria = {
            "gender": "女",
            "profile_statuses": ["active"],
            "exclude_ids": set(),
            "self_profile": {"has_children": 1},
        }

        lower_result = search_candidates.evaluate_candidate(lower_acceptance, criteria)
        softer_result = search_candidates.evaluate_candidate(softer_acceptance, criteria)

        self.assertIsNotNone(lower_result)
        self.assertIsNotNone(softer_result)
        self.assertIn("对方对子女接受度偏低", lower_result["risk_flags"])
        self.assertIn("对方对子女接受需要先接触再判断", softer_result["risk_flags"])
        self.assertLess(lower_result["score"], softer_result["score"])

    def test_evaluate_candidate_marks_concession_stack_when_multiple_soft_risks_accumulate(self):
        record = {
            "id": 301,
            "name": "SoftStack",
            "gender": "男",
            "city": "常州",
            "age": 36,
            "height": 178,
            "relationship_goal": "结婚导向",
            "marital_status": "未婚",
            "profile_status": "active",
            "verified_level": "photo",
            "photo_count": 4,
            "last_active_at": "2099-01-01 00:00:00",
            "combined_text": "",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            "accept_long_distance": "可协商",
            "preferred_age_max": 35,
            "preferred_age_strictness": "可放宽",
            "commitment_clarity": "愿意稳定推进",
            "relationship_execution": "口头长期待验证",
        }
        criteria = {
            "gender": "男",
            "profile_statuses": ["active"],
            "relationship_goals": ["结婚导向"],
            "exclude_ids": set(),
            "self_profile": {
                "age": 38,
                "city": "镇江",
                "accept_long_distance": "不接受",
            },
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNotNone(result)
        self.assertIn("对方年龄要求可能可放宽", result["risk_flags"])
        self.assertIn("对方异地仅可协商", result["risk_flags"])
        self.assertIn("非同城，见面推进成本更高", result["risk_flags"])
        self.assertIn("长期意图有，但推进方式还不够落地", result["risk_flags"])
        self.assertIn("多项条件需要放宽后才成立", result["risk_flags"])

    def test_reciprocal_uses_matcher_preference_tags_for_soft_bonus(self):
        candidate = {
            "matcher_preferences_json": '{"must_have_tags":["情绪稳定"],"preferred_traits":["愿意沟通"]}',
        }
        self_profile = {
            "combined_text": "情绪稳定，也愿意沟通，遇事不逃避。",
        }
        result = search_candidates.evaluate_reciprocal_compatibility(candidate, self_profile)
        self.assertIsNotNone(result)
        self.assertIn("对方软性偏好有重合", result["matched_on"])
        self.assertGreaterEqual(result["score_bonus"], 2)

    def test_evaluate_contextual_fit_rewards_growth_warmth_and_aesthetic(self):
        record = {
            "education": "硕士",
            "income_range": "42-68万/年",
            "growth_signal": "上升明确",
            "warmth_style": "理性但不冷",
            "aesthetic_expression": "有审美输出",
            "conversation_resonance": "能聊想法也能聊日常",
            "personal_presence": "有记忆点",
            "lightness_humor": "有点幽默不端着",
            "commitment_clarity": "明确奔着长期",
            "life_texture": "有见识也有生活感",
            "interaction_comfort": "有边界不拧巴",
            "patience_level": "耐心稳定",
            "communication_style": "主动沟通",
            "dating_pace": "认真推进",
            "career_intensity": "脑力投入型",
        }
        criteria = {
            "prefer": ["成长", "沟通", "生活感", "审美"],
            "relationship_goals": ["结婚导向"],
        }
        self_profile = {
            "age": 31,
            "education": "博士",
            "income_max_wan": 70,
        }
        result = search_candidates.evaluate_contextual_fit(record, criteria, self_profile=self_profile)
        self.assertIn("成长势能更强", result["matched_on"])
        self.assertIn("理性但不冷", result["matched_on"])
        self.assertIn("更有审美和表达感", result["matched_on"])
        self.assertIn("聊天层次更完整", result["matched_on"])
        self.assertIn("资料辨识度更高", result["matched_on"])
        self.assertIn("条件之外，表达层次也更完整", result["matched_on"])
        self.assertIn("互动更轻松", result["matched_on"])
        self.assertIn("进入关系意愿更明确", result["matched_on"])
        self.assertIn("互动不容易太板正", result["matched_on"])
        self.assertGreater(result["score_bonus"], 0)

    def test_evaluate_contextual_fit_rewards_doctorate_match_and_active_communication(self):
        record = {
            "education": "博士",
            "income_range": "60-90万/年",
            "growth_signal": "上升明确",
            "warmth_style": "理性但不冷",
            "aesthetic_expression": "有审美输出",
            "conversation_resonance": "能聊想法也能聊日常",
            "personal_presence": "有记忆点",
            "lightness_humor": "有点幽默不端着",
            "commitment_clarity": "明确奔着长期",
            "life_texture": "有见识也有生活感",
            "interaction_comfort": "有边界不拧巴",
            "patience_level": "耐心稳定",
            "communication_style": "主动沟通",
            "dating_pace": "认真推进",
            "career_intensity": "脑力投入型",
        }
        criteria = {
            "prefer": ["主动沟通", "沟通", "有生活感"],
            "relationship_goals": ["结婚导向"],
        }
        self_profile = {
            "age": 31,
            "education": "博士",
            "income_max_wan": 70,
        }

        result = search_candidates.evaluate_contextual_fit(record, criteria, self_profile=self_profile)

        self.assertIn("认知层次更对位", result["matched_on"])
        self.assertIn("沟通更主动", result["matched_on"])
        self.assertIn("理性但不端着", result["matched_on"])

    def test_evaluate_contextual_fit_rewards_steady_realistic_divorce_acceptance(self):
        steady_record = {
            "career_intensity": "规律稳定",
            "blended_family_readiness": "已想过现实安排",
            "accept_marital_status_strength": "明确接受",
            "notes": "会把婚史、现实安排和双方家里边界聊明白",
            "values": "稳定踏实, 愿意共同经营生活",
            "commitment_clarity": "明确奔着长期",
        }
        busy_record = {
            "career_intensity": "高强度但可协调",
            "blended_family_readiness": "已想过现实安排",
            "accept_marital_status_strength": "明确接受",
            "notes": "明确接受离异未育",
            "values": "稳定踏实, 愿意共同经营生活",
            "commitment_clarity": "明确奔着长期",
        }
        criteria = {
            "prefer": ["稳定踏实", "相处舒服"],
            "relationship_goals": ["结婚导向"],
        }
        self_profile = {
            "age": 34,
            "marital_status": "离异未育",
        }

        steady = search_candidates.evaluate_contextual_fit(steady_record, criteria, self_profile=self_profile)
        busy = search_candidates.evaluate_contextual_fit(busy_record, criteria, self_profile=self_profile)

        self.assertIn("工作节奏更稳", steady["matched_on"])
        self.assertNotIn("复杂现实问题愿意提前讲清", steady["matched_on"])
        self.assertIn("工作节奏偏忙，稳定投入要再看", busy["risk_flags"])

    def test_evaluate_contextual_fit_uses_new_fields_for_consumption_chat_and_execution(self):
        record = {
            "warmth_style": "有温度会接话",
            "lightness_humor": "稳重有分寸",
            "consumption_attitude": "清醒务实",
            "chat_texture": "顺着聊不费劲",
            "commitment_clarity": "明确奔着长期",
            "relationship_execution": "会把安排说清",
        }
        criteria = {
            "prefer": ["消费观正常", "会接话", "不板正", "长期"],
            "relationship_goals": ["认真恋爱"],
        }

        result = search_candidates.evaluate_contextual_fit(record, criteria, self_profile={"age": 29})

        self.assertIn("过日子观念更稳", result["matched_on"])
        self.assertIn("聊天更顺，不容易累", result["matched_on"])
        self.assertIn("稳重但不板正", result["matched_on"])
        self.assertIn("推进方式更落地", result["matched_on"])
        self.assertGreater(result["score_bonus"], 0)

    def test_evaluate_contextual_fit_rewards_positive_energy_and_serious_dating_execution(self):
        record = {
            "life_routine": "生活规律",
            "exercise_habit": "规律运动",
            "warmth_style": "有温度会接话",
            "lightness_humor": "有点幽默不端着",
            "commitment_clarity": "明确奔着长期",
            "relationship_execution": "会把安排说清",
        }
        criteria = {
            "prefer": ["乐观", "生活规律", "规律运动"],
            "relationship_goals": ["认真恋爱"],
        }

        result = search_candidates.evaluate_contextual_fit(record, criteria, self_profile={"age": 28})

        self.assertIn("生活节奏更稳", result["matched_on"])
        self.assertIn("相处更有正反馈", result["matched_on"])
        self.assertIn("相处更有松弛感", result["matched_on"])
        self.assertIn("认真相处意愿更明确", result["matched_on"])
        self.assertIn("认真相处不拖泥带水", result["matched_on"])

    def test_evaluate_candidate_separates_self_profile_gaps_from_candidate_missing_fields(self):
        record = {
            "id": 301,
            "name": "GapSplit",
            "gender": "男",
            "age": 34,
            "city": "上海",
            "preferred_height_min": 175,
            "profile_status": "active",
            "verified_level": "photo",
            "combined_text": "认真恋爱",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "男",
            "profile_statuses": ["active"],
            "exclude_ids": set(),
            "self_profile": {"city": "上海"},
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNotNone(result)
        self.assertIn("self_height", result["self_profile_gaps"])
        self.assertNotIn("self_height", result["missing_fields"])

    def test_evaluate_candidate_surfaces_height_match_when_bound_present(self):
        record = {
            "id": 302,
            "name": "HeightHit",
            "gender": "男",
            "age": 33,
            "height": 182,
            "city": "上海",
            "profile_status": "active",
            "verified_level": "photo",
            "combined_text": "认真恋爱",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "男",
            "age_min": 30,
            "age_max": 36,
            "height_min": 180,
            "profile_statuses": ["active"],
            "exclude_ids": set(),
            "self_profile": {"city": "上海"},
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNotNone(result)
        self.assertIn("身高 182cm", result["matched_on"])

    def test_select_diverse_results_avoids_near_duplicate_top_profiles(self):
        results = [
            {
                "id": 1,
                "score": 100,
                "verified_rank": 3,
                "activity_sort_ts": 30,
                "profile_status_rank": 3,
                "profile": {
                    "job": "产品经理",
                    "career_intensity": "脑力投入型",
                    "communication_style": "主动沟通",
                    "life_routine": "生活规律",
                    "commitment_clarity": "明确奔着长期",
                },
            },
            {
                "id": 2,
                "score": 99,
                "verified_rank": 3,
                "activity_sort_ts": 29,
                "profile_status_rank": 3,
                "profile": {
                    "job": "研发工程师",
                    "career_intensity": "脑力投入型",
                    "communication_style": "主动沟通",
                    "life_routine": "生活规律",
                    "commitment_clarity": "明确奔着长期",
                },
            },
            {
                "id": 3,
                "score": 97,
                "verified_rank": 2,
                "activity_sort_ts": 28,
                "profile_status_rank": 3,
                "profile": {
                    "job": "教师",
                    "career_intensity": "规律稳定",
                    "communication_style": "稳定沟通",
                    "life_routine": "生活稳定",
                    "commitment_clarity": "愿意稳定推进",
                },
            },
        ]

        selected = search_candidates.select_diverse_results(results, 2)

        self.assertEqual([item["id"] for item in selected], [1, 3])

    def test_select_diverse_results_trims_high_risk_tail(self):
        results = [
            {
                "id": 1,
                "score": 155,
                "risk_score": 18,
                "risk_flags": ["对方异地仅可协商"],
                "verified_rank": 2,
                "activity_sort_ts": 30,
                "profile_status_rank": 3,
                "profile": {"job": "设计", "communication_style": "主动沟通"},
            },
            {
                "id": 2,
                "score": 115,
                "risk_score": 43,
                "risk_flags": ["多项条件需要放宽后才成立"],
                "verified_rank": 4,
                "activity_sort_ts": 29,
                "profile_status_rank": 3,
                "profile": {"job": "人事", "communication_style": "稳定沟通"},
            },
            {
                "id": 3,
                "score": 113,
                "risk_score": 43,
                "risk_flags": ["多项条件需要放宽后才成立"],
                "verified_rank": 1,
                "activity_sort_ts": 28,
                "profile_status_rank": 3,
                "profile": {"job": "法务", "communication_style": "慢热少话"},
            },
        ]

        selected = search_candidates.select_diverse_results(results, 3)

        self.assertEqual([item["id"] for item in selected], [1])

    def test_evaluate_candidate_marks_below_self_education_floor_as_risk(self):
        record = {
            "id": 401,
            "name": "EduGap",
            "gender": "女",
            "age": 31,
            "height": 165,
            "city": "宁波",
            "relationship_goal": "结婚导向",
            "marital_status": "未婚",
            "education": "大专",
            "smoking": "否",
            "profile_status": "active",
            "verified_level": "photo",
            "photo_count": 4,
            "combined_text": "认真恋爱 宁波 不抽烟",
            "last_active_at": "2099-01-01 00:00:00",
            "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
        }
        criteria = {
            "gender": "女",
            "cities": ["宁波"],
            "relationship_goals": ["结婚导向"],
            "smoking": "否",
            "profile_statuses": ["active"],
            "verified_level_min": "basic",
            "photo_count_min": 3,
            "exclude_ids": set(),
            "self_profile": {
                "preferred_education_min": "本科",
                "preferred_education_strictness": "可放宽",
            },
        }

        result = search_candidates.evaluate_candidate(record, criteria)

        self.assertIsNotNone(result)
        self.assertIn("学历没有完全卡进你的底线", result["risk_flags"])

    def test_build_follow_up_questions_handles_new_style_fields_and_risks(self):
        questions = search_candidates.build_follow_up_questions(
            {},
            ["consumption_attitude", "chat_texture", "relationship_execution"],
            ["聊天还像完成任务", "长期意图有，但推进方式还不够落地"],
        )

        self.assertIn("确认对方花钱更看重什么，是清醒务实，还是容易被外在包装带着走。", questions)
        self.assertIn("确认对方聊天是顺着聊不费劲，还是容易只剩条件交换。", questions)
        self.assertIn("确认对方认真推进时，会不会把见面节奏、关系预期和现实安排说清。", questions)
        self.assertIn("确认对方聊天是不是容易只讲条件和流程，还是能把话题真正聊活。", questions)
        self.assertIn("确认对方不是只会说想长期，而是真的会把推进节奏和安排说清。", questions)

    def test_build_follow_up_questions_handles_concession_stack_risk(self):
        questions = search_candidates.build_follow_up_questions(
            {},
            [],
            ["多项条件需要放宽后才成立"],
        )

        self.assertEqual(
            questions,
            ["确认这段匹配到底是少数几个点不完美，还是很多关键条件都要靠放宽才行。"],
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

    def test_format_text_shows_compact_signal_fields_when_present(self):
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
                    "self_profile_gaps": ["self_height"],
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
                        "growth_signal": "上升明确",
                        "warmth_style": "有温度会接话",
                        "aesthetic_expression": "有审美输出",
                        "conversation_resonance": "能聊想法也能聊日常",
                        "personal_presence": "有记忆点",
                        "lightness_humor": "有点幽默不端着",
                        "consumption_attitude": "清醒务实",
                        "chat_texture": "有梗也有内容",
                        "commitment_clarity": "明确奔着长期",
                        "relationship_execution": "会把安排说清",
                        "blended_family_readiness": "已想过现实安排",
                    },
                    "source_file": "",
                    "verified_rank": 0,
                    "activity_sort_ts": 0,
                    "profile_status_rank": 0,
                }
            ]
        )
        self.assertIn("signals: 作息=生活规律 | 沟通=主动沟通 | 节奏=自然推进", text)
        self.assertIn("成长=上升明确", text)
        self.assertIn("消费观=清醒务实", text)
        self.assertIn("长期意图=明确奔着长期", text)
        self.assertIn("推进方式=会把安排说清", text)
        self.assertIn("现实承接=已想过现实安排", text)
        self.assertIn("self_profile_gaps: self_height", text)

    def test_format_text_headline_includes_height_and_education_when_present(self):
        text = search_candidates.format_text(
            [
                {
                    "id": 2,
                    "name": "Bob",
                    "score": 51,
                    "fit_score": 31,
                    "confidence_score": 22,
                    "risk_score": 2,
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "self_profile_gaps": [],
                    "risk_flags": [],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "profile": {
                        "age": 31,
                        "height": 178,
                        "city": "上海",
                        "education": "硕士",
                        "job": "产品经理",
                    },
                    "source_file": "",
                    "verified_rank": 0,
                    "activity_sort_ts": 0,
                    "profile_status_rank": 0,
                }
            ]
        )
        self.assertIn("1. Bob | score=51 | 31岁 | 178cm | 上海 | 硕士 | 产品经理", text)

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

    def test_execute_search_returns_structured_run(self):
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
            }
        ]

        args = search_candidates.build_parser().parse_args(
            [
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
            ]
        )

        with mock.patch.object(search_candidates, "load_source", return_value=fake_records), mock.patch.object(
            search_candidates, "attach_photo_previews"
        ) as mocked_attach:
            search_run = search_candidates.execute_search(args)

        self.assertEqual(search_run["records"], fake_records)
        self.assertEqual(len(search_run["results"]), 1)
        self.assertEqual(search_run["results"][0]["name"], "C1")
        self.assertIsNone(search_run["diagnostics"])
        self.assertIsNone(search_run["fallback_results"])
        self.assertEqual(len(search_run["strict_results"]), 1)
        self.assertEqual(len(search_run["compatible_results"]), 0)
        self.assertEqual(search_run["criteria"]["gender"], "女")
        self.assertEqual(search_run["criteria"]["cities"], ["无锡"])
        self.assertEqual(search_run["results"][0]["match_tier"], "strict")
        self.assertEqual(search_run["results"][0]["compatibility_flags"], [])
        self.assertIn("1. C1", search_candidates.render_search_output(search_run))
        mocked_attach.assert_called_once()

    def test_execute_search_populates_no_match_diagnostics(self):
        args = search_candidates.build_parser().parse_args(
            [
                "--source",
                "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                "--gender",
                "女",
                "--limit",
                "2",
            ]
        )

        with mock.patch.object(search_candidates, "load_source", return_value=[]), mock.patch.object(
            search_candidates, "attach_photo_previews"
        ) as mocked_attach:
            search_run = search_candidates.execute_search(args)

        self.assertEqual(search_run["records"], [])
        self.assertEqual(search_run["results"], [])
        self.assertEqual(search_run["fallback_results"], [])
        self.assertIsNotNone(search_run["diagnostics"])
        self.assertEqual(search_run["diagnostics"]["scanned_count"], 0)
        self.assertIn("No matches found.", search_candidates.render_search_output(search_run))
        mocked_attach.assert_called_once()

    def test_render_search_output_labels_compatible_match_tier(self):
        search_run = {
            "results": [
                {
                    "id": 1,
                    "name": "CompatibleA",
                    "score": 50,
                    "fit_score": 40,
                    "confidence_score": 15,
                    "risk_score": 5,
                    "match_tier": "compatible",
                    "compatibility_flags": ["对方收入预期上限未命中，但不构成硬性淘汰"],
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "self_profile_gaps": [],
                    "risk_flags": ["对方收入预期上限未命中，但不构成硬性淘汰"],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "profile": {
                        "age": 29,
                        "city": "上海",
                        "job": "产品经理",
                        "profile_status": "active",
                        "verified_level": "photo",
                    },
                }
            ],
            "strict_results": [],
            "compatible_results": [
                {
                    "id": 1,
                    "name": "CompatibleA",
                    "score": 50,
                    "fit_score": 40,
                    "confidence_score": 15,
                    "risk_score": 5,
                    "match_tier": "compatible",
                    "compatibility_flags": ["对方收入预期上限未命中，但不构成硬性淘汰"],
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "self_profile_gaps": [],
                    "risk_flags": ["对方收入预期上限未命中，但不构成硬性淘汰"],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "profile": {
                        "age": 29,
                        "city": "上海",
                        "job": "产品经理",
                        "profile_status": "active",
                        "verified_level": "photo",
                    },
                }
            ],
            "fallback_results": None,
            "diagnostics": None,
        }

        output = search_candidates.render_search_output(search_run)

        self.assertIn("Compatible matches:", output)
        self.assertIn("match_tier: compatible", output)
        self.assertIn("compatibility_flags: 对方收入预期上限未命中，但不构成硬性淘汰", output)

    def test_build_structured_search_response_splits_strict_and_compatible_results(self):
        search_run = {
            "results": [
                {
                    "id": 1,
                    "name": "StrictA",
                    "score": 60,
                    "fit_score": 50,
                    "confidence_score": 15,
                    "risk_score": 5,
                    "match_tier": "strict",
                    "compatibility_flags": [],
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "self_profile_gaps": [],
                    "risk_flags": [],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "profile": {
                        "verified_level": "photo",
                        "profile_status": "active",
                        "photo_count": 3,
                    },
                },
                {
                    "id": 2,
                    "name": "CompatibleB",
                    "score": 55,
                    "fit_score": 45,
                    "confidence_score": 15,
                    "risk_score": 5,
                    "match_tier": "compatible",
                    "compatibility_flags": ["对方收入预期上限未命中，但不构成硬性淘汰"],
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "self_profile_gaps": [],
                    "risk_flags": ["对方收入预期上限未命中，但不构成硬性淘汰"],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "profile": {
                        "verified_level": "photo",
                        "profile_status": "active",
                        "photo_count": 3,
                    },
                },
            ],
            "strict_results": [
                {
                    "id": 1,
                    "name": "StrictA",
                    "score": 60,
                    "fit_score": 50,
                    "confidence_score": 15,
                    "risk_score": 5,
                    "match_tier": "strict",
                    "compatibility_flags": [],
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "self_profile_gaps": [],
                    "risk_flags": [],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "profile": {
                        "verified_level": "photo",
                        "profile_status": "active",
                        "photo_count": 3,
                    },
                }
            ],
            "compatible_results": [
                {
                    "id": 2,
                    "name": "CompatibleB",
                    "score": 55,
                    "fit_score": 45,
                    "confidence_score": 15,
                    "risk_score": 5,
                    "match_tier": "compatible",
                    "compatibility_flags": ["对方收入预期上限未命中，但不构成硬性淘汰"],
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "self_profile_gaps": [],
                    "risk_flags": ["对方收入预期上限未命中，但不构成硬性淘汰"],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "profile": {
                        "verified_level": "photo",
                        "profile_status": "active",
                        "photo_count": 3,
                    },
                }
            ],
            "fallback_results": [],
            "diagnostics": None,
            "records_count": 2,
        }

        response = search_candidates.build_structured_search_response(search_run)

        self.assertEqual(response["pool_summary"]["strict_count"], 1)
        self.assertEqual(response["pool_summary"]["compatible_count"], 1)
        self.assertEqual(len(response["strict_results"]), 1)
        self.assertEqual(len(response["compatible_results"]), 1)

    def test_render_search_output_uses_no_strict_matches_when_fallback_exists(self):
        search_run = {
            "results": [],
            "fallback_results": [
                {
                    "id": 2,
                    "name": "FallbackB",
                    "score": 45,
                    "fit_score": 35,
                    "confidence_score": 12,
                    "risk_score": 7,
                    "match_tier": "compatible",
                    "compatibility_flags": ["对方收入预期上限未命中，但不构成硬性淘汰"],
                    "matched_on": [],
                    "reciprocal_on": [],
                    "missing_fields": [],
                    "self_profile_gaps": [],
                    "risk_flags": ["对方收入预期上限未命中，但不构成硬性淘汰"],
                    "match_evidence": [],
                    "follow_up_questions": [],
                    "profile": {
                        "age": 30,
                        "city": "上海",
                        "job": "设计师",
                        "profile_status": "active",
                        "verified_level": "photo",
                    },
                    "fallback_reason": "不符合对方城市偏好",
                }
            ],
            "diagnostics": {
                "scanned_count": 5,
                "passed_count": 0,
                "usable_count": 5,
                "top_reasons": [],
                "relax_suggestions": [],
            },
        }

        output = search_candidates.render_search_output(search_run)

        self.assertIn("No strict matches found.", output)
        self.assertIn("兼容对象", output)

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
        self.assertEqual(
            set(diagnostics.keys()),
            {"scanned_count", "passed_count", "usable_count", "top_reasons", "relax_suggestions"},
        )
        self.assertEqual(diagnostics["top_reasons"][0]["reason"], "city_mismatch")
        self.assertEqual(diagnostics["top_reasons"][0]["count"], 2)
        self.assertIn("放宽地域条件", diagnostics["relax_suggestions"][0])

    def test_build_no_match_diagnostics_detects_only_self_exclusion(self):
        records = [
            {
                "id": 999,
                "name": "SelfOnly",
                "gender": "女",
                "age": 27,
                "city": "深圳",
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "认真恋爱",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            }
        ]
        criteria = {
            "gender": "女",
            "profile_statuses": ["active"],
            "exclude_ids": set(),
            "exclude_record_refs": {(999, "mysql://root@127.0.0.1:3307/her?table=profiles#profiles")},
        }

        diagnostics = search_candidates.build_no_match_diagnostics(records, criteria)

        self.assertEqual(diagnostics["usable_count"], 0)
        self.assertEqual(
            diagnostics["top_reasons"][0]["reason"],
            "candidate_pool_empty_after_exclusions",
        )
        self.assertIn("补数据池", diagnostics["relax_suggestions"][0])

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

    def test_main_outputs_fallback_candidates_when_strict_matching_is_empty(self):
        fake_records = [
            {
                "id": 802,
                "name": "NearMatch",
                "gender": "女",
                "age": 29,
                "city": "上海",
                "preferred_cities": "上海",
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "认真恋爱",
                "last_active_at": "2099-01-01 00:00:00",
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
                "--self-city",
                "无锡",
            ],
        ), mock.patch("sys.stdout", new_callable=mock.MagicMock) as mock_stdout:
            search_candidates.main()

        output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        self.assertIn("No matches found.", output)
        self.assertIn("fallback_matches: strict 条件下没人过", output)
        self.assertIn("1. NearMatch", output)
        self.assertIn("fallback_reason: 不符合对方城市偏好", output)

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

    def test_main_with_self_id_negotiable_children_kept_with_risk(self):
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
        self.assertIn("NegotiableA", output)
        self.assertIn("对方对子女情况仅可协商", output)
        self.assertIn("确认对方是能真正接受你有孩子", output)

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
