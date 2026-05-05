import pathlib
import sys
import unittest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from chat_system.profile_loader import profile_row_to_brief, roleplay_participant_id


class ProfileLoaderTests(unittest.TestCase):
    def test_profile_row_to_brief_skips_empty(self):
        s = profile_row_to_brief({"id": 42, "name": "测", "age": 29, "city": "无锡"})
        self.assertIn("测", s)
        self.assertIn("29", s)
        self.assertIn("无锡", s)

    def test_roleplay_participant_id(self):
        self.assertEqual(roleplay_participant_id(30010), "profile-30010")


if __name__ == "__main__":
    unittest.main()
