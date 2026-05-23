"""Tests for context package schema: memory-v1 and legacy conversions."""
from __future__ import annotations

from typing import Any

import pytest

from memory_core.tools.memory_hook_schema import (
    MEMORY_V1_VERSION,
    V1_VERSION,
    V2_VERSION,
    convert_legacy_to_memory_v1,
    convert_to_memory_v1,
    is_memory_v1,
    is_v1,
    is_v2,
)

# ---------------------------------------------------------------------------
# Fixtures: sample packages in each schema format
# ---------------------------------------------------------------------------

def _sample_v2_package() -> dict[str, Any]:
    """Minimal wb-hook-v2 context package."""
    return {
        "schema_version": V2_VERSION,
        "repo_root": "/repo",
        "workspace_root": "/repo/workspace",
        "cwd": "/repo/workspace",
        "project_context": {
            "scope": "test-scope",
            "name": "Test Project",
        },
        "task_context": {
            "task_id": "t-001",
            "description": "do stuff",
        },
        "host": "codex",
        "event": "session-start",
        "status": "ok",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "system_context": {"info": "diagnostic"},
        "missing_paths": ["/some/missing"],
        "allowed_reads": ["/repo/AGENTS.md"],
        "allowed_writes": ["/repo/workspace/memory"],
        "evidence_refs": [],
        "validation_errors": [],
    }


def _sample_v1_package() -> dict[str, Any]:
    """Minimal context-package-v1 context package."""
    return {
        "schema_version": V1_VERSION,
        "paths": {
            "repo_root": "/repo",
            "workspace_root": "/repo/workspace",
            "cwd": "/repo/workspace",
        },
        "project": {
            "scope": "test-scope",
            "name": "Test Project",
        },
        "task": {
            "task_id": "t-001",
            "description": "do stuff",
        },
        "host": "codex",
        "event": "session-start",
        "status": "ok",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "allowed_reads": ["/repo/AGENTS.md"],
        "allowed_writes": ["/repo/workspace/memory"],
        "evidence_refs": [],
        "validation_errors": [],
    }


# ---------------------------------------------------------------------------
# memory-v1 structure verification
# ---------------------------------------------------------------------------

class TestMemoryV1Structure:
    """Verify memory-v1 output references memory/system/* canonical files."""

    def test_schema_version(self) -> None:
        result = convert_to_memory_v1(_sample_v2_package())
        assert result["schema_version"] == MEMORY_V1_VERSION

    def test_project_has_canonical_files(self) -> None:
        result = convert_to_memory_v1(_sample_v2_package())
        project = result["project"]
        assert project["scope"] == "test-scope"
        assert project["canonical"] == "memory/system/CANONICAL.md"
        assert project["plan"] == "memory/system/PLAN.md"
        assert project["state"] == "memory/system/STATE.md"
        assert project["tasks"] == "memory/system/TASKS.md"

    def test_paths_preserved(self) -> None:
        result = convert_to_memory_v1(_sample_v2_package())
        assert result["paths"]["repo_root"] == "/repo"
        assert result["paths"]["workspace_root"] == "/repo/workspace"

    def test_task_preserved(self) -> None:
        result = convert_to_memory_v1(_sample_v2_package())
        assert result["task"]["task_id"] == "t-001"

    def test_keep_keys_forwarded(self) -> None:
        result = convert_to_memory_v1(_sample_v2_package())
        assert result["host"] == "codex"
        assert result["event"] == "session-start"
        assert result["status"] == "ok"
        assert "allowed_reads" in result
        assert "evidence_refs" in result

    def test_dropped_keys_absent(self) -> None:
        result = convert_to_memory_v1(_sample_v2_package())
        assert "system_context" not in result
        assert "missing_paths" not in result
        assert "project_context" not in result
        assert "task_context" not in result


# ---------------------------------------------------------------------------
# legacy conversion: v2 → memory-v1
# ---------------------------------------------------------------------------

class TestV2ToMemoryV1:
    """Legacy conversion from wb-hook-v2 to memory-v1."""

    def test_convert_v2_to_memory_v1(self) -> None:
        v2 = _sample_v2_package()
        result = convert_legacy_to_memory_v1(v2)
        assert result["schema_version"] == MEMORY_V1_VERSION
        assert result["project"]["canonical"] == "memory/system/CANONICAL.md"

    def test_convert_v2_preserves_scope(self) -> None:
        v2 = _sample_v2_package()
        result = convert_legacy_to_memory_v1(v2)
        assert result["project"]["scope"] == "test-scope"


