"""Shared git-repo test helpers (INFRA-300 dedup).

INFRA-300: Function '_setup_git_repo' had 99% AST similarity across test files
(test_compat_and_cross_flows, test_lifecycle_retention, test_event_sharding).
All variants created a minimal git repo (git init + repo-local user.email /
user.name config) for deterministic project_id generation.

Consolidated into a single helper; each test module imports it under its
historical local name via aliased import, so existing call sites stay unchanged.
Public test names and assertions are preserved.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def setup_git_repo(project_dir: Path) -> None:
    """Initialize a minimal git repo for deterministic project_id generation.

    INFRA-300: extracted from 3 near-identical _setup_git_repo bodies
    (99% AST similarity). Creates *project_dir*, runs ``git init``, and sets
    repo-local (never ``--global``) test identity so tests do not depend on
    the developer's global git config.
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=project_dir, check=True, capture_output=True, text=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=project_dir, check=True, capture_output=True, text=True
    )
