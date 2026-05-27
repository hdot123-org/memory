#!/usr/bin/env python3
"""Scan for TODO/FIXME/HACK markers in source code.

Enforces policy: TODO comments should reference an issue number.
Example: TODO(GH-123) or TODO(#456)
"""
import re
import sys
from pathlib import Path

PATTERNS = [
    (re.compile(r"#\s*TODO(?!\s*[\(#])", re.IGNORECASE), "TODO without issue reference"),
    (re.compile(r"#\s*FIXME(?!\s*[\(#])", re.IGNORECASE), "FIXME without issue reference"),
    (re.compile(r"#\s*HACK", re.IGNORECASE), "HACK marker found"),
]

EXCLUDE_DIRS = {"__pycache__", ".git", "node_modules", "dist", "build", ".pytest_cache", ".ruff_cache", "archive", "workspace"}


def scan(root: Path) -> list[tuple[Path, int, str, str]]:
    findings: list[tuple[Path, int, str, str]] = []
    for py_file in root.rglob("*.py"):
        if any(p in py_file.parts for p in EXCLUDE_DIRS):
            continue
        for i, line in enumerate(py_file.read_text(errors="replace").splitlines(), 1):
            for pattern, label in PATTERNS:
                if pattern.search(line):
                    findings.append((py_file, i, label, line.strip()))
    return findings


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    findings = scan(root)
    if not findings:
        print("No unlinked TODO/FIXME/HACK markers found.")
        return 0

    print(f"Found {len(findings)} tech debt marker(s):\n")
    for path, lineno, label, line in findings:
        rel = path.relative_to(root)
        print(f"  {rel}:{lineno} [{label}]")
        print(f"    {line}\n")

    print("Policy: TODO/FIXME should reference an issue. Examples: TODO(#123), FIXME(GH-456)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
