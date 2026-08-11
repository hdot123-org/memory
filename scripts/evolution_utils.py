"""Utility functions for evolution scanner."""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from evolution_adapters import quarantine_corrupted_file, sanitize_structured_field

_SEV_RANK = {"critical": 3, "warning": 2, "info": 1}

# GAP-C3: Grace period for auto-close
# A finding must be absent for this many consecutive ticks before its issue is closed.
# Prevents false closures from transient adapter failures.
GRACE_PERIOD_TICKS = 2

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

            # GAP-C3: Check grace period using history
            if history_path is not None:
                absence_count = _count_consecutive_absences(rule_id, location, history_path)
                if absence_count < GRACE_PERIOD_TICKS:
                    grace_deferred_count += 1
                    print(f"[evolution] Skip auto-close #{issue['number']}: absent {absence_count}/{GRACE_PERIOD_TICKS} ticks (grace period)")
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
