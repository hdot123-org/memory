#!/usr/bin/env python3.12
"""migrate_project_memory 拆分：0.4.0 → 0.5.0 目录布局迁移。

M3 拆分（与 _gateway_* / _audit_* 同构）：持有 .memory/ → memory/system/
布局迁移的全部实现（备份、scope 提取、config/kb/templates/NOW.md 搬迁、
清理与 adapter.toml 版本重写），对外仅暴露 migrate_v040_to_v050。
"""

from __future__ import annotations

import contextlib
import json
import shutil
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION
from memory_core.tools.adapter_toml_schema import (
    dump_adapter_toml,
    load_adapter_toml,
)

from ._migrate_constants import (
    ADAPTER_TOML_NAME,
    BACKUP_MANIFEST_NAME,
    BACKUPS_DIR_NAME,
    V05_BACKUP_LABEL,
    V05_SYSTEM_DIR,
    _serialize_adapter_toml,
)

__all__ = [
    "migrate_v040_to_v050",
]

# ---------------------------------------------------------------------------
# Migrate 0.4.0 → 0.5.0: move .memory/ to memory/system/
# ---------------------------------------------------------------------------

# Config files to move from .memory/ to memory/system/
_V05_CONFIG_FILES = [
    "adapter.toml",
    "ownership.toml",
    "memory.lock",
    "migrations.log",
    "manifest.json",
    "integrity-audit.jsonl",
]

# Template files to move from .memory/ to memory/kb/projects/{scope}/
_V05_TEMPLATE_FILES = [
    "CANONICAL.md",
    "STATE.md",
    "PLAN.md",
    "TASKS.md",
]

# NOW.md: move from .memory/ to project root
_V05_NOW_MD = "NOW.md"

# Directories to delete (or move if non-empty) from .memory/
_V05_DELETED_DIRS = [
    "kb",
    "skills",
]


def _v05_backup(memory_root: Path, target_root: Path) -> Path:
    """Create backup at memory/system/backups/pre-0.5/ containing all .memory/ contents.

    Returns the backup directory path.
    """
    system_dir = target_root / V05_SYSTEM_DIR
    backup_dir = system_dir / BACKUPS_DIR_NAME / V05_BACKUP_LABEL
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Copy all contents of .memory/ to backup, excluding any existing backup dirs
    for item in memory_root.iterdir():
        if item.name == BACKUPS_DIR_NAME:
            continue
        dest = backup_dir / item.name
        if item.is_dir():
            shutil.copytree(str(item), str(dest))
        else:
            shutil.copy2(str(item), str(dest))

    # Write backup manifest
    source_files_count = sum(1 for p in memory_root.rglob("*") if p.is_file())
    manifest = {
        "from_version": "0.4.0",
        "to_version": "0.5.0",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_files_count": source_files_count,
        "source_root": str(memory_root),
    }
    manifest_path = backup_dir / BACKUP_MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return backup_dir


def _extract_scope_from_adapter(memory_root: Path) -> str:
    """Read adapter.toml from .memory/ and extract routing.project_scope.

    Returns the project_scope string.
    Raises ValueError if scope is missing or empty.
    """
    adapter_path = memory_root / ADAPTER_TOML_NAME
    if not adapter_path.exists():
        raise ValueError(
            f"Cannot determine project scope: {ADAPTER_TOML_NAME} not found in .memory/. "
            "Ensure .memory/adapter.toml exists with [routing] section containing project_scope."
        )

    try:
        config = load_adapter_toml(adapter_path)
    except Exception as exc:
        raise ValueError(f"Failed to read adapter.toml: {exc}. Ensure .memory/adapter.toml is valid TOML.") from exc

    scope = config.project_scope
    if not scope or not scope.strip():
        raise ValueError(
            "Cannot determine project scope: routing.project_scope is empty or missing in .memory/adapter.toml. "
            "Add project_scope under [routing] section, e.g.:\n"
            "  [routing]\n"
            '  project_scope = "your-project-name"'
        )

    return scope.strip()


def _v05_check_already_migrated(memory_root: Path, result: dict[str, Any]) -> bool:
    """Check if migration already completed (idempotency)."""
    if not memory_root.exists():
        system_dir = memory_root.parent / V05_SYSTEM_DIR
        if system_dir.exists():
            result["success"] = True
            result["detail"] = "already migrated to 0.5.0"
            return True
    return False


def _v05_move_config(memory_root: Path, system_dir: Path) -> None:
    """Move config files from .memory/ to memory/system/."""
    for filename in _V05_CONFIG_FILES:
        src = memory_root / filename
        if src.exists():
            dest = system_dir / filename
            shutil.move(str(src), str(dest))


def _v05_move_kb(memory_root: Path, system_dir: Path) -> None:
    """Move kb/ and skills/ if non-empty, otherwise remove."""
    for dirname in _V05_DELETED_DIRS:
        src_dir = memory_root / dirname
        if src_dir.exists():
            if any(src_dir.iterdir()):
                dest_dir = system_dir / dirname
                shutil.move(str(src_dir), str(dest_dir))
            else:
                shutil.rmtree(str(src_dir))


