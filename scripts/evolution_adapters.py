"""Adapter functions for converting audit tool output to Finding-compatible dicts."""
import hashlib
import re
from pathlib import Path


def normalize_location(location: str) -> str:
    """Normalize location to repo-relative path.

    - Strips CI runner absolute path prefixes (e.g. /Users/runner/work/repo/repo/...)
    - Strips common absolute path prefixes to find repo-relative portion
    - Returns empty string if location is empty or only whitespace
    - Returns the normalized path (without leading ./)
    """
    if not location or not location.strip():
        return ""
    location = location.strip()
    # If not an absolute path, just strip leading ./
    if not location.startswith("/"):
        return location.removeprefix("./")
    # Try to find repo-relative portion after known markers
    # CI patterns: /Users/runner/work/{repo}/{repo}/... or /home/runner/work/{repo}/{repo}/...
    # Local patterns: /Users/busiji/memory/... or any path containing /memory/ or /memory-core/
    for marker in ("/memory-core/", "/memory/"):
        idx = location.rfind(marker)  # Use rfind to get the LAST occurrence
        if idx != -1:
            relative = location[idx + len(marker):]
            return relative.removeprefix("./")
    # No known marker found; return original value as safe fallback
    return location


def sanitize_text(text: str, max_len: int = 500) -> str:
    """Sanitize untrusted text before it is embedded in an Issue body.

    Character removal (bidi/zero-width, control chars, inline links, HTML comments)
    runs FIRST in a fixed-point loop (max 3 iterations), THEN pattern defenses
    (credential redaction, @mention stripping, markdown line-start stripping).

    The fixed-point loop is needed because one removal step can re-expose patterns
    that another step handles. For example, removing zero-width chars from
    'ghp_AAAA\\u200bBBBB...' reassembles the credential pattern; removing inline
    links from '@[]()droid' regenerates '@droid'.

    Also redacts common credential patterns (VAL-FOLLOWUP-005).

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
    # ReDoS prevention: pre-truncate to 4× max_len before regex processing
    text = text[:max_len * 4]

    # Phase 1: Fixed-point loop for character removal (max 3 iterations)
    # This must run BEFORE pattern defenses so that removable characters
    # cannot be inserted within patterns to bypass redaction/stripping.
    for _iteration in range(3):
        previous = text
        # Strip Unicode bidi override / zero-width characters
        text = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069]', '', text)
        # Strip control characters (keep \t and \n which are legitimate in descriptions)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\r]', '', text)
        # Strip inline links [text](url) → text and inline images ![alt](url) → alt
        text = re.sub(r'!?\[([^\]]{0,500})\]\([^)]{0,500}\)', r'\1', text)
        # Strip HTML comments <!--...--> (prevent hidden instruction injection)
        text = re.sub(r'<!--.{0,2000}?>', '', text, flags=re.DOTALL)
        # Strip unclosed HTML comment <!--...$ (prevent partial marker forgery)
        text = re.sub(r'<!--.{0,2000}$', '', text, flags=re.DOTALL)
        if text == previous:
            break  # Fixed point reached

    # Phase 2: Pattern defenses (run AFTER character removal)
    # Redact common credential patterns
    # GitHub tokens (ghp_, github_pat_)
    text = re.sub(r'ghp_[A-Za-z0-9]{20,}', '***REDACTED***', text)
    text = re.sub(r'github_pat_[A-Za-z0-9_]+', '***REDACTED***', text)
    # AWS access keys (AKIA...)
    text = re.sub(r'AKIA[A-Z0-9]{16}', '***REDACTED***', text)
    # Slack tokens (xoxb-, xoxp-, xoxo-, xoxa-)
    text = re.sub(r'xox[bpoa]-[A-Za-z0-9-]+', '***REDACTED***', text)
    # OpenAI keys (sk-...)
    text = re.sub(r'sk-[A-Za-z0-9]{20,}', '***REDACTED***', text)
    # Remove @ mentions (use @+ to strip multi-@ like @@droid → droid)
    text = re.sub(r'@+(\w+)', r'\1', text)
    # Remove markdown headings, code fences, list markers at line start (including ~ for ~~~ fences)
    text = re.sub(r'^[#`>~-]+\s*', '', text, flags=re.MULTILINE)
    # Truncate
    if len(text) > max_len:
        text = text[:max_len] + "..."
    return text


def sanitize_structured_field(text: str, max_len: int = 100) -> str:
    """Sanitize structured fields (rule_id, location) to prevent field injection.

    Strips control characters (newlines, tabs, etc.) that could enable forging
    body headers. Strips leading/trailing whitespace. Strips bidi characters.
    Truncates to max_len with hash suffix on truncation to prevent collision.

    Args:
        text: Field value to sanitize
        max_len: Maximum length (default 100 for structured fields)

    Returns:
        Sanitized field with control characters removed and whitespace stripped
    """
    # Remove all control characters (newlines, tabs, etc.) including Unicode line/paragraph separators
    text = re.sub(r'[\x00-\x1f\x7f\u0085\u2028\u2029]', '', text)
    # Strip bidi override/formatting characters (prevent dedup asymmetry attacks)
    text = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2066-\u2069]', '', text)
    # Strip leading/trailing whitespace
    text = text.strip()
    # Truncate with hash suffix to prevent collision of different long values
    if len(text) > max_len:
        hash_suffix = hashlib.md5(text.encode()).hexdigest()[:8]
        text = text[:max_len - 9] + "." + hash_suffix
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
                "location": normalize_location(violation.get("file", "")),
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
                    "location": normalize_location(violation.get("file", "")),
                    "evidence": f"{label}: {name}, Detail: {violation.get('detail', '')}",
                })
    return findings


def _consistency_key(error_str: str) -> tuple:
    """Generate dedup key for consistency check findings.

    Includes content hash to prevent different errors with the same rule_id
    and location (both empty for many consistency errors) from collapsing
    into the same dedup key.
    """
    rule_id = _extract_rule_id(error_str)
    location = _extract_location(error_str)
    content_hash = hashlib.md5(error_str.encode()).hexdigest()[:8]
    return (rule_id, location, content_hash)


def _consistency_finding(error_str: str, severity: str) -> dict:
    """Build a Finding dict from a consistency check error/warning string."""
    return {
        "rule_id": _extract_rule_id(error_str),
        "severity": severity,
        "category": "consistency",
        "description": error_str,
        "location": _extract_location(error_str),
        "evidence": error_str,
    }


def adapt_consistency_check(raw: dict) -> list[dict]:
    """Convert consistency check output to Finding dicts.

    Input format: {errors: [str], warnings: [str], checks: [{name, errors, warnings, passed}]}

    Only processes top-level errors and warnings (which carry the [check_name]
    prefix needed for rule_id and location extraction). Per-check arrays contain
    the same strings WITHOUT the prefix, producing duplicate CONSISTENCY_ERROR
    findings with empty locations that cannot be deduped or resolved, causing
    persistent false-positive evolution reports. See INFRA-122.
    """
    findings = []
    seen = set()  # Track _consistency_key tuples to avoid duplicates

    def _add(error_str: str, severity: str):
        key = _consistency_key(error_str)
        if key not in seen:
            seen.add(key)
            findings.append(_consistency_finding(error_str, severity))

    # Process only top-level errors and warnings.
    # The consistency check tool always populates top-level with [check_name]
    # prefix; per-check arrays are redundant copies without the prefix.
    for error_str in raw.get("errors", []):
        _add(error_str, "warning")
    for warning_str in raw.get("warnings", []):
        _add(warning_str, "info")
    return findings


def _extract_rule_id(text: str) -> str:
    """Extract rule/check name from bracket-prefixed string like '[check_name] ...'."""
    if text.startswith("[") and "]" in text:
        return text[1:text.index("]")].upper()
    return "CONSISTENCY_ERROR"


def _extract_location(text: str) -> str:
    """Extract file path from string like '[check] /path/to/file: message'.

    Only returns a path if it looks like a valid file path:
    - Has a file extension (contains '.')
    - OR starts with '/' (absolute path)
    Otherwise returns empty string to prevent message text from being treated as location.
    """
    if "]" in text:
        rest = text[text.index("]") + 1:].strip()
        if ":" in rest:
            candidate = rest.split(":")[0].strip()
            # Validate: must have extension or be absolute path
            if "." in candidate or candidate.startswith("/"):
                return normalize_location(candidate)
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
            "location": normalize_location(f"{entry.get('script', 'unknown')}"),
            "evidence": (
                f"fingerprint={entry.get('fingerprint', '')}, "
                f"count={entry.get('total_count', 0)}, "
                f"threshold={threshold}"
            ),
        })
    return findings


def adapt_audit_layout(raw: dict) -> list[dict]:
    """Convert audit layout output to Finding dicts.

    Input format: parsed JSON object {violations: [{type, severity, file, detail}]}
    Scanner passes json.loads() result directly, so raw is the parsed dict.
    """
    data = raw if isinstance(raw, dict) else {}

    findings = []
    for violation in data.get("violations", []):
        findings.append({
            "rule_id": violation.get("type", "UNKNOWN").upper(),
            "severity": violation.get("severity", "info"),
            "category": "audit_layout",
            "description": violation.get("detail", ""),
            "location": violation.get("file", ""),
            "evidence": f"Detail: {violation.get('detail', '')}",
        })
    return findings


def adapt_validate_project(raw: dict) -> list[dict]:
    """Convert validate project output to Finding dicts.

    Input format: parsed JSON object {violations: [{type, severity, file, detail}]}
    Scanner passes json.loads() result directly, so raw is the parsed dict.
    """
    data = raw if isinstance(raw, dict) else {}

    findings = []
    for violation in data.get("violations", []):
        findings.append({
            "rule_id": violation.get("type", "UNKNOWN").upper(),
            "severity": violation.get("severity", "info"),
            "category": "validate_project",
            "description": violation.get("detail", ""),
            "location": violation.get("file", ""),
            "evidence": f"Detail: {violation.get('detail', '')}",
        })
    return findings


def adapt_evolution_self_audit(raw: dict | list) -> list[dict]:
    """Convert evolution self-audit output to Finding dicts.

    Input format: parsed JSON (list of finding dicts or {findings: [...]})
    Scanner passes json.loads() result directly, so raw is the parsed data.
    """
    data = raw if isinstance(raw, (list, dict)) else {}

    findings = []
    # Handle both list format and dict with "findings" key
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("findings", [])
    else:
        return []

    for finding in items:
        if not isinstance(finding, dict):
            continue
        # Normalize location to be relative path
        location = finding.get("location", "")
        if location.startswith("/"):
            # Convert absolute path to relative
            try:
                location = str(Path(location).relative_to(Path.cwd()))
            except ValueError:
                # Path is not relative to cwd, keep as-is
                pass

        findings.append({
            "rule_id": finding.get("rule_id", "UNKNOWN"),
            "severity": finding.get("severity", "info"),
            "category": finding.get("category", "evolution_self_audit"),
            "description": finding.get("description", ""),
            "location": location,
            "evidence": finding.get("evidence", ""),
        })
    return findings


ADAPTER_MAP = {
    "daily_kb_audit": adapt_daily_audit,
    "consistency_check": adapt_consistency_check,
    "error_patterns": adapt_error_patterns,
    "audit_layout": adapt_audit_layout,
    "validate_project": adapt_validate_project,
    "evolution_self_audit": adapt_evolution_self_audit,
}

# Map tool names to the set of category values their findings carry.
# Used by update_history to skip false "resolved" when a tool fails.
TOOL_TO_CATEGORIES = {
    "daily_kb_audit": {"daily_audit"},
    "consistency_check": {"consistency"},
    "error_patterns": {"error_pattern"},
    "audit_layout": {"audit_layout"},
    "validate_project": {"validate_project"},
    "evolution_self_audit": {"evolution_self_audit"},
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
