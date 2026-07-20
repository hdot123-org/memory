"""Tests for _enrich_project_info_from_config 4 detector extractions.

VAL-M2-003: _enrich_project_info_from_config (CC 37 -> <=20).
This function has 0 direct tests in baseline; these tests must pass
BEFORE refactoring begins to establish behavior baseline.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_core.tools.project_probe import ProjectInfo


@pytest.fixture
def project_info() -> ProjectInfo:
    return ProjectInfo()


# ===================================================================
# _detect_pyproject tests
# ===================================================================

class TestDetectPyproject:
    """Tests for pyproject.toml detection logic."""

    def test_detects_python_with_setuptools(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "pyproject.toml").write_text(
            '[build-system]\nrequires = ["setuptools"]\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.primary_language == "Python"

    def test_detects_python_with_poetry(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "pyproject.toml").write_text(
            '[tool.poetry]\nname = "myapp"\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.primary_language == "Python"

    def test_detects_python_with_project_section(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\nversion = "0.1.0"\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.primary_language == "Python"

    def test_detects_web_api_with_fastapi(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["fastapi"]\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.primary_language == "Python"
        assert project_info.project_type == "web/api"

    def test_detects_web_api_with_flask(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["flask"]\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.project_type == "web/api"

    def test_detects_web_api_with_django(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["django"]\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.project_type == "web/api"

    def test_detects_library_with_pytest(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "mylib"\n[tool.pytest]\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.primary_language == "Python"
        assert project_info.project_type == "library"

    def test_no_detection_when_no_pyproject(self, tmp_path: Path, project_info: ProjectInfo):
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.primary_language == ""

    def test_does_not_overwrite_existing_language(self, tmp_path: Path):
        info = ProjectInfo(primary_language="JavaScript")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, info)
        assert info.primary_language == "JavaScript"

    def test_does_not_overwrite_existing_project_type(self, tmp_path: Path):
        info = ProjectInfo(project_type="cli")
        (tmp_path / "pyproject.toml").write_text(
            '[project]\ndependencies = ["fastapi"]\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, info)
        assert info.project_type == "cli"


# ===================================================================
# _detect_package_json tests
# ===================================================================

class TestDetectPackageJson:
    """Tests for package.json detection logic."""

    def test_detects_javascript_language(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "test"}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.primary_language == "JavaScript"

    def test_detects_frontend_with_next(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"next": "^13.0"}}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.project_type == "frontend"

    def test_detects_frontend_with_react(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^18.0"}}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.project_type == "frontend"

    def test_detects_frontend_with_vue(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"vue": "^3.0"}}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.project_type == "frontend"

    def test_detects_web_api_with_express(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "package.json").write_text(
            json.dumps({"dependencies": {"express": "^4.0"}}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.project_type == "web/api"

    def test_detects_library_with_main_field(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "mylib", "main": "index.js"}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.project_type == "library"

    def test_detects_node_default_type(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "myscript"}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.project_type == "node"

    def test_typescript_upgrade_with_typescript_dep(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "ts-app",
                "devDependencies": {"typescript": "^5.0"},
                "scripts": {"build": "tsc"},
            }),
            encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.primary_language == "TypeScript"

    def test_toolchain_with_build_and_test(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "app",
                "scripts": {"build": "tsc", "test": "jest"},
            }),
            encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        toolchain_names = [t["name"] for t in project_info.toolchain]
        assert "npm" in toolchain_names

    def test_typescript_toolchain_entry(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "ts-app",
                "devDependencies": {"ts-node": "^10.0"},
                "scripts": {"build": "ts-node build.ts"},
            }),
            encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.primary_language == "TypeScript"
        toolchain_names = [t["name"] for t in project_info.toolchain]
        assert "TypeScript" in toolchain_names

    def test_devdeps_also_count_for_detection(self, tmp_path: Path, project_info: ProjectInfo):
        """Dependencies from devDependencies should also trigger detection."""
        (tmp_path / "package.json").write_text(
            json.dumps({
                "name": "app",
                "devDependencies": {"gatsby": "^5.0"},
            }),
            encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.project_type == "frontend"

    def test_does_not_overwrite_toolchain(self, tmp_path: Path):
        info = ProjectInfo(toolchain=[{"name": "make", "config": "Makefile"}])
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "app", "scripts": {"build": "tsc"}}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, info)
        assert len(info.toolchain) == 1
        assert info.toolchain[0]["name"] == "make"


# ===================================================================
# _detect_tsconfig tests
# ===================================================================

class TestDetectTsconfig:
    """Tests for tsconfig.json detection logic."""

    def test_detects_typescript(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "tsconfig.json").write_text(
            json.dumps({"compilerOptions": {"target": "es2020"}}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.primary_language == "TypeScript"

    def test_sets_toolchain(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "tsconfig.json").write_text(
            json.dumps({"compilerOptions": {}}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert len(project_info.toolchain) == 1
        assert project_info.toolchain[0]["name"] == "TypeScript"
        assert project_info.toolchain[0]["config"] == "tsconfig.json"

    def test_does_not_overwrite_language(self, tmp_path: Path):
        info = ProjectInfo(primary_language="Python")
        (tmp_path / "tsconfig.json").write_text(
            json.dumps({"compilerOptions": {}}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, info)
        assert info.primary_language == "Python"

    def test_does_not_overwrite_toolchain(self, tmp_path: Path):
        info = ProjectInfo(toolchain=[{"name": "make", "config": "Makefile"}])
        (tmp_path / "tsconfig.json").write_text(
            json.dumps({"compilerOptions": {}}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, info)
        assert len(info.toolchain) == 1
        assert info.toolchain[0]["name"] == "make"


# ===================================================================
# _detect_cargo tests
# ===================================================================

class TestDetectCargo:
    """Tests for Cargo.toml (Rust) detection logic."""

    def test_detects_rust(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "myapp"\nversion = "0.1.0"\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.primary_language == "Rust"

    def test_sets_project_type_library(self, tmp_path: Path, project_info: ProjectInfo):
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "mylib"\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        assert project_info.project_type == "library"

    def test_does_not_overwrite_language(self, tmp_path: Path):
        info = ProjectInfo(primary_language="Python")
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "mylib"\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, info)
        assert info.primary_language == "Python"

    def test_does_not_overwrite_project_type(self, tmp_path: Path):
        info = ProjectInfo(project_type="cli")
        (tmp_path / "Cargo.toml").write_text(
            '[package]\nname = "mylib"\n', encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, info)
        assert info.project_type == "cli"


# ===================================================================
# Integration / ordering tests
# ===================================================================

class TestEnrichOrdering:
    """Tests for detection ordering and non-ProjectInfo guard."""

    def test_non_project_info_noop(self, tmp_path: Path):
        class FakeInfo:
            primary_language = ""
        (tmp_path / "pyproject.toml").write_text('[project]\n', encoding="utf-8")
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, FakeInfo())  # should not raise

    def test_pyproject_before_package_json(self, tmp_path: Path, project_info: ProjectInfo):
        """When both pyproject.toml and package.json exist, pyproject sets Python first."""
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\n', encoding="utf-8"
        )
        (tmp_path / "package.json").write_text(
            json.dumps({"name": "myapp"}), encoding="utf-8"
        )
        from memory_core.tools.init_project_memory import _enrich_project_info_from_config
        _enrich_project_info_from_config(tmp_path, project_info)
        # pyproject runs first -> Python, then package.json sees language already set
        assert project_info.primary_language == "Python"
