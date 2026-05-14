import json
import importlib.util
import pathlib
import sys
import unittest
from datetime import datetime
from unittest import mock


SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from partner_search import (  # noqa: E402
    SearchRequest,
    load_self_profile,
    normalize_persona_profile,
    search,
    search_profiles,
)
import partner_search.search_candidates as engine  # noqa: E402


class PartnerSearchApiTests(unittest.TestCase):
    def test_search_profiles_returns_structured_results(self):
        fake_records = [
            {
                "id": 901,
                "name": "API1",
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

        with mock.patch.object(engine, "load_source", return_value=fake_records), mock.patch.object(
            engine, "attach_photo_previews"
        ) as mocked_attach:
            response = search_profiles(
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                criteria={
                    "gender": "女",
                    "city": "无锡",
                    "must_have": ["情绪稳定"],
                },
                limit=2,
            )

        self.assertTrue(response["has_match"])
        self.assertEqual(response["result_count"], 1)
        self.assertEqual(response["pool_summary"]["scanned_count"], 1)
        self.assertEqual(response["results"][0]["name"], "API1")
        self.assertEqual(response["results"][0]["verified_level"], "id")
        self.assertEqual(response["results"][0]["verified_label"], "实名认证")
        self.assertIn("verification_items", response["results"][0])
        self.assertEqual(response["results"][0]["verification_items"][0]["key"], "photo")
        self.assertIn("trust_summary", response["results"][0])
        self.assertIn("已实名认证", response["results"][0]["trust_summary"]["headline"])
        self.assertNotIn("source_file", response["results"][0])
        self.assertIn("matched_on", response["results"][0])
        mocked_attach.assert_called_once()

    def test_search_response_to_json_is_json_safe_and_can_include_text(self):
        fake_records = [
            {
                "id": 902,
                "name": "JSONSafe",
                "gender": "女",
                "age": 28,
                "city": "上海",
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "认真恋爱",
                "updated_at": datetime(2099, 1, 1, 0, 0, 0),
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            }
        ]

        with mock.patch.object(engine, "load_source", return_value=fake_records), mock.patch.object(
            engine, "attach_photo_previews"
        ):
            response = search(
                SearchRequest(
                    source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                    criteria={"gender": "女", "city": "上海"},
                    include_source=True,
                )
            )

        payload = json.loads(response.to_json(include_text=True))
        self.assertEqual(payload["results"][0]["name"], "JSONSafe")
        self.assertEqual(payload["results"][0]["profile"]["updated_at"], "2099-01-01 00:00:00")
        self.assertEqual(payload["results"][0]["verified_label"], "照片认证")
        self.assertIn("source", payload["results"][0])
        self.assertIn("text", payload)
        self.assertIn("1. JSONSafe", payload["text"])
        self.assertIn("trust:", payload["text"])

    def test_search_accepts_plain_mapping_request(self):
        fake_records = [
            {
                "id": 903,
                "name": "MappingRequest",
                "gender": "女",
                "age": 29,
                "city": "苏州",
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "生活规律",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            }
        ]

        with mock.patch.object(engine, "load_source", return_value=fake_records), mock.patch.object(
            engine, "attach_photo_previews"
        ):
            response = search(
                {
                    "source": "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                    "criteria": {"gender": "女", "cities": ["苏州"]},
                    "limit": 3,
                }
            )

        self.assertEqual(response.to_dict()["results"][0]["name"], "MappingRequest")

    def test_search_profiles_surfaces_self_reported_vs_verified_trust_items(self):
        fake_records = [
            {
                "id": 907,
                "name": "TrustSignals",
                "gender": "女",
                "age": 30,
                "city": "苏州",
                "education": "硕士",
                "job": "产品经理",
                "income_range": "40-60万/年",
                "marital_status": "未婚",
                "has_children": 0,
                "relationship_goal": "结婚导向",
                "profile_status": "active",
                "verified_level": "id",
                "photo_count": 6,
                "combined_text": "认真恋爱 情绪稳定",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            }
        ]

        with mock.patch.object(engine, "load_source", return_value=fake_records), mock.patch.object(
            engine, "attach_photo_previews"
        ):
            response = search_profiles(
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                criteria={"gender": "女", "cities": ["苏州"]},
            )

        result = response["results"][0]
        trust_items = {item["key"]: item for item in result["verification_items"]}
        self.assertEqual(trust_items["photo"]["status"], "verified")
        self.assertIn("6张", trust_items["photo"]["summary"])
        self.assertEqual(trust_items["identity"]["status"], "verified")
        self.assertEqual(trust_items["education"]["status"], "self_reported")
        self.assertEqual(trust_items["job"]["status"], "self_reported")
        self.assertEqual(trust_items["income"]["status"], "self_reported")
        self.assertIn("学历、职业、收入", result["trust_summary"]["headline"])

    def test_search_profiles_include_photo_verification_and_caution_actions(self):
        fake_records = [
            {
                "id": 908,
                "name": "PhotoTrust",
                "gender": "女",
                "age": 31,
                "city": "上海",
                "education": "本科",
                "education_verification_status": "verified",
                "job": "行政助理",
                "job_verification_status": "needs_review",
                "income_range": "80-100万/年",
                "income_verification_status": "self_reported",
                "profile_review_status": "needs_review",
                "job_change_count_30d": 2,
                "photo_count": 4,
                "photo_verification_level": "live_video_verified",
                "profile_status": "active",
                "verified_level": "id",
                "combined_text": "认真恋爱",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            }
        ]

        with mock.patch.object(engine, "load_source", return_value=fake_records), mock.patch.object(
            engine, "attach_photo_previews"
        ):
            response = search_profiles(
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                criteria={"gender": "女", "cities": ["上海"]},
            )

        result = response["results"][0]
        trust_items = {item["key"]: item for item in result["verification_items"]}
        self.assertEqual(result["photo_verification_level"], "live_video_verified")
        self.assertEqual(result["photo_verification_label"], "活体自拍视频认证")
        self.assertEqual(trust_items["photo"]["status"], "verified")
        self.assertEqual(trust_items["education"]["status"], "verified")
        self.assertEqual(trust_items["job"]["status"], "needs_review")
        self.assertIn("待复核", result["trust_summary"]["headline"])
        self.assertIn("资料填写为主", result["trust_summary"]["headline"])
        self.assertIn("资料存在待复核或不一致信号", result["risk_flags"])
        self.assertGreaterEqual(len(result["caution_items"]), 1)
        self.assertGreaterEqual(len(result["trust_actions"]), 1)

    def test_search_profiles_surface_expired_and_disputed_field_states(self):
        fake_records = [
            {
                "id": 9081,
                "name": "FieldLifecycle",
                "gender": "女",
                "age": 32,
                "city": "上海",
                "education": "硕士",
                "education_verification_status": "expired",
                "job": "产品经理",
                "job_verification_status": "disputed",
                "income_range": "50-80万/年",
                "income_verification_status": "verified",
                "photo_count": 3,
                "photo_verification_level": "human_verified",
                "profile_status": "active",
                "verified_level": "id",
                "combined_text": "认真恋爱",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            }
        ]

        with mock.patch.object(engine, "load_source", return_value=fake_records), mock.patch.object(
            engine, "attach_photo_previews"
        ):
            response = search_profiles(
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                criteria={"gender": "女", "cities": ["上海"]},
            )

        result = response["results"][0]
        trust_items = {item["key"]: item for item in result["verification_items"]}
        self.assertEqual(trust_items["education"]["status"], "needs_review")
        self.assertEqual(trust_items["education"]["raw_status"], "expired")
        self.assertIn("认证已过期", trust_items["education"]["summary"])
        self.assertEqual(trust_items["job"]["status"], "needs_review")
        self.assertEqual(trust_items["job"]["raw_status"], "disputed")
        self.assertIn("争议", trust_items["job"]["summary"])
        self.assertTrue(any("认证已过期" in item for item in result["caution_items"]))
        self.assertTrue(any("争议复核" in item for item in result["caution_items"]))

    def test_search_profiles_can_require_min_photo_verification_level(self):
        fake_records = [
            {
                "id": 909,
                "name": "UploadedOnly",
                "gender": "女",
                "age": 29,
                "city": "上海",
                "photo_count": 4,
                "photo_verification_level": "uploaded",
                "profile_status": "active",
                "verified_level": "id",
                "combined_text": "认真恋爱",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
            {
                "id": 910,
                "name": "VideoVerified",
                "gender": "女",
                "age": 30,
                "city": "上海",
                "photo_count": 5,
                "photo_verification_level": "live_video_verified",
                "profile_status": "active",
                "verified_level": "id",
                "combined_text": "认真恋爱",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
        ]

        with mock.patch.object(engine, "load_source", return_value=fake_records), mock.patch.object(
            engine, "attach_photo_previews"
        ):
            response = search_profiles(
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                criteria={
                    "gender": "女",
                    "cities": ["上海"],
                    "photo_verification_level_min": "live_video_verified",
                },
            )

        self.assertEqual(response["result_count"], 1)
        self.assertEqual(response["results"][0]["name"], "VideoVerified")

    def test_load_self_profile_uses_public_api_boundary_and_returns_json_safe_profile(self):
        with mock.patch.object(
            engine,
            "collect_source_records_for_request",
            return_value=[{"id": 90001}],
        ) as mocked_collect, mock.patch.object(
            engine,
            "build_self_profile",
            return_value={
                "id": 90001,
                "city": "无锡",
                "last_active_at": datetime(2099, 1, 1, 8, 0, 0),
            },
        ) as mocked_build:
            profile = load_self_profile(
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                self_id=90001,
                table_name="profiles",
            )

        mocked_collect.assert_called_once_with(
            ["mysql://user:pass@127.0.0.1:3306/her?table=profiles"],
            table_name="profiles",
            criteria={},
            self_id=90001,
        )
        mocked_build.assert_called_once()
        self.assertEqual(profile["id"], 90001)
        self.assertEqual(profile["last_active_at"], "2099-01-01 08:00:00")

    def test_normalize_persona_profile_maps_synced_profile_into_saved_search_shape(self):
        normalized = normalize_persona_profile(
            {
                "gender": "男",
                "age": 28,
                "city": "无锡",
                "last_active_at": datetime(2099, 1, 1, 8, 0, 0),
                "preferred_age_min": 27,
                "preferred_age_max": 32,
                "accept_marital_status": "未婚,离异无孩",
                "matcher_preferences": {
                    "target_gender": "女",
                    "target_cities": ["苏州", "无锡"],
                    "must_have_tags": ["情绪稳定", "愿意沟通"],
                },
                "matcher_risks": {
                    "must_not_have_tags": ["抽烟"],
                },
            },
            fallback_profile={"target_marital_statuses": ["旧值"]},
        )

        self.assertEqual(normalized["self_gender"], "男")
        self.assertEqual(normalized["target_gender"], "女")
        self.assertEqual(normalized["target_cities"], ["苏州", "无锡"])
        self.assertEqual(normalized["target_age_min"], 27)
        self.assertEqual(normalized["target_marital_statuses"], "未婚,离异无孩")
        self.assertEqual(normalized["must_have_tags"], ["情绪稳定", "愿意沟通"])
        self.assertEqual(normalized["must_not_have_tags"], ["抽烟"])
        self.assertEqual(normalized["last_active_at"], "2099-01-01 08:00:00")

    def test_main_outputs_json_when_requested(self):
        fake_records = [
            {
                "id": 904,
                "name": "CliJson",
                "gender": "女",
                "age": 28,
                "city": "无锡",
                "profile_status": "active",
                "verified_level": "photo",
                "combined_text": "认真恋爱",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            }
        ]

        with mock.patch.object(engine, "load_source", return_value=fake_records), mock.patch.object(
            engine, "attach_photo_previews"
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
                "--output-format",
                "json",
            ],
        ), mock.patch("sys.stdout", new_callable=mock.MagicMock) as mock_stdout:
            engine.main()

        output = "".join(call.args[0] for call in mock_stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertTrue(payload["has_match"])
        self.assertEqual(payload["results"][0]["name"], "CliJson")

    def test_persona_style_request_prefers_better_local_match(self):
        fake_records = [
            {
                "id": 905,
                "name": "LocalSteady",
                "gender": "女",
                "age": 28,
                "city": "无锡",
                "relationship_goal": "认真恋爱",
                "smoking": "否",
                "profile_status": "active",
                "verified_level": "id",
                "photo_count": 5,
                "combined_text": "情绪稳定 消费观正常 生活规律",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
            {
                "id": 906,
                "name": "RemoteLoose",
                "gender": "女",
                "age": 29,
                "city": "上海",
                "relationship_goal": "先接触看看",
                "smoking": "偶尔",
                "profile_status": "active",
                "verified_level": "basic",
                "photo_count": 1,
                "combined_text": "先接触看看",
                "last_active_at": "2099-01-01 00:00:00",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            },
        ]

        with mock.patch.object(engine, "load_source", return_value=fake_records), mock.patch.object(
            engine, "attach_photo_previews"
        ):
            response = search_profiles(
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                criteria={
                    "gender": "女",
                    "city": "无锡",
                    "relationship_goal": ["认真恋爱", "结婚导向"],
                    "must_have": ["情绪稳定"],
                    "prefer": ["消费观正常", "生活规律"],
                    "smoking": "否",
                    "verified_level_min": "photo",
                    "photo_count_min": 3,
                },
            )

        self.assertEqual(response["results"][0]["name"], "LocalSteady")

    def test_python_api_integration_example_builds_outer_system_payload(self):
        example_path = SKILL_ROOT / "examples" / "python_api_integration.py"
        spec = importlib.util.spec_from_file_location("python_api_integration", example_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        saved_search = module.build_demo_saved_search()
        response = {
            "result_count": 2,
            "results": [{"id": 1, "name": "A"}, {"id": 2, "name": "B"}],
        }

        payload = module.build_recommendation_batch(saved_search, response)

        self.assertEqual(payload["subscription_id"], "saved-search-1001")
        self.assertEqual(payload["requester_id"], 70001)
        self.assertEqual(payload["top_candidate_ids"], [1, 2])
        self.assertEqual(payload["search_response"], response)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
