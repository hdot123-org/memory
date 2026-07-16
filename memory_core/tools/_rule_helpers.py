# -*- coding: utf-8 -*-
"""
Shared rule helper functions extracted from business_policy_checks.py.

This module contains 8 functions that were duplicated across:
- business_policy_checks.py
- memory_hook_impls.py
- memory_hook_gateway.py

Part of REF-001 strangler fig scaffold phase.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _path_is_under(path: Path, root: Path) -> bool:
    """Check if path is under root using resolved paths."""
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _get_write_targets_dict(workspace_root: Path) -> dict[str, Any]:
    """
    Build the standard write targets dictionary.

    This is the single source of truth for the write-targets mapping used by:
    - memory_hook_impls.py (PathUtils.write_targets)
    - memory_hook_gateway.py (write_targets function)

    Args:
        workspace_root: The workspace root path

    Returns:
        Dictionary mapping target names to their paths
    """
    today_log = workspace_root / "memory" / "log" / f"{datetime.now().date().isoformat()}.md"
    return {
        "fact": str(today_log),
        "global_canonical": str(workspace_root / "memory" / "kb" / "global"),
        "project_canonical": str(workspace_root / "memory" / "kb" / "projects"),
        "decision": str(workspace_root / "memory" / "kb" / "decisions"),
        "lesson": str(workspace_root / "memory" / "kb" / "lessons"),
        "docs": str(workspace_root / "memory" / "docs"),
        "action": str(workspace_root / "memory" / "inbox.md"),
        "project_runtime": str(workspace_root / "projects"),
        "artifacts": str(workspace_root / "memory" / "artifacts"),
        "system_error": str(workspace_root / "memory" / "system" / "errors.log"),
        "invalid_memory": str(workspace_root / "memory" / "archive" / "invalid"),
        "kb_policy": {
            "mode": "read-first-CRUD",
            "overwrite_allowed": False,
            "conflict_strategy": "preserve-and-escalate",
        },
    }


def _path_is_under_lexical(path: Path, root: Path) -> bool:
    """Check lexical containment without following symlinks."""
    try:
        path.expanduser().absolute().relative_to(root.expanduser().absolute())
        return True
    except ValueError:
        return False


def _section_bullets(text: str, heading: str) -> list[str]:
    """Extract bullet points from a markdown section."""
    lines = text.splitlines()
    bullets: list[str] = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped == heading or stripped.endswith(heading.replace("## ", "").replace("### ", "")):
            in_section = True
            continue
        if in_section and stripped.startswith("#"):
            break
        if in_section and line.strip().startswith("- "):
            bullets.append(line.strip()[2:].strip().strip("`"))
    return bullets


def _section_body(text: str, heading: str) -> str:
    """Extract the body content of a markdown section."""
    lines = text.splitlines()
    start_idx: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() == heading:
            start_idx = idx + 1
            break
    if start_idx is None:
        return ""
    body: list[str] = []
    for line in lines[start_idx:]:
        if line.strip().startswith("## "):
            break
        body.append(line)
    return "\n".join(body)


def _markdown_code_tokens(text: str) -> set[str]:
    """Extract all inline code tokens from markdown text."""
    return {match.group(1) for match in re.finditer(r"`([^`]+)`", text)}


def _json_string_values(text: str, key: str) -> set[str]:
    """Extract all string values for a given JSON key."""
    pattern = rf'"{re.escape(key)}"\s*:\s*"([^"]+)"'
    return {match.group(1) for match in re.finditer(pattern, text)}


def _json_object_keys(text: str) -> set[str]:
    """Extract all keys from JSON object notation."""
    return {match.group(1) for match in re.finditer(r'"([^"]+)"\s*:', text)}


def _existing_paths(paths: list[Path]) -> list[str]:
    """Filter paths to only those that exist on disk."""
    return [str(p) for p in paths if p.exists()]
