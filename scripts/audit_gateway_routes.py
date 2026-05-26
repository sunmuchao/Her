#!/usr/bin/env python3
"""Audit gateway routes for §13.4 cross-domain write violations."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "external-systems" / "partner-http-gateway" / "gateway"

FORBIDDEN_PATTERNS = [
    (re.compile(r"moderation_dsn\s*="), "direct moderation_dsn assignment in gateway"),
]

ALLOWLIST_FILES = {
    "bff/search_profiles.py",
    "jsonrpc_dispatch.py",
}

WRITE_CONNECTORS = {
    "_with_rec(": "recommendation",
    "_with_mm(": "matchmaking",
    "_with_chat(": "chat",
    "_with_ledger(": "ledger",
}


def _iter_gateway_py_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(GATEWAY_DIR.rglob("*.py")):
        if path.name == "__init__.py":
            continue
        files.append(path)
    return files


def _function_connector_sets(tree: ast.AST) -> list[tuple[str, set[str]]]:
    out: list[tuple[str, set[str]]] = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        text = ast.unparse(node)
        owners = {owner for marker, owner in WRITE_CONNECTORS.items() if marker in text}
        if owners:
            out.append((node.name, owners))
    return out


def audit() -> list[str]:
    violations: list[str] = []
    for path in _iter_gateway_py_files():
        rel = path.relative_to(ROOT)
        rel_posix = rel.as_posix()
        text = path.read_text(encoding="utf-8")

        for pattern, message in FORBIDDEN_PATTERNS:
            if not pattern.search(text):
                continue
            if any(allowed in rel_posix for allowed in ALLOWLIST_FILES):
                continue
            violations.append(f"{rel}: {message}")

        if "bff" not in path.parts:
            continue
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for func_name, owners in _function_connector_sets(tree):
            if len(owners) > 1 and func_name.startswith("rest_"):
                violations.append(f"{rel}::{func_name}: multiple domain connectors ({', '.join(sorted(owners))})")
    return violations


def main() -> int:
    violations = audit()
    if violations:
        print("Gateway audit violations:")
        for item in violations:
            print(f"  - {item}")
        return 1
    print("Gateway audit passed (§13.4).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
