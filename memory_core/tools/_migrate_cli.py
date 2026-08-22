#!/usr/bin/env python3.12
"""migrate_project_memory 拆分：CLI 入口（参数解析、回滚模式、输出格式化）。

M3 拆分（与 _gateway_* / _audit_* 同构）：持有 _build_migrate_parser、
--rollback 处理、JSON/文本输出与 main()。依赖链顶层，调用编排模块的
migrate_project_memory 与回滚模块的 plan/execute。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION

from ._migrate_orchestration import migrate_project_memory
from ._migrate_rollback import _find_v05_backup, execute_rollback, plan_rollback

__all__ = [
    "_build_migrate_parser",
    "_emit_json_output",
    "_emit_text_output",
    "_handle_rollback",
    "main",
]


def _build_migrate_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the migrate CLI."""
    parser = argparse.ArgumentParser(description="Migrate a project's .memory/ directory between schema versions.")
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Path to the target project root.",
    )
    parser.add_argument(
        "--from",
        dest="from_version",
        help="Current version of the memory schema.",
    )
    parser.add_argument(
        "--to",
        dest="to_version",
        help="Target version to migrate to.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be done without modifying files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback a previous migration, restoring .memory/ from backup.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {CURRENT_MEMORY_VERSION}")
    return parser


def _handle_rollback(target: Path) -> int:
    """Handle --rollback mode: find backup, plan and execute rollback.

    Returns exit code (0=success, 1=failure, 2=error).
    """
    memory_root = target / ".memory"
    # For rollback, .memory/ may not exist (after 0.4→0.5 migration)
    # but we need it for the plan_rollback and execute_rollback functions
    if not memory_root.exists():
        # Check for v0.5 backup before failing
        v05_backup = _find_v05_backup(target)
        if v05_backup is None:
            print("Error: no backup found for rollback.", file=sys.stderr)
            return 2
        # Create .memory/ temporarily so plan_rollback can find the v0.5 backup
        memory_root.mkdir(parents=True, exist_ok=True)

    plan = plan_rollback(memory_root)
    if not plan["can_rollback"]:
        print(f"Error: {plan.get('reason', 'cannot rollback')}", file=sys.stderr)
        return 2

    print(f"Rolling back from backup: {plan['backup_dir']}")
    print(f"  From: {plan['from_version']} -> To: {plan['to_version']}")

    rb_result = execute_rollback(memory_root)
    if rb_result["success"]:
        print(f"Rollback succeeded. Restored from: {rb_result['restored_from']}")
        return 0
    else:
        print(f"Rollback failed: {rb_result.get('error', 'unknown')}", file=sys.stderr)
        return 1


def _emit_json_output(result: dict[str, Any]) -> None:
    """Print migration result as JSON."""
    output = dict(result)
    for key in ("from_version", "to_version", "target"):
        if key not in output:
            output[key] = ""
    print(json.dumps(output, indent=2, ensure_ascii=False))


def _emit_text_output(result: dict[str, Any]) -> None:
    """Print migration result as human-readable text."""
    print("=" * 60)
    print("Project Memory Migration Report")
    print("=" * 60)
    if result["dry_run"]:
        print(f"  [DRY RUN] Would migrate .memory/ under: {result['target']}")
        print(f"  From: {result['from_version']} -> To: {result['to_version']}")
    print("-" * 60)
    print("  Migrations:")
    for m in result.get("migrations_executed", []):
        status = m["status"]
        print(f"    [{status.upper()}] {m['key']}")
        if m.get("detail"):
            print(f"      {m['detail']}")
    print("-" * 60)
    if result.get("log_entries"):
        print("  Log entries:")
        for entry in result["log_entries"]:
            print(f"    {entry}")
        print("-" * 60)
    if result.get("residue"):
        print("  Residue:")
        for r in result["residue"]:
            print(f"    [RESIDUE] {r}")
        print("-" * 60)
    if result.get("errors"):
        print("  Errors:")
        for e in result["errors"]:
            print(f"    [ERROR] {e}")
        print("-" * 60)
    status = "SUCCESS" if result["success"] else "FAILED"
    print(f"  Status: {status}")
    rb = result.get("rollback", {})
    if rb.get("steps"):
        print(f"  Rollback: {rb.get('warning', '')}")
    print("=" * 60)


def main() -> int:
    parser = _build_migrate_parser()
    args = parser.parse_args()

    # Validate required args for non-rollback mode
    if not args.rollback and (not args.from_version or not args.to_version):
        print("Error: --from and --to are required unless --rollback is specified.", file=sys.stderr)
        return 2

    target = args.target.resolve()
    if not target.is_dir():
        print(f"Error: target path does not exist: {target}", file=sys.stderr)
        return 2

    # Handle --rollback mode
    if args.rollback:
        return _handle_rollback(target)

    result = migrate_project_memory(
        target,
        args.from_version,
        args.to_version,
        dry_run=args.dry_run,
    )

    if args.json:
        _emit_json_output(result)
    else:
        _emit_text_output(result)

    return 0 if result["success"] else 1
