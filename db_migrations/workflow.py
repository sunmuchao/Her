"""Batch workflow helpers for schema upgrade and release checks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Mapping, Sequence

import outer_system_mysql_schema as _schema

from .core import DEFAULT_INIT_MODE, INIT_MODE_ENV
from .runner import TARGETS, get_migration_status, initialize_target_database, resolve_init_mode, resolve_target_source


def run_workflow(
    command: str,
    *,
    targets: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    fail_on_missing: bool = False,
    expected_init_mode: str | None = None,
    persona_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    selected_targets = tuple(targets or sorted(TARGETS))
    options = dict(persona_options or {})
    results: list[dict[str, Any]] = []
    missing_targets: list[dict[str, str]] = []
    ok = True

    actual_init_mode = resolve_init_mode(str(env.get(INIT_MODE_ENV) or DEFAULT_INIT_MODE))
    init_mode_error: str | None = None
    if expected_init_mode is not None and actual_init_mode != expected_init_mode:
        ok = False
        init_mode_error = (
            f"{INIT_MODE_ENV} must be {expected_init_mode!r} for {command}, "
            f"but resolved to {actual_init_mode!r}."
        )

    for target in selected_targets:
        env_var = TARGETS[target].env_var
        source = str(env.get(env_var) or "").strip()
        if not source:
            missing_targets.append({"target": target, "env_var": env_var})
            if fail_on_missing:
                ok = False
            continue
        try:
            result = _run_target_command(command, target=target, source=source, options=options)
        except Exception as exc:  # noqa: BLE001
            ok = False
            results.append(
                {
                    "target": target,
                    "ok": False,
                    "error": str(exc),
                }
            )
            continue
        results.append(
            {
                "target": target,
                "ok": True,
                "result": result,
            }
        )

    return {
        "command": command,
        "ok": ok and not (fail_on_missing and missing_targets),
        "expected_init_mode": expected_init_mode,
        "actual_init_mode": actual_init_mode,
        "init_mode_error": init_mode_error,
        "missing_targets": missing_targets,
        "results": results,
    }


def _run_target_command(
    command: str,
    *,
    target: str,
    source: str,
    options: Mapping[str, Any],
) -> dict[str, Any]:
    resolved_source = resolve_target_source(target, source)
    config = _schema.parse_mysql_dsn(resolved_source)
    conn = _schema.mysql_database_connect(config)
    try:
        if command == "status-all":
            return get_migration_status(conn, target=target, config=config, source=resolved_source, options=options)
        if command == "upgrade-all":
            return initialize_target_database(
                conn,
                target=target,
                config=config,
                mode="migrate",
                source=resolved_source,
                options=options,
            )
        if command in {"validate-all", "release-check"}:
            return initialize_target_database(
                conn,
                target=target,
                config=config,
                mode="validate",
                source=resolved_source,
                options=options,
            )
    finally:
        conn.close()
    raise ValueError(f"Unsupported workflow command: {command}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run batch Her schema workflows.")
    parser.add_argument("command", choices=("status-all", "upgrade-all", "validate-all", "release-check"))
    parser.add_argument("--target", action="append", choices=tuple(sorted(TARGETS)), dest="targets")
    parser.add_argument("--fail-on-missing", action="store_true")
    parser.add_argument("--persona-table", default=None)
    parser.add_argument("--observation-table", default=None)
    parser.add_argument("--profile-table", default=None)
    parser.add_argument("--public-view", default=None)
    parser.add_argument("--expected-init-mode", default="validate")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = run_workflow(
        args.command,
        targets=args.targets,
        fail_on_missing=args.fail_on_missing or args.command == "release-check",
        expected_init_mode=args.expected_init_mode if args.command == "release-check" else None,
        persona_options={
            "persona_table": args.persona_table,
            "observation_table": args.observation_table,
            "profile_table": args.profile_table,
            "public_view": args.public_view,
        },
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
