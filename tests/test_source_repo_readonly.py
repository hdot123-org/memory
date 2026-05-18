"""Tests for M3 source repo readonly context-package behavior.

Verifies:
- Source repo fixture → hook outputs readonly context-package
- Context-package contains rules
- git status shows no changes after hook run
- File mtime unchanged after hook run
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture()
def source_repo(tmp_path: Path) -> Path:
    """Create a fake memory-core source repo with marker files.

    Uses a unique marker directory name to avoid Python import confusion.
    """
    memory_repo = tmp_path / "source-repo"
    nested = memory_repo / "memory_core" / "tools"
    nested.mkdir(parents=True)
    (nested / "memory_hook_gateway.py").write_text("# marker\n", encoding="utf-8")
    (nested / "factory_global_hooks.py").write_text("# marker\n", encoding="utf-8")
    (nested / "codex_global_hooks.py").write_text("# marker\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=memory_repo, check=True, capture_output=True, text=True)
    return memory_repo


def _call_build_readonly_package(cwd: Path, host: str = "factory", event: str = "session-start") -> dict:
    """Call _build_readonly_source_repo_package directly (no subprocess)."""
    from memory_core.tools.memory_hook_gateway import _build_readonly_source_repo_package

    return _build_readonly_source_repo_package(cwd, host, event)


def _run_gateway_subprocess(cwd: Path, host: str = "factory", event: str = "session-start") -> subprocess.CompletedProcess[str]:
    """Run gateway via subprocess with explicit PYTHONPATH to avoid cwd import pollution."""
    payload = json.dumps({"cwd": str(cwd)})
    env = dict(os.environ)
    # Ensure the installed memory_core is used, not any local one
    env["PYTHONPATH"] = str(REPO_ROOT)
    # Set MEMORY_HOOK env vars so gateway discovers cwd correctly
    env["MEMORY_HOOK_PREFER_EXTERNAL_CWD"] = "1"
    env["MEMORY_HOOK_ORIGINAL_CWD"] = str(cwd)
    return subprocess.run(
        [sys.executable, "-m", "memory_core.tools.memory_hook_gateway", "--host", host, "--event", event],
        input=payload,
        cwd=str(REPO_ROOT),  # Run from repo root, not from source_repo tmp
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
        env=env,
    )


class TestSourceRepoReadonlyContextPackage:
    """Test that the gateway outputs a readonly context-package for source repos."""

    def test_build_readonly_package_structure(self, source_repo: Path) -> None:
        """_build_readonly_source_repo_package returns proper readonly structure."""
        pkg = _call_build_readonly_package(source_repo)
        assert pkg["package_kind"] == "source-repo-rules"
        assert pkg["mode"] == "read-only"
        assert pkg["allowed_writes"] == {}
        assert pkg["status"] == "ok"
        assert pkg["project_root"] == str(source_repo)

    def test_readonly_package_contains_rules(self, source_repo: Path) -> None:
        """Readonly package contains ownership rules and protected paths."""
        pkg = _call_build_readonly_package(source_repo)
        rules = pkg["rules"]
        assert "description" in rules
        assert "memory-core source repository" in rules["description"]
        assert "ownership_domains" in rules
        assert isinstance(rules["ownership_domains"], list)
        assert len(rules["ownership_domains"]) > 0
        assert "protected_paths" in rules
        assert isinstance(rules["protected_paths"], list)
        # Verify key protected paths are listed
        protected = rules["protected_paths"]
        assert any("memory/docs" in p for p in protected)
        assert any(".memory" in p for p in protected)

    def test_readonly_package_host_and_event(self, source_repo: Path) -> None:
        """Readonly package includes the correct host and event."""
        pkg = _call_build_readonly_package(source_repo, host="codex", event="prompt-submit")
        assert pkg["host"] == "codex"
        assert pkg["event"] == "prompt-submit"

    def test_ownership_domains_in_rules_have_required_fields(self, source_repo: Path) -> None:
        """Each ownership domain in rules has name, path, level, recursive."""
        pkg = _call_build_readonly_package(source_repo)
        for domain in pkg["rules"]["ownership_domains"]:
            assert "name" in domain
            assert "path" in domain
            assert "level" in domain
            assert "recursive" in domain

    def test_no_memory_directory_created(self, source_repo: Path) -> None:
        """Building readonly package does not create .memory/ or memory/ directories."""
        assert not (source_repo / ".memory").exists()
        assert not (source_repo / "memory").exists()

        _call_build_readonly_package(source_repo)

        assert not (source_repo / ".memory").exists(), ".memory/ should not be created"
        assert not (source_repo / "memory").exists(), "memory/ should not be created"

    def test_no_artifacts_directory_created(self, source_repo: Path) -> None:
        """Building readonly package does not create artifacts/ directory."""
        _call_build_readonly_package(source_repo)
        assert not (source_repo / "artifacts").exists(), "artifacts/ should not be created"

    def test_git_status_unchanged_after_readonly_package_build(self, source_repo: Path) -> None:
        """git status shows no changes after readonly package build."""
        # Setup git state
        subprocess.run(["git", "add", "."], cwd=source_repo, check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "-c", "user.email=test@test.com", "-c", "user.name=Test", "commit", "-m", "init"],
            cwd=source_repo,
            check=True,
            capture_output=True,
            text=True,
        )

        before = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=source_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert before.stdout.strip() == ""

        # Build readonly package (this is a pure function, no side effects)
        _call_build_readonly_package(source_repo)

        after = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=source_repo,
            check=True,
            capture_output=True,
            text=True,
        )
        assert after.stdout.strip() == "", "git status should show no changes after readonly package build"

    def test_mtime_unchanged_after_readonly_package_build(self, source_repo: Path) -> None:
        """File mtime unchanged after readonly package build."""
        marker = source_repo / "memory_core" / "tools" / "test_marker.txt"
        marker.write_text("test\n", encoding="utf-8")
        time.sleep(0.05)

        mtime_before = marker.stat().st_mtime
        _call_build_readonly_package(source_repo)
        mtime_after = marker.stat().st_mtime
        assert mtime_after == mtime_before, "File mtime should be unchanged"


class TestSourceRepoDetectionViaSubprocess:
    """Test that gateway main() produces readonly context-package when running in source repo."""

    def test_gateway_subprocess_outputs_readonly_package(self, source_repo: Path) -> None:
        """Gateway subprocess outputs readonly context-package for source repo."""
        proc = _run_gateway_subprocess(source_repo)
        assert proc.returncode == 0, f"stderr: {proc.stderr}"
        output = json.loads(proc.stdout)
        assert output["package_kind"] == "source-repo-rules"
        assert output["mode"] == "read-only"
        assert output["allowed_writes"] == {}

    def test_gateway_subprocess_contains_rules(self, source_repo: Path) -> None:
        """Gateway subprocess output contains ownership rules."""
        proc = _run_gateway_subprocess(source_repo)
        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        assert "rules" in output
        assert "ownership_domains" in output["rules"]
        assert "protected_paths" in output["rules"]


class TestSourceRepoIsMemoryCoreDetection:
    """Test is_memory_core_source_repo from ownership module."""

    def test_detects_source_repo(self, source_repo: Path) -> None:
        from memory_core.ownership import is_memory_core_source_repo
        assert is_memory_core_source_repo(source_repo) is True

    def test_normal_project_not_detected(self, tmp_path: Path) -> None:
        from memory_core.ownership import is_memory_core_source_repo
        normal = tmp_path / "normal-project"
        normal.mkdir()
        subprocess.run(["git", "init"], cwd=normal, check=True, capture_output=True, text=True)
        assert is_memory_core_source_repo(normal) is False

    def test_subdirectory_detected(self, source_repo: Path) -> None:
        from memory_core.ownership import is_memory_core_source_repo
        subdir = source_repo / "subdir"
        subdir.mkdir()
        assert is_memory_core_source_repo(subdir) is True

    def test_detects_by_factory_hooks_marker(self, tmp_path: Path) -> None:
        from memory_core.ownership import is_memory_core_source_repo
        repo = tmp_path / "repo"
        nested = repo / "memory_core" / "tools"
        nested.mkdir(parents=True)
        (nested / "factory_global_hooks.py").write_text("# marker\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
        assert is_memory_core_source_repo(repo) is True

    def test_detects_by_codex_hooks_marker(self, tmp_path: Path) -> None:
        from memory_core.ownership import is_memory_core_source_repo
        repo = tmp_path / "repo"
        nested = repo / "memory_core" / "tools"
        nested.mkdir(parents=True)
        (nested / "codex_global_hooks.py").write_text("# marker\n", encoding="utf-8")
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
        assert is_memory_core_source_repo(repo) is True

    def test_detects_by_ownership_module(self, tmp_path: Path) -> None:
        from memory_core.ownership import is_memory_core_source_repo
        repo = tmp_path / "repo"
        nested = repo / "memory_core"
        nested.mkdir(parents=True)
        (nested / "ownership.py").write_text("# marker\n", encoding="utf-8")
        assert is_memory_core_source_repo(repo) is True
