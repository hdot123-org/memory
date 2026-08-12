"""Tests for evolution heartbeat monitor.

INFRA-213: Tests the scanner liveness check (gh run list) and main() orchestration.
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path for import
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

import evolution_heartbeat  # noqa: E402


def _gh_result(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    """Create a mock subprocess.run result."""
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


def _recent_run(hours_ago: float, conclusion: str = "success") -> dict:
    """Create a gh run list entry from N hours ago."""
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {"status": "completed", "conclusion": conclusion, "createdAt": ts}


# ---------------------------------------------------------------------------
# check_scanner_liveness
# ---------------------------------------------------------------------------

def test_scanner_alive_recent_success():
    """Scanner ran 30 minutes ago → alive."""
    runs = [_recent_run(0.5, "success")]
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps(runs))
        result = evolution_heartbeat.check_scanner_liveness()

    assert result["alive"] is True
    assert result["hours_since_last_run"] < 1.0


def test_scanner_stale_no_recent_runs():
    """Last scanner run was 5 hours ago → stale."""
    runs = [_recent_run(5.0, "success")]
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps(runs))
        result = evolution_heartbeat.check_scanner_liveness()

    assert result["alive"] is False
    assert "stale" in result["message"].lower()


def test_scanner_no_runs_at_all():
    """No scanner runs found → not alive."""
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result("[]")
        result = evolution_heartbeat.check_scanner_liveness()

    assert result["alive"] is False
    assert "No scanner runs" in result["message"]


def test_scanner_gh_failure():
    """gh command fails → not alive, error message."""
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(returncode=1, stderr="auth error")
        result = evolution_heartbeat.check_scanner_liveness()

    assert result["alive"] is False
    assert "Cannot query" in result["message"]


def test_scanner_mixed_runs_finds_recent():
    """Multiple runs, one recent → alive (picks the most recent)."""
    runs = [
        _recent_run(5.0, "failure"),
        _recent_run(0.5, "success"),
        _recent_run(3.0, "success"),
    ]
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps(runs))
        result = evolution_heartbeat.check_scanner_liveness()

    assert result["alive"] is True
    assert result["hours_since_last_run"] < 1.0


def test_scanner_recent_failure_still_alive():
    """Scanner ran recently but failed → still 'alive' (it ran, just errored).

    The liveness check detects if the scanner STOPPED, not if it errored.
    A recent failure means the scanner is still being triggered.
    """
    runs = [_recent_run(0.5, "failure")]
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps(runs))
        result = evolution_heartbeat.check_scanner_liveness()

    assert result["alive"] is True
    assert result["last_status"] == "failure"


def test_scanner_subprocess_timeout():
    """subprocess raises exception → not alive, error message."""
    with patch("evolution_heartbeat.subprocess.run", side_effect=Exception("timeout")):
        result = evolution_heartbeat.check_scanner_liveness()

    assert result["alive"] is False
    assert "failed" in result["message"].lower()


# ---------------------------------------------------------------------------
# main() orchestration
# ---------------------------------------------------------------------------

def test_main_all_ok_returns_0():
    """Scanner alive + no issues without PR → exit 0."""
    runs = [_recent_run(0.5, "success")]
    with patch("evolution_heartbeat.subprocess.run") as mock_run, \
         patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb, \
         patch("evolution_heartbeat.check_history_freshness") as mock_hist, \
         patch("evolution_heartbeat.write_monitor_heartbeat"):
        mock_run.return_value = _gh_result(json.dumps(runs))
        mock_hb.return_value = {"stale": True, "message": "advisory stale"}
        mock_hist.return_value = {"stale": True, "message": "advisory stale"}
        with patch("evolution_heartbeat.check_pr_coverage") as mock_cov:
            mock_cov.return_value = {
                "issues_without_pr": 0,
                "total_issues": 0,
                "missing": [],
            }
            rc = evolution_heartbeat.main()

    assert rc == 0


def test_main_scanner_stale_returns_1():
    """Scanner stale → exit 1, alert created."""
    runs = [_recent_run(5.0, "success")]
    with patch("evolution_heartbeat.subprocess.run") as mock_run, \
         patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb, \
         patch("evolution_heartbeat.check_history_freshness") as mock_hist, \
         patch("evolution_heartbeat.check_pr_coverage") as mock_cov, \
         patch("evolution_heartbeat.alert_issue_exists", return_value=False), \
         patch("evolution_heartbeat.create_alert_issue") as mock_create, \
         patch("evolution_heartbeat.write_monitor_heartbeat"):
        mock_run.return_value = _gh_result(json.dumps(runs))
        mock_hb.return_value = {"stale": True, "message": "advisory"}
        mock_hist.return_value = {"stale": True, "message": "advisory"}
        mock_cov.return_value = {
            "issues_without_pr": 0,
            "total_issues": 0,
            "missing": [],
        }
        rc = evolution_heartbeat.main()

    assert rc == 1
    mock_create.assert_called_once_with(scanner_stale=True, issues_without_pr=0)


def test_main_advisory_checks_do_not_trigger_alert():
    """File-based checks stale but scanner alive → exit 0, no alert.

    This is the core INFRA-213 fix: cache-dependent checks showing stale
    must NOT trigger alerts when the scanner is confirmed alive.
    """
    runs = [_recent_run(0.3, "success")]
    with patch("evolution_heartbeat.subprocess.run") as mock_run, \
         patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb, \
         patch("evolution_heartbeat.check_history_freshness") as mock_hist, \
         patch("evolution_heartbeat.write_monitor_heartbeat"):
        mock_run.return_value = _gh_result(json.dumps(runs))
        mock_hb.return_value = {"stale": True, "message": "marker missing"}
        mock_hist.return_value = {"stale": True, "message": "history missing"}
        with patch("evolution_heartbeat.check_pr_coverage") as mock_cov:
            mock_cov.return_value = {
                "issues_without_pr": 0,
                "total_issues": 0,
                "missing": [],
            }
            rc = evolution_heartbeat.main()

    assert rc == 0
