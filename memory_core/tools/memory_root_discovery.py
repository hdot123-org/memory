"""Discover memory-system project roots by walking the directory tree.

The canonical project-root marker is a ``memory/system/`` directory.  This module
provides pure functions that resolve *repo root* and *workspace root* from an
arbitrary starting path without depending on any gateway globals.
"""
from __future__ import annotations

import logging
from pathlib import Path

# Fallback used when no memory/system/ ancestor is found.
_SCRIPT_PATH = Path(__file__).resolve()
_FALLBACK_REPO_ROOT = _SCRIPT_PATH.parents[2]

_MEMORY_DIR = "memory/system"
_WORKSPACE_DIR = "memory_core"
_GIT_DIR = ".git"

_MAX_UPWARD_DEPTH = 8

_logger = logging.getLogger(__name__)


def _has_git_not_memory(current: Path) -> bool:
    """Check if *current* has a .git/ dir but no memory/system/ dir (sentinel)."""
    return (current / _GIT_DIR).is_dir() and not (current / _MEMORY_DIR).is_dir()


def discover_project_root(start_path: Path) -> Path:
    """Walk *start_path* and its ancestors looking for a ``memory/system/`` directory.

    Returns the **outermost** (highest-level) ancestor that contains
    ``memory/system/``.  Continues walking after finding the first match
    until a ``.git/`` directory without ``memory/system/`` is encountered
    (monorepo sentinel) or the upward walk exceeds ``_MAX_UPWARD_DEPTH``.
    Falls back to the repository root derived from this module's location
    when nothing is found.
    """
    current = start_path.resolve()
    depth = 0
    outermost: Path | None = None
    while True:
        if (current / _MEMORY_DIR).is_dir():
            outermost = current
        if _has_git_not_memory(current):
            _logger.debug("memory_root_discovery stopped at depth=%d reason=%s", depth, "git_sentinel")
            break
        if depth >= _MAX_UPWARD_DEPTH:
            _logger.debug("memory_root_discovery stopped at depth=%d reason=%s", depth, "max_depth")
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
        depth += 1
    if outermost is not None:
        return outermost
    return _FALLBACK_REPO_ROOT


def discover_workspace_root(project_root: Path) -> Path:
    """Return *project_root* / ``workspace/`` if it exists, else *project_root*."""
    ws = project_root / _WORKSPACE_DIR
    return ws if ws.is_dir() else project_root


def discover_roots(start_path: Path) -> tuple[Path, Path]:
    """Convenience: return ``(repo_root, workspace_root)``."""
    repo = discover_project_root(start_path)
    ws = discover_workspace_root(repo)
    return repo, ws
