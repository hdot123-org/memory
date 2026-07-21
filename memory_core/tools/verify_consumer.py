"""Consumer self-check CLI (T2.6).

Verifies that a memory/system/ directory under a consuming project satisfies the
platform-agnostic protocol contract expected by memory-core consumers
(Factory DCE being the reference implementation).

This is a *read-only* validator. It never writes to memory/system/. Intended for
non-Factory platforms (Claude Code, Cursor, Cline, custom agents) to
self-check their lazy-loader implementations against the open contract.

Exit codes:
    0   all checks passed
    1   one or more contract violations
    2   target path invalid / not initialized
"""

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    from .index_schema import (
        INDEX_SCHEMA_VERSION,
        get_schema_version,
        is_schema_compatible,
        parse_headers,
    )
except ImportError:
    from memory_core.tools.index_schema import (
        INDEX_SCHEMA_VERSION,
        get_schema_version,
        is_schema_compatible,
        parse_headers,
    )

REQUIRED_FILES = [
    "memory/system/adapter.toml",
    "memory/system/ownership.toml",
]

REQUIRED_INDEXES = [
    "INDEX.md",
    "memory/kb/INDEX.md",
    "memory/docs/INDEX.md",
]

logger = logging.getLogger(__name__)


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class VerifyReport:
    target: str
    expected_schema_version: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(CheckResult(name=name, passed=passed, detail=detail))

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "expected_schema_version": self.expected_schema_version,
            "all_passed": self.all_passed,
            "failed_count": self.failed_count,
            "checks": [c.to_dict() for c in self.checks],
        }


def _check_target_initialized(target: Path, report: VerifyReport) -> bool:
    memory_dir = target / "memory" / "system"
    exists = memory_dir.is_dir()
    report.add(
        "target.has_memory_system",
        passed=exists,
        detail=f"memory/system directory at {memory_dir}" if exists else f"missing: {memory_dir}",
    )
    return exists


def _check_required_files(target: Path, report: VerifyReport) -> None:
    for rel in REQUIRED_FILES:
        path = target / rel
        report.add(
            f"file.{rel}",
            passed=path.is_file(),
            detail=str(path),
        )


def _check_indexes_exist(target: Path, report: VerifyReport) -> list[Path]:
    found: list[Path] = []
    for rel in REQUIRED_INDEXES:
        path = target / rel
        present = path.is_file()
        report.add(f"index.{rel}.exists", passed=present, detail=str(path))
        if present:
            found.append(path)
    return found


def _check_index_schema(path: Path, report: VerifyReport) -> None:
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        report.add(f"index.{path}.readable", passed=False, detail=f"read failed: {exc}")
        return
    report.add(f"index.{path}.readable", passed=True, detail=f"{len(content)} bytes")
    headers = parse_headers(content)
    has_schema = "index-schema" in headers
    report.add(
        f"index.{path}.has_schema_header",
        passed=has_schema,
        detail=(
            f"index-schema: {headers['index-schema']}"
            if has_schema
            else "legacy file without explicit schema header (treated as 1.0)"
        ),
    )
    declared = get_schema_version(content)
    compatible = is_schema_compatible(content)
    report.add(
        f"index.{path}.schema_compatible",
        passed=compatible,
        detail=f"declared={declared} expected={INDEX_SCHEMA_VERSION}",
    )


def _check_ownership_mode(target: Path, report: VerifyReport) -> None:
    ownership = target / "memory" / "system" / "ownership.toml"
    if not ownership.is_file():
        return
    try:
        text = ownership.read_text(encoding="utf-8")
    except OSError as exc:
        report.add("ownership.readable", passed=False, detail=str(exc))
        return
    report.add("ownership.readable", passed=True, detail=f"{len(text)} bytes")


# Placeholder markers to detect
_PLACEHOLDERS = [
    "（待填写）",
    "待填写",
]




def _check_fill_quality(target: Path, report: VerifyReport) -> None:
    """Check fill quality — warnings, not errors.

    Verifies that CANONICAL.md has been filled with actual content
    (not just the template placeholders).
    """
    # CANONICAL.md is now at memory/kb/projects/{scope}/CANONICAL.md
    # Find any scope directories under memory/kb/projects/
    projects_dir = target / "memory" / "kb" / "projects"
    if not projects_dir.is_dir():
        return

    for scope_dir in projects_dir.iterdir():
        if not scope_dir.is_dir():
            continue
        canonical = scope_dir / "CANONICAL.md"
        if not canonical.is_file():
            continue
        try:
            text = canonical.read_text(encoding="utf-8")
        except OSError as exc:
            report.add("fill_quality.canonical_readable", passed=False, detail=str(exc))
            return
        # Check for unfilled template placeholders
        unfilled = text.count("{{")
        if unfilled > 0:
            report.add(
                "fill_quality.canonical_filled",
                passed=False,
                detail=f"{unfilled} unfilled placeholders in {scope_dir.name}/CANONICAL.md",
            )
        else:
            report.add(
                "fill_quality.canonical_filled",
                passed=True,
                detail=f"no unfilled placeholders in {scope_dir.name}/CANONICAL.md ({len(text)} bytes)",
            )
        return

    # No CANONICAL.md found
    report.add(
        "fill_quality.canonical_exists",
        passed=False,
        detail="no CANONICAL.md found in any project scope directory",
    )


def verify(target: Path) -> VerifyReport:
    """Run all read-only checks and return a structured report."""
    report = VerifyReport(
        target=str(target),
        expected_schema_version=INDEX_SCHEMA_VERSION,
    )
    if not _check_target_initialized(target, report):
        return report
    _check_required_files(target, report)
    indexes = _check_indexes_exist(target, report)
    for path in indexes:
        _check_index_schema(path, report)
    _check_ownership_mode(target, report)
    _check_fill_quality(target, report)
    return report


def _render_human(report: VerifyReport) -> str:
    lines = [
        f"Consumer Self-Check: {report.target}",
        f"  Expected schema version: {report.expected_schema_version}",
        f"  Result: {'PASS' if report.all_passed else 'FAIL'} ({report.failed_count} failed)",
        "",
    ]
    for c in report.checks:
        mark = "OK  " if c.passed else "FAIL"
        lines.append(f"  [{mark}] {c.name}: {c.detail}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="memory-core verify-consumer",
        description=(
            "Verify that a memory/system/ directory satisfies the memory-core "
            "consumer contract. Read-only; safe to run anytime."
        ),
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path.cwd(),
        help="Project root containing memory/system/ (default: cwd)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output a structured JSON report instead of human text",
    )
    args = parser.parse_args(argv)
    target = args.path.expanduser().resolve()
    if not target.exists():
        sys.stderr.write(f"target path does not exist: {target}\n")
        return 2
    report = verify(target)
    if args.json:
        sys.stdout.write(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(_render_human(report))
    if not any(c.name == "target.has_memory_system" and c.passed for c in report.checks):
        return 2
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
