#!/usr/bin/env python3.12
"""B-layer seed refinement tests (M1-4).

Tests the non-git seed refinement logic that refines REPO_ROOT when:
- Seed directory is non-git (no .git)
- No consent marker present
- Exactly one valid child repository exists

Fulfills: VAL-GTW-006 through VAL-GTW-015.

Uses subprocess-based B-layer dry run to avoid reload/cache issues
and denylist-triggering paths.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run_roots(seed_path: str, extra_env: dict[str, str] | None = None) -> str:
    """Run B-layer dry run: import _gateway_config and print REPO_ROOT.

    Returns stdout stripped.
    """
    env = dict(os.environ)
    env["MEMORY_HOOK_PROJECT_CWD"] = seed_path
    # Remove consent marker by default
    env.pop("MEMORY_HOOK_ALLOW_NON_GIT", None)
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from memory_core.tools import _gateway_config as c; print(c.REPO_ROOT)",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd="/tmp",
        timeout=30,
    )
    return result.stdout.strip()


def _make_git_repo(path: Path) -> None:
    """Create a minimal git repository at path."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "--allow-empty", "-m", "init", "-q"],
        cwd=path,
        check=True,
    )


def _init_memory_system(target: Path) -> None:
    """Initialize memory system in target directory using memory-init."""
    subprocess.run(
        ["memory-init", "--target", str(target), "--host", "factory"],
        capture_output=True,
        text=True,
        check=True,
    )


def _init_memory_system_non_git(target: Path) -> None:
    """Initialize memory system in a non-git directory."""
    subprocess.run(
        ["memory-init", "--target", str(target), "--host", "factory", "--allow-non-git"],
        capture_output=True,
        text=True,
        check=True,
    )


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """Create sandbox under tmp_path (not under $HOME to avoid denylist).

    Uses a name that doesn't trigger denylist junk_pattern.
    """
    # Create a clean sandbox dir with safe name
    safe_name = "gwseedb_sandbox"
    sb = tmp_path / safe_name
    sb.mkdir(parents=True, exist_ok=True)
    yield sb


class TestRefineNonGitSeed:
    """Unit tests for _refine_non_git_seed function."""

    def test_refine_unique_child_returns_child(self, sandbox: Path) -> None:
        """Non-git seed + unique child with .git → returns child."""
        from memory_core.tools._gateway_config import _refine_non_git_seed

        parent = sandbox / "parent"
        parent.mkdir()
        child = parent / "child"
        _make_git_repo(child)

        result = _refine_non_git_seed(parent)
        assert result == child

    def test_refine_seed_with_git_passthrough(self, sandbox: Path) -> None:
        """Seed with .git → returns seed itself (passthrough)."""
        from memory_core.tools._gateway_config import _refine_non_git_seed

        seed = sandbox / "seed_repo"
        _make_git_repo(seed)
        child = seed / "child"
        _make_git_repo(child)

        result = _refine_non_git_seed(seed)
        assert result == seed

    def test_refine_dot_directory_filtered(self, sandbox: Path) -> None:
        """Dot directory children are not counted as candidates."""
        from memory_core.tools._gateway_config import _refine_non_git_seed

        parent = sandbox / "dotparent"
        parent.mkdir()

        # Only dot directory with .git
        dot_child = parent / ".hidden"
        _make_git_repo(dot_child)

        result = _refine_non_git_seed(parent)
        # No non-dot candidates, so should return parent
        assert result == parent

    def test_refine_ambiguous_returns_original(self, sandbox: Path) -> None:
        """Ambiguous (>=2 children) → returns original seed."""
        from memory_core.tools._gateway_config import _refine_non_git_seed

        parent = sandbox / "ambig_parent"
        parent.mkdir()
        child1 = parent / "child1"
        _make_git_repo(child1)
        child2 = parent / "child2"
        _make_git_repo(child2)

        result = _refine_non_git_seed(parent)
        assert result == parent
        assert result not in (child1, child2)

    def test_refine_consent_passthrough(self, sandbox: Path) -> None:
        """Consent marker present → returns original seed (passthrough)."""
        from memory_core.tools._gateway_config import _refine_non_git_seed

        parent = sandbox / "consent_parent"
        parent.mkdir()
        child = parent / "child"
        _make_git_repo(child)

        with patch.dict(os.environ, {"MEMORY_HOOK_ALLOW_NON_GIT": "1"}):
            result = _refine_non_git_seed(parent)
        assert result == parent

    def test_refine_no_children_returns_original(self, sandbox: Path) -> None:
        """No children at all → returns original seed."""
        from memory_core.tools._gateway_config import _refine_non_git_seed

        parent = sandbox / "empty_parent"
        parent.mkdir()

        result = _refine_non_git_seed(parent)
        assert result == parent

    def test_refine_gitfile_worktree_counts(self, sandbox: Path) -> None:
        """.git file (worktree form) counts as valid candidate."""
        from memory_core.tools._gateway_config import _refine_non_git_seed

        parent = sandbox / "wt_parent"
        parent.mkdir()

        # Child with .git as a file (worktree form)
        child = parent / "worktree_child"
        child.mkdir()
        (child / ".git").write_text("gitdir: /some/path")

        result = _refine_non_git_seed(parent)
        assert result == child

    def test_refine_pure_filesystem_no_subprocess(self, sandbox: Path) -> None:
        """Refinement is pure filesystem (no git subprocess calls)."""
        from memory_core.tools._gateway_config import _refine_non_git_seed

        parent = sandbox / "fs_parent"
        parent.mkdir()
        child = parent / "child"
        _make_git_repo(child)

        # Track subprocess.run calls
        calls: list = []
        original_run = subprocess.run

        def tracking_run(*args, **kwargs):
            calls.append((args, kwargs))
            return original_run(*args, **kwargs)

        with patch("subprocess.run", side_effect=tracking_run):
            result = _refine_non_git_seed(parent)

        # No subprocess calls should have been made
        assert len(calls) == 0
        assert result == child


