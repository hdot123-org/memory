#!/usr/bin/env python3.12
"""Layer D — Error Pattern Detector.

Deterministic fingerprinting and pattern grouping engine for error logs.
Reads *-errors.jsonl files, normalizes messages, computes fingerprints,
groups by pattern, evaluates thresholds, and writes registry.

Usage:
    from memory_core.tools.error_pattern_detector import (
        normalize_error_msg,
        compute_fingerprint,
        group_by_fingerprint,
        evaluate_threshold,
    )
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Any

# Import-guarded error_logger for self-failure logging
try:
    from memory_core.tools.error_logger import write_error_log
except ImportError:
    write_error_log = None  # type: ignore[assignment]


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
    # Matches: 2026-07-12T11:07:05.219585+08:00, 2026-07-12 11:07:05, 2026-07-12T11:07:05Z, etc.
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
# Pattern Group Data Structure (VAL-DETECT-001 through VAL-DETECT-020)
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
        # Extract fields (handle missing msg gracefully)
        ts: str = entry.get("ts", "")
        error_type: str = entry.get("type", "")
        script: str = entry.get("script", "")
        project: str = entry.get("project", "")
        msg: str = entry.get("msg", "")
        if msg is None:
            msg = ""

        # Normalize and fingerprint
        normalized = normalize_error_msg(msg)
        fp = compute_fingerprint(error_type, script, normalized)

        # Extract date from ts (first 10 chars: YYYY-MM-DD)
        date_str = ts[:10] if len(ts) >= 10 else ""

        # Initialize or update group
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

            # Update first_seen/last_seen (string comparison works for ISO format)
            if ts < group.first_seen:
                group.first_seen = ts
                group.sample_first = {"ts": ts, "msg": msg}
            if ts > group.last_seen or ts == group.last_seen:
                group.last_seen = ts
                group.sample_last = {"ts": ts, "msg": msg}

            # Add distinct day if not already present
            if date_str and date_str not in group.distinct_days:
                group.distinct_days.append(date_str)

            # Add project if not already present
            if project and project not in group.projects:
                group.projects.append(project)

    # Sort distinct_days and projects for determinism
    for group in groups.values():
        group.distinct_days.sort()
        group.projects.sort()

    return groups


# ---------------------------------------------------------------------------
# Threshold Evaluation (VAL-DETECT-012 through VAL-DETECT-017)
# ---------------------------------------------------------------------------


def evaluate_threshold(group: PatternGroup) -> str | None:
    """Evaluate recurrence threshold for a pattern group.

    Threshold rules:
    - distinct_days >= 2 AND total_count >= 5 → "both"
    - distinct_days >= 2 AND total_count < 5  → "days"
    - distinct_days < 2  AND total_count >= 5 → "count"
    - Neither                                  → None

    Args:
        group: PatternGroup with aggregated metadata

    Returns:
        "both", "days", "count", or None
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
# Main entry point (for CLI, to be implemented in next feature)
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point (placeholder for registry-cli-resilience feature)."""
    print("Error Pattern Detector — CLI not yet implemented")
    print("This module provides core fingerprinting functions.")
    print("Use: normalize_error_msg(), compute_fingerprint(), group_by_fingerprint(), evaluate_threshold()")


if __name__ == "__main__":
    main()
