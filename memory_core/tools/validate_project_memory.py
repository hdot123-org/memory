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
    5. State enumerations (STATE.md/PLAN.md/CANONICAL.md status field)
    6. memory.lock memory_version SemVer format
    7. adapter.toml routing.host enumeration

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

from memory_core.constants import (
    CURRENT_MEMORY_VERSION,
    FRONTMATTER_REQUIREMENTS,
    MESSAGE_VERSION_MISMATCH_DOWNGRADE_DETECTED,
    MESSAGE_VERSION_MISMATCH_UPGRADE_NEEDED,
    MIGRATION_LOG_LINE_PATTERN,
    REQUIRED_MEMORY_DIRS,
    REQUIRED_MEMORY_FILES,
    STATUS_ENUMERATIONS,
    SUPPORTED_HOSTS,
    VALID_HEALTH_VALUES,
)

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter as a flat dict.

    Supports simple key: value pairs.  Handles BOM, CRLF line endings,
    inline list values like ``tags: [tag1, tag2]`` and preserves quoted
    values with nested quotes.  Does not attempt full YAML parsing.
    """
    result: dict[str, str] = {}
    # Strip leading BOM if present so the opening ``---`` is at position 0.
    stripped = text.lstrip("\ufeff")
    # Accept both LF and CRLF line endings.
    m = re.match(r"^---\s*\r?\n(.*?)\r?\n---", stripped, re.DOTALL)
    if not m:
        return result
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kv = line.split(":", 1)
        if len(kv) != 2:
            continue
        key = kv[0].strip()
        if not key:
            continue
        val = kv[1].strip()

        # Inline list values: keep them as-is (e.g. "[tag1, tag2]")
        if val.startswith("[") and val.endswith("]"):
            result[key] = val
            continue

        # Strip surrounding matching quotes while preserving nested quotes.
        # Unquoted values are kept verbatim.
        if len(val) >= 2:
            first, last = val[0], val[-1]
            if (first == '"' and last == '"') or (first == "'" and last == "'"):
                val = val[1:-1]
        result[key] = val
    return result


def _is_json_like(text: str) -> bool:
    """Quick heuristic: text looks like JSON if it starts with { or [."""
    stripped = text.strip()
    return stripped.startswith("{") or stripped.startswith("[")


def _parse_lock_file(path: Path) -> dict[str, Any]:
    """Parse memory.lock as TOML (canonical) or JSON (legacy).

    If TOML parsing fails and the file is not JSON, falls back to a very
    old key=value format but marks the result with ``_parse_warning`` so
    callers know the data may be unreliable.
    """
    text = path.read_text(encoding="utf-8")
    if _is_json_like(text):
        # Legacy JSON format
        data = json.loads(text)
        return {
            "memory": {
                "memory_version": data.get("version", ""),
                "schema_version": data.get("schema", ""),
                "adapter_version": data.get("adapter_version", "builtin"),
                "locked_at": data.get("updated", data.get("initialized", "")),
                "lock_reason": data.get("lock_reason", ""),
            }
        }
    # Canonical TOML format
    try:
        return tomllib.loads(text)
    except Exception as exc:
        # Fallback: key=value lines (very old format)
        # Log the parse error so it is visible in logs / diagnostics.
        logger.warning(
            "TOML parse of %s failed (%s); falling back to legacy key=value parsing",
            path,
            exc,
        )
        result: dict[str, Any] = {"memory": {}}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("["):
                continue
            kv = line.split("=", 1)
            if len(kv) == 2:
                key = kv[0].strip()
                val = kv[1].strip().strip('"').strip("'")
                result["memory"][key] = val
        # Mark the result so callers know parsing was unreliable.
        result["_parse_warning"] = "TOML parse failed; data recovered via legacy fallback"
        return result


def _parse_adapter_toml(path: Path) -> dict[str, str]:
    """Parse adapter.toml using tomllib and flatten to section.key format."""
    text = path.read_text(encoding="utf-8")
    data = tomllib.loads(text)
    result: dict[str, str] = {}
    for section, values in data.items():
        if isinstance(values, dict):
            for key, val in values.items():
                result[f"{section}.{key}"] = str(val)
        else:
            result[section] = str(values)
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
    for fname in REQUIRED_MEMORY_FILES:
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
    for dname in REQUIRED_MEMORY_DIRS:
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

    memory_section = lock_data.get("memory", {})
    version = memory_section.get("memory_version", "")
    if not version:
        # Legacy fallback: try top-level "version" key
        version = lock_data.get("version", "")
    if not version:
        result.record("lock_version", False, "no memory_version key in memory.lock")
        return False

    try:
        lock_tuple = tuple(map(int, version.split(".")))
    except ValueError:
        result.record("lock_version", False, f"invalid version format: '{version}'")
        return False
    current_tuple = tuple(map(int, CURRENT_MEMORY_VERSION.split(".")))

    if lock_tuple == current_tuple:
        result.record("lock_version", True, f"version={version}")
        return True
    elif lock_tuple < current_tuple:
        msg = MESSAGE_VERSION_MISMATCH_UPGRADE_NEEDED.format(
            current=version, target=CURRENT_MEMORY_VERSION,
        )
        result.record("lock_version", False, msg)
        return False
    else:
        msg = MESSAGE_VERSION_MISMATCH_DOWNGRADE_DETECTED.format(
            current=version, target=CURRENT_MEMORY_VERSION,
        )
        result.record("lock_version", False, msg)
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
    """Verify migrations.log is parseable.

    Checks:
    - File exists and is non-empty
    - Each non-comment, non-blank line matches the expected migration log format
    - Malformed lines generate warnings but do not cause check failure (lenient)
    """
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
        # Validate line format (lenient: warn but do not fail)
        malformed: list[str] = []
        for idx, line in enumerate(lines, 1):
            if not MIGRATION_LOG_LINE_PATTERN.match(line):
                malformed.append(f"line {idx}")
        detail = f"{len(lines)} migration records"
        if malformed:
            detail += f"; malformed lines: {', '.join(malformed)}"
        result.record("migrations_log", True, detail)
        return True
    except Exception as exc:
        result.record("migrations_log", False, f"read error: {exc}")
        return False


def check_state_enumerations(memory_root: Path, result: CheckResult) -> bool:
    """Verify Markdown files have valid status values in frontmatter.

    Checks:
    - STATE.md: status must be active|paused|completed|archived
    - PLAN.md: status must be planning|in_progress|review|completed|blocked
    - CANONICAL.md: status must be active
    - STATE.md: health (if present) must be green|yellow|red
    """
    all_ok = True
    for fname, valid_statuses in STATUS_ENUMERATIONS.items():
        fpath = memory_root / fname
        if not fpath.is_file():
            continue
        text = fpath.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        status = fm.get("status", "").strip()
        if not status:
            result.record(f"status_enum:{fname}", False, "status field missing or empty")
            all_ok = False
        elif status not in valid_statuses:
            result.record(
                f"status_enum:{fname}",
                False,
                f"invalid status '{status}', must be one of: {', '.join(valid_statuses)}",
            )
            all_ok = False
        else:
            result.record(f"status_enum:{fname}", True, f"status={status}")

    # Additional: validate STATE.md health field if present
    state_path = memory_root / "STATE.md"
    if state_path.is_file():
        text = state_path.read_text(encoding="utf-8")
        fm = _parse_frontmatter(text)
        health = fm.get("health", "").strip()
        if health:
            if health not in VALID_HEALTH_VALUES:
                result.record(
                    "health_enum:STATE.md",
                    False,
                    f"invalid health '{health}', must be one of: {', '.join(VALID_HEALTH_VALUES)}",
                )
                all_ok = False
            else:
                result.record("health_enum:STATE.md", True, f"health={health}")

    return all_ok


def check_memory_lock_semver(memory_root: Path, result: CheckResult) -> bool:
    """Verify memory.lock memory_version follows SemVer (MAJOR.MINOR.PATCH)."""
    lock_path = memory_root / "memory.lock"
    if not lock_path.is_file():
        result.record("memory_lock_semver", False, "memory.lock not found")
        return False
    try:
        lock_data = _parse_lock_file(lock_path)
    except Exception as exc:
        result.record("memory_lock_semver", False, f"parse error: {exc}")
        return False

    memory_section = lock_data.get("memory") or {}
    version = memory_section.get("memory_version", "")
    if not version:
        # Legacy fallback: try top-level "version" key
        version = lock_data.get("version", "")
    if not version:
        result.record("memory_lock_semver", False, "no memory_version key in memory.lock")
        return False

    # SemVer regex: MAJOR.MINOR.PATCH (simple validation)
    semver_pattern = r"^\d+\.\d+\.\d+$"
    if re.match(semver_pattern, version):
        result.record("memory_lock_semver", True, f"version={version}")
        return True
    else:
        result.record(
            "memory_lock_semver",
            False,
            f"invalid SemVer format: '{version}' (expected MAJOR.MINOR.PATCH)",
        )
        return False


def check_adapter_host_enum(memory_root: Path, result: CheckResult) -> bool:
    """Verify adapter.toml routing.host is in SUPPORTED_HOSTS."""
    adapter_path = memory_root / "adapter.toml"
    if not adapter_path.is_file():
        result.record("adapter_host_enum", False, "adapter.toml not found")
        return False
    try:
        adapter_data = _parse_adapter_toml(adapter_path)
    except Exception as exc:
        result.record("adapter_host_enum", False, f"parse error: {exc}")
        return False

    host = adapter_data.get("routing.host", "")
    if not host:
        result.record("adapter_host_enum", False, "no routing.host key in adapter.toml")
        return False

    if host in SUPPORTED_HOSTS:
        result.record("adapter_host_enum", True, f"host={host}")
        return True
    else:
        result.record(
            "adapter_host_enum",
            False,
            f"invalid host '{host}', must be one of: {', '.join(SUPPORTED_HOSTS)}",
        )
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
        for fname in REQUIRED_MEMORY_FILES:
            result.record(f"dry_run:file:{fname}", True, "would check existence")
        for dname in REQUIRED_MEMORY_DIRS:
            result.record(f"dry_run:dir:{dname}", True, "would check directory")
        for fname in FRONTMATTER_REQUIREMENTS:
            result.record(f"dry_run:frontmatter:{fname}", True, "would check frontmatter")
        result.record("dry_run:lock_version", True, "would check lock version")
        result.record("dry_run:adapter_version", True, "would check adapter version")
        result.record("dry_run:pollution", True, "would check pollution")
        result.record("dry_run:migrations_log", True, "would check migrations.log")
        result.record("dry_run:status_enum", True, "would check status enumerations")
        result.record("dry_run:semver", True, "would check memory_version SemVer format")
        result.record("dry_run:host_enum", True, "would check adapter host enum")
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
    check_state_enumerations(memory_root, result)
    check_memory_lock_semver(memory_root, result)
    check_adapter_host_enum(memory_root, result)

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
