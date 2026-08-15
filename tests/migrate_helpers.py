"""Shared migrate test helpers (INFRA-313 dedup).

INFRA-313: Function '_count_log_lines' had 100% AST similarity across test
files (test_migrate_idempotent_rollback.py, test_cli_migrate.py). Both
variants counted non-comment, non-empty lines in .memory/migrations.log.

Consolidated into a single helper; each test module imports it under its
historical local name via aliased import, so existing call sites stay
unchanged. Public test names and assertions are preserved.
"""

from __future__ import annotations

from pathlib import Path


def count_log_lines(log_path: Path) -> int:
    """Count non-comment, non-empty lines in migrations.log.

    INFRA-313: extracted from 2 identical _count_log_lines bodies
    (100% AST similarity). Returns 0 when the log file does not exist.
    """
    if not log_path.is_file():
        return 0
    text = log_path.read_text(encoding="utf-8")
    return sum(
        1 for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    )
