#!/usr/bin/env python3
"""Tests for layout audit integration in health report.

Verifies that health report includes layout_audit field with:
- total/p0/p1/p2 counts
- root_pollution_count
- multi_generation_conflict boolean
- recommended_mode (fresh/adopt/update/repair/manual)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools import memory_health_report as health_module


def test_health_report_includes_layout_audit_for_clean_project(tmp_path: Path):
    """Clean project should have layout_audit with all fields."""
    # Create a clean project with .memory structure
    project = tmp_path / "clean-project"
    memory_dir = project / ".memory"
    system_dir = memory_dir / "system"
    system_dir.mkdir(parents=True)
    (memory_dir / "manifest.json").write_text(json.dumps({"version": "1.0"}))

    # Create AGENTS.md without markers (modern projects don't need markers in AGENTS.md)
    # This avoids triggering P2 findings from marker detection
    (project / "AGENTS.md").write_text("# Project\nSome agent instructions\n")

    output = tmp_path / "health-report.json"

    # Run health report
    import sys

    old_argv = sys.argv
    try:
        sys.argv = [
            "memory-health-report",
            "--target",
            str(project),
            "--output",
            str(output),
        ]
        result = health_module.main()
        assert result == 0
    finally:
        sys.argv = old_argv

    # Verify report exists and has layout_audit
    assert output.exists()
    report = json.loads(output.read_text())
    assert "layout_audit" in report
    layout = report["layout_audit"]

    # Verify required fields
    assert "total" in layout
    assert "p0" in layout
    assert "p1" in layout
    assert "p2" in layout
    assert "root_pollution_count" in layout
    assert "multi_generation_conflict" in layout
    assert "recommended_mode" in layout

    # Clean project with .memory should have recommended_mode "update" (no issues)
    assert layout["recommended_mode"] in ("update", "repair")  # Allow repair if any P2 findings
    assert layout["multi_generation_conflict"] is False


def test_health_report_detects_root_pollution(tmp_path: Path):
    """Project with root pollution should have correct counts and degraded status."""
    # Create a project with root pollution
    project = tmp_path / "polluted-project"
    project.mkdir()

    # Create a clean .memory structure
    memory_dir = project / ".memory"
    system_dir = memory_dir / "system"
    system_dir.mkdir(parents=True)
    (memory_dir / "manifest.json").write_text(json.dumps({"version": "1.0"}))

    # Create root pollution files
    (project / "status-report.md").write_text("# Status\n")
    (project / "audit-findings.md").write_text("# Audit\n")

    output = tmp_path / "health-report.json"

    import sys

    old_argv = sys.argv
    try:
        sys.argv = [
            "memory-health-report",
            "--target",
            str(project),
            "--output",
            str(output),
        ]
        result = health_module.main()
        assert result == 0
    finally:
        sys.argv = old_argv

    report = json.loads(output.read_text())
    assert "layout_audit" in report
    layout = report["layout_audit"]

    # Should have root pollution findings
    assert layout["root_pollution_count"] >= 1
    assert layout["total"] > 0
    assert layout["p1"] > 0  # P1 for root pollution

    # Status should degrade for layout audit issues rather than hard fail
    assert report["status"] == "degraded"


def test_health_report_detects_multi_generation_conflict(tmp_path: Path):
    """Project with root + workspace memory structures should recommend manual mode."""
    # Create a project with real multi-generation conflict
    # Real conflict = root structures + workspace structures
    project = tmp_path / "multi-gen-project"

    # Create root .memory
    dot_memory = project / ".memory"
    dot_memory.mkdir(parents=True)
    (dot_memory / "manifest.json").write_text(json.dumps({"version": "1.0"}))

    # Create workspace/memory/ (this creates the real conflict)
    workspace_memory = project / "workspace" / "memory"
    workspace_memory.mkdir(parents=True)
    (workspace_memory / "old.json").write_text("{}")

    output = tmp_path / "health-report.json"

    import sys

    old_argv = sys.argv
    try:
        sys.argv = [
            "memory-health-report",
            "--target",
            str(project),
            "--output",
            str(output),
        ]
        result = health_module.main()
        assert result == 0
    finally:
        sys.argv = old_argv

    report = json.loads(output.read_text())
    layout = report["layout_audit"]

    # Should detect multi-generation conflict with workspace
    assert layout["multi_generation_conflict"] is True
    assert layout["has_real_workspace_conflict"] is True
    assert layout["recommended_mode"] == "manual"
    assert layout["p0"] > 0


def test_health_report_valid_current_layout_not_manual(tmp_path: Path):
    """Valid current layout (.memory + memory + project-map) should NOT recommend manual."""
    # Create a project with valid current layout (no workspace conflict)
    project = tmp_path / "valid-current-layout"

    # Create .memory/
    dot_memory = project / ".memory"
    dot_memory.mkdir(parents=True)
    (dot_memory / "manifest.json").write_text(json.dumps({"version": "1.0"}))

    # Create memory/
    legacy_memory = project / "memory"
    legacy_memory.mkdir()
    (legacy_memory / "data.json").write_text("{}")

    # Create project-map/
    project_map = project / "project-map"
    project_map.mkdir()
    (project_map / "map.json").write_text("{}")

    output = tmp_path / "health-report.json"

    import sys

    old_argv = sys.argv
    try:
        sys.argv = [
            "memory-health-report",
            "--target",
            str(project),
            "--output",
            str(output),
        ]
        result = health_module.main()
        assert result == 0
    finally:
        sys.argv = old_argv

    report = json.loads(output.read_text())
    layout = report["layout_audit"]

    # Valid current layout should NOT be manual or critical
    # It can be update, adopt, or repair depending on findings
    assert layout["has_real_workspace_conflict"] is False
    assert layout["recommended_mode"] in ("update", "adopt", "repair")
    assert layout["recommended_mode"] != "manual"


def test_health_report_recommends_fresh_for_clean_project(tmp_path: Path):
    """Truly clean project should recommend fresh mode."""
    project = tmp_path / "truly-clean"
    project.mkdir()

    # Just add README
    (project / "README.md").write_text("# Test\n")

    output = tmp_path / "health-report.json"

    import sys

    old_argv = sys.argv
    try:
        sys.argv = [
            "memory-health-report",
            "--target",
            str(project),
            "--output",
            str(output),
        ]
        result = health_module.main()
        assert result == 0
    finally:
        sys.argv = old_argv

    report = json.loads(output.read_text())
    layout = report["layout_audit"]

    # Clean project without .memory should recommend fresh
    assert layout["total"] == 0
    assert layout["recommended_mode"] == "fresh"


def test_health_report_recommends_adopt_for_legacy_memory(tmp_path: Path):
    """Project with only legacy memory should recommend adopt mode."""
    project = tmp_path / "legacy-project"
    project.mkdir()

    # Create legacy memory structure without .memory
    legacy_memory = project / "memory"
    legacy_memory.mkdir()
    (legacy_memory / "data.json").write_text("{}")

    output = tmp_path / "health-report.json"

    import sys

    old_argv = sys.argv
    try:
        sys.argv = [
            "memory-health-report",
            "--target",
            str(project),
            "--output",
            str(output),
        ]
        result = health_module.main()
        assert result == 0
    finally:
        sys.argv = old_argv

    report = json.loads(output.read_text())
    layout = report["layout_audit"]

    # Project with legacy memory but no .memory should recommend adopt
    assert layout["recommended_mode"] == "adopt"


def test_health_report_skips_denied_root(tmp_path: Path, monkeypatch):
    """Denied root should still skip and not crash."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    output = tmp_path / "health-report.json"

    import sys

    old_argv = sys.argv
    try:
        sys.argv = [
            "memory-health-report",
            "--target",
            str(fake_home),
            "--output",
            str(output),
        ]
        result = health_module.main()
        # Should return 0 without writing output
        assert result == 0
        assert not output.exists()
    finally:
        sys.argv = old_argv


