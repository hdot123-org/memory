#!/usr/bin/env python3
"""M6: Ownership CLI — Manage project ownership configuration.

Subcommands:
    show          Display current ownership.toml in human-readable format
    validate      Validate ownership schema (weakening checks)
    plan-update   Generate a migration plan without writing files
    apply-update  Execute migration plan (requires --yes flag for non-interactive)

Usage:
    python -m memory_core.tools.ownership_cli show --project-root /path
    python -m memory_core.tools.ownership_cli validate --project-root /path
    python -m memory_core.tools.ownership_cli plan-update --project-root /path
    python -m memory_core.tools.ownership_cli apply-update --project-root /path --yes
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION, OWNERSHIP_SCHEMA_VERSION, SYSTEM_DIR, VALID_SOURCE_REPO_MODES
from memory_core.ownership import (
    DEFAULT_OWNERSHIP_DOMAINS,
    DEFAULT_OWNERSHIP_RESOURCES,
    MemoryOwnership,
    OwnershipResource,
    ProtectionLevel,
    get_source_repo_mode,
    is_memory_core_source_repo,
    load_memory_ownership,
    validate_ownership_schema,
)


def _ownership_file_path(project_root: Path) -> Path:
    """Return the expected ownership.toml path."""
    return project_root / SYSTEM_DIR / "ownership.toml"


def _format_protection_level(level: ProtectionLevel) -> str:
    """Format a protection level for human-readable output."""
    labels = {
        ProtectionLevel.CRITICAL: "🔴 CRITICAL",
        ProtectionLevel.STANDARD: "🟡 STANDARD",
        ProtectionLevel.RECOMMENDED: "🟢 RECOMMENDED",
    }
    return labels.get(level, level.name)


def _render_ownership(ownership: MemoryOwnership) -> str:
    """Render ownership configuration as human-readable text."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("Ownership Configuration")
    lines.append("=" * 60)
    lines.append(f"  Schema version : {ownership.schema_version}")
    lines.append(f"  Memory version : {ownership.memory_version or '(none)'}")
    lines.append("")

    if ownership.domains:
        lines.append("Domains:")
        for d in ownership.domains:
            rec = "recursive" if d.recursive else "non-recursive"
            lines.append(f"  • {d.name}")
            lines.append(f"      Path  : {d.path}")
            lines.append(f"      Level : {_format_protection_level(d.level)}")
            lines.append(f"      Mode  : {rec}")
            if d.description:
                lines.append(f"      Desc  : {d.description}")
        lines.append("")

    if ownership.resources:
        lines.append("Resources:")
        for r in ownership.resources:
            lines.append(f"  • {r.name}")
            lines.append(f"      Path  : {r.path}")
            lines.append(f"      Level : {_format_protection_level(r.level)}")
            if r.domain:
                lines.append(f"      Domain: {r.domain}")
            if r.description:
                lines.append(f"      Desc  : {r.description}")
        lines.append("")

    if ownership.policy:
        lines.append("Policy:")
        for key, val in ownership.policy.items():
            lines.append(f"  {key}: {val}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

def cmd_show(project_root: Path, *, json_output: bool = False) -> int:
    """Display current ownership configuration."""
    ownership_path = _ownership_file_path(project_root)
    ownership = load_memory_ownership(project_root)

    if json_output:
        data = ownership.to_dict()
        data["_source_file"] = str(ownership_path)
        data["_source_exists"] = ownership_path.exists()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        if not ownership_path.exists():
            print(
                f"[ownership] No ownership.toml found at {ownership_path}; showing defaults.",
                file=sys.stderr,
            )
        print(_render_ownership(ownership))

    return 0


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

def cmd_validate(project_root: Path, *, json_output: bool = False) -> int:
    """Validate ownership schema for weakening and file existence."""
    ownership_path = _ownership_file_path(project_root)
    errors: list[str] = []
    warnings: list[str] = []

    # Check file exists
    if not ownership_path.exists():
        warnings.append(
            f"ownership.toml not found at {ownership_path}; using defaults"
        )

    ownership = load_memory_ownership(project_root)

    # Run schema validation
    schema_errors = validate_ownership_schema(ownership)
    errors.extend(schema_errors)

    # Check schema version
    if ownership.schema_version != OWNERSHIP_SCHEMA_VERSION:
        warnings.append(
            f"Schema version mismatch: expected {OWNERSHIP_SCHEMA_VERSION}, "
            f"got {ownership.schema_version}"
        )

    if json_output:
        result = {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "ownership_file": str(ownership_path),
            "ownership_file_exists": ownership_path.exists(),
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if warnings:
            for w in warnings:
                print(f"[WARNING] {w}", file=sys.stderr)
        if errors:
            for e in errors:
                print(f"[ERROR] {e}", file=sys.stderr)
            print(f"\nValidation failed with {len(errors)} error(s).")
        else:
            print("Ownership validation passed ✓")

    return 1 if errors else 0


# ---------------------------------------------------------------------------
# plan-update
# ---------------------------------------------------------------------------

def _build_default_ownership() -> MemoryOwnership:
    """Build a fresh default ownership configuration."""
    return MemoryOwnership(
        schema_version=OWNERSHIP_SCHEMA_VERSION,
        memory_version=CURRENT_MEMORY_VERSION,
        domains=list(DEFAULT_OWNERSHIP_DOMAINS),
        resources=list(DEFAULT_OWNERSHIP_RESOURCES),
        policy={},
    )


def _diff_ownership(
    current: MemoryOwnership, proposed: MemoryOwnership
) -> dict[str, Any]:
    """Compute diff between current and proposed ownership."""
    plan: dict[str, Any] = {
        "has_changes": False,
        "domains_added": [],
        "domains_removed": [],
        "domains_modified": [],
        "resources_added": [],
        "resources_removed": [],
        "resources_modified": [],
        "schema_version_change": None,
    }

    # Schema version change
    if current.schema_version != proposed.schema_version:
        plan["schema_version_change"] = {
            "from": current.schema_version,
            "to": proposed.schema_version,
        }
        plan["has_changes"] = True

    # Domain diff
    current_domains = {d.name: d for d in current.domains}
    proposed_domains = {d.name: d for d in proposed.domains}

    for name in set(current_domains) - set(proposed_domains):
        plan["domains_removed"].append(
            {"name": name, "path": current_domains[name].path}
        )
        plan["has_changes"] = True

    for name in set(proposed_domains) - set(current_domains):
        plan["domains_added"].append(
            {"name": name, "path": proposed_domains[name].path}
        )
        plan["has_changes"] = True

    for name in set(current_domains) & set(proposed_domains):
        c = current_domains[name]
        p = proposed_domains[name]
        changes: dict[str, Any] = {}
        if c.path != p.path:
            changes["path"] = {"from": c.path, "to": p.path}
        if c.level != p.level:
            changes["level"] = {
                "from": c.level.name,
                "to": p.level.name,
            }
        if c.recursive != p.recursive:
            changes["recursive"] = {"from": c.recursive, "to": p.recursive}
        if changes:
            plan["domains_modified"].append({"name": name, **changes})
            plan["has_changes"] = True

    # Resource diff
    current_resources: dict[str, OwnershipResource] = {r.name: r for r in current.resources}
    proposed_resources: dict[str, OwnershipResource] = {r.name: r for r in proposed.resources}

    for name in set(current_resources) - set(proposed_resources):
        plan["resources_removed"].append(
            {"name": name, "path": current_resources[name].path}
        )
        plan["has_changes"] = True

    for name in set(proposed_resources) - set(current_resources):
        plan["resources_added"].append(
            {"name": name, "path": proposed_resources[name].path}
        )
        plan["has_changes"] = True

    for name in set(current_resources) & set(proposed_resources):
        c_res: OwnershipResource = current_resources[name]
        p_res: OwnershipResource = proposed_resources[name]
        changes_res: dict[str, Any] = {}
        if c_res.path != p_res.path:
            changes_res["path"] = {"from": c_res.path, "to": p_res.path}
        if c_res.level != p_res.level:
            changes_res["level"] = {
                "from": c_res.level.name,
                "to": p_res.level.name,
            }
        if c_res.domain != p_res.domain:
            changes_res["domain"] = {"from": c_res.domain, "to": p_res.domain}
        if changes_res:
            plan["resources_modified"].append({"name": name, **changes_res})
            plan["has_changes"] = True

    return plan


def cmd_plan_update(
    project_root: Path,
    *,
    json_output: bool = False,
    use_defaults: bool = False,
) -> int:
    """Generate migration plan between current and proposed ownership."""
    current = load_memory_ownership(project_root)

    if use_defaults:
        proposed = _build_default_ownership()
    else:
        # Without explicit proposed config, plan is defaults vs current
        proposed = _build_default_ownership()

    plan = _diff_ownership(current, proposed)

    if json_output:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        if not plan["has_changes"]:
            print("No changes needed — current ownership matches proposed.")
            return 0

        print("=" * 60)
        print("Ownership Migration Plan")
        print("=" * 60)

        if plan["schema_version_change"]:
            sc = plan["schema_version_change"]
            print(f"\n  Schema version: {sc['from']} → {sc['to']}")

        for label, items in [
            ("Domains to add", plan["domains_added"]),
            ("Domains to remove", plan["domains_removed"]),
            ("Domains to modify", plan["domains_modified"]),
            ("Resources to add", plan["resources_added"]),
            ("Resources to remove", plan["resources_removed"]),
            ("Resources to modify", plan["resources_modified"]),
        ]:
            if items:
                print(f"\n  {label}:")
                for item in items:
                    name = item.get("name", "?")
                    path = item.get("path", "")
                    print(f"    • {name} ({path})")
                    for k, v in item.items():
                        if k in ("name", "path"):
                            continue
                        print(f"        {k}: {v}")

        print("\n" + "=" * 60)
        print("Run 'apply-update --yes' to execute this plan.")

    return 0


# ---------------------------------------------------------------------------
# apply-update
# ---------------------------------------------------------------------------

def _write_ownership_toml(project_root: Path, ownership: MemoryOwnership) -> Path:
    """Write ownership configuration as TOML to memory/system/ownership.toml."""
    import json as _json

    ownership_path = _ownership_file_path(project_root)
    ownership_path.parent.mkdir(parents=True, exist_ok=True)

    # Build TOML manually to avoid requiring a TOML writer
    lines: list[str] = []
    lines.append("# ownership.toml — memory-core ownership configuration")
    lines.append(f'schema_version = "{ownership.schema_version}"')
    lines.append(f'memory_version = "{ownership.memory_version}"')
    lines.append("")

    if ownership.domains:
        lines.append("# Domains")
        for d in ownership.domains:
            lines.append("[[domains]]")
            lines.append(f'name = "{d.name}"')
            lines.append(f'path = "{d.path}"')
            lines.append(f'level = "{d.level.name.lower()}"')
            lines.append(f"recursive = {'true' if d.recursive else 'false'}")
            lines.append(f'description = "{d.description}"')
            lines.append("")

    if ownership.resources:
        lines.append("# Resources")
        for r in ownership.resources:
            lines.append("[[resources]]")
            lines.append(f'name = "{r.name}"')
            lines.append(f'path = "{r.path}"')
            lines.append(f'level = "{r.level.name.lower()}"')
            if r.domain:
                lines.append(f'domain = "{r.domain}"')
            else:
                lines.append('domain = ""')
            lines.append(f'description = "{r.description}"')
            lines.append("")

    if ownership.policy:
        lines.append("[policy]")
        for k, v in ownership.policy.items():
            lines.append(f'{k} = {_json.dumps(v)}')
        lines.append("")

    ownership_path.write_text("\n".join(lines), encoding="utf-8")
    return ownership_path


def cmd_apply_update(
    project_root: Path,
    *,
    yes: bool = False,
    json_output: bool = False,
    use_defaults: bool = False,
) -> int:
    """Execute ownership migration plan with approval."""
    current = load_memory_ownership(project_root)

    if use_defaults:
        proposed = _build_default_ownership()
    else:
        proposed = _build_default_ownership()

    plan = _diff_ownership(current, proposed)

    if not plan["has_changes"]:
        # Even if the plan shows no changes, write the file if it doesn't exist
        ownership_path = _ownership_file_path(project_root)
        if not ownership_path.exists():
            ownership_path = _write_ownership_toml(project_root, proposed)
            if json_output:
                print(
                    json.dumps(
                        {
                            "applied": True,
                            "ownership_file": str(ownership_path),
                            "plan_summary": {
                                "domains_added": 0,
                                "domains_removed": 0,
                                "domains_modified": 0,
                                "resources_added": 0,
                                "resources_removed": 0,
                                "resources_modified": 0,
                            },
                        },
                        indent=2,
                    )
                )
            else:
                print(f"Ownership created: {ownership_path}")
            return 0

        if json_output:
            print(json.dumps({"applied": False, "reason": "no_changes"}))
        else:
            print("No changes to apply.")
        return 0

    # Validate the proposed config before applying
    validation_errors = validate_ownership_schema(proposed)
    if validation_errors:
        if json_output:
            print(
                json.dumps(
                    {
                        "applied": False,
                        "reason": "validation_failed",
                        "errors": validation_errors,
                    },
                    indent=2,
                )
            )
        else:
            print("Proposed ownership fails validation:", file=sys.stderr)
            for e in validation_errors:
                print(f"  [ERROR] {e}", file=sys.stderr)
        return 1

    # Require approval
    if not yes:
        if not json_output:
            print("Planned changes:")
            # Show a brief summary
            for label, items in [
                ("Add", plan["domains_added"] + plan["resources_added"]),
                ("Remove", plan["domains_removed"] + plan["resources_removed"]),
                ("Modify", plan["domains_modified"] + plan["resources_modified"]),
            ]:
                if items:
                    names = [i.get("name", "?") for i in items]
                    print(f"  {label}: {', '.join(names)}")
            print()
        try:
            response = input("Apply these changes? [y/N] ").strip().lower()
            if response not in ("y", "yes"):
                print("Aborted.")
                return 0
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.", file=sys.stderr)
            return 0

    # Apply
    ownership_path = _write_ownership_toml(project_root, proposed)

    if json_output:
        print(
            json.dumps(
                {
                    "applied": True,
                    "ownership_file": str(ownership_path),
                    "plan_summary": {
                        "domains_added": len(plan["domains_added"]),
                        "domains_removed": len(plan["domains_removed"]),
                        "domains_modified": len(plan["domains_modified"]),
                        "resources_added": len(plan["resources_added"]),
                        "resources_removed": len(plan["resources_removed"]),
                        "resources_modified": len(plan["resources_modified"]),
                    },
                },
                indent=2,
            )
        )
    else:
        print(f"Ownership updated: {ownership_path}")

    return 0


# ---------------------------------------------------------------------------
# source-repo-mode subcommand
# ---------------------------------------------------------------------------

def _write_source_repo_mode(project_root: Path, mode: str) -> int:
    """Write source_repo mode to ownership.toml.

    Creates memory/system/ directory and ownership.toml if needed.
    Preserves existing domains and resources, updates policy.source_repo section.
    """
    memory_dir = project_root / SYSTEM_DIR
    memory_dir.mkdir(parents=True, exist_ok=True)

    ownership_file = memory_dir / "ownership.toml"
    ownership = load_memory_ownership(project_root)

    from datetime import datetime, timezone

    source_repo_section = {
        "mode": mode,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "activated_by": "cli",
    }

    # Build TOML manually (no tomli_w available)
    lines: list[str] = []
    lines.append(f'schema_version = "{ownership.schema_version}"')
    lines.append(f'memory_version = "{ownership.memory_version or CURRENT_MEMORY_VERSION}"')
    lines.append("")

    # Domains — each gets its own [[domains]] header
    for d in ownership.domains:
        lines.append("[[domains]]")
        lines.append(f'name = "{d.name}"')
        lines.append(f'path = "{d.path}"')
        lines.append(f'level = "{d.level.name.lower()}"')
        lines.append(f'recursive = {str(d.recursive).lower()}')
        lines.append(f'description = "{d.description}"')
        lines.append("")

    # Resources — each gets its own [[resources]] header
    for r in ownership.resources:
        lines.append("[[resources]]")
        lines.append(f'name = "{r.name}"')
        lines.append(f'path = "{r.path}"')
        lines.append(f'level = "{r.level.name.lower()}"')
        lines.append(f'domain = "{r.domain or ""}"')
        lines.append(f'description = "{r.description}"')
        lines.append("")

    # Policy — preserve existing non-source_repo keys
    lines.append("[policy]")
    for key, val in ownership.policy.items():
        if key == "source_repo":
            continue
        if isinstance(val, str):
            lines.append(f'{key} = "{val}"')
        elif isinstance(val, bool):
            lines.append(f'{key} = {str(val).lower()}')
        elif isinstance(val, (int, float)):
            lines.append(f'{key} = {val}')

    # Source repo policy section
    lines.append("")
    lines.append("[policy.source_repo]")
    lines.append(f'mode = "{source_repo_section["mode"]}"')
    lines.append(f'activated_at = "{source_repo_section["activated_at"]}"')
    lines.append(f'activated_by = "{source_repo_section["activated_by"]}"')
    lines.append("")

    ownership_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def cmd_source_repo_mode(project_root: Path, mode: str | None = None, json_output: bool = False) -> int:
    """Manage source repo operating mode.

    With no mode argument: display current mode.
    With mode argument: switch to specified mode.
    """
    if not is_memory_core_source_repo(project_root):
        msg = "Not a memory-core source repository"
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        return 1

    current_mode = get_source_repo_mode(project_root)

    if mode is None:
        # Status query
        if json_output:
            print(json.dumps({"source_repo_mode": current_mode}))
        else:
            print(f"Source repo mode: {current_mode}")
        return 0

    if mode not in VALID_SOURCE_REPO_MODES:
        msg = f"Invalid mode '{mode}'. Valid modes: {', '.join(VALID_SOURCE_REPO_MODES)}"
        if json_output:
            print(json.dumps({"error": msg}))
        else:
            print(f"Error: {msg}", file=sys.stderr)
        return 1

    if mode == current_mode:
        if json_output:
            print(json.dumps({"source_repo_mode": mode, "changed": False}))
        else:
            print(f"Already in {mode} mode")
        return 0

    rc = _write_source_repo_mode(project_root, mode)
    if rc != 0:
        return rc

    if json_output:
        print(json.dumps({"source_repo_mode": mode, "changed": True}))
    else:
        print(f"Source repo mode changed: {current_mode} -> {mode}")
        if mode == "develop":
            print("  Agent can now modify code files. Critical domains remain protected.")
        else:
            print("  Agent can no longer modify any files in this repository.")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Manage project ownership configuration (M6).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # show
    show_p = sub.add_parser("show", help="Display current ownership configuration")
    show_p.add_argument("--project-root", type=Path, required=True, help="Path to project root")
    show_p.add_argument("--json", action="store_true", help="Output as JSON")

    # validate
    val_p = sub.add_parser("validate", help="Validate ownership schema")
    val_p.add_argument("--project-root", type=Path, required=True, help="Path to project root")
    val_p.add_argument("--json", action="store_true", help="Output as JSON")

    # plan-update
    plan_p = sub.add_parser(
        "plan-update", help="Generate ownership migration plan"
    )
    plan_p.add_argument("--project-root", type=Path, required=True, help="Path to project root")
    plan_p.add_argument("--json", action="store_true", help="Output as JSON")
    plan_p.add_argument(
        "--use-defaults",
        action="store_true",
        help="Compare against default ownership",
    )

    # apply-update
    apply_p = sub.add_parser(
        "apply-update", help="Execute ownership migration"
    )
    apply_p.add_argument("--project-root", type=Path, required=True, help="Path to project root")
    apply_p.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    apply_p.add_argument("--json", action="store_true", help="Output as JSON")
    apply_p.add_argument(
        "--use-defaults",
        action="store_true",
        help="Apply default ownership",
    )

    # source-repo-mode
    srm_p = sub.add_parser(
        "source-repo-mode",
        help="Manage source repo operating mode (readonly/develop)",
    )
    srm_p.add_argument("--project-root", type=Path, required=True, help="Path to project root")
    srm_p.add_argument("mode", nargs="?", choices=list(VALID_SOURCE_REPO_MODES),
                       help="Mode to switch to (omit to show current mode)")
    srm_p.add_argument("--json", action="store_true", help="Output as JSON")

    # dev — alias for source-repo-mode develop
    dev_p = sub.add_parser("dev", help="Switch to develop mode (alias)")
    dev_p.add_argument("--project-root", type=Path, required=True, help="Path to project root")

    # prod — alias for source-repo-mode readonly
    prod_p = sub.add_parser("prod", help="Switch to readonly mode (alias)")
    prod_p.add_argument("--project-root", type=Path, required=True, help="Path to project root")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(f"Error: project root does not exist: {project_root}", file=sys.stderr)
        return 2

    if args.command == "show":
        return cmd_show(project_root, json_output=args.json)
    elif args.command == "validate":
        return cmd_validate(project_root, json_output=args.json)
    elif args.command == "plan-update":
        return cmd_plan_update(
            project_root, json_output=args.json, use_defaults=args.use_defaults
        )
    elif args.command == "apply-update":
        return cmd_apply_update(
            project_root,
            yes=args.yes,
            json_output=args.json,
            use_defaults=args.use_defaults,
        )
    elif args.command == "source-repo-mode":
        return cmd_source_repo_mode(
            project_root, mode=args.mode, json_output=args.json
        )
    elif args.command == "dev":
        return cmd_source_repo_mode(
            project_root, mode="develop", json_output=False
        )
    elif args.command == "prod":
        return cmd_source_repo_mode(
            project_root, mode="readonly", json_output=False
        )
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
