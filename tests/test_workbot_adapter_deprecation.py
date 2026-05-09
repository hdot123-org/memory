"""Tests for workbot_runtime_profile deprecation warning and sentinel check.

These tests monkeypatch repo_root/workspace_root to isolated temp dirs
to avoid reading real repository files.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest


def _make_fake_workspace(tmp_path: Path) -> tuple[Path, Path]:
    """Create minimal fake repo_root + workspace_root with kb files."""
    repo_root = tmp_path / "repo"
    workspace_root = repo_root / "memory_core"
    workspace_root.mkdir(parents=True)

    kb_global = workspace_root / "memory" / "kb" / "global"
    kb_global.mkdir(parents=True)

    # Create the 4 sentinel files
    (kb_global / "workbot-truth-model.md").write_text("truth")
    (kb_global / "workbot-memory-system.md").write_text("system")
    (kb_global / "workbot-hook-contract.md").write_text("contract")
    (kb_global / "workbot-policy-pack.json").write_text("{}")

    # Create other files referenced by the profile (minimal stubs)
    project_map = workspace_root / "project-map"
    project_map.mkdir(parents=True)
    (project_map / "INDEX.md").write_text("# index")
    (project_map / "legal-core-map.md").write_text("# legal")
    (project_map / "ingestion-registry-map.md").write_text("# ingestion")
    (kb_global / "workbot-project-map-governance.md").write_text("governance")
    (kb_global / "workbot-memory-routing.md").write_text("routing")

    kb_projects = workspace_root / "memory" / "kb" / "projects"
    kb_projects.mkdir(parents=True)
    (kb_projects / "workbot.md").write_text("workbot")
    (kb_projects / "AEdu.md").write_text("AEdu")
    (kb_projects / "platform-capabilities.md").write_text("pcap")

    kb_lessons = workspace_root / "memory" / "kb" / "lessons"
    kb_lessons.mkdir(parents=True)
    (kb_lessons / "memory-docs-immutable.md").write_text("immutable")
    (kb_lessons / "pm-bot-crawl4ai-runtime-path.md").write_text("crawl4ai")

    # Decision refs
    kb_decisions = workspace_root / "memory" / "kb" / "decisions"
    kb_decisions.mkdir(parents=True)
    (kb_decisions / "INDEX.md").write_text("# decisions")

    # Various INDEX/docs stubs
    (workspace_root / "INDEX.md").write_text("# index")
    (workspace_root / "NOW.md").write_text("# now")
    (workspace_root / "memory" / "kb" / "INDEX.md").write_text("# kb")
    docs = workspace_root / "memory" / "docs"
    docs.mkdir(parents=True)
    (docs / "INDEX.md").write_text("# docs")
    (workspace_root / "memory" / "inbox.md").write_text("# inbox")
    (workspace_root / "memory" / "docs" / "记忆系统全景文档.md").write_text("全景")
    (workspace_root / "memory" / "log").mkdir(parents=True)
    (workspace_root / "memory" / "system").mkdir(parents=True)

    # AEdu directory
    aedu = repo_root / "AEdu"
    (aedu / "00_导航与管理").mkdir(parents=True)
    (aedu / "00_导航与管理" / "KB+INGEST 模块级开发准入评审单.md").write_text("kb")
    (aedu / "00_导航与管理" / "SIM模块级开发准入评审单.md").write_text("sim")
    (aedu / "12_实施与试点运营").mkdir(parents=True)
    (aedu / "12_实施与试点运营" / "09_KB+INGEST 试点范围与责任边界.md").write_text("pilot")
    (aedu / "06_数据接入与事件流").mkdir(parents=True)
    (aedu / "06_数据接入与事件流" / "07_学习事件生成标准.md").write_text("std")
    (aedu / "06_数据接入与事件流" / "12_输入源映射表.md").write_text("map")
    (aedu / "11_系统架构与工程实现").mkdir(parents=True)
    (aedu / "11_系统架构与工程实现" / "22_KB+INGEST-TWIN输入契约.md").write_text("contract")
    (aedu / "11_系统架构与工程实现" / "21_KB+INGEST 端到端样例集.md").write_text("samples")
    (aedu / "11_系统架构与工程实现" / "24_TWIN端到端样例集.md").write_text("twin")
    (aedu / "scripts").mkdir(parents=True)
    (aedu / "scripts" / "validate_kb_closure.py").write_text("# validate")

    # project dirs
    (workspace_root / "projects").mkdir(parents=True)
    (workspace_root / "projects" / "AEdu").mkdir(parents=True)
    (workspace_root / "projects" / "AEdu" / "INDEX.md").write_text("# aedu")
    (workspace_root / "artifacts").mkdir(parents=True)
    (workspace_root / "tools").mkdir(parents=True)

    # Other dirs referenced
    (repo_root / "tests").mkdir(parents=True)
    (repo_root / "app").mkdir(parents=True)
    (repo_root / "agents").mkdir(parents=True)
    (repo_root / "gpt-web-to").mkdir(parents=True)
    (workspace_root / "projects" / "app").mkdir(parents=True)
    (workspace_root / "projects" / "agents").mkdir(parents=True)
    (workspace_root / "projects" / "skills").mkdir(parents=True)

    (workspace_root / "memory" / "docs" / "research" / "projects" / "AEdu").mkdir(parents=True)
    (workspace_root / "memory" / "docs" / "research" / "projects" / "AEdu" / "INDEX.md").write_text("# aedu-research")
    (workspace_root / "projects" / "AEdu" / "INDEX.md").write_text("# aedu-project")

    return repo_root, workspace_root


def test_workbot_runtime_profile_emits_deprecation_warning(tmp_path):
    """Calling build_workbot_runtime_profile always emits DeprecationWarning."""
    from memory_core.tools.memory_hook_adapters.workbot_runtime_profile import (
        build_workbot_runtime_profile,
    )

    repo_root, workspace_root = _make_fake_workspace(tmp_path)

    with pytest.warns(DeprecationWarning, match="workbot adapter is deprecated"):
        build_workbot_runtime_profile(repo_root, workspace_root)


def test_workbot_runtime_profile_warns_when_kb_files_missing(tmp_path, caplog):
    """When sentinel kb files don't exist, a WARNING log is emitted."""
    from memory_core.tools.memory_hook_adapters.workbot_runtime_profile import (
        build_workbot_runtime_profile,
    )

    # Create a workspace with NO kb files at all
    repo_root = tmp_path / "repo"
    workspace_root = repo_root / "memory_core"
    workspace_root.mkdir(parents=True)
    # No kb files created — all 4 sentinel files will be missing

    caplog.set_level(logging.WARNING, logger="memory_core.tools.memory_hook_adapters.workbot_runtime_profile")

    with pytest.warns(DeprecationWarning):
        build_workbot_runtime_profile(repo_root, workspace_root)

    assert any("kb file(s) missing" in r.message for r in caplog.records)
    assert any("archive/legacy-workbot/kb/" in r.message for r in caplog.records)


def test_workbot_runtime_profile_silent_when_kb_files_present(tmp_path, caplog):
    """When all sentinel kb files exist, no WARNING about missing files is emitted.

    The DeprecationWarning is still emitted, but that's separate from the sentinel check.
    """
    from memory_core.tools.memory_hook_adapters.workbot_runtime_profile import (
        build_workbot_runtime_profile,
    )

    repo_root, workspace_root = _make_fake_workspace(tmp_path)

    caplog.set_level(logging.WARNING, logger="memory_core.tools.memory_hook_adapters.workbot_runtime_profile")

    with pytest.warns(DeprecationWarning):
        build_workbot_runtime_profile(repo_root, workspace_root)

    # No sentinel warnings should be logged
    sentinel_warnings = [
        r for r in caplog.records
        if "kb file(s) missing" in r.message
    ]
    assert len(sentinel_warnings) == 0, f"Unexpected sentinel warnings: {sentinel_warnings}"
