"""Adapter functions for converting audit tool output to Finding-compatible dicts."""
import re


def sanitize_text(text: str, max_len: int = 500) -> str:
    """Sanitize text to prevent prompt injection attacks.

    Removes @ mentions (to prevent triggering GitHub users/bots),
    removes dangerous markdown formatting, and truncates to max_len.

    Args:
        text: Text to sanitize
        max_len: Maximum length before truncation (default 500)

    Returns:
        Sanitized text
    """
    # Remove @ mentions (prevent triggering GitHub users/bots)
    text = re.sub(r'@(\w+)', r'\1', text)
    # Remove markdown headings, code fences, list markers at line start
    text = re.sub(r'^[#`>-]+\s*', '', text, flags=re.MULTILINE)
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
    # Remove all control characters (newlines, tabs, etc.)
    text = re.sub(r'[\x00-\x1f\x7f]', '', text)
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
    # Infrastructure servers are also under projects or separately
    infra = raw.get("infrastructure", {})
    for server_name, server_data in infra.get("servers", {}).items():
        if not isinstance(server_data, dict):
            continue
        for violation in server_data.get("violations", []):
            findings.append({
                "rule_id": violation.get("type", "UNKNOWN").upper(),
                "severity": violation.get("severity", "info"),
                "category": "daily_audit",
                "description": violation.get("detail", ""),
                "location": violation.get("file", ""),
                "evidence": f"Server: {server_name}, Detail: {violation.get('detail', '')}",
            })
    return findings


def adapt_consistency_check(raw: dict) -> list[dict]:
    """Convert consistency check output to Finding dicts.

    Input format: {errors: [str], warnings: [str], checks: [{name, errors, warnings, passed}]}
    """
    findings = []
    # Top-level errors
    for error_str in raw.get("errors", []):
        rule_id = _extract_rule_id(error_str)
        findings.append({
            "rule_id": rule_id,
            "severity": "warning",
            "category": "consistency",
            "description": error_str,
            "location": "",
            "evidence": error_str,
        })
    # Top-level warnings
    for warning_str in raw.get("warnings", []):
        rule_id = _extract_rule_id(warning_str)
        findings.append({
            "rule_id": rule_id,
            "severity": "info",
            "category": "consistency",
            "description": warning_str,
            "location": _extract_location(warning_str),
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
