"""Tests for evolution heartbeat monitor.

INFRA-213: Tests the scanner liveness check (gh run list) and main() orchestration.
"""

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
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
    ts = (datetime.now(UTC) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
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
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
    ):
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
    """Scanner stale + dispatch REJECTED → exit 1, alert created.

    INFRA-597 contract change: a *successful* dispatch now suppresses the
    scanner_stale alert (see test_infra597_* below). The alert path is only
    entered when self-heal itself fails (or the outage is severe).
    """
    runs = [_recent_run(5.0, "success")]
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.check_pr_coverage") as mock_cov,
        patch("evolution_heartbeat.alert_issue_exists", return_value=False),
        patch("evolution_heartbeat.create_alert_issue") as mock_create,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
        patch("evolution_heartbeat.trigger_scanner_dispatch", return_value=False),
    ):
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
    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["scanner_stale"] is True
    assert kwargs["issues_without_pr"] == 0


def test_main_advisory_checks_do_not_trigger_alert():
    """File-based checks stale but scanner alive → exit 0, no alert.

    This is the core INFRA-213 fix: cache-dependent checks showing stale
    must NOT trigger alerts when the scanner is confirmed alive.
    """
    runs = [_recent_run(0.3, "success")]
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
    ):
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


# ---------------------------------------------------------------------------
# VAL-HB: heartbeat self-heal (P1)
# ---------------------------------------------------------------------------

_ALERT_BODY_ISSUES_WITHOUT_PR = (
    "## Evolution Heartbeat Alert\n\n"
    "**Detected**: 2026-08-14T16:48:41.340399+00:00\n"
    "**Scope**: evolution-found\n\n"
    "### Anomalies\n\n"
    "- 1 evolution-found issue(s) without associated PR\n"
)

_ALERT_BODY_SCANNER_STALE = (
    "## Evolution Heartbeat Alert\n\n"
    "**Detected**: 2026-08-14T16:48:41.340399+00:00\n"
    "**Scope**: evolution-found\n\n"
    "### Anomalies\n\n"
    "- evolution-scan workflow has not run recently (scanner may have stopped)\n"
)

_ALERT_BODY_BOTH = (
    "## Evolution Heartbeat Alert\n\n"
    "**Detected**: 2026-08-14T16:48:41.340399+00:00\n"
    "**Scope**: evolution-found\n\n"
    "### Anomalies\n\n"
    "- evolution-scan workflow has not run recently (scanner may have stopped)\n"
    "- 1 evolution-found issue(s) without associated PR\n"
)


def test_heartbeat_001_anomaly_resolved_auto_closes_alert():
    """VAL-HB-001: anomaly disappeared → alert issue auto-closed + Chinese self-heal comment."""
    open_alerts = [
        {"number": 646, "body": _ALERT_BODY_ISSUES_WITHOUT_PR},
    ]
    # Current anomaly set: no anomalies (scanner alive, no issues without PR)
    current_anomalies: set[str] = set()

    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(returncode=0)
        closed = evolution_heartbeat.resolve_cleared_alerts(
            current_anomalies,
            open_alerts,
        )

    assert closed == [646]

    # Verify gh was called: first to comment, then to close
    gh_calls = [call.args[0] for call in mock_run.call_args_list]
    # Should have a comment call and a close call
    comment_calls = [c for c in gh_calls if "comment" in c]
    close_calls = [c for c in gh_calls if "close" in c]
    assert len(comment_calls) == 1
    assert len(close_calls) == 1
    # The comment body should contain Chinese self-heal text
    # Find the comment call and check its --body argument
    for call in mock_run.call_args_list:
        args = call.args[0]
        if "comment" in args:
            body_idx = args.index("--body") + 1
            body = args[body_idx]
            assert "自愈" in body
            assert "646" in body or "evolution-found" in body.lower() or "已消失" in body


def test_heartbeat_001b_both_anomalies_cleared():
    """VAL-HB-001 variant: issue with both anomalies, both cleared → close."""
    open_alerts = [
        {"number": 700, "body": _ALERT_BODY_BOTH},
    ]
    current_anomalies: set[str] = set()

    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(returncode=0)
        closed = evolution_heartbeat.resolve_cleared_alerts(
            current_anomalies,
            open_alerts,
        )

    assert closed == [700]


def test_heartbeat_002_anomaly_persists_no_close():
    """VAL-HB-002: anomaly still present → alert stays OPEN, zero close actions."""
    open_alerts = [
        {"number": 646, "body": _ALERT_BODY_ISSUES_WITHOUT_PR},
    ]
    # Current anomaly set: issues_without_pr still present
    current_anomalies: set[str] = {"issues_without_pr"}

    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(returncode=0)
        closed = evolution_heartbeat.resolve_cleared_alerts(
            current_anomalies,
            open_alerts,
        )

    assert closed == []
    # No gh calls should have been made for close or comment
    for call in mock_run.call_args_list:
        args = call.args[0]
        assert "close" not in args, "Should not close when anomaly persists"


