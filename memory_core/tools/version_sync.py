"""Version synchronization: patch ownership.toml memory_version across known projects.

Manual CLI tool invoked via `memory-sync-versions`. Currently there is no hook
auto-trigger; version_sync is not called from the session-start handler.
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION

# Re-sign modules (ImportError 时静默跳过，不阻塞版本同步)
try:
    from memory_core.tools.memory_hook_integrity_keys import load_key
    from memory_core.tools.memory_hook_integrity_manifest import sign_project_incremental
except ImportError:
    sign_project_incremental = None  # type: ignore[assignment]
    load_key = None  # type: ignore[assignment]


def read_ownership_memory_version(ownership_path: Path) -> str | None:
    """Read memory_version from an ownership.toml file.

    Returns None if file doesn't exist or field not found.
    """
    if not ownership_path.exists():
        return None
    try:
        content = ownership_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^memory_version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else None


def patch_ownership_memory_version(ownership_path: Path, target_version: str) -> bool:
    """Patch memory_version in ownership.toml without rewriting the entire file.

    Returns True if patched, False if already up-to-date or skipped.
    """
    if not ownership_path.exists():
        return False
    try:
        content = ownership_path.read_text(encoding="utf-8")
    except OSError:
        return False

    new_content, count = re.subn(
        r'^(memory_version\s*=\s*)"[^"]+"',
        rf'\g<1>"{target_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0 or new_content == content:
        return False
    ownership_path.write_text(new_content, encoding="utf-8")
    return True


def patch_memory_lock(lock_path: Path, target_version: str) -> bool:
    """Patch memory_version and locked_at in memory.lock without rewriting the entire file.

    Returns True if patched, False if already up-to-date or skipped.
    """
    if not lock_path.exists():
        return False
    try:
        content = lock_path.read_text(encoding="utf-8")
    except OSError:
        return False

    # Check if already at target version
    match = re.search(r'^memory_version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if match and match.group(1) == target_version:
        return False

    # Patch memory_version
    new_content, count1 = re.subn(
        r'^(memory_version\s*=\s*)"[^"]+"',
        rf'\g<1>"{target_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if count1 == 0:
        return False

    # Patch locked_at to current timestamp
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_content, count2 = re.subn(
        r'^(locked_at\s*=\s*)"[^"]+"',
        rf'\g<1>"{now_iso}"',
        new_content,
        count=1,
        flags=re.MULTILINE,
    )
    if count2 == 0:
        # locked_at field missing or couldn't be patched
        return False

    lock_path.write_text(new_content, encoding="utf-8")
    return True


def patch_adapter_toml_version(adapter_path: Path, target_version: str) -> bool:
    """Patch version under [core] section in adapter.toml without rewriting the entire file.

    Returns True if patched, False if already up-to-date or skipped.
    """
    if not adapter_path.exists():
        return False
    try:
        content = adapter_path.read_text(encoding="utf-8")
    except OSError:
        return False

    # Find [core] section and patch version within it
    lines = content.splitlines(keepends=True)
    in_core_section = False
    patched_lines = []
    version_found = False
    version_already_correct = False

    for i, line in enumerate(lines):
        if line.strip() == "[core]":
            in_core_section = True
            patched_lines.append(line)
            continue

        if in_core_section and line.strip().startswith("["):
            # Left [core] section
            in_core_section = False

        if in_core_section and not version_found:
            match = re.match(r'^(version\s*=\s*)"([^"]+)"', line)
            if match:
                version_found = True
                if match.group(2) == target_version:
                    version_already_correct = True
                    patched_lines.append(line)
                else:
                    new_line = f'{match.group(1)}"{target_version}"\n'
                    patched_lines.append(new_line)
                continue

        patched_lines.append(line)

    if not version_found or version_already_correct:
        return False

    new_content = "".join(patched_lines)
    adapter_path.write_text(new_content, encoding="utf-8")
    return True


def _gate_version_bump(
    current_version: str, target_version: str, schema_changed: bool
) -> str:
    """Gate check for version upgrade.

    Returns "allowed" if upgrade is safe (patch/minor + schema unchanged).
    Returns "blocked:<reason>" if upgrade requires migration.

    Args:
        current_version: Current memory_version
        target_version: Target memory_version
        schema_changed: Whether schema_version differs between current and target

    Returns:
        "allowed" or "blocked:major" or "blocked:schema_changed"
    """
    # Check schema change first (highest priority)
    if schema_changed:
        return "blocked:schema_changed"

    # Parse versions for SemVer comparison
    try:
        from packaging.version import Version

        current = Version(current_version)
        target = Version(target_version)
    except Exception:
        # Fallback: simple string comparison if packaging unavailable
        if current_version == target_version:
            return "allowed"
        return "blocked:major"

    # Major version bump -> blocked
    if target.major > current.major:
        return "blocked:major"

    # Minor/patch bump -> allowed
    return "allowed"


def _read_lock_schema_version(lock_path: Path) -> str | None:
    """Read schema_version from memory.lock file."""
    if not lock_path.exists():
        return None
    try:
        content = lock_path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'^schema_version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    return match.group(1) if match else None


def _read_adapter_version(adapter_path: Path) -> str | None:
    """Read version from [core] section of adapter.toml."""
    if not adapter_path.exists():
        return None
    try:
        content = adapter_path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Find [core] section
    lines = content.splitlines()
    in_core = False
    for line in lines:
        if line.strip() == "[core]":
            in_core = True
            continue
        if in_core and line.strip().startswith("["):
            break
        if in_core:
            match = re.match(r'^version\s*=\s*"([^"]+)"', line)
            if match:
                return match.group(1)
    return None


def load_path_index(lifecycle_root: Path) -> dict[str, Any]:
    """Load path-index.json from the lifecycle root."""
    path = lifecycle_root / "project-lifecycle" / "path-index.json"
    if not path.exists():
        return {"paths": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"paths": {}}
    return data if isinstance(data, dict) else {"paths": {}}


def sync_all_known_projects(
    lifecycle_root: Path | None = None,
    target_version: str = CURRENT_MEMORY_VERSION,
) -> dict[str, Any]:
    """Iterate all registered projects and patch three files if version is stale.

    Returns a report dict with patched/skipped/errors lists.
    """
    if lifecycle_root is None:
        lifecycle_root = Path("~/.memory-core").expanduser()

    report: dict[str, Any] = {
        "target_version": target_version,
        "patched": [],
        "skipped": [],
        "errors": [],
    }

    path_index = load_path_index(lifecycle_root)
    paths = path_index.get("paths", {})
    if not isinstance(paths, dict):
        return report

    for local_path, entry in paths.items():
        if not isinstance(entry, dict):
            continue
        project_name = entry.get("project_name", "unknown")
        try:
            project_path = Path(local_path)
            ownership_path = project_path / "memory" / "system" / "ownership.toml"
            current_version = read_ownership_memory_version(ownership_path)
            if current_version is None:
                report["skipped"].append({"path": local_path, "name": project_name, "reason": "no ownership.toml"})
                continue
            if current_version == target_version:
                report["skipped"].append({"path": local_path, "name": project_name, "reason": "already up-to-date"})
                continue

            # Use sync_single_project for three-file patch logic
            result = sync_single_project(project_path, target_version)

            if result.get("patched"):
                entry_data = {
                    "path": local_path,
                    "name": project_name,
                    "from": current_version,
                    "to": target_version,
                }
                if result.get("gate_blocked"):
                    entry_data["gate_blocked"] = True
                    entry_data["gate_reason"] = result.get("gate_reason", "")
                if result.get("files_changed"):
                    entry_data["files_changed"] = result["files_changed"]
                report["patched"].append(entry_data)

            # Propagate errors from sync_single_project
            for error in result.get("errors", []):
                report["errors"].append({
                    "path": local_path,
                    "name": project_name,
                    **error,
                })
        except Exception as exc:
            report["errors"].append({"path": local_path, "name": project_name, "reason": str(exc)})

    return report


def sync_single_project(
    project_path: Path,
    target_version: str = CURRENT_MEMORY_VERSION,
) -> dict[str, Any]:
    """Patch ownership.toml, memory.lock, and adapter.toml for a single project.

    Gate logic prevents automatic major/schema upgrades.

    Returns a result dict with patched/blocked/errors.
    """
    result: dict[str, Any] = {"patched": False, "errors": []}

    # Check ownership.toml exists
    ownership_path = project_path / "memory" / "system" / "ownership.toml"
    if not ownership_path.exists():
        result["reason"] = "no ownership.toml"
        return result

    # Read current versions
    current_version = read_ownership_memory_version(ownership_path)
    if current_version is None:
        result["reason"] = "cannot read memory_version from ownership.toml"
        return result

    # Idempotent: already at target?
    if current_version == target_version:
        result["patched"] = False
        result["reason"] = "already up-to-date"
        return result

    # Check lock and adapter files
    lock_path = project_path / "memory" / "system" / "memory.lock"
    adapter_path = project_path / "memory" / "system" / "adapter.toml"

    # Read schema_version from lock to detect schema change
    current_schema = _read_lock_schema_version(lock_path)
    # Compare with target schema - if different, mark as changed
    # Use canonical schema schema version as the target
    from memory_core.constants import CANONICAL_MEMORY_LOCK_SCHEMA
    schema_changed = current_schema is not None and current_schema != CANONICAL_MEMORY_LOCK_SCHEMA

    # Gate check
    gate_result = _gate_version_bump(current_version, target_version, schema_changed)

    if gate_result.startswith("blocked"):
        # Gate blocked: only patch ownership.toml (backward compatibility)
        if patch_ownership_memory_version(ownership_path, target_version):
            result["patched"] = True
            result["from"] = current_version
            result["to"] = target_version
            result["gate_blocked"] = True
            result["gate_reason"] = gate_result

            # Resign ownership.toml only
            resign_result = _try_resign_all(project_path, ["memory/system/ownership.toml"])
            if not resign_result["resigned"]:
                result["errors"].append({
                    "step": "resign",
                    "reason": resign_result["reason"],
                })
        else:
            result["reason"] = "patch failed"
        return result

    # Gate allowed: patch all three files
    changed_paths = []

    if patch_ownership_memory_version(ownership_path, target_version):
        changed_paths.append("memory/system/ownership.toml")

    if lock_path.exists():
        if patch_memory_lock(lock_path, target_version):
            changed_paths.append("memory/system/memory.lock")

    if adapter_path.exists():
        if patch_adapter_toml_version(adapter_path, target_version):
            changed_paths.append("memory/system/adapter.toml")

    if changed_paths:
        result["patched"] = True
        result["from"] = current_version
        result["to"] = target_version
        result["files_changed"] = changed_paths

        # Resign all changed files
        resign_result = _try_resign_all(project_path, changed_paths)
        if not resign_result["resigned"]:
            result["errors"].append({
                "step": "resign",
                "reason": resign_result["reason"],
            })
    else:
        result["reason"] = "no files changed"

    return result


def _try_resign_all(project_path: Path, changed_paths: list[str]) -> dict[str, Any]:
    """Re-sign changed files after version patch to keep manifest hash in sync.

    Args:
        project_path: Absolute path to project root
        changed_paths: List of relative paths that were modified

    Returns:
        Dict with "resigned" (bool) and "reason" (str) keys.
        Never silently swallows errors.
    """
    if sign_project_incremental is None or load_key is None:
        return {"resigned": False, "reason": "signing module unavailable"}
    try:
        key = load_key()
        if key is None:
            return {"resigned": False, "reason": "no signing key available"}
        sign_project_incremental(
            project_path,
            key,
            changed_paths=changed_paths,
        )
        return {"resigned": True, "paths": changed_paths}
    except Exception as exc:
        # Return error dict instead of silently swallowing
        return {"resigned": False, "reason": str(exc)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync ownership.toml memory_version across all known projects."
    )
    parser.add_argument(
        "--target",
        type=Path,
        default=None,
        help="Sync a single project path instead of all known projects.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON.",
    )
    args = parser.parse_args(argv)

    if args.target:
        target = args.target.resolve()
        if not target.is_dir():
            print(f"Error: {target} is not a directory", file=sys.stderr)
            return 2
        result = sync_single_project(target)
    else:
        result = sync_all_known_projects()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if "patched" in result and isinstance(result.get("patched"), list):
            for entry in result.get("patched", []):
                print(f"  [PATCH] {entry['name']}: {entry['from']} -> {entry['to']}")
            for entry in result.get("skipped", []):
                print(f"  [SKIP]  {entry['name']}: {entry['reason']}")
            for entry in result.get("errors", []):
                print(f"  [ERROR] {entry['name']}: {entry['reason']}")
        else:
            if result.get("patched"):
                print(f"Patched: {result['from']} -> {result['to']}")
            else:
                print(f"Skipped: {result.get('reason', 'unknown')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
