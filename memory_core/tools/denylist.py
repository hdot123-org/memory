"""Project denylist mechanism for memory-core.

This module implements path rejection logic to prevent memory initialization
and hook execution in inappropriate locations:

- $TMPDIR and /tmp subdirectories
- ~/.factory subdirectories
- $HOME root (exact match)
- Pattern-based junk directory names (tmp.*, demo-*, test-*, smoke-test-*, restart-*, file-list-*)
- Non-git directories (without --allow-non-git flag)
- Explicit denied project roots (from denied_project_roots module)

The denylist is enforced at two points:
1. init_project_memory.py: During memory initialization
2. memory_hook_gateway.py: At runtime when processing hook events
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DenylistResult:
    """Result of a denylist check.

    Attributes:
        denied: Whether the path is denied
        rule: The rule that triggered denial (e.g., "tmpdir", "factory", "home_root", "junk_pattern", "non_git")
        message: Human-readable error message explaining the denial and available overrides
    """
    denied: bool
    rule: Optional[str] = None
    message: Optional[str] = None

    @classmethod
    def denied_ok(cls) -> "DenylistResult":
        """Create a result indicating the path is allowed."""
        return cls(denied=False)

    @classmethod
    def denied(cls, rule: str, message: str) -> "DenylistResult":
        """Create a result indicating the path is denied."""
        return cls(denied=True, rule=rule, message=message)


# Junk directory name patterns that should be rejected
JUNK_DIR_PATTERNS = [
    re.compile(r"^tmp\..*"),           # tmp.*
    re.compile(r"^demo-.*"),           # demo-*
    re.compile(r"^test-.*"),           # test-*
    re.compile(r"^smoke-test-.*"),     # smoke-test-*
    re.compile(r"^restart-.*"),        # restart-*
    re.compile(r"^file-list-.*"),      # file-list-*
]


def check_denylist(target: Path, allow_non_git: bool = False) -> DenylistResult:
    """Check if a target path is denied by the denylist.

    Args:
        target: The project directory path to check
        allow_non_git: If True, allow non-git directories; if False, reject them

    Returns:
        DenylistResult indicating whether the path is denied and why

    Checks performed (in order):
    1. $TMPDIR subdirectories
    2. /tmp subdirectories
    3. ~/.factory subdirectories
    4. $HOME root (exact match)
    5. Junk directory name patterns
    6. Non-git directories (if allow_non_git is False)
    """
    # Test-only bypass: allow pytest tests to bypass denylist checks
    if os.environ.get("MEMORY_CORE_BYPASS_DENYLIST") == "1":
        return DenylistResult.denied_ok()

    target_resolved = target.resolve()
    target_name = target_resolved.name

    # 1. Check $TMPDIR
    tmpdir = os.environ.get("TMPDIR")
    if tmpdir:
        tmpdir_path = Path(tmpdir).resolve()
        if target_resolved == tmpdir_path or str(target_resolved).startswith(str(tmpdir_path) + os.sep):
            return DenylistResult.denied(
                "tmpdir",
                f"Path is under $TMPDIR ({tmpdir_path}). "
                f"Temporary directories are not suitable for project memory."
            )

    # 2. Check /tmp (and /private/tmp on macOS where /tmp is a symlink)
    target_str = str(target_resolved)
    if (
        target_str == "/tmp"
        or target_str.startswith("/tmp/")
        or target_str == "/private/tmp"
        or target_str.startswith("/private/tmp/")
    ):
        return DenylistResult.denied(
            "tmpdir",
            "Path is under /tmp. Temporary directories are not suitable for project memory."
        )

    # 3. Check ~/.factory
    factory_path = (Path.home() / ".factory").resolve()
    if target_resolved == factory_path or str(target_resolved).startswith(str(factory_path) + os.sep):
        return DenylistResult.denied(
            "factory",
            f"Path is under ~/.factory ({factory_path}). "
            f"Factory internal directories should not have project memory."
        )

    # 4. Check $HOME root (exact match)
    home_path = Path.home().resolve()
    if target_resolved == home_path:
        return DenylistResult.denied(
            "home_root",
            f"Path is $HOME ({home_path}). "
            f"Initialize memory in a specific project directory, not the home root."
        )

    # 5. Check junk directory name patterns
    for pattern in JUNK_DIR_PATTERNS:
        if pattern.match(target_name):
            return DenylistResult.denied(
                "junk_pattern",
                f"Directory name '{target_name}' matches junk pattern '{pattern.pattern}'. "
                f"These directories are typically temporary or test artifacts."
            )

    # 6. Check non-git directories
    if not allow_non_git:
        git_dir = target_resolved / ".git"
        if not git_dir.exists():
            return DenylistResult.denied(
                "non_git",
                "Path is not a git repository (no .git directory found). "
                "Use --allow-non-git to override this check if the directory is a valid project."
            )

    return DenylistResult.denied_ok()


def denied_project_roots() -> list[Path]:
    """Return exact project roots that memory hooks must never manage."""
    roots: list[Path] = []
    try:
        roots.append(Path.home())
    except RuntimeError:
        pass

    configured = os.environ.get("MEMORY_HOOK_DENY_PROJECT_ROOTS", "")
    for raw in configured.split(os.pathsep):
        value = raw.strip()
        if value:
            roots.append(Path(value).expanduser())

    deduped: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(resolved)
    return deduped


def is_denied_project_root(path: Path) -> bool:
    """Return True only when path exactly matches a denied project root.

    This function consolidates the denied_project_roots logic into the denylist module
    for unified path rejection handling.
    """
    resolved = path.expanduser().resolve(strict=False)
    return any(resolved == denied for denied in denied_project_roots())
