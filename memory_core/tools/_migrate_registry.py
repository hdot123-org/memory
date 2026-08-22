#!/usr/bin/env python3.12
"""migrate_project_memory 拆分：迁移注册表、发现与 migrations.log 写入。

M3 拆分（与 _gateway_* / _audit_* 同构）：持有 0.1→0.2 与 0.7→0.8 单步
迁移、MIGRATION_REGISTRY、discover_migrations 以及带 fcntl 排他锁的
migrations.log 原子追加（``_append_migrations_log`` / ``append_migration_log``）。
"""

from __future__ import annotations

import json
import os
import tomllib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION
from memory_core.tools.adapter_toml_schema import (
    _apply_migration_transforms,
    dump_adapter_toml,
    load_adapter_toml,
)

from ._file_utils import exclusive_lock
from ._migrate_constants import (
    ADAPTER_TOML_NAME,
    MEMORY_LOCK_NAME,
    MIGRATIONS_LOG_NAME,
    _serialize_adapter_toml,
    _write_toml_memory_lock,
)
from ._migrate_v05 import migrate_v040_to_v050

__all__ = [
    "MIGRATION_REGISTRY",
    "_append_migrations_log",
    "append_migration_log",
    "discover_migrations",
    "migrate_v010_to_v020",
    "migrate_v070_to_v080",
]

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
                    "locked_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "lock_reason": "upgrade",
                }
            }
        else:
            lock_data = tomllib.loads(text)
            memory = lock_data.get("memory") or {}
            old_version = memory.get("memory_version", "unknown")
            memory["memory_version"] = CURRENT_MEMORY_VERSION
            memory["locked_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
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
            raw_data: dict[str, Any] = tomllib.loads(adapter_path.read_text(encoding="utf-8"))
            transformed = _apply_migration_transforms(
                raw_data,
                "0.1.0",
                CURRENT_MEMORY_VERSION,
            )
            # Write transformed dict as temp TOML, load as AdapterConfig, dump canonical
            _tmp_path = adapter_path.parent / ".adapter.toml.migrating"
            _lines = _serialize_adapter_toml(transformed, header="adapter.toml (migrated)")
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


# ---------------------------------------------------------------------------
# Migrate 0.7.0 → 0.8.0: inject [global_kb] section
# ---------------------------------------------------------------------------


def migrate_v070_to_v080(memory_root: Path) -> dict[str, Any]:
    """Migration: 0.7.0 → 0.8.0.

    1. Reads adapter.toml from memory/system/
    2. If [global_kb] section already exists, skip injection (idempotent)
    3. Otherwise, inject [global_kb] section with defaults:
       - enabled = true
       - root = "~/.memory/global-kb"
    4. Updates memory.lock version to 0.8.0
    5. Updates adapter.toml [core].version to 0.8.0
    6. Preserves all existing [core]/[policy]/[routing]/[sync] sections

    Idempotent: if [global_kb] already exists, returns success without changes.
    """
    result: dict[str, Any] = {"success": False, "detail": "", "residue": []}

    adapter_path = memory_root / ADAPTER_TOML_NAME
    if not adapter_path.is_file():
        result["detail"] = f"{ADAPTER_TOML_NAME} not found in {memory_root}"
        return result

    lock_path = memory_root / MEMORY_LOCK_NAME
    if not lock_path.is_file():
        result["detail"] = f"{MEMORY_LOCK_NAME} not found in {memory_root}"
        return result

    try:
        # Load adapter.toml
        config = load_adapter_toml(adapter_path)

        # Check if [global_kb] already exists in raw TOML
        raw_data = tomllib.loads(adapter_path.read_text(encoding="utf-8"))
        has_global_kb = "global_kb" in raw_data

        if has_global_kb:
            # Already has [global_kb], just update version if needed
            result["success"] = True
            result["detail"] = "already has [global_kb] section, skipped injection"
            # Still need to update version
        else:
            # Inject [global_kb] with defaults
            # The AdapterConfig already has default values for global_kb_enabled and global_kb_root
            # We just need to ensure they are set correctly
            config.global_kb_enabled = True
            config.global_kb_root = str(Path("~/.memory/global-kb").expanduser())

        # Update version in AdapterConfig
        config.adapter_version = "0.8.0"

        # Write back adapter.toml
        adapter_path.write_text(dump_adapter_toml(config), encoding="utf-8")

        # Update memory.lock
        lock_text = lock_path.read_text(encoding="utf-8")
        # JSON format (legacy) or TOML format (canonical)
        lock_data = json.loads(lock_text) if lock_text.strip().startswith("{") else tomllib.loads(lock_text)
        lock_data.setdefault("memory", {})["memory_version"] = "0.8.0"
        lock_data["memory"]["locked_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        lock_data["memory"]["lock_reason"] = "upgrade to 0.8.0"
        _write_toml_memory_lock(lock_data, lock_path)

        if not result["detail"]:
            result["detail"] = "Migrated from 0.7.0 to 0.8.0: injected [global_kb] section"
        result["success"] = True

        # Sync project-map files to current template (fixes stale legal-core-map
        # and ingestion-registry-map from older init templates).
        project_root = memory_root.parent.parent  # memory/system → project root
        project_map_dir = project_root / "project-map"
        if project_map_dir.is_dir():
            try:
                from memory_core.tools.init_project_memory import KB_TEMPLATES
            except ImportError:
                KB_TEMPLATES = {}

            synced = []
            for rel_name in (
                "project-map/legal-core-map.md",
                "project-map/ingestion-registry-map.md",
            ):
                template_entry = KB_TEMPLATES.get(rel_name)
                target_path = project_root / rel_name
                if template_entry is None or not target_path.parent.is_dir():
                    continue
                template_text = template_entry("default")[0]  # (content, deps)
                if not target_path.exists() or target_path.read_text(encoding="utf-8") != template_text:
                    target_path.write_text(template_text, encoding="utf-8")
                    synced.append(rel_name)
            if synced:
                result["residue"].append(f"synced project-map files: {', '.join(synced)}")

        return result

    except Exception as exc:
        result["detail"] = f"Failed to migrate 0.7.0→0.8.0: {exc}"
        return result


MIGRATION_REGISTRY: dict[str, Callable[[Path], dict[str, Any]]] = {
    f"0.1.0->{CURRENT_MEMORY_VERSION}": migrate_v010_to_v020,
    "0.4.0->0.5.0": migrate_v040_to_v050,
    "0.7.0->0.8.0": migrate_v070_to_v080,
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

    Uses exclusive_lock for cross-platform file locking.
    """
    with log_path.open("a", encoding="utf-8") as f, exclusive_lock(f):
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


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
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
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
