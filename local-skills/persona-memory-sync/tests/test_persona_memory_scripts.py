import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest
from unittest import mock


SCRIPT_DIR = pathlib.Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


def load_script_module(name: str):
    path = SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PersonaMemoryScriptTests(unittest.TestCase):
    def test_upsert_persona_memory_main_delegates_to_engine_and_prints_json(self):
        module = load_script_module("upsert_persona_memory")
        stdout = io.StringIO()

        with (
            mock.patch.object(module, "parse_patch_json", return_value={}),
            mock.patch.object(
                module,
                "execute_upsert_persona_memory",
                return_value={"user_key": "user-1", "synced_profile": True},
            ) as execute_mock,
            mock.patch.object(
                sys,
                "argv",
                [
                    "upsert_persona_memory.py",
                    "--user-key",
                    "user-1",
                    "--source-type",
                    "explicit",
                    "--profile-id",
                    "42",
                    "--display-name",
                    "测试用户",
                    "--sync-profile",
                ],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            module.main()

        execute_mock.assert_called_once()
        self.assertEqual(
            execute_mock.call_args.args[0],
            module.UpsertPersonaMemoryRequest(
                source=None,
                user_key="user-1",
                source_type="explicit",
                patch={"profile_id": 42, "display_name": "测试用户"},
                persona_table=module.DEFAULT_PERSONA_TABLE,
                observation_table=module.DEFAULT_OBSERVATION_TABLE,
                profile_table=None,
                confidence_score=None,
                evidence_text=None,
                conversation_ref=None,
                sync_profile=True,
            ),
        )
        self.assertEqual(
            stdout.getvalue().strip(),
            '{\n  "user_key": "user-1",\n  "synced_profile": true\n}',
        )

    def test_sync_persona_to_profile_main_delegates_to_engine_and_prints_json(self):
        module = load_script_module("sync_persona_to_profile")
        stdout = io.StringIO()

        with (
            mock.patch.object(
                module,
                "execute_sync_persona_profile",
                return_value={"user_key": "user-2", "profile_id": 88},
            ) as execute_mock,
            mock.patch.object(
                sys,
                "argv",
                [
                    "sync_persona_to_profile.py",
                    "--user-key",
                    "user-2",
                ],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            module.main()

        execute_mock.assert_called_once_with(
            module.SyncPersonaProfileRequest(
                source=None,
                user_key="user-2",
                profile_id=None,
                persona_table=module.DEFAULT_PERSONA_TABLE,
                profile_table=None,
            )
        )
        self.assertEqual(
            stdout.getvalue().strip(),
            '{\n  "user_key": "user-2",\n  "profile_id": 88\n}',
        )

    def test_sync_persona_to_profile_main_preserves_cli_exit_message(self):
        module = load_script_module("sync_persona_to_profile")

        with (
            mock.patch.object(module, "execute_sync_persona_profile", side_effect=ValueError("Persona not found.")),
            mock.patch.object(sys, "argv", ["sync_persona_to_profile.py", "--user-key", "user-2"]),
        ):
            with self.assertRaises(SystemExit) as exc:
                module.main()

        self.assertEqual(str(exc.exception), "Persona not found.")

    def test_render_public_profile_main_delegates_to_engine_and_prints_json(self):
        module = load_script_module("render_public_profile")
        stdout = io.StringIO()

        with (
            mock.patch.object(
                module,
                "execute_render_public_profile",
                return_value={"user_key": "user-3", "public_personality": "现居上海"},
            ) as execute_mock,
            mock.patch.object(
                sys,
                "argv",
                [
                    "render_public_profile.py",
                    "--user-key",
                    "user-3",
                    "--write-profile",
                ],
            ),
            contextlib.redirect_stdout(stdout),
        ):
            module.main()

        execute_mock.assert_called_once_with(
            module.RenderPublicProfileRequest(
                source=None,
                user_key="user-3",
                profile_id=None,
                persona_table=module.DEFAULT_PERSONA_TABLE,
                profile_table=None,
                write_profile=True,
            )
        )
        self.assertEqual(
            stdout.getvalue().strip(),
            '{\n  "user_key": "user-3",\n  "public_personality": "现居上海"\n}',
        )

    def test_render_public_profile_main_preserves_cli_exit_message(self):
        module = load_script_module("render_public_profile")

        with (
            mock.patch.object(module, "execute_render_public_profile", side_effect=ValueError("Persona not found.")),
            mock.patch.object(sys, "argv", ["render_public_profile.py", "--user-key", "user-3"]),
        ):
            with self.assertRaises(SystemExit) as exc:
                module.main()

        self.assertEqual(str(exc.exception), "Persona not found.")


if __name__ == "__main__":
    unittest.main()
