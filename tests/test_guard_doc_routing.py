#!/usr/bin/env python3
"""Tests for guard doc routing integration.

Verifies that the guard blocks writes to unregistered memory/docs/ and memory/kb/ paths,
while allowing writes to registered directories (DOC_CATEGORIES and EXCEPTION_DIRS).
"""

from pathlib import Path

from memory_core.tools._guard_classify import (
    _check_doc_routing,
    classify_tool_use,
)


def test_check_doc_routing_blocks_unknown_dir():
    """Test that _check_doc_routing blocks writes to unknown memory/docs/ subdirectories."""
    result = _check_doc_routing("memory/docs/unknown_category/test.md")
    assert result is not None
    assert result["decision"] == "block"
    assert "未注册" in result["reason"]


def test_check_doc_routing_allows_registered_dir():
    """Test that _check_doc_routing allows writes to registered directories."""
    result = _check_doc_routing("memory/docs/plans/test.md")
    assert result is None

    result = _check_doc_routing("memory/kb/decisions/test.md")
    assert result is None


def test_check_doc_routing_allows_exception_dirs():
    """Test that _check_doc_routing allows writes to exception directories."""
    result = _check_doc_routing("memory/docs/archive/test.md")
    assert result is None

    result = _check_doc_routing("memory/kb/projects/test.md")
    assert result is None


def test_check_doc_routing_ignores_non_memory_paths():
    """Test that _check_doc_routing ignores paths outside memory/."""
    result = _check_doc_routing("src/main.py")
    assert result is None

    result = _check_doc_routing("README.md")
    assert result is None


def test_guard_write_blocks_unknown_category():
    """Test that Write tool is blocked for unknown memory/docs/ categories."""
    payload = {
        "tool_name": "Write",
        "file_path": "memory/docs/unknown_category/test.md",
        "content": "# Test",
    }
    project_root = Path("/tmp/test_project")
    result = classify_tool_use(payload, project_root)
    assert result.matched
    assert result.severity == "error"
    assert "未注册" in result.message
    assert result.detail["decision"] == "block"


def test_guard_write_allows_registered_category():
    """Test that Write tool is allowed for registered memory/docs/ categories."""
    payload = {
        "tool_name": "Write",
        "file_path": "memory/docs/plans/test.md",
        "content": "# Test Plan",
    }
    project_root = Path("/tmp/test_project")
    result = classify_tool_use(payload, project_root)
    # Should not be blocked by doc routing (may be blocked by ownership, but that's separate)
    # We only check that doc routing doesn't block it
    if result.matched and result.detail.get("decision") == "block":
        assert "未注册" not in result.message


def test_guard_write_allows_exception_dirs():
    """Test that Write tool is allowed for exception directories."""
    payload = {
        "tool_name": "Write",
        "file_path": "memory/docs/archive/old.md",
        "content": "# Archive",
    }
    project_root = Path("/tmp/test_project")
    result = classify_tool_use(payload, project_root)
    if result.matched and result.detail.get("decision") == "block":
        assert "未注册" not in result.message


def test_guard_edit_blocks_unknown_category():
    """Test that Edit tool is blocked for unknown memory/docs/ categories."""
    payload = {
        "tool_name": "Edit",
        "file_path": "memory/docs/unknown/test.md",
        "old_str": "old",
        "new_str": "new",
    }
    project_root = Path("/tmp/test_project")
    result = classify_tool_use(payload, project_root)
    assert result.matched
    assert result.severity == "error"
    assert "未注册" in result.message
    assert result.detail["decision"] == "block"


def test_guard_edit_allows_registered_category():
    """Test that Edit tool is allowed for registered memory/docs/ categories."""
    payload = {
        "tool_name": "Edit",
        "file_path": "memory/kb/decisions/D-001.md",
        "old_str": "old",
        "new_str": "new",
    }
    project_root = Path("/tmp/test_project")
    result = classify_tool_use(payload, project_root)
    if result.matched and result.detail.get("decision") == "block":
        assert "未注册" not in result.message


def test_guard_multiedit_blocks_unknown_category():
    """Test that MultiEdit tool is blocked when any file is in unknown category."""
    payload = {
        "tool_name": "MultiEdit",
        "edits": [
            {
                "file_path": "memory/docs/unknown/test1.md",
                "old_str": "old1",
                "new_str": "new1",
            },
            {
                "file_path": "memory/docs/plans/test2.md",
                "old_str": "old2",
                "new_str": "new2",
            },
        ],
    }
    project_root = Path("/tmp/test_project")
    result = classify_tool_use(payload, project_root)
    assert result.matched
    assert result.severity == "error"
    assert result.detail["decision"] == "block"
    # Should have blocked the unknown file
    blocked_paths = [r["path"] for r in result.detail["item_results"] if r["decision"] == "block"]
    assert "memory/docs/unknown/test1.md" in blocked_paths


def test_guard_multiedit_allows_all_registered():
    """Test that MultiEdit tool is allowed when all files are in registered categories."""
    payload = {
        "tool_name": "MultiEdit",
        "edits": [
            {
                "file_path": "memory/docs/plans/plan.md",
                "old_str": "old1",
                "new_str": "new1",
            },
            {
                "file_path": "memory/kb/lessons/lesson.md",
                "old_str": "old2",
                "new_str": "new2",
            },
        ],
    }
    project_root = Path("/tmp/test_project")
    result = classify_tool_use(payload, project_root)
    # Check that doc routing didn't block these
    if result.detail.get("decision") == "block":
        for item in result.detail.get("item_results", []):
            if item["decision"] == "block":
                assert "未注册" not in item["reason"]


def test_guard_all_categories_registered():
    """Test that all DOC_CATEGORIES directories are allowed."""
    from memory_core.tools.doc_router import DOC_CATEGORIES

    for category, dir_path in DOC_CATEGORIES.items():
        test_file = f"{dir_path}test.md"
        result = _check_doc_routing(test_file)
        assert result is None, f"Category {category} ({dir_path}) should be allowed"


def test_guard_exception_dirs_registered():
    """Test that all EXCEPTION_DIRS are allowed."""
    from memory_core.tools.doc_router import EXCEPTION_DIRS

    for exc_dir in EXCEPTION_DIRS:
        test_file = f"{exc_dir}test.md"
        result = _check_doc_routing(test_file)
        assert result is None, f"Exception dir {exc_dir} should be allowed"
