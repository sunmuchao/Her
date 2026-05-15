import pathlib
import sys
import unittest
from unittest import mock

SYSTEM_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(SYSTEM_ROOT) not in sys.path:
    sys.path.insert(0, str(SYSTEM_ROOT))

from chat_system import assistant_context  # noqa: E402


class AssistantContextTests(unittest.TestCase):
    def test_get_profile_snapshot_prefers_public_profile_view(self):
        conn = object()
        metadata = {
            "participant_a_id": "user-a",
            "participant_a_profile_id": 11,
            "participant_a_profile": {
                "id": 11,
                "name": "内部名",
                "public_display_name": "不该出现",
                "job": "内部岗位",
            },
            "participant_a_persona": {"secret": "keep"},
        }

        with (
            mock.patch.object(
                assistant_context,
                "get_conversation_by_case_and_key",
                return_value={"metadata": metadata},
            ),
            mock.patch.object(assistant_context, "list_case_conversations", return_value=[]),
            mock.patch.object(
                assistant_context,
                "load_public_profile_from_persona_source",
                return_value={
                    "id": 11,
                    "name": "公开名",
                    "city": "上海",
                    "job": "产品经理",
                    "personality": "稳定，真诚",
                    "values": "看重稳定",
                    "notes": "会照顾日常",
                },
            ) as public_mock,
        ):
            snapshot = assistant_context.get_profile_snapshot(conn, "case-1", "user-a")

        public_mock.assert_called_once_with(11)
        self.assertEqual(snapshot["profile_id"], 11)
        self.assertEqual(snapshot["profile"]["name"], "公开名")
        self.assertNotIn("public_display_name", snapshot["profile"])
        self.assertEqual(snapshot["persona"], {"secret": "keep"})


if __name__ == "__main__":
    unittest.main()