def test_heartbeat_002b_partial_clear_no_close():
    """VAL-HB-002 variant: one anomaly cleared but other persists → no close."""
    open_alerts = [
        {"number": 700, "body": _ALERT_BODY_BOTH},
    ]
    # Only scanner_stale persists; issues_without_pr cleared
    current_anomalies: set[str] = {"scanner_stale"}

    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(returncode=0)
        closed = evolution_heartbeat.resolve_cleared_alerts(
            current_anomalies,
            open_alerts,
        )

    assert closed == []


def test_heartbeat_003_no_anomaly_no_action():
    """VAL-HB-003: no current anomalies, no open alerts → zero close, zero create."""
    current_anomalies: set[str] = set()
    open_alerts: list[dict] = []

    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(returncode=0)
        closed = evolution_heartbeat.resolve_cleared_alerts(
            current_anomalies,
            open_alerts,
        )

    assert closed == []
    mock_run.assert_not_called()


def test_extract_recorded_anomalies_from_body():
    """Unit: parse anomaly types from alert issue body."""
    assert evolution_heartbeat.extract_recorded_anomalies(_ALERT_BODY_ISSUES_WITHOUT_PR) == {"issues_without_pr"}
    assert evolution_heartbeat.extract_recorded_anomalies(_ALERT_BODY_SCANNER_STALE) == {"scanner_stale"}
    assert evolution_heartbeat.extract_recorded_anomalies(_ALERT_BODY_BOTH) == {"scanner_stale", "issues_without_pr"}
    assert evolution_heartbeat.extract_recorded_anomalies("") == set()


def test_compute_current_anomalies_from_checks():
    """Unit: compute current anomaly set from liveness + coverage results."""
    # Scanner alive, no issues without PR → empty
    assert (
        evolution_heartbeat.compute_current_anomalies(
            {"alive": True},
            {"issues_without_pr": 0},
        )
        == set()
    )

    # Scanner stale → scanner_stale
    assert evolution_heartbeat.compute_current_anomalies(
        {"alive": False},
        {"issues_without_pr": 0},
    ) == {"scanner_stale"}

    # Issues without PR → issues_without_pr
    assert evolution_heartbeat.compute_current_anomalies(
        {"alive": True},
        {"issues_without_pr": 3},
    ) == {"issues_without_pr"}

    # Both
    assert evolution_heartbeat.compute_current_anomalies(
        {"alive": False},
        {"issues_without_pr": 1},
    ) == {"scanner_stale", "issues_without_pr"}


# ---------------------------------------------------------------------------
# VAL-HB-004: fail-closed hardening
# ---------------------------------------------------------------------------


def test_heartbeat_004_check_pr_coverage_gh_failure_marks_data_unknown():
    """VAL-HB-004: gh subprocess failure in check_pr_coverage must NOT return
    issues_without_pr=0 with data_ok=True. Must signal data_ok=False."""
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        # Simulate gh issue list failing (transient auth error / network)
        mock_run.return_value = _gh_result(returncode=1, stderr="fatal: unable to access")
        result = evolution_heartbeat.check_pr_coverage()

    assert result["data_ok"] is False, "check_pr_coverage must set data_ok=False when gh fails"


def test_heartbeat_004_resolve_cleared_alerts_skips_when_coverage_data_unknown():
    """VAL-HB-004: resolve_cleared_alerts must zero-close when coverage data is unknown.
    Even if anomalies appear 'cleared', we must not self-heal on unreliable data."""
    open_alerts = [
        {"number": 646, "body": _ALERT_BODY_ISSUES_WITHOUT_PR},
    ]
    # current_anomalies is empty (would look like anomaly cleared)
    current_anomalies: set[str] = set()

    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        closed = evolution_heartbeat.resolve_cleared_alerts(
            current_anomalies,
            open_alerts,
            coverage_data_ok=False,
        )

    assert closed == [], "Must not close any alerts when coverage data is unknown"
    mock_run.assert_not_called(), "No gh calls should be made when data is unknown"


