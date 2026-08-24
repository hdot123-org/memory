"""Version synchronization: patch ownership.toml memory_version across known projects.

Manual CLI tool invoked via `memory-sync-versions`.

M1: Gateway session-start probe added (probe_version_and_sync).
Called from _gateway_handlers.py session-start chain to auto-sync consumer versions.
INFRA-545: .sync.lock best-effort concurrency guard added around the
three-file patch + resign critical section (O_CREAT|O_EXCL, stale ~10s ignored).

Design note — path-index key limitation (M3):
    The path-index (``~/.memory-core/project-lifecycle/path-index.json``) uses
    the project's *cwd* as its key. This means:

    - **Stale entries**: directories that no longer exist (e.g. ``/tmp``
      sandboxes from validation runs, or deleted project folders) remain
      registered in the index and will be hit by ``sync_all_known_projects``.
    - **Missing registrations**: if a project is moved or its cwd changes,
      the old entry persists and the new location is not auto-registered.

    For these reasons, the gateway session-start probe **must use
    ``sync_single_project`` (single-project mode)** and must **never call
    ``sync_all_known_projects``**. Single-project mode bypasses the path-index
    entirely and operates only on the project whose hook is firing, avoiding
    stale/missing directory issues.
"""

import argparse
import contextlib
import json
import logging
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION

# Stale lock threshold (seconds): a .sync.lock older than this is considered
# abandoned (e.g. process crashed while holding it) and is ignored/broken.
SYNC_LOCK_STALE_SECONDS = 10.0

# Lock acquisition retry budget (seconds): give concurrent holders a short
# window to finish instead of failing fast on the first EEXIST.
SYNC_LOCK_WAIT_SECONDS = 2.0

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
    M1: Atomic write with tmp + os.replace.
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

    # Atomic write: tmp + os.replace
    tmp_path = ownership_path.with_suffix(".tmp")
    try:
        tmp_path.write_text(new_content, encoding="utf-8")
        os.replace(tmp_path, ownership_path)  # noqa: PTH105 - intentional atomic operation
    except OSError:
        # Clean up tmp on failure
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    return True


def patch_memory_lock(lock_path: Path, target_version: str) -> bool:
    """Patch memory_version and locked_at in memory.lock without rewriting the entire file.

    Returns True if patched, False if already up-to-date or skipped.
    M1: Atomic write with tmp + os.replace.
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
    now_iso = datetime.now(UTC).isoformat(timespec="seconds")
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

    # Atomic write: tmp + os.replace
    tmp_path = lock_path.with_suffix(".tmp")
    try:
        tmp_path.write_text(new_content, encoding="utf-8")
        os.replace(tmp_path, lock_path)  # noqa: PTH105 - intentional atomic operation
    except OSError:
        # Clean up tmp on failure
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    return True


def patch_adapter_toml_version(adapter_path: Path, target_version: str) -> bool:
    """Patch version under [core] section in adapter.toml without rewriting the entire file.

    Returns True if patched, False if already up-to-date or skipped.
    M1: Atomic write with tmp + os.replace.
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

    for _i, line in enumerate(lines):
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

    # Atomic write: tmp + os.replace
    tmp_path = adapter_path.with_suffix(".tmp")
    try:
        tmp_path.write_text(new_content, encoding="utf-8")
        os.replace(tmp_path, adapter_path)  # noqa: PTH105 - intentional atomic operation
    except OSError:
        # Clean up tmp on failure
        if tmp_path.exists():
            tmp_path.unlink()
        raise
    return True


