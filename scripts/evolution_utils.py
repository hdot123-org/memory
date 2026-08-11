"""Utility functions for evolution scanner."""
import json
import subprocess
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


def _parse_issue_category(body: str) -> str | None:
    """Parse the Category field from an issue body.

    Used by auto_close_resolved to decide whether an issue belongs to a failed
    audit category (GAP-C1). Returns the category string, or None when the
    field is absent (e.g. legacy issues created without the Category line).
    """
    for line in body.split('\n'):
        if line.startswith('**Description**') or line.startswith('**Evidence**'):
            break
        if line.startswith('**Category**:'):
            value = line.split(':', 1)[1].strip()
            return value or None
    return None


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


def auto_close_resolved(findings: list, dedup_label: str, failed_categories: set[str] | None = None) -> None:
    """Close GitHub Issues whose findings are no longer present in current scan.

    Compares current findings against open evolution-found GitHub Issues.
    Issues whose (rule_id, location) is NOT in current findings are closed
    via `gh issue close` with an explanatory comment.

    Issues whose category belongs to a failed audit tool are NOT closed: a
    crashed/timed-out tool emits no findings, so its issues temporarily
    disappear from the current scan even though the underlying problem may
    still exist. Such issues are skipped with a warning instead (GAP-C1).

    Args:
        findings: List of Finding objects from current scan
        dedup_label: Label used to identify evolution scanner issues
        failed_categories: Set of audit categories whose tool failed this tick.
            Issues whose category is in this set are protected from auto-close.
    """
    # Build set of current finding keys
    current_keys = {(f.rule_id, f.location) for f in findings}

    # Fetch all open evolution-found issues
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--search", f"label:{dedup_label}",
             "--state", "open", "--limit", "200", "--json", "number,body"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"[evolution] Warning: Failed to list open issues: {result.stderr}")
            return

        issues = json.loads(result.stdout) if result.stdout.strip() else []
    except Exception as e:
        print(f"[evolution] Warning: Failed to fetch open issues: {e}")
        return

    # Close issues not in current findings
    closed_count = 0
    protected_count = 0
    for issue in issues:
        rule_id, location = _parse_issue_fields(issue.get("body", ""))
        if rule_id is None or location is None:
            continue

        issue_key = (rule_id, location)
        if issue_key not in current_keys:
            # GAP-C1: protect issues whose category came from a failed audit tool.
            # A failed tool emits no findings, so its issues vanish from the
            # current scan even though the underlying problem may still exist.
            if failed_categories:
                category = _parse_issue_category(issue.get("body", ""))
                if category and category in failed_categories:
                    protected_count += 1
                    print(f"[evolution] Skip auto-close #{issue['number']}: category '{category}' tool failed this tick ({rule_id} @ {location})")
                    continue

            # This finding is no longer present - close the issue
            close_msg = (
                f"该 finding 在最近一次扫描中已不再出现，自动关闭此 Issue。"
                f"（Rule: {rule_id}, Location: {location}）"
            )
            try:
                close_result = subprocess.run(
                    ["gh", "issue", "close", str(issue["number"]),
                     "--comment", close_msg],
                    capture_output=True, text=True, timeout=30
                )
                if close_result.returncode == 0:
                    closed_count += 1
                    print(f"[evolution] Closed issue #{issue['number']}: {rule_id} @ {location}")
                else:
                    print(f"[evolution] Warning: Failed to close issue #{issue['number']}: {close_result.stderr}")
            except Exception as e:
                print(f"[evolution] Warning: Failed to close issue #{issue['number']}: {e}")

    if closed_count > 0:
        print(f"[evolution] Auto-closed {closed_count} resolved issues")
    if protected_count > 0:
        print(f"[evolution] Protected {protected_count} issue(s) from auto-close due to failed audit categories")
