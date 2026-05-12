#!/usr/bin/env python3
"""Install Factory Droid global hooks for the memory gateway.

Factory stores user-level hook configuration in ``~/.factory/settings.json``.
This module keeps that file host-owned and project-agnostic: the global hook
calls one stable wrapper, and the memory runtime decides project identity from
Factory's hook payload/current project directory.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

FACTORY_HOOK_EVENTS: tuple[tuple[str, str], ...] = (
    ("SessionStart", "session-start"),
    ("UserPromptSubmit", "prompt-submit"),
    ("Stop", "stop"),
    ("Notification", "notification"),
)

DEFAULT_TIMEOUT_SECONDS = 10

_MEMORY_COMMAND_MARKERS = (
    "memory_hook_gateway.py",
    "memory-hook-gateway",
    "memory-hook --host factory",
)


def default_factory_home() -> Path:
    """Return the Factory user configuration directory."""
    return Path(os.environ.get("FACTORY_HOME", "~/.factory")).expanduser()


def default_storage_root() -> Path:
    """Return the stable memory storage root used by the hook wrapper."""
    return Path(os.environ.get("MEMORY_HOOK_GLOBAL_STATE_ROOT", "~/.memory-core")).expanduser()


def wrapper_path(factory_home: Path) -> Path:
    """Return the stable global wrapper path for Factory hooks."""
    return factory_home / "bin" / "memory-hook"


def settings_path(factory_home: Path) -> Path:
    """Return the Factory user settings file path."""
    return factory_home / "settings.json"


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
    """Render the shell wrapper installed into ``~/.factory/bin``."""
    quoted_storage = shlex.quote(str(storage_root.expanduser()))
    quoted_gateway = shlex.quote(gateway_command)
    quoted_init = shlex.quote(init_command)
    return f"""#!/bin/sh
set -eu

MEMORY_HOOK_GLOBAL_STATE_ROOT={quoted_storage}
MEMORY_HOOK_GATEWAY=${{MEMORY_HOOK_GATEWAY:-{quoted_gateway}}}
MEMORY_HOOK_PROJECT_INIT=${{MEMORY_HOOK_PROJECT_INIT:-{quoted_init}}}
ORIGINAL_CWD=${{FACTORY_PROJECT_DIR:-${{PWD:-}}}}
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${{PATH:-}}"

export PATH
export MEMORY_HOOK_ORIGINAL_CWD="$ORIGINAL_CWD"
export MEMORY_HOOK_GLOBAL_STATE_ROOT
export MEMORY_HOOK_FORCE="${{MEMORY_HOOK_FORCE:-1}}"
export MEMORY_HOOK_PREFER_EXTERNAL_CWD="${{MEMORY_HOOK_PREFER_EXTERNAL_CWD:-1}}"
export MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE="${{MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE:-1}}"

mkdir -p "$MEMORY_HOOK_GLOBAL_STATE_ROOT/memory/system" 2>/dev/null || true
PROJECT_CWD="$ORIGINAL_CWD"
if [ -n "$ORIGINAL_CWD" ] && [ -d "$ORIGINAL_CWD" ]; then
    GIT_ROOT=$(git -C "$ORIGINAL_CWD" rev-parse --show-toplevel 2>/dev/null || true)
    if [ -n "$GIT_ROOT" ]; then
        PROJECT_CWD="$GIT_ROOT"
    fi
fi

# Anti-pollution: Skip memory-core source repo (detected by marker files) regardless of .memory existence
if [ -n "$PROJECT_CWD" ] && [ -d "$PROJECT_CWD" ]; then
    if [ -f "$PROJECT_CWD/memory_core/tools/memory_hook_gateway.py" ] || [ -f "$PROJECT_CWD/memory_core/tools/factory_global_hooks.py" ] || [ -f "$PROJECT_CWD/memory_core/tools/codex_global_hooks.py" ]; then
        printf '{{}}\n'
        exit 0
    fi
fi

if [ -n "$PROJECT_CWD" ] && [ -d "$PROJECT_CWD" ] && [ ! -d "$PROJECT_CWD/.memory" ]; then
    "$MEMORY_HOOK_PROJECT_INIT" --target "$PROJECT_CWD" --host factory \
        >/dev/null 2>>"$MEMORY_HOOK_GLOBAL_STATE_ROOT/memory/system/errors.log" || true
fi

