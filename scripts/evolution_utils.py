"""Utility functions for evolution scanner."""
import json
import logging
import os
import re
import statistics
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evolution_adapters import quarantine_corrupted_file, sanitize_structured_field

_SEV_RANK = {"critical": 3, "warning": 2, "info": 1}

# GAP-C3: Grace period for auto-close
# A finding must be absent for this many consecutive ticks before its issue is closed.
# Prevents false closures from transient adapter failures.
# Increased from 2→3 (2026-08-13): 2 ticks is marginal for transient adapter failures.
GRACE_PERIOD_TICKS = 3

# Self-audit findings (e.g., heartbeat staleness) are transient health signals,
# not code defects. They resolve when the scanner recovers, not when code is
# fixed via PR. Auto-closing them triggers a flapping loop with the state gate
# (Gate A). Exclude them from auto-close (INFRA-216).
SELF_AUDIT_CATEGORY = "evolution_self_audit"

# Deadlock exit sentinel prefix (architecture §3.2).
# Written by reconcile-evolution.sh when pushing a stale non-terminal Linear
# issue to terminal after verifying session-completed+exitCode=0.
# The trust chain (_verify_fix_merged_via_linear) checks for this sentinel
# as an alternative verification path alongside merged PR attachments.
DEADLOCK_EXIT_SENTINEL_PREFIX = "<!-- deadlock-exit "

# Required config keys for evolution scanner
REQUIRED_CONFIG_KEYS = [
    "audit_tools",
    "severity_order",
    "dedup_label",
    "isolation_threshold",
    "failure_label",
    "max_issues_per_tick",
    "max_self_audit_issues_per_tick",
    "max_code_hygiene_issues_per_tick",
    "snapshot_limit",
]


def validate_config(config: dict[str, Any]) -> None:
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


def dedup_intra_tick(findings: list[Any]) -> list[Any]:
    """Remove duplicate findings within a single tick.

    Keeps the highest severity finding for each (rule_id, location) pair.

    Args:
        findings: List of Finding objects

    Returns:
        List of Finding objects with duplicates removed
    """
    best: dict[tuple[str, str], Any] = {}
    for f in findings:
        key = (f.rule_id, f.location)
        if key not in best or _SEV_RANK.get(f.severity, 0) > _SEV_RANK.get(best[key].severity, 0):
            best[key] = f
    return list(best.values())


def _parse_issue_fields(body: str) -> tuple[str | None, str | None]:
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


def load_history(history_path: Path) -> dict[str, Any] | None:
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


def _count_consecutive_absences(rule_id: str, location: str, history_path: Path) -> int:
    """Count consecutive absences of a finding in history snapshots.

    GAP-C3 FIX (v2): Walks backwards through history snapshots to count how many
    consecutive recent snapshots lack the (rule_id, location) pair.

    CRITICAL INVARIANT: main() calls update_history() BEFORE auto_close_resolved(),
    so the current tick's snapshot is ALREADY the most-recent entry in history.
    This function MUST NOT add +1 for the current tick — doing so double-counts
    it and defeats the grace period (Issue #455).

    When called, the function is invoked because the finding is absent in the
    current tick. Since update_history() already wrote the current snapshot
    (which does not contain this finding), the first snapshot examined is
    already the current tick's absence.

    Args:
        rule_id: The rule ID to check
        location: The location to check
        history_path: Path to findings_over_time.json

    Returns:
        Number of consecutive absences (0 if no history or finding present in
        most recent snapshot)
    """
    data = load_history(history_path)
    if data is None:
        return 0

    snapshots = data.get("snapshots", [])
    if not snapshots:
        return 0

    # Walk backwards through snapshots counting consecutive absences
    absence_count = 0
    for snapshot in reversed(snapshots):
        findings = snapshot.get("findings", [])
        present = any(
            f.get("rule_id") == rule_id and f.get("location") == location
            for f in findings if isinstance(f, dict)
        )
        if present:
            break
        absence_count += 1

    return absence_count


# ============================================================================
# PR-Merged Verification (M1 Trust Chain)
# ============================================================================

logger = logging.getLogger(__name__)


def _has_linear_linkback_marker(issue_body: str, issue_comments: str = "") -> bool:
    """Check if text contains a linear-linkback marker (any format).

    Used to distinguish "no Linear association at all" (environmental finding,
    backward-compat allow close) from "marker present but ID unextractable"
    (fail-closed to prevent unverified close).
    """
    return "linear-linkback" in issue_body or "linear-linkback" in issue_comments


