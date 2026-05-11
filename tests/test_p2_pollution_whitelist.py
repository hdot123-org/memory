"""Tests for pollution detection whitelist / blacklist (B.Q5-2 + B.Q5-3).

Each test constructs a miniature repository under tmp_path and calls
detect_pollution() directly.  No real-repo state is touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the module under test is importable even when pytest rewrites paths.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _REPO_ROOT / "memory_core" / "tools"
for p in (str(_TOOLS_DIR), str(_REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from validate_memory_system import detect_pollution  # type: ignore


def _create_minimal_repo(tmp_path: Path) -> Path:
    """Create a clean, minimal repo structure under *tmp_path*.

    Includes enough directories to exercise the whitelist rules without
    planting any pollution.
    """
    (tmp_path / "memory_core" / ".memory").mkdir(parents=True)
    (tmp_path / "memory_core" / "memory" / "kb" / "global").mkdir(parents=True)
    (tmp_path / "memory_core" / "project-map").mkdir(parents=True)
    (tmp_path / "archive" / "legacy-workbot" / "kb").mkdir(parents=True)
    (tmp_path / "workspace" / "templates" / ".memory").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "README.md").write_text("# memory-core\n")
    (tmp_path / ".gitignore").write_text("*.pyc\n")
    return tmp_path


class TestCleanRepo:
    """A repo with only whitelisted paths should report zero findings."""

    def test_clean_repo_no_findings(self, tmp_path: Path) -> None:
        _create_minimal_repo(tmp_path)
        findings = detect_pollution(tmp_path)
        assert findings == [], f"Expected no findings, got {findings}"


class TestForbiddenStateFiles:
    """Runtime state files in non-whitelisted locations are errors."""

    def test_state_in_workspace_projects(self, tmp_path: Path) -> None:
        _create_minimal_repo(tmp_path)
        bad = tmp_path / "workspace" / "projects" / "myproj"
        bad.mkdir(parents=True)
        (bad / "STATE.md").write_text("# Project State\n")
        findings = detect_pollution(tmp_path)
        error_findings = [f for f in findings if f["severity"] == "error"]
        assert any(f["path"] == "workspace/projects/myproj/STATE.md" for f in error_findings)

    def test_state_at_repo_root(self, tmp_path: Path) -> None:
        _create_minimal_repo(tmp_path)
        (tmp_path / "STATE.md").write_text("# State\n")
        findings = detect_pollution(tmp_path)
        error_findings = [f for f in findings if f["severity"] == "error"]
        assert any(f["path"] == "STATE.md" for f in error_findings)

    def test_plan_file_at_repo_root(self, tmp_path: Path) -> None:
        _create_minimal_repo(tmp_path)
        (tmp_path / "PLAN.md").write_text("# Plan\n")
        findings = detect_pollution(tmp_path)
        error_findings = [f for f in findings if f["severity"] == "error"]
        assert any("PLAN.md" in f["path"] for f in error_findings)


class TestWhitelistedLocations:
    """Canonical locations may contain state files without flagging."""

    def test_state_in_memory_core_dot_memory(self, tmp_path: Path) -> None:
        root = _create_minimal_repo(tmp_path)
        mem_dir = root / "memory_core" / ".memory"
        (mem_dir / "STATE.md").write_text("# State\n")
        (mem_dir / "PLAN.md").write_text("# Plan\n")
        (mem_dir / "CANONICAL.md").write_text("# Canonical\n")
        findings = detect_pollution(tmp_path)
        error_findings = [f for f in findings if f["severity"] == "error"]
        assert not any(
            ".memory/STATE.md" in f["path"] or ".memory/PLAN.md" in f["path"] or ".memory/CANONICAL.md" in f["path"]
            for f in error_findings
        ), f"Unexpected finding: {error_findings}"

    def test_state_in_archive_legacy_workbot(self, tmp_path: Path) -> None:
        root = _create_minimal_repo(tmp_path)
        wb_mem = root / "archive" / "legacy-workbot" / ".memory"
        wb_mem.mkdir(parents=True)
        (wb_mem / "STATE.md").write_text("# Archived State\n")
        (wb_mem / "PLAN.md").write_text("# Archived Plan\n")
        findings = detect_pollution(tmp_path)
        error_findings = [f for f in findings if f["severity"] == "error"]
        assert not any(
            "legacy-workbot" in f["path"] and "STATE.md" in f["path"]
            for f in error_findings
        ), f"Unexpected finding: {error_findings}"

    def test_state_in_workspace_templates_dot_memory(self, tmp_path: Path) -> None:
        """workspace/templates/.memory/ is a canonical template location — OK."""
        root = _create_minimal_repo(tmp_path)
        tpl_mem = root / "workspace" / "templates" / ".memory"
        (tpl_mem / "STATE.md").write_text("# Template State\n")
        (tpl_mem / "PLAN.md").write_text("# Template Plan\n")
        findings = detect_pollution(tmp_path)
        error_findings = [f for f in findings if f["severity"] == "error"]
        assert not any(
            "templates/.memory" in f["path"]
            for f in error_findings
        ), f"Unexpected finding: {error_findings}"


class TestBusinessStringPollution:
    """Business keywords in newly created runtime content should be flagged."""

    def test_axonhub_in_project_map(self, tmp_path: Path) -> None:
        root = _create_minimal_repo(tmp_path)
        pm = root / "memory_core" / "project-map"
        (pm / "test-map.md").write_text("# Project Map\n\nThis is for axonhub integration.\n")
        findings = detect_pollution(tmp_path)
        error_findings = [f for f in findings if f["severity"] == "error"]
        assert any(
            "business-string" in f["rule"] and "axonhub" in f.get("detail", "").lower()
            for f in error_findings
        )

    def test_workbot_in_global_kb(self, tmp_path: Path) -> None:
        root = _create_minimal_repo(tmp_path)
        kb = root / "memory_core" / "memory" / "kb" / "global"
        (kb / "new-guide.md").write_text("# Guide\n\nworkbot-specific instructions here.\n")
        findings = detect_pollution(tmp_path)
        error_findings = [f for f in findings if f["severity"] == "error"]
        assert any(
            "business-string" in f["rule"] and "workbot" in f.get("detail", "").lower()
            for f in error_findings
        )


class TestUnexpectedMemoryDirs:
    """.memory/ directories outside canonical locations are flagged."""

    def test_memory_dir_in_workspace_projects(self, tmp_path: Path) -> None:
        root = _create_minimal_repo(tmp_path)
        proj_mem = root / "workspace" / "projects" / "alpha" / ".memory"
        proj_mem.mkdir(parents=True)
        (proj_mem / "STATE.md").write_text("# State\n")
        findings = detect_pollution(tmp_path)
        error_findings = [f for f in findings if f["severity"] == "error"]
        assert any(
            f["rule"] == "unexpected-memory-dir" for f in error_findings
        ), f"Expected unexpected-memory-dir finding, got {error_findings}"

    def test_memory_dir_at_repo_root(self, tmp_path: Path) -> None:
        root = _create_minimal_repo(tmp_path)
        (root / ".memory").mkdir()
        (root / ".memory" / "STATE.md").write_text("# State\n")
        findings = detect_pollution(tmp_path)
        error_findings = [f for f in findings if f["severity"] == "error"]
        # .memory at repo root should be flagged as unexpected
        assert any(
            f["rule"] == "unexpected-memory-dir" for f in error_findings
        ), f"Expected unexpected-memory-dir for root .memory/, got {error_findings}"
