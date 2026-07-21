#!/usr/bin/env python3
"""End-to-end test: memory-init writes INDEX.md with schema headers (T2.5 + T2.3)."""

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from memory_core.tools.index_schema import (
    PROJECT_VERSION_MARKER,
    SCHEMA_VERSION_MARKER,
    parse_headers,
)
from memory_core.tools.init_project_memory import init_project_memory


def test_init_injects_index_schema_headers(tmp_path: Path):
    target = tmp_path / "consumer-project"
    target.mkdir()
    result = init_project_memory(
        target,
        scope="consumer-project",
        host="codex",
        dry_run=False,
        json_output=True,
        force=False,
        no_clobber=False,
        mode="create",
    )
    assert result["success"], result
    index = target / "INDEX.md"
    assert index.exists()
    content = index.read_text(encoding="utf-8")
    headers = parse_headers(content)
    assert SCHEMA_VERSION_MARKER in headers
    assert PROJECT_VERSION_MARKER in headers


def test_init_post_check_runs(tmp_path: Path, capsys):
    # Use the main() entry point to verify the post-init summary prints
    from memory_core.tools.init_project_memory import main

    target = tmp_path / "consumer-project"
    target.mkdir()
    rc = main(["--target", str(target), "--scope", "consumer-project"])
    captured = capsys.readouterr()
    assert rc == 0
    # Post-init self-check summary should appear on stdout
    assert "Post-init consumer self-check" in captured.out
