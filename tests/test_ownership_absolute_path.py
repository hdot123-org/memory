"""Tests for absolute path ownership classification gap fix (VAL-CROSS-003).

Verifies that absolute paths to ALL 4 protected domain markers are blocked
by the normal ownership classifier, not just memory/kb and memory/docs.

The gap: classify_owned_path (_check_path_escape) early-returns on absolute
paths, so memory/system/ and memory/log/ were ALLOWED in normal operation.
The fix: _guard_classify normalizes absolute paths to project-root-relative
before calling classify_owned_path.
"""

from pathlib import Path

import pytest

from memory_core.tools._guard_classify import (
    _normalize_to_project_relative,
    classify_tool_use,
)


class TestNormalizeToProjectRelative:
    """Test the _normalize_to_project_relative helper."""

    def test_absolute_path_under_project_root(self, tmp_path: Path) -> None:
        """Absolute path under project root is converted to relative."""
        abs_path = str(tmp_path / "memory/system/errors.log")
        result = _normalize_to_project_relative(abs_path, tmp_path)
        assert result == "memory/system/errors.log"

    def test_relative_path_unchanged(self, tmp_path: Path) -> None:
        """Relative paths are returned as-is."""
        rel_path = "memory/system/errors.log"
        result = _normalize_to_project_relative(rel_path, tmp_path)
        assert result == rel_path

    def test_absolute_path_outside_project_root(self, tmp_path: Path) -> None:
        """Absolute path NOT under project root is returned as-is."""
        abs_path = "/completely/different/path/memory/system/file.txt"
        result = _normalize_to_project_relative(abs_path, tmp_path)
        assert result == abs_path

    @pytest.mark.parametrize(
        "marker",
        [
            "memory/kb/file.md",
            "memory/docs/file.md",
            "memory/system/file.txt",
            "memory/log/file.log",
        ],
    )
    def test_all_domain_markers_normalized(self, tmp_path: Path, marker: str) -> None:
        """All 4 protected domain markers are correctly normalized from absolute."""
        abs_path = str(tmp_path / marker)
        result = _normalize_to_project_relative(abs_path, tmp_path)
        assert result == marker


