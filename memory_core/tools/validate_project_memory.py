#!/usr/bin/env python3
"""Validate a project's memory/system/ directory structure and integrity.

Usage:
    python validate_project_memory.py --target /path/to/project
    python validate_project_memory.py --target /path/to/project --json
    python validate_project_memory.py --target /path/to/project --dry-run

Checks performed:
    1. Required files existence (memory.lock, adapter.toml, migrations.log)
    2. Lock/adapter version compatibility
    3. Pollution guard (no business state written into memory repo)
    4. memory.lock memory_version SemVer format
    5. adapter.toml routing.host enumeration

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

import argparse
import importlib.metadata
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import tomllib

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
from memory_core.constants import (
    CURRENT_MEMORY_VERSION,
    MIGRATION_LOG_LINE_PATTERN,
    REQUIRED_MEMORY_DIRS,
    REQUIRED_MEMORY_FILES,
    SUPPORTED_HOSTS,
)
from memory_core.ownership import (
    load_memory_ownership,
    validate_ownership_schema,
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
    """Quick heuristic: text looks like JSON if it starts with { or [.

    Distinguishes between JSON arrays like [{...}] and TOML section headers
    like [memory]. A line starting with [word] is treated as TOML, not JSON.
    """
    stripped = text.strip()
    if stripped.startswith("{"):
        return True
    if stripped.startswith("["):
        # Check if it looks like a TOML section header: [word] or [word.subword]
        # TOML section: [identifier] where identifier is alphanumeric/underscore/hyphen/dot
        # JSON array: [{ or [" or [1 or [...] where content is not just an identifier
        match = re.match(r'^\[([a-zA-Z_][a-zA-Z0-9_\-\.]*)\]', stripped)
        if match:
            # Looks like a TOML section header, not JSON
            return False
        # Otherwise treat as JSON array
        return True
    return False


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
    """Verify all required files exist inside memory/system/."""
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


def check_lock_version(memory_root: Path, result: CheckResult) -> bool:
    """Verify memory.lock version is compatible.

    Backward compatible: accepts any version in the compat matrix.
    Only warns for unknown versions (not in matrix).
    """
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

    # Backward compatibility: accept any known version from compat matrix
    from memory_core.compat import _COMPAT_MATRIX
    if version in _COMPAT_MATRIX:
        result.record("lock_version", True, f"version={version} (known version)")
        return True

    # Unknown version: warn but don't fail (allow future versions)
    current_tuple = tuple(map(int, CURRENT_MEMORY_VERSION.split(".")))
    if lock_tuple < current_tuple:
        msg = f"version={version} is older than current {CURRENT_MEMORY_VERSION}; consider running memory-migrate"
        result.record("lock_version", True, msg)
        return True
    else:
        msg = f"version={version} is newer than current {CURRENT_MEMORY_VERSION}; assuming forward compatibility"
        result.record("lock_version", True, msg)
        return True


def check_adapter_version(memory_root: Path, result: CheckResult) -> bool:
    """Verify adapter.toml version is compatible.

    Backward compatible: accepts any version in the compat matrix.
    Only warns for version mismatches, doesn't fail validation.
    """
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

    # Backward compatibility: accept any known version from compat matrix
    from memory_core.compat import _COMPAT_MATRIX
    if version in _COMPAT_MATRIX:
        result.record("adapter_version", True, f"version={version} (known version)")
        return True

    # Unknown version: warn but don't fail
    if version == CURRENT_MEMORY_VERSION:
        result.record("adapter_version", True, f"version={version}")
        return True
    else:
        msg = f"version={version} differs from current {CURRENT_MEMORY_VERSION}; consider running memory-migrate"
        result.record("adapter_version", True, msg)
        return True


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


def check_ownership_declaration(memory_root: Path, result: CheckResult) -> bool:
    """Step 2.3: Verify ownership.toml declaration exists and is valid.

    Checks:
    - ownership.toml exists in memory/system/
    - Schema version is valid (matches OWNERSHIP_SCHEMA_VERSION)
    - Default domains not deleted/downgraded via validate_ownership_schema()
    """
    all_ok = True
    ownership_path = memory_root / "ownership.toml"

    if not ownership_path.is_file():
        result.record("ownership_declaration", False, "ownership.toml not found in memory/system/")
        all_ok = False
    else:
        result.record("ownership_declaration", True, "ownership.toml exists")

        # Load and validate ownership
        try:
            ownership = load_memory_ownership(memory_root.parent)
            schema_errors = validate_ownership_schema(ownership)
            if schema_errors:
                for error in schema_errors:
                    result.record("ownership_schema", False, error)
                    all_ok = False
            else:
                result.record("ownership_schema", True, "schema valid, no weakening detected")
        except Exception as exc:
            result.record("ownership_schema", False, f"failed to validate ownership: {exc}")
            all_ok = False

    return all_ok


def check_domain_integrity(target: Path, memory_root: Path, result: CheckResult) -> bool:
    """Step 2.4: Verify critical domain paths exist and are not symlinks.

    Checks:
    - memory/ and project-map/ exist and are not symlinks
    - Paths don't escape project root
    """
    all_ok = True
    # memory_root is target / "memory" / "system", so:
    #   memory_root.parent = target / "memory"
    #   memory_root.parent.parent = target
    critical_paths = [
        ("memory", memory_root.parent),
        ("project-map", memory_root.parent.parent / "project-map"),
    ]

    for name, path in critical_paths:
        if not path.exists():
            result.record(f"domain_integrity:{name}", False, f"{name} does not exist")
            all_ok = False
            continue

        if path.is_symlink():
            result.record(f"domain_integrity:{name}", False, f"{name} is a symlink (forbidden)")
            all_ok = False
            continue

        # Check path doesn't escape project root
        try:
            path.relative_to(target.resolve())
            result.record(f"domain_integrity:{name}", True, f"{name} is valid directory")
        except ValueError:
            result.record(f"domain_integrity:{name}", False, f"{name} escapes project root")
            all_ok = False

    return all_ok


def check_document_paths(memory_root: Path, result: CheckResult) -> bool:
    """Step 2.5: Verify document index consistency.

    Checks:
    - memory/docs/INDEX.md exists and is consistent
    - memory/kb/INDEX.md exists and is consistent
    - project-map/INDEX.md exists and is consistent
    - Referenced documents exist
    """
    all_ok = True
    # memory_root is target / "memory" / "system", so:
    #   memory_root.parent.parent = target
    project_root = memory_root.parent.parent
    index_files = [
        ("memory/docs/INDEX.md", project_root / "memory" / "docs" / "INDEX.md"),
        ("memory/kb/INDEX.md", project_root / "memory" / "kb" / "INDEX.md"),
        ("project-map/INDEX.md", project_root / "project-map" / "INDEX.md"),
    ]

    for rel_path, full_path in index_files:
        if not full_path.is_file():
            result.record(f"document_paths:{rel_path}", False, f"{rel_path} not found")
            all_ok = False
            continue

        # Try to read the index
        try:
            content = full_path.read_text(encoding="utf-8")
            # Basic check: non-empty and has some structure
            if not content.strip():
                result.record(f"document_paths:{rel_path}", False, f"{rel_path} is empty")
                all_ok = False
                continue

            # Check for referenced files (basic pattern matching)
            # Look for markdown file references like "- path/to/file.md"
            referenced_files = re.findall(r"[\s\-]*([\w\-/]+\.md)", content)
            missing_refs = []
            for ref in referenced_files:
                ref_path = project_root / ref
                if not ref_path.exists() and not ref.startswith("http"):
                    # Skip if it looks like a pattern, not a literal path
                    if "*" not in ref and "?" not in ref:
                        missing_refs.append(ref)

            if missing_refs:
                result.record(
                    f"document_paths:{rel_path}",
                    False,
                    f"{len(missing_refs)} referenced files missing: {', '.join(missing_refs[:3])}...",
                )
                all_ok = False
            else:
                result.record(f"document_paths:{rel_path}", True, f"{rel_path} valid, references OK")
        except Exception as exc:
            # Step 2.7 fix: record error instead of continue
            result.record(f"document_paths:{rel_path}", False, f"read error: {exc}")
            all_ok = False

    return all_ok


def check_shared_resources(target: Path, memory_root: Path, result: CheckResult) -> bool:
    """Step 2.6: Verify shared resource markers.

    Checks:
    - AGENTS.md markers are paired (MEMORY_HOOK_BEGIN and MEMORY_HOOK_END)
    - .claude/hooks.json or .codex/hooks.json entries are complete
    """
    all_ok = True

    # Check AGENTS.md markers
    agents_path = target / "AGENTS.md"
    if agents_path.is_file():
        try:
            content = agents_path.read_text(encoding="utf-8")
            has_begin = "<!-- MEMORY_HOOK_BEGIN -->" in content
            has_end = "<!-- MEMORY_HOOK_END -->" in content

            if has_begin and has_end:
                result.record("shared_resources:agents_md", True, "AGENTS.md markers paired")
            elif has_begin or has_end:
                missing = "END" if has_begin else "BEGIN"
                result.record(
                    "shared_resources:agents_md",
                    False,
                    f"AGENTS.md missing {missing} marker",
                )
                all_ok = False
            else:
                # No markers - might be old style or not initialized
                result.record(
                    "shared_resources:agents_md",
                    True,
                    "AGENTS.md exists (no markers)",
                )
        except Exception as exc:
            result.record("shared_resources:agents_md", False, f"read error: {exc}")
            all_ok = False
    else:
        result.record("shared_resources:agents_md", False, "AGENTS.md not found")
        all_ok = False

    # Check hooks.json
    for host in SUPPORTED_HOSTS:
        hooks_path = target / f".{host}" / "hooks.json"
        if hooks_path.is_file():
            try:
                data = json.loads(hooks_path.read_text(encoding="utf-8"))
                hooks = data.get("hooks", [])
                if isinstance(hooks, list):
                    # Check each hook has required fields
                    incomplete = []
                    for idx, hook in enumerate(hooks):
                        if not isinstance(hook, dict):
                            continue
                        if "memory-hook" in hook.get("command", ""):
                            if not hook.get("event") or not hook.get("command"):
                                incomplete.append(str(idx))

                    if incomplete:
                        result.record(
                            f"shared_resources:hooks_{host}",
                            False,
                            f"{len(incomplete)} incomplete memory hook entries",
                        )
                        all_ok = False
                    else:
                        result.record(
                            f"shared_resources:hooks_{host}",
                            True,
                            f"{len(hooks)} hooks, all complete",
                        )
                else:
                    result.record(
                        f"shared_resources:hooks_{host}",
                        False,
                        "hooks field is not a list",
                    )
                    all_ok = False
            except json.JSONDecodeError as exc:
                result.record(
                    f"shared_resources:hooks_{host}",
                    False,
                    f"invalid JSON: {exc}",
                )
                all_ok = False
            except Exception as exc:
                result.record(f"shared_resources:hooks_{host}", False, f"read error: {exc}")
                all_ok = False

    return all_ok


from memory_core.tools.evidence_ref_validator import validate_evidence_refs_on_disk


def check_kb_evidence_refs(target: Path, result: CheckResult) -> bool:
    """Step 2.7: Verify KB evidence refs point to existing files on disk.

    Uses the shared evidence_ref_validator module so that the same
    validation logic is available to init_project_memory.py and
    migrate_project_memory.py.
    """
    errors = validate_evidence_refs_on_disk(target)
    all_ok = True
    if errors:
        for err in errors:
            result.record(
                f"evidence_refs:{err.kb_file}",
                False,
                f"{len(err.missing_refs)} missing evidence refs: {', '.join(err.missing_refs[:3])}",
            )
            all_ok = False
    else:
        result.record("evidence_refs", True, "all KB evidence refs exist on disk")
    return all_ok


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------

def validate_project_memory(
    target: Path,
    *,
    dry_run: bool = False,
) -> CheckResult:
    """Run all validation checks on a project's memory/system/ directory.

    Args:
        target: Path to the target project root (must contain memory/system/).
        dry_run: If True, only report what would be checked without reading files.

    Returns:
        CheckResult with all check outcomes.
    """
    result = CheckResult()

    if dry_run:
        result.record("dry_run", True, f"would validate memory/system/ under {target}")
        for fname in REQUIRED_MEMORY_FILES:
            result.record(f"dry_run:file:{fname}", True, "would check existence")
        for dname in REQUIRED_MEMORY_DIRS:
            result.record(f"dry_run:dir:{dname}", True, "would check directory")
        result.record("dry_run:lock_version", True, "would check lock version")
        result.record("dry_run:adapter_version", True, "would check adapter version")
        result.record("dry_run:pollution", True, "would check pollution")
        result.record("dry_run:migrations_log", True, "would check migrations.log")
        result.record("dry_run:semver", True, "would check memory_version SemVer format")
        result.record("dry_run:host_enum", True, "would check adapter host enum")
        result.record("dry_run:ownership", True, "would check ownership declaration")
        result.record("dry_run:domain_integrity", True, "would check domain integrity")
        result.record("dry_run:document_paths", True, "would check document paths")
        result.record("dry_run:shared_resources", True, "would check shared resources")
        return result

    memory_root = target / "memory" / "system"
    if not memory_root.is_dir():
        result.record("memory_root", False, f"memory/system/ directory not found at {memory_root}")
        return result

    result.record("memory_root", True, str(memory_root))

    check_required_files(memory_root, result)
    check_required_dirs(memory_root, result)
    check_lock_version(memory_root, result)
    check_adapter_version(memory_root, result)
    check_pollution(memory_root, result)
    check_migrations_log(memory_root, result)
    check_memory_lock_semver(memory_root, result)
    check_adapter_host_enum(memory_root, result)

    # Step 2.3-2.6: Ownership-related checks
    check_ownership_declaration(memory_root, result)
    check_domain_integrity(target, memory_root, result)
    check_document_paths(memory_root, result)
    check_shared_resources(target, memory_root, result)
    check_kb_evidence_refs(target, result)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a project's memory/system/ directory structure and integrity."
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="Path to the target project root (must contain memory/system/).",
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
