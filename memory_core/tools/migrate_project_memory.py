#!/usr/bin/env python3
"""Migrate a project's .memory/ directory between schema versions.

Usage:
    python migrate_project_memory.py --target /path/to/project --from 0.1.0 --to 0.2.0
    python migrate_project_memory.py --target /path/to/project --from 0.1.0 --to 0.2.0 --dry-run
    python migrate_project_memory.py --target /path/to/project --from 0.1.0 --to 0.2.0 --json

Features:
    - from/to version parameters
    - Idempotent: already at target → noop
    - Downgrade explicit reject
    - Pre-migration backup
    - migrations.log atomic append (fcntl on POSIX)
    - Soft rollback (plan + execute)
    - Auto-rollback on failure
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
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

from memory_core.constants import (
    _BACKUP_FAILED,
    CURRENT_MEMORY_VERSION,
)
from memory_core.tools.adapter_toml_schema import (
    _apply_migration_transforms,
    dump_adapter_toml,
    load_adapter_toml,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIGRATIONS_LOG_NAME = "migrations.log"
MEMORY_LOCK_NAME = "memory.lock"
ADAPTER_TOML_NAME = "adapter.toml"
BACKUPS_DIR_NAME = "backups"
BACKUP_MANIFEST_NAME = "BACKUP_MANIFEST.json"

# Local downgrade-reject constants (not in constants.py to avoid coupling)
_DOWNGRADE_NOT_SUPPORTED = "downgrade_not_supported"
_CURRENT_NEWER_THAN_TARGET = "current_newer_than_target"


def _parse_version_tuple(ver: str) -> tuple[int, ...]:
    """Parse a version string like '0.1.0' into a comparable tuple."""
    return tuple(map(int, ver.split(".")))


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
        if text.strip().startswith("{"):
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

    adapter_path = memory_root / ADAPTER_TOML_NAME
    if adapter_path.is_file():
        try:
            # Structured: load -> transform -> dump
            raw_data: dict[str, Any] = tomllib.loads(
                adapter_path.read_text(encoding="utf-8")
            )
            transformed = _apply_migration_transforms(
                raw_data, "0.1.0", CURRENT_MEMORY_VERSION,
            )
            # Write transformed dict as temp TOML, load as AdapterConfig, dump canonical
            _tmp_path = adapter_path.parent / ".adapter.toml.migrating"
            _lines: list[str] = ["# adapter.toml (migrated)", ""]
            for _section, _sdata in transformed.items():
                if isinstance(_sdata, dict):
                    _lines.append(f"[{_section}]")
                    for _k, _v in _sdata.items():
                        if isinstance(_v, list):
                            _vals = ", ".join(f'"{x}"' for x in _v)
                            _lines.append(f"{_k} = [{_vals}]")
                        elif isinstance(_v, bool):
                            _lines.append(f"{_k} = {'true' if _v else 'false'}")
                        else:
                            _lines.append(f'{_k} = "{_v}"')
                    _lines.append("")
            _tmp_path.write_text("\n".join(_lines), encoding="utf-8")
            _config = load_adapter_toml(_tmp_path)
            _config.adapter_version = CURRENT_MEMORY_VERSION
            adapter_path.write_text(dump_adapter_toml(_config), encoding="utf-8")
            _tmp_path.unlink(missing_ok=True)
        except Exception as exc:
            result["residue"].append(f"adapter.toml update failed: {exc}")

    result["success"] = True
    result["detail"] = f"Migrated from {old_version} to {CURRENT_MEMORY_VERSION}"
    return result


MIGRATION_REGISTRY: dict[str, Callable[[Path], dict[str, Any]]] = {
    f"0.1.0->{CURRENT_MEMORY_VERSION}": migrate_v010_to_v020,
}


# ---------------------------------------------------------------------------
# Migration discovery
# ---------------------------------------------------------------------------

def discover_migrations(from_version: str, to_version: str) -> list[dict[str, Any]]:
    """Discover applicable migrations between two versions."""
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

    available = list(MIGRATION_REGISTRY.keys())
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
# _append_migrations_log helper — atomic with fcntl on POSIX
# ---------------------------------------------------------------------------

def _append_migrations_log(log_path: Path, line: str) -> None:
    """Append a single line to migrations.log with file locking.

    POSIX: uses fcntl.LOCK_EX + fsync.
    Windows: falls back to plain open("a").
    """
    with open(log_path, "a", encoding="utf-8") as f:
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except (OSError, AttributeError, ModuleNotFoundError):
            # Windows or non-POSIX: skip locking, just write
            f.write(line + "\n")
            return
        try:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        finally:
            try:
                import fcntl
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except (OSError, AttributeError):
                pass


# ---------------------------------------------------------------------------
# migrations.log public writer
# ---------------------------------------------------------------------------

def append_migration_log(
    memory_root: Path,
    from_version: str,
    to_version: str,
    status: str,
    detail: str,
    dry_run: bool = False,
) -> str:
    """Append a record to migrations.log. Returns the log line."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dry_tag = " [DRY RUN]" if dry_run else ""
    line = f"{now} | {from_version} | {to_version} | {status} | {detail}{dry_tag}"

    if dry_run:
        return line

    log_path = memory_root / MIGRATIONS_LOG_NAME
    if not log_path.is_file():
        log_path.write_text(f"# Migrations Log\n{line}\n", encoding="utf-8")
    else:
        _append_migrations_log(log_path, line)

    return line