def test_heartbeat_004_main_skips_self_heal_on_coverage_data_unknown():
    """VAL-HB-004: main() must skip self-heal when check_pr_coverage reports data_ok=False."""
    runs = [_recent_run(0.5, "success")]  # scanner alive
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
        patch("evolution_heartbeat.list_open_alert_issues") as mock_list,
    ):
        # gh run list succeeds (scanner alive)
        # gh issue list for check_pr_coverage fails
        def side_effect(args, **kwargs):
            if "run" in args and "list" in args:
                return _gh_result(json.dumps(runs))
            if "issue" in args and "list" in args and "--label" in args:
                # This is check_pr_coverage's gh issue list call → fail
                label_idx = args.index("--label") + 1
                if args[label_idx] == evolution_heartbeat.EVOLUTION_FOUND_LABEL:
                    return _gh_result(returncode=1, stderr="network error")
                # This is list_open_alert_issues → return empty
                return _gh_result("[]")
            return _gh_result(returncode=0)

        mock_run.side_effect = side_effect
        mock_hb.return_value = {"stale": True, "message": "advisory"}
        mock_hist.return_value = {"stale": True, "message": "advisory"}
        mock_list.return_value = [{"number": 646, "body": _ALERT_BODY_ISSUES_WITHOUT_PR}]

        rc = evolution_heartbeat.main()

    # Scanner alive + coverage unknown → no anomaly from coverage, but self-heal skipped
    # Exit 0 because no confirmed anomaly
    assert rc == 0

    # Strengthened assertion: verify zero gh issue close/comment subprocess calls
    # (not just "skip self-heal" but actively prove no gh close/comment was invoked)
    close_or_comment_calls = [
        c
        for c in mock_run.call_args_list
        if ("comment" in c.args[0] or "close" in c.args[0]) and "run" not in c.args[0]  # exclude "gh run list"
    ]
    assert len(close_or_comment_calls) == 0, (
        f"Zero gh close/comment calls expected when coverage data unknown, "
        f"but found {len(close_or_comment_calls)}: {[c.args[0] for c in close_or_comment_calls]}"
    )


# ---------------------------------------------------------------------------
# Close/comment returncode hardening
# ---------------------------------------------------------------------------


def test_heartbeat_close_failure_not_added_to_closed_list():
    """gh issue close fails → issue NOT in closed list, error logged."""
    open_alerts = [
        {"number": 646, "body": _ALERT_BODY_ISSUES_WITHOUT_PR},
    ]
    current_anomalies: set[str] = set()

    with patch("evolution_heartbeat.subprocess.run") as mock_run:

        def side_effect(args, **kwargs):
            if "comment" in args:
                return _gh_result(returncode=0)  # comment succeeds
            if "close" in args:
                return _gh_result(returncode=1, stderr="permission denied")  # close fails
            return _gh_result(returncode=0)

        mock_run.side_effect = side_effect
        closed = evolution_heartbeat.resolve_cleared_alerts(
            current_anomalies,
            open_alerts,
        )

    assert closed == [], "Failed close must not be in closed list"


def test_heartbeat_comment_failure_prevents_close():
    """gh issue comment fails → skip close entirely (no orphan close without audit trail)."""
    open_alerts = [
        {"number": 646, "body": _ALERT_BODY_ISSUES_WITHOUT_PR},
    ]
    current_anomalies: set[str] = set()

    with patch("evolution_heartbeat.subprocess.run") as mock_run:

        def side_effect(args, **kwargs):
            if "comment" in args:
                return _gh_result(returncode=1, stderr="rate limited")  # comment fails
            if "close" in args:
                return _gh_result(returncode=0)  # close would succeed
            return _gh_result(returncode=0)

        mock_run.side_effect = side_effect
        closed = evolution_heartbeat.resolve_cleared_alerts(
            current_anomalies,
            open_alerts,
        )

    assert closed == [], "Close must be skipped when comment fails"
    # Verify close was NOT called (no orphan close)
    for call in mock_run.call_args_list:
        args = call.args[0]
        if "close" in args and "comment" not in args:
            raise AssertionError("Close should not be called when comment fails")


# ---------------------------------------------------------------------------
# String coupling elimination: roundtrip test
# ---------------------------------------------------------------------------


def test_anomaly_text_roundtrip_scanner_stale():
    """create_alert_issue body must be parseable by extract_recorded_anomalies.
    This roundtrip test prevents wording drift that would cause silent never-heal."""
    # Simulate what create_alert_issue writes for scanner_stale
    body = evolution_heartbeat._build_alert_body(scanner_stale=True, issues_without_pr=0)
    parsed = evolution_heartbeat.extract_recorded_anomalies(body)
    assert parsed == {"scanner_stale"}, f"Roundtrip failed: create_alert_issue body not parseable. Got {parsed}"


def test_anomaly_text_roundtrip_issues_without_pr():
    """Roundtrip: issues_without_pr anomaly text."""
    body = evolution_heartbeat._build_alert_body(scanner_stale=False, issues_without_pr=3)
    parsed = evolution_heartbeat.extract_recorded_anomalies(body)
    assert parsed == {"issues_without_pr"}, f"Roundtrip failed: create_alert_issue body not parseable. Got {parsed}"


