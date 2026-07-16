#!/usr/bin/env python3
"""PreToolUse guard for memory-core ownership protection.

Reads stdin JSON payload, classifies the target path, and outputs
{"decision":"block"/"allow","reason":"..."} JSON to stdout.

Exit codes:
- 0: allow
- 2: block
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from memory_core.tools._guard_classify import _get_project_root_for_task, classify_tool_use  # noqa: F401
from memory_core.tools._guard_patterns import FORBIDDEN_DIRS, FORBIDDEN_SUFFIXES  # noqa: F401
from memory_core.tools.memory_hook_metrics import _resolve_metrics_path, append_metrics_record

# Import now_iso utility (REF-001 §4.8)
try:
    from ._file_utils import now_iso
except ImportError:
    from _file_utils import now_iso  # type: ignore


def _load_project_root() -> Path | None:
    """Determine project root from environment."""
    # Try FACTORY_PROJECT_DIR first
    factory_dir = os.environ.get("FACTORY_PROJECT_DIR")
    if factory_dir:
        return Path(factory_dir).expanduser().resolve()

    # Try MEMORY_HOOK_ORIGINAL_CWD
    original_cwd = os.environ.get("MEMORY_HOOK_ORIGINAL_CWD")
    if original_cwd:
        return Path(original_cwd).expanduser().resolve()

    # Fallback to current working directory
    try:
        return Path.cwd().resolve()
    except Exception:
        return None


_now_iso = now_iso


def _write_metrics_jsonl(project_root: Path, record: dict[str, Any]) -> None:
    """Write a metrics record to metrics.jsonl using append_metrics_record."""
    try:
        metrics_path = _resolve_metrics_path(project_root / "memory" / "artifacts" / "memory-hook")
        append_metrics_record(metrics_path, record)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("metrics write failed: %s", exc)


def main() -> int:
    """Main entry point for PreToolUse guard."""
    start_time = time.time()

    # MEMORY_HOOK_FORCE does NOT bypass PreToolUse guard
    # This is intentional - PreToolUse is a hard guard

    # Read JSON payload from stdin
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"decision": "allow", "reason": f"Invalid JSON input: {e}"}))
        return 0
    except Exception as e:
        print(json.dumps({"decision": "allow", "reason": f"Error reading input: {e}"}))
        return 0

    # Normalize payload: Factory hooks wrap tool params in tool_input
    # Standalone tests pass fields at top level
    if "tool_input" in payload:
        tool_input = payload.get("tool_input", {})
        for k, v in tool_input.items():
            payload.setdefault(k, v)

    # Get project root
    project_root = _load_project_root()
    if project_root is None:
        print(json.dumps({"decision": "allow", "reason": "Cannot determine project root"}))
        return 0

    # Check if memory/system exists (if not, this isn't a memory-managed project)
    if not (project_root / "memory" / "system").exists():
        print(json.dumps({
            "decision": "allow",
            "reason": "Not a memory-managed project (no memory/system directory)"
        }))
        return 0

    # Classify the tool use
    result = classify_tool_use(payload, project_root)

    # Write metrics to local JSONL (replaces PostHog telemetry)
    try:
        duration_ms = int((time.time() - start_time) * 1000)
        metrics_record = {
            "event": "tool_used",
            "tool_name": payload.get("tool_name", "unknown"),
            "decision": result.get("decision", "unknown"),
            "reason": result.get("reason", ""),
            "duration_ms": duration_ms,
            "timestamp": _now_iso(),
        }
        _write_metrics_jsonl(project_root, metrics_record)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("metrics write failed in main: %s", exc)

    # Output JSON result
    print(json.dumps(result))

    # Exit code: 0 = allow, 2 = block
    if result["decision"] == "block":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
