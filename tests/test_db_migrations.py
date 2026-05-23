from __future__ import annotations

from unittest import mock

import pytest

import db_migrations.runner as runner
import db_migrations.scaffold as scaffold
import db_migrations.workflow as workflow

from persona_memory_sync import schema_tools  # noqa: E402


class FakeCursor:
    def __init__(self, conn: "FakeConn") -> None:
        self.conn = conn
        self._rows: list[dict[str, object]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple[object, ...] | None = None) -> None:
        query = " ".join(sql.split())
        params = params or ()
        if query.startswith("SELECT scope, migration_id, checksum, description, applied_at FROM `schema_migrations` WHERE"):
            scope, migration_id = params
            row = next(
                (
                    candidate
                    for candidate in self.conn.migration_rows
                    if candidate["scope"] == scope and candidate["migration_id"] == migration_id
                ),
                None,
            )
            self._rows = [] if row is None else [dict(row)]
            return
        if query.startswith("SELECT scope, migration_id, checksum, description, applied_at FROM `schema_migrations` ORDER BY"):
            ordered = sorted(self.conn.migration_rows, key=lambda row: (str(row["scope"]), str(row["migration_id"])))
            self._rows = [dict(row) for row in ordered]
            return
        if query.startswith("INSERT INTO `schema_migrations`"):
            scope, migration_id, checksum, description = params
            self.conn.migration_rows.append(
                {
                    "scope": str(scope),
                    "migration_id": str(migration_id),
                    "checksum": str(checksum),
                    "description": str(description),
                    "applied_at": "2026-05-13 10:00:00",
                }
            )
            self._rows = []
            return
        if query.startswith("UPDATE profile_recommendations"):
            self._rows = []
            return
        raise AssertionError(f"Unexpected SQL in fake cursor: {query}")

    def fetchone(self) -> dict[str, object] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, object]]:
        return list(self._rows)


class FakeConn:
    def __init__(self) -> None:
        self.tables: set[str] = set()
        self.migration_rows: list[dict[str, object]] = []
        self.commits = 0
        self.rollbacks = 0
        self.config = {"database": "her_test"}

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _fake_table_exists(conn: FakeConn, table_name: str) -> bool:
    return table_name in conn.tables


def _fake_ensure_schema(conn: FakeConn, tables, *, prefix=None, config=None, commit=True) -> dict[str, list[str]]:
    for table in tables:
        conn.tables.add(table.name)
    if commit:
        conn.commit()
    return {table.name: [] for table in tables}


def _fake_validate_schema(conn: FakeConn, tables, *, prefix=None) -> dict[str, list[str]]:
    missing_tables = [table.name for table in tables if table.name not in conn.tables]
    return {
        "missing_tables": missing_tables,
        "missing_columns": [],
        "missing_unique_keys": [],
        "missing_indexes": [],
    }


def test_resolve_init_mode_defaults_to_migrate() -> None:
    with mock.patch.dict("os.environ", {}, clear=True):
        assert runner.resolve_init_mode() == "migrate"


def test_initialize_target_database_dispatches_validate() -> None:
    fake_conn = FakeConn()
    with mock.patch.object(runner, "validate_target_database", return_value={"ok": True}) as validate_mock:
        result = runner.initialize_target_database(fake_conn, target="recommendation", mode="validate")
    validate_mock.assert_called_once()
    assert result == {"ok": True}


def test_upgrade_target_database_records_baseline_migration() -> None:
    fake_conn = FakeConn()
    with (
        mock.patch.object(runner._schema, "ensure_database", return_value=None),
        mock.patch.object(runner._schema, "ensure_schema", side_effect=_fake_ensure_schema),
        mock.patch.object(runner._schema, "ensure_table_columns", return_value=None),
        mock.patch.object(runner._schema, "ensure_indexes", return_value=None),
        mock.patch.object(runner._schema, "table_exists", side_effect=_fake_table_exists),
    ):
        result = runner.upgrade_target_database(fake_conn, target="recommendation", config=fake_conn.config)

    assert result["target"] == "recommendation"
    assert result["mode"] == "migrate"
    assert result["applied"] == [
        {
            "scope": "recommendation",
            "migration_id": "0001_baseline",
            "description": "Baseline recommendation schema",
        },
        {
            "scope": "recommendation",
            "migration_id": "0002_add_outbox_delivery_state",
            "description": "Add delivery state to recommendation outbox events",
        },
        {
            "scope": "recommendation",
            "migration_id": "0003_add_async_jobs",
            "description": "Add persisted async jobs to recommendation",
        },
        {
            "scope": "recommendation",
            "migration_id": "0004_add_active_case_status",
            "description": "Add active_case_status mirror field to profile recommendations",
        },
        {
            "scope": "recommendation",
            "migration_id": "0005_normalize_delivery_statuses",
            "description": "Normalize legacy recommendation delivery_status values",
        },
    ]
    assert result["already_applied"] == []
    assert fake_conn.commits == 1
    assert fake_conn.rollbacks == 0
    assert ("recommendation", "0001_baseline") == (
        fake_conn.migration_rows[0]["scope"],
        fake_conn.migration_rows[0]["migration_id"],
    )
    assert ("recommendation", "0002_add_outbox_delivery_state") == (
        fake_conn.migration_rows[1]["scope"],
        fake_conn.migration_rows[1]["migration_id"],
    )
    assert ("recommendation", "0003_add_async_jobs") == (
        fake_conn.migration_rows[2]["scope"],
        fake_conn.migration_rows[2]["migration_id"],
    )
    assert ("recommendation", "0004_add_active_case_status") == (
        fake_conn.migration_rows[3]["scope"],
        fake_conn.migration_rows[3]["migration_id"],
    )
    assert ("recommendation", "0005_normalize_delivery_statuses") == (
        fake_conn.migration_rows[4]["scope"],
        fake_conn.migration_rows[4]["migration_id"],
    )


