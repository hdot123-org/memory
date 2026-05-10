#!/usr/bin/env python3
"""Install Codex App global hooks for the memory gateway.

Codex stores hook configuration under ``~/.codex/hooks.json``.  This module
keeps that file host-owned and project-agnostic: the global hook calls one
stable wrapper, and the memory runtime decides how to handle project identity.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import stat
import sys
from pathlib import Path
from typing import Any

CODEX_HOOK_EVENTS: tuple[tuple[str, str], ...] = (
    ("SessionStart", "session-start"),
    ("UserPromptSubmit", "prompt-submit"),
    ("Stop", "stop"),
)

DEFAULT_TIMEOUT_SECONDS = 10

_MEMORY_COMMAND_MARKERS = (
    "memory_hook_gateway.py",
    "memory-hook-gateway",
    "memory-hook --host codex",
)


def default_codex_home() -> Path:
    """Return the Codex configuration directory."""
    return Path(os.environ.get("CODEX_HOME", "~/.codex")).expanduser()


def default_memory_repo() -> Path:
    """Return the repository root that contains this module."""
    return Path(__file__).resolve().parents[2]


def wrapper_path(codex_home: Path) -> Path:
    """Return the stable global wrapper path for Codex hooks."""
    return codex_home / "bin" / "memory-hook"


def render_wrapper(memory_repo: Path, python_bin: str = "python3") -> str:
    """Render the shell wrapper installed into ``~/.codex/bin``.

    The wrapper records the original working directory before switching into
    the stable memory repository.  The gateway then uses that original cwd for
    project identity while still writing artifacts under the memory repo.
    """
    quoted_repo = shlex.quote(str(memory_repo.expanduser().resolve()))
    quoted_python = shlex.quote(python_bin)
    return f"""#!/bin/sh
set -eu

MEMORY_REPO={quoted_repo}
PYTHON_BIN=${{PYTHON_BIN:-{quoted_python}}}
ORIGINAL_CWD=${{PWD:-}}

export MEMORY_HOOK_ORIGINAL_CWD="$ORIGINAL_CWD"
export MEMORY_HOOK_FORCE="${{MEMORY_HOOK_FORCE:-1}}"
export MEMORY_HOOK_PREFER_EXTERNAL_CWD="${{MEMORY_HOOK_PREFER_EXTERNAL_CWD:-1}}"
export MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE="${{MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE:-1}}"

cd "$MEMORY_REPO"
exec "$PYTHON_BIN" "$MEMORY_REPO/memory_core/tools/memory_hook_gateway.py" "$@"
"""


def desired_codex_hooks(command_path: Path, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Return the Codex App hooks.json shape for memory hooks."""
    hooks: dict[str, Any] = {}
    for codex_event, gateway_event in CODEX_HOOK_EVENTS:
        hooks[codex_event] = [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{command_path} --host codex --event {gateway_event}",
                        "timeout": timeout,
                    }
                ]
            }
        ]
    return {"hooks": hooks}


def _empty_codex_hooks() -> dict[str, Any]:
    return {"hooks": {}}


def _load_hooks_json(path: Path, warnings: list[str]) -> dict[str, Any]:
    if not path.exists():
        return _empty_codex_hooks()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        warnings.append(f"hooks.json corrupt or unreadable, treated as empty: {exc}")
        return _empty_codex_hooks()
    if not isinstance(loaded, dict):
        warnings.append("hooks.json root is not an object, treated as empty")
        return _empty_codex_hooks()
    if not isinstance(loaded.get("hooks"), dict):
        warnings.append("hooks.json hooks field is missing or non-standard, treated as empty")
        loaded["hooks"] = {}
    return loaded


def _is_memory_hook_command(command: str) -> bool:
    if "--host codex" not in command or "--event" not in command:
        return False
    return any(marker in command for marker in _MEMORY_COMMAND_MARKERS)