class TestAbsolutePathsBlockedByNormalClassifier:
    """VAL-CROSS-003: All 4 protected markers must block with absolute paths.

    This is the core assertion: previously only memory/kb and memory/docs
    blocked via _check_doc_routing (Path.parts-based, absolute-safe).
    memory/system and memory/log escaped because classify_owned_path
    rejected absolute paths via _check_path_escape early-return.
    """

    @pytest.mark.parametrize(
        "marker",
        [
            "memory/kb/article.md",
            "memory/docs/INDEX.md",
            "memory/system/errors.log",
            "memory/log/session.log",
        ],
        ids=["kb", "docs", "system", "log"],
    )
    def test_write_absolute_path_blocks(
        self, tmp_path: Path, marker: str
    ) -> None:
        """Write with absolute path to protected domain is blocked."""
        # Create memory/system to make it a memory-managed project
        (tmp_path / "memory" / "system").mkdir(parents=True)

        # Use absolute path (as Factory sends them)
        abs_file_path = str(tmp_path / marker)
        payload = {
            "tool_name": "Write",
            "file_path": abs_file_path,
            "content": "test",
        }
        result = classify_tool_use(payload, tmp_path)
        assert result.matched is True, f"{marker} should be blocked but was allowed"
        assert result.detail["decision"] == "block", (
            f"{marker} decision should be 'block' but was '{result.detail['decision']}'"
        )
        # Verify it's NOT allowed due to path-escape false positive
        assert "Path escape" not in result.message

    @pytest.mark.parametrize(
        "marker",
        [
            "memory/kb/article.md",
            "memory/docs/INDEX.md",
            "memory/system/errors.log",
            "memory/log/session.log",
        ],
        ids=["kb", "docs", "system", "log"],
    )
    def test_edit_absolute_path_blocks(self, tmp_path: Path, marker: str) -> None:
        """Edit with absolute path to protected domain is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        abs_file_path = str(tmp_path / marker)
        payload = {
            "tool_name": "Edit",
            "file_path": abs_file_path,
            "old_str": "old",
            "new_str": "new",
        }
        result = classify_tool_use(payload, tmp_path)
        assert result.matched is True
        assert result.detail["decision"] == "block"

    @pytest.mark.parametrize(
        "marker",
        [
            "memory/kb/article.md",
            "memory/docs/INDEX.md",
            "memory/system/errors.log",
            "memory/log/session.log",
        ],
        ids=["kb", "docs", "system", "log"],
    )
    def test_multiedit_absolute_path_blocks(self, tmp_path: Path, marker: str) -> None:
        """MultiEdit with absolute path to protected domain is blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        abs_file_path = str(tmp_path / marker)
        payload = {
            "tool_name": "MultiEdit",
            "edits": [
                {"file_path": abs_file_path, "old_str": "old", "new_str": "new"},
            ],
        }
        result = classify_tool_use(payload, tmp_path)
        assert result.matched is True
        assert result.detail["decision"] == "block"

    def test_all_four_markers_block_with_absolute_paths(
        self, tmp_path: Path
    ) -> None:
        """Comprehensive: all 4 markers block with absolute paths in one project."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "memory" / "kb").mkdir(parents=True)
        (tmp_path / "memory" / "docs").mkdir(parents=True)
        (tmp_path / "memory" / "log").mkdir(parents=True)

        markers = [
            "memory/kb/article.md",
            "memory/docs/INDEX.md",
            "memory/system/errors.log",
            "memory/log/session.log",
        ]
        for marker in markers:
            abs_path = str(tmp_path / marker)
            payload = {"tool_name": "Write", "file_path": abs_path, "content": "test"}
            result = classify_tool_use(payload, tmp_path)
            assert result.matched is True, f"{marker} should be blocked but was allowed"
            assert result.detail["decision"] == "block", (
                f"{marker} decision should be 'block' but was '{result.detail['decision']}'"
            )


class TestRelativePathsStillWork:
    """No regression: relative paths must continue to work as before."""

    @pytest.mark.parametrize(
        "marker",
        [
            "memory/kb/article.md",
            "memory/docs/INDEX.md",
            "memory/system/errors.log",
            "memory/log/session.log",
        ],
    )
    def test_relative_path_still_blocks(self, tmp_path: Path, marker: str) -> None:
        """Relative paths to protected domains are still blocked."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {"tool_name": "Write", "file_path": marker, "content": "test"}
        result = classify_tool_use(payload, tmp_path)
        assert result.matched is True
        assert result.detail["decision"] == "block"

    def test_non_protected_relative_path_allowed(self, tmp_path: Path) -> None:
        """Non-protected relative paths are still allowed."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "src/main.py",
            "content": "print('hello')",
        }
        result = classify_tool_use(payload, tmp_path)
        assert result.matched is False
        assert result.detail["decision"] == "allow"


class TestAbsolutePathOutsideProjectNotAffected:
    """Absolute paths outside the project root should NOT be treated as owned."""

    def test_absolute_path_outside_project_allowed(self, tmp_path: Path) -> None:
        """Absolute path NOT under project root is allowed (not our domain)."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "/tmp/random/file.txt",
            "content": "test",
        }
        result = classify_tool_use(payload, tmp_path)
        assert result.matched is False
        assert result.detail["decision"] == "allow"

    def test_absolute_path_outside_project_with_memory_string_allowed(
        self, tmp_path: Path
    ) -> None:
        """Absolute path outside project containing 'memory/' string is allowed."""
        (tmp_path / "memory" / "system").mkdir(parents=True)

        payload = {
            "tool_name": "Write",
            "file_path": "/other/project/memory/system/file.txt",
            "content": "test",
        }
        result = classify_tool_use(payload, tmp_path)
        assert result.matched is False
        assert result.detail["decision"] == "allow"
