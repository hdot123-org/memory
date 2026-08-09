"""Adapter functions for converting audit tool output to Finding-compatible dicts."""
import re


def sanitize_text(text: str, max_len: int = 500) -> str:
    """Sanitize untrusted text before it is embedded in an Issue body.

    Removes @-mentions, inline links/images, line-leading markdown, bidi
    override characters, and control characters; truncates to max_len.

    RESIDUAL RISK: This is NOT a complete prompt-injection defense. Plain-text
    imperative instructions aimed at the consuming agent are intentionally NOT
    neutralized, because description/evidence must remain readable. The Issue
    body therefore structurally marks untrusted regions (see create_issue).

    Args:
        text: Text to sanitize
        max_len: Maximum length before truncation (default 500)

    Returns:
        Sanitized text
    """
    # Strip Unicode bidi override characters (prevent text obfuscation attacks)
    text = re.sub(r'[\u202a-\u202e\u2066-\u2069]', '', text)
    # Strip control characters (keep \t and \n which are legitimate in descriptions)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\r]', '', text)
    # Remove @ mentions (prevent triggering GitHub users/bots)
    text = re.sub(r'@(\w+)', r'\1', text)
    # Strip inline links [text](url) → text and inline images ![alt](url) → alt
    text = re.sub(r'!?\[([^\]]*)\]\([^)]*\)', r'\1', text)
    # Remove markdown headings, code fences, list markers at line start (including ~ for ~~~ fences)
    text = re.sub(r'^[#`>~-]+\s*', '', text, flags=re.MULTILINE)
    # Truncate
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def sanitize_structured_field(text: str, max_len: int = 100) -> str:
    """Sanitize structured fields (rule_id, location) to prevent field injection.

    Strips control characters (newlines, tabs, etc.) that could enable forging
    body headers. Truncates to max_len.

    Args:
        text: Field value to sanitize
        max_len: Maximum length (default 100 for structured fields)

    Returns:
        Sanitized field with control characters removed
    """
    # Remove all control characters (newlines, tabs, etc.) including Unicode line/paragraph separators
    text = re.sub(r'[\x00-\x1f\x7f\u0085\u2028\u2029]', '', text)
    # Truncate
    if len(text) > max_len:
        text = text[:max_len]
    return text


def adapt_daily_audit(raw: dict) -> list[dict]:
    """Convert nested daily audit output to flat Finding dicts.

    Input format: {projects: {name: {violations: [{type, severity, file, detail}]}},
                   infrastructure: {servers: {name: {violations: [...]}}}}
    """
    findings = []
    for project_name, project_data in raw.get("projects", {}).items():
        if not isinstance(project_data, dict):
            continue
        for violation in project_data.get("violations", []):
            findings.append({
                "rule_id": violation.get("type", "UNKNOWN").upper(),
                "severity": violation.get("severity", "info"),
                "category": "daily_audit",
                "description": violation.get("detail", ""),
                "location": violation.get("file", ""),
                "evidence": f"Project: {project_name}, Detail: {violation.get('detail', '')}",
            })
    # Infrastructure servers and databases carry the same violations schema
    infra = raw.get("infrastructure", {})
    for kind in ("servers", "databases"):
        for name, data in infra.get(kind, {}).items():
            if not isinstance(data, dict):
                continue
            for violation in data.get("violations", []):
                label = "Server" if kind == "servers" else "Database"
                findings.append({
                    "rule_id": violation.get("type", "UNKNOWN").upper(),
                    "severity": violation.get("severity", "info"),
                    "category": "daily_audit",
                    "description": violation.get("detail", ""),
                    "location": violation.get("file", ""),
                    "evidence": f"{label}: {name}, Detail: {violation.get('detail', '')}",
                })
    return findings


