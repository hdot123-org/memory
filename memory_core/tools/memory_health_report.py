#!/usr/bin/env python3
"""Deep project memory health checker — runs asynchronously and writes a report."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure the memory_core package is importable
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
sys.path.insert(0, str(REPO_ROOT))

# Switch to target directory so discover_roots works correctly
# This is critical because build_context_package relies on cwd

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="Project root path")
    parser.add_argument("--output", default=None, help="Output report path")
    args = parser.parse_args()
    
    target = Path(args.target).resolve()
    if not target.exists():
        return 1
        
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
        # Use 'codex' as host since it validates the input
        package = build_context_package("codex", "health-check", payload)
        
        report = {
            "status": package.get("status"),
            "missing_paths": package.get("missing_paths", []),
            "validation_errors": package.get("validation_errors", []),
            "project_scope": package.get("project_scope"),
            "generated_at": package.get("generated_at"),
        }
    except Exception as e:
        report = {
            "status": "error",
            "error": str(e),
            "missing_paths": [],
            "validation_errors": [],
        }
    
    output_path = Path(args.output) if args.output else (target / "memory" / "system" / "health-report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
