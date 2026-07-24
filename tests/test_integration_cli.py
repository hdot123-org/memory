"""Integration tests: CLI tools invoked as subprocesses.

These tests exercise the full CLI entry points end-to-end, verifying
that the packaged commands work correctly when invoked via python -m.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory for CLI integration tests."""
    (tmp_project := tmp_path / "test-project").mkdir()
    (tmp_project / ".git").mkdir()  # fake git root
    return tmp_project


class TestMemoryInitCLI:
    """Integration tests for memory-init CLI."""

    def test_init_dry_run(self, tmp_project: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.init_project_memory",
             "--target", str(tmp_project), "--dry-run", "--json"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data.get("dry_run") is True or data.get("action_taken") == "dry-run"

    def test_init_creates_structure(self, tmp_project: Path) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.init_project_memory",
             "--target", str(tmp_project), "--json"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert (tmp_project / "memory" / "system").is_dir()
        assert (tmp_project / "memory" / "system" / "adapter.toml").is_file()

    def test_init_mode_adopt(self, tmp_project: Path) -> None:
        # Create existing structure first
        (tmp_project / "memory" / "system").mkdir(parents=True)
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.init_project_memory",
             "--target", str(tmp_project), "--mode", "adopt", "--json"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_init_version_flag(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.init_project_memory", "--version"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0
        assert "0.9.1" in result.stdout


class TestMemoryValidateCLI:
    """Integration tests for memory-validate CLI."""

    def test_validate_initialized_project(self, tmp_project: Path) -> None:
        # First init the project
        subprocess.run(
            [sys.executable, "-m", "memory_core.tools.init_project_memory",
             "--target", str(tmp_project), "--json"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.validate_project_memory",
             "--target", str(tmp_project), "--json"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        data = json.loads(result.stdout)
        assert data.get("status") == "ok" or data.get("passed", 0) > 0


class TestMemoryConsistencyCheckCLI:
    """Integration tests for memory-consistency-check CLI."""

    def test_consistency_check_on_repo(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.consistency_check", "--json"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        data = json.loads(result.stdout)
        assert isinstance(data, dict)
        assert "errors" in data or "status" in data


class TestMemoryAuditLayoutCLI:
    """Integration tests for memory-audit-layout CLI."""

    def test_audit_layout_on_repo(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.audit_project_layout",
             "--target", str(REPO_ROOT), "--json"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
