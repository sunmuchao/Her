"""Stable hashes for search candidate snapshots."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from outer_mysql_compat import json_dumps


def candidate_snapshot_hash(result: Mapping[str, Any] | dict[str, Any]) -> str:
    return hashlib.sha256(json_dumps(dict(result)).encode("utf-8")).hexdigest()