def _extract_linear_linkback(issue_body: str, issue_comments: str = "") -> str | None:
    """Extract INFRA-xxx ID from linear-linkback in issue body or comments.

    Two-tier extraction:
    - Tier 1: inline HTML comment format ``<!-- linear-linkback INFRA-xxx -->``
      (backward compat with existing issues).
    - Tier 2: only when ``linear-linkback`` marker string is present in text:
      - href format: ``linear.app/.../issue/INFRA-xxx``
      - anchor text format: ``<a ...>INFRA-xxx</a>``
      This handles the format written by linear-code (bare marker + external
      anchor), which caused 25 false closures in the #648 oscillation.

    Returns:
        The INFRA-xxx identifier, or None if not found.  Callers must check
        ``_has_linear_linkback_marker`` to distinguish "no Linear association"
        (allow close) from "marker present but extraction failed" (fail-closed).
    """
    combined = issue_body + "\n" + issue_comments

    # Tier 1: inline HTML comment format (backward compat)
    pattern = r'<!--\s*linear-linkback\s+(INFRA-\d+)\s*-->'
    match = re.search(pattern, combined)
    if match:
        return match.group(1)

    # Tier 2: only attempt when marker is present (avoids false positives
    # on environmental findings with no Linear association)
    if "linear-linkback" not in combined:
        return None

    # Tier 2a: extract from href (linear.app/OWNER/issue/INFRA-xxx)
    href_pattern = r'linear\.app/[^/\s"]+/issue/([A-Z]+-\d+)'
    match = re.search(href_pattern, combined)
    if match:
        return match.group(1)

    # Tier 2b: extract from anchor text (<a ...>INFRA-xxx</a>)
    anchor_pattern = r'<a[^>]*>\s*([A-Z]+-\d+)\s*</a>'
    match = re.search(anchor_pattern, combined)
    if match:
        return match.group(1)

    return None


def _split_comment_blocks(comments_text: str) -> list[str]:
    """Split combined comment text into comment blocks (blank-line separated).

    ``gh issue view --json comments --jq '.comments[].body'`` emits each
    comment body in raw form, so a multi-line comment body arrives as a
    contiguous run of lines with no per-comment delimiter. Comment blocks
    are therefore delimited by blank lines: consecutive non-empty lines
    belong to the same block (see docs/architecture/issue-flow.md §9.4).
    """
    blocks: list[str] = []
    current: list[str] = []
    for line in comments_text.split("\n"):
        if line.strip() == "":
            if current:
                blocks.append("\n".join(current))
                current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))
    return blocks


def extract_linkback_anchor(comments_text: str) -> str | None:
    """Extract anchor (INFRA-xxx) from the marker-bearing COMMENT BLOCK.

    Window semantics (INFRA-357): the extraction window is the ENTIRE
    comment block containing the ``linear-linkback`` marker, not just the
    marker line. Production linkback comments (ci-gateway multi-line
    format) carry a bare marker line with the href on a following line::

        _此 comment 由 ci-gateway skill 自动生成。_
        <!-- linear-linkback -->
        <p><a href="https://linear.app/jtoom/issue/INFRA-357">INFRA-357</a></p>

    Line-scoped extraction returned None for every such comment (the marker
    line itself carries no id). Contract: docs/architecture/issue-flow.md
    §9.4 / §10.3.

    #724 safety rationale: extraction stays scoped to the FIRST
    marker-bearing block only. Notification issues whose bodies/comments
    merely MENTION an INFRA id (no marker) still yield None, and ids in
    later comment blocks are never harvested — this prevents full-text
    false matches like the #724 mis-closures.

    Algorithm:
    1. Split comments into comment blocks (blank-line separated)
    2. Pick the FIRST block containing the "linear-linkback" marker
    3. Apply tiers in order within that block: Tier1 inline marker,
       Tier2a href, Tier2b anchor text
    4. Return INFRA-xxx or None

    Args:
        comments_text: Combined comment bodies, as returned by
            gh issue view --json comments --jq '.comments[].body'

    Returns:
        INFRA-xxx identifier from the first linkback comment block, or None
        (marker present but no id extractable -> None, fail-closed).
    """
    if not comments_text or "linear-linkback" not in comments_text:
        return None

    # Find first comment BLOCK containing "linear-linkback" marker
    linkback_block = None
    for block in _split_comment_blocks(comments_text):
        if "linear-linkback" in block:
            linkback_block = block
            break

    if not linkback_block:
        return None

    # Apply Tier1 extraction: <!-- linear-linkback INFRA-xxx -->
    pattern = r'<!--\s*linear-linkback\s+(INFRA-\d+)\s*-->'
    match = re.search(pattern, linkback_block)
    if match:
        return match.group(1)

    # Apply Tier2a: href format (linear.app/OWNER/issue/INFRA-xxx)
    href_pattern = r'linear\.app/[^/\s"]+/issue/([A-Z]+-\d+)'
    match = re.search(href_pattern, linkback_block)
    if match:
        return match.group(1)

    # Apply Tier2b: anchor text (<a ...>INFRA-xxx</a>) - FIRST occurrence only
    anchor_pattern = r'<a[^>]*>\s*([A-Z]+-\d+)\s*</a>'
    match = re.search(anchor_pattern, linkback_block)
    if match:
        return match.group(1)

    # Marker present but extraction failed - return None (caller decides fail-closed)
    return None


