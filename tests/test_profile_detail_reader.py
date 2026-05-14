from __future__ import annotations

import unittest
from unittest import mock

import profile_detail_reader
import partner_search.search_candidates as engine


class ProfileDetailReaderTests(unittest.TestCase):
    def test_load_profile_detail_returns_canonical_payload(self) -> None:
        fake_records = [
            {
                "id": 909,
                "name": "DetailProfile",
                "gender": "女",
                "age": 30,
                "city": "上海",
                "job": "产品经理",
                "education": "硕士",
                "relationship_goal": "认真恋爱",
                "marital_status": "未婚",
                "income_range": "30-50万/年",
                "notes": "平时作息规律；周末喜欢徒步和看展。",
                "photo_count": 3,
                "verified_level": "id",
                "profile_status": "active",
                "combined_text": "认真恋爱",
                "source_file": "mysql://root@127.0.0.1:3307/her?table=profiles#profiles",
            }
        ]

        def _attach_previews(results, _preview_count, photos_table_name=None):
            del photos_table_name
            results[0]["photo_preview"] = ["https://static.example.com/p/909/1.jpg"]

        with mock.patch.object(engine, "load_source", return_value=fake_records) as mocked_load_source, mock.patch.object(
            engine,
            "attach_photo_previews",
            side_effect=_attach_previews,
        ):
            payload = profile_detail_reader.load_profile_detail(
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                profile_id=909,
            )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["id"], 909)
        self.assertEqual(payload["name"], "DetailProfile")
        self.assertEqual(payload["profile"]["job"], "产品经理")
        self.assertEqual(payload["photo_preview"], ["https://static.example.com/p/909/1.jpg"])
        self.assertIn("平时作息规律", payload["notes_summary"])
        self.assertEqual(mocked_load_source.call_args.kwargs["include_ids_mode"], "only")


if __name__ == "__main__":
    unittest.main()
