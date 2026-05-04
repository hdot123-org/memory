#!/usr/bin/env python3
"""Migrate a project's .memory/ directory between schema versions.

Usage:
    python migrate_project_memory.py --target /path/to/project --from 0.1.0 --to 0.2.0
    python migrate_project_memory.py --target /path/to/project --from 0.1.0 --to 0.2.0 --dry-run
    python migrate_project_memory.py --target /path/to/project --from 0.1.0 --to 0.2.0 --json

Features:
    - from/to version parameters
    - Migration discovery (auto-discovers applicable migration scripts)
    - migrations.log write rules
    - Rollback/residue output
    - Dry-run mode

Exit codes:
    0 — migration succeeded (or dry-run completed)
    1 — migration failed
    2 — usage error (bad args, missing files, etc.)
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from memory_core.constants import CURRENT_MEMORY_VERSION

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIGRATIONS_LOG_NAME = "migrations.log"
MEMORY_LOCK_NAME = "memory.lock"
ADAPTER_TOML_NAME = "adapter.toml"


def _write_toml_memory_lock(data: dict[str, Any], path: Path) -> None:
    """Write memory section as TOML to path."""
    memory = data.get("memory") or {}
    lines = ["# memory.lock -- project binding to memory-core", ""]
    lines.append("[memory]")
    for key in ("memory_version", "schema_version", "adapter_version", "locked_at", "lock_reason"):
        val = memory.get(key, "")
        lines.append(f'{key} = "{val}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Migration registry
# ---------------------------------------------------------------------------

# Each migration is a function that takes a memory_root Path and returns
# a dict with 'success', 'detail', and optionally 'residue' keys.
# The registry key is "from_version->to_version".

def migrate_v010_to_v020(memory_root: Path) -> dict[str, Any]:
    """Migration: 0.1.0 -> CURRENT_MEMORY_VERSION.

    Handles both legacy JSON and canonical TOML memory.lock formats.
    """
    result: dict[str, Any] = {"success": False, "detail": "", "residue": []}

    lock_path = memory_root / MEMORY_LOCK_NAME
    if not lock_path.is_file():
        result["detail"] = f"{MEMORY_LOCK_NAME} not found"
        return result

    try:
        text = lock_path.read_text(encoding="utf-8")
        # Detect format
        if text.strip().startswith("{"):
            # Legacy JSON -> convert to TOML
            data_json = json.loads(text)
            old_version = data_json.get("version", "unknown")
            lock_data = {
                "memory": {
                    "memory_version": CURRENT_MEMORY_VERSION,
                    "schema_version": data_json.get("schema", "context-package-v1"),
                    "adapter_version": "builtin",
                    "locked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "lock_reason": "upgrade",
                }
            }
        else:
            # Canonical TOML
            lock_data = tomllib.loads(text)
            memory = lock_data.get("memory") or {}
            old_version = memory.get("memory_version", "unknown")
            memory["memory_version"] = CURRENT_MEMORY_VERSION
            memory["locked_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            memory["lock_reason"] = "upgrade"
            lock_data["memory"] = memory
    except Exception as exc:
        result["detail"] = f"Failed to parse {MEMORY_LOCK_NAME}: {exc}"
        return result

    try:
        _write_toml_memory_lock(lock_data, lock_path)
    except Exception as exc:
        result["detail"] = f"Failed to write {MEMORY_LOCK_NAME}: {exc}"
        return result

    # Update adapter.toml version
    adapter_path = memory_root / ADAPTER_TOML_NAME
    if adapter_path.is_file():
        try:
            atext = adapter_path.read_text(encoding="utf-8")
            atext = atext.replace('version = "0.1.0"', f'version = "{CURRENT_MEMORY_VERSION}"')
            adapter_path.write_text(atext, encoding="utf-8")
        except Exception as exc:
            result["residue"].append(f"adapter.toml update failed: {exc}")

    result["success"] = True
    result["detail"] = f"Migrated from {old_version} to {CURRENT_MEMORY_VERSION}"
    return result


# Registry: "from->to" string -> migration function
MIGRATION_REGISTRY: dict[str, Callable[[Path], dict[str, Any]]] = {
    f"0.1.0->{CURRENT_MEMORY_VERSION}": migrate_v010_to_v020,
}


# ---------------------------------------------------------------------------
# Migration discovery
# ---------------------------------------------------------------------------

def discover_migrations(from_version: str, to_version: str) -> list[dict[str, Any]]:
    """Discover applicable migrations between two versions.

    Returns a list of migration descriptors in execution order.
    Supports direct and chained migrations.
    """
    direct_key = f"{from_version}->{to_version}"
    if direct_key in MIGRATION_REGISTRY:
        return [
            {
                "key": direct_key,
                "from": from_version,
                "to": to_version,
                "fn": MIGRATION_REGISTRY[direct_key],
            }
        ]

    # Try to find a chain: from -> intermediate -> to
    # For now, only support single-hop migrations
    available = list(MIGRATION_REGISTRY.keys())
    # Look for a chain through known versions
    for mid_key in available:
        mid_from, mid_to = mid_key.split("->")
        if mid_from == from_version:
            next_key = f"{mid_to}->{to_version}"
            if next_key in MIGRATION_REGISTRY:
                return [
                    {
                        "key": mid_key,
                        "from": mid_from,
                        "to": mid_to,
                        "fn": MIGRATION_REGISTRY[mid_key],
                    },
                    {
                        "key": next_key,
                        "from": mid_to,
                        "to": to_version,
                        "fn": MIGRATION_REGISTRY[next_key],
                    },
                ]

    return []


# ---------------------------------------------------------------------------
# migrations.log writer
# ---------------------------------------------------------------------------

def append_migration_log(
    memory_root: Path,
    from_version: str,
    to_version: str,
    status: str,
    detail: str,
    dry_run: bool = False,
) -> str:
    """Append a record to migrations.log.

    Returns the log line that was (or would be) written.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dry_tag = " [DRY RUN]" if dry_run else ""
    line = f"{now} | {from_version} | {to_version} | {status} | {detail}{dry_tag}"

    if dry_run:
        return line

    log_path = memory_root / MIGRATIONS_LOG_NAME
    if not log_path.is_file():
        log_path.write_text(f"# Migrations Log\n{line}\n", encoding="utf-8")
    else:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    return line


