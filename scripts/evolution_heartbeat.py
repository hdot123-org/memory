#!/usr/bin/env python3
"""Evolution heartbeat: observe downstream pipeline health.

Independent workflow that runs every 2 hours to detect anomalies in the
evolution scanner pipeline:
  1. Check findings_over_time.json freshness (last snapshot too old)
  2. Check recent evolution-found issues for PR association
  3. Create alert issues when anomalies are detected
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Heartbeat configuration
HISTORY_PATH = Path(".evolution/findings_over_time.json")
FRESHNESS_THRESHOLD_HOURS = 2  # Alert if no snapshot within 2 hours
PR_CHECK_WINDOW_ISSUES = 10  # Check last N evolution-found issues
ALERT_LABEL = "evolution-heartbeat"
EVOLUTION_FOUND_LABEL = "evolution-found"
HEARTBEAT_MARKER_PATH = Path(".evolution/heartbeat.json")
MONITOR_HEARTBEAT_PATH = Path(".evolution/monitor_heartbeat.json")


def check_history_freshness(
    history_path: Path = HISTORY_PATH,
    max_age_hours: int = FRESHNESS_THRESHOLD_HOURS,
) -> dict:
    """Check if findings_over_time.json has a recent snapshot.

    Returns a dict with:
      - stale (bool): True if the latest snapshot is older than max_age_hours
      - age_hours (float): age in hours of the latest snapshot (inf if unknown)
      - message (str): human-readable status
    """
    result: dict = {"stale": True, "age_hours": float("inf"), "message": ""}

    if not history_path.exists():
        result["message"] = f"History file {history_path} does not exist"
        return result

    try:
        data = json.loads(history_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        result["message"] = f"Cannot read history file: {exc}"
        return result

    snapshots = data.get("snapshots", [])
    if not snapshots:
        result["message"] = "History file has no snapshots"
        return result

    last_snapshot = snapshots[-1]
    ts_str = last_snapshot.get("timestamp", "")
    try:
        ts = datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        result["message"] = f"Cannot parse last snapshot timestamp: {ts_str!r}"
        return result

    # Ensure timezone-aware comparison
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    age_hours = (now - ts).total_seconds() / 3600
    result["age_hours"] = age_hours

    if age_hours > max_age_hours:
        result["stale"] = True
        result["message"] = (
            f"findings_over_time.json is stale: last snapshot "
            f"{age_hours:.1f}h ago (threshold: {max_age_hours}h)"
        )
    else:
        result["stale"] = False
        result["message"] = f"History freshness: OK ({age_hours:.1f}h old)"

    return result


def check_pr_coverage(label: str = EVOLUTION_FOUND_LABEL) -> dict:
    """Check whether recent evolution-found issues have associated PRs.

    Returns a dict with:
      - issues_without_pr (int): open issues lacking an associated PR
      - total_issues (int): total open issues inspected
      - missing (list[int]): issue numbers without a PR
    """
    result: dict = {"issues_without_pr": 0, "total_issues": 0, "missing": []}

    list_result = subprocess.run(
        [
            "gh", "issue", "list",
            "--label", label,
            "--state", "open",
            "--limit", str(PR_CHECK_WINDOW_ISSUES),
            "--json", "number,title,createdAt",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if list_result.returncode != 0:
        print(f"[heartbeat] Failed to query issues: {list_result.stderr.strip()}")
        return result

    try:
        issues = json.loads(list_result.stdout) if list_result.stdout.strip() else []
    except json.JSONDecodeError:
        print("[heartbeat] Cannot parse issue list JSON")
        return result

    result["total_issues"] = len(issues)

    for issue in issues:
        number = issue["number"]
        # Check for associated PR via 'Fixes #N' references
        pr_result = subprocess.run(
            [
                "gh", "pr", "list",
                "--search", f'"{number}"',
                "--state", "all",
                "--limit", "1",
                "--json", "number",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        try:
            prs = json.loads(pr_result.stdout) if pr_result.stdout.strip() else []
        except json.JSONDecodeError:
            prs = []

        if not prs:
            result["issues_without_pr"] += 1
            result["missing"].append(number)

    return result


def alert_issue_exists(label: str = ALERT_LABEL) -> bool:
    """Check if an open heartbeat alert issue already exists (INFRA-204 dedup)."""
    try:
        result = subprocess.run(
            ["gh", "issue", "list", "--label", label, "--state", "open",
             "--limit", "10", "--json", "number"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return False
        issues = json.loads(result.stdout) if result.stdout.strip() else []
        return len(issues) > 0
    except Exception:
        return False


def check_heartbeat_marker(max_age_hours: int = FRESHNESS_THRESHOLD_HOURS) -> dict:
    """Check dedicated heartbeat.json marker freshness (INFRA-204).

    This is a more precise signal than findings_over_time.json: the
    heartbeat is written at the END of a successful tick, so staleness
    means the scanner either didn't run or failed mid-tick.
    """
    result: dict = {"stale": True, "age_hours": float("inf"), "message": ""}

    if not HEARTBEAT_MARKER_PATH.exists():
        result["message"] = f"Heartbeat marker {HEARTBEAT_MARKER_PATH} does not exist"
        return result

    try:
        data = json.loads(HEARTBEAT_MARKER_PATH.read_text())
        ts_str = data.get("timestamp", "")
        if not ts_str:
            result["message"] = "Heartbeat marker has no timestamp"
            return result

        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        age_hours = (now - ts).total_seconds() / 3600
        result["age_hours"] = age_hours

        if age_hours > max_age_hours:
            result["stale"] = True
            result["message"] = (
                f"heartbeat.json is stale: last heartbeat "
                f"{age_hours:.1f}h ago (threshold: {max_age_hours}h)"
            )
        else:
            result["stale"] = False
            result["message"] = f"Heartbeat marker: OK ({age_hours:.1f}h old)"
    except (json.JSONDecodeError, ValueError, TypeError, OSError) as exc:
        result["message"] = f"Cannot read heartbeat marker: {exc}"

    return result


def write_monitor_heartbeat(anomalies: int) -> None:
    """Write monitor heartbeat marker for meta-monitoring (INFRA-204).

    Allows the scanner's self-audit to detect if the heartbeat monitor
    workflow itself has stopped running.
    """
    now = datetime.now(timezone.utc)
    data = {
        "timestamp": now.isoformat(),
        "status": "ok" if anomalies == 0 else "anomaly",
        "anomalies_detected": anomalies,
    }
    tmp = MONITOR_HEARTBEAT_PATH.with_suffix(".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, MONITOR_HEARTBEAT_PATH)


def create_alert_issue(
    stale_history: bool,
    issues_without_pr: int,
    dedup_label: str = EVOLUTION_FOUND_LABEL,
    heartbeat_stale: bool = False,
) -> bool:
    """Create a GitHub Issue for detected pipeline anomalies.

    Returns True if an issue was created, False if no anomaly or creation failed.
    """
    if not stale_history and issues_without_pr == 0 and not heartbeat_stale:
        return False

    anomalies = []
    if heartbeat_stale:
        anomalies.append("heartbeat.json marker is stale (scanner may have stopped)")
    if stale_history:
        anomalies.append("findings_over_time.json is stale (no recent snapshot)")
    if issues_without_pr > 0:
        anomalies.append(
            f"{issues_without_pr} evolution-found issue(s) without associated PR"
        )

    body_lines = [
        "## Evolution Heartbeat Alert",
        "",
        f"**Detected**: {datetime.now(timezone.utc).isoformat()}",
        f"**Scope**: {dedup_label}",
        "",
        "### Anomalies",
        "",
    ]
    for anomaly in anomalies:
        body_lines.append(f"- {anomaly}")

    title = "[heartbeat] Pipeline anomaly detected"

    create_result = subprocess.run(
        [
            "gh", "issue", "create",
            "--title", title,
            "--body", "\n".join(body_lines),
            "--label", ALERT_LABEL,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if create_result.returncode != 0:
        print(f"[heartbeat] Failed to create alert issue: {create_result.stderr.strip()}")
        return False

    print(f"[heartbeat] Created alert issue: {create_result.stdout.strip()}")
    return True


def main(history_path: Path = HISTORY_PATH) -> int:
    """Run heartbeat checks and alert on anomalies. Returns process exit code."""
    # INFRA-204: Check dedicated heartbeat marker (most precise signal)
    heartbeat = check_heartbeat_marker()
    if heartbeat["stale"]:
        print(f"[heartbeat] ALERT: {heartbeat['message']}")
    else:
        print(f"[heartbeat] {heartbeat['message']}")

    # Check 1: History freshness
    freshness = check_history_freshness(history_path)
    if freshness["stale"]:
        print(f"[heartbeat] ALERT: {freshness['message']}")
    else:
        print(f"[heartbeat] {freshness['message']}")

    # Check 2: PR coverage
    coverage = check_pr_coverage()
    if coverage["issues_without_pr"] > 0:
        print(
            f"[heartbeat] ALERT: {coverage['issues_without_pr']} issue(s) "
            f"without PR: {coverage['missing']}"
        )
    else:
        print("[heartbeat] PR coverage: OK")

    # INFRA-204: Write monitor heartbeat for meta-monitoring
    anomaly_count = sum([heartbeat["stale"], freshness["stale"], bool(coverage["issues_without_pr"] > 0)])

    # Create alert issue if any anomaly detected
    if heartbeat["stale"] or freshness["stale"] or coverage["issues_without_pr"] > 0:
        if alert_issue_exists():
            print("[heartbeat] Open alert issue already exists, skipping duplicate creation")
        else:
            create_alert_issue(
                stale_history=freshness["stale"],
                issues_without_pr=coverage["issues_without_pr"],
                heartbeat_stale=heartbeat["stale"],
            )
        write_monitor_heartbeat(anomaly_count)
        return 1  # Non-zero exit signals anomaly to CI

    write_monitor_heartbeat(anomaly_count)
    print("[heartbeat] All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
