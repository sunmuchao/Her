from __future__ import annotations

import json
import sys
import types
import unittest
from datetime import datetime
from unittest import mock

import profile_service.api as profile_service_api
from persona_memory_sync import persona_memory_lib


class _FakeResult:
    def __init__(self, *, rowcount: int = 0, fetchone_result=None, fetchall_result=None) -> None:
        self.rowcount = rowcount
        self._fetchone_result = fetchone_result
        self._fetchall_result = list(fetchall_result or [])

    def fetchone(self):
        return self._fetchone_result

    def fetchall(self):
        return list(self._fetchall_result)


class _FakeConnection:
    def __init__(self, *, rowcount: int = 1, select_exists: bool = True, responses=None) -> None:
        self.driver_connection = object()
        self.config = {"database": "her"}
        self.rowcount = rowcount
        self.select_exists = select_exists
        self.responses = list(responses or [])
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.committed = False
        self.closed = False

    def execute(self, sql: str, params: tuple[object, ...] = ()):
        self.calls.append((sql, params))
        if self.responses:
            return self.responses.pop(0)
        if sql.lstrip().startswith("SELECT 1"):
            return _FakeResult(fetchone_result=(1,) if self.select_exists else None)
        return _FakeResult(rowcount=self.rowcount)

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


class ProfileServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        profile_service_api._profile_metadata_cache.clear()
        self._release_patcher = mock.patch.object(
            profile_service_api,
            "release_profile_connection",
            side_effect=lambda _source_dsn, conn: conn.close(),
        )
        self._release_patcher.start()

    def tearDown(self) -> None:
        self._release_patcher.stop()

    def test_persona_profile_sync_blocks_profile_fact_fields(self):
        payload = persona_memory_lib.build_profile_payload(
            {
                "display_name": "Alice",
                "self_age": 31,
                "self_city": "上海",
                "self_height": 168,
                "self_marital_status": "未婚",
                "self_has_children": 0,
                "target_age_min": 29,
                "target_age_max": 35,
                "target_accept_long_distance": "不接受",
                "preferred_traits": ["成熟稳重"],
            },
            existing_profile={},
            include_null_persona_fields=set(),
            profile_sync_mode="public_only",
        )

        self.assertNotIn("age", payload)
        self.assertNotIn("city", payload)
        self.assertNotIn("height", payload)
        self.assertNotIn("marital_status", payload)
        self.assertNotIn("has_children", payload)
        self.assertNotIn("income_range", payload)
        self.assertNotIn("preferred_age_min", payload)
        self.assertNotIn("preferred_age_max", payload)
        self.assertNotIn("accept_long_distance", payload)

    def test_split_multi_value_supports_json_array_strings(self):
        self.assertEqual(
            persona_memory_lib.items_from_csv('["情绪稳定", "会沟通"]'),
            ["情绪稳定", "会沟通"],
        )

    def test_normalize_patch_serializes_json_trait_fields(self):
        normalized = persona_memory_lib.normalize_patch(
            {
                "preferred_traits": ["情绪稳定", "会沟通"],
                "target_cities": ["无锡", "苏州"],
            }
        )

        self.assertEqual(
            normalized["preferred_traits"],
            json.dumps(["情绪稳定", "会沟通"], ensure_ascii=False),
        )
        self.assertEqual(normalized["target_cities"], "无锡,苏州")

    def test_merge_persona_treats_json_trait_lists_as_stable(self):
        merged, field_results = persona_memory_lib.merge_persona(
            {"preferred_traits": json.dumps(["情绪稳定", "会沟通"], ensure_ascii=False)},
            {"preferred_traits": ["情绪稳定", "会沟通"]},
            "profile_form",
        )

        self.assertEqual(
            merged["preferred_traits"],
            json.dumps(["情绪稳定", "会沟通"], ensure_ascii=False),
        )
        self.assertFalse(field_results[0]["applied_to_persona"])
        self.assertEqual(field_results[0]["note"], "no_change")

    def test_persona_profile_sync_legacy_mode_still_maps_preferences(self):
        payload = persona_memory_lib.build_profile_payload(
            {
                "target_age_min": 29,
                "target_age_max": 35,
                "target_accept_long_distance": "不接受",
            },
            existing_profile={},
            profile_sync_mode="legacy",
        )
        self.assertEqual(payload.get("preferred_age_min"), 29)
        self.assertEqual(payload.get("preferred_age_max"), 35)
        self.assertEqual(payload.get("accept_long_distance"), "不接受")

    def test_persona_profile_sync_columns_skip_blocked_profile_facts(self):
        columns = persona_memory_lib.profile_columns_for_persona_patch(
            {
                "self_city": "上海",
                "self_age": 31,
                "target_age_min": 29,
                "target_age_max": 35,
                "target_location_semantics": "接受同城，长期异地不考虑",
            }
        )

        self.assertNotIn("city", columns)
        self.assertNotIn("age", columns)
        self.assertIn("preferred_age_min", columns)
        self.assertIn("preferred_age_max", columns)
        self.assertIn("location_preference_semantics", columns)

    def test_apply_persona_patch_delegates_to_persona_memory_sync(self):
        request = {"user_key": "user-1", "source_type": "explicit", "patch": {"city": "上海"}}
        fake_persona_module = types.ModuleType("persona_memory_sync")
        mocked = mock.Mock(return_value={"status": "ok"})
        fake_persona_module.upsert_persona_memory = mocked

        with mock.patch.dict(sys.modules, {"persona_memory_sync": fake_persona_module}):
            result = profile_service_api.apply_persona_patch(request)

        self.assertEqual(result, {"status": "ok"})
        mocked.assert_called_once_with(request)

    def test_render_public_profile_delegates_to_persona_engine(self):
        request = {"profile_id": 42, "write_profile": True}
        fake_persona_api = types.SimpleNamespace(
            coerce_render_request=mock.Mock(return_value="render-request"),
        )
        fake_persona_engine = types.SimpleNamespace(
            execute_render_public_profile=mock.Mock(return_value={"profile_id": 42, "public_personality": "现居上海"}),
        )
        fake_persona_module = types.ModuleType("persona_memory_sync")
        fake_persona_module.api = fake_persona_api
        fake_persona_module.persona_memory_engine = fake_persona_engine

        with mock.patch.dict(
            sys.modules,
            {
                "persona_memory_sync": fake_persona_module,
                "persona_memory_sync.api": fake_persona_api,
                "persona_memory_sync.persona_memory_engine": fake_persona_engine,
            },
        ):
            result = profile_service_api.render_public_profile(request)

        fake_persona_api.coerce_render_request.assert_called_once_with(request)
        fake_persona_engine.execute_render_public_profile.assert_called_once_with("render-request")
        self.assertEqual(result["profile_id"], 42)

    def test_get_profile_loads_single_profile_row(self):
        fake_conn = _FakeConnection(
            responses=[_FakeResult(fetchone_result={"id": 12, "avatar_url": "https://img.her.local/12.jpg"})]
        )

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_list_table_columns", return_value=["id", "avatar_url"]),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            result = profile_service_api.get_profile(
                source_dsn="mysql://profiles",
                source_table_name="profiles",
                profile_id=12,
            )

        self.assertEqual(result, {"id": 12, "avatar_url": "https://img.her.local/12.jpg"})
        self.assertEqual(
            fake_conn.calls[0],
            ("SELECT * FROM `profiles` WHERE `id` = ? LIMIT 1", (12,)),
        )
        self.assertTrue(fake_conn.closed)

    def test_list_profile_photo_features_returns_mapping(self):
        fake_conn = _FakeConnection(
            responses=[
                _FakeResult(
                    fetchall_result=[
                        {"profile_id": 12, "appearance_score_global": 80, "photo_quality_score": 75},
                        {"profile_id": 18, "appearance_score_global": 66, "photo_quality_score": 70},
                    ]
                )
            ]
        )

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_table_exists", return_value=True),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            result = profile_service_api.list_profile_photo_features(
                source_dsn="mysql://persona",
                profile_ids=[12, 18],
            )

        self.assertEqual(result[12]["appearance_score_global"], 80)
        self.assertEqual(result[18]["photo_quality_score"], 70)

    def test_upsert_user_appearance_preference_inserts_row(self):
        fake_conn = _FakeConnection(
            responses=[
                _FakeResult(fetchone_result=None),
                _FakeResult(rowcount=1),
                _FakeResult(
                    fetchone_result={
                        "user_key": "user-1",
                        "preferred_mature_score": 80,
                        "positive_sample_count": 3,
                    }
                ),
            ]
        )

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_table_exists", return_value=True),
            mock.patch.object(profile_service_api, "_column_exists", return_value=True),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            result = profile_service_api.upsert_user_appearance_preference(
                source_dsn="mysql://persona",
                user_key="user-1",
                patch={
                    "preferred_mature_score": 80,
                    "positive_sample_count": 3,
                },
            )

        self.assertEqual(result["user_key"], "user-1")
        self.assertEqual(result["preferred_mature_score"], 80)

    def test_get_public_profile_loads_single_view_row(self):
        fake_conn = _FakeConnection(
            responses=[_FakeResult(fetchone_result={"id": 12, "name": "用户0012", "job": "产品经理"})]
        )

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_list_schema_tables", return_value=["public_profile_view"]),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            result = profile_service_api.get_public_profile(
                source_dsn="mysql://profiles",
                profile_id=12,
            )

        self.assertEqual(result, {"id": 12, "name": "用户0012", "job": "产品经理"})
        self.assertEqual(
            fake_conn.calls[0],
            ("SELECT * FROM `public_profile_view` WHERE `id` = ? LIMIT 1", (12,)),
        )
        self.assertTrue(fake_conn.closed)

    def test_detect_profile_table_uses_best_scored_schema_match(self):
        fake_conn = _FakeConnection(
            responses=[
                _FakeResult(fetchall_result=[{"table_name": "audit_logs"}, {"table_name": "profiles"}]),
                _FakeResult(fetchall_result=[{"column_name": "id"}, {"column_name": "event_name"}]),
                _FakeResult(
                    fetchall_result=[
                        {"column_name": "id"},
                        {"column_name": "姓名"},
                        {"column_name": "性别"},
                        {"column_name": "年龄"},
                        {"column_name": "城市"},
                    ]
                ),
            ]
        )

        with mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn):
            result = profile_service_api.detect_profile_table(source_dsn="mysql://profiles")

        self.assertEqual(result, "profiles")
        self.assertIn("FROM information_schema.tables", fake_conn.calls[0][0])
        self.assertTrue(fake_conn.closed)

    def test_list_profile_columns_reads_information_schema(self):
        fake_conn = _FakeConnection(
            responses=[
                _FakeResult(
                    fetchall_result=[
                        {"column_name": "id"},
                        {"column_name": "name"},
                        {"column_name": "gender"},
                    ]
                )
            ]
        )

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_list_schema_tables", return_value=["profiles"]),
        ):
            result = profile_service_api.list_profile_columns(
                source_dsn="mysql://profiles",
                source_table_name="profiles",
            )

        self.assertEqual(result, ["id", "name", "gender"])
        self.assertIn("FROM information_schema.columns", fake_conn.calls[0][0])
        self.assertTrue(fake_conn.closed)

    def test_list_profiles_runs_select_with_optional_where_clause(self):
        fake_conn = _FakeConnection(
            responses=[_FakeResult(fetchall_result=[{"id": 12, "name": "Alice"}])]
        )

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_list_schema_tables", return_value=["profiles"]),
            mock.patch.object(profile_service_api, "_list_table_columns", return_value=["id", "name", "gender"]),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            result = profile_service_api.list_profiles(
                source_dsn="mysql://profiles",
                source_table_name="profiles",
                where_clause="WHERE `gender` = ?",
                params=("女",),
            )

        self.assertEqual(result, [{"id": 12, "name": "Alice"}])
        self.assertEqual(fake_conn.calls[0], ("SELECT * FROM `profiles` WHERE `gender` = ?", ("女",)))
        self.assertTrue(fake_conn.closed)

    def test_list_profile_photos_prefers_photo_rows_over_avatar_fallback(self):
        fake_conn = _FakeConnection(
            responses=[
                _FakeResult(fetchone_result={"id": 12, "avatar_url": "https://img.her.local/avatar.jpg"}),
                _FakeResult(
                    fetchall_result=[
                        {"profile_id": 12, "photo_url": "https://img.her.local/primary.jpg"},
                        {"profile_id": 12, "photo_url": "https://img.her.local/primary.jpg"},
                        {"profile_id": 12, "photo_url": "https://img.her.local/gallery.jpg"},
                    ]
                ),
            ]
        )

        def fake_list_schema_tables(_conn) -> list[str]:
            return ["profiles", "profile_photos"]

        def fake_list_table_columns(_conn, table_name: str) -> list[str]:
            if table_name == "profiles":
                return ["id", "avatar_url"]
            if table_name == "profile_photos":
                return ["profile_id", "photo_url", "is_primary", "photo_type", "sort_order", "id"]
            return []

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_list_schema_tables", side_effect=fake_list_schema_tables),
            mock.patch.object(profile_service_api, "_list_table_columns", side_effect=fake_list_table_columns),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            result = profile_service_api.list_profile_photos(
                source_dsn="mysql://profiles?photos_table=profile_photos",
                source_table_name="profiles",
                profile_id=12,
                limit=3,
            )

        self.assertEqual(
            result,
            [
                {
                    "source_profile_id": 12,
                    "photo_source": "https://img.her.local/primary.jpg",
                    "asset_origin": "photo_table",
                },
                {
                    "source_profile_id": 12,
                    "photo_source": "https://img.her.local/gallery.jpg",
                    "asset_origin": "photo_table",
                },
            ],
        )
        self.assertIn("ORDER BY `is_primary` DESC", fake_conn.calls[1][0])
        self.assertIn("CASE WHEN `photo_type` = 'avatar' THEN 0 ELSE 1 END ASC", fake_conn.calls[1][0])
        self.assertIn("`sort_order` ASC", fake_conn.calls[1][0])
        self.assertIn("LIMIT ?", fake_conn.calls[1][0])
        self.assertEqual(fake_conn.calls[1][1], (12, 3))
        self.assertTrue(fake_conn.closed)

    def test_list_profile_photos_falls_back_to_avatar_when_photo_table_is_missing(self):
        fake_conn = _FakeConnection(
            responses=[_FakeResult(fetchone_result={"id": 18, "avatar_url": "https://img.her.local/avatar-only.jpg"})]
        )

        def fake_list_schema_tables(_conn) -> list[str]:
            return ["profiles"]

        def fake_list_table_columns(_conn, table_name: str) -> list[str]:
            if table_name == "profiles":
                return ["id", "avatar_url"]
            return []

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_list_schema_tables", side_effect=fake_list_schema_tables),
            mock.patch.object(profile_service_api, "_list_table_columns", side_effect=fake_list_table_columns),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            result = profile_service_api.list_profile_photos(
                source_dsn="mysql://profiles?photos_table=profile_photos",
                source_table_name="profiles",
                profile_id=18,
            )

        self.assertEqual(
            result,
            [
                {
                    "source_profile_id": 18,
                    "photo_source": "https://img.her.local/avatar-only.jpg",
                    "asset_origin": "avatar_fallback",
                }
            ],
        )
        self.assertEqual(len(fake_conn.calls), 1)
        self.assertTrue(fake_conn.closed)

    def test_list_profile_photo_previews_builds_preview_lookup(self):
        fake_conn = _FakeConnection(
            responses=[
                _FakeResult(
                    fetchall_result=[
                        {"profile_id": 12, "photo_url": "https://img.her.local/12-1.jpg"},
                        {"profile_id": 12, "photo_url": "https://img.her.local/12-1.jpg"},
                        {"profile_id": 12, "photo_url": "https://img.her.local/12-2.jpg"},
                        {"profile_id": 18, "photo_url": "https://img.her.local/18-1.jpg"},
                    ]
                )
            ]
        )

        def fake_list_schema_tables(_conn) -> list[str]:
            return ["profile_photos"]

        def fake_list_table_columns(_conn, table_name: str) -> list[str]:
            if table_name == "profile_photos":
                return ["profile_id", "photo_url", "is_primary", "sort_order", "id"]
            return []

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_list_schema_tables", side_effect=fake_list_schema_tables),
            mock.patch.object(profile_service_api, "_list_table_columns", side_effect=fake_list_table_columns),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            result = profile_service_api.list_profile_photo_previews(
                source_dsn="mysql://profiles?photos_table=profile_photos",
                source_table_name="profiles",
                profile_ids=[12, 18],
                preview_count=2,
            )

        self.assertEqual(
            result,
            {
                12: ["https://img.her.local/12-1.jpg", "https://img.her.local/12-2.jpg"],
                18: ["https://img.her.local/18-1.jpg"],
            },
        )
        self.assertIn("WHERE `profile_id` IN (?, ?)", fake_conn.calls[0][0])
        self.assertTrue(fake_conn.closed)

    def test_list_profile_photo_sources_projects_photo_urls(self):
        with mock.patch.object(
            profile_service_api,
            "list_profile_photos",
            return_value=[
                {
                    "source_profile_id": 12,
                    "photo_source": "https://img.her.local/12-1.jpg",
                    "asset_origin": "photo_table",
                },
                {
                    "source_profile_id": 12,
                    "photo_source": "https://img.her.local/12-2.jpg",
                    "asset_origin": "photo_table",
                },
            ],
        ) as mocked:
            result = profile_service_api.list_profile_photo_sources(
                source_dsn="mysql://profiles",
                source_table_name="profiles",
                profile_id=12,
                limit=2,
            )

        self.assertEqual(result, ["https://img.her.local/12-1.jpg", "https://img.her.local/12-2.jpg"])
        mocked.assert_called_once()

    def test_list_comparison_profile_photos_falls_back_to_avatar_rows(self):
        fake_conn = _FakeConnection(
            responses=[
                _FakeResult(fetchall_result=[]),
                _FakeResult(
                    fetchall_result=[
                        {"id": 20, "avatar_url": "https://img.her.local/20.jpg"},
                        {"id": 21, "avatar_url": "https://img.her.local/21.jpg"},
                    ]
                ),
            ]
        )

        def fake_list_schema_tables(_conn) -> list[str]:
            return ["profiles", "profile_photos"]

        def fake_list_table_columns(_conn, table_name: str) -> list[str]:
            if table_name == "profile_photos":
                return ["profile_id", "photo_url"]
            if table_name == "profiles":
                return ["avatar_url", "id"]
            return []

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_list_schema_tables", side_effect=fake_list_schema_tables),
            mock.patch.object(profile_service_api, "_list_table_columns", side_effect=fake_list_table_columns),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            result = profile_service_api.list_comparison_profile_photos(
                source_dsn="mysql://profiles?photos_table=profile_photos",
                source_table_name="profiles",
                profile_id=12,
                limit=2,
            )

        self.assertEqual(
            result,
            [
                {
                    "source_profile_id": 20,
                    "photo_source": "https://img.her.local/20.jpg",
                    "asset_origin": "avatar_fallback",
                },
                {
                    "source_profile_id": 21,
                    "photo_source": "https://img.her.local/21.jpg",
                    "asset_origin": "avatar_fallback",
                },
            ],
        )
        self.assertTrue(fake_conn.closed)

    def test_detect_profile_table_reuses_metadata_cache(self):
        fake_conn = _FakeConnection(
            responses=[
                _FakeResult(fetchall_result=[{"table_name": "profiles"}]),
                _FakeResult(fetchall_result=[{"column_name": "id"}, {"column_name": "name"}, {"column_name": "age"}]),
            ]
        )

        with mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn):
            first = profile_service_api.detect_profile_table(source_dsn="mysql://profiles")
            second = profile_service_api.detect_profile_table(source_dsn="mysql://profiles")

        self.assertEqual(first, "profiles")
        self.assertEqual(second, "profiles")
        self.assertEqual(len(fake_conn.calls), 2)

    def test_iter_profile_batches_uses_keyset_pagination_when_id_column_exists(self):
        fake_conn = _FakeConnection(
            responses=[
                _FakeResult(fetchall_result=[{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]),
                _FakeResult(fetchall_result=[{"id": 3, "name": "C"}]),
            ]
        )

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_list_schema_tables", return_value=["profiles"]),
            mock.patch.object(profile_service_api, "_list_table_columns", return_value=["id", "name"]),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            batches = list(
                profile_service_api.iter_profile_batches(
                    source_dsn="mysql://profiles",
                    source_table_name="profiles",
                    where_clause="WHERE `gender` = ?",
                    params=("女",),
                    batch_size=2,
                )
            )

        self.assertEqual(len(batches), 2)
        self.assertIn("ORDER BY `id` ASC LIMIT 2", fake_conn.calls[0][0])
        self.assertNotIn("OFFSET", fake_conn.calls[0][0])
        self.assertIn("AND `id` > ?", fake_conn.calls[1][0])
        self.assertIn("SELECT *", fake_conn.calls[0][0])
        self.assertIn("SELECT *", fake_conn.calls[1][0])
        self.assertEqual(fake_conn.calls[1][1], ("女", 2))

    def test_iter_profile_batches_preserves_selected_projection_across_keyset_pages(self):
        fake_conn = _FakeConnection(
            responses=[
                _FakeResult(fetchall_result=[{"id": 1, "name": "A"}, {"id": 2, "name": "B"}]),
                _FakeResult(fetchall_result=[{"id": 3, "name": "C"}]),
            ]
        )

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api, "_list_schema_tables", return_value=["profiles"]),
            mock.patch.object(profile_service_api, "_list_table_columns", return_value=["id", "name", "bio"]),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            batches = list(
                profile_service_api.iter_profile_batches(
                    source_dsn="mysql://profiles",
                    source_table_name="profiles",
                    where_clause="WHERE `gender` = ?",
                    params=("女",),
                    selected_columns=("id", "name"),
                    batch_size=2,
                )
            )

        self.assertEqual(len(batches), 2)
        self.assertIn("SELECT `id`, `name` FROM `profiles`", fake_conn.calls[0][0])
        self.assertIn("SELECT `id`, `name` FROM `profiles`", fake_conn.calls[1][0])
        self.assertNotIn("SELECT *", fake_conn.calls[1][0])

    def test_list_comparison_profile_photo_sources_projects_photo_urls(self):
        with mock.patch.object(
            profile_service_api,
            "list_comparison_profile_photos",
            return_value=[
                {
                    "source_profile_id": 20,
                    "photo_source": "https://img.her.local/20.jpg",
                    "asset_origin": "avatar_fallback",
                },
                {
                    "source_profile_id": 21,
                    "photo_source": "https://img.her.local/21.jpg",
                    "asset_origin": "avatar_fallback",
                },
            ],
        ) as mocked:
            result = profile_service_api.list_comparison_profile_photo_sources(
                source_dsn="mysql://profiles",
                source_table_name="profiles",
                profile_id=12,
                limit=2,
            )

        self.assertEqual(result, ["https://img.her.local/20.jpg", "https://img.her.local/21.jpg"])
        mocked.assert_called_once()

    def test_apply_profile_updates_skips_when_no_supported_columns_exist(self):
        fake_conn = _FakeConnection()

        def fake_column_exists(_raw_conn, _table_name: str, column: str) -> bool:
            return column == "id"

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api.schema, "column_exists", side_effect=fake_column_exists),
        ):
            result = profile_service_api.apply_profile_updates(
                source_dsn="mysql://profiles",
                source_table_name="profiles",
                profile_id=12,
                updates={"job": "工程师"},
            )

        self.assertEqual(
            result,
            {"status": "skipped", "reason": "no_sync_columns", "updated_fields": []},
        )
        self.assertEqual(fake_conn.calls, [])
        self.assertFalse(fake_conn.committed)
        self.assertTrue(fake_conn.closed)

    def test_apply_profile_updates_updates_supported_columns(self):
        fake_conn = _FakeConnection()
        fixed_now = datetime(2026, 5, 14, 19, 0, 0)

        def fake_column_exists(_raw_conn, _table_name: str, column: str) -> bool:
            return column in {"id", "job", "updated_at"}

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api.schema, "column_exists", side_effect=fake_column_exists),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
            mock.patch.object(profile_service_api, "current_time", return_value=fixed_now),
        ):
            result = profile_service_api.apply_profile_updates(
                source_dsn="mysql://profiles",
                source_table_name="profiles",
                profile_id=12,
                updates={"job": "工程师", "unknown": "ignored", "city": None},
            )

        self.assertEqual(
            result,
            {
                "status": "synced",
                "profile_id": 12,
                "table_name": "profiles",
                "updated_fields": ["job", "updated_at"],
            },
        )
        self.assertEqual(len(fake_conn.calls), 1)
        self.assertEqual(
            fake_conn.calls[0],
            (
                "UPDATE `profiles` SET `job` = ?, `updated_at` = ? WHERE `id` = ?",
                ("工程师", fixed_now, 12),
            ),
        )
        self.assertTrue(fake_conn.committed)
        self.assertTrue(fake_conn.closed)

    def test_apply_profile_updates_keeps_explicit_updated_at_value(self):
        fake_conn = _FakeConnection()
        explicit_updated_at = datetime(2026, 5, 14, 20, 0, 0)

        def fake_column_exists(_raw_conn, _table_name: str, column: str) -> bool:
            return column in {"id", "job", "updated_at"}

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api.schema, "column_exists", side_effect=fake_column_exists),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
            mock.patch.object(profile_service_api, "current_time", side_effect=AssertionError("should not be called")),
        ):
            result = profile_service_api.apply_profile_updates(
                source_dsn="mysql://profiles",
                source_table_name="profiles",
                profile_id=18,
                updates={"job": "设计师", "updated_at": explicit_updated_at},
            )

        self.assertEqual(
            result,
            {
                "status": "synced",
                "profile_id": 18,
                "table_name": "profiles",
                "updated_fields": ["job", "updated_at"],
            },
        )
        self.assertEqual(
            fake_conn.calls[0],
            (
                "UPDATE `profiles` SET `job` = ?, `updated_at` = ? WHERE `id` = ?",
                ("设计师", explicit_updated_at, 18),
            ),
        )
        self.assertTrue(fake_conn.committed)
        self.assertTrue(fake_conn.closed)

    def test_apply_profile_updates_raises_when_profile_row_is_missing(self):
        fake_conn = _FakeConnection(rowcount=0, select_exists=False)

        def fake_column_exists(_raw_conn, _table_name: str, column: str) -> bool:
            return column in {"id", "job"}

        with (
            mock.patch.object(profile_service_api, "_connect_profile_db", return_value=fake_conn),
            mock.patch.object(profile_service_api.schema, "column_exists", side_effect=fake_column_exists),
            mock.patch.object(profile_service_api.schema, "quote_mysql_ident", side_effect=lambda value: f"`{value}`"),
        ):
            with self.assertRaisesRegex(ValueError, "profile 99 was not found"):
                profile_service_api.apply_profile_updates(
                    source_dsn="mysql://profiles",
                    source_table_name="profiles",
                    profile_id=99,
                    updates={"job": "工程师"},
                )

        self.assertEqual(len(fake_conn.calls), 2)
        self.assertTrue(fake_conn.closed)
