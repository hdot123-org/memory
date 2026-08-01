#!/usr/bin/env python3.12
"""Layer D — Error Pattern Detector.

Deterministic CLI tool that reads *-errors.jsonl files, normalizes/fingerprints
error messages, groups by pattern, evaluates recurrence thresholds, and writes
a machine-readable pattern registry to memory/kb/patterns/registry.jsonl.

Usage:
    python3.12 -m memory_core.tools.error_pattern_detector [--project PATH | --all-projects] [--dry-run] [--verbose]
    memory-error-patterns [--project PATH | --all-projects] [--dry-run] [--verbose]
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Import-guarded error_logger for self-failure logging
try:
    from memory_core.tools.error_logger import write_error_log
except ImportError:
    write_error_log = None  # type: ignore[assignment]

# Import-guarded now_iso for consistent timestamps
try:
    from memory_core.tools._file_utils import now_iso as _now_iso_impl
except ImportError:
    try:
        from _file_utils import now_iso as _now_iso_impl  # type: ignore[no-redef]
    except ImportError:
        def _now_iso_impl() -> str:
            """Fallback now_iso if _file_utils unavailable."""
            from datetime import datetime
            return datetime.now().astimezone().isoformat(timespec="seconds")

def now_iso() -> str:
    """Wrapper for now_iso implementation."""
    return _now_iso_impl()


# ---------------------------------------------------------------------------
# Normalization (VAL-FINGERPRINT-001 through VAL-FINGERPRINT-018)
# ---------------------------------------------------------------------------


def normalize_error_msg(msg: str | None) -> str:
    """Normalize an error message by stripping variable parts.

    Applies 7 transforms in order:
    1. Paths → <PATH>
    2. ISO timestamps → <TS>
    3. UUIDs → <UUID>
    4. 8-char hex IDs → <HEX>
    5. Standalone numbers → N
    6. Whitespace collapse → single space
    7. Strip leading/trailing whitespace

    Args:
        msg: Raw error message (None treated as empty string)

    Returns:
        Normalized message string (deterministic, no time/locale dependence)
    """
    if msg is None:
        return ""

    result = msg

    # 1. File system paths (absolute, relative, with ~)
    # Must run before number replacement to avoid partial replacement
    result = re.sub(r"/[\w./\-~]+(?:/[\w./\-~]+)+", "<PATH>", result)
    result = re.sub(r"~(?:/[\w./\-]+)+", "<PATH>", result)
    # Relative multi-segment paths (e.g., memory/log/foo.jsonl)
    result = re.sub(r"\b[\w]+(?:/[\w./\-]+)+\b", "<PATH>", result)

    # 2. ISO-8601 timestamps (with/without fractional seconds, various offsets)
    result = re.sub(
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?",
        "<TS>",
        result,
    )

    # 3. Full UUIDs (12345678-1234-1234-1234-1234567890ab)
    result = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "<UUID>",
        result,
        flags=re.IGNORECASE,
    )

    # 4. 8-char hex session IDs (word-bounded, exactly 8 hex chars)
    result = re.sub(r"\b[0-9a-f]{8}\b", "<HEX>", result, flags=re.IGNORECASE)

    # 5. Standalone decimal numbers (word-bounded)
    result = re.sub(r"\b\d+\b", "N", result)

    # 6. Whitespace collapse (spaces, tabs, newlines → single space)
    result = re.sub(r"\s+", " ", result)

    # 7. Strip leading/trailing whitespace
    result = result.strip()

    return result


# ---------------------------------------------------------------------------
# Fingerprint (VAL-FINGERPRINT-012, VAL-FINGERPRINT-013)
# ---------------------------------------------------------------------------


def compute_fingerprint(error_type: str, script: str, normalized_msg: str) -> str:
    """Compute a 16-char hex fingerprint from type, script, and normalized message.

    Fingerprint = SHA256("{type}|{script}|{normalized_msg}")[:16]

    Args:
        error_type: Error type (e.g., "llm_api_error")
        script: Script name (e.g., "daily_summary_generator")
        normalized_msg: Normalized error message

    Returns:
        16-character lowercase hex string
    """
    composition = f"{error_type}|{script}|{normalized_msg}"
    sha256_hash = hashlib.sha256(composition.encode("utf-8")).hexdigest()
    return sha256_hash[:16]


# ---------------------------------------------------------------------------
# Pattern Group Data Structure
# ---------------------------------------------------------------------------


@dataclass
class PatternGroup:
    """Aggregated pattern group with metadata."""

    fingerprint: str
    type: str
    script: str
    normalized_msg: str
    status: str  # Always "detected" in Phase 1
    first_seen: str  # Earliest ts (ISO string)
    last_seen: str  # Latest ts (ISO string)
    distinct_days: list[str]  # Sorted unique YYYY-MM-DD strings
    total_count: int  # Number of entries in group
    projects: list[str]  # Sorted unique project paths
    sample_first: dict[str, str]  # {"ts": ..., "msg": ...} (raw, non-normalized)
    sample_last: dict[str, str]  # {"ts": ..., "msg": ...} (raw, non-normalized)


# ---------------------------------------------------------------------------
# Grouping (VAL-DETECT-001 through VAL-DETECT-011)
# ---------------------------------------------------------------------------


def group_by_fingerprint(entries: list[dict[str, Any]]) -> dict[str, PatternGroup]:
    """Group error entries by fingerprint and aggregate metadata.

    Args:
        entries: List of error log entries (each with ts, type, script, project, msg)

    Returns:
        Dict mapping fingerprint → PatternGroup
    """
    groups: dict[str, PatternGroup] = {}

    for entry in entries:
        ts: str = entry.get("ts", "")
        error_type: str = entry.get("type", "")
        script: str = entry.get("script", "")
        project: str = entry.get("project", "")
        msg: str = entry.get("msg", "")
        if msg is None:
            msg = ""

        normalized = normalize_error_msg(msg)
        fp = compute_fingerprint(error_type, script, normalized)

        date_str = ts[:10] if len(ts) >= 10 else ""

        if fp not in groups:
            groups[fp] = PatternGroup(
                fingerprint=fp,
                type=error_type,
                script=script,
                normalized_msg=normalized,
                status="detected",
                first_seen=ts,
                last_seen=ts,
                distinct_days=[date_str] if date_str else [],
                total_count=1,
                projects=[project] if project else [],
                sample_first={"ts": ts, "msg": msg},
                sample_last={"ts": ts, "msg": msg},
            )
        else:
            group = groups[fp]
            group.total_count += 1

            if ts < group.first_seen:
                group.first_seen = ts
                group.sample_first = {"ts": ts, "msg": msg}
            if ts >= group.last_seen:
                group.last_seen = ts
                group.sample_last = {"ts": ts, "msg": msg}

            if date_str and date_str not in group.distinct_days:
                group.distinct_days.append(date_str)

            if project and project not in group.projects:
                group.projects.append(project)

    for group in groups.values():
        group.distinct_days.sort()
        group.projects.sort()

    return groups


# ---------------------------------------------------------------------------
# Threshold Evaluation
# ---------------------------------------------------------------------------


def evaluate_threshold(group: PatternGroup) -> str | None:
    """Evaluate recurrence threshold for a pattern group.

    Threshold rules:
    - distinct_days >= 2 AND total_count >= 5 → "both"
    - distinct_days >= 2 AND total_count < 5  → "days"
    - distinct_days < 2  AND total_count >= 5 → "count"
    - Neither                                  → None
    """
    days_met = len(group.distinct_days) >= 2
    count_met = group.total_count >= 5

    if days_met and count_met:
        return "both"
    elif days_met:
        return "days"
    elif count_met:
        return "count"
    else:
        return None


# ---------------------------------------------------------------------------
# Registry I/O (VAL-REGISTRY-*)
# ---------------------------------------------------------------------------

# Required fields for every registry line
REGISTRY_REQUIRED_FIELDS = frozenset({
    "fingerprint", "type", "script", "normalized_msg", "status",
    "first_seen", "last_seen", "first_detected", "last_updated",
    "distinct_days", "total_count", "projects", "threshold_met",
    "sample_first", "sample_last",
})


def read_registry(path: Path) -> dict[str, dict[str, Any]]:
    """Read existing registry JSONL file.

    Args:
        path: Path to registry.jsonl

    Returns:
        Dict mapping fingerprint → registry entry dict.
        Malformed lines are skipped (logged to stderr).
    """
    result: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return result

    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                print(
                    f"warning: malformed JSONL at {path}:{line_no}, skipping",
                    file=sys.stderr,
                )
                continue

            if not isinstance(entry, dict):
                print(
                    f"warning: non-object JSONL at {path}:{line_no}, skipping",
                    file=sys.stderr,
                )
                continue

            fp = entry.get("fingerprint")
            if not fp or not isinstance(fp, str):
                print(
                    f"warning: missing fingerprint at {path}:{line_no}, skipping",
                    file=sys.stderr,
                )
                continue

            result[fp] = entry

    return result


def write_registry(path: Path, entries: list[dict[str, Any]]) -> None:
    """Write registry entries as JSONL (full rewrite, not append).

    Creates parent directories if needed.
    Empty entries list → writes an empty file (0 bytes).

    Args:
        path: Path to registry.jsonl
        entries: List of registry entry dicts (one per fingerprint)
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def merge_patterns(
    detected: dict[str, PatternGroup],
    existing: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge detected patterns with existing registry, preserving first_detected.

    For each detected pattern:
    - If fingerprint exists in registry: preserve first_detected, update everything else
    - If new: set first_detected = current run time

    All aggregated fields (first_seen, last_seen, distinct_days, total_count,
    projects, samples) are recomputed from source data on every run.

    Args:
        detected: Dict of fingerprint → PatternGroup from current detection
        existing: Dict of fingerprint → entry from existing registry

    Returns:
        List of registry entry dicts, sorted by fingerprint for determinism
    """
    run_time: str = now_iso()
    result: list[dict[str, Any]] = []

    for fp in sorted(detected.keys()):
        group = detected[fp]
        threshold = evaluate_threshold(group)

        # Preserve first_detected from existing entry, or set to current run time
        first_detected: str = run_time
        if fp in existing:
            existing_entry = existing[fp]
            fd = existing_entry.get("first_detected")
            if fd and isinstance(fd, str):
                first_detected = fd

        entry: dict[str, Any] = {
            "fingerprint": fp,
            "type": group.type,
            "script": group.script,
            "normalized_msg": group.normalized_msg,
            "status": group.status,
            "first_seen": group.first_seen,
            "last_seen": group.last_seen,
            "first_detected": first_detected,
            "last_updated": run_time,
            "distinct_days": group.distinct_days,
            "total_count": group.total_count,
            "projects": group.projects,
            "threshold_met": threshold,
            "sample_first": group.sample_first,
            "sample_last": group.sample_last,
        }
        result.append(entry)

    return result


# ---------------------------------------------------------------------------
# Error Log Discovery & Parsing
# ---------------------------------------------------------------------------


def discover_error_files(project_root: Path) -> list[Path]:
    """Find all *-errors.jsonl files in a project's memory/log/ directory.

    Args:
        project_root: Project root directory

    Returns:
        Sorted list of error log file paths
    """
    log_dir = project_root / "memory" / "log"
    if not log_dir.exists():
        return []
    return sorted(log_dir.glob("*-errors.jsonl"))


def parse_error_file(path: Path) -> list[dict[str, Any]]:
    """Parse a JSONL error log file, skipping malformed lines.

    Args:
        path: Path to the error log file

    Returns:
        List of parsed entry dicts
    """
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                print(
                    f"warning: malformed JSONL at {path}:{line_no}, skipping",
                    file=sys.stderr,
                )
                continue
            if not isinstance(entry, dict):
                print(
                    f"warning: non-object JSONL at {path}:{line_no}, skipping",
                    file=sys.stderr,
                )
                continue
            entries.append(entry)
    return entries


def scan_project(project_root: Path) -> list[dict[str, Any]]:
    """Scan a single project for error entries.

    Args:
        project_root: Project root directory

    Returns:
        List of all parsed error entries from the project
    """
    all_entries: list[dict[str, Any]] = []
    for error_file in discover_error_files(project_root):
        all_entries.extend(parse_error_file(error_file))
    return all_entries


# ---------------------------------------------------------------------------
# Multi-Project Discovery
# ---------------------------------------------------------------------------


def discover_all_projects() -> list[Path]:
    """Discover all projects from path-index.json.

    Reads ~/.memory-core/project-lifecycle/path-index.json and returns
    a list of project paths. Missing index or non-existent paths are skipped.

    Returns:
        List of existing project root paths
    """
    index_path = Path.home() / ".memory-core" / "project-lifecycle" / "path-index.json"
    if not index_path.exists():
        print(
            f"warning: path-index.json not found at {index_path}, no projects discovered",
            file=sys.stderr,
        )
        return []

    try:
        with index_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(
            f"warning: failed to read path-index.json: {e}",
            file=sys.stderr,
        )
        return []

    # Support both "paths" and "LIFECYCLE_INDEX" keys
    paths_dict: dict[str, Any] = data.get("paths", data.get("LIFECYCLE_INDEX", {}))
    if not isinstance(paths_dict, dict):
        return []

    result: list[Path] = []
    for project_path_str in sorted(paths_dict.keys()):
        project_path = Path(project_path_str)
        if project_path.exists():
            result.append(project_path)
        else:
            print(
                f"warning: project path {project_path_str} does not exist, skipping",
                file=sys.stderr,
            )

    return result


def detect_project_from_cwd() -> Path | None:
    """Auto-detect the project root from the current working directory.

    Uses git rev-parse --show-toplevel to find the project root.

    Returns:
        Project root path, or None if detection fails
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return None


# ---------------------------------------------------------------------------
# Verbose Output
# ---------------------------------------------------------------------------


def print_verbose_output(entries: list[dict[str, Any]]) -> None:
    """Print detailed per-pattern detection output to stdout.

    Format:
    [pattern] fingerprint: xxx
      type: ...
      script: ...
      count: N
      days: N
      threshold: ...
      projects: ...
      first_seen: ...
      last_seen: ...
    """
    for entry in entries:
        fp = entry.get("fingerprint", "?")
        print(f"[pattern] fingerprint: {fp}")
        print(f"  type: {entry.get('type', '?')}")
        print(f"  script: {entry.get('script', '?')}")
        print(f"  count: {entry.get('total_count', 0)}")
        print(f"  days: {len(entry.get('distinct_days', []))}")
        threshold = entry.get("threshold_met")
        print(f"  threshold: {threshold if threshold is not None else 'null'}")
        projects = entry.get("projects", [])
        print(f"  projects: {', '.join(projects) if projects else '(none)'}")
        print(f"  first_seen: {entry.get('first_seen', '?')}")
        print(f"  last_seen: {entry.get('last_seen', '?')}")


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(
    project_paths: Path | list[Path],
    registry_path: Path | None,
    dry_run: bool = False,
    verbose: bool = False,
) -> list[dict[str, Any]]:
    """Run the full detection pipeline.

    Args:
        project_paths: Single project root or list of project root directories to scan
        registry_path: Path to registry.jsonl (None for dry-run)
        dry_run: If True, skip writing the registry
        verbose: If True, print per-pattern detail to stdout

    Returns:
        List of registry entry dicts
    """
    # Normalize to list
    if isinstance(project_paths, Path):
        paths_list: list[Path] = [project_paths]
    else:
        paths_list = list(project_paths)

    # Step 1-2: Discover and parse error files from all projects
    all_entries: list[dict[str, Any]] = []
    for project_path in paths_list:
        entries = scan_project(project_path)
        all_entries.extend(entries)

    # Step 3-4: Fingerprint and group
    groups = group_by_fingerprint(all_entries)

    # Step 5: Evaluate thresholds (done inside merge_patterns)

    # Step 6: Merge with existing registry
    existing: dict[str, dict[str, Any]] = {}
    if not dry_run and registry_path is not None and registry_path.exists():
        existing = read_registry(registry_path)

    merged = merge_patterns(groups, existing)

    # Step 7: Write registry (unless dry-run)
    if not dry_run and registry_path is not None:
        try:
            write_registry(registry_path, merged)
        except OSError as e:
            error_msg = f"Failed to write registry to {registry_path}: {e}"
            print(f"error: {error_msg}", file=sys.stderr)
            if write_error_log is not None and paths_list:
                try:
                    write_error_log(
                        project_root=str(paths_list[0]),
                        error_type="file_write_failed",
                        context={"registry_path": str(registry_path)},
                        error_msg=error_msg,
                    )
                except Exception:
                    pass

    # Verbose output
    if verbose:
        print_verbose_output(merged)

    return merged


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="error_pattern_detector",
        description="Error Pattern Detector — detect recurring error patterns from *-errors.jsonl files",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--project",
        type=str,
        metavar="PATH",
        help="Scan a single project's error logs",
    )
    group.add_argument(
        "--all-projects",
        action="store_true",
        help="Scan all known projects (from path-index.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect patterns but don't write registry",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed detection output to stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for the error pattern detector.

    Follows the resilience pattern: catches all internal errors,
    logs them, and exits 0 (never blocks launchd).
    """
    try:
        _main_inner(argv)
    except SystemExit:
        raise
    except Exception as e:
        print(f"error: internal error: {e}", file=sys.stderr)
        if write_error_log is not None:
            try:
                write_error_log(
                    project_root=str(Path.cwd()),
                    error_type="file_write_failed",
                    context={"component": "error_pattern_detector"},
                    error_msg=f"Internal error in main: {e}",
                )
            except Exception:
                pass
        sys.exit(0)


def _main_inner(argv: list[str] | None = None) -> None:
    """Inner main logic (exceptions caught by outer main)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Determine project paths to scan
    project_paths: list[Path] = []

    if args.all_projects:
        project_paths = discover_all_projects()
    elif args.project:
        project_path = Path(args.project)
        if not project_path.exists():
            print(
                f"warning: project path {args.project} does not exist",
                file=sys.stderr,
            )
            sys.exit(0)
        project_paths = [project_path]
    else:
        # Auto-detect from cwd
        detected = detect_project_from_cwd()
        if detected is not None:
            project_paths = [detected]
        else:
            print(
                "warning: could not detect project from cwd, use --project or --all-projects",
                file=sys.stderr,
            )
            sys.exit(0)

    # Determine registry path
    registry_path: Path | None = None
    if not args.dry_run and project_paths:
        # Use the first project's memory/kb/patterns/ as the registry location
        registry_path = project_paths[0] / "memory" / "kb" / "patterns" / "registry.jsonl"

    # Run the pipeline
    run_pipeline(
        project_paths=project_paths,
        registry_path=registry_path,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
