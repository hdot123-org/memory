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
import shutil
import stat
import string
import sys
from datetime import datetime, timezone
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


def default_storage_root() -> Path:
    """Return the stable memory storage root used by the hook wrapper."""
    return Path(os.environ.get("MEMORY_HOOK_GLOBAL_STATE_ROOT", "~/.memory-core")).expanduser()


def wrapper_path(codex_home: Path) -> Path:
    """Return the stable global wrapper path for Codex hooks."""
    return codex_home / "bin" / "memory-hook"


def _looks_like_path(command: str) -> bool:
    return command.startswith("~") or "/" in command


def _resolve_installed_command(command: str, warnings: list[str], *, label: str) -> str | None:
    if _looks_like_path(command):
        candidate = Path(command).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        warnings.append(f"{label} command not found: {command}")
        return None

    resolved = shutil.which(command)
    if resolved:
        return resolved

    warnings.append(
        f"{label} command not found: {command}; "
        f"install memory-core or pass --{label.replace('_', '-').replace(' ', '-')}-command /absolute/path"
    )
    return None


def resolve_gateway_command(gateway_command: str, warnings: list[str]) -> str | None:
    """Resolve the gateway executable to a stable absolute path."""
    return _resolve_installed_command(gateway_command, warnings, label="gateway")


def resolve_init_command(init_command: str, warnings: list[str]) -> str | None:
    """Resolve the project initializer executable to a stable absolute path."""
    return _resolve_installed_command(init_command, warnings, label="init")


def _backup_existing_file(path: Path) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = path.with_name(f"{path.name}.bak.{timestamp}")
    suffix = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.bak.{timestamp}.{suffix:02d}")
        suffix += 1
    shutil.copy2(path, backup_path)
    return backup_path


