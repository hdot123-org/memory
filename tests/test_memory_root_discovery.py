"""Tests for workspace.tools.memory_root_discovery.

Covers:
    - .memory/ marker found at various depths
    - Fallback to SCRIPT_PATH.parents[2] when no marker exists
    - workspace/ subdirectory detection
    - discover_roots convenience wrapper
"""
from __future__ import annotations

from pathlib import Path

from workspace.tools.memory_root_discovery import (
    _FALLBACK_REPO_ROOT,
    discover_project_root,
    discover_roots,
    discover_workspace_root,
)


# ---------------------------------------------------------------------------
# discover_project_root
# ---------------------------------------------------------------------------

class TestDiscoverProjectRoot:
    """discover_project_root walks upward to find .memory/."""

    def test_memory_at_start_path(self, tmp_path: Path) -> None:
        """Start path itself contains .memory/ -> returns start_path."""
        (tmp_path / ".memory").mkdir()
        assert discover_project_root(tmp_path) == tmp_path

    def test_memory_one_level_up(self, tmp_path: Path) -> None:
        """Parent directory contains .memory/."""
        (tmp_path / ".memory").mkdir()
        child = tmp_path / "a" / "b"
        child.mkdir(parents=True)
        assert discover_project_root(child) == tmp_path

    def test_memory_several_levels_up(self, tmp_path: Path) -> None:
        """Grandparent directory contains .memory/."""
        (tmp_path / ".memory").mkdir()
        deep = tmp_path / "x" / "y" / "z"
        deep.mkdir(parents=True)
        assert discover_project_root(deep) == tmp_path

    def test_no_memory_marker_falls_back(self, tmp_path: Path) -> None:
        """No .memory/ anywhere -> fallback to SCRIPT_PATH.parents[2]."""
        island = tmp_path / "no_marker" / "sub"
        island.mkdir(parents=True)
        assert discover_project_root(island) == _FALLBACK_REPO_ROOT

    def test_nearest_wins(self, tmp_path: Path) -> None:
        """Two nested .memory/ markers -> returns the closest one."""
        (tmp_path / ".memory").mkdir()
        inner = tmp_path / "inner"
        (inner / ".memory").mkdir(parents=True)
        assert discover_project_root(inner / "leaf" / "deep") == inner

    def test_memory_must_be_directory(self, tmp_path: Path) -> None:
        """A regular file named .memory is not a marker."""
        (tmp_path / ".memory").touch()
        child = tmp_path / "sub"
        child.mkdir()
        assert discover_project_root(child) == _FALLBACK_REPO_ROOT


# ---------------------------------------------------------------------------
# discover_workspace_root
# ---------------------------------------------------------------------------

class TestDiscoverWorkspaceRoot:
    """discover_workspace_root checks for workspace/ subdir."""

    def test_workspace_exists(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspace"
        ws.mkdir()
        assert discover_workspace_root(tmp_path) == ws

    def test_workspace_missing(self, tmp_path: Path) -> None:
        """No workspace/ subdir -> returns project_root itself."""
        assert discover_workspace_root(tmp_path) == tmp_path

    def test_workspace_is_file_not_dir(self, tmp_path: Path) -> None:
        """A file named workspace is not a directory."""
        (tmp_path / "workspace").touch()
        assert discover_workspace_root(tmp_path) == tmp_path


# ---------------------------------------------------------------------------
# discover_roots
# ---------------------------------------------------------------------------

class TestDiscoverRoots:
    """discover_roots returns (repo_root, workspace_root)."""

    def test_with_memory_and_workspace(self, tmp_path: Path) -> None:
        (tmp_path / ".memory").mkdir()
        (tmp_path / "workspace").mkdir()
        repo, ws = discover_roots(tmp_path)
        assert repo == tmp_path
        assert ws == tmp_path / "workspace"

    def test_with_memory_no_workspace(self, tmp_path: Path) -> None:
        (tmp_path / ".memory").mkdir()
        repo, ws = discover_roots(tmp_path)
        assert repo == tmp_path
        assert ws == tmp_path  # falls back to project_root

    def test_no_marker_uses_fallback(self, tmp_path: Path) -> None:
        island = tmp_path / "nowhere"
        island.mkdir()
        repo, ws = discover_roots(island)
        assert repo == _FALLBACK_REPO_ROOT