def adapt_consistency_check(raw: dict) -> list[dict]:
    """Convert consistency check output to Finding dicts.

    Input format: {errors: [str], warnings: [str], checks: [{name, errors, warnings, passed}]}
    """
    findings = []
    seen = set()  # Track (description, location) pairs to avoid duplicates

    # Top-level errors
    for error_str in raw.get("errors", []):
        rule_id = _extract_rule_id(error_str)
        location = _extract_location(error_str)
        key = (error_str, location)
        if key not in seen:
            seen.add(key)
            findings.append({
                "rule_id": rule_id,
                "severity": "warning",
                "category": "consistency",
                "description": error_str,
                "location": location,
                "evidence": error_str,
            })
    # Top-level warnings
    for warning_str in raw.get("warnings", []):
        rule_id = _extract_rule_id(warning_str)
        location = _extract_location(warning_str)
        key = (warning_str, location)
        if key not in seen:
            seen.add(key)
            findings.append({
                "rule_id": rule_id,
                "severity": "info",
                "category": "consistency",
                "description": warning_str,
                "location": location,
                "evidence": warning_str,
            })
    # Process checks array
    for check in raw.get("checks", []):
        if not isinstance(check, dict):
            continue
        # Check errors
        for error_str in check.get("errors", []):
            rule_id = _extract_rule_id(error_str)
            location = _extract_location(error_str)
            key = (error_str, location)
            if key not in seen:
                seen.add(key)
                findings.append({
                    "rule_id": rule_id,
                    "severity": "warning",
                    "category": "consistency",
                    "description": error_str,
                    "location": location,
                    "evidence": error_str,
                })
        # Check warnings
        for warning_str in check.get("warnings", []):
            rule_id = _extract_rule_id(warning_str)
            location = _extract_location(warning_str)
            key = (warning_str, location)
            if key not in seen:
                seen.add(key)
                findings.append({
                    "rule_id": rule_id,
                    "severity": "info",
                    "category": "consistency",
                    "description": warning_str,
                    "location": location,
                    "evidence": warning_str,
                })
    return findings


def _extract_rule_id(text: str) -> str:
    """Extract rule/check name from bracket-prefixed string like '[check_name] ...'."""
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")].upper()
    return "CONSISTENCY_ERROR"


def _extract_location(text: str) -> str:
    """Extract file path from string like '[check] /path/to/file: message'."""
    if "]" in text:
        rest = text[text.index("]") + 1:].strip()
        if ":" in rest:
            return rest.split(":")[0].strip()
    return ""


def adapt_error_patterns(lines: list[dict]) -> list[dict]:
    """Convert registry.jsonl entries to Finding dicts.

    Input: list of dicts from JSONL lines with fields:
    fingerprint, type, script, normalized_msg, status, threshold_met, etc.
    """
    findings = []
    for entry in lines:
        threshold = entry.get("threshold_met")
        if not threshold:
            continue
        findings.append({
            "rule_id": f"ERROR_PATTERN_{entry.get('type', 'UNKNOWN').upper()}",
            "severity": "critical" if threshold == "both" else "warning",
            "category": "error_pattern",
            "description": entry.get("normalized_msg", ""),
            "location": f"{entry.get('script', 'unknown')}",
            "evidence": (
                f"fingerprint={entry.get('fingerprint', '')}, "
                f"count={entry.get('total_count', 0)}, "
                f"threshold={threshold}"
            ),
        })
    return findings


ADAPTER_MAP = {
    "daily_kb_audit": adapt_daily_audit,
    "consistency_check": adapt_consistency_check,
    "error_patterns": adapt_error_patterns,
}


def quarantine_corrupted_file(history_path) -> None:
    """Rename corrupted history file to quarantine path with timestamp."""
    from datetime import datetime, timezone
    if not history_path.exists():
        return
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    qpath = history_path.with_suffix(f".corrupted.{ts}.json")
    # Handle collision: if quarantine file already exists, append counter
    counter = 1
    while qpath.exists():
        qpath = history_path.with_suffix(f".corrupted.{ts}.{counter}.json")
        counter += 1
    history_path.rename(qpath)
    print(f"[evolution] Warning: {history_path} corrupted, quarantined to {qpath}")