def test_anomaly_text_roundtrip_both():
    """Roundtrip: both anomalies."""
    body = evolution_heartbeat._build_alert_body(scanner_stale=True, issues_without_pr=2)
    parsed = evolution_heartbeat.extract_recorded_anomalies(body)
    assert parsed == {"scanner_stale", "issues_without_pr"}, (
        f"Roundtrip failed: create_alert_issue body not parseable. Got {parsed}"
    )


def test_anomaly_constants_match():
    """Module-level constants used by both producer and consumer must be identical."""
    # Verify the constants exist and are used consistently
    assert hasattr(evolution_heartbeat, "_ANOMALY_SCANNER_STALE_MARKER")
    assert hasattr(evolution_heartbeat, "_ANOMALY_ISSUES_WITHOUT_PR_MARKER")
    assert hasattr(evolution_heartbeat, "_SELF_HEAL_MARKER")

    # Verify extract_recorded_anomalies uses the constants
    body_with_scanner = f"some text {evolution_heartbeat._ANOMALY_SCANNER_STALE_MARKER} more text"
    assert evolution_heartbeat.extract_recorded_anomalies(body_with_scanner) == {"scanner_stale"}

    body_with_pr = f"some text {evolution_heartbeat._ANOMALY_ISSUES_WITHOUT_PR_MARKER} more text"
    assert evolution_heartbeat.extract_recorded_anomalies(body_with_pr) == {"issues_without_pr"}


# ---------------------------------------------------------------------------
# Repeat comment protection (duplicate prevention)
# ---------------------------------------------------------------------------


def test_issue_has_self_heal_comment_detects_existing():
    """_issue_has_self_heal_comment: detects existing self-heal comment."""
    comments_json = json.dumps(
        {
            "comments": [
                {"body": "Some regular comment"},
                {"body": "🩹 **自愈**：以下异常已消失，自动关闭此告警：\n\n- test"},
            ]
        }
    )
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(stdout=comments_json)
        result = evolution_heartbeat._issue_has_self_heal_comment(646)

    assert result is True
    # Verify gh was called correctly
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[:3] == ["gh", "issue", "view"]
    assert "646" in args


def test_issue_has_self_heal_comment_no_match():
    """_issue_has_self_heal_comment: no self-heal marker → False."""
    comments_json = json.dumps(
        {
            "comments": [
                {"body": "Some regular comment"},
                {"body": "Another comment without the marker"},
            ]
        }
    )
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(stdout=comments_json)
        result = evolution_heartbeat._issue_has_self_heal_comment(646)

    assert result is False


def test_issue_has_self_heal_comment_gh_failure_fail_open():
    """_issue_has_self_heal_comment: gh failure → fail-open (return False)."""
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(returncode=1, stderr="error")
        result = evolution_heartbeat._issue_has_self_heal_comment(646)

    assert result is False


def test_resolve_cleared_alerts_skips_duplicate_comment():
    """resolve_cleared_alerts: existing self-heal comment → skip duplicate, still try close."""
    open_alerts = [
        {"number": 646, "body": _ALERT_BODY_ISSUES_WITHOUT_PR},
    ]
    current_anomalies: set[str] = set()

    # Simulate: gh issue view returns existing self-heal comment, close succeeds
    def side_effect(args, **kwargs):
        if "view" in args:  # gh issue view for checking comments
            return _gh_result(stdout=json.dumps({"comments": [{"body": "🩹 **自愈**：previous attempt"}]}))
        if "close" in args:
            return _gh_result(returncode=0)  # close succeeds this time
        return _gh_result(returncode=0)

    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.side_effect = side_effect
        closed = evolution_heartbeat.resolve_cleared_alerts(
            current_anomalies,
            open_alerts,
        )

    assert closed == [646], "Should close after detecting existing comment"
    # Verify no duplicate comment was posted
    comment_calls = [c for c in mock_run.call_args_list if "comment" in c.args[0]]
    assert len(comment_calls) == 0, "Should not post duplicate self-heal comment"


def test_resolve_cleared_alerts_skips_duplicate_comment_close_fails():
    """resolve_cleared_alerts: existing self-heal comment + close fails → not in closed list."""
    open_alerts = [
        {"number": 646, "body": _ALERT_BODY_ISSUES_WITHOUT_PR},
    ]
    current_anomalies: set[str] = set()

    def side_effect(args, **kwargs):
        if "view" in args:  # gh issue view for checking comments
            return _gh_result(stdout=json.dumps({"comments": [{"body": "🩹 **自愈**：previous attempt"}]}))
        if "close" in args:
            return _gh_result(returncode=1, stderr="still failing")  # close fails again
        return _gh_result(returncode=0)

    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.side_effect = side_effect
        closed = evolution_heartbeat.resolve_cleared_alerts(
            current_anomalies,
            open_alerts,
        )

    assert closed == [], "Should not add to closed list when close fails"
    # Verify no duplicate comment was posted
    comment_calls = [c for c in mock_run.call_args_list if "comment" in c.args[0]]
    assert len(comment_calls) == 0, "Should not post duplicate self-heal comment"


