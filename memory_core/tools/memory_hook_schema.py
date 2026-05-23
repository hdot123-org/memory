"""Schema conversion: wb-hook-v2 → context-package-v1."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
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


# ---------------------------------------------------------------------------
# Generic diff helpers (used by is_lossless)
# ---------------------------------------------------------------------------


def _diff_dicts(
    input_obj: dict,
    output_obj: dict,
    prefix: str,
    expected_keys: set[str],
    dropped: list[str],
) -> None:
    """Recursively find keys in input_obj missing from output_obj."""
    for key in input_obj:
        full_path = f"{prefix}.{key}" if prefix else key
        if key in expected_keys:
            continue
        if key not in output_obj:
            dropped.append(full_path)
            continue

        in_val = input_obj[key]
        out_val = output_obj[key]

        if isinstance(in_val, dict) and isinstance(out_val, dict):
            _diff_dicts(in_val, out_val, full_path, expected_keys, dropped)
        elif isinstance(in_val, list) and isinstance(out_val, list):
            _diff_list(in_val, out_val, full_path, expected_keys, dropped)


def _diff_list(
    input_list: list,
    output_list: list,
    prefix: str,
    expected_keys: set[str],
    dropped: list[str],
) -> None:
    """Compare lists element-by-element for dict items."""
    min_len = min(len(input_list), len(output_list))
    for i in range(min_len):
        in_item = input_list[i]
        out_item = output_list[i]
        if isinstance(in_item, dict) and isinstance(out_item, dict):
            _diff_dicts(in_item, out_item, f"{prefix}[{i}]", expected_keys, dropped)
    for i in range(min_len, len(input_list)):
        dropped.append(f"{prefix}[{i}]")


# ---------------------------------------------------------------------------
# Audit logging — file-based (env-overridable) with stderr fallback
# ---------------------------------------------------------------------------

_DEFAULT_AUDIT_LOG = str(Path(__file__).resolve().parent.parent / "memory" / "system" / "schema-audit.log")


def _get_audit_log_path() -> str:
    return os.environ.get("MEMORY_SCHEMA_AUDIT_LOG", _DEFAULT_AUDIT_LOG)


def _write_audit_log(
    schema_from: str,
    schema_to: str,
    dropped_keys: list[str],
    input_size: int,
    output_size: int,
) -> None:
    """Write a structured audit line when keys are dropped.

    Writes to MEMORY_SCHEMA_AUDIT_LOG (default: memory_core/memory/system/schema-audit.log).
    Also emits to stderr for backward compatibility (existing tests rely on this).
    Falls back to stderr-only if the path is not writable.
    """
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "schema_convert",
        "drop_audit": True,
        "from_version": schema_from,
        "to_version": schema_to,
        "dropped_keys": dropped_keys,
        "input_size": input_size,
        "output_size": output_size,
    }
    line = json.dumps(record, ensure_ascii=False)

    log_path = _get_audit_log_path()
    try:
        p = Path(log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass

    # Always emit to stderr for backward compatibility
    print(line, file=sys.stderr)


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
    """Write a drop-audit record to file (fallback stderr).

    Never raises an exception.
    """
    if not _audit_enabled():
        return
    try:
        _write_audit_log(schema_from, schema_to, dropped_keys, 0, 0)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Schema converters
# ---------------------------------------------------------------------------


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

    # Audit: after conversion, check if any keys were dropped
    if _audit_enabled():
        _, dropped = _check_lossless_v2_to_v1(package)
        if dropped:
            _write_audit_log(
                V2_VERSION, V1_VERSION, dropped,
                len(package), len(result),
            )

    return result


def is_v1(package: dict[str, Any]) -> bool:
    """Return True if the package uses the context-package-v1 schema."""
    return package.get("schema_version") == V1_VERSION


def is_v2(package: dict[str, Any]) -> bool:
    """Return True if the package uses the wb-hook-v2 schema."""
    return package.get("schema_version") == V2_VERSION


# ---------------------------------------------------------------------------
# memory-v1 schema: project section references memory/system/* canonical files
# ---------------------------------------------------------------------------

MEMORY_V1_VERSION = "memory-v1"

_MEMORY_CANONICAL_MAP: dict[str, str] = {
    "canonical": "memory/system/CANONICAL.md",
    "plan": "memory/system/PLAN.md",
    "state": "memory/system/STATE.md",
    "tasks": "memory/system/TASKS.md",
}


def convert_to_memory_v1(package: dict[str, Any]) -> dict[str, Any]:
    """Convert a wb-hook-v2 context package to memory-v1 format.

    Structural changes on top of v1 conversion:
    - schema_version: "wb-hook-v2" → "memory-v1"
    - project section only references memory/system/* canonical files
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

    # Build memory/system/* canonical project section
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

    # Audit
    if _audit_enabled():
        _, dropped = _check_lossless_v2_to_memory_v1(package)
        if dropped:
            _write_audit_log(
                V2_VERSION, MEMORY_V1_VERSION, dropped,
                len(package), len(result),
            )

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

    # Audit
    if _audit_enabled():
        _, dropped = _check_lossless_v1_to_memory_v1(package)
        if dropped:
            _write_audit_log(
                V1_VERSION, MEMORY_V1_VERSION, dropped,
                len(package), len(result),
            )

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
    input_data: dict | str,
    output_data: dict | None = None,
    expected_keys: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """Return (is_lossless, list_of_dropped_keys).

    Two calling conventions:

    1. Generic dict comparison (primary):
       is_lossless(input_dict, output_dict, expected_keys=None)
       is_lossless == True iff every key from input_data exists in output_data
       (or in expected_keys whitelist).

    2. Schema-aware (backward compat):
       is_lossless(package, schema_from, schema_to)
       Supported paths: v2→v1, v1→memory-v1, v2→memory-v1.
    """
    # Detect schema-aware calling convention (2nd arg is a version string)
    if isinstance(input_data, dict) and isinstance(output_data, str):
        schema_from = output_data
        schema_to = (expected_keys if isinstance(expected_keys, str) else "")
        return _is_lossless_schema_aware(input_data, schema_from, schema_to)

    # Generic dict comparison
    if expected_keys is None:
        expected_keys = set()

    dropped: list[str] = []
    _diff_dicts(input_data, output_data or {}, "", expected_keys, dropped)
    return (len(dropped) == 0, dropped)


def _is_lossless_schema_aware(
    package: dict[str, Any],
    schema_from: str,
    schema_to: str,
) -> tuple[bool, list[str]]:
    """Backward-compatible schema-aware lossless check."""
    if schema_from == V2_VERSION and schema_to == V1_VERSION:
        return _check_lossless_v2_to_v1(package)
    if schema_from == V1_VERSION and schema_to == MEMORY_V1_VERSION:
        return _check_lossless_v1_to_memory_v1(package)
    if schema_from == V2_VERSION and schema_to == MEMORY_V1_VERSION:
        return _check_lossless_v2_to_memory_v1(package)
    return (False, [f"unknown_schema_pair: {schema_from}->{schema_to}"])


# Aliases for backward compatibility
is_lossless_schema = is_lossless
