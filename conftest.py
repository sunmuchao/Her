"""Pytest bootstrap for repository-local imports."""

from __future__ import annotations

from pathlib import Path

from her_monorepo_bootstrap import ensure_her_repo_on_sys_path
from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path

REPO_ROOT = ensure_her_repo_on_sys_path(Path(__file__))
ensure_partner_system_roots_on_sys_path(REPO_ROOT)