# ---------------------------------------------------------------------------
# INFRA-578: scanner stale self-heal via workflow_dispatch
# ---------------------------------------------------------------------------


def test_infra578_trigger_scanner_dispatch_success():
    """INFRA-578: dispatch succeeds → True, correct gh workflow run command."""
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(returncode=0)
        result = evolution_heartbeat.trigger_scanner_dispatch()

    assert result is True
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args == ["gh", "workflow", "run", evolution_heartbeat.SCANNER_WORKFLOW]


def test_infra578_trigger_scanner_dispatch_failure():
    """INFRA-578: gh workflow run fails → False (alert still raised by main)."""
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(returncode=1, stderr="workflow not found")
        result = evolution_heartbeat.trigger_scanner_dispatch()

    assert result is False


def test_infra578_trigger_scanner_dispatch_timeout():
    """INFRA-578: subprocess timeout → False, no exception escapes."""
    with patch("evolution_heartbeat.subprocess.run", side_effect=subprocess.TimeoutExpired("gh", 30)):
        result = evolution_heartbeat.trigger_scanner_dispatch()

    assert result is False


def test_infra578_main_stale_scanner_triggers_dispatch():
    """INFRA-578: main() with stale scanner must attempt self-heal dispatch before alerting.

    INFRA-597: with the dispatch mocked to FAIL here, the alert must still be
    created (observability preserved when self-heal is broken).
    """
    runs = [_recent_run(5.0, "success")]  # stale
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.check_pr_coverage") as mock_cov,
        patch("evolution_heartbeat.alert_issue_exists", return_value=False),
        patch("evolution_heartbeat.create_alert_issue") as mock_create,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
        patch("evolution_heartbeat.trigger_scanner_dispatch", return_value=False) as mock_dispatch,
    ):
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
    mock_dispatch.assert_called_once()
    # Alert must still be created because dispatch was rejected
    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["scanner_stale"] is True
    assert kwargs["issues_without_pr"] == 0


def test_infra578_main_alive_scanner_skips_dispatch():
    """INFRA-578: main() with alive scanner must NOT dispatch (no spurious triggers)."""
    runs = [_recent_run(0.5, "success")]  # alive
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.check_pr_coverage") as mock_cov,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
        patch("evolution_heartbeat.trigger_scanner_dispatch") as mock_dispatch,
    ):
        mock_run.return_value = _gh_result(json.dumps(runs))
        mock_hb.return_value = {"stale": True, "message": "advisory"}
        mock_hist.return_value = {"stale": True, "message": "advisory"}
        mock_cov.return_value = {
            "issues_without_pr": 0,
            "total_issues": 0,
            "missing": [],
        }
        rc = evolution_heartbeat.main()

    assert rc == 0
    mock_dispatch.assert_not_called()


def test_infra578_main_dispatch_failure_still_alerts():
    """INFRA-578: dispatch fails → alert still created, exit 1 (observability preserved)."""
    runs = [_recent_run(5.0, "success")]  # stale
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.check_pr_coverage") as mock_cov,
        patch("evolution_heartbeat.alert_issue_exists", return_value=False),
        patch("evolution_heartbeat.create_alert_issue") as mock_create,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
        patch("evolution_heartbeat.trigger_scanner_dispatch", return_value=False),
    ):
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
    kwargs = mock_create.call_args.kwargs
    assert kwargs["scanner_stale"] is True
    assert kwargs["issues_without_pr"] == 0


# ---------------------------------------------------------------------------
# INFRA-597: alert suppression on successful self-heal dispatch
# ---------------------------------------------------------------------------


def test_infra597_successful_dispatch_suppresses_alert():
    """INFRA-597: stale scanner + dispatch ACCEPTED (non-severe) → no alert issue, exit 0.

    Root cause of the 4-day alert storm (#1046/#1051/#1055/#1059): GitHub
    load-shed dropped cron slots for both workflows; the heartbeat detected a
    transient 5.8h gap, healed it via workflow_dispatch (run completed), and
    STILL created an alert issue that synced to Linear and dispatched an
    agent session. Alert semantics must be "self-heal failed", not "staleness
    occurred".
    """
    runs = [_recent_run(5.0, "success")]  # stale but non-severe (< 8h)
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.check_pr_coverage") as mock_cov,
        patch("evolution_heartbeat.alert_issue_exists") as mock_exists,
        patch("evolution_heartbeat.create_alert_issue") as mock_create,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
        patch("evolution_heartbeat.trigger_scanner_dispatch", return_value=True),
    ):
        mock_run.return_value = _gh_result(json.dumps(runs))
        mock_hb.return_value = {"stale": True, "message": "advisory"}
        mock_hist.return_value = {"stale": True, "message": "advisory"}
        mock_cov.return_value = {
            "issues_without_pr": 0,
            "total_issues": 0,
            "missing": [],
        }
        rc = evolution_heartbeat.main()

    assert rc == 0
    mock_create.assert_not_called()
    mock_exists.assert_not_called()


