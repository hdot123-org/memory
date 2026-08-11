#!/usr/bin/env python3
"""Evolution heartbeat: observe downstream pipeline health.

Independent workflow that runs every 2 hours to detect anomalies in the
evolution scanner pipeline:
  1. Check findings_over_time.json freshness (last snapshot < threshold)
  2. Check recent evolution-found issues for PR association
  3. Create alert issues when anomalies are detected
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Heartbeat configuration
HISTORY_PATH = Path(".evolution/findings_over_time.json")
FRESHNESS_THRESHOLD_HOURS = 6  # Alert if no snapshot in 6 hours
PR_CHECK_WINDOW_ISSUES = 10  # Check last N evolution-found issues
ALERT_LABEL = "evolution-heartbeat"


def check_history_freshness(history_path: Path = HISTORY_PATH,
                            threshold_hours: int = FRESHNESS_THRESHOLD_HOURS) -> str | None:
    """Check if findings_over_time.json has a recent snapshot.

    Returns an alert message if stale, None if fresh.
    """
    if not history_path.exists():
        return f"History file {history_path} does not exist"

    try:
        data = json.loads(history_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return f"Cannot read history file: {exc}"

    snapshots = data.get("snapshots", [])
    if not snapshots:
        return "History file has no snapshots"

    # Get the most recent snapshot timestamp
    last_snapshot = snapshots[-1]
    ts_str = last_snapshot.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return f"Cannot parse last snapshot timestamp: {ts_str!r}"

    # Ensure timezone-aware comparison
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age_hours = (now - ts).total_seconds() / 3600

    if age_hours > threshold_hours:
        return (f"findings_over_time.json is stale: last snapshot "
                f"{age_hours:.1f}h ago (threshold: {threshold_hours}h)")

    return None


def check_pr_coverage(window: int = PR_CHECK_WINDOW_ISSUES) -> list[str]:
    """Check whether recent evolution-found issues have associated PRs.

    Returns a list of alert messages for issues without PRs.
    """
    alerts = []

    # Query recent evolution-found issues
    result = subprocess.run(
        ["gh", "issue", "list",
         "--label", "evolution-found",
         "--state", "open",
         "--limit", str(window),
         "--json", "number,title,createdAt"],
        capture_output=True, text=True, timeout=30,
    )

    if result.returncode != 0:
        alerts.append(f"Failed to query issues: {result.stderr.strip()}")
        return alerts

    try:
        issues = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        alerts.append("Cannot parse issue list JSON")
        return alerts

    if not issues:
        return alerts

    for issue in issues:
        number = issue["number"]
        # Check for associated PR via 'Fixes #N' references
        pr_result = subprocess.run(
            ["gh", "pr", "list",
             "--search", f'"{number}"',
             "--state", "all",
             "--limit", "1",
             "--json", "number"],
            capture_output=True, text=True, timeout=30,
        )

        if pr_result.returncode != 0:
            alerts.append(f"Failed to check PR for issue #{number}: {pr_result.stderr.strip()}")
            continue

        try:
            prs = json.loads(pr_result.stdout) if pr_result.stdout.strip() else []
        except json.JSONDecodeError:
            prs = []

        if not prs:
            title = issue.get("title", "")
            alerts.append(f"Issue #{number} ({title[:60]}) has no associated PR")

    return alerts


def create_alert_issue(alerts: list[str], alert_type: str) -> bool:
    """Create a GitHub Issue for detected pipeline anomalies.

    Uses idempotent check to avoid duplicate alert issues.
    Returns True if issue was created, False otherwise.
    """
    if not alerts:
        return False

    # Check for existing open alert issue to avoid duplicates
    existing = subprocess.run(
        ["gh", "issue", "list",
         "--label", ALERT_LABEL,
         "--state", "open",
         "--limit", "1",
         "--json", "number"],
        capture_output=True, text=True, timeout=30,
    )

    if existing.returncode == 0:
        try:
            open_alerts = json.loads(existing.stdout) if existing.stdout.strip() else []
        except json.JSONDecodeError:
            open_alerts = []
        if open_alerts:
            print(f"[heartbeat] Alert issue already open: #{open_alerts[0]['number']}")
            return False

    # Ensure alert label exists
    subprocess.run(
        ["gh", "label", "create", ALERT_LABEL,
         "--color", "D93F0B",
         "--description", "Heartbeat pipeline alert"],
        capture_output=True, text=True, timeout=30,
    )

    body_lines = [
        "## Evolution Heartbeat Alert",
        "",
        f"**Type**: {alert_type}",
        f"**Detected**: {datetime.now(timezone.utc).isoformat()}",
        "",
        "### Alerts",
        "",
    ]
    for alert in alerts:
        body_lines.append(f"- {alert}")

    title = f"[heartbeat] {alert_type}: {alerts[0][:80]}"

    result = subprocess.run(
        ["gh", "issue", "create",
         "--title", title,
         "--body", "\n".join(body_lines),
         "--label", ALERT_LABEL],
        capture_output=True, text=True, timeout=30,
    )

    if result.returncode != 0:
        print(f"[heartbeat] Failed to create alert issue: {result.stderr.strip()}")
        return False

    print(f"[heartbeat] Created alert issue: {result.stdout.strip()}")
    return True


def main() -> int:
    """Run heartbeat checks and alert on anomalies."""
    all_alerts = []

    # Check 1: History freshness
    freshness_alert = check_history_freshness()
    if freshness_alert:
        all_alerts.append(freshness_alert)
        print(f"[heartbeat] ALERT: {freshness_alert}")
    else:
        print("[heartbeat] History freshness: OK")

    # Check 2: PR coverage
    pr_alerts = check_pr_coverage()
    if pr_alerts:
        all_alerts.extend(pr_alerts)
        for alert in pr_alerts:
            print(f"[heartbeat] ALERT: {alert}")
    else:
        print("[heartbeat] PR coverage: OK")

    # Create alert issue if anomalies detected
    if all_alerts:
        alert_type = "stale-pipeline" if freshness_alert else "missing-prs"
        create_alert_issue(all_alerts, alert_type)
        return 1  # Non-zero exit to signal CI

    print("[heartbeat] All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
