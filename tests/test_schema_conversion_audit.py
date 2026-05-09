"""Schema conversion audit logging tests (Phase 4d: three-layer schema conversion audit + is_lossless self-check)."""
from __future__ import annotations

import os
from typing import Any

import pytest

from memory_core.tools.memory_hook_schema import (
    MEMORY_V1_VERSION,
    V1_VERSION,
    V2_VERSION,
    convert_to_v1,
    is_lossless,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _v2_package_with_drops() -> dict[str, Any]:
    """wb-hook-v2 package containing keys that get dropped."""
    return {
        "schema_version": V2_VERSION,
        "repo_root": "/repo",
        "workspace_root": "/repo/workspace",
        "cwd": "/repo",
        "project_context": {
            "scope": "test-scope",
            "name": "Test Project",
            "description": "A test project",
            "tech_stack": ["Python"],
        },
        "task_context": {"task_id": "t-001"},
        "host": "codex",
        "event": "session-start",
        "status": "ok",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "system_context": {"info": "diagnostic"},
        "missing_paths": ["/some/missing"],
        "allowed_reads": [],
        "allowed_writes": [],
        "evidence_refs": [],
        "validation_errors": [],
    }


def _v2_package_without_drops() -> dict[str, Any]:
    """wb-hook-v2 package with NO keys that would be dropped."""
    return {
        "schema_version": V2_VERSION,
        "repo_root": "/repo",
        "workspace_root": "/repo/workspace",
        "cwd": "/repo",
        "project_context": {"scope": "test-scope"},
        "task_context": {"task_id": "t-001"},
        "host": "codex",
        "event": "session-start",
        "status": "ok",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "allowed_reads": [],
        "allowed_writes": [],
        "evidence_refs": [],
        "validation_errors": [],
    }


def _v1_package_with_project_fields() -> dict[str, Any]:
    """context-package-v1 package containing project sub-keys that get dropped."""
    return {
        "schema_version": V1_VERSION,
        "paths": {"repo_root": "/repo", "workspace_root": "/repo/workspace", "cwd": "/repo"},
        "project": {
            "scope": "test-scope",
            "name": "Test Project",
            "description": "A test project",
            "tech_stack": ["Python"],
        },
        "task": {"task_id": "t-001"},
        "host": "codex",
        "event": "session-start",
        "status": "ok",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "allowed_reads": [],
        "allowed_writes": [],
        "evidence_refs": [],
        "validation_errors": [],
    }


# ---------------------------------------------------------------------------
# Test 1: is_lossless returns (True, []) when no keys are dropped
# ---------------------------------------------------------------------------

class TestIsLosslessNoDrop:
    def test_is_lossless_no_drop_returns_true(self) -> None:
        """输入 package 不含 _DROP_KEYS 的键，is_lossless 返回 (True, [])."""
        pkg = _v2_package_without_drops()
        lossless, dropped = is_lossless(pkg, V2_VERSION, V1_VERSION)
        assert lossless is True
        assert dropped == []


# ---------------------------------------------------------------------------
# Test 2: is_lossless detects system_context drop
# ---------------------------------------------------------------------------

class TestIsLosslessDropsSystemContext:
    def test_is_lossless_drops_system_context(self) -> None:
        """含 system_context，wb-hook-v2 → context-package-v1 返回 (False, ['system_context'])."""
        pkg = _v2_package_with_drops()
        lossless, dropped = is_lossless(pkg, V2_VERSION, V1_VERSION)
        assert lossless is False
        assert "system_context" in dropped


# ---------------------------------------------------------------------------
# Test 3: audit emitted on drop when enabled
# ---------------------------------------------------------------------------

class TestAuditEmittedOnDrop:
    def test_audit_emitted_on_drop_when_enabled(self, capsys: pytest.CaptureFixture) -> None:
        """用 capsys 捕获 stderr，包含 'drop_audit' 与 'system_context'."""
        pkg = _v2_package_with_drops()
        # Ensure audit is enabled (default)
        os.environ.pop("MEMORY_HOOK_SCHEMA_AUDIT", None)
        convert_to_v1(pkg)
        captured = capsys.readouterr()
        assert "drop_audit" in captured.err
        assert "system_context" in captured.err


# ---------------------------------------------------------------------------
# Test 4: audit silent when disabled
# ---------------------------------------------------------------------------

class TestAuditSilentWhenDisabled:
    def test_audit_silent_when_disabled(self, capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch) -> None:
        """MEMORY_HOOK_SCHEMA_AUDIT=0 时 stderr 无 'drop_audit'."""
        monkeypatch.setenv("MEMORY_HOOK_SCHEMA_AUDIT", "0")
        pkg = _v2_package_with_drops()
        convert_to_v1(pkg)
        captured = capsys.readouterr()
        assert "drop_audit" not in captured.err


# ---------------------------------------------------------------------------
# Test 5: convert_to_v1 still returns same shape after audit (compatibility regression)
# ---------------------------------------------------------------------------

class TestConvertToV1Shape:
    def test_convert_to_v1_still_returns_same_shape_after_audit(self, capsys: pytest.CaptureFixture) -> None:
        """审计不改变返回结构（兼容性回归）."""
        os.environ.pop("MEMORY_HOOK_SCHEMA_AUDIT", None)
        pkg = _v2_package_with_drops()
        result = convert_to_v1(pkg)
        # Verify shape: schema_version, paths, project, task, kept keys
        assert result["schema_version"] == V1_VERSION
        assert "paths" in result
        assert "project" in result
        assert "task" in result
        # Dropped keys must not appear
        assert "system_context" not in result
        assert "missing_paths" not in result
        # Kept keys must be present
        assert result["host"] == "codex"
        assert result["event"] == "session-start"


# ---------------------------------------------------------------------------
# Test 6: v1 → memory-v1 drops project business fields
# ---------------------------------------------------------------------------

class TestV1ToMemoryV1DropsProjectFields:
    def test_v1_to_memory_v1_drops_project_business_fields(self) -> None:
        """含 project.name 转换时被识别为有损."""
        pkg = _v1_package_with_project_fields()
        lossless, dropped = is_lossless(pkg, V1_VERSION, MEMORY_V1_VERSION)
        assert lossless is False
        # Check that project sub-keys are detected
        assert any("project.name" in k for k in dropped)
        assert any("project.description" in k for k in dropped)
        assert any("project.tech_stack" in k for k in dropped)
