#!/usr/bin/env python3.12
"""Gateway 配置层：路径常量、适配器配置存储、日志器、完整性检查。

依赖层级：无内部依赖（最底层）。
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib
import json
import logging
import os
import re
import stat
import threading
import tomllib  # stdlib since Python 3.11 (project requires 3.12)
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

__all__ = [
    # Path constants
    "REPO_ROOT",
    "WORKSPACE_ROOT",
    "ARTIFACT_ROOT",
    "CONTEXT_ROOT",
    "EVENT_LOG",
    "ERROR_LOG",
    "PROJECT_LIFECYCLE_ROOT",
    "BATCH_SIZE",
    "NON_INJECTION_EVENTS",
    "_FORCE_HOOK",
    # Seed refinement
    "_refine_non_git_seed",
    # Configuration (Phase 2)
    "_parse_project_config",
    # File utilities (re-exported)
    "exclusive_lock",
    "now_iso",
    # Ownership/mode detection (conditionally available)
    "get_source_repo_mode",
    "is_memory_core_source_repo",
    # Lifecycle tracking
    "record_project_lifecycle",
    # Rule helpers (re-exported)
    "_existing_paths",
    "_get_write_targets_dict",
    "_json_object_keys",
    "_json_string_values",
    "_markdown_code_tokens",
    "_path_is_under",
    "_path_is_under_lexical",
    "_section_body",
    "_section_bullets",
    # Adapter configuration
    "_ADAPTER_NAME",
    "_adapter_config",
    "_load_adapter_profile",
    "get_config",
    "get_config_dict",
    "load_adapter_config",
    "reload_adapter",
    # Integrity checking
    "_integrity_sign",
    "_integrity_verify",
    "_collect_changed_paths",
    # IF-5 facade functions
    "_get_gateway_business_policy",
    "_get_policy_registry",
    "_get_route_policy",
    "_get_write_policy",
    "_get_artifact_sink",
    "_get_error_sink",
    "_resolve_route_target_via_policy",
    "_apply_hook_runtime_write_targets",
    "_write_targets_via_policy",
    "_get_policy_pack_via_registry",
    "_resolve_policy_conflict_via_registry",
    # Utilities
    "_logger",
]

# ---------------------------------------------------------------------------
# 日志器（必须在其他函数之前定义，因为它们依赖 _logger）
# ---------------------------------------------------------------------------

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 路径发现与常量
# ---------------------------------------------------------------------------

_project_cwd_env = os.environ.get("MEMORY_HOOK_PROJECT_CWD", "")
_cwd_seed = Path(_project_cwd_env) if _project_cwd_env else Path.cwd()

try:
    from .memory_root_discovery import discover_roots
except ImportError:
    from memory_core.tools.memory_root_discovery import discover_roots


def _refine_non_git_seed(seed: Path) -> Path:
    """Refine non-git seed to unique valid child repository if applicable.

    B-layer seed refinement: when seed is non-git (no .git), no consent marker
    is present, and exactly one valid child repository exists, return that child
    as the refined seed.

    Valid child = has .git (file or directory), not a dot directory.
    Pure filesystem operation, no subprocess calls.

    Args:
        seed: The initial seed path from MEMORY_HOOK_PROJECT_CWD or cwd()

    Returns:
        Refined seed path (child repo) if conditions met, otherwise original seed
    """
    # If seed itself has .git, passthrough (no refinement needed)
    if (seed / ".git").exists():
        return seed

    # If consent marker present, passthrough (respect user intent)
    # Check env var first (legacy)
    if os.environ.get("MEMORY_HOOK_ALLOW_NON_GIT"):
        return seed

    # Check persistent consent markers (M1-1: ownership.toml and/or manifest.json)
    # Uses anchored regex to avoid false positives like 'allow_non_git = false # true'
    _consent_pattern = re.compile(r"^\s*allow_non_git\s*=\s*true\s*$", re.MULTILINE)

    # Check ownership.toml [policy] section
    ownership_toml_path = seed / "memory" / "system" / "ownership.toml"
    if ownership_toml_path.exists():
        try:
            content = ownership_toml_path.read_text(encoding="utf-8")
            if _consent_pattern.search(content):
                return seed  # Persistent consent found, passthrough
        except (OSError, UnicodeDecodeError):
            pass  # If we can't read it, continue to next check

    # Check manifest.json
    manifest_json_path = seed / "memory" / "system" / "manifest.json"
    if manifest_json_path.exists():
        try:
            content = manifest_json_path.read_text(encoding="utf-8")
            manifest = json.loads(content)
            if manifest.get("allow_non_git") is True:
                return seed  # Persistent consent found, passthrough
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            pass  # If we can't read or parse it, continue

    # Find valid child repositories
    # Valid = has .git (file or dir), not a dot directory (name.startswith('.'))
    # VAL-GTW-008/012: Only check for .git existence (not memory tree existence)
    valid_children = []
    try:
        for child in seed.iterdir():
            # Skip dot directories (shell glob alignment)
            if child.name.startswith("."):
                continue

            # Check if child has .git (file or directory) - only .git existence matters (not memory tree)
            if (child / ".git").exists():
                valid_children.append(child)

                # Early exit: if we find 2+ children, it's ambiguous
                if len(valid_children) >= 2:
                    # Ambiguous: return original seed (don't silently choose)
                    return seed
    except (OSError, PermissionError):
        # If we can't iterate, return original seed
        return seed

    # Exactly one valid child found
    if len(valid_children) == 1:
        return valid_children[0]

    # No children or ambiguous: return original seed
    return seed


# ============================================================================
# Phase 2: Project Configuration (memory-project.toml)
# ============================================================================

_PROJECT_CONFIG_NAME = "memory-project.toml"
_HOME_ENV = os.environ.get("HOME", "")
_SYSTEM_PATHS = frozenset({"/", "/usr", "/System", "/Library", str(Path("~/").expanduser())})


def _find_project_config_path(seed: Path) -> Path | None:
    """Find memory-project.toml following locate-then-use rules.

    Rules:
    1. Self first: check {seed}/memory-project.toml
    2. Ancestor fallback: walk up directory tree
    3. Nearest wins: first found wins (not merging)

    Args:
        seed: The initial seed path

    Returns:
        Absolute path to config file if found, None otherwise
    """
    # Normalize to absolute path, nearest-first collection
    configs = _find_all_project_configs(seed)
    return configs[0] if configs else None


def _find_all_project_configs(seed: Path) -> list[Path]:
    """Collect every memory-project.toml from seed up to filesystem root.

    Nearest first (seed directory before ancestors). Used by
    VAL-CFG-006 cross-config members-overlap detection.

    Args:
        seed: The initial seed path

    Returns:
        List of absolute config paths (empty if none found)
    """
    configs: list[Path] = []

    # Traverse up to root
    current = seed.resolve()
    while True:
        candidate = current / _PROJECT_CONFIG_NAME
        if candidate.exists() and candidate.is_file():
            configs.append(candidate.resolve())

        # Stop at root (parent == self)
        parent = current.parent
        if parent == current:
            break
        current = parent

    return configs


def _parse_project_config(config_path: Path, *, strict: bool = False) -> dict[str, Any] | None:
    """Parse memory-project.toml and validate structure.

    Args:
        config_path: Absolute path to config file
        strict: If True, raise on syntax error (for VAL-CFG-012 explicit error)

    Returns:
        Parsed config dict with keys: project, memory_root, members
        None if parsing fails or file unreadable
    """
    try:
        content = config_path.read_text(encoding="utf-8")
        try:
            parsed = tomllib.loads(content)
        except Exception as exc:
            # VAL-CFG-012: Syntax error - explicit error if strict, warning otherwise
            if strict:
                raise
            _logger.warning("_parse_project_config: parse failed for %s: %s", config_path, exc)
            return None

        # Validate required keys
        if not isinstance(parsed, dict):
            _logger.warning("_parse_project_config: config root is not a dict: %s", config_path)
            return None

        # memory_root is optional in config but we extract it for routing
        # project and members are optional but can be used for validation

        result: dict[str, Any] = {}
        if "project" in parsed:
            result["project"] = parsed["project"]
        if "memory_root" in parsed:
            result["memory_root"] = parsed["memory_root"]
        if "members" in parsed:
            result["members"] = parsed["members"]

        return result
    except (OSError, UnicodeDecodeError) as exc:
        _logger.warning("_parse_project_config: read failed for %s: %s", config_path, exc)
        return None


def _resolve_memory_root(  # noqa: C901
    mem_root: str | list[Any], config_path: Path
) -> Path | None:
    """Resolve memory_root value to absolute path with containment check.

    - "./" or "." → return config parent (self-root, valid)
    - Relative paths → resolve relative to config parent, check containment
    - Absolute paths → check against config parent containment

    Args:
        mem_root: memory_root value from config (string or list for members case)
        config_path: Absolute path to config file

    Returns:
        Resolved absolute path if valid, None if invalid/omitted
    """
    config_parent = config_path.parent

    # Handle members list or string
    if isinstance(mem_root, list):
        # Extract first element if it's a members list, otherwise skip
        if mem_root:
            mem_root = mem_root[0] if isinstance(mem_root[0], str) else str(mem_root[0])
        else:
            return None

    if not isinstance(mem_root, str):
        mem_root = str(mem_root)

    # Val-CFG-015: self-reference "./" or "." is valid
    if mem_root in {"./", "."}:
        return config_parent

    # Normalize path (handle ../ and ./)
    try:
        resolved = (config_parent / mem_root).resolve()
    except (OSError, ValueError) as exc:
        _logger.warning("_resolve_memory_root: path resolution failed for %s/%s: %s", config_parent, mem_root, exc)
        return None

    # Val-CFG-007/008/009: containment + same-mount check
    # Must be under config parent's tree (no .. escape to parent)
    # But allow same directory (self-reference handled above)
    try:
        resolved.relative_to(config_parent)
    except ValueError:
        # Not under config parent - check if it IS the config parent (self-ref handled above)
        if resolved != config_parent:
            _logger.warning("_resolve_memory_root: %s escapes config parent %s", resolved, config_parent)
            return None

    # VAL-CFG-009: deny specific paths
    # Use realpath to resolve symlinks
    try:
        resolved_real = resolved.resolve()
    except (OSError, ValueError):
        resolved_real = resolved

    resolved_str = str(resolved_real)

    # Check system paths: exact match or proper subdirectory (with separator)
    for sys_path in _SYSTEM_PATHS:
        try:
            sys_resolve = Path(sys_path).resolve()
            sys_resolve_str = str(sys_resolve)
            # Special handling for HOME: only exact match (not subdirectory)
            # This prevents denying all paths under home, which would block memory projects
            if sys_resolve_str == _HOME_ENV:
                if resolved_real == sys_resolve:
                    _logger.warning("_resolve_memory_root: %s is HOME itself, denied", resolved_real)
                    return None
            else:
                # Other system paths: deny exact match or subdirectory
                if resolved_real == sys_resolve or resolved_str.startswith(sys_resolve_str + "/"):
                    _logger.warning("_resolve_memory_root: %s is in deny list", resolved_real)
                    return None
        except OSError:
            continue

    # Check if it's memory-core source repo.
    # Lazy import: the module-level re-export near the bottom of this file binds
    # only AFTER the REPO_ROOT init call, so referencing the global here during
    # module init raised NameError (silently swallowed), disabling this check
    # on the initialization path.
    is_src_repo_fn: Callable[[Path], bool] | None = None
    try:
        from ..ownership import is_memory_core_source_repo

        is_src_repo_fn = is_memory_core_source_repo
    except ImportError:
        pass
    if is_src_repo_fn is not None:
        try:
            if is_src_repo_fn(resolved_real):
                _logger.warning("_resolve_memory_root: %s is memory-core source repo", resolved_real)
                return None
        except Exception:
            pass

    # VAL-CFG-008: symlink穿透 with realpath
    # For containment check, use resolved path
    try:
        resolved_real.relative_to(config_parent.resolve())
    except ValueError:
        # Not under config parent after realpath
        if resolved_real != config_parent.resolve():
            _logger.warning(
                "_resolve_memory_root: realpath %s escapes config parent %s", resolved_real, config_parent.resolve()
            )
            return None

    return resolved


def _check_members_overlap(configs: list[tuple[Path, dict[str, Any]]]) -> list[str] | None:  # noqa: C901
    """Check for overlapping member paths across configs.

    VAL-CFG-006: Directory tree with two configs having overlapping members → reject and list conflict.
    Overlap is detected as:
    - Exact path equality (p1 == p2), OR
    - Cross-config ancestor-descendant relationship (one path is parent of another under different config)

    Trigger: requires ≥2 different configs (same config内重复成员不触发).

    Args:
        configs: List of (config_path, parsed_config) tuples

    Returns:
        List of overlapping paths if found, None otherwise
    """
    # Filter out world-writable configs (VAL-CFG-010:降级为忽略)
    filtered_configs = []
    for cfg_path, cfg in configs:
        try:
            mode = cfg_path.stat().st_mode
            if not bool(mode & stat.S_IWOTH):  # Not world-writable
                filtered_configs.append((cfg_path, cfg))
        except OSError:
            filtered_configs.append((cfg_path, cfg))

    # If no configs after filtering, no overlaps possible
    if len(filtered_configs) < 2:
        return None

    # Group by resolved path, tracking which configs declare each path
    path_to_configs: dict[str, list[Path]] = {}

    for config_path, config in filtered_configs:
        members = config.get("members", [])
        if not isinstance(members, list):
            members = [members] if members else []
        for member in members:
            if not isinstance(member, str):
                member = str(member)
            # Resolve relative to config path
            try:
                resolved = (config_path.parent / member).resolve()
            except (OSError, ValueError):
                continue  # Skip unresolvable paths
            resolved_str = str(resolved)
            if resolved_str not in path_to_configs:
                path_to_configs[resolved_str] = []
            # Avoid duplicate config entries for same path
            if config_path not in path_to_configs[resolved_str]:
                path_to_configs[resolved_str].append(config_path)

    # Find overlaps: either exact paths with ≥2 different configs, or nested relationships
    overlaps = []
    paths_list = list(path_to_configs.keys())

    for i, path_str1 in enumerate(paths_list):
        config_paths1 = path_to_configs[path_str1]

        # Check for exact overlap (same path from multiple configs)
        unique_configs_set = set(str(p) for p in config_paths1)
        if len(unique_configs_set) >= 2:
            overlaps.append(f"{path_str1} (declared in: {', '.join(str(p) for p in config_paths1)})")
            continue

        # Check for nested relationships with other paths
        for j, path_str2 in enumerate(paths_list):
            if i >= j:
                continue
            config_paths2 = path_to_configs[path_str2]
            # Only check cross-config relationships (≥2 different configs)
            all_configs = set(str(p) for p in config_paths1) | set(str(p) for p in config_paths2)
            if len(all_configs) < 2:
                continue  # Same config only - don't trigger

            path1 = Path(path_str1)
            path2 = Path(path_str2)

            # Check if one is ancestor of the other (嵌套包含)
            # path2 under path1 - path1 is ancestor of path2
            try:
                path2.relative_to(path1)
                overlaps.append(
                    f"{path_str2} (ancestor:{path_str1}, declared in: {', '.join(str(p) for p in config_paths2)})"
                )
                continue
            except ValueError:
                pass

            # path1 under path2 - path2 is ancestor of path1
            try:
                path1.relative_to(path2)
                overlaps.append(
                    f"{path_str1} (ancestor:{path_str2}, declared in: {', '.join(str(p) for p in config_paths1)})"
                )
                continue
            except ValueError:
                pass

    return overlaps if overlaps else None


def _check_members_existence(config_path: Path, members: list[Any], logger: logging.Logger) -> list[str]:
    """Check if member paths exist and return ghost paths.

    VAL-CFG-016: members含不存在路径 → 显式可见，不静默.
    Response: warn + route to valid memory_root.

    Args:
        config_path: Absolute path to config file
        members: Members list from config
        logger: Logger instance

    Returns:
        List of ghost (non-existent) paths
    """
    ghost_paths = []
    config_parent = config_path.parent

    for member in members:
        if not isinstance(member, str):
            member = str(member)
        resolved = (config_parent / member).resolve()
        if not resolved.exists():
            ghost_paths.append(str(resolved))

    if ghost_paths:
        logger.warning(
            "_check_members_existence: members contain ghost paths in %s: %s",
            config_path,
            ", ".join(ghost_paths),
        )

    return ghost_paths


def _validate_memory_root_value(mem_root: Any, config_path: Path) -> tuple[bool, str | None]:
    """Validate memory_root value for special cases.

    VAL-CFG-018: memory_root empty string → invalid value explicit error.
    VAL-CFG-017: memory_root missing → not used for routing (handled by caller).

    Args:
        mem_root: memory_root value from config (Any - str, list, or None)
        config_path: Absolute path to config file

    Returns:
        (is_valid, error_message) tuple
    """
    # Handle empty string
    mem_root_str = ""
    if isinstance(mem_root, list):
        if mem_root:
            mem_root_str = mem_root[0] if isinstance(mem_root[0], str) else str(mem_root[0])
    else:
        mem_root_str = str(mem_root) if mem_root else ""

    if isinstance(mem_root, list) and not mem_root:
        return False, f"memory_root is empty list in {config_path}"
    if mem_root_str == "":
        return False, f"memory_root is empty string in {config_path}"

    return True, None


def _check_world_writable(config_path: Path) -> bool:
    """Check if config file is world-writable.

    Returns True if mode has world-writable bit set.
    """
    try:
        mode = config_path.stat().st_mode
        return bool(mode & stat.S_IWOTH)
    except OSError:
        return False


def _check_members_boundaries(members: list[Any], config_path: Path) -> list[str]:
    """Check if members are within config parent boundaries (VAL-CFG-007).

    Rules:
    - None of members should escape config parent (containment check)
    - Absolute paths outside config root are rejected
    - ../ escaping is rejected
    - Uses realpath+containment+deny for each member entry

    Args:
        members: Members list from config
        config_path: Absolute path to config file

    Returns:
        List of out-of-bounds member entries (or paths) if found, empty list otherwise
    """
    config_parent = config_path.parent
    out_of_bounds_entries = []

    for member in members:
        member_str = str(member) if not isinstance(member, str) else member

        try:
            # Check for empty string
            if not member_str or member_str.strip() == "":
                out_of_bounds_entries.append(f"empty string in {config_path}")
                continue

            # Resolve relative to config parent
            resolved = (config_parent / member_str).resolve()
            resolved_str = str(resolved)

            # Check containment - must be under config parent
            try:
                resolved.relative_to(config_parent)
            except ValueError:
                # Not under config parent
                if resolved != config_parent:
                    out_of_bounds_entries.append(
                        f"{member_str} -> {resolved_str} (escapes config parent in {config_path})"
                    )
                    continue

            # Check deny list (HOME/system paths/memory-core source)
            # Use realpath for symlink穿透
            try:
                resolved_real = resolved.resolve()
            except (OSError, ValueError):
                resolved_real = resolved

            resolved_real_str = str(resolved_real)
            home_env = os.environ.get("HOME", "")

            # Check deny paths
            deny_list = ["/", "/usr", "/System", "/Library", home_env, str(Path("~/").expanduser())]
            for sys_path in deny_list:
                try:
                    sys_resolve = Path(sys_path).resolve()
                    sys_resolve_str = str(sys_resolve)
                    if sys_resolve_str == home_env:
                        # HOME: exact match only
                        if resolved_real == sys_resolve:
                            out_of_bounds_entries.append(
                                f"{member_str} -> {resolved_real_str} (HOME denied in {config_path})"
                            )
                            break
                    else:
                        # Other paths: exact or subdirectory
                        if resolved_real == sys_resolve or resolved_real_str.startswith(sys_resolve_str + "/"):
                            out_of_bounds_entries.append(
                                f"{member_str} -> {resolved_real_str} (system path denied in {config_path})"
                            )
                            break
                except OSError:
                    continue

            # Check memory-core source repo
            try:
                from ..ownership import is_memory_core_source_repo

                if is_memory_core_source_repo(resolved_real):
                    out_of_bounds_entries.append(
                        f"{member_str} -> {resolved_real_str} (memory-core source denied in {config_path})"
                    )
            except (ImportError, Exception):
                pass

        except (OSError, ValueError) as exc:
            out_of_bounds_entries.append(f"{member_str} -> resolution error ({exc}) in {config_path}")

    return out_of_bounds_entries


def _resolve_repo_root_with_config(seed: Path) -> tuple[Path, Path]:  # noqa: C901
    """Resolve REPO_ROOT and WORKSPACE_ROOT with four-level priority.

    The gateway receives PROJECT_CWD that was already normalized by the wrapper
    (which does git rev-parse --show-toplevel). The gateway's job is to:
    1. Check if this is already a git-governed root (noFurther action needed)
    2. Otherwise, check for memory-project.toml configuration
    3. If config found, use it to resolve memory_root (if present)
    4. Otherwise, fall back to B-layer refinement

    Priority (highest to lowest):
    - Git upwards: already done by wrapper, but we verify if seed has .git
    - 项目根硬化配置: memory-project.toml (config level)
    - 启发式向下探测: B-layer seed refinement
    - 显式拒绝: fallback to cwd ( may be invalid)

    Args:
        seed: Initial seed path from MEMORY_HOOK_PROJECT_CWD (wrapper-normalized)

    Returns:
        (REPO_ROOT, WORKSPACE_ROOT) tuple
    """
    # Level 1: Check if seed is already git-governed (wrapper did git normalization)
    config_at_git_seed = None
    if (seed / ".git").exists():
        # Seed is a git repo - use it directly (no config needed for git repos)
        # VAL-CFG-005: If config exists with memory_root ≠ git root, emit conflict
        config_at_git_seed = _find_project_config_path(seed)
        if config_at_git_seed is not None:
            try:
                config = _parse_project_config(config_at_git_seed)
                if config is not None and config.get("memory_root") is not None:
                    mem_root = config.get("memory_root")
                    # Check for empty values first (non-blocking) before any processing
                    is_valid, error_msg = _validate_memory_root_value(mem_root, config_at_git_seed)
                    if not is_valid:
                        _logger.error(error_msg)
                        # Non-blocking: don't raise, just fall through to degraded routing
                        # The config level is rejected, fall through to B-layer refinement
                        # Continue to fall through to B-layer
                    elif isinstance(mem_root, list):
                        if mem_root:
                            mem_root = mem_root[0] if isinstance(mem_root[0], str) else str(mem_root[0])
                        else:
                            # Empty list already handled by _validate_memory_root_value above
                            # which returns error_msg
                            pass  # Continue to B-layer
                    if isinstance(mem_root, str) and mem_root not in {"./", "."}:
                        resolved_mem = (config_at_git_seed.parent / mem_root).resolve()
                        git_root = seed.resolve()
                        if resolved_mem != git_root:
                            # Emit conflict line: git root, config declared root, config path
                            _logger.error(
                                "_resolve_repo_root_with_config: config and git root conflict "
                                "(VAL-CFG-005): git_root=%s, config_memory_root=%s, config_path=%s",
                                git_root,
                                resolved_mem,
                                config_at_git_seed,
                            )
            except Exception:
                pass  # Don't crash on config parsing errors
        return (seed, seed)

    # Level 2: Project config (memory-project.toml)
    # Search in seed directory and ancestors
    config_path = _find_project_config_path(seed)
    if config_path is not None:
        # VAL-CFG-006: members declared by multiple configs in the tree that
        # resolve to the same absolute path → reject the config level entirely
        # and surface the conflict list
        # VAL-CFG-010: Filter out world-writable configs before overlap detection
        parsed_configs: list[tuple[Path, dict[str, Any]]] = []
        for cfg_path in _find_all_project_configs(seed):
            # Check world-writable (VAL-CFG-010) - skip world-writable configs for overlap
            try:
                mode = cfg_path.stat().st_mode
                if bool(mode & stat.S_IWOTH):
                    # World-writable config is ignored for overlap detection
                    continue
            except OSError:
                pass  # If we can't stat, include it
            parsed_cfg = _parse_project_config(cfg_path)
            if parsed_cfg is not None:
                parsed_configs.append((cfg_path, parsed_cfg))
        member_overlaps = _check_members_overlap(parsed_configs)
        if member_overlaps is not None:
            _logger.error(
                "_resolve_repo_root_with_config: members overlap across configs, "
                "rejecting config level (VAL-CFG-006): %s",
                "; ".join(member_overlaps),
            )
            config_path = None
    if config_path is not None:
        # Check world-writable (VAL-CFG-010)
        world_writable = _check_world_writable(config_path)
        if world_writable:
            _logger.warning("_resolve_repo_root_with_config: config %s is world-writable, ignoring", config_path)
            # VAL-CFG-010:降级为忽略 + 告警 -> skip config, fall through to next level
            config_path = None  # Explicitly set to None so fall through happens
        else:
            # Parse config
            config = _parse_project_config(config_path)
            if config is not None:
                # Try to resolve memory_root
                mem_root = config.get("memory_root")
                if mem_root is not None:
                    # VAL-CFG-018: Check memory_root empty string/list - non-blocking error
                    is_valid, error_msg = _validate_memory_root_value(mem_root, config_path)
                    if not is_valid:
                        _logger.error(error_msg)
                        # Non-blocking: don't raise, just fall through to degraded routing
                        # The config level is rejected, fall through to B-layer refinement
                        config_path = None
                    else:
                        resolved_root = _resolve_memory_root(mem_root, config_path)
                        if resolved_root is not None:
                            # If config has members, also check out-of-bounds entries
                            if "members" in config:
                                members = config.get("members", [])
                                out_of_bounds_entries = _check_members_boundaries(members, config_path)
                                if out_of_bounds_entries:
                                    _logger.error(
                                        "_resolve_repo_root_with_config: members contain out-of-bounds entries in %s: %s",
                                        config_path,
                                        ", ".join(out_of_bounds_entries),
                                    )
                                    # Out-of-bounds rejection: degrade config level
                                    config_path = None
                                else:
                                    # Check for members ghost paths (VAL-CFG-016)
                                    _check_members_existence(config_path, members, _logger)
                                    return (resolved_root, resolved_root)
                            else:
                                # No members, return resolved memory_root
                                return (resolved_root, resolved_root)
                # If memory_root not specified, but config exists with members,
                # use config parent as the project root
                elif "members" in config:
                    # Check members boundary violations first (VAL-CFG-007)
                    members = config.get("members", [])
                    out_of_bounds_entries = _check_members_boundaries(members, config_path)
                    if out_of_bounds_entries:
                        _logger.error(
                            "_resolve_repo_root_with_config: members contain out-of-bounds entries in %s: %s",
                            config_path,
                            ", ".join(out_of_bounds_entries),
                        )
                        # Out-of-bounds rejection: degrade config level
                        config_path = None
                    else:
                        # Check for members ghost paths (VAL-CFG-016)
                        _check_members_existence(config_path, members, _logger)
                        return (config_path.parent, config_path.parent)
                # If memory_root not specified and no members, fall through to next level

    # VAL-CFG-017: memory_root缺失 → 不完整配置：告警 + 降级探测
    # Fall-through warning only when resolution succeeded (config exists) but truly no memory_root and no members
    # Do NOT emit if config was rejected (world-writable, out-of-bounds, empty value, etc.)
    if config_path is not None:
        _logger.warning(
            "_resolve_repo_root_with_config: config %s has no memory_root and no members, falling back to next level",
            config_path,
        )

    # Level 3: B-layer seed refinement (pure filesystem)
    seed_refined = _refine_non_git_seed(seed)
    if (seed_refined / ".git").exists():
        # Refined seed has .git (file or dir), it's already a git-governed root
        return (seed_refined, seed_refined)
    elif seed_refined == seed:
        # Refined seed is same as input - no git, no refinement possible
        # This happens when config was rejected or config doesn't exist
        # Return seed as best guess (graceful degradation)
        return (seed, seed)
    else:
        # Non-git refined seed (refined from a different path), use normal discovery
        return discover_roots(seed_refined)


# Use the new routing logic
REPO_ROOT, WORKSPACE_ROOT = _resolve_repo_root_with_config(_cwd_seed)

_FORCE_HOOK = bool(os.environ.get("MEMORY_HOOK_FORCE") or os.environ.get("WORKBOT_FORCE_HOOK"))
BATCH_SIZE = 500


def _configured_artifact_root(workspace_root: Path) -> Path:
    artifact_root = os.environ.get("MEMORY_HOOK_ARTIFACT_ROOT")
    if artifact_root:
        return Path(artifact_root).expanduser()
    return workspace_root / "memory" / "artifacts" / "memory-hook"


def _configured_error_log(workspace_root: Path) -> Path:
    error_log = os.environ.get("MEMORY_HOOK_ERROR_LOG")
    if error_log:
        return Path(error_log).expanduser()
    return workspace_root / "memory" / "system" / "errors.log"


def _configured_invalid_memory_root(workspace_root: Path) -> Path:
    return workspace_root / "memory" / "archive" / "invalid"


def _configured_project_lifecycle_root(workspace_root: Path) -> Path:
    global_state_root = os.environ.get("MEMORY_HOOK_GLOBAL_STATE_ROOT")
    if global_state_root:
        return Path(global_state_root).expanduser() / "project-lifecycle"
    return workspace_root / "memory" / "artifacts" / "memory-hook" / "project-lifecycle"


ARTIFACT_ROOT = _configured_artifact_root(WORKSPACE_ROOT)
CONTEXT_ROOT = ARTIFACT_ROOT / "contexts"
EVENT_LOG = ARTIFACT_ROOT / "events.jsonl"
ERROR_LOG = _configured_error_log(WORKSPACE_ROOT)
PROJECT_LIFECYCLE_ROOT = _configured_project_lifecycle_root(WORKSPACE_ROOT)

# Note: _logger is already defined at module top (line ~83); this duplicate is kept
# for compatibility but is dead code (module top version shadows this)

# ---------------------------------------------------------------------------
# 文件工具与规则辅助（re-exported for test access）
# ---------------------------------------------------------------------------

try:
    from ._file_utils import exclusive_lock, now_iso  # noqa: F401
except ImportError:
    from _file_utils import now_iso  # type: ignore  # noqa: F401

try:
    from ._rule_helpers import (
        _existing_paths,
        _get_write_targets_dict,
        _json_object_keys,
        _json_string_values,
        _markdown_code_tokens,
        _path_is_under,
        _path_is_under_lexical,
        _section_body,
        _section_bullets,
    )
except ImportError:
    from _rule_helpers import (  # type: ignore  # noqa: F401
        _existing_paths,
        _get_write_targets_dict,
        _json_object_keys,
        _json_string_values,
        _markdown_code_tokens,
        _path_is_under,
        _path_is_under_lexical,
        _section_body,
        _section_bullets,
    )

# ---------------------------------------------------------------------------
# 所有权 / 拒绝列表 / 生命周期
# ---------------------------------------------------------------------------

with contextlib.suppress(ImportError):
    from .cmux_hook_state import default_hook_state_path, record_hook_event  # noqa: F401

with contextlib.suppress(ImportError):
    from ..ownership import get_source_repo_mode, is_memory_core_source_repo  # noqa: F401

with contextlib.suppress(ImportError):
    from .project_lifecycle import record_project_lifecycle  # noqa: F401

try:
    import memory_core.tools.denylist as _denylist

    is_denied_project_root = _denylist.is_denied_project_root
except ImportError:
    import memory_core.tools.denylist as _denylist

    is_denied_project_root = _denylist.is_denied_project_root

# ---------------------------------------------------------------------------
# 非注入事件集合
# ---------------------------------------------------------------------------

NON_INJECTION_EVENTS: frozenset[str] = frozenset(
    {
        "stop",
        "notification",
        "subagent-stop",
        "post-tool-use",
        "pre-compact",
        "session-end",
    }
)

# ---------------------------------------------------------------------------
# L2 完整性（lazy import 避免循环依赖）
# ---------------------------------------------------------------------------


def _integrity_sign(project_root: Path) -> None:
    """Sign project manifest after artifact write. Non-blocking."""
    try:
        from .memory_hook_integrity_keys import load_or_create_key
        from .memory_hook_integrity_manifest import sign_project

        key = load_or_create_key()
        sign_project(project_root, key)
    except Exception as exc:
        _logger.debug("integrity sign skipped: %s", exc)


def _integrity_verify(project_root: Path) -> dict[str, Any] | None:
    """Verify project manifest on session-start. Returns result dict or None."""
    try:
        from .memory_hook_integrity_keys import load_key
        from .memory_hook_integrity_verify import verify_project

        key = load_key()
        if key is None:
            _logger.warning("Integrity key not found — protection disabled")
            return {"ok": False, "skipped_reason": "key_not_found"}
        result = verify_project(project_root, key)
        return result.to_dict()
    except Exception as exc:
        _logger.debug("integrity verify skipped: %s", exc)
        return None


def _collect_changed_paths(
    project_root: Path,
    manifest: dict[str, Any],
) -> set[str]:
    """F3: Compare manifest SHA-256 entries with on-disk files to find changes."""
    resolved_root = project_root.resolve()
    changed: set[str] = set()
    for entry in manifest.get("entries", []):
        rel_path = entry.get("rel_path", "")
        expected_sha = entry.get("sha256", "")
        if not rel_path or not expected_sha:
            continue
        abs_path = resolved_root / rel_path
        if not abs_path.exists():
            changed.add(rel_path)
            continue
        try:
            raw = abs_path.read_bytes()
            actual_sha = hashlib.sha256(raw).hexdigest()
            if actual_sha != expected_sha:
                changed.add(rel_path)
        except OSError as exc:
            _logger.warning("_collect_changed_paths: cannot read %s: %s", rel_path, exc)
            changed.add(rel_path)
    return changed


# ---------------------------------------------------------------------------
# 适配器配置存储（替代 globals().update 注入）
# ---------------------------------------------------------------------------

_ADAPTER_NAME = os.environ.get("MEMORY_HOOK_ADAPTER", "default")
_ADAPTER_REGISTRY = {
    "default": (".memory_hook_adapters.default_runtime_profile", "build_default_runtime_profile"),
}


def _load_adapter_profile(adapter_name: str, repo_root: Path, workspace_root: Path) -> dict[str, Any]:
    """Load adapter profile.

    Raises:
        KeyError: If adapter_name is not in _ADAPTER_REGISTRY.
        ImportError: If the adapter module cannot be imported.
    """
    if adapter_name not in _ADAPTER_REGISTRY:
        raise KeyError(f"unknown adapter: {adapter_name}")
    _mod_path, _fn_name = _ADAPTER_REGISTRY[adapter_name]
    _mod = importlib.import_module(_mod_path, package="memory_core.tools")
    _fn = getattr(_mod, _fn_name)
    return cast(dict[str, Any], _fn(repo_root, workspace_root))


_adapter_config: dict[str, Any] = {}
_config_lock = threading.Lock()


def get_config(key: str, default: Any = None) -> Any:
    """Thread-safe read from adapter config."""
    with _config_lock:
        return _adapter_config.get(key, default)


def get_config_dict() -> dict[str, Any]:
    """Return a shallow copy of the current adapter config for safe iteration."""
    with _config_lock:
        return dict(_adapter_config)


def load_adapter_config(profile: dict[str, Any]) -> None:
    """Load adapter runtime profile into _adapter_config."""
    with _config_lock:
        _adapter_config.clear()
        _adapter_config.update(profile)


_adapter_profile = _load_adapter_profile(_ADAPTER_NAME, REPO_ROOT, WORKSPACE_ROOT)
load_adapter_config(_adapter_profile)


def reload_adapter(adapter_name: str | None = None) -> None:
    """Reload adapter configuration in the current process."""
    global _adapter_profile, _adapter_config, _ADAPTER_NAME
    if adapter_name is None:
        adapter_name = os.environ.get("MEMORY_HOOK_ADAPTER", "default")
    new_profile = _load_adapter_profile(adapter_name, REPO_ROOT, WORKSPACE_ROOT)
    _adapter_profile = new_profile
    with _config_lock:
        _adapter_config.clear()
        _adapter_config.update(new_profile)
    _ADAPTER_NAME = adapter_name


# ---------------------------------------------------------------------------
# IF-5 门面函数（基础层）
# ---------------------------------------------------------------------------

from .memory_hook_adapters.neutral_policy import NeutralGatewayBusinessPolicy
from .memory_hook_impls import (
    ArtifactSinkImpl,
    ErrorSinkImpl,
    GatewayBusinessPolicyConfig,
    PolicyRegistryImpl,
    RouteTargetPolicyImpl,
    WriteTargetPolicyImpl,
)

_default_policy_registry: PolicyRegistryImpl | None = None
_default_route_policy: RouteTargetPolicyImpl | None = None
_default_write_policy: WriteTargetPolicyImpl | None = None


def _get_gateway_business_policy() -> Any:
    """获取业务策略实例。"""

    def _read_text_if_exists(path: Path) -> str:
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    config = GatewayBusinessPolicyConfig(
        repo_root=REPO_ROOT,
        workspace_root=WORKSPACE_ROOT,
        project_map_root=get_config("PROJECT_MAP_ROOT"),
        project_map_files=get_config("PROJECT_MAP_FILES"),
        project_map_governance=get_config("PROJECT_MAP_GOVERNANCE"),
        truth_model=get_config("TRUTH_MODEL"),
        global_canonical=get_config("GLOBAL_CANONICAL"),
        authority_allowed_paths=get_config("AUTHORITY_ALLOWED_PATHS"),
        lower_evidence_roots=get_config("LOWER_EVIDENCE_ROOTS"),
        legal_core_markers=get_config("LEGAL_CORE_MARKERS"),
        required_registry_scopes=get_config("REQUIRED_REGISTRY_SCOPES"),
        project_canonical=get_config("PROJECT_CANONICAL"),
        project_runtime_root=get_config("PROJECT_RUNTIME_ROOT"),
        project_doc_refs=get_config("PROJECT_DOC_REFS"),
        default_decision_refs=get_config("DEFAULT_DECISION_REFS"),
        project_decision_refs=get_config("PROJECT_DECISION_REFS"),
        default_lesson_refs=get_config("DEFAULT_LESSON_REFS"),
        project_lesson_refs=get_config("PROJECT_LESSON_REFS"),
        governance_frozen_tuple_files=get_config("GOVERNANCE_FROZEN_TUPLE_FILES"),
        event_contract_files=get_config("EVENT_CONTRACT_FILES"),
        frozen_tuple_expected=get_config("FROZEN_TUPLE_EXPECTED"),
        frozen_tuple_legacy_markers=get_config("FROZEN_TUPLE_LEGACY_MARKERS"),
        formal_source_types=get_config("FORMAL_SOURCE_TYPES"),
        formal_event_types=get_config("FORMAL_EVENT_TYPES"),
        formal_event_statuses=get_config("FORMAL_EVENT_STATUSES"),
        formal_field_keys=get_config("FORMAL_FIELD_KEYS"),
        legacy_field_keys=get_config("LEGACY_FIELD_KEYS"),
        required_canonical=get_config("REQUIRED_CANONICAL"),
        workspace_index_path=WORKSPACE_ROOT / "INDEX.md",
        docs_index_path=WORKSPACE_ROOT / "memory" / "docs" / "INDEX.md",
        overview_doc_path=WORKSPACE_ROOT / "memory" / "docs" / "记忆系统全景文档.md",
        global_index_path=WORKSPACE_ROOT / "memory" / "kb" / "global" / "INDEX.md",
        hook_contract_path=get_config("HOOK_CONTRACT_PATH"),
        default_project_scope=get_config("DEFAULT_PROJECT_SCOPE"),
        scope_match_hints=get_config("SCOPE_MATCH_HINTS"),
        read_text_if_exists_fn=_read_text_if_exists,
    )
    policy_class = _adapter_config.get("GATEWAY_POLICY_CLASS", NeutralGatewayBusinessPolicy)
    return policy_class(config=config)


def _get_policy_registry() -> PolicyRegistryImpl:
    """获取策略注册表。"""
    global _default_policy_registry
    if _default_policy_registry is None:
        _default_policy_registry = PolicyRegistryImpl(
            policy_pack_path=get_config("POLICY_PACK_PATH"),
            allowed_scopes=set(get_config("POLICY_ALLOWED_SCOPES")),
            scope_inherits=dict(get_config("POLICY_SCOPE_INHERITS")),
        )
    return _default_policy_registry


def _get_route_policy() -> RouteTargetPolicyImpl:
    """获取路由策略。"""
    global _default_route_policy
    if _default_route_policy is None:
        _default_route_policy = RouteTargetPolicyImpl(
            WORKSPACE_ROOT,
            REPO_ROOT,
            global_rule_path=get_config("GLOBAL_RULE_PATH"),
            project_runtime_path=get_config("PROJECT_RUNTIME_ROOT").get(get_config("ROUTE_PROJECT_RUNTIME_SCOPE")),
        )
    return _default_route_policy


def _get_write_policy() -> WriteTargetPolicyImpl:
    """获取写入策略。"""
    global _default_write_policy
    if _default_write_policy is None:
        _default_write_policy = WriteTargetPolicyImpl(WORKSPACE_ROOT)
    return _default_write_policy


def _get_artifact_sink() -> ArtifactSinkImpl:
    """获取 artifact sink。"""
    from datetime import datetime

    return ArtifactSinkImpl(CONTEXT_ROOT, EVENT_LOG, datetime_module=datetime)


def _get_error_sink() -> ErrorSinkImpl:
    """获取 error sink。"""
    return ErrorSinkImpl(ERROR_LOG, now_iso_fn=now_iso)


def _resolve_route_target_via_policy(kind: str) -> str:
    """IF-5: Resolve route target via Policy facade."""
    return _get_route_policy().resolve(kind)


def _apply_hook_runtime_write_targets(targets: dict[str, Any]) -> dict[str, Any]:
    """Expose global lifecycle state without redirecting project memory writes."""
    updated = dict(targets)
    if os.environ.get("MEMORY_HOOK_GLOBAL_STATE_ROOT"):
        updated["hook_lifecycle"] = str(PROJECT_LIFECYCLE_ROOT)
        updated["hook_global_state_root"] = str(Path(os.environ["MEMORY_HOOK_GLOBAL_STATE_ROOT"]).expanduser())
    return updated


def _write_targets_via_policy() -> dict[str, Any]:
    """IF-5: Get write targets via Policy facade."""
    return _apply_hook_runtime_write_targets(_get_write_policy().get_targets())


def _get_policy_pack_via_registry(scope: str) -> dict[str, Any]:
    """IF-5: Get policy pack via PolicyRegistry facade."""
    return _get_policy_registry().get_policy_pack(scope)


def _resolve_policy_conflict_via_registry(
    policy_key: str,
    values: list[str],
    strategy: str | None = None,
) -> str:
    """IF-5: Resolve policy conflict via PolicyRegistry facade."""
    return _get_policy_registry().resolve_conflict(policy_key, values, strategy or "default")