def _gate_version_bump(current_version: str, target_version: str, schema_changed: bool) -> str:
    """Gate check for version upgrade.

    Returns "allowed" if upgrade is safe (patch/minor + schema unchanged).
    Returns "blocked:<reason>" if upgrade requires migration or is a downgrade.

    Args:
        current_version: Current memory_version
        target_version: Target memory_version
        schema_changed: Whether schema_version differs between current and target

    Returns:
        "allowed" or "blocked:major" or "blocked:schema_changed" or "blocked:downgrade"
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
        # Conservative: block if we can't parse
        return "blocked:major"

    # Major version bump -> blocked
    if target.major > current.major:
        return "blocked:major"

    # Downgrade (target < current) -> blocked
    if target < current:
        return "blocked:downgrade"

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
                report["errors"].append(
                    {
                        "path": local_path,
                        "name": project_name,
                        **error,
                    }
                )
        except Exception as exc:
            report["errors"].append({"path": local_path, "name": project_name, "reason": str(exc)})

    return report


@contextlib.contextmanager
def _sync_lock(project_path: Path) -> Any:
    """Best-effort per-project concurrency guard for version sync (INFRA-545).

    Acquires ``memory/system/.sync.lock`` via ``O_CREAT|O_EXCL``. Never blocks
    the caller indefinitely and never raises:

    - Lock acquired → yield ``True`` (caller owns the critical section).
    - Lock held by a live holder → retry briefly, then yield ``False``
      (caller should skip; the concurrent holder is syncing the same files).
    - Lock held but stale (mtime older than SYNC_LOCK_STALE_SECONDS) → break
      the stale lock and re-acquire → yield ``True``.
    - Any OSError (read-only fs, permission, dangling parent dir) → yield
      ``False`` (fail-safe: sync is skipped, main chain continues).

    Always releases the lock on exit if we own it.
    """
    lock_path = project_path / "memory" / "system" / ".sync.lock"
    owned = False
    deadline = time.monotonic() + SYNC_LOCK_WAIT_SECONDS

    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            # Lock exists: stale (abandoned) or held by a concurrent sync.
            try:
                age = time.time() - lock_path.stat().st_mtime
            except OSError:
                age = 0.0
            if age > SYNC_LOCK_STALE_SECONDS:
                # Stale lock: unlink and retry immediately (best-effort break;
                # a concurrent breaker may win the race, in which case the
                # next O_EXCL attempt by either party resolves ownership).
                with contextlib.suppress(OSError):
                    lock_path.unlink()
                continue
            if time.monotonic() >= deadline:
                break  # Live holder did not finish in time: skip
            time.sleep(0.05)
            continue
        except OSError:
            # Filesystem-level failure (read-only, permissions, missing dir):
            # fail-safe skip, never raise into the hook chain.
            break
        else:
            with contextlib.suppress(OSError):
                os.write(fd, f"{os.getpid()}".encode())
            os.close(fd)
            owned = True
            break

    try:
        yield owned
    finally:
        if owned:
            with contextlib.suppress(OSError):
                lock_path.unlink()


def _patch_three_files_under_lock(
    project_path: Path,
    ownership_path: Path,
    lock_path: Path,
    adapter_path: Path,
    current_version: str,
    target_version: str,
) -> dict[str, Any]:
    """INFRA-545: run the three-file patch + resign critical section under .sync.lock.

    Mutates and returns the caller's ``result`` dict. Handles:
    - lock contention → ``lock_skipped`` (no writes)
    - concurrent winner re-read → idempotent skip
    - external mid-flight edit → conservative skip
    - patch failures → recorded in ``errors``, never raised
    """
    result: dict[str, Any] = {"patched": False, "errors": []}

    with _sync_lock(project_path) as lock_acquired:
        if not lock_acquired:
            result["from"] = current_version
            result["to"] = target_version
            result["lock_skipped"] = True
            result["reason"] = "sync lock held by concurrent holder"
            return result

        # Re-read under lock: the concurrent winner may have already patched.
        locked_version = read_ownership_memory_version(ownership_path)
        if locked_version == target_version:
            result["reason"] = "already up-to-date"
            return result
        if locked_version is not None and locked_version != current_version:
            # State changed mid-flight (external edit): conservative skip
            result["from"] = current_version
            result["to"] = locked_version
            result["reason"] = "version changed concurrently; skipping"
            return result

        # Gate allowed: patch all three files
        changed_paths = []

        try:
            if patch_ownership_memory_version(ownership_path, target_version):
                changed_paths.append("memory/system/ownership.toml")
        except OSError as exc:
            result["errors"].append({"step": "patch_ownership", "reason": str(exc)})

        try:
            if lock_path.exists() and patch_memory_lock(lock_path, target_version):
                changed_paths.append("memory/system/memory.lock")
        except OSError as exc:
            result["errors"].append({"step": "patch_lock", "reason": str(exc)})

        try:
            if adapter_path.exists() and patch_adapter_toml_version(adapter_path, target_version):
                changed_paths.append("memory/system/adapter.toml")
        except OSError as exc:
            result["errors"].append({"step": "patch_adapter", "reason": str(exc)})

        if changed_paths:
            result["patched"] = True
            result["from"] = current_version
            result["to"] = target_version
            result["files_changed"] = changed_paths

            # Resign all changed files
            resign_result = _try_resign_all(project_path, changed_paths)
            if not resign_result["resigned"]:
                result["errors"].append(
                    {
                        "step": "resign",
                        "reason": resign_result["reason"],
                    }
                )
        else:
            result["reason"] = "no files changed"

    return result


def sync_single_project(
    project_path: Path,
    target_version: str = CURRENT_MEMORY_VERSION,
) -> dict[str, Any]:
    """Patch ownership.toml, memory.lock, and adapter.toml for a single project.

    Gate logic prevents automatic major/schema upgrades and downgrades.
    M1: Write failures caught and returned in errors list, never raise.
    INFRA-545: The three-file patch + resign critical section is guarded by a
    best-effort ``.sync.lock``; concurrent syncs on the same project are
    skipped (lock contention) instead of racing on the same files.

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
    # Use canonical memory lock schema as the target
    from memory_core.constants import CANONICAL_MEMORY_LOCK_SCHEMA

    schema_changed = current_schema is not None and current_schema != CANONICAL_MEMORY_LOCK_SCHEMA

    # Gate check
    gate_result = _gate_version_bump(current_version, target_version, schema_changed)

    if gate_result.startswith("blocked"):
        # Gate blocked: log warning and do NOT write any files
        # This applies to: major version bump, downgrade, schema change
        logging.warning(f"Version sync blocked: {gate_result} (current={current_version}, target={target_version})")
        result["patched"] = False
        result["from"] = current_version
        result["to"] = target_version
        result["gate_blocked"] = True
        result["gate_reason"] = gate_result
        result["reason"] = f"gate blocked: {gate_result}"
        return result

    # INFRA-545: best-effort concurrency guard around the write section.
    # On lock contention (concurrent session-start syncing the same project)
    # we skip entirely: the winner performs the identical patch.
    return _patch_three_files_under_lock(
        project_path,
        ownership_path,
        lock_path,
        adapter_path,
        current_version,
        target_version,
    )


