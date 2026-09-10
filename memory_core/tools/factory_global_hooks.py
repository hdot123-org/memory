#!/usr/bin/env python3.12
"""Install Factory Droid global hooks for the memory gateway.

Factory stores user-level hook configuration in ``~/.factory/hooks.json``.
This module keeps that file host-owned and project-agnostic: the global hook
calls one stable wrapper, and the memory runtime decides project identity from
Factory's hook payload/current project directory.

settings.json is maintained for backward compatibility but the hooks key is
deprecated since 2026-08-17 (hooks.json is the real registration point).
"""

import argparse
import json
import os
import shlex
import shutil
import stat
import string
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

FACTORY_HOOK_EVENTS: tuple[tuple[str, str], ...] = (
    ("SessionStart", "session-start"),
    ("UserPromptSubmit", "prompt-submit"),
    ("Stop", "stop"),
    ("Notification", "notification"),
    ("PreToolUse", "pre-tool-use"),
    ("PostToolUse", "post-tool-use"),
    ("SubagentStop", "subagent-stop"),
    ("PreCompact", "pre-compact"),
    ("SessionEnd", "session-end"),
)

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
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
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
    # Resolve bare gateway_command to absolute path via shutil.which() to
    # prevent intermittent 'exec: memory-hook-gateway: not found' errors
    # when the daemon's execution context doesn't resolve PATH correctly.
    # If resolution fails, fall back to the bare name (preserve existing
    # behavior). MEMORY_HOOK_GATEWAY env var override still takes precedence.
    resolved_gateway = gateway_command
    if not _looks_like_path(gateway_command):
        which_result = shutil.which(gateway_command)
        if which_result is not None:
            resolved_gateway = which_result

    quoted_storage = shlex.quote(str(storage_root.expanduser()))
    quoted_gateway = shlex.quote(resolved_gateway)
    quoted_init = shlex.quote(init_command)

    # Import version at render time so the baked-in version is always current
    from memory_core.constants import CURRENT_MEMORY_VERSION as _VER

    # Use string.Template for safer variable substitution
    template = string.Template("""#!/bin/sh
set -eu

MEMORY_HOOK_GLOBAL_STATE_ROOT=$quoted_storage
MEMORY_HOOK_GATEWAY=${MEMORY_HOOK_GATEWAY:-$quoted_gateway}
MEMORY_HOOK_PROJECT_INIT=${MEMORY_HOOK_PROJECT_INIT:-$quoted_init}
ORIGINAL_CWD=${FACTORY_PROJECT_DIR:-${PWD:-}}
PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

export PATH
export MEMORY_HOOK_ORIGINAL_CWD="$ORIGINAL_CWD"
export MEMORY_HOOK_GLOBAL_STATE_ROOT
export MEMORY_HOOK_FORCE="${MEMORY_HOOK_FORCE:-1}"
export MEMORY_HOOK_PREFER_EXTERNAL_CWD="${MEMORY_HOOK_PREFER_EXTERNAL_CWD:-1}"
export MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE="${MEMORY_HOOK_RECORD_PROJECT_LIFECYCLE:-1}"
export HOME="${HOME:-$MEMORY_HOOK_GLOBAL_STATE_ROOT/..}"

# Parse --event value (POSIX-compliant, no bash arrays)
# hooks.json 实测形态: $1=--host $2=factory $3=--event $4=<事件名>
EVENT_NAME=""
_prev_was_event=0
for _arg in "$$@"; do
    case "$_arg" in
        --event=*)
            EVENT_NAME="$${_arg#--event=}"
            ;;
        --event)
            _prev_was_event=1
            ;;
        *)
            if [ "$_prev_was_event" -eq 1 ]; then
                EVENT_NAME="$_arg"
            fi
            _prev_was_event=0
            ;;
    esac
done

mkdir -p "$MEMORY_HOOK_GLOBAL_STATE_ROOT/memory/system" 2>/dev/null || true
PROJECT_CWD="$ORIGINAL_CWD"
if [ -n "$ORIGINAL_CWD" ] && [ -d "$ORIGINAL_CWD" ]; then
    GIT_ROOT=$(git -C "$ORIGINAL_CWD" rev-parse --show-toplevel 2>/dev/null || true)
    if [ -n "$GIT_ROOT" ]; then
        PROJECT_CWD="$GIT_ROOT"
    fi
fi

HOME_ROOT=$(cd "$${HOME:-$MEMORY_HOOK_GLOBAL_STATE_ROOT/..}" 2>/dev/null && pwd -P || true)
PROJECT_CWD_RESOLVED=$(cd "$PROJECT_CWD" 2>/dev/null && pwd -P || true)
if [ -n "$HOME_ROOT" ] && [ -n "$PROJECT_CWD_RESOLVED" ] && [ "$PROJECT_CWD_RESOLVED" = "$HOME_ROOT" ]; then
    printf '{}\\n'
    exit 0
fi

# Export PROJECT_CWD before READONLY checks to ensure it's available for source repo detection
export MEMORY_HOOK_PROJECT_CWD="$PROJECT_CWD"

# M3: Anti-pollution - source repo gets readonly context-package instead of noop
if [ -n "$PROJECT_CWD" ] && [ -d "$PROJECT_CWD" ]; then
    if [ -f "$PROJECT_CWD/memory_core/tools/memory_hook_gateway.py" ] || [ -f "$PROJECT_CWD/memory_core/tools/factory_global_hooks.py" ] || [ -f "$PROJECT_CWD/memory_core/ownership.py" ]; then
        export READONLY=1
        exec "$MEMORY_HOOK_GATEWAY" "$$@"
    fi
fi

# ============================================================================
# NESTED REPO PROBE (M1-2): Four-level routing probe
# ============================================================================
# Triggered only when ALL five conditions are met:
#   1. GIT_ROOT is empty (upward normalization failed)
#   2. CWD has no .git (not a real repo, even dataless/unreadable)
#   3. No consent marker (allow_non_git=true)
#   4. CWD is not $$HOME exact match (HOME guard already ran)
#   5. Escape hatch not set (MEMORY_HOOK_DISABLE_DOWNWARD_PROBE != 1)

NESTED_REPO_PROBE_ENABLED=0
if [ -z "$${GIT_ROOT:-}" ] && \\
   [ ! -e "$PROJECT_CWD/.git" ] && \\
   [ "$${MEMORY_HOOK_DISABLE_DOWNWARD_PROBE:-0}" != "1" ]; then

    # Check consent marker (anchored regex)
    CONSENT_MARKER=""
    if [ -f "$PROJECT_CWD/memory/system/ownership.toml" ]; then
        if grep -q '^[[:space:]]*allow_non_git[[:space:]]*=[[:space:]]*true' "$PROJECT_CWD/memory/system/ownership.toml" 2>/dev/null; then
            CONSENT_MARKER="1"
        fi
    fi
    if [ -z "$CONSENT_MARKER" ] && [ -f "$PROJECT_CWD/memory/system/manifest.json" ]; then
        if grep -q '"allow_non_git"[[:space:]]*:[[:space:]]*true' "$PROJECT_CWD/memory/system/manifest.json" 2>/dev/null; then
            CONSENT_MARKER="1"
        fi
    fi

    if [ -z "$CONSENT_MARKER" ]; then
        NESTED_REPO_PROBE_ENABLED=1
    fi
fi

if [ "$NESTED_REPO_PROBE_ENABLED" -eq 1 ]; then
    # Phase 1: Candidate detection (stat gate + rev-parse confirm, skip symlinks)
    # Scan ALL candidates (no cap-at-2) so initialized-child priority works for ≥3 (VAL-WRAP-019 ≥3 case)
    NESTED_COUNT=0
    NESTED_CANDIDATES=""
    NESTED_CONFIRMED_ROOT=""

    for _child in "$PROJECT_CWD"/*/; do
        # Strip trailing slash: [ -L "path/" ] follows the symlink and
        # always reports false, defeating symlink exclusion (VAL-WRAP-013)
        _child="$${_child%/}"
        [ -d "$_child" ] || continue
        [ -L "$_child" ] && continue  # Skip symlinks
        [ -e "$_child/.git" ] || continue  # Stat gate
        # rev-parse confirm: dangling/corrupt .git excluded from candidates (VAL-WRAP-008)
        _confirmed_root=$$(git -C "$_child" rev-parse --show-toplevel 2>/dev/null || true)
        [ -n "$_confirmed_root" ] || continue

        NESTED_COUNT=$$((NESTED_COUNT + 1))
        NESTED_CONFIRMED_ROOT="$$_confirmed_root"
        if [ -z "$NESTED_CANDIDATES" ]; then
            NESTED_CANDIDATES="$$_child"
        else
            # Use newline separator to support paths with spaces
            NESTED_CANDIDATES="$$NESTED_CANDIDATES
$$_child"
        fi
    done

    # Initialized child priority: run BEFORE cap (works for ≥3 candidates)
    if [ "$NESTED_COUNT" -ge 2 ]; then
        INITIALIZED_CHILD=""
        # Use IFS=newline to iterate, supporting paths with spaces
        OLD_IFS="$$IFS"
        IFS='
'
        for _cand in $$NESTED_CANDIDATES; do
            if [ -d "$_cand/memory/system" ]; then
                INITIALIZED_CHILD="$$_cand"
                break
            fi
        done
        IFS="$$OLD_IFS"
        if [ -n "$INITIALIZED_CHILD" ]; then
            # Initialized child has priority: route to it
            PROJECT_CWD="$$INITIALIZED_CHILD"
            NESTED_COUNT=1
        fi
    elif [ "$NESTED_COUNT" -eq 1 ]; then
        # Exactly one valid candidate: route to its rev-parse confirmed root
        PROJECT_CWD="$$NESTED_CONFIRMED_ROOT"
    fi

    # Three-branch logic
    if [ "$NESTED_COUNT" -eq 0 ]; then
        # 0 candidates: noop, log to errors.log (session-start only, event tag)
        # VAL-WRAP-006 fourth form: missing --event → no log (contract says non-session-start)
        if [ "$EVENT_NAME" = "session-start" ]; then
            printf '[%s] [memory-hook-wrapper] [warn] [event=%s] No nested repos found under %s\\n' \\
                "$(date -u '+%Y-%m-%dT%H:%M:%S%z')" "$EVENT_NAME" "$PROJECT_CWD" \\
                >>"$MEMORY_HOOK_GLOBAL_STATE_ROOT/memory/system/errors.log" 2>/dev/null || true
        fi
        printf '{}\\n'
        exit 0
    elif [ "$NESTED_COUNT" -ge 2 ]; then
        # ≥2 candidates: noop + stderr diagnostics (ALL candidates listed) + errors.log
        # VAL-WRAP-004: stderr must list ALL candidates (no truncation)
        CANDIDATE_LIST=""
        # Use IFS=newline to iterate, supporting paths with spaces
        OLD_IFS="$$IFS"
        IFS='
'
        for _cand in $$NESTED_CANDIDATES; do
            if [ -z "$CANDIDATE_LIST" ]; then
                CANDIDATE_LIST="$$_cand"
            else
                CANDIDATE_LIST="$$CANDIDATE_LIST, $$_cand"
            fi
        done
        IFS="$$OLD_IFS"

        # stderr: exactly one diagnostic line with ALL candidates + way out (VAL-WRAP-004)
        printf 'memory-hook: ambiguous nested repos under %s: %s -> cd into a specific repo, or create memory-project.toml to declare membership\\n' \\
            "$PROJECT_CWD" "$CANDIDATE_LIST" >&2

        # errors.log: session-start only (VAL-WRAP-006 fourth form: missing --event → no log)
        if [ "$EVENT_NAME" = "session-start" ]; then
            printf '[%s] [memory-hook-wrapper] [warn] [event=%s] Ambiguous nested repos under %s: %s\\n' \\
                "$(date -u '+%Y-%m-%dT%H:%M:%S%z')" "$EVENT_NAME" "$PROJECT_CWD" "$CANDIDATE_LIST" \\
                >>"$MEMORY_HOOK_GLOBAL_STATE_ROOT/memory/system/errors.log" 2>/dev/null || true
        fi

        printf '{}\\n'
        exit 0
    fi
    # NESTED_COUNT == 1: PROJECT_CWD already set, continue to export
    # Re-export PROJECT_CWD after probe adjustment
    export MEMORY_HOOK_PROJECT_CWD="$PROJECT_CWD"
fi
# ============================================================================
# END NESTED REPO PROBE
# ============================================================================

# READONLY re-evaluation after probe routing (VAL-WRAP-017 edge case)
# If probe routed to a memory-core clone, re-check and set READONLY
if [ -n "$PROJECT_CWD" ] && [ -d "$PROJECT_CWD" ] && [ "$NESTED_REPO_PROBE_ENABLED" -eq 1 ]; then
    if [ -f "$PROJECT_CWD/memory_core/tools/memory_hook_gateway.py" ] || [ -f "$PROJECT_CWD/memory_core/tools/factory_global_hooks.py" ] || [ -f "$PROJECT_CWD/memory_core/ownership.py" ]; then
        export READONLY=1
    fi
fi

# Check for memory-project.toml (Phase 2 / M4)
if [ -n "$PROJECT_CWD" ] && [ -d "$PROJECT_CWD" ]; then
    for _config_candidate in "$PROJECT_CWD/memory-project.toml" "$PROJECT_CWD/../memory-project.toml"; do
        if [ -f "$_config_candidate" ]; then
            export MEMORY_HOOK_PROJECT_CONFIG="$_config_candidate"
            break
        fi
    done
fi

# Project init with mode awareness
# Probe-triggered init uses adopt mode to avoid dirtying user clones
if [ -n "$PROJECT_CWD" ] && [ -d "$PROJECT_CWD" ] && [ ! -d "$PROJECT_CWD/memory/system" ]; then
    INIT_MODE="create"
    if [ "$NESTED_REPO_PROBE_ENABLED" -eq 1 ]; then
        INIT_MODE="adopt"
    fi

    if ! "$MEMORY_HOOK_PROJECT_INIT" --target "$PROJECT_CWD" --host factory --mode "$INIT_MODE" \\
        >/dev/null 2>>"$MEMORY_HOOK_GLOBAL_STATE_ROOT/memory/system/errors.log"; then
        # Probe-triggered init denied by denylist (e.g., junk pattern): degrade to noop
        if [ "$NESTED_REPO_PROBE_ENABLED" -eq 1 ]; then
            printf '{}\\n'
            exit 0
        fi
        # Normal init failure: report error
        echo '{"error": "project_init_failed", "message": "Failed to initialize project memory"}' >&2
        exit 1
    fi
fi

exec "$MEMORY_HOOK_GATEWAY" "$$@"
""")

    return template.safe_substitute(
        quoted_storage=quoted_storage,
        quoted_gateway=quoted_gateway,
        quoted_init=quoted_init,
        memory_version=_VER,
    )


