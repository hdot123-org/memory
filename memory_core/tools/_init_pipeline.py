"""Initialization pipeline: validation, dry-run, and directory creation."""

import logging
import subprocess
from pathlib import Path
from typing import Any

from memory_core.ownership import (
    Owned,
    classify_owned_path,
)
from memory_core.tools.denylist import check_denylist

from ._init_config import (
    DIRECTORY_STRUCTURE,
    ESSENTIAL_FILES,
    KB_TEMPLATES,
    RUNTIME_EXTRA_FILES,
    RUNTIME_KB_FILES,
)

logger = logging.getLogger(__name__)


def _validate_init_args(
    target: Path,
    mode: str,
    no_clobber: bool,
    allow_non_git: bool,
    memory_root: Path,
    project_name: str,
) -> tuple[bool, str]:
    """Validate initialization arguments and check denylist/no-clobber.

    Returns:
        Tuple of (is_valid, error_message). If is_valid is False, error_message explains why.
    """
    # Mode validation
    if mode not in ("create", "adopt", "update", "repair"):
        return False, f"Invalid mode: {mode}. Must be one of: create, adopt, update, repair"

    # Denylist check
    deny_result = check_denylist(target, allow_non_git=allow_non_git)
    if deny_result.denied:
        return False, f"Project denied by denylist rule '{deny_result.rule}': {deny_result.message}"

    # No-clobber check (only for create mode)
    if no_clobber and mode == "create":
        existing_essential = []
        for fname in ESSENTIAL_FILES:
            if (memory_root / fname).exists():
                existing_essential.append(fname)
        for fname in RUNTIME_KB_FILES:
            if (target / fname).exists():
                existing_essential.append(fname)
        scope_file = f"memory/kb/projects/{project_name}.md"
        if (target / scope_file).exists():
            existing_essential.append(scope_file)
        if existing_essential:
            return False, (
                f"refused to clobber existing memory/system/; use --force to overwrite "
                f"or remove existing files first. Existing files: {', '.join(existing_essential)}"
            )

    return True, ""


def _dry_run_action(
    file_path: Path,
    mode: str,
    force: bool,
    is_business_file: bool = False,
    is_marker_protected: bool = False,
) -> str:
    """Determine action for dry-run based on mode, file existence, and file type."""
    exists = file_path.exists()

    if mode == "adopt":
        return "skip - exists (adopt mode preserves existing)" if exists else "create"

    if mode == "update":
        if is_business_file:
            return "skip - business file (update mode preserves)"
        if exists:
            return "replace marker block" if is_marker_protected else "skip - exists (update mode preserves non-marker files)"
        return "create"

    if mode == "repair":
        return "skip - exists (repair mode never overwrites)" if exists else "create"

    # create mode
    if exists:
        return "overwrite" if force else "skip - exists"
    return "create"


def _build_dry_run_result(
    target: Path,
    mode: str,
    force: bool,
    project_name: str,
    memory_root: Path,
) -> dict[str, Any]:
    """Build dry-run output showing what would be created."""
    dry_run_output: dict[str, Any] = {
        "would_create_dirs": list(DIRECTORY_STRUCTURE),
        "would_create_files": [],
        "project_name": project_name,
    }

    # Check all file categories
    for fname in ESSENTIAL_FILES:
        action = _dry_run_action(memory_root / fname, mode, force)
        dry_run_output["would_create_files"].append(f"{fname} ({action})")

    for fname in RUNTIME_KB_FILES:
        action = _dry_run_action(target / fname, mode, force)
        dry_run_output["would_create_files"].append(f"{fname} ({action})")

    scope_file = f"memory/kb/projects/{project_name}.md"
    action = _dry_run_action(target / scope_file, mode, force)
    dry_run_output["would_create_files"].append(f"{scope_file} ({action})")

    for fname in KB_TEMPLATES:
        is_business = fname == "INDEX.md" or fname.startswith("project-map/")
        action = _dry_run_action(target / fname, mode, force, is_business_file=is_business)
        dry_run_output["would_create_files"].append(f"{fname} ({action})")

    for fname in RUNTIME_EXTRA_FILES:
        action = _dry_run_action(target / fname, mode, force)
        dry_run_output["would_create_files"].append(f"{fname} ({action})")

    per_scope_dir = f"memory/kb/projects/{project_name}"
    dry_run_output["would_create_dirs"].append(f"{per_scope_dir}/")
    for scope_file in ("CANONICAL.md", "STATE.md", "PLAN.md", "TASKS.md"):
        action = _dry_run_action(target / per_scope_dir / scope_file, mode, force)
        dry_run_output["would_create_files"].append(f"{per_scope_dir}/{scope_file} ({action})")

    action = _dry_run_action(target / "NOW.md", mode, force)
    dry_run_output["would_create_files"].append(f"NOW.md ({action})")

    return dry_run_output


