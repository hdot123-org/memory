"""Smoke tests for memory-init CLI entry point.

Tests call memory_core.tools.init_project_memory.main() directly
(import, not subprocess) to avoid environment dependency on installed scripts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from memory_core.constants import REQUIRED_MEMORY_DIRS, REQUIRED_MEMORY_FILES

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _call_main(argv: list[str]) -> int:
    """Invoke init_project_memory.main() with patched sys.argv."""
    from memory_core.tools.init_project_memory import main
    old_argv = sys.argv
    try:
        sys.argv = ["memory-init", *argv]
        return main()
    finally:
        sys.argv = old_argv


def _read_adapter_toml(target: Path) -> dict[str, Any]:
    """Parse adapter.toml from target .memory/ directory."""
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    adapter_path = target / ".memory" / "adapter.toml"
    with open(adapter_path, "rb") as f:
        return tomllib.load(f)


# ---------------------------------------------------------------------------
# 1. test_init_creates_required_files_in_target
# ---------------------------------------------------------------------------

def test_init_creates_required_files_in_target(tmp_path: Path) -> None:
    """main([... --target tmp_path]) 后 7 必备文件 + 4 kb 子目录全部存在."""
    exit_code = _call_main(["--target", str(tmp_path)])
    assert exit_code == 0

    memory_root = tmp_path / ".memory"
    assert memory_root.is_dir()

    # 7 required files
    for fname in REQUIRED_MEMORY_FILES:
        assert (memory_root / fname).is_file(), f"{fname} missing"

    # 4 required subdirectories under kb/
    for d in REQUIRED_MEMORY_DIRS:
        assert (memory_root / d).is_dir(), f"kb/{d} missing"


# ---------------------------------------------------------------------------
# 2. test_init_dry_run_does_not_write
# ---------------------------------------------------------------------------

def test_init_dry_run_does_not_write(tmp_path: Path) -> None:
    """--dry-run 后目标目录不应有 .memory/."""
    exit_code = _call_main(["--target", str(tmp_path), "--dry-run"])
    assert exit_code == 0
    assert not (tmp_path / ".memory").exists(), "dry-run should not create .memory/"


# ---------------------------------------------------------------------------
# 3. test_init_dry_run_json_output_shape
# ---------------------------------------------------------------------------

def test_init_dry_run_json_output_shape(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """--dry-run --json 输出可被 json.loads 解析，含至少 success/operations 字段."""
    exit_code = _call_main(["--target", str(tmp_path), "--dry-run", "--json"])
    assert exit_code == 0

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["success"] is True
    assert "dry_run_output" in data
    do = data["dry_run_output"]
    assert "project_name" in do
    assert len(do.get("would_create_files", [])) >= len(REQUIRED_MEMORY_FILES)
    assert len(do.get("would_create_dirs", [])) > 0


# ---------------------------------------------------------------------------
# 4. test_init_with_explicit_scope
# ---------------------------------------------------------------------------

def test_init_with_explicit_scope(tmp_path: Path) -> None:
    """--scope my-proj 后 adapter.toml routing.project_scope == "my_proj"."""
    exit_code = _call_main(["--target", str(tmp_path), "--scope", "my-proj"])
    assert exit_code == 0

    adapter = _read_adapter_toml(tmp_path)
    routing = adapter.get("routing", {})
    assert routing.get("project_scope") == "my_proj"
    assert routing.get("project_name") == "my_proj"


# ---------------------------------------------------------------------------
# 5. test_init_with_host_claude
# ---------------------------------------------------------------------------

def test_init_with_host_claude(tmp_path: Path) -> None:
    """--host claude 后 adapter.toml routing.host == "claude"."""
    exit_code = _call_main(["--target", str(tmp_path), "--host", "claude"])
    assert exit_code == 0

    adapter = _read_adapter_toml(tmp_path)
    routing = adapter.get("routing", {})
    assert routing.get("host") == "claude"


# ---------------------------------------------------------------------------
# 6. test_init_rejects_invalid_host
# ---------------------------------------------------------------------------

def test_init_rejects_invalid_host(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """--host invalid 应因 argparse choices 限制而退出非零."""
    with pytest.raises(SystemExit) as exc_info:
        _call_main(["--target", str(tmp_path), "--host", "invalid"])
    # argparse exits with code 2 for invalid choice
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# 7. test_init_idempotent_on_existing_memory
# ---------------------------------------------------------------------------

def test_init_idempotent_on_existing_memory(tmp_path: Path) -> None:
    """已 init 过的 target 再次 init 不应报错也不应破坏现有内容."""
    # First init
    exit1 = _call_main(["--target", str(tmp_path), "--scope", "proj-x"])
    assert exit1 == 0

    memory_root = tmp_path / ".memory"
    assert memory_root.is_dir()

    # Record canonical content after first init
    canonical_path = memory_root / "CANONICAL.md"
    content_first = canonical_path.read_text(encoding="utf-8")

    # Second init — should succeed (skip existing files)
    exit2 = _call_main(["--target", str(tmp_path), "--scope", "proj-x"])
    assert exit2 == 0

    # Content should be preserved (files are skipped, not overwritten)
    content_second = canonical_path.read_text(encoding="utf-8")
    assert content_first == content_second

    # All required files still exist
    for fname in REQUIRED_MEMORY_FILES:
        assert (memory_root / fname).is_file(), f"{fname} missing after second init"