def _empty_factory_settings() -> dict[str, Any]:
    return {"hooks": {}}


def _load_settings_json(path: Path, warnings: list[str]) -> tuple[dict[str, Any], bool]:
    """Load settings.json, returning (settings_dict, is_corrupted).

    Returns:
        Tuple of (settings_dict, is_corrupted) where is_corrupted indicates
        if the file exists but is unreadable/invalid JSON.
    """
    if not path.exists():
        return _empty_factory_settings(), False
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        warnings.append(f"settings.json corrupt or unreadable, skipping: {exc}")
        return _empty_factory_settings(), True
    if not isinstance(loaded, dict):
        warnings.append("settings.json root is not an object, skipping")
        return _empty_factory_settings(), True
    if not isinstance(loaded.get("hooks"), dict):
        loaded["hooks"] = {}
    return loaded, False


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


def _sanitize_sensitive_data(data: dict[str, Any]) -> dict[str, Any]:
    """Sanitize sensitive data in the installation result."""
    sanitized = dict(data)
    
    # Keys that might contain sensitive information
    sensitive_keys = {
        "factory_home", 
        "settings_path", 
        "wrapper_path", 
        "storage_root",
        "gateway_command",
        "init_command"
    }
    
    # Sanitize settings data if present
    if "settings" in sanitized and isinstance(sanitized["settings"], dict):
        sanitized["settings"] = _sanitize_settings_dict(sanitized["settings"])
    
    return sanitized