def _check_merged_pr(github_prs: list[dict[str, Any]], linear_id: str) -> bool | None:
    """Check if any GitHub PR attachment is merged.

    Args:
        github_prs: List of GitHub PR attachment dicts from Linear API
        linear_id: Linear issue identifier (e.g., INFRA-123)

    Returns:
        True if any PR is merged, False on gh error (caller should fail-closed),
        None if PRs exist but none merged OR no PRs had extractable numbers
        (caller should fall through to next verification path — deadlock sentinel).
    """
    for pr_attachment in github_prs:
        pr_url = pr_attachment.get("url", "")
        pr_match = re.search(r'/pull/(\d+)', pr_url)
        if not pr_match:
            continue

        pr_number = pr_match.group(1)
        # Extract owner/repo so cross-repo PRs are verified against the
        # correct repository. Without --repo, gh pr view only checks the
        # current repo context and silently fails (fail-open) for PRs in
        # other repos — the merge state is never actually confirmed.
        repo_match = re.search(r'github\.com/([^/]+/[^/]+)/pull/', pr_url)
        gh_cmd = ["gh", "pr", "view", pr_number, "--json", "mergedAt"]
        if repo_match:
            gh_cmd.extend(["--repo", repo_match.group(1)])

        try:
            result = subprocess.run(
                gh_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                pr_data = json.loads(result.stdout)
                if pr_data.get("mergedAt"):
                    logger.info(f"PR #{pr_number} for {linear_id} is merged")
                    return True
                else:
                    logger.info(f"PR #{pr_number} for {linear_id} not yet merged")
            else:
                # gh pr view failed - fail-closed: block close immediately
                logger.warning(
                    f"gh pr view failed for PR #{pr_number}: {result.stderr} — "
                    f"fail-closed: blocking close to prevent unverified state"
                )
                return False
        except Exception as e:
            # gh pr view exception - fail-closed: block close immediately
            logger.warning(
                f"Exception checking PR #{pr_number} via gh CLI: {e} — "
                f"fail-closed: blocking close to prevent unverified state"
            )
            return False

    # All PRs checked but none merged, or no extractable PRs
    # → fall through to Path B sentinel check (architecture §3.2)
    return None
def _fetch_issue_comments(issue_number: int) -> str | None:
    """Fetch issue comments for linkback/sentinel search.

    Returns:
        Comment text if successful, None if fetch fails (fail-closed signal)
    """
    try:
        comment_result = subprocess.run(
            ["gh", "issue", "view", str(issue_number),
             "--json", "comments", "--jq", ".comments[].body"],
            capture_output=True, text=True, timeout=30
        )
        if comment_result.returncode == 0:
            return comment_result.stdout
        else:
            logger.warning(
                f"Failed to fetch comments for issue #{issue_number} "
                f"(exit code {comment_result.returncode}): {comment_result.stderr}"
            )
            return None
    except Exception as e:
        logger.warning(f"Exception fetching comments for issue #{issue_number}: {e}")
        return None


def _verify_fix_merged_via_linear(issue_body: str, issue_number: int | None = None) -> bool:
    """Verify that the fix for this issue has been merged via Linear API.

    Extracts INFRA-xxx ID from linear-linkback HTML comment in issue body or
    comments, queries Linear GraphQL API for issue state and GitHub PR
    attachments, and checks if any PR has been merged (mergedAt != null).

    Args:
        issue_body: GitHub Issue body text
        issue_number: Issue number. When provided, fetches issue comments to
            search for linear-linkback (Linear integration writes it in
            comments, not the body).

    Returns:
        True if a merged PR is verified or if no Linear linkback exists
        (backward compat for environmental findings — allow close).

        Returns False (block close) when:
        - Linear linkback found but issue is NOT in a terminal state
          (prevents churn from Linear native GitHub integration reopening)
        - Linear linkback found but PR is not merged
        - LINEAR_API_KEY missing (fail-closed: closing a Linear-linked issue
          without verification triggers reopen churn)
    """
    # Step 1: Try to extract linkback from body ONLY (no comment fetch yet)
    # Optimization (VAL-CLOSE-026): skip comment fetch if body already has linkback
    linear_id = _extract_linear_linkback(issue_body, "")

    # Step 2: If body doesn't have linkback, check if marker exists but extraction failed
    if not linear_id and _has_linear_linkback_marker(issue_body, ""):
        # P0-1 fail-closed: marker present but ID extraction failed
        logger.warning(
            "linear-linkback marker found but ID could not be extracted — "
            "fail-closed: blocking close to prevent unverified state"
        )
        return False

    # Step 3: If body has no linkback marker at all, fetch comments to search there
    # VAL-FAILOPEN-005/006/007: comment fetch failure → fail-closed (return False)
    # because the linkback may exist in comments and we can't verify without them.
    issue_comments = ""
    if not linear_id and issue_number is not None:
        # No linkback in body, check comments
        fetched_comments = _fetch_issue_comments(issue_number)
        if fetched_comments is None:
            # Fail-closed: can't verify linkback in comments
            logger.warning(
                f"Failed to fetch comments for issue #{issue_number} — "
                f"fail-closed: blocking close to prevent unverified state"
            )
            return False
        issue_comments = fetched_comments
        # Try to extract linkback from comments
        linear_id = _extract_linear_linkback(issue_body, issue_comments)

        # Check if marker exists in comments but extraction failed
        if not linear_id and _has_linear_linkback_marker(issue_body, issue_comments):
            logger.warning(
                "linear-linkback marker found in comments but ID could not be extracted — "
                "fail-closed: blocking close to prevent unverified state"
            )
            return False

    # Step 4: No linkback found anywhere - backward compat for environmental findings
    if not linear_id:
        logger.debug("No linear-linkback found in issue body or comments")
        return True

    # Check if LINEAR_API_KEY is available
    # Fail-CLOSED: if we can't verify Linear state, don't close — the Linear
    # native GitHub integration will reopen it, causing infinite churn.
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        logger.warning(
            f"LINEAR_API_KEY not set, fail-closed: blocking close for issue "
            f"linked to {linear_id} to prevent Linear reopen churn"
        )
        return False

    # Query Linear GraphQL API for issue attachments
    try:
        query = """
        query($id: String!) {
          issue(id: $id) {
            id
            state {
              id
              name
              type
            }
            attachments {
              nodes {
                id
                url
                sourceType
                metadata
              }
            }
          }
        }
        """
        payload = json.dumps({
            "query": query,
            "variables": {"id": linear_id}
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.linear.app/graphql",
            data=payload,
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json"
            },
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=10) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))

        # Check for GraphQL errors
        if "errors" in response_data:
            logger.warning(
                f"Linear API returned errors for {linear_id}: {response_data['errors']} "
                f"— fail-closed: blocking close to prevent unverified state"
            )
            return False

        issue_data = response_data.get("data", {}).get("issue")
        if not issue_data:
            logger.warning(
                f"Linear issue {linear_id} not found — fail-closed: blocking close "
                f"(issue may have been deleted)"
            )
            return False

        # Check Linear issue state FIRST — this is the key churn-prevention gate.
        # If the Linear issue is NOT in a terminal state, closing the GitHub
        # issue will cause the Linear native GitHub integration to reopen it.
        state_type = issue_data.get("state", {}).get("type", "")
        if state_type not in ("completed", "canceled"):
            logger.info(
                f"Linear issue {linear_id} state is '{state_type}' (not terminal), "
                f"blocking close to prevent Linear reopen churn"
            )
            return False

        # Linear issue is terminal — now verify via one of two paths:
        # Path A: merged PR attachment (existing)
        # Path B: deadlock exit sentinel in Linear comments (architecture §3.2)

        # Path A: Check if any PR is merged
        # INFRA-372: Linear removed the `attachmentType` field from the
        # Attachment type (GraphQL validation 400 → trust chain permanently
        # fail-closed). The replacement discriminator is `sourceType`
        # ("github" | "url" | ...), verified against live schema
        # (__type name: "Attachment") and production attachment data.
        attachments = issue_data.get("attachments", {}).get("nodes", [])
        github_prs = [
            att for att in attachments
            if att.get("sourceType") == "github"
        ]

        if github_prs:
            pr_result = _check_merged_pr(github_prs, linear_id)
            if pr_result is True:
                return True
            if pr_result is False:
                # gh pr view error → fail-closed immediately
                return False
            # pr_result is None → PRs exist but none merged, or no extractable PRs
            # → fall through to Path B sentinel check (architecture §3.2)

        # Path B: Deadlock exit sentinel (architecture §3.2)
        # Reconcile deadlock exit writes a sentinel comment to Linear after verifying
        # session-completed + sessionId + exitCode=0. This proves the session completed
        # successfully even without a merged PR attachment.
        #
        # Conditional fetch (VAL-CLOSE-026): only fetch comments for sentinel check
        # when PR attachments exist but can't prove merge. If no PRs, skip sentinel check.
        if github_prs:
            # PRs exist but none merged → check for deadlock sentinel in comments
            # If comments were already fetched (body had no linkback), reuse them
            # Otherwise, fetch now for sentinel check
            path_b_comments = issue_comments
            if not path_b_comments and issue_number is not None:
                fetched = _fetch_issue_comments(issue_number)
                if fetched is not None:
                    path_b_comments = fetched
                # Fetch failure here is NOT fail-closed — we already have linkback from
                # body; sentinel absence just means Path B can't confirm, so we fall
                # through to the final "return False" below.

            if path_b_comments and f"<!-- deadlock-exit {linear_id}" in path_b_comments:
                logger.info(f"Deadlock exit sentinel found for {linear_id} — trust chain passes (session-completed)")
                return True

        # Neither path succeeded — do NOT close
        if not github_prs:
            logger.info(f"No GitHub PR attachments and no deadlock exit sentinel found for {linear_id}")
        else:
            logger.info(f"No merged PR and no deadlock exit sentinel found for {linear_id} after checking all attachments")
        return False

    except urllib.error.URLError as e:
        logger.warning(
            f"Linear API unreachable for {linear_id}: {e} — fail-closed: "
            f"blocking close to prevent unverified state"
        )
        return False
    except Exception as e:
        logger.warning(
            f"Error verifying fix via Linear for {linear_id}: {e} — fail-closed: "
            f"blocking close to prevent unverified state"
        )
        return False


