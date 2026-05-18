#!/usr/bin/env python3
"""M6: Hook Upgrade — Inspect and upgrade Factory memory hook installations.

Subcommands:
    inspect        Scan settings.json and wrapper for old patterns
    plan-upgrade   Generate an upgrade plan based on inspection findings
    apply-upgrade  Backup existing, preserve unrelated hooks, apply upgrades

Usage:
    python -m memory_core.tools.hook_upgrade inspect
    python -m memory_core.tools.hook_upgrade plan-upgrade
    python -m memory_core.tools.hook_upgrade apply-upgrade --yes
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from memory_core.tools.factory_global_hooks import (
    FACTORY_HOOK_EVENTS,
    _backup_existing_file,
    _load_settings_json,
    default_factory_home,
    settings_path,
    wrapper_path,
)

# Patterns that indicate old/detected issues
_OLD_WRAPPER_PATTERNS = [
    (r"\|\|\s*true", "|| true pattern (init failure suppression)"),
    (r"MEMORY_HOOK_FORCE=1", "FORCE noop pattern (bypass guard)"),
    (r"printf\s+'\{\}'", "old empty-JSON noop output"),
]

_MISSING_HOOK_EVENTS = ["PreToolUse"]

# Current wrapper signature markers
_CURRENT_WRAPPER_MARKERS = [
    "# M3: Anti-pollution",
    "READONLY=1",
    "MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE",
]


def _inspect_wrapper(wrapper_file: Path) -> dict[str, Any]:
    """Inspect a wrapper script for known issues."""
    findings: dict[str, Any] = {
        "exists": wrapper_file.exists(),
        "path": str(wrapper_file),
        "issues": [],
        "current_markers_found": [],
    }

    if not wrapper_file.exists():
        findings["issues"].append(
            {"kind": "missing_wrapper", "detail": "Wrapper script not found"}
        )
        return findings

    try:
        content = wrapper_file.read_text(encoding="utf-8")
    except OSError as exc:
        findings["issues"].append(
            {"kind": "unreadable", "detail": f"Cannot read wrapper: {exc}"}
        )
        return findings

    # Check for old patterns
    for pattern, description in _OLD_WRAPPER_PATTERNS:
        if re.search(pattern, content):
            findings["issues"].append(
                {"kind": "old_pattern", "pattern": pattern, "detail": description}
            )

    # Check for current markers
    for marker in _CURRENT_WRAPPER_MARKERS:
        if marker in content:
            findings["current_markers_found"].append(marker)

    # Check if wrapper looks very old (no current markers at all)
    if not findings["current_markers_found"]:
        findings["issues"].append(
            {
                "kind": "old_wrapper",
                "detail": "Wrapper lacks current markers; likely needs regeneration",
            }
        )

    return findings


def _inspect_settings(settings_file: Path) -> dict[str, Any]:
    """Inspect settings.json for hook configuration issues."""
    findings: dict[str, Any] = {
        "exists": settings_file.exists(),
        "path": str(settings_file),
        "issues": [],
        "registered_events": [],
        "missing_events": [],
    }

    if not settings_file.exists():
        findings["issues"].append(
            {"kind": "missing_settings", "detail": "settings.json not found"}
        )
        return findings

    warnings: list[str] = []
    settings = _load_settings_json(settings_file, warnings)
    if warnings:
        findings["issues"].extend(
            {"kind": "settings_parse", "detail": w} for w in warnings
        )

    hooks = settings.get("hooks", {})
    memory_command_markers = (
        "memory_hook_gateway.py",
        "memory-hook-gateway",
        "memory-hook",
    )

    # Check which events are registered with memory hooks
    for event_name, _gateway_event in FACTORY_HOOK_EVENTS:
        event_groups = hooks.get(event_name, [])
        has_memory_hook = False
        if isinstance(event_groups, list):
            for group in event_groups:
                if not isinstance(group, dict):
                    continue
                for hook in group.get("hooks", []):
                    command = hook.get("command", "")
                    if any(marker in command for marker in memory_command_markers):
                        has_memory_hook = True
                        break
        if has_memory_hook:
            findings["registered_events"].append(event_name)

    # Check for missing hook events
    expected_events = [event for event, _ in FACTORY_HOOK_EVENTS]
    for event in expected_events:
        if event not in findings["registered_events"]:
            findings["missing_events"].append(event)

    if findings["missing_events"]:
        for event in findings["missing_events"]:
            findings["issues"].append(
                {
                    "kind": "missing_hook_event",
                    "event": event,
                    "detail": f"Hook event {event} not registered with memory hooks",
                }
            )

    return findings


# ---------------------------------------------------------------------------
# inspect
# ---------------------------------------------------------------------------

def cmd_inspect(
    *,
    factory_home: Path | None = None,
    json_output: bool = False,
) -> dict[str, Any]:
    """Inspect current hook installation for issues."""
    fh = (factory_home or default_factory_home()).expanduser()
    wp = wrapper_path(fh)
    sp = settings_path(fh)

    wrapper_findings = _inspect_wrapper(wp)
    settings_findings = _inspect_settings(sp)

    all_issues = wrapper_findings.get("issues", []) + settings_findings.get("issues", [])

    result: dict[str, Any] = {
        "factory_home": str(fh),
        "wrapper": wrapper_findings,
        "settings": settings_findings,
        "issue_count": len(all_issues),
        "needs_upgrade": len(all_issues) > 0,
    }

    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("Hook Installation Inspection")
        print("=" * 60)

        if not all_issues:
            print("  No issues found ✓")
        else:
            for issue in all_issues:
                kind = issue.get("kind", "unknown")
                detail = issue.get("detail", "")
                print(f"  [{kind.upper()}] {detail}")

        if settings_findings.get("registered_events"):
            print(f"\n  Registered events: {', '.join(settings_findings['registered_events'])}")
        if settings_findings.get("missing_events"):
            print(f"  Missing events: {', '.join(settings_findings['missing_events'])}")

        print("=" * 60)

    return result


# ---------------------------------------------------------------------------
# plan-upgrade
# ---------------------------------------------------------------------------

def cmd_plan_upgrade(
    *,
    factory_home: Path | None = None,
    json_output: bool = False,
) -> dict[str, Any]:
    """Generate an upgrade plan based on inspection findings."""
    fh = (factory_home or default_factory_home()).expanduser()
    wp = wrapper_path(fh)
    sp = settings_path(fh)

    wrapper_findings = _inspect_wrapper(wp)
    settings_findings = _inspect_settings(sp)

    plan: dict[str, Any] = {
        "factory_home": str(fh),
        "actions": [],
        "files_to_backup": [],
        "files_to_modify": [],
    }

    # Plan wrapper actions
    wrapper_issues = wrapper_findings.get("issues", [])
    wrapper_needs_regen = any(
        i.get("kind") in ("old_wrapper", "old_pattern", "missing_wrapper")
        for i in wrapper_issues
    )
    if wrapper_needs_regen:
        plan["actions"].append(
            {"action": "regenerate_wrapper", "path": str(wp), "reason": "Old wrapper detected"}
        )
        if wp.exists():
            plan["files_to_backup"].append(str(wp))
        plan["files_to_modify"].append(str(wp))

    # Plan settings actions
    settings_issues = settings_findings.get("issues", [])
    settings_needs_update = any(
        i.get("kind") in ("missing_hook_event", "missing_settings")
        for i in settings_issues
    )
    if settings_needs_update:
        plan["actions"].append(
            {"action": "update_settings", "path": str(sp), "reason": "Missing hook events"}
        )
        if sp.exists():
            plan["files_to_backup"].append(str(sp))
        plan["files_to_modify"].append(str(sp))

    if json_output:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        print("=" * 60)
        print("Hook Upgrade Plan")
        print("=" * 60)

        if not plan["actions"]:
            print("  No upgrade actions needed ✓")
        else:
            for action in plan["actions"]:
                print(f"  • {action['action']}: {action['path']}")
                print(f"    Reason: {action['reason']}")

            if plan["files_to_backup"]:
                print("\n  Files to backup:")
                for f in plan["files_to_backup"]:
                    print(f"    - {f}")

        print("=" * 60)

    return plan


# ---------------------------------------------------------------------------
# apply-upgrade
# ---------------------------------------------------------------------------

def cmd_apply_upgrade(
    *,
    factory_home: Path | None = None,
    yes: bool = False,
    json_output: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Backup existing files, preserve unrelated hooks, apply upgrades."""
    from memory_core.tools.factory_global_hooks import (
        default_storage_root,
        install_factory_hooks,
    )

    fh = (factory_home or default_factory_home()).expanduser()

    # First, get the plan (suppress text output when json_output)
    plan = cmd_plan_upgrade(factory_home=fh, json_output=json_output)

    result: dict[str, Any] = {
        "factory_home": str(fh),
        "actions_applied": [],
        "backups": [],
        "errors": [],
        "dry_run": dry_run,
    }

    if not plan["actions"]:
        result["message"] = "No upgrade actions needed"
        if json_output:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("No upgrade actions needed ✓")
        return result

    # Require approval
    if not yes and not dry_run:
        try:
            response = input("Apply upgrade? [y/N] ").strip().lower()
            if response not in ("y", "yes"):
                result["message"] = "Aborted by user"
                print("Aborted.")
                return result
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.", file=sys.stderr)
            result["message"] = "Aborted by user"
            return result

    if dry_run:
        result["message"] = "Dry run — no changes applied"
        result["planned_actions"] = plan["actions"]
        if json_output:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Dry run — would apply {len(plan['actions'])} action(s)")
        return result

    # Backup files
    for file_path_str in plan.get("files_to_backup", []):
        file_path = Path(file_path_str)
        if file_path.exists():
            try:
                backup = _backup_existing_file(file_path)
                result["backups"].append(str(backup))
            except Exception as exc:
                result["errors"].append(f"Backup failed for {file_path}: {exc}")
                if json_output:
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                else:
                    print(f"[ERROR] Backup failed: {exc}", file=sys.stderr)
                return result

    # Apply upgrade via install_factory_hooks (preserves unrelated hooks)
    install_result = install_factory_hooks(
        factory_home=fh,
        storage_root=default_storage_root(),
        dry_run=False,
    )

    if install_result.get("success"):
        result["actions_applied"] = plan["actions"]
        result["backups"].extend(install_result.get("backups", []))
        result["message"] = "Upgrade applied successfully"
    else:
        result["errors"].extend(
            f"Install failed: {w}" for w in install_result.get("warnings", [])
        )
        result["message"] = "Upgrade failed"

    if json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["errors"]:
            print("Upgrade completed with errors:", file=sys.stderr)
            for e in result["errors"]:
                print(f"  [ERROR] {e}", file=sys.stderr)
        else:
            print("Upgrade applied successfully ✓")
            if result["backups"]:
                print("  Backups created:")
                for b in result["backups"]:
                    print(f"    - {b}")

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Inspect and upgrade Factory memory hook installations (M6).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # inspect
    inspect_p = sub.add_parser("inspect", help="Inspect hook installation")
    inspect_p.add_argument("--factory-home", type=Path, default=None, help="Factory config directory")
    inspect_p.add_argument("--json", action="store_true", help="Output as JSON")

    # plan-upgrade
    plan_p = sub.add_parser("plan-upgrade", help="Generate upgrade plan")
    plan_p.add_argument("--factory-home", type=Path, default=None, help="Factory config directory")
    plan_p.add_argument("--json", action="store_true", help="Output as JSON")

    # apply-upgrade
    apply_p = sub.add_parser("apply-upgrade", help="Apply hook upgrade")
    apply_p.add_argument("--factory-home", type=Path, default=None, help="Factory config directory")
    apply_p.add_argument("--yes", action="store_true", help="Skip confirmation")
    apply_p.add_argument("--json", action="store_true", help="Output as JSON")
    apply_p.add_argument("--dry-run", action="store_true", help="Preview without changes")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    factory_home = args.factory_home

    if args.command == "inspect":
        result = cmd_inspect(factory_home=factory_home, json_output=args.json)
    elif args.command == "plan-upgrade":
        result = cmd_plan_upgrade(factory_home=factory_home, json_output=args.json)
    elif args.command == "apply-upgrade":
        result = cmd_apply_upgrade(
            factory_home=factory_home,
            yes=args.yes,
            json_output=args.json,
            dry_run=args.dry_run,
        )
    else:
        parser.print_help()
        return 2

    return 0 if not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
