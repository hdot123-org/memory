#!/usr/bin/env python3
"""Validate a project's .memory/ directory structure and integrity.

Usage:
    python validate_project_memory.py --target /path/to/project
    python validate_project_memory.py --target /path/to/project --json
    python validate_project_memory.py --target /path/to/project --dry-run

Checks performed:
    1. Required files existence (memory.lock, adapter.toml, CANONICAL.md,
       PLAN.md, STATE.md, TASKS.md, migrations.log)
    2. Frontmatter / schema validation on Markdown files
    3. Lock/adapter version compatibility
    4. Pollution guard (no business state written into memory repo)

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Required files inside .memory/
REQUIRED_FILES = [
    "memory.lock",
    "adapter.toml",
    "CANONICAL.md",
    "PLAN.md",
    "STATE.md",
    "TASKS.md",
    "migrations.log",
]

# Expected frontmatter fields per file type
FRONTMATTER_REQUIREMENTS: dict[str, list[str]] = {
    "CANONICAL.md": ["type", "title", "shortname", "status", "created", "updated"],
    "PLAN.md": ["type", "title", "shortname", "status", "created"],
    "STATE.md": ["type", "title", "shortname", "status", "updated"],
    "TASKS.md": ["type", "title", "shortname", "status"],
}

# Current schema version for the memory system
CURRENT_MEMORY_VERSION = "0.2.0"

# Paths that MUST NOT appear inside the memory repo — these belong in the
# target project's own workspace, not in the memory repository.
POLLUTION_PATTERNS = [
    re.compile(r"node_modules", re.IGNORECASE),
    re.compile(r"__pycache__", re.IGNORECASE),
    re.compile(r"\.venv", re.IGNORECASE),
    re.compile(r"target/", re.IGNORECASE),  # Rust/Cargo
    re.compile(r"\\.gradle", re.IGNORECASE),
    re.compile(r"\.DS_Store", re.IGNORECASE),
    re.compile(r"\\.git/", re.IGNORECASE),
]

# Sub-paths inside .memory/ that are expected directories
EXPECTED_DIRS = [
    "kb/projects",
    "kb/decisions",
    "kb/lessons",
    "kb/global",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter as a flat dict.

    Supports simple key: value pairs. Does not attempt full YAML parsing.
    """
    result: dict[str, str] = {}
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return result
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kv = line.split(":", 1)
        if len(kv) == 2:
            key = kv[0].strip()
            val = kv[1].strip().strip('"').strip("'")
            result[key] = val
    return result


def _is_json_like(text: str) -> bool:
    """Quick heuristic: text looks like JSON if it starts with { or [."""
    stripped = text.strip()
    return stripped.startswith("{") or stripped.startswith("[")


def _parse_lock_file(path: Path) -> dict[str, str]:
    """Parse memory.lock as JSON or key=value lines."""
    text = path.read_text(encoding="utf-8")
    if _is_json_like(text):
        data = json.loads(text)
        return {str(k): str(v) for k, v in data.items()}
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kv = line.split("=", 1)
        if len(kv) == 2:
            result[kv[0].strip()] = kv[1].strip()
    return result


def _parse_adapter_toml(path: Path) -> dict[str, str]:
    """Parse adapter.toml as simple key=value (no full TOML dependency)."""
    result: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    in_section = ""
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        section_m = re.match(r"^\[(.+)\]$", stripped)
        if section_m:
            in_section = section_m.group(1)
            continue
        kv = stripped.split("=", 1)
        if len(kv) == 2:
            key = kv[0].strip()
            val = kv[1].strip().strip('"').strip("'")
            full_key = f"{in_section}.{key}" if in_section else key
            result[full_key] = val
    return result


