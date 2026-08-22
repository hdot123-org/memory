#!/usr/bin/env python3.12
"""migrate_project_memory 拆分：备份创建与软回滚（plan + execute）。

M3 拆分（与 _gateway_* / _audit_* 同构）：持有迁移前备份
（.memory/backups/<ts>/ 与 v0.5+ 布局备份）、备份发现、plan_rollback /
execute_rollback 软回滚，以及 memory.lock 当前版本读取。
"""

from __future__ import annotations

import json
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._migrate_constants import (
    BACKUP_MANIFEST_NAME,
    BACKUPS_DIR_NAME,
    MEMORY_LOCK_NAME,
    MIGRATIONS_LOG_NAME,
    V05_BACKUP_LABEL,
    V05_SYSTEM_DIR,
)
from ._migrate_registry import _append_migrations_log

__all__ = [
    "_count_backup_source_files",
    "_create_backup",
    "_find_v05_backup",
    "_read_current_version",
    "_write_backup_manifest",
    "execute_rollback",
    "plan_rollback",
]

# ---------------------------------------------------------------------------
# Backup helpers
# ---------------------------------------------------------------------------


def _count_backup_source_files(memory_root: Path) -> int:
    """Count files under memory_root, excluding the backups/ subtree."""
    count = 0
    for p in memory_root.rglob("*"):
        if p.is_file():
            rel = p.relative_to(memory_root)
            if rel.parts[0] != BACKUPS_DIR_NAME:
                count += 1
    return count


def _write_backup_manifest(
    backup_dest: Path,
    from_version: str,
    to_version: str,
    source_files_count: int,
    *,
    layout: str | None = None,
) -> None:
    """Write BACKUP_MANIFEST.json into a freshly created backup directory."""
    manifest = {
        "from_version": from_version,
        "to_version": to_version,
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_files_count": source_files_count,
    }
    if layout is not None:
        manifest["layout"] = layout
    manifest_path = backup_dest / BACKUP_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _create_backup(memory_root: Path, from_version: str, to_version: str) -> Path:
    """Copy .memory/ (excluding backups/) to .memory/backups/<utc_iso8601_compact>/.

    Returns the backup directory path.
    """
    backups_dir = memory_root / BACKUPS_DIR_NAME
    backups_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_dest = backups_dir / ts

    def _ignore_backups(dirpath: str, names: list[str]) -> list[str]:
        """Exclude the backups/ subdirectory from copy."""
        if Path(dirpath) == memory_root:
            return [BACKUPS_DIR_NAME]
        return []

    shutil.copytree(str(memory_root), str(backup_dest), ignore=_ignore_backups)

    # Count source files (excluding backups/)
    source_files_count = _count_backup_source_files(memory_root)
    _write_backup_manifest(backup_dest, from_version, to_version, source_files_count)

    return backup_dest


# ---------------------------------------------------------------------------
# Rollback planning — reads backups directory
# ---------------------------------------------------------------------------


def _find_v05_backup(target_root: Path) -> Path | None:
    """Find a 0.4→0.5 backup at memory/system/backups/pre-0.5/.

    Returns the backup dir path or None.
    """
    system_dir = target_root / V05_SYSTEM_DIR
    backup_dir = system_dir / BACKUPS_DIR_NAME / V05_BACKUP_LABEL
    if backup_dir.is_dir() and (backup_dir / BACKUP_MANIFEST_NAME).is_file():
        return backup_dir
    return None


def plan_rollback(memory_root: Path) -> dict[str, Any]:
    """Check if a rollback is possible by looking at backups/.

    Checks both legacy location (.memory/backups/) and new location
    (memory/system/backups/pre-0.5/).
    Returns the latest backup metadata or can_rollback=False.
    """
    target_root = memory_root.parent

    # Check new 0.5 location first
    v05_backup = _find_v05_backup(target_root)
    if v05_backup is not None:
        manifest = json.loads((v05_backup / BACKUP_MANIFEST_NAME).read_text(encoding="utf-8"))
        return {
            "can_rollback": True,
            "backup_dir": str(v05_backup),
            "from_version": manifest["from_version"],
            "to_version": manifest["to_version"],
            "ts": manifest["timestamp"],
            "is_v05_backup": True,
        }

    # Fall back to legacy location
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
    manifest = json.loads((latest / BACKUP_MANIFEST_NAME).read_text(encoding="utf-8"))

    return {
        "can_rollback": True,
        "backup_dir": str(latest),
        "from_version": manifest["from_version"],
        "to_version": manifest["to_version"],
        "ts": manifest["timestamp"],
        "is_v05_backup": False,
    }


# ---------------------------------------------------------------------------
# execute_rollback — restore from backup
# ---------------------------------------------------------------------------


def execute_rollback(memory_root: Path, *, backup_dir: Path | None = None) -> dict[str, Any]:
    """Restore .memory/ from the latest backup (or specified backup_dir).

    Supports both legacy backups (.memory/backups/<ts>/) and v0.5 backups
    (memory/system/backups/pre-0.5/).
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

    # Determine the plan: check if this is a v0.5 backup by looking for manifest
    manifest_path = bd / BACKUP_MANIFEST_NAME
    is_v05_backup = False
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            is_v05_backup = manifest.get("to_version") == "0.5.0"
        except (json.JSONDecodeError, OSError):
            pass

    # For v0.5 backups, .memory/ may not exist yet — create it
    if is_v05_backup and not memory_root.exists():
        memory_root.mkdir(parents=True, exist_ok=True)

    # Delete current .memory/ contents except backups/
    if memory_root.exists():
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
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
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
            return str(data.get("version")) if data.get("version") is not None else None
        else:
            data = tomllib.loads(text)
            ver = data.get("memory", {}).get("memory_version")
            return str(ver) if ver is not None else None
    except Exception:
        return None
