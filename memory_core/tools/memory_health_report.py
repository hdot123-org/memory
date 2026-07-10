#!/usr/bin/env python3
"""Deep project memory health checker — runs asynchronously and writes a report."""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

# Ensure the memory_core package is importable
SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[2]
sys.path.insert(0, str(REPO_ROOT))

from memory_core.tools.denylist import is_denied_project_root

# M3: Import is_memory_core_source_repo from ownership module
try:
    from memory_core.ownership import is_memory_core_source_repo
except ImportError:
    is_memory_core_source_repo = None  # type: ignore


def _run_layout_audit(target: Path) -> dict[str, Any] | None:
    """Run layout audit and return summary, or None if unavailable/error.

    This is a read-only operation that does not modify any files.
    """
    try:
        # Import audit module - may not be available
        from memory_core.tools.audit_project_layout import audit_project_layout

        result = audit_project_layout(target)
        summary = result.to_dict().get("summary", {})
        findings = result.findings

        # Count root pollution findings
        root_pollution_count = sum(1 for f in findings if f.suggested_bucket == "root_pollution")

        # Check for multi-generation conflict (from audit findings)
        multi_generation_conflict = any(f.kind == "multi_generation_conflict" for f in findings)

        # Also check for real workspace conflict that requires manual mode
        # Real conflict = root memory structures + workspace structures
        has_real_workspace_conflict = _has_workspace_memory_conflict(target, findings)

        # Determine recommended mode
        recommended_mode = _determine_recommended_mode(
            total=summary.get("total", 0),
            p0=summary.get("p0", 0),
            p1=summary.get("p1", 0),
            p2=summary.get("p2", 0),
            root_pollution_count=root_pollution_count,
            multi_generation_conflict=multi_generation_conflict,
            has_real_workspace_conflict=has_real_workspace_conflict,
            has_system_memory=(target / "memory" / "system").exists(),
        )

        return {
            "total": summary.get("total", 0),
            "p0": summary.get("p0", 0),
            "p1": summary.get("p1", 0),
            "p2": summary.get("p2", 0),
            "root_pollution_count": root_pollution_count,
            "multi_generation_conflict": multi_generation_conflict,
            "has_real_workspace_conflict": has_real_workspace_conflict,
            "recommended_mode": recommended_mode,
        }
    except ImportError:
        # Audit module not available - degrade gracefully
        warnings.warn("audit_project_layout module not available", RuntimeWarning, stacklevel=2)
        return None
    except Exception as e:
        # Audit failed - degrade gracefully with warning
        warnings.warn(f"Layout audit failed: {e}", RuntimeWarning, stacklevel=2)
        return {
            "error": str(e),
            "degraded": True,
        }


def _has_workspace_memory_conflict(target: Path, findings: list) -> bool:
    """Check if there's a real workspace conflict that requires manual mode.

    Real conflict = root memory structures (memory/system/, memory/, project-map/)
    coexist with workspace structures (workspace/memory/, workspace/project-map/).

    Having just memory/system/ + memory/ + project-map/ without workspace
    structures is a valid current layout, not a conflict.
    """
    # Check for workspace structures
    has_workspace_memory = (target / "workspace" / "memory").exists()
    has_workspace_project_map = (target / "workspace" / "project-map").exists()

    if not has_workspace_memory and not has_workspace_project_map:
        # No workspace structures = no real conflict
        return False

    # Check if there's any conflict finding that mentions workspace
    for finding in findings:
        if finding.kind == "multi_generation_conflict":
            message = getattr(finding, "message", "")
            # If the finding message mentions workspace, it's a real conflict
            if "workspace" in message.lower():
                return True

    # Also detect directly if audit didn't flag it
    has_root_system_memory = (target / "memory" / "system").exists()
    has_root_memory = (target / "memory").exists()
    has_root_project_map = (target / "project-map").exists()

    root_structures = has_root_system_memory or has_root_memory or has_root_project_map
    workspace_structures = has_workspace_memory or has_workspace_project_map

    return root_structures and workspace_structures


def _determine_recommended_mode(
    total: int,
    p0: int,
    p1: int,
    p2: int,
    root_pollution_count: int,
    multi_generation_conflict: bool,
    has_real_workspace_conflict: bool,
    has_system_memory: bool,
) -> str:
    """Determine recommended initialization mode based on audit findings.

    Modes:
        - fresh: Clean project, no memory structures
        - adopt: Has memory/system structure but some legacy residue
        - update: Clean memory/system structure, no conflicts
        - repair: Has issues that need fixing but auto-fixable
        - manual: Complex multi-generation conflicts need human decision
    """
    # Only recommend manual for real workspace conflicts
    if has_real_workspace_conflict:
        return "manual"

    # Also check for multi_generation_conflict from audit (for compatibility)
    if multi_generation_conflict and has_real_workspace_conflict:
        return "manual"

    if total == 0:
        # No findings - clean project
        return "fresh" if not has_system_memory else "update"

    if p0 > 0:
        # Critical issues (but not workspace conflicts)
        if not has_system_memory:
            return "adopt"
        return "repair"

    if p1 > 0:
        # Important issues
        if not has_system_memory:
            return "adopt"
        return "repair"

    if p2 > 0 or root_pollution_count > 0:
        # Minor issues - can repair or update
        return "repair" if has_system_memory else "adopt"

    return "update" if has_system_memory else "adopt"


# M3: is_memory_core_source_repo now imported from memory_core.ownership


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True, help="Project root path")
    parser.add_argument("--output", default=None, help="Output report path")
    args = parser.parse_args()

    target = Path(args.target).resolve()
    if not target.exists():
        return 1

    # M3: Anti-pollution: Skip if target is memory-core source repo
    if is_memory_core_source_repo is not None and is_memory_core_source_repo(target):
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

    # Run layout audit (read-only, never modifies files)
    layout_audit = _run_layout_audit(target)
    if layout_audit:
        report["layout_audit"] = layout_audit
        # Surface layout audit findings without letting them hard-fail the health report.
        if layout_audit.get("degraded"):
            if report["status"] != "error":
                report["status"] = "degraded"
        elif layout_audit.get("p0", 0) > 0 or layout_audit.get("p1", 0) > 0:
            if report["status"] not in ("error", "degraded"):
                report["status"] = "degraded"

    output_path = Path(args.output) if args.output else (target / "memory" / "system" / "health-report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