def _should_skip_file(
    file_path: Path,
    mode: str,
    force: bool,
    ownership: Any,
    authorized_maintenance: bool,
    target: Path,
    result: dict[str, Any],
    is_business_file: bool = False,
) -> tuple[bool, str]:
    """Determine if file should be skipped based on mode.

    Returns (should_skip, reason)
    """
    if not file_path.exists():
        return False, "create"

    if mode == "adopt":
        return True, f"{mode} mode preserves existing"

    if mode == "update":
        if is_business_file:
            return True, f"{mode} mode preserves business files"
        if force:
            return False, "overwrite"
        return True, f"{mode} mode preserves existing (use --force to overwrite)"

    if mode == "repair":
        return True, f"{mode} mode only creates missing files"

    # create mode with force
    if force:
        try:
            rel_path = file_path.relative_to(target).as_posix()
        except ValueError:
            rel_path = str(file_path)
        classification = classify_owned_path(rel_path, ownership=ownership)
        if isinstance(classification, Owned) and not authorized_maintenance:
            result["errors"].append(f"Force overwrite rejected: {rel_path} is owned ({classification.reason})")
            return True, "force rejected - owned file"
        return False, "overwrite"

    return True, "already exists"


def _write_template_file(
    file_path: Path,
    fname: str,
    template_fn: Any,
    project_name: str,
    mode: str,
    force: bool,
    ownership: Any,
    authorized_maintenance: bool,
    target: Path,
    result: dict[str, Any],
    is_business_file: bool = False,
    decorate_fn: Any = None,
) -> tuple[bool, bool]:
    """Write a single template file with mode-aware handling.

    Returns (was_overwritten, was_skipped)
    """
    was_overwritten = False
    was_skipped = False

    file_exists_before = file_path.exists()

    should_skip, reason = _should_skip_file(
        file_path, mode, force, ownership, authorized_maintenance, target, result, is_business_file
    )

    if file_exists_before and should_skip:
        result["skipped"].append(f"file:{fname} ({reason})")
        return False, True

    try:
        content, warnings = template_fn(project_name)
        if decorate_fn:
            content = decorate_fn(fname, content)

        if file_exists_before:
            result["created"].append(f"file:{fname} (overwritten)")
            was_overwritten = True
        else:
            result["created"].append(f"file:{fname}")

        file_path.write_text(content, encoding="utf-8")
        result["warnings"].extend(warnings)
    except Exception as exc:
        action = "overwrite" if file_exists_before else "create"
        result["errors"].append(f"failed to {action} {fname}: {exc}")

    return was_overwritten, was_skipped


def _create_directories(target: Path, result: dict[str, Any]) -> None:
    """Create directory structure and .keep files."""
    for dir_rel in DIRECTORY_STRUCTURE:
        dir_path = target / dir_rel
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            result["created"].append(f"dir:{dir_rel}")
        except Exception as exc:
            result["errors"].append(f"failed to create {dir_rel}: {exc}")

    for dir_rel in DIRECTORY_STRUCTURE:
        if dir_rel in ("memory", "memory/system"):
            continue
        keep_path = target / dir_rel / ".keep"
        if not keep_path.exists():
            try:
                keep_path.write_text("", encoding="utf-8")
                result["created"].append(f"file:{dir_rel}/.keep")
            except Exception as exc:
                result["errors"].append(f"failed to create {dir_rel}/.keep: {exc}")


def _find_repo_root(start_path: Path) -> Path | None:
    """Find the root of the git repository containing start_path.

    Returns:
        Path to the git root, or None if not in a git repository.
    """
    try:
        result = subprocess.run(
            ["git", "-C", str(start_path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def _is_memory_repo(repo_root: Path) -> bool:
    """Heuristic: is this repo the memory repo?

    Requires the memory_hook_gateway.py marker (unique to this repo)
    AND either the memory/ directory or memory_core/ package.
    """
    gateway_marker = repo_root / "memory_core" / "tools" / "memory_hook_gateway.py"
    if not gateway_marker.is_file():
        return False
    # Memory repo has both: gateway + repo-root memory/ directory
    return (repo_root / "memory").is_dir()

