"""Compatibility helpers for verifying packaged skill imports."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


def _require_skill_package(package_name: str) -> Path:
    spec = importlib.util.find_spec(package_name)
    if spec is None:
        raise ModuleNotFoundError(
            f"Required skill package '{package_name}' is not importable. "
            "Install the Her repo as a package before starting the service."
        )
    search_locations = list(spec.submodule_search_locations or ())
    if search_locations:
        return Path(search_locations[0]).resolve()
    if spec.origin:
        return Path(spec.origin).resolve().parent
    raise ModuleNotFoundError(
        f"Required skill package '{package_name}' resolved without a filesystem location."
    )


def ensure_partner_search_skill_on_path() -> Path:
    return _require_skill_package("partner_search")


def ensure_persona_memory_skill_on_path() -> Path:
    return _require_skill_package("persona_memory_sync")


__all__ = [
    "ensure_partner_search_skill_on_path",
    "ensure_persona_memory_skill_on_path",
]
