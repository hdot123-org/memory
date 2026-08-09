"""Utility functions for evolution scanner."""
import json
from pathlib import Path

from evolution_adapters import quarantine_corrupted_file, sanitize_structured_field

_SEV_RANK = {"critical": 3, "warning": 2, "info": 1}


def dedup_intra_tick(findings):
    """Remove duplicate findings within a single tick.

    Keeps the highest severity finding for each (rule_id, location) pair.

    Args:
        findings: List of Finding objects

    Returns:
        List of Finding objects with duplicates removed
    """
    best = {}
    for f in findings:
        key = (f.rule_id, f.location)
        if key not in best or _SEV_RANK.get(f.severity, 0) > _SEV_RANK.get(best[key].severity, 0):
            best[key] = f
    return list(best.values())


def _parse_issue_fields(body: str):
    """Parse rule_id and location from issue body.

    Extracts structured fields from markdown-formatted issue body.
    Applies sanitization to ensure round-trip consistency with normalize_finding.

    Args:
        body: Issue body text

    Returns:
        Tuple of (rule_id, location)
    """
    rule_id = location = None

    for line in body.split('\n'):
        if line.startswith('**Description**') or line.startswith('**Evidence**'):
            break
        if rule_id is None and line.startswith('**Rule ID**:'):
            rule_id = sanitize_structured_field(line.split(':', 1)[1].strip())
        elif location is None and line.startswith('**Location**:'):
            location = sanitize_structured_field(line.split(':', 1)[1].strip())
        if rule_id and location:
            break

    return rule_id, location


def load_history(history_path: Path):
    """Load evolution history from JSON file with structural validation.

    Validates that the file contains a dict with 'snapshots' as a list.
    Quarantines corrupted files and returns None on failure.

    Args:
        history_path: Path to history JSON file

    Returns:
        Dict with history data, or None if file is missing/invalid
    """
    if not history_path.exists():
        return None

    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        print(f"[evolution] Warning: Failed to load {history_path}: {e}")
        quarantine_corrupted_file(history_path)
        return None

    # Structural validation
    if not isinstance(data, dict) or not isinstance(data.get('snapshots'), list):
        print(f"[evolution] Warning: Invalid history structure in {history_path}")
        quarantine_corrupted_file(history_path)
        return None

    return data
