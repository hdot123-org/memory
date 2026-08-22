"""Shared test helpers for migration tests.

Extracted by INFRA-313 (CODE_HYGIENE_DUPLICATE_BLOCK): two test files
(test_migrate_idempotent_rollback.py, test_cli_migrate.py) contained identical
_count_log_lines definitions (100% AST similarity). Follows INFRA-283
(silent_swallow_helpers) / INFRA-300 (git_helpers) precedent.

INFRA-313: Consolidated into a single helper; each test module imports it
under its historical local name via aliased import, so existing call sites
stay unchanged. Public test names and assertions are preserved.

INFRA-318: Also consolidates _create_memory_skeleton which had 81% AST
similarity (24 lines / 150 tokens vs 20 lines / 159 tokens) across the
same two files.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from memory_core.constants import CURRENT_MEMORY_VERSION


def count_log_lines(log_path: Path) -> int:
    """Count non-comment, non-empty lines in migrations.log.

    INFRA-313: extracted from 2 identical _count_log_lines bodies
    (100% AST similarity). Returns 0 when the log file does not exist.
    """
    if not log_path.is_file():
        return 0
    text = log_path.read_text(encoding="utf-8")
    return sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith("#"))


def create_memory_skeleton(
    tmp_path: Path,
    *,
    version: str = CURRENT_MEMORY_VERSION,
    adapter_version: str = "0.1.0",
) -> Path:
    """Create a valid .memory/ skeleton and return the project root.

    INFRA-318: extracted from two near-identical _create_memory_skeleton
    definitions in test_migrate_idempotent_rollback.py and test_cli_migrate.py.
    The adapter_version parameter supports the CLI test variant that writes
    a custom adapter version into adapter.toml.
    """
    memory_root = tmp_path / ".memory"
    memory_root.mkdir(parents=True)
    (memory_root / "kb" / "projects").mkdir(parents=True)
    (memory_root / "kb" / "decisions").mkdir(parents=True)
    (memory_root / "kb" / "lessons").mkdir(parents=True)
    (memory_root / "kb" / "global").mkdir(parents=True)

    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    (memory_root / "memory.lock").write_text(
        f'# memory.lock\n[memory]\nmemory_version = "{version}"\n'
        f'schema_version = "context-package-v1"\nadapter_version = "builtin"\n'
        f'locked_at = "{now}"\nlock_reason = "initial"\n',
        encoding="utf-8",
    )
    (memory_root / "adapter.toml").write_text(
        f'[core]\nversion = "{adapter_version}"\nadapter = "default"\n',
        encoding="utf-8",
    )
    (memory_root / "migrations.log").write_text(
        "# Migrations Log\n",
        encoding="utf-8",
    )
    return tmp_path