def _should_skip_partial_output(findings: list[Any], history_path: Path) -> bool:
    """Check if auto-close should be skipped due to partial output.

    Returns True if the current findings count is significantly below the
    recent baseline median, indicating a potential partial audit tool output.
    """
    if history_path is None:
        return False

    _po_data = load_history(history_path)
    if _po_data is None:
        return False

    _po_snapshots = _po_data.get("snapshots", [])
    if len(_po_snapshots) < 2:
        return False

    _po_counts = [len(s.get("findings", [])) for s in _po_snapshots[-5:]]
    _po_baseline = statistics.median(_po_counts)

    if _po_baseline > 0 and len(findings) < _po_baseline * 0.8:
        print(
            f"[evolution] Skip auto-close: findings count ({len(findings)}) "
            f"is below 80% of recent baseline median ({_po_baseline:.0f}). "
            f"Possible partial-output from audit tools."
        )
        return True

    return False


def auto_close_resolved(findings: list[Any], dedup_label: str, failed_categories: set[str] | None = None,
                       history_path: Path | None = None) -> None:
    """Close GitHub Issues whose findings are no longer present in current scan.

    Compares current findings against open evolution-found GitHub Issues.
    Issues whose (rule_id, location) is NOT in current findings are closed
    via `gh issue close` with an explanatory comment.

    Issues whose category belongs to a failed audit tool are NOT closed: a
    crashed/timed-out tool emits no findings, so its issues temporarily
    disappear from the current scan even though the underlying problem may
    still exist. Such issues are skipped with a warning instead (GAP-C1).

    GAP-C3: Issues must be absent for GRACE_PERIOD_TICKS consecutive ticks
    before closing. Uses history_path to count absences. When history_path
    is provided, only closes after the grace period is satisfied.

    INFRA-216: Self-audit category findings (evolution_self_audit) are NEVER
    auto-closed. These are transient health signals (e.g., heartbeat staleness)
    that resolve when the scanner recovers, not when code is fixed. Auto-closing
    them triggers a flapping loop with the state gate.

    Args:
        findings: List of Finding objects from current scan
        dedup_label: Label used to identify evolution scanner issues
        failed_categories: Set of audit categories whose tool failed this tick.
            Issues whose category is in this set are protected from auto-close.
        history_path: Path to findings_over_time.json for grace period check.
            If None, falls back to immediate close (backward compatibility).
    """
    # Build set of current finding keys
    current_keys = {(f.rule_id, f.location) for f in findings}

    # P0-A: Partial-output protection — skip tick if findings drop significantly
    if history_path is not None and _should_skip_partial_output(findings, history_path):
        return

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
    grace_deferred_count = 0
    self_audit_skip_count = 0
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

            # INFRA-216: Exclude self-audit findings from auto-close.
            # Self-audit findings (e.g., EVOLUTION_HEARTBEAT_STALE) are transient
            # health signals. Auto-closing them triggers a flapping loop with the
            # state gate (Gate A), which reverts any non-Droid closure. These
            # issues should stay open until investigated by a human or Droid.
            category = _parse_issue_category(issue.get("body", ""))
            if category == SELF_AUDIT_CATEGORY:
                self_audit_skip_count += 1
                print(f"[evolution] Skip auto-close #{issue['number']}: self-audit finding "
                      f"({rule_id} @ {location}) — transient health signal, requires manual/Droid resolution")
                continue

            # GAP-C3: Check grace period using history
            if history_path is not None:
                absence_count = _count_consecutive_absences(rule_id, location, history_path)
                if absence_count < GRACE_PERIOD_TICKS:
                    grace_deferred_count += 1
                    print(f"[evolution] Skip auto-close #{issue['number']}: absent {absence_count}/{GRACE_PERIOD_TICKS} ticks (grace period)")
                    continue

            # VAL-CLOSE-001-024: Verify fix is merged via Linear before closing
            issue_body = issue.get("body", "")
            if not _verify_fix_merged_via_linear(issue_body, issue.get("number")):
                logger.info(f"Skipping auto-close for issue #{issue['number']}: fix not verified as merged")
                print(f"[evolution] Skip auto-close #{issue['number']}: fix not verified as merged via Linear")
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
    if grace_deferred_count > 0:
        print(f"[evolution] Deferred {grace_deferred_count} issue(s) auto-close due to grace period")
    if self_audit_skip_count > 0:
        print(f"[evolution] Skipped {self_audit_skip_count} self-audit issue(s) from auto-close (transient health signals)")


