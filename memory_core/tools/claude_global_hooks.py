#!/usr/bin/env python3
"""Install Claude global hooks for the memory gateway.

Claude stores hook configuration under ``~/.claude/hooks.json``. This module
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

CLAUDE_HOOK_EVENTS: tuple[tuple[str, str], ...] = (
    ("SessionStart", "session-start"),
    ("UserPromptSubmit", "prompt-submit"),
    ("Notification", "notification"),
    ("Stop", "stop"),
)

DEFAULT_TIMEOUT_SECONDS = 10

_MEMORY_COMMAND_MARKERS = (
    "memory_hook_gateway.py",
    "memory-hook-gateway",
    "memory-hook --host claude",
)


def default_claude_home() -> Path:
    """Return the Claude configuration directory."""
    return Path(os.environ.get("CLAUDE_HOME", "~/.claude")).expanduser()


def default_storage_root() -> Path:
    """Return the stable memory storage root used by the hook wrapper."""
    return Path(os.environ.get("MEMORY_HOOK_GLOBAL_STATE_ROOT", "~/.memory-core")).expanduser()


def wrapper_path(claude_home: Path) -> Path:
    """Return the stable global wrapper path for Claude hooks."""
    return claude_home / "bin" / "memory-hook"


def hooks_path(claude_home: Path) -> Path:
    """Return the Claude hooks.json file path."""
    return claude_home / "hooks.json"


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
    """Render the shell wrapper installed into ``~/.claude/bin``.

    The wrapper records the original working directory, ensures the current
    Claude project has project-local memory files, then calls the installed
    gateway command. It does not point at a source checkout or worktree.
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
    if [ -f "$PROJECT_CWD/memory_core/tools/memory_hook_gateway.py" ] || [ -f "$PROJECT_CWD/memory_core/tools/factory_global_hooks.py" ] || [ -f "$PROJECT_CWD/memory_core/tools/codex_global_hooks.py" ] || [ -f "$PROJECT_CWD/memory_core/tools/claude_global_hooks.py" ]; then
        export READONLY=1
        exec "$MEMORY_HOOK_GATEWAY" "$@"
    fi
fi

# M3: Remove || true to make init failures visible with structured error output
if [ -n "$PROJECT_CWD" ] && [ -d "$PROJECT_CWD" ] && [ ! -d "$PROJECT_CWD/memory/system" ]; then
    if ! "$MEMORY_HOOK_PROJECT_INIT" --target "$PROJECT_CWD" --host claude \\
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


