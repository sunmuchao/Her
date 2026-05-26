import unittest
from unittest import mock

import persona_memory_sync.persona_memory_engine as module
import persona_memory_sync.persona_memory_lib as lib


class PersonaMemoryEngineTests(unittest.TestCase):
    def test_execute_upsert_persona_memory_normalizes_patch_and_resolves_profile_table(self):
        request = module.UpsertPersonaMemoryRequest(
            source=None,
            user_key="user-1",
            source_type="explicit",
            patch={"self_city": "上海"},
            sync_profile=True,
        )

        with (
            mock.patch.object(module, "normalize_patch", return_value={"self_city": "上海", "normalized": True}) as normalize_mock,
            mock.patch.object(module, "resolve_profile_table", return_value="profiles") as resolve_mock,
            mock.patch.object(
                module,
                "apply_persona_patch_impl",
                return_value={"user_key": "user-1", "synced_profile": True},
            ) as apply_mock,
        ):
            result = module.execute_upsert_persona_memory(request)

        normalize_mock.assert_called_once_with({"self_city": "上海"})
        resolve_mock.assert_called_once_with(None, None)
        apply_mock.assert_called_once_with(
            source=None,
            user_key="user-1",
            source_type="explicit",
            normalized_patch={"self_city": "上海", "normalized": True},
            persona_table=module.DEFAULT_PERSONA_TABLE,
            observation_table=module.DEFAULT_OBSERVATION_TABLE,
            profile_table="profiles",
            confidence_score=None,
            evidence_text=None,
            conversation_ref=None,
            apply_scope="persona_and_profile",
            sync_profile=True,
            source_channel=None,
        )
        self.assertEqual(result, {"user_key": "user-1", "synced_profile": True})

    def test_execute_upsert_persona_memory_can_include_normalized_patch(self):
        request = module.UpsertPersonaMemoryRequest(
            source=None,
            user_key="user-1",
            source_type="explicit",
            patch={"self_city": "上海"},
        )

        with (
            mock.patch.object(module, "normalize_patch", return_value={"self_city": "上海"}) as normalize_mock,
            mock.patch.object(module, "resolve_profile_table", return_value="profiles"),
            mock.patch.object(
                module,
                "apply_persona_patch_impl",
                return_value={"user_key": "user-1", "synced_profile": False},
            ),
        ):
            result = module.execute_upsert_persona_memory(request, include_normalized_patch=True)

        normalize_mock.assert_called_once()
        self.assertEqual(
            result,
            {
                "user_key": "user-1",
                "synced_profile": False,
                "normalized_patch": {"self_city": "上海"},
            },
        )

    def test_execute_upsert_persona_memory_can_use_observation_only_scope(self):
        request = module.UpsertPersonaMemoryRequest(
            source=None,
            user_key="user-3",
            source_type="explicit",
            patch={"self_job": "财务"},
            apply_scope="observation_only",
        )

        with (
            mock.patch.object(module, "normalize_patch", return_value={"self_job": "财务"}) as normalize_mock,
            mock.patch.object(module, "resolve_profile_table", return_value="profiles"),
            mock.patch.object(
                module,
                "apply_persona_patch_impl",
                return_value={"user_key": "user-3", "apply_scope": "observation_only", "synced_profile": False},
            ) as apply_mock,
        ):
            result = module.execute_upsert_persona_memory(request)

        normalize_mock.assert_called_once()
        apply_mock.assert_called_once_with(
            source=None,
            user_key="user-3",
            source_type="explicit",
            normalized_patch={"self_job": "财务"},
            persona_table=module.DEFAULT_PERSONA_TABLE,
            observation_table=module.DEFAULT_OBSERVATION_TABLE,
            profile_table="profiles",
            confidence_score=None,
            evidence_text=None,
            conversation_ref=None,
            apply_scope="observation_only",
            sync_profile=False,
            source_channel=None,
        )
        self.assertEqual(result["apply_scope"], "observation_only")

    def test_execute_sync_persona_profile_delegates_to_library(self):
        request = module.SyncPersonaProfileRequest(
            source=None,
            user_key="user-2",
        )

        with (
            mock.patch.object(module, "resolve_profile_table", return_value="profiles") as resolve_mock,
            mock.patch.object(
                module,
                "sync_persona_profile_impl",
                return_value={"user_key": "user-2", "profile_id": 99},
            ) as sync_mock,
        ):
            result = module.execute_sync_persona_profile(request)

        resolve_mock.assert_called_once_with(None, None)
        sync_mock.assert_called_once_with(
            source=None,
            persona_table=module.DEFAULT_PERSONA_TABLE,
            profile_table="profiles",
            user_key="user-2",
            profile_id=None,
        )
        self.assertEqual(result, {"user_key": "user-2", "profile_id": 99})

    def test_execute_render_public_profile_delegates_to_library(self):
        request = module.RenderPublicProfileRequest(
            source=None,
            user_key="user-3",
            write_profile=True,
        )

        with (
            mock.patch.object(module, "resolve_profile_table", return_value="profiles") as resolve_mock,
            mock.patch.object(
                module,
                "render_public_profile_result_impl",
                return_value={"user_key": "user-3", "public_personality": "现居上海"},
            ) as render_mock,
        ):
            result = module.execute_render_public_profile(request)

        resolve_mock.assert_called_once_with(None, None)
        render_mock.assert_called_once_with(
            source=None,
            persona_table=module.DEFAULT_PERSONA_TABLE,
            profile_table="profiles",
            user_key="user-3",
            profile_id=None,
            write_profile=True,
        )
        self.assertEqual(result, {"user_key": "user-3", "public_personality": "现居上海"})

    def test_render_public_profile_result_reads_public_view_when_not_writing(self):
        fake_conn = mock.MagicMock()
        fake_cursor = mock.MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
        fake_conn.commit = mock.Mock()
        fake_conn.close = mock.Mock()

        with (
            mock.patch.object(lib, "mysql_connect", return_value=fake_conn),
            mock.patch.object(lib, "fetch_persona", return_value={"user_key": "user-1", "profile_id": 7}),
            mock.patch.object(lib, "fetch_public_profile", return_value={"id": 7, "name": "公开名", "job": "产品经理"}) as fetch_public_mock,
            mock.patch.object(lib, "fetch_profile") as fetch_profile_mock,
            mock.patch.object(lib, "build_profile_payload") as build_payload_mock,
            mock.patch.object(lib, "write_public_profile_fields") as write_public_mock,
        ):
            result = lib.render_public_profile_result(
                source=None,
                profile_table="profiles",
                user_key="user-1",
                write_profile=False,
            )

        self.assertEqual(result["user_key"], "user-1")
        self.assertEqual(result["profile_id"], 7)
        self.assertEqual(result["name"], "公开名")
        fetch_public_mock.assert_called_once_with(fake_cursor, lib.DEFAULT_PUBLIC_VIEW, 7)
        fetch_profile_mock.assert_not_called()
        build_payload_mock.assert_not_called()
        write_public_mock.assert_not_called()

    def test_render_public_profile_result_writes_then_reads_public_view(self):
        fake_conn = mock.MagicMock()
        fake_cursor = mock.MagicMock()
        fake_conn.cursor.return_value.__enter__.return_value = fake_cursor
        fake_conn.commit = mock.Mock()
        fake_conn.close = mock.Mock()

        with (
            mock.patch.object(lib, "mysql_connect", return_value=fake_conn),
            mock.patch.object(lib, "fetch_persona", return_value={"user_key": "user-2", "profile_id": 8}),
            mock.patch.object(lib, "fetch_profile", return_value={"id": 8, "name": "旧名"}) as fetch_profile_mock,
            mock.patch.object(lib, "build_profile_payload", return_value={"name": "新名"}) as build_payload_mock,
            mock.patch.object(lib, "write_public_profile_fields") as write_public_mock,
            mock.patch.object(lib, "fetch_public_profile", return_value={"id": 8, "name": "公开名", "job": "医生"}) as fetch_public_mock,
        ):
            result = lib.render_public_profile_result(
                source=None,
                profile_table="profiles",
                user_key="user-2",
                write_profile=True,
            )

        self.assertEqual(result["user_key"], "user-2")
        self.assertEqual(result["profile_id"], 8)
        self.assertEqual(result["name"], "公开名")
        fetch_profile_mock.assert_called_once_with(fake_cursor, "profiles", 8)
        build_payload_mock.assert_called_once()
        write_public_mock.assert_called_once()
        fetch_public_mock.assert_called_once_with(fake_cursor, lib.DEFAULT_PUBLIC_VIEW, 8)


if __name__ == "__main__":
    unittest.main()