def test_infra597_suppression_heals_prior_alert():
    """INFRA-597: dispatch accepted → prior open scanner_stale alert gets self-heal closed.

    This is the #1059 scenario: by the time this fix lands, the transient
    alert may still be open. With suppression active, the current anomaly set
    treats the scanner as recovered, so resolve_cleared_alerts closes it with
    the standard self-heal comment instead of waiting for the next scan run.
    """
    runs = [_recent_run(5.0, "success")]  # stale but non-severe
    open_alerts = [{"number": 1059, "body": _ALERT_BODY_SCANNER_STALE}]

    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_scanner_liveness") as mock_liveness,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.check_pr_coverage") as mock_cov,
        patch("evolution_heartbeat.list_open_alert_issues", return_value=open_alerts),
        patch("evolution_heartbeat.alert_issue_exists", return_value=False),
        patch("evolution_heartbeat.create_alert_issue"),
        patch("evolution_heartbeat.write_monitor_heartbeat"),
        patch("evolution_heartbeat.trigger_scanner_dispatch", return_value=True),
    ):
        mock_liveness.return_value = {
            "alive": False,
            "hours_since_last_run": 5.0,
            "last_status": "success",
            "message": "Scanner stale: last run 5.0h ago",
        }
        # _issue_has_self_heal_comment (gh issue view) → no prior comment;
        # self-heal comment + close succeed
        def side_effect(args, **kwargs):
            if "view" in args:
                return _gh_result(stdout=json.dumps({"comments": []}))
            return _gh_result(stdout="[]", returncode=0)

        mock_run.side_effect = side_effect
        mock_hb.return_value = {"stale": True, "message": "advisory"}
        mock_hist.return_value = {"stale": True, "message": "advisory"}
        mock_cov.return_value = {
            "issues_without_pr": 0,
            "total_issues": 0,
            "missing": [],
        }
        rc = evolution_heartbeat.main()

    assert rc == 0
    close_calls = [c.args[0] for c in mock_run.call_args_list if "close" in c.args[0]]
    assert len(close_calls) == 1, "Prior alert #1059 must be self-heal closed"


def test_infra597_severe_outage_alerts_despite_dispatch():
    """INFRA-597: outage > SCANNER_SEVERE_STALENESS_HOURS → alert even if dispatch accepted.

    Repeated dispatch success with no new run appearing implies systemic
    failure (broken workflow, disabled runner, auth issue). The suppression
    must not silence a genuinely long outage.
    """
    runs = [_recent_run(12.0, "success")]  # severe (> 8h)
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.check_pr_coverage") as mock_cov,
        patch("evolution_heartbeat.alert_issue_exists", return_value=False),
        patch("evolution_heartbeat.create_alert_issue") as mock_create,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
        patch("evolution_heartbeat.trigger_scanner_dispatch", return_value=True),
    ):
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
    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["scanner_stale"] is True
    assert kwargs["scanner_stale_hours"] is not None
    assert kwargs["scanner_stale_hours"] > 12.0 - 1.0  # ~12h, not 5h


def test_infra597_suppression_does_not_affect_coverage_anomaly():
    """INFRA-597: suppression only covers scanner_stale; issues_without_pr still alerts."""
    runs = [_recent_run(5.0, "success")]  # stale but non-severe
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.check_pr_coverage") as mock_cov,
        patch("evolution_heartbeat.alert_issue_exists", return_value=False),
        patch("evolution_heartbeat.create_alert_issue") as mock_create,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
        patch("evolution_heartbeat.trigger_scanner_dispatch", return_value=True),
    ):
        mock_run.return_value = _gh_result(json.dumps(runs))
        mock_hb.return_value = {"stale": True, "message": "advisory"}
        mock_hist.return_value = {"stale": True, "message": "advisory"}
        mock_cov.return_value = {
            "issues_without_pr": 2,
            "total_issues": 2,
            "missing": [101, 102],
        }
        rc = evolution_heartbeat.main()

    assert rc == 1
    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["scanner_stale"] is False  # suppressed
    assert kwargs["issues_without_pr"] == 2  # still alerting


