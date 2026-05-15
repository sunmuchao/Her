from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import her_monorepo_bootstrap as bootstrap
import setuptools


REPO_ROOT = Path(__file__).resolve().parents[1]


class _FakeEntryPoint:
    def __init__(self, name: str, group: str = "console_scripts") -> None:
        self.name = name
        self.group = group


class _FakeDistribution:
    def __init__(self, name: str, *, version: str = "0.1.0", entry_points: list[_FakeEntryPoint] | None = None) -> None:
        self.metadata = {"Name": name}
        self.version = version
        self.entry_points = list(entry_points or [])

    def locate_file(self, path: str) -> Path:
        return Path("/virtual/site-packages") / path


def _load_check_skill_packaging_module():
    script_path = REPO_ROOT / "scripts" / "check_skill_packaging.py"
    spec = importlib.util.spec_from_file_location("test_check_skill_packaging", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_check_installed_runtime_module():
    script_path = REPO_ROOT / "scripts" / "check_installed_runtime.py"
    spec = importlib.util.spec_from_file_location("test_check_installed_runtime", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_bootstrap_detects_packaged_skill_layout(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "match_domain").mkdir(parents=True)
    (repo_root / "partner_search").mkdir()
    (repo_root / "persona_memory_sync").mkdir()
    anchor = repo_root / "external-systems" / "partner-recommendation-system" / "recommendation_system" / "service.py"
    anchor.parent.mkdir(parents=True)

    monkeypatch.delenv("HER_REPO_ROOT", raising=False)
    original_sys_path = list(sys.path)
    sys.path[:] = [item for item in sys.path if item != str(repo_root)]
    try:
        resolved = bootstrap.ensure_her_repo_on_sys_path(anchor)
    finally:
        sys.path[:] = original_sys_path

    assert resolved == repo_root


def test_bootstrap_keeps_legacy_local_skills_layout_support(tmp_path, monkeypatch) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "match_domain").mkdir(parents=True)
    (repo_root / "local-skills" / "partner-search").mkdir(parents=True)
    (repo_root / "local-skills" / "persona-memory-sync").mkdir(parents=True)
    anchor = repo_root / "external-systems" / "partner-http-gateway" / "gateway" / "app.py"
    anchor.parent.mkdir(parents=True)

    monkeypatch.delenv("HER_REPO_ROOT", raising=False)
    original_sys_path = list(sys.path)
    sys.path[:] = [item for item in sys.path if item != str(repo_root)]
    try:
        resolved = bootstrap.ensure_her_repo_on_sys_path(anchor)
    finally:
        sys.path[:] = original_sys_path

    assert resolved == repo_root


def test_check_skill_packaging_reports_module_import_errors(monkeypatch) -> None:
    module = _load_check_skill_packaging_module()

    def failing_import(name: str):
        raise ModuleNotFoundError(f"missing {name}")

    monkeypatch.setattr(module.importlib, "import_module", failing_import)
    summary = module._module_summary("partner_search", ["search_profiles"])  # noqa: SLF001

    assert summary["module"] == "partner_search"
    assert summary["file"] is None
    assert summary["has_attributes"] == {"search_profiles": False}
    assert "ModuleNotFoundError" in str(summary["import_error"])


def test_check_skill_packaging_tracks_console_script_provider(monkeypatch) -> None:
    module = _load_check_skill_packaging_module()
    fake_distributions = [
        _FakeDistribution(
            "her",
            entry_points=[_FakeEntryPoint("partner-search"), _FakeEntryPoint("persona-memory-sync")],
        )
    ]
    monkeypatch.setattr(module.importlib.metadata, "distributions", lambda: fake_distributions)

    summary = module._console_script_summary(  # noqa: SLF001
        "partner-search",
        expected_distribution="her",
    )

    assert summary == {
        "name": "partner-search",
        "installed": True,
        "provider": "her",
        "owned_by_expected_distribution": True,
    }


def test_check_installed_runtime_reports_import_errors(monkeypatch) -> None:
    module = _load_check_installed_runtime_module()

    def failing_import(name: str):
        raise ModuleNotFoundError(f"missing {name}")

    monkeypatch.setattr(module.importlib, "import_module", failing_import)
    summary = module._module_summary("discovery_system.service")  # noqa: SLF001

    assert summary == {
        "module": "discovery_system.service",
        "file": None,
        "import_error": "ModuleNotFoundError: missing discovery_system.service",
    }


def test_check_installed_runtime_targets_discovery_service() -> None:
    module = _load_check_installed_runtime_module()
    assert "discovery_system.service" in module.TARGET_MODULES


def test_setup_py_declares_expected_console_scripts(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_setup(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(setuptools, "setup", fake_setup)
    script_path = REPO_ROOT / "setup.py"
    spec = importlib.util.spec_from_file_location("test_setup_py", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    spec.loader.exec_module(module)

    assert captured["name"] == "her"
    assert captured["python_requires"] == ">=3.10"
    assert "discovery_system" in captured["packages"]
    assert "profile_service" in captured["packages"]
    assert "her_repo_path_bootstrap" in captured["py_modules"]
    assert captured["package_dir"]["discovery_system"] == "external-systems/partner-discovery-system/discovery_system"
    assert captured["entry_points"] == {
        "console_scripts": [
            "partner-search=partner_search.search_candidates:main",
            "persona-memory-sync=persona_memory_sync.cli:main",
        ]
    }


def test_pyproject_includes_profile_service_package() -> None:
    contents = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"profile_service*"' in contents
    assert '"her_repo_path_bootstrap"' in contents