# ============================================================================
# GAP-A (INFRA-174): Linear 同步失败检测 — GitHub→Linear 反向对账
# ============================================================================

# 孤立 Issue 判定阈值（分钟）：GitHub Issue 创建后超过此时间仍无 Linear 同步，
# 视为 Linear native GitHub 集成同步失败。
GAP_A_THRESHOLD_MIN = 30


def _parse_iso_timestamp(ts: str) -> datetime | None:
    """解析 ISO 8601 时间戳为带时区的 datetime（UTC）。

    兼容尾部 'Z' 与无时区两种情况。解析失败返回 None。
    """
    try:
        # fromisoformat 在 Python 3.11+ 才支持 'Z'，这里统一归一化
        normalized = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
        dt = datetime.fromisoformat(normalized)
    except (ValueError, TypeError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def detect_sync_orphans(
    gh_issues: list[dict[str, Any]],
    linear_titles: set[str],
    threshold_minutes: int = GAP_A_THRESHOLD_MIN,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """检测 GitHub Issue 在 Linear 中没有对应的孤立 Issue（GAP-A / INFRA-174）。

    当 Linear native GitHub 集成同步失败（API 限流、集成故障）时，evolution
    scanner 创建的 GitHub Issue 在 Linear 中没有对应记录，导致 Linear webhook
    永不触发、droid 永不处理。本函数通过反向对账（GitHub→Linear）识别这类孤立
    Issue，供 reconcile-evolution.sh 补偿创建 Linear Issue。

    Args:
        gh_issues: GitHub Issue 列表，每个元素是 dict 包含:
            - number: int (GitHub issue number)
            - title: str (issue title)
            - created_at: str (ISO 8601 timestamp)
            - has_linear_linkback: bool (是否有 <!-- linear-linkback --> 评论)
        linear_titles: Linear 中 evolution-found issue 的标题集合
        threshold_minutes: 超过此时间（分钟）仍无 Linear 同步视为孤立
        now: 当前时间（测试注入），默认 datetime.now(timezone.utc)

    Returns:
        孤立 GitHub Issue 列表（list of dict，同输入格式）

    判定条件（全部满足才视为孤立）：
        1. has_linear_linkback == False（无 Linear 同步标记）
        2. 标题不在 linear_titles 中（Linear 中没有同标题 issue）
        3. age > threshold_minutes（给 Linear 足够的同步时间）
    """
    if now is None:
        now = datetime.now(timezone.utc)
    # 防御：注入的 now 若为 naive，按 UTC 处理，避免与 tz-aware created_at 相减报错
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    orphans: list[dict[str, Any]] = []
    for issue in gh_issues:
        # 条件 1：已存在 Linear linkback → 已同步，跳过
        if issue.get("has_linear_linkback", False):
            continue

        # 条件 2：标题在 Linear 中已存在 → linkback 虽缺失但 Linear issue 已创建，跳过
        title = issue.get("title", "")
        if title in linear_titles:
            continue

        # 条件 3：age > threshold（给 Linear 足够的同步窗口）
        created_at = _parse_iso_timestamp(issue.get("created_at", ""))
        if created_at is None:
            # 无法解析时间戳，保守跳过（不误判）
            continue
        age_minutes = (now - created_at).total_seconds() / 60
        if age_minutes <= threshold_minutes:
            continue

        orphans.append(issue)

    return orphans


# GAP-E: Reconciliation sentinel for idempotency
# Embedded as hidden HTML comment so it's invisible in GitHub UI
RECON_ADVISORY_SENTINEL = "<!-- evolution-recon-advisory -->"


def reconcile_in_progress(dedup_label: str) -> int:
    """Check for stuck evolution-found issues (open > 72h, no PR).

    GAP-E: Detects issues that have been open for more than 72 hours with no
    associated PR. Adds an advisory comment (Chinese) to stuck issues.
    ADVISORY ONLY - never force-closes or changes labels.

    Idempotency guard: embeds a hidden HTML sentinel in the comment. Before
    commenting, scans the issue's existing comments for the sentinel. If found,
    skips commenting to prevent duplicate advisories on every tick.

    Args:
        dedup_label: Label used to identify evolution scanner issues

    Returns:
        Number of stuck issues that were flagged with advisory comments
    """
    RECON_STUCK_THRESHOLD_HOURS = 72

    # Fetch all open evolution-found issues with createdAt
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--search", f"label:{dedup_label}",
             "--state", "open", "--limit", "200", "--json", "number,body,createdAt"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            print(f"[evolution] Warning: Failed to list open issues for reconciliation: {result.stderr}")
            return 0

        issues = json.loads(result.stdout) if result.stdout.strip() else []
    except Exception as e:
        print(f"[evolution] Warning: Failed to fetch open issues for reconciliation: {e}")
        return 0

    now = datetime.now(timezone.utc)
    stuck_count = 0

    for issue in issues:
        issue_number = issue.get("number")
        created_at_str = issue.get("createdAt", "")

        # Parse creation time
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            age_hours = (now - created_at).total_seconds() / 3600
        except (ValueError, TypeError):
            # Skip issues with invalid createdAt
            continue

        # Skip recent issues (< 72h threshold)
        if age_hours < RECON_STUCK_THRESHOLD_HOURS:
            continue

        # Check for associated PR (search for "Fixes #N" in PR bodies)
        try:
            pr_result = subprocess.run(
                ["gh", "pr", "list", "--search", f"Fixes #{issue_number}",
                 "--state", "all", "--limit", "1", "--json", "number"],
                capture_output=True, text=True, timeout=30
            )
            if pr_result.returncode != 0:
                print(f"[evolution] Warning: Failed to check PR for issue #{issue_number}: {pr_result.stderr}")
                continue

            prs = json.loads(pr_result.stdout) if pr_result.stdout.strip() else []

            # If PR exists, issue is not stuck
            if prs:
                continue

        except Exception as e:
            print(f"[evolution] Warning: Failed to check PR association for issue #{issue_number}: {e}")
            continue

        # Idempotency guard: check if advisory comment already exists
        try:
            comments_result = subprocess.run(
                ["gh", "issue", "view", str(issue_number),
                 "--json", "comments", "--jq", ".comments[].body"],
                capture_output=True, text=True, timeout=30
            )
            if comments_result.returncode == 0 and RECON_ADVISORY_SENTINEL in comments_result.stdout:
                print(f"[evolution] Skip advisory for #{issue_number}: sentinel already present (idempotency guard)")
                continue
        except Exception as e:
            print(f"[evolution] Warning: Failed to check comments for #{issue_number}: {e}")
            # On failure, proceed to comment (fail-open to avoid silent skip)

        # Issue is stuck (old + no PR) - add advisory comment with sentinel
        comment_msg = (
            f"{RECON_ADVISORY_SENTINEL}\n"
            f"⚠️ 此 Issue 已卡住 {int(age_hours)} 小时（超过 {RECON_STUCK_THRESHOLD_HOURS}h 阈值），"
            f"未检测到关联的 PR。可能需要人工检查进度或重新评估优先级。\n\n"
            f"此评论仅为提醒，不会自动关闭或修改 Issue 状态。"
        )

        try:
            comment_result = subprocess.run(
                ["gh", "issue", "comment", str(issue_number), "--body", comment_msg],
                capture_output=True, text=True, timeout=30
            )
            if comment_result.returncode == 0:
                stuck_count += 1
                print(f"[evolution] Advisory: Issue #{issue_number} stuck for {int(age_hours)}h with no PR")
            else:
                print(f"[evolution] Warning: Failed to comment on issue #{issue_number}: {comment_result.stderr}")
        except Exception as e:
            print(f"[evolution] Warning: Failed to comment on issue #{issue_number}: {e}")

    if stuck_count > 0:
        print(f"[evolution] Reconciliation: {stuck_count} stuck issue(s) flagged with advisory comments")

    return stuck_count


# ============================================================================
# VAL-DRF-002/003: Reverse Drift Watch - Orphan Issue Classification
# ============================================================================

from dataclasses import dataclass


@dataclass
class OrphanIssueClassification:
    """Structured classification of an orphan issue (open issue not in findings).
    
    VAL-DRF-002: Each orphan issue must be classified into one of:
    - CLOSE_READY: Has merge/session evidence, can be closed after grace period
    - BLOCKED_NO_EVIDENCE: No evidence, retained with blocking reason recorded
    
    VAL-DRF-003: Every classification must have audit trail (reason + timestamp).
    """
    issue_number: int
    rule_id: str
    location: str
    classification: str  # "CLOSE_READY" or "BLOCKED_NO_EVIDENCE"
    reason: str  # Audit trail: why this classification
    timestamp: str  # ISO 8601 timestamp
    action_taken: str = ""  # What action was taken (close attempt or retain)


def classify_orphan_issues(
    current_findings: list[Any],
    open_issues: list[dict[str, Any]],
) -> list[OrphanIssueClassification]:
    """Classify orphan issues (open issues not in current findings).
    
    VAL-DRF-002: For each open evolution-found issue whose key is NOT in current
    findings, classify into:
    - CLOSE_READY: Has merge/session evidence → grace then close
    - BLOCKED_NO_EVIDENCE: No evidence → retain with blocking reason recorded
    
    VAL-DRF-003: Every classification must leave audit trail (reason + timestamp + action).
    Must take action (close or record), not just alert.
    
    VAL-DRF-004: Incremental implementation - accepts open_issues as parameter,
    does not fetch them (no new full scan).
    
    Args:
        current_findings: List of Finding objects from current scan
        open_issues: List of open GitHub issues (from current tick, not newly fetched)
    
    Returns:
        List of OrphanIssueClassification with audit trail for each orphan issue
    """
    # Build set of current finding keys for O(1) lookup
    current_keys = {(f.rule_id, f.location) for f in current_findings}
    
    classifications = []
    now_iso = datetime.now(timezone.utc).isoformat()
    
    for issue in open_issues:
        # Parse issue fields
        rule_id, location = _parse_issue_fields(issue.get("body", ""))
        if rule_id is None or location is None:
            # Malformed issue body - skip
            continue
        
        issue_key = (rule_id, location)
        issue_number = issue.get("number")
        if issue_number is None:
            # Invalid issue data
            continue
        assert isinstance(issue_number, int)  # Type assertion for mypy
        
        # Check if this is an orphan (not in current findings)
        if issue_key in current_keys:
            # Not an orphan - in current findings
            continue
        
        # This is an orphan issue - classify it
        issue_body = issue.get("body", "")
        
        # Try to verify fix via Linear (checks for merge/session evidence)
        verified = _verify_fix_merged_via_linear(issue_body, issue_number)
        
        if verified:
            # Has merge or session evidence
            # Determine specific reason
            has_linear_linkback = _has_linear_linkback_marker(issue_body)
            has_session_evidence = DEADLOCK_EXIT_SENTINEL_PREFIX in issue_body
            
            if has_session_evidence:
                reason = "session_completed_verified"
            elif has_linear_linkback:
                reason = "merged_pr_verified"
            else:
                reason = "fix_verified_no_linkback"
            
            classifications.append(OrphanIssueClassification(
                issue_number=issue_number,
                rule_id=rule_id,
                location=location,
                classification="CLOSE_READY",
                reason=reason,
                timestamp=now_iso,
                action_taken="close_attempt"
            ))
            
            logger.info(f"Orphan #{issue_number} classified as CLOSE_READY: {reason}")
            
        else:
            # No evidence - retain with blocking reason
            has_linear_linkback = _has_linear_linkback_marker(issue_body)
            has_marker_but_no_id = (
                has_linear_linkback and 
                not _extract_linear_linkback(issue_body)
            )
            
            if has_marker_but_no_id:
                reason = "linkback_marker_present_but_id_extraction_failed"
            elif has_linear_linkback:
                reason = "linkback_found_but_fix_not_verified"
            else:
                reason = "no_evidence_of_resolution"
            
            classifications.append(OrphanIssueClassification(
                issue_number=issue_number,
                rule_id=rule_id,
                location=location,
                classification="BLOCKED_NO_EVIDENCE",
                reason=reason,
                timestamp=now_iso,
                action_taken="retained_with_reason"
            ))
            
            logger.info(f"Orphan #{issue_number} classified as BLOCKED_NO_EVIDENCE: {reason}")
    
    return classifications


def execute_orphan_classifications(
    classifications: list[OrphanIssueClassification],
    history_path: Path | None = None,
) -> dict[str, int]:
    """Execute actions based on orphan issue classifications.
    
    VAL-DRF-003: Must take action (not just alert). This function:
    - CLOSE_READY: Attempts to close issue after grace period check
    - BLOCKED_NO_EVIDENCE: Records blocking reason in issue comment
    
    Args:
        classifications: List of OrphanIssueClassification from classify_orphan_issues
        history_path: Path to findings_over_time.json for grace period check
    
    Returns:
        Dict with counts: {closed: int, retained: int, deferred: int}
    """
    closed_count = 0
    retained_count = 0
    deferred_count = 0
    
    for classification in classifications:
        issue_number = classification.issue_number
        
        if classification.classification == "CLOSE_READY":
            # Check grace period before closing
            if history_path is not None:
                absence_count = _count_consecutive_absences(
                    classification.rule_id,
                    classification.location,
                    history_path
                )
                if absence_count < GRACE_PERIOD_TICKS:
                    deferred_count += 1
                    logger.info(
                        f"Orphan #{issue_number} deferred: absent {absence_count}/{GRACE_PERIOD_TICKS} ticks"
                    )
                    continue
            
            # Close the issue with classification reason in comment
            close_msg = (
                f"该 finding 在最近一次扫描中已不再出现，自动关闭此 Issue。\n"
                f"分类依据：{classification.reason}\n"
                f"（Rule: {classification.rule_id}, Location: {classification.location}）"
            )
            
            try:
                close_result = subprocess.run(
                    ["gh", "issue", "close", str(issue_number), "--comment", close_msg],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if close_result.returncode == 0:
                    closed_count += 1
                    logger.info(f"Closed orphan #{issue_number}: {classification.reason}")
                else:
                    logger.warning(f"Failed to close orphan #{issue_number}: {close_result.stderr}")
            except Exception as e:
                logger.error(f"Failed to close orphan #{issue_number}: {e}")
                
        elif classification.classification == "BLOCKED_NO_EVIDENCE":
            # Record blocking reason in issue comment (audit trail)
            comment_msg = (
                f"🔒 反向漂移守望：此 Issue 当前分类为 BLOCKED_NO_EVIDENCE\n"
                f"原因：{classification.reason}\n"
                f"时间：{classification.timestamp}\n"
                f"动作：保留 Issue，等待进一步证据"
            )
            
            try:
                comment_result = subprocess.run(
                    ["gh", "issue", "comment", str(issue_number), "--body", comment_msg],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if comment_result.returncode == 0:
                    retained_count += 1
                    logger.info(f"Recorded blocking reason for orphan #{issue_number}: {classification.reason}")
                else:
                    logger.warning(f"Failed to comment on orphan #{issue_number}: {comment_result.stderr}")
            except Exception as e:
                logger.error(f"Failed to comment on orphan #{issue_number}: {e}")
    
    return {
        "closed": closed_count,
        "retained": retained_count,
        "deferred": deferred_count
    }


def reverse_drift_watch(
    findings: list[Any],
    open_issues: list[dict[str, Any]],
    history_path: Path | None = None,
) -> dict[str, int]:
    """VAL-DRF-002/003: Reverse drift watch with automatic remediation.
    
    For each open evolution-found issue whose key is NOT in current findings:
    - Classify based on evidence (merge/session evidence → CLOSE_READY, no evidence → BLOCKED)
    - Execute action (close after grace period, or retain with blocking reason recorded)
    
    This function must take action (not just alert), fulfilling VAL-DRF-003.
    Every action leaves audit trail (reason + timestamp + action), fulfilling VAL-DRF-002.
    
    Args:
        findings: Current tick's findings (for comparison)
        open_issues: List of open GitHub issues (already fetched, incremental)
        history_path: Path to findings_over_time.json for grace period check
    
    Returns:
        Dict with counts: {closed: int, retained: int, deferred: int}
    """
    # Step 1: Classify all orphan issues
    classifications = classify_orphan_issues(findings, open_issues)
    
    # Step 2: Execute actions based on classifications
    result = execute_orphan_classifications(classifications, history_path)
    
    # Log summary
    if result["closed"] > 0 or result["retained"] > 0 or result["deferred"] > 0:
        logger.info(
            f"Reverse drift watch complete: {result['closed']} closed, "
            f"{result['retained']} retained, {result['deferred']} deferred"
        )
    
    return result
