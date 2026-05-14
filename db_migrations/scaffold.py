"""Scaffold helpers for new migration files."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


_FILENAME_RE = re.compile(r"m(?P<number>\d{4})_[a-z0-9_]+\.py$")


def normalize_migration_slug(name: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", str(name or "").strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    if not slug:
        raise ValueError("Migration name cannot be empty.")
    if slug[0].isdigit():
        slug = f"change_{slug}"
    return slug


def target_directory(target: str, *, repo_root: Path | None = None) -> Path:
    root = (repo_root or Path(__file__).resolve().parents[1]).resolve()
    return root / "db_migrations" / "targets" / target


def next_migration_number(target: str, *, repo_root: Path | None = None) -> int:
    target_dir = target_directory(target, repo_root=repo_root)
    numbers = []
    for path in target_dir.glob("m*.py"):
        match = _FILENAME_RE.fullmatch(path.name)
        if match is None:
            continue
        numbers.append(int(match.group("number")))
    return max(numbers, default=0) + 1


def render_migration_template(
    *,
    target: str,
    migration_number: int,
    migration_slug: str,
    description: str,
) -> str:
    migration_id = f"{migration_number:04d}_{migration_slug}"
    scope_fn = "persona_scope" if target == "persona" else "default_scope"
    return f'''"""Schema migration {migration_id} for {target}."""

from __future__ import annotations

from db_migrations.core import MigrationContext, MigrationSpec, empty_issues
from db_migrations.helpers import {scope_fn}


def apply(mysql_conn, context: MigrationContext) -> None:
    # Implement the DDL or data backfill here.
    # Example:
    # with mysql_conn.cursor() as cursor:
    #     cursor.execute("ALTER TABLE ...")
    raise NotImplementedError("Implement migration apply steps.")


def validate(mysql_conn, context: MigrationContext) -> dict[str, list[str]]:
    issues = empty_issues()
    # Add post-migration checks here.
    # Example:
    # issues["missing_columns"].append("outbox_events.retry_count")
    return issues


MIGRATION = MigrationSpec(
    migration_id="{migration_id}",
    description="{description}",
    scope_fn={scope_fn},
    apply_fn=apply,
    validate_fn=validate,
)
'''


def create_migration_file(
    target: str,
    name: str,
    *,
    description: str | None = None,
    repo_root: Path | None = None,
) -> Path:
    target_dir = target_directory(target, repo_root=repo_root)
    if not target_dir.is_dir():
        raise ValueError(f"Unknown migration target directory: {target_dir}")
    migration_slug = normalize_migration_slug(name)
    migration_number = next_migration_number(target, repo_root=repo_root)
    description_text = str(description or migration_slug.replace("_", " ")).strip()
    filename = f"m{migration_number:04d}_{migration_slug}.py"
    path = target_dir / filename
    if path.exists():
        raise FileExistsError(f"Migration file already exists: {path}")
    path.write_text(
        render_migration_template(
            target=target,
            migration_number=migration_number,
            migration_slug=migration_slug,
            description=description_text,
        ),
        encoding="utf-8",
    )
    return path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scaffold a new Her schema migration file.")
    parser.add_argument("target", choices=("recommendation", "matchmaking", "chat", "persona"))
    parser.add_argument("name", help="Migration slug, e.g. add_retry_count_to_outbox")
    parser.add_argument("--description", default=None, help="Human-readable migration description.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    path = create_migration_file(args.target, args.name, description=args.description)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