def desired_claude_hooks(command_path: Path, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Return the Claude hooks.json shape for memory hooks.

    Claude uses a flat list format: {"hooks": [{"event": "...", "command": "...", "stdin": true}, ...]}
    """
    hooks: list[dict[str, Any]] = []
    for claude_event, gateway_event in CLAUDE_HOOK_EVENTS:
        hooks.append({
            "event": claude_event,
            "command": f"{command_path} --host claude --event {gateway_event}",
            "stdin": True,
        })
    return {"hooks": hooks}


def _empty_claude_hooks() -> dict[str, Any]:
    return {"hooks": []}


def _load_hooks_json(path: Path, warnings: list[str]) -> dict[str, Any]:
    if not path.exists():
        return _empty_claude_hooks()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        warnings.append(f"hooks.json corrupt or unreadable, treated as empty: {exc}")
        return _empty_claude_hooks()
    if not isinstance(loaded, dict):
        warnings.append("hooks.json root is not an object, treated as empty")
        return _empty_claude_hooks()
    if not isinstance(loaded.get("hooks"), list):
        warnings.append("hooks.json hooks field is missing or non-standard, treated as empty")
        loaded["hooks"] = []
    return loaded


def _is_memory_hook_command(command: str) -> bool:
    if "--host claude" not in command or "--event" not in command:
        return False
    return any(marker in command for marker in _MEMORY_COMMAND_MARKERS)


def _filter_memory_hooks(hooks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter out old memory hook entries from the hooks list."""
    filtered: list[dict[str, Any]] = []
    for hook in hooks:
        if not isinstance(hook, dict):
            filtered.append(hook)
            continue
        command = hook.get("command")
        if isinstance(command, str) and _is_memory_hook_command(command):
            continue
        filtered.append(hook)
    return filtered


def merge_claude_hooks(existing: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
    """Merge desired memory hooks while preserving unrelated hooks.

    Claude uses a flat list format, so we filter existing memory hooks
    and append the desired ones.
    """
    merged = dict(existing)
    existing_hooks = merged.get("hooks")
    if not isinstance(existing_hooks, list):
        existing_hooks = []

    # Filter out old memory hooks from existing
    filtered_hooks = _filter_memory_hooks(existing_hooks)

    # Append desired hooks
    desired_hooks = desired.get("hooks", [])
    if isinstance(desired_hooks, list):
        filtered_hooks.extend(desired_hooks)

    merged["hooks"] = filtered_hooks
    return merged


def install_claude_hooks(
    *,
    claude_home: Path | None = None,
    storage_root: Path | None = None,
    gateway_command: str = "memory-hook-gateway",
    init_command: str = "memory-init",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install the global Claude memory hook wrapper and hooks.json entries."""
    resolved_claude_home = (claude_home or default_claude_home()).expanduser()
    resolved_storage_root = (storage_root or default_storage_root()).expanduser()
    hook_wrapper = wrapper_path(resolved_claude_home)
    hooks_file = hooks_path(resolved_claude_home)
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
    desired = desired_claude_hooks(hook_wrapper, timeout=timeout)
    existing = _load_hooks_json(hooks_file, warnings)
    merged = merge_claude_hooks(existing, desired)
    rendered_hooks = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"

    result: dict[str, Any] = {
        "success": True,
        "dry_run": dry_run,
        "claude_home": str(resolved_claude_home),
        "storage_root": str(resolved_storage_root),
        "gateway_command": resolved_gateway_command or gateway_command,
        "init_command": resolved_init_command or init_command,
        "wrapper": str(hook_wrapper),
        "hooks_json": str(hooks_file),
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
    existing_hooks_text = hooks_file.read_text(encoding="utf-8") if hooks_file.exists() else None

    if existing_wrapper == wrapper_content:
        result["skipped"].append("wrapper up-to-date")
    elif hook_wrapper.exists():
        result["updated"].append(str(hook_wrapper))
    else:
        result["created"].append(str(hook_wrapper))

    if existing_hooks_text == rendered_hooks:
        result["skipped"].append("hooks.json up-to-date")
    elif hooks_file.exists():
        result["updated"].append(str(hooks_file))
    else:
        result["created"].append(str(hooks_file))

    if dry_run:
        return result

    hook_wrapper.parent.mkdir(parents=True, exist_ok=True)
    hook_wrapper.write_text(wrapper_content, encoding="utf-8")
    current_mode = hook_wrapper.stat().st_mode
    hook_wrapper.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    hooks_file.parent.mkdir(parents=True, exist_ok=True)
    if hooks_file.exists() and existing_hooks_text != rendered_hooks:
        backup_path = _backup_existing_file(hooks_file)
        result["backups"].append(str(backup_path))
    hooks_file.write_text(rendered_hooks, encoding="utf-8")
    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Claude global memory hooks")
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("install", help="Install/update Claude global memory hooks")
    install.add_argument("--claude-home", type=Path, default=None, help="Claude config directory (default: ~/.claude)")
    install.add_argument("--storage-root", type=Path, default=None, help="Global memory state root (default: ~/.memory-core)")
    install.add_argument("--gateway-command", default="memory-hook-gateway", help="Gateway command or absolute path")
    install.add_argument("--init-command", default="memory-init", help="Project init command or absolute path")
    install.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Hook timeout in seconds")
    install.add_argument("--dry-run", action="store_true", help="Preview changes without writing files")
    install.add_argument("--json", action="store_true", help="Print JSON result")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.command != "install":
        raise AssertionError(args.command)

    result = install_claude_hooks(
        claude_home=args.claude_home,
        storage_root=args.storage_root,
        gateway_command=args.gateway_command,
        init_command=args.init_command,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["success"]:
            action = "Would install" if result.get("dry_run") else "Installed"
            print(f"{action} Claude memory hook wrapper: {result['wrapper']}")
            print(f"{action} Claude hooks: {result['hooks_json']}")
        else:
            print("Claude memory hook install failed", file=sys.stderr)
        for warning in result.get("warnings", []):
            print(f"warning: {warning}", file=sys.stderr)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
