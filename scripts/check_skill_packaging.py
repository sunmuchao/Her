#!/usr/bin/env python3

"""Verify the packaged local skills are importable and expose their public APIs."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
from typing import Any


def _module_summary(module_name: str, attributes: list[str]) -> dict[str, Any]:
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - report packaging/import failures in the payload
        return {
            "module": module_name,
            "file": None,
            "has_attributes": {name: False for name in attributes},
            "import_error": f"{type(exc).__name__}: {exc}",
        }
    return {
        "module": module_name,
        "file": getattr(module, "__file__", None),
        "has_attributes": {name: hasattr(module, name) for name in attributes},
        "import_error": None,
    }


def _distribution_summary(name: str) -> dict[str, Any]:
    try:
        dist = importlib.metadata.distribution(name)
    except importlib.metadata.PackageNotFoundError:
        return {"name": name, "installed": False, "version": None, "location": None}
    return {
        "name": str(dist.metadata.get("Name") or name),
        "installed": True,
        "version": dist.version,
        "location": str(dist.locate_file("")),
    }


def _console_script_summary(name: str, *, expected_distribution: str) -> dict[str, Any]:
    provider: str | None = None
    for dist in importlib.metadata.distributions():
        dist_name = str(dist.metadata.get("Name") or "").strip()
        if not dist_name:
            continue
        for entry_point in getattr(dist, "entry_points", ()):
            if entry_point.group == "console_scripts" and entry_point.name == name:
                provider = dist_name
                break
        if provider is not None:
            break
    return {
        "name": name,
        "installed": provider is not None,
        "provider": provider,
        "owned_by_expected_distribution": (provider or "").lower() == expected_distribution.lower(),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify packaged skill imports and optional console scripts.")
    parser.add_argument(
        "--require-console-scripts",
        action="store_true",
        help="Exit non-zero when the packaged console scripts are not registered in the current environment.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    expected_distribution = "her"
    payload = {
        "distribution": _distribution_summary(expected_distribution),
        "modules": [
            _module_summary(
                "partner_search",
                ["SearchRequest", "search_profiles", "load_self_profile"],
            ),
            _module_summary(
                "persona_memory_sync",
                ["UpsertPersonaMemoryRequest", "upsert_persona_memory", "render_public_profile"],
            ),
        ],
        "console_scripts": {
            "partner-search": _console_script_summary(
                "partner-search",
                expected_distribution=expected_distribution,
            ),
            "persona-memory-sync": _console_script_summary(
                "persona-memory-sync",
                expected_distribution=expected_distribution,
            ),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if any(module["import_error"] for module in payload["modules"]):
        return 1
    if args.require_console_scripts and (
        not payload["distribution"]["installed"]
        or not all(
            script["installed"] and script["owned_by_expected_distribution"]
            for script in payload["console_scripts"].values()
        )
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
