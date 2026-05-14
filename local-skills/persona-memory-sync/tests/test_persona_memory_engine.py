import unittest
from unittest import mock

import persona_memory_sync.persona_memory_engine as module


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


if __name__ == "__main__":
    unittest.main()