def test_validate_target_database_raises_when_migration_row_missing() -> None:
    fake_conn = FakeConn()
    fake_conn.tables.update(table.name for table in runner._schema.recommendation_tables())
    with (
        mock.patch.object(runner._schema, "table_exists", side_effect=_fake_table_exists),
        mock.patch.object(runner._schema, "validate_schema", side_effect=_fake_validate_schema),
    ):
        with pytest.raises(runner.SchemaValidationError) as excinfo:
            runner.validate_target_database(fake_conn, target="recommendation", config=fake_conn.config)

    assert excinfo.value.issues["missing_tables"] == ["schema_migrations"]
    assert excinfo.value.issues["missing_migrations"] == [
        "recommendation:0001_baseline",
        "recommendation:0002_add_outbox_delivery_state",
        "recommendation:0003_add_async_jobs",
        "recommendation:0004_add_active_case_status",
        "recommendation:0005_normalize_delivery_statuses",
    ]


def test_build_persona_scope_uses_profile_table_from_source_query() -> None:
    scope = schema_tools.build_persona_scope(
        source="mysql://demo@127.0.0.1:3306/her?table=partner_profiles",
        public_view="persona_public_view",
    )
    assert scope == "persona:user_personas:user_persona_observations:partner_profiles:persona_public_view"


def test_load_target_migrations_reads_baseline_module() -> None:
    migrations = runner.load_target_migrations("recommendation")
    assert [migration.migration_id for migration in migrations] == [
        "0001_baseline",
        "0002_add_outbox_delivery_state",
        "0003_add_async_jobs",
        "0004_add_active_case_status",
        "0005_normalize_delivery_statuses",
    ]


def test_load_matchmaking_target_migrations_reads_real_0002_module() -> None:
    migrations = runner.load_target_migrations("matchmaking")
    assert [migration.migration_id for migration in migrations] == [
        "0001_baseline",
        "0002_add_outbox_delivery_state",
        "0003_add_async_jobs",
    ]


def test_load_chat_target_migrations_reads_real_0002_module() -> None:
    migrations = runner.load_target_migrations("chat")
    migration_ids = [migration.migration_id for migration in migrations]
    assert migration_ids[:2] == [
        "0001_baseline",
        "0002_add_outbox_retry_state",
    ]
    assert "0004_add_outbox_processing_claim" in migration_ids
    assert "0005_add_async_jobs" in migration_ids
    assert migration_ids == sorted(migration_ids)


def test_load_relationship_ledger_target_migrations_reads_baseline_module() -> None:
    migrations = runner.load_target_migrations("relationship_ledger")
    assert [migration.migration_id for migration in migrations] == [
        "0001_baseline",
    ]


def test_create_migration_file_generates_next_0002_template(tmp_path) -> None:
    target_dir = tmp_path / "db_migrations" / "targets" / "recommendation"
    target_dir.mkdir(parents=True)
    (target_dir / "m0001_baseline.py").write_text("# baseline\n", encoding="utf-8")

    path = scaffold.create_migration_file(
        "recommendation",
        "add retry count to outbox",
        description="Add retry count to outbox",
        repo_root=tmp_path,
    )

    assert path.name == "m0002_add_retry_count_to_outbox.py"
    content = path.read_text(encoding="utf-8")
    assert 'migration_id="0002_add_retry_count_to_outbox"' in content
    assert 'description="Add retry count to outbox"' in content
    assert "scope_fn=default_scope" in content


def test_workflow_release_check_requires_validate_mode() -> None:
    with mock.patch.object(workflow, "_run_target_command", return_value={"target": "recommendation"}):
        result = workflow.run_workflow(
            "release-check",
            targets=("recommendation",),
            environ={
                "PARTNER_RECOMMENDATION_DB": "mysql://root@127.0.0.1:3307/her_recommendation",
                "HER_SCHEMA_INIT_MODE": "migrate",
            },
            expected_init_mode="validate",
        )
    assert result["ok"] is False
    assert result["actual_init_mode"] == "migrate"
    assert "HER_SCHEMA_INIT_MODE" in str(result["init_mode_error"])


def test_workflow_runs_configured_targets_with_batch_command() -> None:
    with mock.patch.object(workflow, "_run_target_command", return_value={"target": "recommendation"}) as run_mock:
        result = workflow.run_workflow(
            "validate-all",
            targets=("recommendation",),
            environ={
                "PARTNER_RECOMMENDATION_DB": "mysql://root@127.0.0.1:3307/her_recommendation",
                "HER_SCHEMA_INIT_MODE": "validate",
            },
        )

    assert result["ok"] is True
    assert result["missing_targets"] == []
    assert result["results"] == [
        {
            "target": "recommendation",
            "ok": True,
            "result": {"target": "recommendation"},
        }
    ]
    run_mock.assert_called_once_with(
        "validate-all",
        target="recommendation",
        source="mysql://root@127.0.0.1:3307/her_recommendation",
        options={},
    )
