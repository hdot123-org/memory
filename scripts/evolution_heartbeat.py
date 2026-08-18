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
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Heartbeat configuration
HISTORY_PATH = Path(".evolution/findings_over_time.json")
FRESHNESS_THRESHOLD_HOURS = 2  # Alert if no snapshot within 2 hours
PR_CHECK_WINDOW_ISSUES = 10  # Check last N evolution-found issues
ALERT_LABEL = "evolution-heartbeat"
EVOLUTION_FOUND_LABEL = "evolution-found"
HEARTBEAT_MARKER_PATH = Path(".evolution/heartbeat.json")
MONITOR_HEARTBEAT_PATH = Path(".evolution/monitor_heartbeat.json")
SCANNER_WORKFLOW = "evolution-scan.yml"
SCANNER_LIVENESS_THRESHOLD_HOURS = 2  # Alert if scanner hasn't run in 2 hours

# --- Shared anomaly markers (producer ↔ consumer coupling) ---
# These strings are written by create_alert_issue/_build_alert_body and parsed by
# extract_recorded_anomalies.  Both sides MUST use the same constants to prevent
# wording drift that would cause silent never-heal.
_ANOMALY_SCANNER_STALE_MARKER = "evolution-scan workflow has not run recently"
_ANOMALY_ISSUES_WITHOUT_PR_MARKER = "evolution-found issue(s) without associated PR"
_SELF_HEAL_MARKER = "自愈"  # Marker in self-heal comments to detect duplicates


def _unique_tmp_path(final_path: Path) -> Path:
    """Return a collision-free tmp path for atomic writes to final_path.

    Fixed tmp names race across concurrent writers (see evolution_scanner):
    mkstemp+unlink still races at thread level because the unlinked name can
    be re-issued to another thread before the first writer recreates it.
    pid + uuid4 names are unique per call with no existence-dependent window.
    """
    return final_path.parent / f"{final_path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"


def check_history_freshness(
    history_path: Path = HISTORY_PATH,
    max_age_hours: int = FRESHNESS_THRESHOLD_HOURS,
) -> dict[str, Any]:
    """Check if findings_over_time.json has a recent snapshot.

    Returns a dict with:
      - stale (bool): True if the latest snapshot is older than max_age_hours
      - age_hours (float): age in hours of the latest snapshot (inf if unknown)
      - message (str): human-readable status
    """
    result: dict[str, Any] = {"stale": True, "age_hours": float("inf"), "message": ""}

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


def check_pr_coverage(label: str = EVOLUTION_FOUND_LABEL) -> dict[str, Any]:
    """Check whether recent evolution-found issues have associated PRs.

    Returns a dict with:
      - issues_without_pr (int): open issues lacking an associated PR
      - total_issues (int): total open issues inspected
      - missing (list[int]): issue numbers without a PR
      - data_ok (bool): False if gh subprocess failed; callers must NOT treat
        issues_without_pr=0 as "anomaly cleared" when data_ok is False.
    """
    result: dict[str, Any] = {
        "issues_without_pr": 0,
        "total_issues": 0,
        "missing": [],
        "data_ok": True,
    }

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
        result["data_ok"] = False
        return result

    try:
        issues = json.loads(list_result.stdout) if list_result.stdout.strip() else []
    except json.JSONDecodeError:
        print("[heartbeat] Cannot parse issue list JSON")
        result["data_ok"] = False
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


