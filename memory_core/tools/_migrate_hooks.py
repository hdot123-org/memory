#!/usr/bin/env python3.12
"""migrate_project_memory 拆分：M6 所有权/manifest 升级钩子。

M3 拆分（与 _gateway_* / _audit_* 同构）：持有旧项目迁移所需的
ownership.toml 默认生成（M6）与 manifest v1→v2 结构升级，供迁移编排
在 post-migration hook 阶段调用。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from memory_core.constants import (
    CURRENT_MEMORY_VERSION,
    OWNERSHIP_SCHEMA_VERSION,
)

# M6: Import ownership APIs for old project migration
try:
    from memory_core.ownership import (
        DEFAULT_OWNERSHIP_DOMAINS,
        DEFAULT_OWNERSHIP_RESOURCES,
        MemoryOwnership,
    )
except ImportError:
    MemoryOwnership = None  # type: ignore[misc,assignment]
    DEFAULT_OWNERSHIP_DOMAINS = []
    DEFAULT_OWNERSHIP_RESOURCES = []

__all__ = [
    "MANIFEST_FILENAME",
    "OWNERSHIP_TOML_NAME",
    "_generate_default_ownership_toml",
    "_upgrade_manifest_v1_to_v2",
]

# ---------------------------------------------------------------------------
# M6: Ownership generation for old projects
# ---------------------------------------------------------------------------

OWNERSHIP_TOML_NAME = "ownership.toml"


def _generate_default_ownership_toml(memory_root: Path) -> dict[str, Any]:
    """Generate a default ownership.toml for old projects that lack one.

    Returns a result dict with 'success' and 'detail' keys.
    """
    if MemoryOwnership is None:
        return {"success": False, "detail": "ownership module not available"}

    ownership_path = memory_root / OWNERSHIP_TOML_NAME
    if ownership_path.exists():
        return {"success": True, "detail": "ownership.toml already exists, skipped"}

    try:
        ownership = MemoryOwnership(
            schema_version=OWNERSHIP_SCHEMA_VERSION,
            memory_version=CURRENT_MEMORY_VERSION,
            domains=list(DEFAULT_OWNERSHIP_DOMAINS),
            resources=list(DEFAULT_OWNERSHIP_RESOURCES),
            policy={},
        )

        # Write TOML manually (no tomli-w dependency)
        lines = [
            f'schema_version = "{ownership.schema_version}"',
            f'memory_version = "{ownership.memory_version}"',
            "",
        ]

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
                lines.append(f'domain = "{r.domain or ""}"')
                lines.append(f'description = "{r.description}"')
                lines.append("")

        ownership_path.write_text("\n".join(lines), encoding="utf-8")
        return {"success": True, "detail": f"Generated default {OWNERSHIP_TOML_NAME}"}

    except Exception as exc:
        return {"success": False, "detail": f"Failed to generate ownership.toml: {exc}"}


# ---------------------------------------------------------------------------
# M6: Manifest version handling for migration
# ---------------------------------------------------------------------------

MANIFEST_FILENAME = "manifest.json"


def _upgrade_manifest_v1_to_v2(memory_root: Path) -> dict[str, Any]:
    """Read old v1 manifest (if present), upgrade structure to v2 format.

    The v1 manifest has entries without ownership fields.
    The v2 manifest adds ownership_id, protection_level, classification_source.
    If no manifest exists, returns success without action.
    """
    manifest_path = memory_root / MANIFEST_FILENAME
    if not manifest_path.exists():
        return {"success": True, "detail": "No manifest to upgrade"}

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"success": False, "detail": f"Cannot read manifest: {exc}"}

    schema = data.get("schema_version", "")
    if schema == "integrity-manifest-v2":
        return {"success": True, "detail": "Manifest already v2, skipped"}
    if schema != "integrity-manifest-v1":
        return {"success": True, "detail": f"Unknown schema {schema}, skipped"}

    # Upgrade v1 entries to v2 by adding ownership fields
    for entry in data.get("entries", []):
        entry.setdefault("ownership_id", "none")
        entry.setdefault("protection_level", "none")
        entry.setdefault("classification_source", "none")

    data["schema_version"] = "integrity-manifest-v2"
    data.setdefault("ownership_digest", "")

    try:
        manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return {"success": True, "detail": "Upgraded manifest v1 → v2"}
    except OSError as exc:
        return {"success": False, "detail": f"Failed to write v2 manifest: {exc}"}
