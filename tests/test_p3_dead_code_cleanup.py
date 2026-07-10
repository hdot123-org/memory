#!/usr/bin/env python3
"""Tests for P3 C.9: CLAUDE_HOOK_STATE_DIR dead code cleanup.

Verifies that CLAUDE_HOOK_STATE_DIR does not appear anywhere in memory_core
(except possibly in archive/ or docs/ which are not code).
"""

from __future__ import annotations

import subprocess
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root setup
# ---------------------------------------------------------------------------

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

MEMORY_CORE = repo_root / "memory_core"


class TestClaudeHookStateDirDeadCode:
    """C.9: CLAUDE_HOOK_STATE_DIR should not appear in memory_core source code."""

    def test_no_claude_hook_state_dir_in_memory_core(self) -> None:
        """Grep entire memory_core tree; CLAUDE_HOOK_STATE_DIR must not appear."""
        # Try rg first, fall back to grep if rg is not available (e.g., in CI)
        rg_available = shutil.which("rg") is not None
        if rg_available:
            result = subprocess.run(
                ["rg", "-l", "CLAUDE_HOOK_STATE_DIR", str(MEMORY_CORE)],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            # Fallback to grep
            result = subprocess.run(
                ["grep", "-rl", "CLAUDE_HOOK_STATE_DIR", str(MEMORY_CORE)],
                capture_output=True,
                text=True,
                check=False,
            )
        if result.returncode == 0:
            # Files found — filter out archive/ only (allowed exception)
            files = [
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip()
                and "/archive/" not in line
                and "/docs/" not in line
            ]
            assert not files, (
                f"CLAUDE_HOOK_STATE_DIR still found in memory_core source: {files}"
            )

    def test_no_claude_hook_state_dir_in_gateway_module(self) -> None:
        """CLAUDE_HOOK_STATE_DIR must not be in memory_hook_gateway.py."""
        gateway_path = MEMORY_CORE / "tools" / "memory_hook_gateway.py"
        if gateway_path.exists():
            content = gateway_path.read_text(encoding="utf-8")
            assert "CLAUDE_HOOK_STATE_DIR" not in content, (
                "CLAUDE_HOOK_STATE_DIR should not appear in gateway module"
            )
