"""Tests for evolution heartbeat monitor.

INFRA-213: Tests the scanner liveness check (gh run list) and main() orchestration.
"""

import json
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
    """Scanner stale → exit 1, alert created."""
    runs = [_recent_run(5.0, "success")]
    with (
        patch("evolution_heartbeat.subprocess.run") as mock_run,
        patch("evolution_heartbeat.check_heartbeat_marker") as mock_hb,
        patch("evolution_heartbeat.check_history_freshness") as mock_hist,
        patch("evolution_heartbeat.check_pr_coverage") as mock_cov,
        patch("evolution_heartbeat.alert_issue_exists", return_value=False),
        patch("evolution_heartbeat.create_alert_issue") as mock_create,
        patch("evolution_heartbeat.write_monitor_heartbeat"),
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
    mock_create.assert_called_once_with(scanner_stale=True, issues_without_pr=0)


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