def _v05_move_templates(
    memory_root: Path,
    template_dest_dir: Path,
    result: dict[str, Any],
) -> None:
    """Move template files to memory/kb/projects/{scope}/."""
    for filename in _V05_TEMPLATE_FILES:
        src = memory_root / filename
        if src.exists():
            dest = template_dest_dir / filename
            if dest.exists():
                result["residue"].append(f"Skipped {filename}: destination already exists")
            else:
                shutil.move(str(src), str(dest))


def _v05_move_now_md(memory_root: Path, result: dict[str, Any]) -> None:
    """Move NOW.md from .memory/ to project root."""
    target_root = memory_root.parent
    now_md_src = memory_root / _V05_NOW_MD
    now_md_dest = target_root / _V05_NOW_MD
    if now_md_src.exists():
        if now_md_dest.exists():
            result["residue"].append(f"Skipped {_V05_NOW_MD}: already exists at project root")
            now_md_src.unlink()
        else:
            shutil.move(str(now_md_src), str(now_md_dest))


def _v05_cleanup(memory_root: Path, result: dict[str, Any]) -> None:
    """Remove .memory/ directory if empty or has only remaining subdirs."""
    remaining_items = list(memory_root.iterdir())
    for item in remaining_items:
        if item.name == BACKUPS_DIR_NAME and not any(item.iterdir()):
            shutil.rmtree(str(item))

    try:
        for item in memory_root.iterdir():
            if item.is_dir():
                with contextlib.suppress(OSError):
                    shutil.rmtree(str(item))
            else:
                item.unlink()
        memory_root.rmdir()
    except OSError:
        result["residue"].append("Warning: .memory/ directory could not be fully removed")


def _v05_rewrite_adapter_toml(
    adapter_path: Path,
    result: dict[str, Any],
) -> None:
    """Update adapter.toml version to 0.5.0."""
    if not adapter_path.exists():
        return
    try:
        raw_data: dict[str, Any] = tomllib.loads(adapter_path.read_text(encoding="utf-8"))
        if "core" in raw_data:
            raw_data["core"]["version"] = CURRENT_MEMORY_VERSION
        elif "adapter" in raw_data:
            raw_data["adapter"]["adapter_version"] = CURRENT_MEMORY_VERSION

        lines = _serialize_adapter_toml(raw_data, header="adapter.toml (migrated to 0.5.0)")
        tmp_path = adapter_path.parent / ".adapter.toml.migrating"
        tmp_path.write_text("\n".join(lines), encoding="utf-8")
        config = load_adapter_toml(tmp_path)
        config.adapter_version = CURRENT_MEMORY_VERSION
        adapter_path.write_text(dump_adapter_toml(config), encoding="utf-8")
        tmp_path.unlink(missing_ok=True)
    except Exception as exc:
        result["residue"].append(f"adapter.toml update failed: {exc}")


def migrate_v040_to_v050(memory_root: Path) -> dict[str, Any]:
    """Migration: 0.4.0 → 0.5.0.

    1. Reads adapter.toml from .memory/ to extract project_scope
    2. Backs up .memory/ to memory/system/backups/pre-0.5/
    3. Moves config files (adapter.toml, ownership.toml, memory.lock,
       migrations.log, manifest.json, integrity-audit.jsonl) to memory/system/
    4. Moves kb/ and skills/ if they exist and are non-empty
    5. Moves template files (CANONICAL.md, STATE.md, PLAN.md, TASKS.md) to
       memory/kb/projects/{scope}/ (skips if destination already exists)
    6. Moves NOW.md from .memory/ to project root (if not already there)
    7. Removes empty .memory/ directory
    8. Updates adapter.toml version to 0.5.0

    Idempotent: if .memory/ doesn't exist, returns success with noop.
    """
    result: dict[str, Any] = {"success": False, "detail": "", "residue": [], "errors": []}

    if _v05_check_already_migrated(memory_root, result):
        return result

    target_root = memory_root.parent
    system_dir = target_root / V05_SYSTEM_DIR
    system_dir.mkdir(parents=True, exist_ok=True)

    try:
        project_scope = _extract_scope_from_adapter(memory_root)
    except ValueError as exc:
        result["success"] = False
        result["error"] = "missing_project_scope"
        result["detail"] = str(exc)
        result["errors"].append(str(exc))
        return result

    template_dest_dir = target_root / "memory" / "kb" / "projects" / project_scope
    template_dest_dir.mkdir(parents=True, exist_ok=True)

    try:
        _v05_backup(memory_root, target_root)
    except Exception as exc:
        result["detail"] = f"Backup creation failed: {exc}"
        return result

    _v05_move_config(memory_root, system_dir)
    _v05_move_kb(memory_root, system_dir)
    _v05_move_templates(memory_root, template_dest_dir, result)
    _v05_move_now_md(memory_root, result)
    _v05_cleanup(memory_root, result)

    adapter_path = system_dir / ADAPTER_TOML_NAME
    _v05_rewrite_adapter_toml(adapter_path, result)

    result["success"] = True
    result["detail"] = (
        f"Migrated from 0.4.0 to 0.5.0: moved config to memory/system/, "
        f"templates to memory/kb/projects/{project_scope}/, removed .memory/"
    )
    return result