def _filter_memory_hooks(groups: Any) -> list[dict[str, Any]]:
    if not isinstance(groups, list):
        return []
    filtered_groups: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_hooks = group.get("hooks")
        if not isinstance(group_hooks, list):
            filtered_groups.append(group)
            continue
        kept_hooks: list[Any] = []
        for hook in group_hooks:
            if not isinstance(hook, dict):
                kept_hooks.append(hook)
                continue
            command = hook.get("command")
            if isinstance(command, str) and _is_memory_hook_command(command):
                continue
            kept_hooks.append(hook)
        if kept_hooks:
            new_group = dict(group)
            new_group["hooks"] = kept_hooks
            filtered_groups.append(new_group)
    return filtered_groups


def merge_codex_hooks(existing: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
    """Merge desired memory hooks while preserving unrelated hooks."""
    merged = dict(existing)
    existing_hooks = merged.get("hooks")
    if not isinstance(existing_hooks, dict):
        existing_hooks = {}
    merged_hooks = dict(existing_hooks)
    desired_hooks = desired.get("hooks", {})
    if not isinstance(desired_hooks, dict):
        desired_hooks = {}

    for codex_event, _gateway_event in CODEX_HOOK_EVENTS:
        preserved = _filter_memory_hooks(merged_hooks.get(codex_event, []))
        desired_groups = desired_hooks.get(codex_event, [])
        if isinstance(desired_groups, list):
            merged_hooks[codex_event] = preserved + desired_groups
    merged["hooks"] = merged_hooks
    return merged


def install_codex_hooks(
    *,
    codex_home: Path | None = None,
    memory_repo: Path | None = None,
    python_bin: str = "python3",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install the global Codex memory hook wrapper and hooks.json entries."""
    resolved_codex_home = (codex_home or default_codex_home()).expanduser()
    resolved_memory_repo = (memory_repo or default_memory_repo()).expanduser()
    hook_wrapper = wrapper_path(resolved_codex_home)
    hooks_path = resolved_codex_home / "hooks.json"
    warnings: list[str] = []

    wrapper_content = render_wrapper(resolved_memory_repo, python_bin=python_bin)
    desired = desired_codex_hooks(hook_wrapper, timeout=timeout)
    existing = _load_hooks_json(hooks_path, warnings)
    merged = merge_codex_hooks(existing, desired)
    rendered_hooks = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"

    result: dict[str, Any] = {
        "success": True,
        "dry_run": dry_run,
        "codex_home": str(resolved_codex_home),
        "memory_repo": str(resolved_memory_repo),
        "wrapper": str(hook_wrapper),
        "hooks_json": str(hooks_path),
        "created": [],
        "updated": [],
        "skipped": [],
        "warnings": warnings,
    }

    existing_wrapper = hook_wrapper.read_text(encoding="utf-8") if hook_wrapper.exists() else None
    existing_hooks_text = hooks_path.read_text(encoding="utf-8") if hooks_path.exists() else None

    if existing_wrapper == wrapper_content:
        result["skipped"].append("wrapper up-to-date")
    elif hook_wrapper.exists():
        result["updated"].append(str(hook_wrapper))
    else:
        result["created"].append(str(hook_wrapper))

    if existing_hooks_text == rendered_hooks:
        result["skipped"].append("hooks.json up-to-date")
    elif hooks_path.exists():
        result["updated"].append(str(hooks_path))
    else:
        result["created"].append(str(hooks_path))

    if dry_run:
        return result

    hook_wrapper.parent.mkdir(parents=True, exist_ok=True)
    hook_wrapper.write_text(wrapper_content, encoding="utf-8")
    current_mode = hook_wrapper.stat().st_mode
    hook_wrapper.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    hooks_path.write_text(rendered_hooks, encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Codex App global memory hooks.")
    parser.add_argument("command", choices=("install",), help="Operation to perform.")
    parser.add_argument("--codex-home", type=Path, default=None, help="Codex config directory (default: ~/.codex).")
    parser.add_argument("--memory-repo", type=Path, default=None, help="Stable memory repository path.")
    parser.add_argument("--python-bin", default="python3", help="Python executable used by the hook wrapper.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Codex hook timeout in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing files.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    result = install_codex_hooks(
        codex_home=args.codex_home,
        memory_repo=args.memory_repo,
        python_bin=args.python_bin,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Codex hooks installed: {result['hooks_json']}")
        print(f"Wrapper: {result['wrapper']}")
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
