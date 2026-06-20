"""Minimal pkg_resources compatibility shim for local tooling.

This repo only needs the subset used by milvus-lite during import:
- DistributionNotFound
- get_distribution(name).version
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version


class DistributionNotFound(Exception):
    """Raised when a requested distribution is not installed."""


@dataclass
class _Distribution:
    version: str


def get_distribution(name: str) -> _Distribution:
    try:
        return _Distribution(version=version(name))
    except PackageNotFoundError as exc:
        raise DistributionNotFound(str(exc)) from exc