def _sanitize_settings_dict(settings: dict[str, Any]) -> dict[str, Any]:
    """Sanitize potentially sensitive values in settings dict."""
    # Deep copy the settings to avoid modifying the original
    import copy
    sanitized = copy.deepcopy(settings)
    
    # Look for potentially sensitive keys
    sensitive_patterns = [
        "token", "key", "secret", "password", "auth", "api", "credential"
    ]
    
    def _sanitize_recursive(obj):
        if isinstance(obj, dict):
            sanitized_dict = {}
            for k, v in obj.items():
                # Check if key suggests sensitive data
                is_sensitive = any(pattern in k.lower() for pattern in sensitive_patterns)
                if is_sensitive:
                    sanitized_dict[k] = "***SANITIZED***"
                else:
                    sanitized_dict[k] = _sanitize_recursive(v)
            return sanitized_dict
        elif isinstance(obj, list):
            return [_sanitize_recursive(item) for item in obj]
        else:
            return obj
    
    return _sanitize_recursive(sanitized)


def install_factory_hooks(
    *,
    factory_home: Path | None = None,
    storage_root: Path | None = None,
    gateway_command: str = "memory-hook-gateway",
    init_command: str = "memory-init",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Install Factory user-level hooks for memory-core.

    Since 2026-08-17, hooks.json is the real registration point.
    settings.json hooks key is deprecated and will not be injected.
    Existing dead hooks in settings.json will be cleaned.

    VAL-REL-012: Existing wrapper will be backed up before re-rendering.
    """
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

    # VAL-REL-006: Do NOT inject hooks into settings.json (dead key since 2026-08-17)
    # Only clean existing dead hooks if settings.json exists
    existing, is_corrupted = _load_settings_json(settings_file, warnings)

    # If file is corrupted, skip write to avoid replacing it
    if is_corrupted:
        cleaned = existing
    else:
        # Filter out any existing memory hooks (dead keys) from settings.json
        cleaned = dict(existing)
        if "hooks" in cleaned and isinstance(cleaned["hooks"], dict):
            cleaned_hooks = dict(cleaned["hooks"])
            for event_name in list(cleaned_hooks.keys()):
                kept_groups = _filter_memory_hooks(cleaned_hooks[event_name])
                if kept_groups:
                    cleaned_hooks[event_name] = kept_groups
                else:
                    # Remove empty event entries
                    del cleaned_hooks[event_name]
            # Don't write empty hooks key
            if cleaned_hooks:
                cleaned["hooks"] = cleaned_hooks
            else:
                cleaned.pop("hooks", None)

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
        "settings": cleaned if dry_run else None,
    }

    if dry_run:
        return result

    # VAL-REL-012: Backup existing wrapper before re-rendering
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    if wrapper.exists():
        backups.append(str(_backup_existing_file(wrapper)))

    wrapper.write_text(wrapper_content, encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)

    # Write cleaned settings.json (without injecting new dead hooks)
    settings_file.parent.mkdir(parents=True, exist_ok=True)

    # Skip write if file is corrupted or content unchanged (idempotent install)
    if is_corrupted:
        warnings.append(f"settings.json is corrupted, skipping write to avoid overwriting: {settings_file}")
    else:
        new_settings_content = json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n"
        if settings_file.exists():
            try:
                existing_content = settings_file.read_text(encoding="utf-8")
                if existing_content == new_settings_content:
                    # No change needed - skip write and backup
                    pass
                else:
                    # Content differs - backup then write
                    backups.append(str(_backup_existing_file(settings_file)))
                    settings_file.write_text(new_settings_content, encoding="utf-8")
            except OSError:
                # Can't read existing file - write anyway
                settings_file.write_text(new_settings_content, encoding="utf-8")
        else:
            # New file - just write
            settings_file.write_text(new_settings_content, encoding="utf-8")

    return result


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install Factory Droid global memory hooks")
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("install", help="Install/update Factory user-level memory hooks")
    install.add_argument(
        "--factory-home", type=Path, default=None, help="Factory config directory (default: ~/.factory)"
    )
    install.add_argument(
        "--storage-root", type=Path, default=None, help="Global memory state root (default: ~/.memory-core)"
    )
    install.add_argument("--gateway-command", default="memory-hook-gateway", help="Gateway command or absolute path")
    install.add_argument("--init-command", default="memory-init", help="Project init command or absolute path")
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
        dry_run=args.dry_run,
    )
    if args.json:
        # Sanitize result for dry-run output to avoid showing sensitive data
        sanitized_result = _sanitize_sensitive_data(result)
        print(json.dumps(sanitized_result, indent=2, ensure_ascii=False))
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
