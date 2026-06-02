"""Version synchronization: patch ownership.toml memory_version across known projects.

Triggered automatically by the hook wrapper when it detects a version mismatch
between the installed memory-core package and a project's ownership.toml.
Can also be invoked manually via `memory-sync-versions`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from memory_core.constants import CURRENT_MEMORY_VERSION


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
    """Iterate all registered projects and patch ownership.toml if version is stale.

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
            ownership_path = Path(local_path) / "memory" / "system" / "ownership.toml"
            current_version = read_ownership_memory_version(ownership_path)
            if current_version is None:
                report["skipped"].append({"path": local_path, "name": project_name, "reason": "no ownership.toml"})
                continue
            if current_version == target_version:
                report["skipped"].append({"path": local_path, "name": project_name, "reason": "already up-to-date"})
                continue
            if patch_ownership_memory_version(ownership_path, target_version):
                report["patched"].append({"path": local_path, "name": project_name, "from": current_version, "to": target_version})
            else:
                report["errors"].append({"path": local_path, "name": project_name, "reason": "patch failed"})
        except Exception as exc:
            report["errors"].append({"path": local_path, "name": project_name, "reason": str(exc)})

    return report


def sync_single_project(
    project_path: Path,
    target_version: str = CURRENT_MEMORY_VERSION,
) -> dict[str, Any]:
    """Patch ownership.toml for a single project.

    Returns a simple result dict.
    """
    ownership_path = project_path / "memory" / "system" / "ownership.toml"
    current_version = read_ownership_memory_version(ownership_path)

    if current_version is None:
        return {"patched": False, "reason": "no ownership.toml"}
    if current_version == target_version:
        return {"patched": False, "reason": "already up-to-date", "version": current_version}
    if patch_ownership_memory_version(ownership_path, target_version):
        return {"patched": True, "from": current_version, "to": target_version}
    return {"patched": False, "reason": "patch failed"}


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
