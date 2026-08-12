"""Utility functions for evolution scanner."""
import json
import logging
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

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

# Required config keys for evolution scanner
REQUIRED_CONFIG_KEYS = [
    "audit_tools",
    "severity_order",
    "dedup_label",
    "isolation_threshold",
    "failure_label",
    "max_issues_per_tick",
    "max_self_audit_issues_per_tick",
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


def _extract_linear_linkback(issue_body: str, issue_comments: str = "") -> str | None:
    """Extract INFRA-xxx ID from linear-linkback in issue body or comments.

    Linear native GitHub integration writes the linkback as an HTML comment,
    but it appears in issue COMMENTS, not the body. This function searches
    both sources.

    Returns:
        The INFRA-xxx identifier, or None if not found.
    """
    pattern = r'<!--\s*linear-linkback\s+(INFRA-\d+)\s*-->'
    body_match = re.search(pattern, issue_body)
    if body_match:
        return body_match.group(1)
    comment_match = re.search(pattern, issue_comments)
    if comment_match:
        return comment_match.group(1)
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
    # Fetch issue comments to search for linkback, but ONLY if the body
    # doesn't already contain a linkback. Linear integration sometimes writes
    # the linkback in comments instead of the body.
    body_match = re.search(r'<!--\s*linear-linkback\s+(INFRA-\d+)\s*-->', issue_body)
    issue_comments = ""
    if body_match is None and issue_number is not None:
        try:
            comment_result = subprocess.run(
                ["gh", "issue", "view", str(issue_number),
                 "--json", "comments", "--jq", ".comments[].body"],
                capture_output=True, text=True, timeout=30
            )
            if comment_result.returncode == 0:
                issue_comments = comment_result.stdout
            else:
                # Fail-closed: cannot confirm linkback in comments
                logger.warning(
                    f"Failed to fetch comments for issue #{issue_number} "
                    f"(exit code {comment_result.returncode}): {comment_result.stderr} "
                    f"— fail-closed: blocking close to prevent unverified state"
                )
                return False
        except Exception as e:
            # Fail-closed: cannot confirm linkback in comments
            logger.warning(
                f"Exception fetching comments for issue #{issue_number}: {e} "
                f"— fail-closed: blocking close to prevent unverified state"
            )
            return False

    linear_id = _extract_linear_linkback(issue_body, issue_comments)
    if not linear_id:
        # No linkback found — environmental finding, allow close (backward compat)
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
                attachmentType
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

        # Linear issue is terminal — now verify a PR was actually merged
        attachments = issue_data.get("attachments", {}).get("nodes", [])
        github_prs = [
            att for att in attachments
            if att.get("attachmentType") == "github"
        ]

        if not github_prs:
            # No PR attachments found - issue should NOT be closed
            logger.info(f"No GitHub PR attachments found for {linear_id}")
            return False

        # Check if any PR is merged
        for pr_attachment in github_prs:
            # Extract PR number and repo from URL, check via gh CLI
            pr_url = pr_attachment.get("url", "")
            pr_match = re.search(r'/pull/(\d+)', pr_url)
            if pr_match:
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
                        # gh pr view failed - fail-open
                        logger.warning(f"gh pr view failed for PR #{pr_number}: {result.stderr}")
                        return True  # Fail-open
                except Exception as e:
                    # gh pr view exception - fail-open
                    logger.warning(f"Exception checking PR #{pr_number} via gh CLI: {e}")
                    return True  # Fail-open

        # All PRs checked successfully but none merged -> do NOT close
        logger.info(f"No merged PR found for {linear_id} after checking all attachments")
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


def auto_close_resolved(findings: list, dedup_label: str, failed_categories: set[str] | None = None,
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
    gh_issues: list[dict],
    linear_titles: set[str],
    threshold_minutes: int = GAP_A_THRESHOLD_MIN,
    now: datetime | None = None,
) -> list[dict]:
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

    orphans: list[dict] = []
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
