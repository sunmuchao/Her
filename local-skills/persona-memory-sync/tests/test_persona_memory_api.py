import pathlib
import sys
import unittest
import importlib.util
from unittest import mock


SKILL_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from persona_memory_sync import (  # noqa: E402
    DEFAULT_OBSERVATION_TABLE,
    DEFAULT_PERSONA_TABLE,
    RenderPublicProfileRequest,
    SyncPersonaProfileRequest,
    UpsertPersonaMemoryRequest,
    render_public_profile,
    sync_persona_profile,
    upsert_persona_memory,
)
from persona_memory_sync import api as persona_memory_api  # noqa: E402


class PersonaMemoryApiTests(unittest.TestCase):
    def test_upsert_persona_memory_accepts_mapping_request(self):
        with mock.patch.object(
            persona_memory_api.engine,
            "execute_upsert_persona_memory",
            return_value={"user_key": "user-1", "synced_profile": True},
        ) as execute_mock:
            result = upsert_persona_memory(
                {
                    "source": "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                    "user_key": "user-1",
                    "source_type": "explicit",
                    "patch": {"self_city": "上海"},
                    "sync_profile": True,
                }
            )

        execute_mock.assert_called_once_with(
            UpsertPersonaMemoryRequest(
                source="mysql://user:pass@127.0.0.1:3306/her?table=profiles",
                user_key="user-1",
                source_type="explicit",
                patch={"self_city": "上海"},
                persona_table=DEFAULT_PERSONA_TABLE,
                observation_table=DEFAULT_OBSERVATION_TABLE,
                profile_table=None,
                confidence_score=None,
                evidence_text=None,
                conversation_ref=None,
                basis=None,
                apply_scope=None,
                sync_profile=True,
            ),
            include_normalized_patch=False,
        )
        self.assertEqual(result["user_key"], "user-1")

    def test_upsert_persona_memory_accepts_request_object_and_include_normalized_patch(self):
        request = UpsertPersonaMemoryRequest(
            source=None,
            user_key="user-2",
            source_type="strong_inference",
            patch={"preferred_traits": "沟通顺畅"},
        )

        with mock.patch.object(
            persona_memory_api.engine,
            "execute_upsert_persona_memory",
            return_value={"user_key": "user-2", "normalized_patch": {"preferred_traits": "沟通顺畅"}},
        ) as execute_mock:
            result = upsert_persona_memory(request, include_normalized_patch=True)

        execute_mock.assert_called_once_with(
            request,
            include_normalized_patch=True,
        )
        self.assertEqual(result["user_key"], "user-2")

    def test_sync_persona_profile_accepts_mapping_request(self):
        with mock.patch.object(
            persona_memory_api.engine,
            "execute_sync_persona_profile",
            return_value={"user_key": "user-3", "profile_id": 88},
        ) as execute_mock:
            result = sync_persona_profile(
                {
                    "source": None,
                    "user_key": "user-3",
                    "profile_table": "profiles_shadow",
                }
            )

        execute_mock.assert_called_once_with(
            SyncPersonaProfileRequest(
                source=None,
                user_key="user-3",
                profile_id=None,
                persona_table=DEFAULT_PERSONA_TABLE,
                profile_table="profiles_shadow",
            )
        )
        self.assertEqual(result["profile_id"], 88)

    def test_render_public_profile_accepts_mapping_request(self):
        with mock.patch.object(
            persona_memory_api.engine,
            "execute_render_public_profile",
            return_value={"user_key": "user-4", "public_personality": "现居上海"},
        ) as execute_mock:
            result = render_public_profile(
                {
                    "source": None,
                    "profile_id": 42,
                    "write_profile": True,
                }
            )

        execute_mock.assert_called_once_with(
            RenderPublicProfileRequest(
                source=None,
                user_key=None,
                profile_id=42,
                persona_table=DEFAULT_PERSONA_TABLE,
                profile_table=None,
                write_profile=True,
            )
        )
        self.assertEqual(result["user_key"], "user-4")

    def test_python_api_integration_example_builds_outer_system_payload(self):
        example_path = SKILL_ROOT / "examples" / "python_api_integration.py"
        spec = importlib.util.spec_from_file_location("persona_memory_python_api_integration", example_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        memory_update = module.build_demo_memory_update()
        upsert_result = {"user_key": "demo-user", "synced_profile": True}
        public_profile = {"public_personality": "现居上海，认真了解"}

        payload = module.build_sync_batch(memory_update, upsert_result, public_profile)

        self.assertEqual(payload["event_id"], "memory-update-1001")
        self.assertEqual(payload["user_key"], "demo-user")
        self.assertEqual(payload["upsert_result"], upsert_result)
        self.assertEqual(payload["public_profile"], public_profile)


if __name__ == "__main__":
    unittest.main()
