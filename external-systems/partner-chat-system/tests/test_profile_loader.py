import pathlib
import sys
import unittest
from unittest.mock import patch

_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from chat_system import profile_loader as profile_loader_mod
from chat_system.profile_loader import (
    _profile_lookup_columns,
    fetch_profile_for_participant,
    parse_profile_id_candidate,
    profile_row_to_brief,
    roleplay_participant_id,
)


class _FakeProfileConn:
    def __init__(self):
        self._sql = ""
        self._params = ()

    def execute(self, sql, params=()):
        self._sql = str(sql)
        self._params = params
        return self

    def fetchone(self):
        if "WHERE id = ?" in self._sql and self._params == (30010,):
            return {"id": 30010, "job": "工程师"}
        if "WHERE user_key = ?" in self._sql and self._params == ("alice-user",):
            return {"id": 42, "user_key": "alice-user", "job": "产品经理"}
        return None

    def fetchall(self):
        if "SHOW COLUMNS FROM profiles" in self._sql:
            return [
                {"Field": "id"},
                {"Field": "user_key"},
                {"Field": "job"},
            ]
        return []

    def close(self):
        return None


class ProfileLoaderTests(unittest.TestCase):
    def setUp(self):
        _profile_lookup_columns.cache_clear()

    def test_profile_row_to_brief_skips_empty(self):
        s = profile_row_to_brief({"id": 42, "name": "测", "age": 29, "city": "无锡"})
        self.assertIn("测", s)
        self.assertIn("29", s)
        self.assertIn("无锡", s)

    def test_roleplay_participant_id(self):
        self.assertEqual(roleplay_participant_id(30010), "profile-30010")

    def test_parse_profile_id_candidate_supports_numeric_participant_ids(self):
        self.assertEqual(parse_profile_id_candidate("profile-30010"), 30010)
        self.assertEqual(parse_profile_id_candidate("30010"), 30010)
        self.assertIsNone(parse_profile_id_candidate("alice"))

    def test_fetch_profile_for_participant_supports_numeric_and_user_key_lookup(self):
        with patch.object(profile_loader_mod, "connect_mysql_repo_db", return_value=_FakeProfileConn()):
            by_id = fetch_profile_for_participant("mysql://root@127.0.0.1:3307/her", "30010")
            by_user_key = fetch_profile_for_participant(
                "mysql://root@127.0.0.1:3307/her",
                "alice",
                user_key_hint="alice-user",
            )

        self.assertIsNotNone(by_id)
        self.assertEqual(by_id["job"], "工程师")
        self.assertIsNotNone(by_user_key)
        self.assertEqual(by_user_key["user_key"], "alice-user")


if __name__ == "__main__":
    unittest.main()