def probe_version_and_sync(project_path: Path) -> dict[str, Any] | None:
    """Gateway session-start probe: detect version mismatch and auto-sync.

    M1: Called from _gateway_handlers.py session-start chain.
    Reads memory/system/memory.lock, compares with CURRENT_MEMORY_VERSION,
    and calls sync_single_project if mismatch detected.

    Fail-safe: any exception returns None, never blocks hook main chain.

    Returns:
        None if memory/system doesn't exist (skip)
        Dict with result if sync attempted
    """
    try:
        lock_path = project_path / "memory" / "system" / "memory.lock"
        if not lock_path.exists():
            # memory/system doesn't exist or no lock file: skip
            return None

        # Regex read memory_version from lock
        try:
            content = lock_path.read_text(encoding="utf-8")
        except OSError:
            # Can't read lock: skip
            return None

        match = re.search(r'^memory_version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if not match:
            # Can't parse lock: skip
            return None

        lock_version = match.group(1)
        if lock_version == CURRENT_MEMORY_VERSION:
            # Already at target: skip
            return None

        # Version mismatch: call sync_single_project
        return sync_single_project(project_path, CURRENT_MEMORY_VERSION)

    except Exception as exc:
        # Fail-safe: any exception returns None
        # Log for debugging but don't block hook main chain
        logging.debug("probe_version_and_sync failed: %s", exc)
        return None


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
    parser = argparse.ArgumentParser(description="Sync ownership.toml memory_version across all known projects.")
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
