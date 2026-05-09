"""Schema conversion: wb-hook-v2 → context-package-v1."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
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

# project sub-keys that are dropped during v1 → memory-v1 conversion
_DROP_PROJECT_KEYS = frozenset({
    "name",
    "description",
    "tech_stack",
})


def _audit_enabled() -> bool:
    """Return True if audit logging is enabled (default: enabled).

    Controlled by env var MEMORY_HOOK_SCHEMA_AUDIT:
    - "0" → silent (disabled)
    - anything else (including unset) → enabled
    """
    return os.environ.get("MEMORY_HOOK_SCHEMA_AUDIT", "1") != "0"


def _emit_drop_audit(
    schema_from: str,
    schema_to: str,
    dropped_keys: list[str],
    package_id: str = "",
) -> None:
    """Write a drop-audit record to stderr.

    Format:
    [memory_hook_schema][drop_audit] from=<src> to=<dst> dropped=<keys_csv> ts=<iso8601>

    Never raises an exception.
    """
    try:
        keys_csv = ",".join(dropped_keys)
        ts = datetime.now(timezone.utc).isoformat()
        msg = (
            f"[memory_hook_schema][drop_audit] "
            f"from={schema_from} to={schema_to} "
            f"dropped={keys_csv} ts={ts}"
        )
        print(msg, file=sys.stderr)
    except Exception:
        pass  # Never raise


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
    # Audit: detect dropped keys and emit
    if _audit_enabled():
        lossless, dropped = _check_lossless_v2_to_v1(package)
        if not lossless and dropped:
            _emit_drop_audit(V2_VERSION, V1_VERSION, dropped)

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


# ---------------------------------------------------------------------------
# is_lossless public API + internal helpers (must come after MEMORY_V1_VERSION)
# ---------------------------------------------------------------------------


def _check_lossless_v2_to_v1(package: dict[str, Any]) -> tuple[bool, list[str]]:
    """Internal helper: check if v2→v1 conversion would drop any _DROP_KEYS."""
    dropped: list[str] = [key for key in _DROP_KEYS if key in package]
    if dropped:
        return (False, dropped)
    return (True, [])


def _check_lossless_v1_to_memory_v1(package: dict[str, Any]) -> tuple[bool, list[str]]:
    """Internal helper: check if v1→memory-v1 would drop project sub-keys."""
    dropped: list[str] = []
    if "project" in package:
        project = package["project"]
        for sub_key in _DROP_PROJECT_KEYS:
            if sub_key in project:
                dropped.append(f"project.{sub_key}")
    if dropped:
        return (False, dropped)
    return (True, [])


def _check_lossless_v2_to_memory_v1(package: dict[str, Any]) -> tuple[bool, list[str]]:
    """Internal helper: check if v2→memory-v1 would drop keys."""
    dropped: list[str] = [key for key in _DROP_KEYS if key in package]
    if "project_context" in package:
        project_ctx = package["project_context"]
        for sub_key in _DROP_PROJECT_KEYS:
            if sub_key in project_ctx:
                dropped.append(f"project.{sub_key}")
    if dropped:
        return (False, dropped)
    return (True, [])


def is_lossless(
    package: dict[str, Any],
    schema_from: str,
    schema_to: str,
) -> tuple[bool, list[str]]:
    """Return (True, []) if the conversion would be lossless, else (False, dropped_keys).

    Supported conversion paths:
    - wb-hook-v2 → context-package-v1: checks _DROP_KEYS
    - context-package-v1 → memory-v1: checks project sub-keys (name, description, tech_stack)
    - wb-hook-v2 → memory-v1: checks both _DROP_KEYS and project sub-keys
    """
    if schema_from == V2_VERSION and schema_to == V1_VERSION:
        return _check_lossless_v2_to_v1(package)
    if schema_from == V1_VERSION and schema_to == MEMORY_V1_VERSION:
        return _check_lossless_v1_to_memory_v1(package)
    if schema_from == V2_VERSION and schema_to == MEMORY_V1_VERSION:
        return _check_lossless_v2_to_memory_v1(package)
    return (True, [])