# ---------------------------------------------------------------------------
# Rollback planning
# ---------------------------------------------------------------------------

def plan_rollback(
    from_version: str,
    to_version: str,
    migrations: list[dict[str, Any]],
) -> dict[str, Any]:
    """Plan what would be needed to roll back the migration."""
    rollback_steps: list[str] = []
    for m in reversed(migrations):
        rollback_steps.append(f"Roll back {m['from']} -> {m['to']}")

    return {
        "can_rollback": False,  # Migrations are not auto-reversible by default
        "steps": rollback_steps,
        "warning": "Manual rollback may be required. Review residue before proceeding.",
    }


# ---------------------------------------------------------------------------
# Main migration logic
# ---------------------------------------------------------------------------

def migrate_project_memory(
    target: Path,
    from_version: str,
    to_version: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Execute migration on a project's .memory/ directory.

    Args:
        target: Path to the target project root.
        from_version: Current version of the memory schema.
        to_version: Target version to migrate to.
        dry_run: If True, only report what would be done.

    Returns:
        Dict with migration results.
    """
    result: dict[str, Any] = {
        "success": False,
        "dry_run": dry_run,
        "target": str(target.resolve()),
        "from_version": from_version,
        "to_version": to_version,
        "migrations_executed": [],
        "migrations_skipped": [],
        "log_entries": [],
        "residue": [],
        "rollback": {},
        "errors": [],
    }

    memory_root = target / ".memory"
    if not memory_root.is_dir():
        result["errors"].append(f".memory/ directory not found at {memory_root}")
        return result

    # Verify current version
    lock_path = memory_root / MEMORY_LOCK_NAME
    if lock_path.is_file():
        try:
            text = lock_path.read_text(encoding="utf-8")
            # Support both TOML and legacy JSON
            if text.strip().startswith("{"):
                data = json.loads(text)
                current = data.get("version", "unknown")
            else:
                data = tomllib.loads(text)
                current = data.get("memory", {}).get("memory_version", "unknown")
            if current != from_version:
                result["errors"].append(
                    f"Version mismatch: memory.lock says {current!r}, "
                    f"but --from is {from_version!r}"
                )
                return result
        except Exception as exc:
            result["errors"].append(f"Failed to read {MEMORY_LOCK_NAME}: {exc}")
            return result

    # Discover migrations
    migrations = discover_migrations(from_version, to_version)
    if not migrations:
        result["errors"].append(
            f"No migration path found from {from_version} to {to_version}. "
            f"Available: {list(MIGRATION_REGISTRY.keys())}"
        )
        return result

    # Execute migrations
    all_success = True
    for mig in migrations:
        mig_desc = f"{mig['from']}->{mig['to']}"

        if dry_run:
            result["migrations_executed"].append(
                {"key": mig_desc, "status": "would_execute"}
            )
            log_entry = append_migration_log(
                memory_root, mig["from"], mig["to"], "pending (dry-run)",
                f"Would migrate {mig['from']} to {mig['to']}",
                dry_run=True,
            )
            result["log_entries"].append(log_entry)
            continue

        # Execute
        mig_result = mig["fn"](memory_root)
        status = "success" if mig_result["success"] else "failed"
        log_entry = append_migration_log(
            memory_root, mig["from"], mig["to"], status,
            mig_result.get("detail", ""),
            dry_run=False,
        )
        result["log_entries"].append(log_entry)
        result["migrations_executed"].append(
            {
                "key": mig_desc,
                "status": status,
                "detail": mig_result.get("detail", ""),
            }
        )

        if mig_result.get("residue"):
            result["residue"].extend(mig_result["residue"])

        if not mig_result["success"]:
            all_success = False
            result["errors"].append(
                f"Migration {mig_desc} failed: {mig_result.get('detail', 'unknown')}"
            )
            break  # Stop on first failure

    # Rollback plan
    result["rollback"] = plan_rollback(from_version, to_version, migrations)

    result["success"] = all_success
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate a project's .memory/ directory between schema versions."
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Path to the target project root.",
    )
    parser.add_argument(
        "--from",
        dest="from_version",
        required=True,
        help="Current version of the memory schema.",
    )
    parser.add_argument(
        "--to",
        dest="to_version",
        required=True,
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
    try:
        _pkg_version = importlib.metadata.version("memory-core")
    except importlib.metadata.PackageNotFoundError:
        _pkg_version = "unknown"
    parser.add_argument("--version", action="version", version=f"%(prog)s {_pkg_version}")
    args = parser.parse_args()

    target = args.target.resolve()
    if not target.is_dir():
        print(f"Error: target path does not exist: {target}", file=sys.stderr)
        return 2

    result = migrate_project_memory(
        target,
        args.from_version,
        args.to_version,
        dry_run=args.dry_run,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
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

    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
