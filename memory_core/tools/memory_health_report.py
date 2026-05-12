#!/usr/bin/env python3
"""Deep project memory health checker — runs asynchronously and writes a report."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Ensure the memory_core package is importable
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
sys.path.insert(0, str(REPO_ROOT))

from memory_core.tools.denied_project_roots import is_denied_project_root


def _is_memory_core_source_repo(path: Path) -> bool:
    """Check if path is the memory-core source repository (anti-pollution)."""
    resolved = path.resolve()
    markers = [
        resolved / "memory_core" / "tools" / "memory_hook_gateway.py",
        resolved / "memory_core" / "tools" / "factory_global_hooks.py",
        resolved / "memory_core" / "tools" / "codex_global_hooks.py",
    ]
    if any(marker.exists() for marker in markers):
        return True
    # Also check git root
    try:
        git_root = subprocess.run(
            ["git", "-C", str(resolved), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=False,
        )
        if git_root.returncode == 0 and git_root.stdout.strip():
            git_path = Path(git_root.stdout.strip())
            git_markers = [
                git_path / "memory_core" / "tools" / "memory_hook_gateway.py",
                git_path / "memory_core" / "tools" / "factory_global_hooks.py",
                git_path / "memory_core" / "tools" / "codex_global_hooks.py",
            ]
            if any(marker.exists() for marker in git_markers):
                return True
    except Exception:
        pass
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="Project root path")
    parser.add_argument("--output", default=None, help="Output report path")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    if not target.exists():
        return 1

    # Anti-pollution: Skip if target is memory-core source repo
    if _is_memory_core_source_repo(target):
        return 0

    if is_denied_project_root(target):
        return 0

    # Change working directory to target
    os.chdir(target)
    os.environ["PWD"] = str(target)

    try:
        from memory_core.tools.memory_hook_gateway import build_context_package
    except ImportError:
        from memory_hook_gateway import build_context_package

    # Fake payload
    payload = {"cwd": str(target)}

    try:
        package = build_context_package("codex", "health-check", payload)
        report = {
            "status": package.get("status"),
            "missing_paths": package.get("missing_paths", []),
            "validation_errors": package.get("validation_errors", []),
            "project_scope": package.get("project_scope"),
            "checked_at": datetime.now().isoformat(),
        }
    except Exception as e:
        report = {
            "status": "error",
            "error": str(e),
            "missing_paths": [],
            "validation_errors": [],
            "checked_at": datetime.now().isoformat(),
        }

    output_path = Path(args.output) if args.output else (target / "memory" / "system" / "health-report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