# ---------------------------------------------------------------------------
# Backup helpers
# ---------------------------------------------------------------------------

def _create_backup(memory_root: Path, from_version: str, to_version: str) -> Path:
    """Copy .memory/ (excluding backups/) to .memory/backups/<utc_iso8601_compact>/.

    Returns the backup directory path.
    """
    backups_dir = memory_root / BACKUPS_DIR_NAME
    backups_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dest = backups_dir / ts

    def _ignore_backups(dirpath: str, names: list[str]) -> list[str]:
        """Exclude the backups/ subdirectory from copy."""
        if Path(dirpath) == memory_root:
            return [BACKUPS_DIR_NAME]
        return []

    shutil.copytree(str(memory_root), str(backup_dest), ignore=_ignore_backups)

    # Count source files (excluding backups/)
    source_files_count = sum(
        1 for p in memory_root.rglob("*")
        if p.is_file() and BACKUPS_DIR_NAME not in p.parts[-2:] and p.parent != backups_dir
    )
    # Recount properly: files directly under memory_root but not under backups/
    source_files_count = 0
    for p in memory_root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(memory_root)
            if rel.parts[0] != BACKUPS_DIR_NAME:
                source_files_count += 1

    manifest = {
        "from_version": from_version,
        "to_version": to_version,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_files_count": source_files_count,
    }
    manifest_path = backup_dest / BACKUP_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return backup_dest


# ---------------------------------------------------------------------------
# Rollback planning — reads backups directory
# ---------------------------------------------------------------------------

def plan_rollback(memory_root: Path) -> dict[str, Any]:
    """Check if a rollback is possible by looking at backups/.

    Returns the latest backup metadata or can_rollback=False.
    """
    backups_dir = memory_root / BACKUPS_DIR_NAME
    if not backups_dir.is_dir():
        return {"can_rollback": False, "reason": "no backup found"}

    # Find backup dirs that have BACKUP_MANIFEST.json
    backup_dirs = []
    for d in backups_dir.iterdir():
        if d.is_dir() and (d / BACKUP_MANIFEST_NAME).is_file():
            backup_dirs.append(d)

    if not backup_dirs:
        return {"can_rollback": False, "reason": "no backup found"}

    # Pick the latest by name (timestamp-based)
    latest = max(backup_dirs, key=lambda d: d.name)
    manifest = json.loads(
        (latest / BACKUP_MANIFEST_NAME).read_text(encoding="utf-8")
    )

    return {
        "can_rollback": True,
        "backup_dir": str(latest),
        "from_version": manifest["from_version"],
        "to_version": manifest["to_version"],
        "ts": manifest["timestamp"],
    }


# ---------------------------------------------------------------------------
# execute_rollback — restore from backup
# ---------------------------------------------------------------------------

def execute_rollback(memory_root: Path, *, backup_dir: Path | None = None) -> dict[str, Any]:
    """Restore .memory/ from the latest backup (or specified backup_dir).

    Deletes current .memory/ contents (except backups/), copies backup in.
    Writes a status=rolled_back entry to migrations.log.
    """
    # Resolve backup_dir
    if backup_dir is not None:
        bd = Path(backup_dir)
    else:
        plan = plan_rollback(memory_root)
        if not plan["can_rollback"]:
            return {"success": False, "error": "no backup found"}
        bd = Path(plan["backup_dir"])

    if not bd.is_dir():
        return {"success": False, "error": f"backup dir not found: {bd}"}

    # Delete current .memory/ contents except backups/
    for item in memory_root.iterdir():
        if item.name == BACKUPS_DIR_NAME:
            continue
        if item.is_dir():
            shutil.rmtree(str(item))
        else:
            item.unlink()

    # Copy backup contents back
    for item in bd.iterdir():
        if item.name == BACKUP_MANIFEST_NAME:
            continue
        dest = memory_root / item.name
        if item.is_dir():
            shutil.copytree(str(item), str(dest))
        else:
            shutil.copy2(str(item), str(dest))

    # Write rolled_back log entry
    log_path = memory_root / MIGRATIONS_LOG_NAME
    if log_path.is_file():
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = f"{now} | {bd.name} | rollback | rolled_back | Restored from backup {bd.name}"
        _append_migrations_log(log_path, line)

    return {"success": True, "restored_from": str(bd)}


