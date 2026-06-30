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

# 读取 MySQL 密钥文件（如果存在）
mysql_password_file = os.environ.get("MYSQL_ROOT_PASSWORD_FILE")
if mysql_password_file and os.path.exists(mysql_password_file):
    with open(mysql_password_file) as f:
        mysql_password = f.read().strip()
    # 设置 MySQL 密码环境变量（供 outer_system_mysql_schema.py 使用）
    os.environ["MYSQL_ROOT_PASSWORD"] = mysql_password
    print(f"[compose-bootstrap] MySQL password loaded from {mysql_password_file}")

if __name__ == "__main__":
    host = os.environ.get("HER_E2E_MYSQL_HOST", "127.0.0.1")
    port = os.environ.get("HER_E2E_MYSQL_PORT", "3307")
    os.environ.setdefault("HER_E2E_BOOTSTRAP_RESET", "0")
    os.environ.setdefault("HER_E2E_BOOTSTRAP_SEED_DEMO", "0")
    print(f"[compose-bootstrap] targeting mysql://root@{host}:{port}")
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "ci_bootstrap_frontend_e2e.py")],
        check=False,
    )
    raise SystemExit(result.returncode)