def _check_pollution(memory_root: Path) -> list[str]:
    """Scan all files under memory_root for pollution patterns."""
    violations: list[str] = []
    for f in memory_root.rglob("*"):
        if not f.is_file():
            continue
        # Check the file path itself
        rel = str(f.relative_to(memory_root))
        for pat in POLLUTION_PATTERNS:
            if pat.search(rel):
                violations.append(f"pollution: path matches pattern in {rel}")
        # Check file contents for references to business-state paths
        if f.suffix in (".md", ".toml", ".json", ".lock", ".log", ".txt"):
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for line_no, line in enumerate(content.splitlines(), 1):
                for pat in POLLUTION_PATTERNS:
                    if pat.search(line):
                        violations.append(
                            f"pollution: {rel}:{line_no} contains '{pat.pattern}'"
                        )
    return violations


# ---------------------------------------------------------------------------
# Check classes
# ---------------------------------------------------------------------------

class CheckResult:
    """Collects individual check results and produces structured output."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def record(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append({"name": name, "passed": passed, "detail": detail})

    @property
    def all_passed(self) -> bool:
        return all(c["passed"] for c in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "checks": self.checks,
            "total": len(self.checks),
            "passed": sum(1 for c in self.checks if c["passed"]),
            "failed": sum(1 for c in self.checks if not c["passed"]),
        }

    def to_text(self) -> str:
        lines: list[str] = []
        lines.append("=" * 60)
        lines.append("Project Memory Validation Report")
        lines.append("=" * 60)
        for c in self.checks:
            mark = "PASS" if c["passed"] else "FAIL"
            line = f"  [{mark}] {c['name']}"
            if c["detail"]:
                line += f" — {c['detail']}"
            lines.append(line)
        lines.append("-" * 60)
        d = self.to_dict()
        lines.append(f"  {d['passed']}/{d['total']} checks passed")
        lines.append("=" * 60)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_required_files(memory_root: Path, result: CheckResult) -> bool:
    """Verify all required files exist inside .memory/."""
    all_ok = True
    for fname in REQUIRED_FILES:
        fpath = memory_root / fname
        if fpath.is_file():
            result.record(f"file:{fname}", True)
        else:
            result.record(f"file:{fname}", False, f"missing: {fpath}")
            all_ok = False
    return all_ok


def check_required_dirs(memory_root: Path, result: CheckResult) -> bool:
    """Verify expected directory structure exists."""
    all_ok = True
    for dname in EXPECTED_DIRS:
        dpath = memory_root / dname
        if dpath.is_dir():
            result.record(f"dir:{dname}", True)
        else:
            result.record(f"dir:{dname}", False, f"missing directory: {dpath}")
            all_ok = False
    return all_ok


def check_frontmatter(memory_root: Path, result: CheckResult) -> bool:
    """Verify Markdown files have required frontmatter fields."""
    all_ok = True
    for fname, required_keys in FRONTMATTER_REQUIREMENTS.items():
        fpath = memory_root / fname
        if not fpath.is_file():
            # Already reported by check_required_files; skip here
            continue
        text = fpath.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        missing = [k for k in required_keys if k not in fm]
        if missing:
            result.record(f"frontmatter:{fname}", False, f"missing keys: {missing}")
            all_ok = False
        else:
            result.record(f"frontmatter:{fname}", True, f"{len(required_keys)} keys present")
    return all_ok


def check_lock_version(memory_root: Path, result: CheckResult) -> bool:
    """Verify memory.lock version matches current schema."""
    lock_path = memory_root / "memory.lock"
    if not lock_path.is_file():
        result.record("lock_version", False, "memory.lock not found")
        return False
    try:
        lock_data = _parse_lock_file(lock_path)
    except Exception as exc:
        result.record("lock_version", False, f"parse error: {exc}")
        return False

    version = lock_data.get("version", lock_data.get("schema_version", ""))
    if not version:
        result.record("lock_version", False, "no version key in memory.lock")
        return False

    if version == CURRENT_MEMORY_VERSION:
        result.record("lock_version", True, f"version={version}")
        return True
    else:
        result.record(
            "lock_version",
            False,
            f"version mismatch: lock={version}, expected={CURRENT_MEMORY_VERSION}",
        )
        return False


def check_adapter_version(memory_root: Path, result: CheckResult) -> bool:
    """Verify adapter.toml version is compatible."""
    adapter_path = memory_root / "adapter.toml"
    if not adapter_path.is_file():
        result.record("adapter_version", False, "adapter.toml not found")
        return False
    try:
        adapter_data = _parse_adapter_toml(adapter_path)
    except Exception as exc:
        result.record("adapter_version", False, f"parse error: {exc}")
        return False

    version = adapter_data.get("core.version", adapter_data.get("version", ""))
    if not version:
        result.record("adapter_version", False, "no version key in adapter.toml")
        return False

    if version == CURRENT_MEMORY_VERSION:
        result.record("adapter_version", True, f"version={version}")
        return True
    else:
        result.record(
            "adapter_version",
            False,
            f"version mismatch: adapter={version}, expected={CURRENT_MEMORY_VERSION}",
        )
        return False


def check_pollution(memory_root: Path, result: CheckResult) -> bool:
    """Verify no business-state pollution in memory repo."""
    violations = _check_pollution(memory_root)
    if violations:
        for v in violations:
            result.record("pollution_guard", False, v)
        return False
    result.record("pollution_guard", True, "no pollution detected")
    return True


def check_migrations_log(memory_root: Path, result: CheckResult) -> bool:
    """Verify migrations.log is parseable."""
    log_path = memory_root / "migrations.log"
    if not log_path.is_file():
        result.record("migrations_log", False, "migrations.log not found")
        return False
    try:
        text = log_path.read_text(encoding="utf-8").strip()
        if not text:
            result.record("migrations_log", False, "migrations.log is empty")
            return False
        # Each line should be a migration record
        lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
        result.record("migrations_log", True, f"{len(lines)} migration records")
        return True
    except Exception as exc:
        result.record("migrations_log", False, f"read error: {exc}")
        return False


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------

def validate_project_memory(
    target: Path,
    *,
    dry_run: bool = False,
) -> CheckResult:
    """Run all validation checks on a project's .memory/ directory.

    Args:
        target: Path to the target project root (must contain .memory/).
        dry_run: If True, only report what would be checked without reading files.

    Returns:
        CheckResult with all check outcomes.
    """
    result = CheckResult()

    if dry_run:
        result.record("dry_run", True, f"would validate .memory/ under {target}")
        for fname in REQUIRED_FILES:
            result.record(f"dry_run:file:{fname}", True, "would check existence")
        for dname in EXPECTED_DIRS:
            result.record(f"dry_run:dir:{dname}", True, "would check directory")
        for fname in FRONTMATTER_REQUIREMENTS:
            result.record(f"dry_run:frontmatter:{fname}", True, "would check frontmatter")
        result.record("dry_run:lock_version", True, "would check lock version")
        result.record("dry_run:adapter_version", True, "would check adapter version")
        result.record("dry_run:pollution", True, "would check pollution")
        result.record("dry_run:migrations_log", True, "would check migrations.log")
        return result

    memory_root = target / ".memory"
    if not memory_root.is_dir():
        result.record("memory_root", False, f".memory/ directory not found at {memory_root}")
        return result

    result.record("memory_root", True, str(memory_root))

    check_required_files(memory_root, result)
    check_required_dirs(memory_root, result)
    check_frontmatter(memory_root, result)
    check_lock_version(memory_root, result)
    check_adapter_version(memory_root, result)
    check_pollution(memory_root, result)
    check_migrations_log(memory_root, result)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a project's .memory/ directory structure and integrity."
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Path to the target project root (must contain .memory/).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON instead of text.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be checked without reading files.",
    )
    try:
        _pkg_version = importlib.metadata.version("memory-core")
    except importlib.metadata.PackageNotFoundError:
        _pkg_version = "unknown"
    parser.add_argument("--version", action="version", version=f"%(prog)s {_pkg_version}")
    args = parser.parse_args()

    target = args.target.resolve()
    if not target.is_dir():
        print(f"Error: target path does not exist or is not a directory: {target}", file=sys.stderr)
        return 2

    result = validate_project_memory(target, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(result.to_text())

    return 0 if result.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
