"""Schema conversion: wb-hook-v2 → context-package-v1."""

from __future__ import annotations

from typing import Any

V1_VERSION = "context-package-v1"
V2_VERSION = "wb-hook-v2"

# Top-level keys carried forward as-is from v2 to v1
_KEEP_KEYS = frozenset({
    "generated_at",
    "host",
    "event",
    "status",
    "project_scope",
    "allowed_reads",
    "allowed_writes",
    "evidence_refs",
    "validation_errors",
})

# v2 keys that are dropped (diagnostic info → stderr/logs)
_DROP_KEYS = frozenset({
    "system_context",
    "missing_paths",
})


def convert_to_v1(package: dict[str, Any]) -> dict[str, Any]:
    """Convert a wb-hook-v2 context package to context-package-v1 format.

    Structural changes:
    - schema_version: "wb-hook-v2" → "context-package-v1"
    - Flatten repo_root / workspace_root / cwd into nested "paths" sub-dict
    - Rename "project_context" → "project"
    - Rename "task_context" → "task"
    - Remove "system_context" (diagnostic info goes to stderr/logs)
    - Remove "missing_paths" (merged into validation_errors upstream)
    """
    result: dict[str, Any] = {"schema_version": V1_VERSION}

    # Nest path fields
    paths: dict[str, Any] = {}
    for key in ("repo_root", "workspace_root", "cwd"):
        if key in package:
            paths[key] = package[key]
    if paths:
        result["paths"] = paths

    # Rename project_context → project
    if "project_context" in package:
        result["project"] = package["project_context"]

    # Rename task_context → task
    if "task_context" in package:
        result["task"] = package["task_context"]

    # Carry forward remaining top-level keys as-is
    for key in _KEEP_KEYS:
        if key in package:
            result[key] = package[key]

    return result


def is_v1(package: dict[str, Any]) -> bool:
    """Return True if the package uses the context-package-v1 schema."""
    return package.get("schema_version") == V1_VERSION


def is_v2(package: dict[str, Any]) -> bool:
    """Return True if the package uses the wb-hook-v2 schema."""
    return package.get("schema_version") == V2_VERSION
