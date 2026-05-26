#!/usr/bin/env python3

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from match_domain.outbox_cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main("recommendation"))
