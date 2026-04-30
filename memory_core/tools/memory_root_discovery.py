"""Discover memory-system project roots by walking the directory tree.

The canonical project-root marker is a ``.memory/`` directory.  This module
provides pure functions that resolve *repo root* and *workspace root* from an
arbitrary starting path without depending on any gateway globals.
"""
from __future__ import annotations

from pathlib import Path

# Fallback used when no .memory/ ancestor is found.
_SCRIPT_PATH = Path(__file__).resolve()
_FALLBACK_REPO_ROOT = _SCRIPT_PATH.parents[2]

_MEMORY_DIR = ".memory"
_WORKSPACE_DIR = "memory_core"


def discover_project_root(start_path: Path) -> Path:
    """Walk *start_path* and its ancestors looking for a ``.memory/`` directory.

    Returns the first ancestor (inclusive) that contains ``.memory/``.
    Falls back to the repository root derived from this module's location
    when nothing is found.
    """
    current = start_path.resolve()
    while True:
        if (current / _MEMORY_DIR).is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
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
