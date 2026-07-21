"""Tests for memory_core.tools.memory_root_discovery.

Covers:
    - .memory/ marker found at various depths
    - Fallback to SCRIPT_PATH.parents[2] when no marker exists
    - memory_core/ subdirectory detection
    - discover_roots convenience wrapper
"""

from pathlib import Path

from memory_core.tools.memory_root_discovery import (
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
        (tmp_path / "memory" / "system").mkdir(parents=True)
        assert discover_project_root(tmp_path) == tmp_path

    def test_memory_one_level_up(self, tmp_path: Path) -> None:
        """Parent directory contains .memory/."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        child = tmp_path / "a" / "b"
        child.mkdir(parents=True)
        assert discover_project_root(child) == tmp_path

    def test_memory_several_levels_up(self, tmp_path: Path) -> None:
        """Grandparent directory contains .memory/."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        deep = tmp_path / "x" / "y" / "z"
        deep.mkdir(parents=True)
        assert discover_project_root(deep) == tmp_path

    def test_no_memory_marker_falls_back(self, tmp_path: Path) -> None:
        """No .memory/ anywhere -> fallback to SCRIPT_PATH.parents[2]."""
        island = tmp_path / "no_marker" / "sub"
        island.mkdir(parents=True)
        assert discover_project_root(island) == _FALLBACK_REPO_ROOT

    def test_outermost_wins(self, tmp_path: Path) -> None:
        """Two nested .memory/ markers -> returns the outermost one."""
        (tmp_path / "memory" / "system").mkdir(parents=True)
        inner = tmp_path / "inner"
        (inner / "memory" / "system").mkdir(parents=True)
        assert discover_project_root(inner / "leaf" / "deep") == tmp_path

    def test_nested_consumer_case(self, tmp_path: Path) -> None:
        """Actual bug case: cwd in memory/system/tools/ with nested markers.

        Simulates:
            consumer_project/
            ├── memory/system/          ← outer marker (should be selected)
            └── memory_core/
                └── memory/system/
                    └── tools/          ← cwd starts here
        """
        outer = tmp_path / "consumer_project"
        outer.mkdir()
        (outer / "memory" / "system").mkdir(parents=True)
        inner_core = outer / "memory_core"
        (inner_core / "memory" / "system" / "tools").mkdir(parents=True)
        cwd = inner_core / "memory" / "system" / "tools"
        result = discover_project_root(cwd)
        assert result.resolve() == outer.resolve()

    def test_memory_must_be_directory(self, tmp_path: Path) -> None:
        """A regular file named memory/system is not a marker."""
        (tmp_path / "memory").mkdir()
        (tmp_path / "memory" / "system").touch()
        child = tmp_path / "sub"
        child.mkdir()
        assert discover_project_root(child) == _FALLBACK_REPO_ROOT


# ---------------------------------------------------------------------------
# discover_workspace_root
# ---------------------------------------------------------------------------

class TestDiscoverWorkspaceRoot:
    """discover_workspace_root checks for memory_core/ subdir."""

    def test_workspace_exists(self, tmp_path: Path) -> None:
        ws = tmp_path / "memory_core"
        ws.mkdir()
        assert discover_workspace_root(tmp_path) == ws

    def test_workspace_missing(self, tmp_path: Path) -> None:
        """No memory_core/ subdir -> returns project_root itself."""
        assert discover_workspace_root(tmp_path) == tmp_path

    def test_workspace_is_file_not_dir(self, tmp_path: Path) -> None:
        """A file named memory_core is not a directory."""
        (tmp_path / "memory_core").touch()
        assert discover_workspace_root(tmp_path) == tmp_path


# ---------------------------------------------------------------------------
# discover_roots
# ---------------------------------------------------------------------------

class TestDiscoverRoots:
    """discover_roots returns (repo_root, workspace_root)."""

    def test_with_memory_and_workspace(self, tmp_path: Path) -> None:
        (tmp_path / "memory" / "system").mkdir(parents=True)
        (tmp_path / "memory_core").mkdir()
        repo, ws = discover_roots(tmp_path)
        assert repo == tmp_path
        assert ws == tmp_path / "memory_core"

    def test_with_memory_no_workspace(self, tmp_path: Path) -> None:
        (tmp_path / "memory" / "system").mkdir(parents=True)
        repo, ws = discover_roots(tmp_path)
        assert repo == tmp_path
        assert ws == tmp_path  # falls back to project_root

    def test_no_marker_uses_fallback(self, tmp_path: Path) -> None:
        island = tmp_path / "nowhere"
        island.mkdir()
        repo, ws = discover_roots(island)
        assert repo == _FALLBACK_REPO_ROOT

    def test_discover_roots_nested(self, tmp_path: Path) -> None:
        """Nested memory/system markers with memory_core workspace → correct workspace_root.

        Verifies VAL-ROOT-005: when discover_roots() is called from memory/system/tools/
        inside a project with outer memory/system/, workspace_root resolves to the
        outer project root (not the inner memory_core/ directory).
        """
        outer = tmp_path / "consumer_project"
        outer.mkdir()
        (outer / "memory" / "system").mkdir(parents=True)
        (outer / "memory_core").mkdir()
        inner_tools = outer / "memory_core" / "memory" / "system" / "tools"
        inner_tools.mkdir(parents=True)
        repo, ws = discover_roots(inner_tools)
        assert repo.resolve() == outer.resolve()
        assert ws.resolve() == (outer / "memory_core").resolve()