def test_health_report_skips_memory_core_source_repo(tmp_path: Path):
    """Memory-core source repo should skip without crashing."""
    # Create a fake memory-core source repo
    memory_repo = tmp_path / "memory-core"
    nested = memory_repo / "memory_core" / "tools"
    nested.mkdir(parents=True)
    (nested / "memory_hook_gateway.py").write_text("# marker\n", encoding="utf-8")
    (nested / "factory_global_hooks.py").write_text("# marker\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=memory_repo, check=True, capture_output=True, text=True)

    output = tmp_path / "health-report.json"

    import sys

    old_argv = sys.argv
    try:
        sys.argv = [
            "memory-health-report",
            "--target",
            str(memory_repo),
            "--output",
            str(output),
        ]
        result = health_module.main()
        # Should return 0 without writing output
        assert result == 0
        assert not output.exists()
    finally:
        sys.argv = old_argv


def test_determine_recommended_mode_logic():
    """Test the recommended mode logic directly."""
    # Test fresh mode
    assert (
        health_module._determine_recommended_mode(
            total=0, p0=0, p1=0, p2=0, root_pollution_count=0, multi_generation_conflict=False, has_real_workspace_conflict=False, has_dot_memory=False
        )
        == "fresh"
    )

    assert (
        health_module._determine_recommended_mode(
            total=0, p0=0, p1=0, p2=0, root_pollution_count=0, multi_generation_conflict=False, has_real_workspace_conflict=False, has_dot_memory=True
        )
        == "update"
    )

    # Test manual mode for real workspace conflict
    assert (
        health_module._determine_recommended_mode(
            total=5, p0=1, p1=2, p2=2, root_pollution_count=1, multi_generation_conflict=True, has_real_workspace_conflict=True, has_dot_memory=True
        )
        == "manual"
    )

    # Test NOT manual for multi_generation_conflict without workspace (compatibility)
    assert (
        health_module._determine_recommended_mode(
            total=5, p0=1, p1=2, p2=2, root_pollution_count=1, multi_generation_conflict=True, has_real_workspace_conflict=False, has_dot_memory=True
        )
        == "repair"
    )

    # Test adopt mode for legacy without .memory
    assert (
        health_module._determine_recommended_mode(
            total=1, p0=0, p1=1, p2=0, root_pollution_count=0, multi_generation_conflict=False, has_real_workspace_conflict=False, has_dot_memory=False
        )
        == "adopt"
    )

    # Test repair mode for .memory with issues
    assert (
        health_module._determine_recommended_mode(
            total=2, p0=1, p1=0, p2=1, root_pollution_count=0, multi_generation_conflict=False, has_real_workspace_conflict=False, has_dot_memory=True
        )
        == "repair"
    )

    assert (
        health_module._determine_recommended_mode(
            total=1, p0=0, p1=1, p2=0, root_pollution_count=0, multi_generation_conflict=False, has_real_workspace_conflict=False, has_dot_memory=True
        )
        == "repair"
    )

    # Test update mode for clean .memory
    assert (
        health_module._determine_recommended_mode(
            total=0, p0=0, p1=0, p2=0, root_pollution_count=0, multi_generation_conflict=False, has_real_workspace_conflict=False, has_dot_memory=True
        )
        == "update"
    )


def test_run_layout_audit_returns_none_on_import_error(tmp_path: Path, monkeypatch):
    """When audit module unavailable, should return None gracefully."""
    # Mock import to fail by hiding the module and patching __import__
    import builtins

    # Remove the audit module if it's loaded
    saved_module = sys.modules.get("memory_core.tools.audit_project_layout")
    if "memory_core.tools.audit_project_layout" in sys.modules:
        del sys.modules["memory_core.tools.audit_project_layout"]

    # Patch builtins.__import__ to fail for audit_project_layout
    original_import = builtins.__import__

    def failing_import(name, *args, **kwargs):
        if "audit_project_layout" in name:
            raise ImportError(f"No module named '{name}'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", failing_import)

    with pytest.warns(RuntimeWarning, match="not available"):
        result = health_module._run_layout_audit(tmp_path / "test")

    assert result is None

    # Restore module
    if saved_module:
        sys.modules["memory_core.tools.audit_project_layout"] = saved_module


def test_run_layout_audit_returns_degraded_on_exception(tmp_path: Path, monkeypatch):
    """When audit fails with exception, should return degraded info."""
    # Mock audit_project_layout to raise
    import memory_core.tools.audit_project_layout as audit_module

    def failing_audit(*args, **kwargs):
        raise RuntimeError("Disk read error")

    monkeypatch.setattr(audit_module, "audit_project_layout", failing_audit)

    with pytest.warns(RuntimeWarning, match="failed"):
        result = health_module._run_layout_audit(tmp_path / "test")

    assert result is not None
    assert result.get("degraded") is True
    assert "error" in result
    assert "Disk read error" in result["error"]
