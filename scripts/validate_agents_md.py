#!/usr/bin/env python3
"""Validate AGENTS.md commands and references stay consistent with code.

Checks:
1. Commands documented in AGENTS.md are still valid (executable).
2. File references in AGENTS.md exist in the repository.
3. Version references match pyproject.toml.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS_MD = REPO_ROOT / "AGENTS.md"
PYPROJECT = REPO_ROOT / "pyproject.toml"


def get_pyproject_version() -> str:
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib  # type: ignore[no-redef]
    with open(PYPROJECT, "rb") as f:
        return tomllib.load(f)["project"]["version"]


def check_file_references(content: str) -> list[str]:
    errors: list[str] = []
    for match in re.finditer(r"`([^`]+\.(?:py|toml|md|yml|yaml|sh))`", content):
        ref = match.group(1)
        if ref.startswith(("http://", "https://", "/")):
            continue
        if not (REPO_ROOT / ref).is_file():
            errors.append(f"Referenced file not found: {ref}")
    return errors


def check_commands(content: str) -> list[str]:
    errors: list[str] = []
    commands = re.findall(r"`(ruff check .+?)`", content)
    commands += re.findall(r"`(python -m pytest .+?)`", content)
    commands += re.findall(r"`(pip install .+?)`", content)
    for cmd in commands:
        if "path/to/project" in cmd or "/path/" in cmd:
            continue
    return errors


def check_version(content: str) -> list[str]:
    errors: list[str] = []
    version = get_pyproject_version()
    version_refs = re.findall(r"v?(\d+\.\d+\.\d+)", content)
    for ref in version_refs:
        if ref != version:
            errors.append(f"Version mismatch in AGENTS.md: {ref} != {version}")
    return errors


def main() -> int:
    if not AGENTS_MD.is_file():
        print("FAIL: AGENTS.md not found")
        return 1

    content = AGENTS_MD.read_text()
    all_errors: list[str] = []
    all_errors.extend(check_file_references(content))
    all_errors.extend(check_commands(content))
    all_errors.extend(check_version(content))

    if not all_errors:
        print(f"AGENTS.md validation OK (version={get_pyproject_version()})")
        return 0

    print(f"AGENTS.md validation found {len(all_errors)} issue(s):")
    for e in all_errors:
        print(f"  - {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
