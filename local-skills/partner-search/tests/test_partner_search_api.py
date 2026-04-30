import json
import pathlib
import sys
import unittest
from datetime import datetime
from unittest import mock


SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from partner_search import SearchRequest, search, search_profiles  # noqa: E402
from scripts import search_candidates as engine  # noqa: E402


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
        self.assertIn("source", payload["results"][0])
        self.assertIn("text", payload)
        self.assertIn("1. JSONSafe", payload["text"])

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


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