def test_infra597_suppression_boundary_exact_severe_threshold():
    """INFRA-597: just BELOW the severe threshold (8h) is NOT severe — suppress.

    Uses 7.9h instead of exactly 8.0h to avoid a time-of-test race: the age is
    recomputed from `runs` timestamps, and a few ms of drift would push a
    nominally-exact 8.0h over the strict `>` boundary and flip the outcome.
    """
    runs = [_recent_run(7.9, "success")]  # below 8h → non-severe
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.check_pr_coverage") as mock_cov,
        patch("evolution_heartbeat.alert_issue_exists") as mock_exists,
        patch("evolution_heartbeat.create_alert_issue") as mock_create,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
        patch("evolution_heartbeat.trigger_scanner_dispatch", return_value=True),
    ):
        mock_run.return_value = _gh_result(json.dumps(runs))
        mock_hb.return_value = {"stale": True, "message": "advisory"}
        mock_hist.return_value = {"stale": True, "message": "advisory"}
        mock_cov.return_value = {
            "issues_without_pr": 0,
            "total_issues": 0,
            "missing": [],
        }
        rc = evolution_heartbeat.main()

    assert rc == 0
    mock_create.assert_not_called()
    mock_exists.assert_not_called()


def test_infra597_alert_body_includes_stale_hours():
    """INFRA-597: alert body for a dispatch-failed stale carries the outage duration.

    The duration makes the new alert semantics ('self-heal failed or severe')
    visible in the Linear/GitHub mirror without opening the run log.
    """
    body = evolution_heartbeat._build_alert_body(scanner_stale=True, issues_without_pr=0, scanner_stale_hours=5.8)
    parsed = evolution_heartbeat.extract_recorded_anomalies(body)
    assert parsed == {"scanner_stale"}, "Roundtrip must survive the new suffix"
    assert "5.8h" in body


def test_infra597_severity_threshold_locked():
    """INFRA-597: SCANNER_SEVERE_STALENESS_HOURS must stay well above observed
    transient load-shed gaps (5.8h on 2026-08-28) and below a genuinely dead
    pipeline. Locks the value to force a review if either reality shifts.
    """
    threshold = evolution_heartbeat.SCANNER_SEVERE_STALENESS_HOURS
    assert threshold >= 6, "Must exceed the largest observed transient gap (5.8h)"
    assert threshold <= 24, "A dead pipeline must alert within a day"


# ---------------------------------------------------------------------------
# INFRA-578: off-peak cron minutes (GitHub load-shed avoidance)
# ---------------------------------------------------------------------------


def test_infra578_scan_cron_uses_offpeak_minutes():
    """INFRA-578: evolution-scan cron minutes must avoid :00/:30 peak windows.

    GitHub-hosted scheduled runs at peak minutes get load-shed (dropped, not
    queued). Evidence 2026-08-26: */30 drifted to 55m-139m gaps with whole
    slots dropped after 20:32Z.
    """
    import yaml

    workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "evolution-scan.yml"
    with workflow_path.open() as f:
        data = yaml.safe_load(f)

    on_triggers = data.get("on") or data.get(True)
    cron_entry = on_triggers["schedule"][0].get("cron", "")
    assert cron_entry, "scan workflow must define a cron"

    minute_field = cron_entry.split()[0]
    minutes = {int(m) for part in minute_field.split(",") for m in _expand_cron_part(part)}
    assert minutes, "cron minute field must expand to at least one minute"
    assert not (minutes & {0, 30}), f"Cron minutes must avoid :00/:30 (GitHub peak load-shed), got: {sorted(minutes)}"


def test_infra578_heartbeat_cron_uses_offpeak_minutes():
    """INFRA-578: evolution-heartbeat cron minute must avoid :00 peak window."""
    import yaml

    workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "evolution-heartbeat.yml"
    with workflow_path.open() as f:
        data = yaml.safe_load(f)

    on_triggers = data.get("on") or data.get(True)
    cron_entry = on_triggers["schedule"][0].get("cron", "")
    assert cron_entry, "heartbeat workflow must define a cron"

    minute_field = cron_entry.split()[0]
    minutes = {int(m) for part in minute_field.split(",") for m in _expand_cron_part(part)}
    assert minutes, "cron minute field must expand to at least one minute"
    assert 0 not in minutes, f"Cron minute must avoid :00 (GitHub peak load-shed), got: {sorted(minutes)}"


def _expand_cron_part(part: str) -> list[int]:
    """Expand a single cron minute field component (N, */S, or N-M) to minutes."""
    if "-" in part:
        lo, hi = part.split("-", 1)
        return list(range(int(lo), int(hi) + 1))
    if part.startswith("*/"):
        return list(range(0, 60, int(part[2:])))
    return [int(part)]


# ---------------------------------------------------------------------------
# INFRA-588: heartbeat reverse-watch (scanner → heartbeat self-heal)
# ---------------------------------------------------------------------------


def test_infra588_check_heartbeat_workflow_liveness_alive():
    """INFRA-588: heartbeat ran 1h ago (cron is 2h, threshold 3h) → alive."""
    runs = [_recent_run(1.0, "success")]
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps(runs))
        result = evolution_heartbeat.check_heartbeat_workflow_liveness()

    assert result["alive"] is True


