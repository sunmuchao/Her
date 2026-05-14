"""CLI for Her schema migrations."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import outer_system_mysql_schema as _schema

from .runner import TARGETS, get_migration_status, initialize_target_database, resolve_target_source


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Her MySQL schema migrations.")
    parser.add_argument("command", choices=("upgrade", "validate", "status"))
    parser.add_argument("target", choices=tuple(sorted(TARGETS)))
    parser.add_argument("--dsn", default=None, help="Explicit MySQL DSN. Defaults to the target env var.")
    parser.add_argument("--persona-table", default=None)
    parser.add_argument("--observation-table", default=None)
    parser.add_argument("--profile-table", default=None)
    parser.add_argument("--public-view", default=None)
    return parser


def _resolve_dsn(target: str, explicit_dsn: str | None) -> str:
    try:
        return resolve_target_source(target, explicit_dsn)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def _extra_options(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "persona_table": args.persona_table,
        "observation_table": args.observation_table,
        "profile_table": args.profile_table,
        "public_view": args.public_view,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    dsn = _resolve_dsn(args.target, args.dsn)
    config = _schema.parse_mysql_dsn(dsn)
    if args.command == "upgrade":
        _schema.ensure_database(config)
    conn = _schema.mysql_database_connect(config)
    try:
        if args.command == "status":
            result = get_migration_status(
                conn,
                target=args.target,
                config=config,
                source=dsn,
                options=_extra_options(args),
            )
        else:
            result = initialize_target_database(
                conn,
                target=args.target,
                config=config,
                mode="migrate" if args.command == "upgrade" else "validate",
                source=dsn,
                options=_extra_options(args),
            )
    finally:
        conn.close()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
