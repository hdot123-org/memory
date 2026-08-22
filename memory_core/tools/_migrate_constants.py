#!/usr/bin/env python3.12
"""migrate_project_memory 拆分：底层常量与纯工具函数。

M3 拆分（与 _gateway_* / _audit_* 同构）：本模块位于依赖链最底层，
仅持有名称/路径常量、降级拒绝常量，以及无副作用的版本解析与
memory.lock TOML 写入工具；不依赖任何其他 _migrate_* 子模块。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = [
    "ADAPTER_TOML_NAME",
    "BACKUP_MANIFEST_NAME",
    "BACKUPS_DIR_NAME",
    "MEMORY_LOCK_NAME",
    "MIGRATIONS_LOG_NAME",
    "V05_BACKUP_LABEL",
    "V05_SYSTEM_DIR",
    "_CURRENT_NEWER_THAN_TARGET",
    "_DOWNGRADE_NOT_SUPPORTED",
    "_parse_version_tuple",
    "_serialize_adapter_toml",
    "_write_toml_memory_lock",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIGRATIONS_LOG_NAME = "migrations.log"
MEMORY_LOCK_NAME = "memory.lock"
ADAPTER_TOML_NAME = "adapter.toml"
BACKUPS_DIR_NAME = "backups"
BACKUP_MANIFEST_NAME = "BACKUP_MANIFEST.json"

# 0.4 → 0.5 migration constants
V05_SYSTEM_DIR = Path("memory") / "system"
V05_BACKUP_LABEL = "pre-0.5"

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


def _serialize_adapter_toml(raw_data: dict[str, Any], *, header: str) -> list[str]:
    """Serialize an adapter config dict to simple TOML lines (sections/scalars/lists).

    Shared by the 0.1→0.2 and 0.4→0.5 migrations, which must both round-trip
    legacy adapter.toml content through a minimal writer before reloading it
    via load_adapter_toml.
    """
    lines: list[str] = [f"# {header}", ""]
    for section, sdata in raw_data.items():
        if isinstance(sdata, dict):
            lines.append(f"[{section}]")
            for k, v in sdata.items():
                if isinstance(v, list):
                    vals = ", ".join(f'"{x}"' for x in v)
                    lines.append(f"{k} = [{vals}]")
                elif isinstance(v, bool):
                    lines.append(f"{k} = {'true' if v else 'false'}")
                else:
                    lines.append(f'{k} = "{v}"')
            lines.append("")
    return lines