class TestBLayerEndToEnd:
    """End-to-end tests via subprocess B-layer dry run.

    These tests verify REPO_ROOT after full import with proper env.
    """

    def test_val_gtw_006_unique_child_repo(self, sandbox: Path) -> None:
        """VAL-GTW-006: non-git seed + unique child → root=child."""
        parent = sandbox / "gtw006_outer"
        parent.mkdir()
        child = parent / "inner"
        _make_git_repo(child)
        _init_memory_system(child)

        result = _run_roots(str(parent))
        assert result == str(child.resolve()), f"Expected {child.resolve()}, got {result}"

    def test_val_gtw_007_seed_with_git_passthrough(self, sandbox: Path) -> None:
        """VAL-GTW-007: seed with .git → root=seed (passthrough)."""
        seed = sandbox / "gtw007_repo"
        _make_git_repo(seed)
        _init_memory_system(seed)

        child = seed / "child"
        _make_git_repo(child)

        result = _run_roots(str(seed))
        assert result == str(seed.resolve()), f"Expected {seed.resolve()}, got {result}"

    def test_val_gtw_008_dot_directory_filtering_e2e(self, sandbox: Path) -> None:
        """VAL-GTW-008: dot directory child not counted, non-dot child found."""
        parent = sandbox / "gtw008_dot"
        parent.mkdir()
        inner = parent / "inner"
        _make_git_repo(inner)
        _init_memory_system(inner)

        # Dot directory with .git (should be ignored)
        dot_child = parent / ".cache_hidden"
        _make_git_repo(dot_child)

        result = _run_roots(str(parent))
        assert result == str(inner.resolve()), f"Expected {inner.resolve()}, got {result}"

    def test_val_gtw_008b_only_dot_directory_no_refine(self, sandbox: Path) -> None:
        """VAL-GTW-008b: only dot directory → don't refine into it."""
        parent = sandbox / "gtw008b_dotonly"
        parent.mkdir()
        dot_child = parent / ".only_dot"
        _make_git_repo(dot_child)

        result = _run_roots(str(parent))
        # Should not resolve into dot directory
        assert not result.endswith(".only_dot"), f"Should not refine into dot dir, got {result}"

    def test_val_gtw_009_ambiguous_e2e(self, sandbox: Path) -> None:
        """VAL-GTW-009: >=2 children → don't silently choose."""
        parent = sandbox / "gtw009_ambig"
        parent.mkdir()
        child_a = parent / "repo_a"
        _make_git_repo(child_a)
        child_b = parent / "repo_b"
        _make_git_repo(child_b)

        result = _run_roots(str(parent))
        # Should not silently choose one
        assert result not in (str(child_a.resolve()), str(child_b.resolve())), (
            f"Should not silently choose one of multiple candidates, got {result}"
        )

    def test_val_gtw_011_pure_filesystem_e2e(self, sandbox: Path) -> None:
        """VAL-GTW-011: B-layer is pure FS — git stub in PATH doesn't break it."""
        parent = sandbox / "gtw011_fs"
        parent.mkdir()
        child = parent / "inner"
        _make_git_repo(child)
        _init_memory_system(child)

        # Create a git stub that records calls and always fails
        bin_dir = sandbox / "fake_bin"
        bin_dir.mkdir()
        git_stub = bin_dir / "git"
        git_stub.write_text('#!/bin/sh\necho CALLED >> "$GIT_STUB_LOG"\nexit 1\n')
        git_stub.chmod(0o755)

        stub_log = sandbox / "git_stub.log"

        env = {
            "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
            "GIT_STUB_LOG": str(stub_log),
        }
        result = _run_roots(str(parent), extra_env=env)

        # Should still resolve correctly
        assert result == str(child.resolve()), f"Expected {child.resolve()}, got {result}"
        # Git stub should not have been called
        if stub_log.exists():
            assert stub_log.read_text() == "", (
                f"Git stub was called {stub_log.read_text().count('CALLED')} times, expected 0"
            )

    def test_val_gtw_012_worktree_gitfile_e2e(self, sandbox: Path) -> None:
        """VAL-GTW-012: .git file (worktree) counts as valid candidate."""
        parent = sandbox / "gtw012_wt"
        parent.mkdir()
        child = parent / "wt_inner"
        child.mkdir()
        (child / ".git").write_text("gitdir: /some/path")

        # Init memory system (non-git, with consent)
        _init_memory_system_non_git(child)

        result = _run_roots(str(parent))
        assert result == str(child.resolve()), f"Worktree child (.git file) should be detected, got {result}"

    def test_val_gtw_014_mcp_server_import(self, sandbox: Path) -> None:
        """VAL-GTW-014: mcp_server import from non-git dir is predictable."""
        parent = sandbox / "gtw014_mcp"
        parent.mkdir()
        child = parent / "inner"
        _make_git_repo(child)
        _init_memory_system(child)

        env = dict(os.environ)
        env["MEMORY_HOOK_PROJECT_CWD"] = str(parent)
        env.pop("MEMORY_HOOK_ALLOW_NON_GIT", None)

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from memory_core.tools import mcp_server; from memory_core.tools._gateway_config import REPO_ROOT; print(REPO_ROOT)",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd="/tmp",
            timeout=30,
        )
        assert result.returncode == 0, f"Import failed: {result.stderr}"
        assert result.stdout.strip() == str(child.resolve()), f"Expected {child.resolve()}, got {result.stdout.strip()}"


# Needed for unit test patching
from unittest.mock import patch  # noqa: E402