def check_scanner_liveness(
    threshold_hours: int = SCANNER_LIVENESS_THRESHOLD_HOURS,
) -> dict[str, Any]:
    """Check if the evolution scanner workflow has run recently.

    Uses the GitHub Actions API (gh run list) to verify the scanner is alive.
    This replaces cache-dependent file freshness checks: cross-workflow cache
    sharing is unreliable (eviction, scope issues), causing false-positive
    staleness alerts. Querying workflow run history is stateless and reliable.

    Returns a dict with:
      - alive (bool): True if the scanner ran within threshold_hours
      - hours_since_last_run (float): age of the most recent run (inf if unknown)
      - last_status (str): conclusion of the most recent run
      - message (str): human-readable status
    """
    result: dict[str, Any] = {
        "alive": True,
        "hours_since_last_run": float("inf"),
        "last_status": "unknown",
        "message": "",
    }
    try:
        proc = subprocess.run(
            [
                "gh", "run", "list",
                "--workflow", SCANNER_WORKFLOW,
                "--limit", "5",
                "--json", "status,conclusion,createdAt",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            result["alive"] = False
            result["message"] = f"Cannot query scanner runs: {proc.stderr.strip()}"
            return result

        runs = json.loads(proc.stdout) if proc.stdout.strip() else []
        if not runs:
            result["alive"] = False
            result["message"] = "No scanner runs found (workflow may be disabled)"
            return result

        now = datetime.now(timezone.utc)
        for run in runs:
            created_str = run.get("createdAt", "")
            try:
                created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            age_hours = (now - created).total_seconds() / 3600
            if age_hours < result["hours_since_last_run"]:
                result["hours_since_last_run"] = age_hours
                result["last_status"] = run.get("conclusion") or run.get("status", "unknown")
            if age_hours <= threshold_hours:
                result["alive"] = True
                result["message"] = (
                    f"Scanner alive: last run {age_hours:.1f}h ago "
                    f"(status: {result['last_status']})"
                )
                return result

        result["alive"] = False
        result["message"] = (
            f"Scanner stale: last run {result['hours_since_last_run']:.1f}h ago "
            f"(threshold: {threshold_hours}h, status: {result['last_status']})"
        )
    except Exception as exc:
        result["alive"] = False
        result["message"] = f"Scanner liveness check failed: {exc}"
    return result


def check_heartbeat_marker(max_age_hours: int = FRESHNESS_THRESHOLD_HOURS) -> dict[str, Any]:
    """Check dedicated heartbeat.json marker freshness (INFRA-204).

    This is a more precise signal than findings_over_time.json: the
    heartbeat is written at the END of a successful tick, so staleness
    means the scanner either didn't run or failed mid-tick.
    """
    result: dict[str, Any] = {"stale": True, "age_hours": float("inf"), "message": ""}

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
    MONITOR_HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _unique_tmp_path(MONITOR_HEARTBEAT_PATH)
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, MONITOR_HEARTBEAT_PATH)


def extract_recorded_anomalies(issue_body: str) -> set[str]:
    """Parse anomaly types from an alert issue body.

    Returns a set of anomaly type strings: {"scanner_stale", "issues_without_pr"}.

    Uses shared constants to ensure producer/consumer consistency.
    """
    anomalies = set()
    if _ANOMALY_SCANNER_STALE_MARKER in issue_body:
        anomalies.add("scanner_stale")
    if _ANOMALY_ISSUES_WITHOUT_PR_MARKER in issue_body:
        anomalies.add("issues_without_pr")
    return anomalies


def compute_current_anomalies(
    liveness: dict[str, Any], coverage: dict[str, Any]
) -> set[str]:
    """Compute the current set of anomaly types from check results.

    Returns a set of anomaly type strings: {"scanner_stale", "issues_without_pr"}.
    """
    anomalies: set[str] = set()
    if not liveness.get("alive", True):
        anomalies.add("scanner_stale")
    if coverage.get("issues_without_pr", 0) > 0:
        anomalies.add("issues_without_pr")
    return anomalies


def list_open_alert_issues() -> list[dict[str, Any]]:
    """List open heartbeat alert issues with their numbers and bodies."""
    result = subprocess.run(
        [
            "gh", "issue", "list",
            "--label", ALERT_LABEL,
            "--state", "open",
            "--json", "number,body",
            "--limit", "50",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"[heartbeat] Failed to list open alert issues: {result.stderr.strip()}")
        return []
    try:
        return json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        print("[heartbeat] Cannot parse open alert issues JSON")
        return []


def _issue_has_self_heal_comment(issue_num: int) -> bool:
    """Check if an issue already has a self-heal comment (duplicate prevention).

    Queries existing comments via `gh issue view --json comments` and checks
    if any comment body contains the self-heal marker. Used to avoid posting
    duplicate self-heal comments when close keeps failing across ticks.
    """
    try:
        result = subprocess.run(
            [
                "gh", "issue", "view", str(issue_num),
                "--json", "comments",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            # Fail-open: if we can't query comments, proceed with posting
            # (better to post duplicate than miss a legitimate self-heal)
            return False
        data = json.loads(result.stdout) if result.stdout.strip() else {}
        comments = data.get("comments", [])
        return any(_SELF_HEAL_MARKER in c.get("body", "") for c in comments)
    except (json.JSONDecodeError, OSError, subprocess.TimeoutExpired):
        # Fail-open on any error
        return False


def resolve_cleared_alerts(
    current_anomalies: set[str],
    open_alerts: list[dict[str, Any]] | None = None,
    coverage_data_ok: bool = True,
) -> list[int]:
    """Close alert issues whose recorded anomalies have all cleared.

    For each open alert issue, compares its recorded anomalies with the current
    anomaly set. If ALL recorded anomalies have disappeared (none remain in current),
    closes the issue and adds a Chinese self-heal comment listing which anomalies cleared.

    Args:
        current_anomalies: Set of currently active anomaly types
        open_alerts: List of open alert issues (fetched if None)
        coverage_data_ok: If False, skip self-heal entirely (fail-closed).
            This prevents false closes when check_pr_coverage couldn't verify data.

    Returns list of closed issue numbers.
    """
    # Fail-closed: if coverage data is unreliable, don't attempt self-heal
    if not coverage_data_ok:
        print("[heartbeat] Coverage data unavailable, skipping self-heal (fail-closed)")
        return []

    if open_alerts is None:
        open_alerts = list_open_alert_issues()

    if not open_alerts:
        return []

    closed: list[int] = []
    for issue in open_alerts:
        issue_num = issue.get("number")
        if not issue_num:
            continue

        recorded = extract_recorded_anomalies(issue.get("body", ""))
        if not recorded:
            continue

        # Check if all recorded anomalies have cleared
        cleared = recorded - current_anomalies
        if cleared and not (recorded & current_anomalies):
            # All anomalies cleared → close the issue
            cleared_names = sorted(cleared)  # deterministic order

            # Build Chinese self-heal comment
            anomaly_descriptions = {
                "scanner_stale": "扫描器心跳异常（scanner stale）",
                "issues_without_pr": "evolution-found issue 缺少关联 PR",
            }
            cleared_desc = [anomaly_descriptions.get(a, a) for a in cleared_names]

            comment = (
                "🩹 **自愈**：以下异常已消失，自动关闭此告警：\n\n"
                + "\n".join(f"- {desc}" for desc in cleared_desc)
            )

            # Check if a self-heal comment already exists (duplicate prevention)
            # This handles the case where close failed in a previous tick but
            # comment succeeded — avoid posting duplicate self-heal comments
            if _issue_has_self_heal_comment(issue_num):
                print(f"[heartbeat] Self-heal comment already exists on #{issue_num}, skipping duplicate comment")
                # Still try to close in case previous close failed
                close_result = subprocess.run(
                    ["gh", "issue", "close", str(issue_num)],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if close_result.returncode == 0:
                    print(f"[heartbeat] Self-heal: closed alert #{issue_num} (cleared: {cleared_names})")
                    closed.append(issue_num)
                else:
                    print(f"[heartbeat] Failed to close #{issue_num}: {close_result.stderr.strip()}")
                continue

            # Add self-heal comment and check return code
            comment_result = subprocess.run(
                [
                    "gh", "issue", "comment", str(issue_num),
                    "--body", comment,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if comment_result.returncode != 0:
                print(f"[heartbeat] Failed to comment on #{issue_num}: {comment_result.stderr.strip()}")
                # Don't proceed to close if comment failed (avoid orphan close)
                continue

            # Close the issue and check return code
            close_result = subprocess.run(
                ["gh", "issue", "close", str(issue_num)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if close_result.returncode != 0:
                print(f"[heartbeat] Failed to close #{issue_num}: {close_result.stderr.strip()}")
                # Don't add to closed list if close failed
                continue

            print(f"[heartbeat] Self-heal: closed alert #{issue_num} (cleared: {cleared_names})")
            closed.append(issue_num)

    return closed


def _build_alert_body(scanner_stale: bool, issues_without_pr: int) -> str:
    """Build alert issue body using shared constants.

    This function is the single source of truth for anomaly text format.
    The text MUST be parseable by extract_recorded_anomalies() using the same
    shared constants to prevent wording drift that would cause silent never-heal.
    """
    anomalies = []
    if scanner_stale:
        anomalies.append(f"{_ANOMALY_SCANNER_STALE_MARKER} (scanner may have stopped)")
    if issues_without_pr > 0:
        anomalies.append(f"{issues_without_pr} {_ANOMALY_ISSUES_WITHOUT_PR_MARKER}")

    body_lines = [
        "## Evolution Heartbeat Alert",
        "",
        f"**Detected**: {datetime.now(timezone.utc).isoformat()}",
        "",
        "### Anomalies",
        "",
    ]
    for anomaly in anomalies:
        body_lines.append(f"- {anomaly}")

    return "\n".join(body_lines)


def create_alert_issue(
    scanner_stale: bool,
    issues_without_pr: int,
    dedup_label: str = EVOLUTION_FOUND_LABEL,
) -> bool:
    """Create a GitHub Issue for detected pipeline anomalies.

    Returns True if an issue was created, False if no anomaly or creation failed.
    """
    if not scanner_stale and issues_without_pr == 0:
        return False

    body = _build_alert_body(scanner_stale, issues_without_pr)
    title = "[heartbeat] Pipeline anomaly detected"

    create_result = subprocess.run(
        [
            "gh", "issue", "create",
            "--title", title,
            "--body", body,
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
    # Primary: scanner liveness via GitHub Actions API (stateless, no cache dependency)
    liveness = check_scanner_liveness()
    if liveness["alive"]:
        print(f"[heartbeat] {liveness['message']}")
    else:
        print(f"[heartbeat] ALERT: {liveness['message']}")

    # Advisory: file-based checks (may show stale if cache missed — NOT an alert basis)
    heartbeat = check_heartbeat_marker()
    print(f"[heartbeat] (advisory) {heartbeat['message']}")

    freshness = check_history_freshness(history_path)
    print(f"[heartbeat] (advisory) {freshness['message']}")

    # Check 2: PR coverage
    coverage = check_pr_coverage()
    if not coverage.get("data_ok", True):
        print("[heartbeat] WARNING: PR coverage check failed, data unreliable")
    elif coverage["issues_without_pr"] > 0:
        print(
            f"[heartbeat] ALERT: {coverage['issues_without_pr']} issue(s) "
            f"without PR: {coverage['missing']}"
        )
    else:
        print("[heartbeat] PR coverage: OK")

    # P1 self-heal: close alert issues whose anomalies have cleared
    current_anomalies = compute_current_anomalies(liveness, coverage)
    closed = resolve_cleared_alerts(
        current_anomalies,
        coverage_data_ok=coverage.get("data_ok", True),
    )
    if closed:
        print(f"[heartbeat] Self-heal: closed {len(closed)} alert(s): {closed}")

    # INFRA-204: Write monitor heartbeat for meta-monitoring
    anomaly_count = sum([not liveness["alive"], bool(coverage["issues_without_pr"] > 0)])

    # Create alert issue if scanner is stale or issues lack PRs
    if not liveness["alive"] or coverage["issues_without_pr"] > 0:
        if alert_issue_exists():
            print("[heartbeat] Open alert issue already exists, skipping duplicate creation")
        else:
            create_alert_issue(
                scanner_stale=not liveness["alive"],
                issues_without_pr=coverage["issues_without_pr"],
            )
        write_monitor_heartbeat(anomaly_count)
        return 1  # Non-zero exit signals anomaly to CI

    write_monitor_heartbeat(anomaly_count)
    print("[heartbeat] All checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
