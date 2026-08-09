"""Utility functions for evolution scanner."""
import json
import sys
from pathlib import Path

from evolution_adapters import quarantine_corrupted_file, sanitize_structured_field

_SEV_RANK = {"critical": 3, "warning": 2, "info": 1}

# Required config keys for evolution scanner
REQUIRED_CONFIG_KEYS = [
    "audit_tools",
    "severity_order",
    "dedup_label",
    "isolation_threshold",
    "failure_label",
    "max_issues_per_tick",
    "snapshot_limit",
]


def validate_config(config: dict) -> None:
    """Validate that all required config keys are present.

    Args:
        config: Configuration dictionary from .evolution/config.yml

    Raises:
        SystemExit: If config is not a dict or any required keys are missing
    """
    # VAL-R3-006: Guard against None (empty config.yml → yaml.safe_load returns None)
    if not isinstance(config, dict):
        print("[evolution] Error: config.yml must be a YAML mapping (got empty or invalid file)")
        sys.exit(1)

    missing_keys = [key for key in REQUIRED_CONFIG_KEYS if key not in config]
    if missing_keys:
        print(f"[evolution] Error: Missing required config keys: {', '.join(missing_keys)}")
        print("[evolution] Please check .evolution/config.yml for required fields")
        sys.exit(1)


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
    Also validates each snapshot entry is a dict with 'findings' key.
    Corrupt snapshot entries are skipped with a warning.
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

    # Deep validation: each snapshot must be a dict with 'findings' as a list
    # Skip corrupt entries with a warning, preserve valid entries (VAL-FOLLOWUP-001)
    valid_snapshots = []
    for i, snapshot in enumerate(data['snapshots']):
        if isinstance(snapshot, dict) and 'findings' in snapshot:
            # P2-3: findings must be a list
            if not isinstance(snapshot['findings'], list):
                print(f"[evolution] Warning: Snapshot at index {i} has non-list findings in {history_path}, skipped")
                continue
            # Filter non-dict entries from findings
            valid_findings = [f for f in snapshot['findings'] if isinstance(f, dict)]
            if len(valid_findings) != len(snapshot['findings']):
                print(f"[evolution] Warning: Filtered {len(snapshot['findings']) - len(valid_findings)} non-dict findings from snapshot {i} in {history_path}")
            # P3: Deep-validate finding dicts have required keys for dedup
            required_finding_keys = {"rule_id", "location"}
            before_count = len(valid_findings)
            valid_findings = [f for f in valid_findings if required_finding_keys.issubset(f.keys())]
            if len(valid_findings) < before_count:
                dropped = before_count - len(valid_findings)
                print(f"[evolution] Warning: Dropped {dropped} findings missing rule_id/location in snapshot {i} in {history_path}")
            snapshot['findings'] = valid_findings
            valid_snapshots.append(snapshot)
        else:
            print(f"[evolution] Warning: Corrupt snapshot at index {i} in {history_path}, skipped")
    data['snapshots'] = valid_snapshots

    # VAL-R3-004: resolved_findings must be a list; reset to [] if not
    if 'resolved_findings' in data and not isinstance(data['resolved_findings'], list):
        print(f"[evolution] Warning: resolved_findings is not a list in {history_path}, resetting to []")
        data['resolved_findings'] = []
    # Validate resolved_findings entries: each must be dict with rule_id and location
    elif isinstance(data.get('resolved_findings'), list):
        valid_resolved = []
        for i, entry in enumerate(data['resolved_findings']):
            if isinstance(entry, dict) and 'rule_id' in entry and 'location' in entry:
                valid_resolved.append(entry)
            else:
                print(f"[evolution] Warning: Corrupt resolved_findings at index {i} in {history_path}, skipped")
        data['resolved_findings'] = valid_resolved

    return data
