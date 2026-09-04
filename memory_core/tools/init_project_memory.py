#!/usr/bin/env python3.12
"""Initialize a memory/system/ directory skeleton in a target project.

This module is the main entry point that coordinates initialization by delegating
to specialized submodules.

Usage:
    python init_project_memory.py --target /path/to/project
    python init_project_memory.py --target /path/to/project --dry-run
    python init_project_memory.py --target /path/to/project --dry-run --json
    python init_project_memory.py --target /path/to/project --host claude
    python init_project_memory.py --target /path/to/project --force
    python init_project_memory.py --target /path/to/project --no-clobber
    python init_project_memory.py --target /path/to/project --no-auto-fill

This tool creates the minimal memory/system/ directory structure required by the
memory system. It is designed to run against a *business project* repository,
NOT against the memory repository itself.

Key guarantees:
    - Default target is the business project repository
    - Does NOT write real project state into the memory repository
    - Generated skeleton passes validate_project_memory.py
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION, SUPPORTED_HOSTS

# Import from submodules (absolute imports for script execution)
from memory_core.tools._init_autofill import _enrich_project_info_from_config, fill_template_fields
from memory_core.tools._init_config import (
    CLAUDE_HOOK_EVENTS,
    DIRECTORY_STRUCTURE,
    ESSENTIAL_FILES,
    FILE_TEMPLATES,
    KB_TEMPLATES,
    MEMORY_HOOK_BEGIN_MARKER,
    MEMORY_HOOK_END_MARKER,
    RUNTIME_EXTRA_FILES,
    RUNTIME_KB_FILES,
)
from memory_core.tools._init_finalize import _finalize_init
from memory_core.tools._init_hooks import (
    _cleanup_legacy_hooks_json,
    _is_old_bare_gateway_command,
    _scrub_legacy_refs,
    generate_hooks_json,
    template_agents_md_block,
    template_hooks_json,
    update_agents_md,
)
from memory_core.tools._init_pipeline import (
    _build_dry_run_result,
    _create_directories,
    _find_repo_root,
    _is_memory_repo,
    _validate_init_args,
)
from memory_core.tools._init_render import _render_all_templates
from memory_core.tools._init_templates_core import (
    _decorate_index_content,
    _is_index_md,
    _now_iso,
    _project_name,
    _slug,
    template_adapter_toml,
    template_canonical_md,
    template_memory_lock,
)
from memory_core.tools._init_templates_misc import (
    template_inbox_md,
    template_migrations_log,
    template_ownership_toml,
    template_project_scope_md,
)
from memory_core.tools._init_templates_plans import (
    template_now_md,
    template_plan_md,
    template_state_md,
    template_tasks_md,
)
from memory_core.tools.global_kb_init import create_global_kb_structure, get_global_kb_root

# Setup logging for template warnings
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Re-export symbols for backward compatibility
__all__ = [
    # Constants
    "CLAUDE_HOOK_EVENTS",
    "DIRECTORY_STRUCTURE",
    "ESSENTIAL_FILES",
    "FILE_TEMPLATES",
    "KB_TEMPLATES",
    "MEMORY_HOOK_BEGIN_MARKER",
    "MEMORY_HOOK_END_MARKER",
    "RUNTIME_EXTRA_FILES",
    "RUNTIME_KB_FILES",
    # Helper functions
    "_now_iso",
    "_slug",
    "_project_name",
    "_is_index_md",
    "_decorate_index_content",
    # Template functions
    "template_memory_lock",
    "template_adapter_toml",
    "template_canonical_md",
    "template_plan_md",
    "template_state_md",
    "template_tasks_md",
    "template_now_md",
    "template_migrations_log",
    "template_inbox_md",
    "template_ownership_toml",
    "template_project_scope_md",
    "template_hooks_json",
    "generate_hooks_json",
    "template_agents_md_block",
    # Hook functions
    "_is_old_bare_gateway_command",
    "_cleanup_legacy_hooks_json",
    "_scrub_legacy_refs",
    "update_agents_md",
    # Fill functions
    "fill_template_fields",
    "_enrich_project_info_from_config",
    # Main functions
    "init_project_memory",
    "main",
]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def init_project_memory(
    target: Path,
    *,
    scope: str | None = None,
    host: str = "factory",
    dry_run: bool = False,
    json_output: bool = False,
    force: bool = False,
    no_clobber: bool = False,
    mode: str = "create",
    auto_fill: bool = True,
    allow_non_git: bool = False,
) -> dict[str, Any]:
    """Initialize memory/system/ directory skeleton in the target project.

    Args:
        target: Path to the target project root.
        scope: Explicit project scope name (auto-discovered if omitted).
        host: Host platform for hook gateway configuration ("factory" or "zcode"; see SUPPORTED_HOSTS).
        dry_run: If True, only report what would be created.
        json_output: If True, return structured output dict.
        force: If True, overwrite existing files.
        no_clobber: If True, error if any essential file already exists.
        mode: One of "create", "adopt", "update", "repair".
            - create: Standard initialization (default).
            - adopt: Adopt existing project without overwriting business files.
            - update: Update existing memory structure, replace marked blocks.
            - repair: Repair missing required files only.
        auto_fill: If True (default), auto-detect project info and fill templates.
            Set to False to keep all placeholders ("（待填写）").

    Returns:
        Dict with 'success', 'created', 'skipped', 'errors', 'mode', 'warnings' keys.
    """
    result: dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "target": str(target.resolve()),
        "created": [],
        "skipped": [],
        "errors": [],
        "mode": "dry-run" if dry_run else mode,
        "requested_mode": mode,
        "warnings": [],
        "force_overwrite": False,
    }

    memory_root = target / "memory" / "system"
    project_name = _project_name(target, scope)

    # Validate arguments
    is_valid, error_msg = _validate_init_args(target, mode, no_clobber, allow_non_git, memory_root, project_name)
    if not is_valid:
        result["errors"].append(error_msg)
        result["mode"] = "error"
        return result

    # Mode-aware business file check
    index_md_path = target / "INDEX.md"
    has_business_index = (
        index_md_path.exists()
        and "project-map" not in index_md_path.read_text(encoding="utf-8", errors="ignore").lower()
    )
    if mode in ("adopt", "update", "repair") and has_business_index:
        result["warnings"].append(f"{mode} mode: skipping business INDEX.md (not a memory file)")

    # Dry-run mode
    if dry_run:
        result["success"] = True
        result["dry_run_output"] = _build_dry_run_result(target, mode, force, project_name, memory_root)
        result["force_overwrite"] = force
        result["action_taken"] = "dry-run"
        return result

    # Safety guard: do NOT initialize inside the memory repo itself
    repo_root = _find_repo_root(target)
    if repo_root and _is_memory_repo(repo_root):
        result["errors"].append(
            "Refusing to initialize memory/system/ inside the memory repository itself. "
            "This tool is for business project repositories only."
        )
        return result

    # Create global KB structure
    global_kb_root = get_global_kb_root()
    global_kb_result = create_global_kb_structure(global_kb_root)
    if global_kb_result["success"]:
        result["created"].extend(global_kb_result["created_paths"])
        result["skipped"].extend(global_kb_result["skipped_paths"])
    else:
        result["warnings"].extend(global_kb_result["errors"])

    # Create directories
    _create_directories(target, result)

    # Render all templates
    any_overwritten, any_skipped = _render_all_templates(target, memory_root, project_name, host, mode, force, result)

    result["success"] = len(result["errors"]) == 0
    result["force_overwrite"] = force
    result["action_taken"] = "overwrite" if any_overwritten else ("skip" if any_skipped else "create")
    result["mode"] = result["action_taken"] if mode == "create" else mode

    # Finalize
    _finalize_init(target, memory_root, project_name, host, mode, force, auto_fill, result)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a memory/system/ directory skeleton in a target project.")
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Path to the target project root (business project repository).",
    )
    parser.add_argument(
        "--scope",
        type=str,
        default=None,
        help="Explicit project scope name. If omitted, auto-discovered from git remote or directory name.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be created without writing files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="factory",
        choices=SUPPORTED_HOSTS,
        help="Host platform for hook gateway configuration (default: factory).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Overwrite existing files (default: skip existing files).",
    )
    parser.add_argument(
        "--no-clobber",
        action="store_true",
        default=False,
        help="Error if any essential file already exists (mutually exclusive with --force).",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="create",
        choices=["create", "adopt", "update", "repair"],
        help="Initialization mode: create (default), adopt, update, or repair.",
    )
    parser.add_argument(
        "--no-auto-fill",
        action="store_true",
        default=False,
        help="Disable automatic project info detection and template filling.",
    )
    parser.add_argument(
        "--allow-non-git",
        action="store_true",
        default=False,
        help="Allow initialization in non-git directories (default: reject non-git).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {CURRENT_MEMORY_VERSION}")
    args = parser.parse_args(argv)

    # Validate mutually exclusive options
    if args.force and args.no_clobber:
        print(
            "Error: --force and --no-clobber are mutually exclusive. "
            "Use --force to overwrite, or --no-clobber to error on existing files.",
            file=sys.stderr,
        )
        return 2

    target = args.target.resolve()
    if not target.is_dir():
        print(f"Error: target path does not exist or is not a directory: {target}", file=sys.stderr)
        return 2

    result = init_project_memory(
        target,
        scope=args.scope,
        host=args.host,
        dry_run=args.dry_run,
        json_output=args.json,
        force=args.force,
        no_clobber=args.no_clobber,
        mode=args.mode,
        auto_fill=not args.no_auto_fill,
        allow_non_git=args.allow_non_git,
    )

    if args.json or args.dry_run:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("Project Memory Initialization Report")
        print("=" * 60)
        if result["dry_run"]:
            print(f"  [DRY RUN] Would initialize memory/system/ under: {result['target']}")
            do = result.get("dry_run_output", {})
            print(f"  Project name: {do.get('project_name', 'N/A')}")
            print(f"  Would create {len(do.get('would_create_dirs', []))} directories")
            print(f"  Would create {len(do.get('would_create_files', []))} files")
        else:
            for path in result.get("created", []):
                print(f"  [CREATE] {path}")
            for path in result.get("skipped", []):
                print(f"  [SKIP]   {path}")
            for err in result.get("errors", []):
                print(f"  [ERROR]  {err}")
            for warning in result.get("warnings", []):
                print(f"  [WARN]   {warning}")
        print("-" * 60)
        status = "SUCCESS" if result["success"] else "FAILED"
        print(f"  Status: {status}")
        print(f"  Init Mode: {result.get('mode', 'create')}")
        if result.get("force_overwrite"):
            print("  Force overwrite: True")
        print("=" * 60)

        if result["success"] and not result["dry_run"]:
            _print_post_init_health_summary(target)

            # Security baseline reminder
            print("\n🔒 安全基线提醒: 运行以下命令部署 CI 安全 workflow:")
            print("  bash scripts/deploy-security-baseline.sh .")
            print("  (或对远程仓库: bash scripts/deploy-security-baseline.sh --repo owner/repo)")

    return 0 if result["success"] else 1


def _print_post_init_health_summary(target: Path) -> None:
    """Print a brief post-init consumer self-check summary.

    Best-effort: any failure is swallowed so it never breaks init.
    """
    try:
        try:
            from .verify_consumer import verify
        except ImportError:
            from memory_core.tools.verify_consumer import verify
        report = verify(target)
        passed = sum(1 for c in report.checks if c.passed)
        total = len(report.checks)
        marker = "OK" if report.all_passed else "ATTENTION"
        print()
        print(f"Post-init consumer self-check: {marker} ({passed}/{total} checks passed)")
        if not report.all_passed:
            print("  Failed checks:")
            for c in report.checks:
                if not c.passed:
                    print(f"    - {c.name}: {c.detail}")
            print(f"  Run 'memory-verify-consumer --path {target}' for full details.")
    except Exception:  # pragma: no cover - never break init
        return


if __name__ == "__main__":
    raise SystemExit(main())