def render_wrapper(
    storage_root: Path,
    *,
    gateway_command: str = "memory-hook-gateway",
    init_command: str = "memory-init",
) -> str:
    """Render the shell wrapper installed into ``~/.codex/bin``.

    The wrapper records the original working directory, ensures the current
    Codex project has project-local memory files, then calls the installed
    gateway command.  It does not point at a source checkout or worktree.
    """
    quoted_storage = shlex.quote(str(storage_root.expanduser()))
    quoted_gateway = shlex.quote(gateway_command)
    quoted_init = shlex.quote(init_command)
    from memory_core.constants import CURRENT_MEMORY_VERSION as _VER

    # Use string.Template for safer variable substitution
    template = string.Template("""#!/bin/sh
set -eu

MEMORY_HOOK_GLOBAL_STATE_ROOT=$quoted_storage
MEMORY_HOOK_GATEWAY=${MEMORY_HOOK_GATEWAY:-$quoted_gateway}
MEMORY_HOOK_PROJECT_INIT=${MEMORY_HOOK_PROJECT_INIT:-$quoted_init}
ORIGINAL_CWD=${PWD:-}
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

export PATH
export MEMORY_HOOK_ORIGINAL_CWD="$ORIGINAL_CWD"
export MEMORY_HOOK_GLOBAL_STATE_ROOT
export MEMORY_HOOK_FORCE="${MEMORY_HOOK_FORCE:-1}"
export MEMORY_HOOK_PREFER_EXTERNAL_CWD="${MEMORY_HOOK_PREFER_EXTERNAL_CWD:-1}"
export MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE="${MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE:-1}"
export HOME="${HOME:-$MEMORY_HOOK_GLOBAL_STATE_ROOT/..}"

mkdir -p "$MEMORY_HOOK_GLOBAL_STATE_ROOT/memory/system" 2>/dev/null || true
PROJECT_CWD="$ORIGINAL_CWD"
if [ -n "$ORIGINAL_CWD" ] && [ -d "$ORIGINAL_CWD" ]; then
    GIT_ROOT=$(git -C "$ORIGINAL_CWD" rev-parse --show-toplevel 2>/dev/null || true)
    if [ -n "$GIT_ROOT" ]; then
        PROJECT_CWD="$GIT_ROOT"
    fi
fi

HOME_ROOT=$(cd "${HOME:-$MEMORY_HOOK_GLOBAL_STATE_ROOT/..}" 2>/dev/null && pwd -P || true)
PROJECT_CWD_RESOLVED=$(cd "$PROJECT_CWD" 2>/dev/null && pwd -P || true)
if [ -n "$HOME_ROOT" ] && [ -n "$PROJECT_CWD_RESOLVED" ] && [ "$PROJECT_CWD_RESOLVED" = "$HOME_ROOT" ]; then
    printf '{}\\n'
    exit 0
fi

# M3: Anti-pollution - source repo gets readonly context-package instead of noop
if [ -n "$PROJECT_CWD" ] && [ -d "$PROJECT_CWD" ]; then
    if [ -f "$PROJECT_CWD/memory_core/tools/memory_hook_gateway.py" ] || [ -f "$PROJECT_CWD/memory_core/tools/factory_global_hooks.py" ] || [ -f "$PROJECT_CWD/memory_core/tools/codex_global_hooks.py" ]; then
        export READONLY=1
        exec "$MEMORY_HOOK_GATEWAY" "$@"
    fi
fi

# M3: Remove || true to make init failures visible with structured error output
if [ -n "$PROJECT_CWD" ] && [ -d "$PROJECT_CWD" ] && [ ! -d "$PROJECT_CWD/memory/system" ]; then
    if ! "$MEMORY_HOOK_PROJECT_INIT" --target "$PROJECT_CWD" --host codex \\
        >/dev/null 2>>"$MEMORY_HOOK_GLOBAL_STATE_ROOT/memory/system/errors.log"; then
        echo '{"error": "project_init_failed", "message": "Failed to initialize project memory"}' >&2
        exit 1
    fi
fi

# Version sync: patch ownership.toml if project version is stale
if [ -n "$PROJECT_CWD" ] && [ -d "$PROJECT_CWD/memory/system" ] && [ -f "$PROJECT_CWD/memory/system/ownership.toml" ]; then
    _OWNERSHIP_VER=$(grep -o '^memory_version[[:space:]]*=[[:space:]]*"[^"]*"' "$PROJECT_CWD/memory/system/ownership.toml" 2>/dev/null | grep -o '"[^"]*"$$' | tr -d '"' || true)
    if [ -n "$_OWNERSHIP_VER" ] && [ "$_OWNERSHIP_VER" != "$memory_version" ]; then
        sed -i.bak 's/^memory_version[[:space:]]*=.*/memory_version = "$memory_version"/' "$PROJECT_CWD/memory/system/ownership.toml" 2>/dev/null && rm -f "$PROJECT_CWD/memory/system/ownership.toml.bak" 2>/dev/null || true
    fi
fi

exec "$MEMORY_HOOK_GATEWAY" "$@"
""")

    return template.safe_substitute(
        quoted_storage=quoted_storage,
        quoted_gateway=quoted_gateway,
        quoted_init=quoted_init,
        memory_version=_VER,
    )


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
    storage_root: Path | None = None,
    gateway_command: str = "memory-hook-gateway",
    init_command: str = "memory-init",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install the global Codex memory hook wrapper and hooks.json entries."""
    resolved_codex_home = (codex_home or default_codex_home()).expanduser()
    resolved_storage_root = (storage_root or default_storage_root()).expanduser()
    hook_wrapper = wrapper_path(resolved_codex_home)
    hooks_path = resolved_codex_home / "hooks.json"
    warnings: list[str] = []
    resolved_gateway_command = resolve_gateway_command(gateway_command, warnings)
    resolved_init_command = resolve_init_command(init_command, warnings)

    wrapper_content = (
        render_wrapper(
            resolved_storage_root,
            gateway_command=resolved_gateway_command,
            init_command=resolved_init_command,
        )
        if resolved_gateway_command and resolved_init_command
        else ""
    )
    desired = desired_codex_hooks(hook_wrapper, timeout=timeout)
    existing = _load_hooks_json(hooks_path, warnings)
    merged = merge_codex_hooks(existing, desired)
    rendered_hooks = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"

    result: dict[str, Any] = {
        "success": True,
        "dry_run": dry_run,
        "codex_home": str(resolved_codex_home),
        "storage_root": str(resolved_storage_root),
        "gateway_command": resolved_gateway_command or gateway_command,
        "init_command": resolved_init_command or init_command,
        "wrapper": str(hook_wrapper),
        "hooks_json": str(hooks_path),
        "created": [],
        "updated": [],
        "skipped": [],
        "backups": [],
        "warnings": warnings,
    }

    if not resolved_gateway_command or not resolved_init_command:
        result["success"] = False
        return result

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
    if hooks_path.exists() and existing_hooks_text != rendered_hooks:
        backup_path = _backup_existing_file(hooks_path)
        result["backups"].append(str(backup_path))
    hooks_path.write_text(rendered_hooks, encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Codex App global memory hooks.")
    parser.add_argument("command", choices=("install",), help="Operation to perform.")
    parser.add_argument("--codex-home", type=Path, default=None, help="Codex config directory (default: ~/.codex).")
    parser.add_argument("--storage-root", type=Path, default=None, help="Stable global state root for Codex hook indexes (default: ~/.memory-core).")
    parser.add_argument("--gateway-command", default="memory-hook-gateway", help="Installed gateway command used by the hook wrapper.")
    parser.add_argument("--init-command", default="memory-init", help="Installed project initializer command used by the hook wrapper.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Codex hook timeout in seconds.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing files.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    args = parser.parse_args(argv)

    result = install_codex_hooks(
        codex_home=args.codex_home,
        storage_root=args.storage_root,
        gateway_command=args.gateway_command,
        init_command=args.init_command,
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