def test_infra588_check_heartbeat_workflow_liveness_stale():
    """INFRA-588: heartbeat last ran 5h ago (> 3h threshold) → stale.

    This is the 2026-08-27 scenario: heartbeat cron slots load-shed for 20+ h
    after healing the scanner, leaving the pipeline unwatched.
    """
    runs = [_recent_run(5.0, "success")]
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps(runs))
        result = evolution_heartbeat.check_heartbeat_workflow_liveness()

    assert result["alive"] is False
    assert "stale" in result["message"].lower()


def test_infra588_check_heartbeat_workflow_liveness_gh_failure():
    """INFRA-588: gh query fails → not alive (fail-safe, no exception)."""
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(returncode=1, stderr="auth error")
        result = evolution_heartbeat.check_heartbeat_workflow_liveness()

    assert result["alive"] is False
    assert "Cannot query" in result["message"]


def test_infra588_liveness_probe_queries_heartbeat_workflow():
    """INFRA-588: the heartbeat probe must query evolution-heartbeat.yml, not the scan workflow."""
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps([_recent_run(0.5, "success")]))
        evolution_heartbeat.check_heartbeat_workflow_liveness()

    cmd = mock_run.call_args[0][0]
    assert "evolution-heartbeat.yml" in cmd, f"Probe must target heartbeat workflow, got: {cmd}"
    assert "evolution-scan.yml" not in cmd


def test_infra588_scanner_liveness_queries_scan_workflow():
    """INFRA-588 regression: shared _check_workflow_liveness must not break scanner probe target."""
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(json.dumps([_recent_run(0.5, "success")]))
        evolution_heartbeat.check_scanner_liveness()

    cmd = mock_run.call_args[0][0]
    assert "evolution-scan.yml" in cmd, f"Scanner probe must target scan workflow, got: {cmd}"
    assert "evolution-heartbeat.yml" not in cmd


def test_infra588_trigger_heartbeat_dispatch_success():
    """INFRA-588: dispatch succeeds → True, correct gh workflow run command."""
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(stdout="", returncode=0)
        ok = evolution_heartbeat.trigger_heartbeat_dispatch()

    assert ok is True
    cmd = mock_run.call_args[0][0]
    assert cmd == ["gh", "workflow", "run", "evolution-heartbeat.yml"]


def test_infra588_trigger_heartbeat_dispatch_failure():
    """INFRA-588: gh workflow run fails → False, no exception escapes."""
    with patch("evolution_heartbeat.subprocess.run") as mock_run:
        mock_run.return_value = _gh_result(returncode=1, stderr="workflow disabled")
        ok = evolution_heartbeat.trigger_heartbeat_dispatch()

    assert ok is False


def test_infra588_trigger_heartbeat_dispatch_timeout():
    """INFRA-588: subprocess timeout → False, no exception escapes."""
    with patch("evolution_heartbeat.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30)):
        ok = evolution_heartbeat.trigger_heartbeat_dispatch()

    assert ok is False


def test_infra588_threshold_covers_cron_drift():
    """INFRA-588: 2h cron + 1h slack threshold (3h) tolerates the observed 2h18m+ drift.

    Locks HEARTBEAT_LIVENESS_THRESHOLD_HOURS so a future edit cannot silently
    shrink it below the cron interval (which would cause perpetual re-dispatch
    loops) or inflate it so far that a dead heartbeat goes unnoticed.
    """
    cron_hours = 2  # evolution-heartbeat.yml: cron '47 */2 * * *'
    threshold = evolution_heartbeat.HEARTBEAT_LIVENESS_THRESHOLD_HOURS
    assert threshold >= cron_hours + 1, f"Threshold must cover cron + 1h drift slack, got {threshold}h"
    assert threshold <= cron_hours * 3, f"Threshold too loose for a 2h cron, got {threshold}h"


def test_infra588_heartbeat_cron_interval_is_two_hours():
    """INFRA-588: heartbeat cron hour field must stay */2 (threshold coupling).

    HEARTBEAT_LIVENESS_THRESHOLD_HOURS=3 assumes a 2h schedule. If the cron
    interval changes, the threshold must be re-derived — this test forces that
    review instead of silently breaking the reverse-watch contract.
    """
    import yaml

    workflow_path = Path(__file__).parent.parent / ".github" / "workflows" / "evolution-heartbeat.yml"
    with workflow_path.open() as f:
        data = yaml.safe_load(f)

    on_triggers = data.get("on") or data.get(True)
    cron_entry = on_triggers["schedule"][0].get("cron", "")
    fields = cron_entry.split()
    assert fields[1] == "*/2", (
        f"Heartbeat cron hour field is '{fields[1]}', expected '*/2'. "
        "HEARTBEAT_LIVENESS_THRESHOLD_HOURS (3h) assumes a 2h interval — update both together."
    )