# ---------------------------------------------------------------------------
# legacy conversion: v1 → memory-v1
# ---------------------------------------------------------------------------

class TestV1ToMemoryV1:
    """Legacy conversion from context-package-v1 to memory-v1."""

    def test_convert_v1_to_memory_v1(self) -> None:
        v1 = _sample_v1_package()
        result = convert_legacy_to_memory_v1(v1)
        assert result["schema_version"] == MEMORY_V1_VERSION
        assert result["project"]["canonical"] == "memory/system/CANONICAL.md"

    def test_convert_v1_preserves_paths(self) -> None:
        v1 = _sample_v1_package()
        result = convert_legacy_to_memory_v1(v1)
        assert result["paths"] == v1["paths"]

    def test_convert_v1_preserves_task(self) -> None:
        v1 = _sample_v1_package()
        result = convert_legacy_to_memory_v1(v1)
        assert result["task"]["task_id"] == "t-001"


# ---------------------------------------------------------------------------
# identity: memory-v1 → memory-v1 (no-op)
# ---------------------------------------------------------------------------

class TestMemoryV1Identity:
    """Already memory-v1 package is returned as-is."""

    def test_identity_returns_same_object(self) -> None:
        pkg: dict[str, Any] = {
            "schema_version": MEMORY_V1_VERSION,
            "project": {"scope": "s", "canonical": "memory/system/CANONICAL.md"},
        }
        result = convert_legacy_to_memory_v1(pkg)
        assert result is pkg


# ---------------------------------------------------------------------------
# predicate helpers
# ---------------------------------------------------------------------------

class TestPredicates:
    """is_v1 / is_v2 / is_memory_v1 predicates."""

    def test_is_v2(self) -> None:
        assert is_v2(_sample_v2_package())
        assert not is_v2(_sample_v1_package())

    def test_is_v1(self) -> None:
        assert is_v1(_sample_v1_package())
        assert not is_v1(_sample_v2_package())

    def test_is_memory_v1(self) -> None:
        v2 = _sample_v2_package()
        mem = convert_to_memory_v1(v2)
        assert is_memory_v1(mem)
        assert not is_memory_v1(_sample_v2_package())
        assert not is_memory_v1(_sample_v1_package())


# ---------------------------------------------------------------------------
# build_context_package_simple: integration tests
# ---------------------------------------------------------------------------

class TestBuildContextPackageSimple:
    """Test build_context_package_simple with both schema modes."""

    @pytest.fixture()
    def _patch_build(self, monkeypatch: pytest.MonkeyPatch):
        """Monkeypatch build_context_package to return a synthetic v2 package."""
        from memory_core.tools import memory_hook_gateway as gw

        sample = _sample_v2_package()
        monkeypatch.setattr(gw, "build_context_package", lambda host, event, payload=None: sample)
        return gw

    def test_default_schema_returns_v1(self, _patch_build: Any) -> None:
        gw = _patch_build
        result = gw.build_context_package_simple("codex", "session-start")
        assert result["schema_version"] == V1_VERSION
        assert "project" in result
        # v1 project preserves the full original project_context fields
        assert result["project"]["scope"] == "test-scope"

    def test_memory_v1_schema(self, _patch_build: Any) -> None:
        gw = _patch_build
        result = gw.build_context_package_simple("codex", "session-start", schema="memory-v1")
        assert result["schema_version"] == MEMORY_V1_VERSION
        project = result["project"]
        assert project["canonical"] == "memory/system/CANONICAL.md"
        assert project["plan"] == "memory/system/PLAN.md"
        assert project["state"] == "memory/system/STATE.md"
        assert project["tasks"] == "memory/system/TASKS.md"
        assert project["scope"] == "test-scope"

    def test_explicit_v1_schema(self, _patch_build: Any) -> None:
        gw = _patch_build
        result = gw.build_context_package_simple("codex", "session-start", schema="context-package-v1")
        assert result["schema_version"] == V1_VERSION
