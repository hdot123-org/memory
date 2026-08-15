"""Shared test helpers for source_repo fixture construction (INFRA-324 dedup).

INFRA-324: ``source_repo`` fixture definitions in
``test_source_repo_readonly.py`` and ``test_source_repo_develop_mode.py``
duplicated the marker-file creation + ``git init`` block (3 base markers
in ``memory_core/tools/``, optional extras, ``subprocess.run(["git", "init"])``).

Consolidated into a single factory ``make_source_repo``; each test module
calls it with its own ``extra_marker_files`` (or none), so the construction
logic has exactly one implementation site.  Follows the INFRA-297 /
INFRA-313 / INFRA-317 / INFRA-318 dedup precedent pattern.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_BASE_MARKER_FILES: tuple[str, ...] = (
    "memory_hook_gateway.py",
    "factory_global_hooks.py",
    "codex_global_hooks.py",
)


def make_source_repo(
    tmp_path: Path,
    extra_marker_files: tuple[str, ...] = (),
) -> Path:
    """Create a fake memory-core source repo with marker files and return its path.

    Creates ``memory_core/tools/`` with the three base marker files
    (``memory_hook_gateway.py``, ``factory_global_hooks.py``,
    ``codex_global_hooks.py``), any *extra_marker_files* appended
    in the same directory, then runs ``git init`` on the repo root.
    """
    repo = tmp_path / "source-repo"
    nested = repo / "memory_core" / "tools"
    nested.mkdir(parents=True)

    for name in _BASE_MARKER_FILES:
        (nested / name).write_text("# marker\n", encoding="utf-8")

    for name in extra_marker_files:
        (nested / name).write_text("# marker\n", encoding="utf-8")

    subprocess.run(
        ["git", "init"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return repo
