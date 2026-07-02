from __future__ import annotations

import io
import json
import pathlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


GATEWAY_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(GATEWAY_ROOT) not in sys.path:
    sys.path.insert(0, str(GATEWAY_ROOT))

from gateway.persona_routes import rest_persona_patch


class _PersonaGatewayStub:
    def _current_actor(self, environ: dict[str, object]) -> object | None:
        return environ.get("_actor")

    def _is_auth_session_end_user(self, actor: object | None) -> bool:
        return bool(getattr(actor, "auth_source", None) == "auth_session")

    def _resolve_end_user_principal(self, environ: dict[str, object], *, require_profile: bool = False) -> object:
        return types.SimpleNamespace(profile_id=42)


class PersonaRoutesTests(unittest.TestCase):
    @patch("gateway.persona_routes._default_profile_source", return_value="mysql://root@127.0.0.1/test?table=profiles")
    @patch("gateway.persona_routes.apply_persona_patch")
    def test_persona_patch_serializes_trait_tags_as_json(
        self,
        apply_mock: MagicMock,
        _source_mock: MagicMock,
    ) -> None:
        apply_mock.return_value = {
            "applied_fields": [{"field": "preferred_traits", "applied_to_persona": True}],
            "skipped_fields": [],
        }
        gateway = _PersonaGatewayStub()
        actor = types.SimpleNamespace(actor_id="user-1", auth_source="auth_session")
        environ = {
            "_actor": actor,
            "CONTENT_LENGTH": "49",
            "wsgi.input": io.BytesIO(
                json.dumps({"patch": {"preferred_traits": ["情绪稳定", "会沟通"]}}).encode("utf-8")
            ),
        }

        status, body = rest_persona_patch(gateway, environ)

        self.assertEqual(status, 200)
        self.assertEqual(body["profile_id"], 42)
        apply_mock.assert_called_once_with(
            source="mysql://root@127.0.0.1/test?table=profiles",
            user_key="42",
            source_type="explicit",
            source_channel="profile_form",
            normalized_patch={
                "preferred_traits": json.dumps(["情绪稳定", "会沟通"], ensure_ascii=False),
            },
            evidence_text="用户手动编辑标签",
            apply_scope="persona_only",
        )

    @patch("gateway.persona_routes._default_profile_source", return_value="mysql://root@127.0.0.1/test?table=profiles")
    @patch("gateway.persona_routes.apply_persona_patch")
    def test_persona_patch_keeps_csv_for_legacy_multi_value_fields(
        self,
        apply_mock: MagicMock,
        _source_mock: MagicMock,
    ) -> None:
        apply_mock.return_value = {
            "applied_fields": [{"field": "must_have_tags", "applied_to_persona": True}],
            "skipped_fields": [],
        }
        gateway = _PersonaGatewayStub()
        actor = types.SimpleNamespace(actor_id="user-1", auth_source="auth_session")
        environ = {
            "_actor": actor,
            "CONTENT_LENGTH": "44",
            "wsgi.input": io.BytesIO(
                json.dumps({"patch": {"must_have_tags": ["真诚", "靠谱"]}}).encode("utf-8")
            ),
        }

        status, _body = rest_persona_patch(gateway, environ)

        self.assertEqual(status, 200)
        self.assertEqual(
            apply_mock.call_args.kwargs["normalized_patch"],
            {"must_have_tags": "真诚,靠谱"},
        )


if __name__ == "__main__":
    unittest.main()