exec "$MEMORY_HOOK_GATEWAY" "$@"
"""


def desired_factory_hooks(command_path: Path, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Return the Factory settings hooks shape for memory hooks."""
    hooks: dict[str, Any] = {}
    for factory_event, gateway_event in FACTORY_HOOK_EVENTS:
        hooks[factory_event] = [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{command_path} --host factory --event {gateway_event}",
                        "timeout": timeout,
                    }
                ]
            }
        ]
    return {"hooks": hooks}


def _empty_factory_settings() -> dict[str, Any]:
    return {"hooks": {}}


def _load_settings_json(path: Path, warnings: list[str]) -> dict[str, Any]:
    if not path.exists():
        return _empty_factory_settings()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        warnings.append(f"settings.json corrupt or unreadable, treated as empty: {exc}")
        return _empty_factory_settings()
    if not isinstance(loaded, dict):
        warnings.append("settings.json root is not an object, treated as empty")
        return _empty_factory_settings()
    if not isinstance(loaded.get("hooks"), dict):
        loaded["hooks"] = {}
    return loaded


def _is_memory_hook_command(command: str) -> bool:
    if "--host factory" not in command or "--event" not in command:
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


def merge_factory_settings(existing: dict[str, Any], desired: dict[str, Any]) -> dict[str, Any]:
    """Merge desired memory hooks while preserving unrelated settings and hooks."""
    merged = dict(existing)
    existing_hooks = merged.get("hooks")
    if not isinstance(existing_hooks, dict):
        existing_hooks = {}

    merged_hooks: dict[str, Any] = dict(existing_hooks)
    for event_name, desired_groups in desired.get("hooks", {}).items():
        kept_groups = _filter_memory_hooks(merged_hooks.get(event_name, []))
        merged_hooks[event_name] = kept_groups + desired_groups

    merged["hooks"] = merged_hooks
    return merged


def install_factory_hooks(
    *,
    factory_home: Path | None = None,
    storage_root: Path | None = None,
    gateway_command: str = "memory-hook-gateway",
    init_command: str = "memory-init",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install Factory user-level hooks for memory-core."""
    warnings: list[str] = []
    backups: list[str] = []
    factory_home = (factory_home or default_factory_home()).expanduser()
    storage_root = (storage_root or default_storage_root()).expanduser()
    settings_file = settings_path(factory_home)
    wrapper = wrapper_path(factory_home)

    resolved_gateway = resolve_gateway_command(gateway_command, warnings)
    resolved_init = resolve_init_command(init_command, warnings)
    if resolved_gateway is None or resolved_init is None:
        return {
            "success": False,
            "warnings": warnings,
            "factory_home": str(factory_home),
            "settings_path": str(settings_file),
            "wrapper_path": str(wrapper),
            "backups": backups,
        }

    wrapper_content = render_wrapper(
        storage_root,
        gateway_command=resolved_gateway,
        init_command=resolved_init,
    )
    desired = desired_factory_hooks(wrapper, timeout=timeout)
    existing = _load_settings_json(settings_file, warnings)
    merged = merge_factory_settings(existing, desired)

    result: dict[str, Any] = {
        "success": True,
        "dry_run": dry_run,
        "warnings": warnings,
        "factory_home": str(factory_home),
        "settings_path": str(settings_file),
        "wrapper_path": str(wrapper),
        "storage_root": str(storage_root),
        "gateway_command": resolved_gateway,
        "init_command": resolved_init,
        "backups": backups,
        "settings": merged if dry_run else None,
    }

    if dry_run:
        return result

    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(wrapper_content, encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)

    settings_file.parent.mkdir(parents=True, exist_ok=True)
    if settings_file.exists():
        backups.append(str(_backup_existing_file(settings_file)))
    settings_file.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Factory Droid global memory hooks")
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("install", help="Install/update Factory user-level memory hooks")
    install.add_argument("--factory-home", type=Path, default=None, help="Factory config directory (default: ~/.factory)")
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

    result = install_factory_hooks(
        factory_home=args.factory_home,
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
            print(f"{action} Factory memory hook wrapper: {result['wrapper_path']}")
            print(f"{action} Factory settings: {result['settings_path']}")
        else:
            print("Factory memory hook install failed", file=sys.stderr)
        for warning in result.get("warnings", []):
            print(f"warning: {warning}", file=sys.stderr)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
