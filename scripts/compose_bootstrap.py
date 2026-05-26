#!/usr/bin/env python3
"""Initialize MySQL schemas for docker compose (idempotent)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
os.chdir(REPO_ROOT)
os.environ.setdefault("HER_E2E_MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("HER_E2E_MYSQL_PORT", "3307")

if __name__ == "__main__":
    host = os.environ.get("HER_E2E_MYSQL_HOST", "127.0.0.1")
    port = os.environ.get("HER_E2E_MYSQL_PORT", "3307")
    print(f"[compose-bootstrap] targeting mysql://root@{host}:{port}")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ci_bootstrap_frontend_e2e.py")],
        check=False,
    )
    raise SystemExit(result.returncode)