# ---------------------------------------------------------------------------
# _read_current_version helper
# ---------------------------------------------------------------------------

def _read_current_version(memory_root: Path) -> str | None:
    """Read the memory_version from memory.lock. Returns None on failure."""
    lock_path = memory_root / MEMORY_LOCK_NAME
    if not lock_path.is_file():
        return None
    try:
        text = lock_path.read_text(encoding="utf-8")
        if text.strip().startswith("{"):
            data = json.loads(text)
            return data.get("version")
        else:
            data = tomllib.loads(text)
            return data.get("memory", {}).get("memory_version")
    except Exception:
        return None


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
    """Execute migration on a project's .memory/ directory."""
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

    try:
        to_tuple = _parse_version_tuple(to_version)
        from_tuple = _parse_version_tuple(from_version)
    except (ValueError, AttributeError) as exc:
        result["errors"].append(
            f"Invalid version format for migration: from={from_version!r} "
            f"to={to_version!r} ({exc}); expected SemVer-like 'MAJOR.MINOR.PATCH'"
        )
        result["error"] = "invalid_version_format"
        return result

    current_version = _read_current_version(memory_root)
    if current_version is not None:
        try:
            current_tuple = _parse_version_tuple(current_version)
        except (ValueError, AttributeError):
            current_tuple = None
    else:
        current_tuple = None

    # ---- A. Idempotency: current == to → noop ----
    if current_tuple is not None and current_tuple == to_tuple:
        result["success"] = True
        result["noop"] = True
        result["reason"] = "already at target version"
        return result

    # ---- B. Downgrade explicit reject ----
    if to_tuple < from_tuple:
        result["success"] = False
        result["error"] = _DOWNGRADE_NOT_SUPPORTED
        result["message"] = f"Downgrade not supported: from={from_version} to={to_version}"
        result["errors"].append(result["message"])
        return result

    if current_tuple is not None and current_tuple > to_tuple:
        result["success"] = False
        result["error"] = _CURRENT_NEWER_THAN_TARGET
        result["message"] = (
            f"Current version ({current_version}) is newer than target ({to_version})"
        )
        result["errors"].append(result["message"])
        return result

    # ---- Discover migrations ----
    migrations = discover_migrations(from_version, to_version)
    if not migrations:
        result["errors"].append(
            f"No migration path found from {from_version} to {to_version}. "
            f"Available: {list(MIGRATION_REGISTRY.keys())}"
        )
        return result

    # ---- C. Backup (before writing anything) ----
    if not dry_run:
        try:
            _create_backup(memory_root, from_version, to_version)
        except Exception as exc:
            log_path = memory_root / MIGRATIONS_LOG_NAME
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            line = f"{now} | {from_version} | {to_version} | failed_backup_failed | Backup creation failed: memory_root={memory_root} exc={exc}"
            if log_path.is_file():
                _append_migrations_log(log_path, line)
            else:
                log_path.write_text(f"# Migrations Log\n{line}\n", encoding="utf-8")
            result["success"] = False
            result["error"] = _BACKUP_FAILED
            result["errors"].append(
                f"Backup creation failed for {memory_root}: {exc}"
            )
            return result

    # ---- Execute migrations with auto-rollback on failure ----
    try:
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
                break

        # Rollback plan
        result["rollback"] = plan_rollback(memory_root)
        result["success"] = all_success
        return result

    except Exception as exc:
        # ---- F. Auto-rollback on any exception ----
        try:
            rb_result = execute_rollback(memory_root)
            rb_succeeded = rb_result.get("success", False)
        except Exception as rb_exc:
            rb_succeeded = False
            rb_result = {"success": False, "error": str(rb_exc)}

        log_path = memory_root / MIGRATIONS_LOG_NAME
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if rb_succeeded:
            line = f"{now} | {from_version} | {to_version} | failed_rolled_back | {exc}"
        else:
            line = f"{now} | {from_version} | {to_version} | failed_rollback_failed | Original migration error: {exc}; Rollback also failed: {rb_result.get('error', 'unknown')}"

        if log_path.is_file():
            _append_migrations_log(log_path, line)

        result["success"] = False
        result["rollback_attempted"] = True
        result["rollback_succeeded"] = rb_succeeded

        if rb_succeeded:
            result["errors"].append(f"Migration failed and rolled back: {exc}")
        else:
            result["errors"].append(
                f"Migration failed and rollback also failed. Original error: {exc}; Rollback error: {rb_result.get('error', 'unknown')}"
            )
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
        # Ensure JSON output always includes key fields even for noop
        output = dict(result)
        for key in ("from_version", "to_version", "target"):
            if key not in output:
                output[key] = ""
        print(json.dumps(output, indent=2, ensure_ascii=False))
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
