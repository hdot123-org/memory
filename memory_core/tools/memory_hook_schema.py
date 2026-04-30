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


# ---------------------------------------------------------------------------
# memory-v1 schema: project section references .memory/* canonical files
# ---------------------------------------------------------------------------

MEMORY_V1_VERSION = "memory-v1"

_MEMORY_CANONICAL_MAP: dict[str, str] = {
    "canonical": ".memory/CANONICAL.md",
    "plan": ".memory/PLAN.md",
    "state": ".memory/STATE.md",
    "tasks": ".memory/TASKS.md",
}


def convert_to_memory_v1(package: dict[str, Any]) -> dict[str, Any]:
    """Convert a wb-hook-v2 context package to memory-v1 format.

    Structural changes on top of v1 conversion:
    - schema_version: "wb-hook-v2" → "memory-v1"
    - project section only references .memory/* canonical files
    - Keeps paths, task, and remaining top-level keys identical to v1
    """
    result: dict[str, Any] = {"schema_version": MEMORY_V1_VERSION}

    # Nest path fields
    paths: dict[str, Any] = {}
    for key in ("repo_root", "workspace_root", "cwd"):
        if key in package:
            paths[key] = package[key]
    if paths:
        result["paths"] = paths

    # Build .memory/* canonical project section
    if "project_context" in package:
        project_ctx = package["project_context"]
        result["project"] = {
            "scope": project_ctx.get("scope", ""),
            **_MEMORY_CANONICAL_MAP,
        }

    # Rename task_context → task
    if "task_context" in package:
        result["task"] = package["task_context"]

    # Carry forward remaining top-level keys as-is
    for key in _KEEP_KEYS:
        if key in package:
            result[key] = package[key]

    return result


def convert_legacy_to_memory_v1(package: dict[str, Any]) -> dict[str, Any]:
    """Convert either v2 or v1 context package to memory-v1 format.

    - If already memory-v1, return as-is.
    - If context-package-v1, lift from v1 structure.
    - If wb-hook-v2, delegate to convert_to_memory_v1.
    """
    if is_memory_v1(package):
        return package
    if is_v1(package):
        return _convert_v1_to_memory_v1(package)
    return convert_to_memory_v1(package)


def _convert_v1_to_memory_v1(package: dict[str, Any]) -> dict[str, Any]:
    """Convert a context-package-v1 package to memory-v1 format."""
    result: dict[str, Any] = {"schema_version": MEMORY_V1_VERSION}

    if "paths" in package:
        result["paths"] = package["paths"]

    if "project" in package:
        project_v1 = package["project"]
        result["project"] = {
            "scope": project_v1.get("scope", ""),
            **_MEMORY_CANONICAL_MAP,
        }

    if "task" in package:
        result["task"] = package["task"]

    for key in _KEEP_KEYS:
        if key in package:
            result[key] = package[key]

    return result


def is_memory_v1(package: dict[str, Any]) -> bool:
    """Return True if the package uses the memory-v1 schema."""
    return package.get("schema_version") == MEMORY_V1_VERSION
