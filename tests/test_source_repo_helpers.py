"""Regression tests for the shared source_repo helper factory (INFRA-324).

Verifies that ``make_source_repo`` correctly creates the three base marker
files, appends (rather than replaces) extra markers, and initialises a
``.git`` directory via ``git init``.
"""

from __future__ import annotations

from pathlib import Path

from tests.source_repo_helpers import make_source_repo


class TestMakeSourceRepoDefault:
    """Default invocation (no extra_marker_files) tests."""

    def test_creates_exactly_three_base_markers(self, tmp_path: Path) -> None:
        """All three base markers exist and ownership.py does NOT exist."""
        repo = make_source_repo(tmp_path)
        tools = repo / "memory_core" / "tools"

        assert (tools / "memory_hook_gateway.py").exists()
        assert (tools / "factory_global_hooks.py").exists()
        assert (tools / "codex_global_hooks.py").exists()
        assert not (tools / "ownership.py").exists(), "ownership.py should NOT exist when extra_marker_files is empty"


class TestMakeSourceRepoExtraMarkers:
    """extra_marker_files append semantics."""

    def test_extra_appends_without_replacing_base(self, tmp_path: Path) -> None:
        """Extra markers are added alongside (not replacing) the base three."""
        repo = make_source_repo(tmp_path, extra_marker_files=("ownership.py",))
        tools = repo / "memory_core" / "tools"

        # Extra marker must exist
        assert (tools / "ownership.py").exists(), "ownership.py must exist when passed via extra_marker_files"
        # All three base markers must still exist (append, not replace)
        assert (tools / "memory_hook_gateway.py").exists()
        assert (tools / "factory_global_hooks.py").exists()
        assert (tools / "codex_global_hooks.py").exists()


class TestMakeSourceRepoGitInit:
    """git init side-effect."""

    def test_git_directory_exists(self, tmp_path: Path) -> None:
        """Returned repo path has a .git directory (git init ran successfully)."""
        repo = make_source_repo(tmp_path)
        assert (repo / ".git").is_dir(), ".git should be a directory after git init"
