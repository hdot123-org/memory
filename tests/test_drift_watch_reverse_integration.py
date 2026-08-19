"""Integration tests for D1 reverse drift watch execution layer.

Tests that classify_orphan_issues + execute_orphan_classifications work together
to actually close issues (CLOSE_READY) and record blocking reasons (BLOCKED_NO_EVIDENCE).

These tests verify the action-taking requirement of VAL-DRF-003.

INFRA-403: execute_orphan_classifications now checks each issue's live state
before acting (skip already-closed issues, fail-closed on unknown state), so
the subprocess mocks must serve `gh issue view --json state` responses first.
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path for imports
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from evolution_scanner import Finding
from evolution_utils import (
    OrphanIssueClassification,
    execute_orphan_classifications,
    reverse_drift_watch,
)

from tests.drift_watch_helpers import make_issue as _make_issue


def _gh_ok(stdout: str = "") -> MagicMock:
    return MagicMock(returncode=0, stdout=stdout, stderr="")


def _state_open() -> MagicMock:
    return _gh_ok(json.dumps({"state": "OPEN"}))


def test_execute_close_ready_actually_closes():
    """VAL-DRF-003: CLOSE_READY classification triggers gh issue close.

    Red evidence: execute_orphan_classifications doesn't exist yet.
    """
    # Create a CLOSE_READY classification
    classification = OrphanIssueClassification(
        issue_number=101,
        rule_id="RULE_101",
        location="file101.py",
        classification="CLOSE_READY",
        reason="merged_pr_verified",
        timestamp="2026-01-01T00:00:00Z",
        action_taken="close_attempt"
    )

    with patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.side_effect = [
            _state_open(),  # INFRA-403: live state check
            _gh_ok(),       # close
        ]

        result = execute_orphan_classifications([classification])

        # Verify close was called
        assert result["closed"] == 1, f"Expected 1 closed, got {result['closed']}"

        # Verify subprocess.run was called with gh issue close
        close_calls = [
            c for c in mock_run.call_args_list
            if c[0][0][0:2] == ["gh", "issue"] and c[0][0][2] == "close"
        ]
        assert len(close_calls) == 1, "Should call gh issue close once"
        assert "101" in close_calls[0][0][0], "Should close issue #101"


def test_execute_blocked_records_reason():
    """VAL-DRF-003: BLOCKED_NO_EVIDENCE classification records blocking reason.

    Red evidence: execute_orphan_classifications doesn't exist yet.
    """
    classification = OrphanIssueClassification(
        issue_number=102,
        rule_id="RULE_102",
        location="file102.py",
        classification="BLOCKED_NO_EVIDENCE",
        reason="no_evidence_of_resolution",
        timestamp="2026-01-01T00:00:00Z",
        action_taken="retained_with_reason"
    )

    with patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.side_effect = [
            _state_open(),  # INFRA-403: live state check
            _gh_ok(""),     # INFRA-403: comment scan (no sentinel yet)
            _gh_ok(),       # comment posted
        ]

        result = execute_orphan_classifications([classification])

        # Verify retained
        assert result["retained"] == 1, f"Expected 1 retained, got {result['retained']}"

        # Verify comment was posted (audit trail)
        comment_calls = [
            c for c in mock_run.call_args_list
            if c[0][0][0:2] == ["gh", "issue"] and c[0][0][2] == "comment"
        ]
        assert len(comment_calls) == 1, "Should post comment with blocking reason"
        assert "102" in comment_calls[0][0][0], "Should comment on issue #102"
        # Verify reason is in comment body
        comment_body = comment_calls[0][0][0][-1]  # Last arg is --body
        assert "no_evidence_of_resolution" in comment_body, \
            "Comment must include blocking reason (audit trail)"


def test_execute_respects_grace_period():
    """VAL-DRF-003: CLOSE_READY respects grace period before closing.

    Red evidence: No grace period check in execute layer yet.
    """
    classification = OrphanIssueClassification(
        issue_number=103,
        rule_id="RULE_103",
        location="file103.py",
        classification="CLOSE_READY",
        reason="merged_pr_verified",
        timestamp="2026-01-01T00:00:00Z",
        action_taken="close_attempt"
    )

    with patch('evolution_utils._count_consecutive_absences', return_value=1), \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.side_effect = [
            _state_open(),  # INFRA-403: live state check
        ]

        # history_path provided, but absence count < GRACE_PERIOD_TICKS (3)
        result = execute_orphan_classifications(
            [classification],
            history_path=Path("/tmp/test_history.json")
        )

        # Should defer, not close
        assert result["deferred"] == 1, f"Expected 1 deferred, got {result['deferred']}"
        assert result["closed"] == 0, "Should not close before grace period"

        # Verify no close call
        close_calls = [
            c for c in mock_run.call_args_list
            if c[0][0][0:2] == ["gh", "issue"] and c[0][0][2] == "close"
        ]
        assert len(close_calls) == 0, "Should not call gh issue close"


def test_reverse_drift_watch_end_to_end():
    """VAL-DRF-002/003: Full pipeline classifies and executes.

    Red evidence: reverse_drift_watch doesn't exist yet.
    """
    current_findings = [Finding("RULE_001", "warning", "test", "desc", "file1.py", "ev")]
    open_issues = [
        _make_issue(201, "RULE_201", "file201.py", linear_linkback="INFRA-201"),
        _make_issue(202, "RULE_202", "file202.py", linear_linkback="INFRA-202"),
    ]

    with patch('evolution_utils._verify_fix_merged_via_linear', side_effect=[True, False]), \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.side_effect = [
            _state_open(),  # INFRA-403: state check 201
            _gh_ok(),       # close 201
            _state_open(),  # INFRA-403: state check 202
            _gh_ok(""),     # INFRA-403: comment scan 202 (no sentinel yet)
            _gh_ok(),       # comment 202
        ]

        result = reverse_drift_watch(current_findings, open_issues)

        # Should have 1 closed (201 with merge evidence) and 1 retained (202 no evidence)
        assert result["closed"] == 1, f"Expected 1 closed, got {result['closed']}"
        assert result["retained"] == 1, f"Expected 1 retained, got {result['retained']}"

        # Verify both actions occurred
        close_calls = [c for c in mock_run.call_args_list if c[0][0][2] == "close"]
        comment_calls = [c for c in mock_run.call_args_list if c[0][0][2] == "comment"]

        assert len(close_calls) == 1, "Should close issue 201"
        assert len(comment_calls) == 1, "Should comment on issue 202"


def test_reverse_drift_watch_incremental_proof():
    """VAL-DRF-004: reverse_drift_watch doesn't fetch issues (incremental).

    Red evidence: Current implementation fetches issues internally.
    """
    current_findings = [Finding("RULE_001", "warning", "test", "desc", "file1.py", "ev")]
    open_issues = [
        _make_issue(301, "RULE_301", "file301.py"),
    ]

    with patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = _gh_ok()

        reverse_drift_watch(current_findings, open_issues)

        # Verify no issue list fetch
        fetch_calls = [
            c for c in mock_run.call_args_list
            if c[0][0][0:2] == ["gh", "issue"] and c[0][0][2] == "list"
        ]
        assert len(fetch_calls) == 0, "reverse_drift_watch must not fetch issues"


def test_b2_fixture_integration():
    """B2 fixture exit classification integration test.

    Fixture-like issues (RULE_A-E, file0-4.py) without evidence should be
    retained with blocking reason recorded.

    Red evidence: No integration between B2 fixtures and D1 reverse watch.
    """
    current_findings = []  # No current findings
    open_issues = [
        _make_issue(401, "RULE_A", "file0.py"),
        _make_issue(402, "RULE_B", "file1.py"),
        _make_issue(403, "RULE_C", "file2.py"),
    ]

    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=False), \
         patch('evolution_utils.subprocess.run') as mock_run:
        # Per blocked issue: state check, comment scan (empty), comment post
        mock_run.side_effect = [
            _state_open(), _gh_ok(""), _gh_ok(),
            _state_open(), _gh_ok(""), _gh_ok(),
            _state_open(), _gh_ok(""), _gh_ok(),
        ]

        result = reverse_drift_watch(current_findings, open_issues)

        # All should be retained (no evidence)
        assert result["retained"] == 3, f"Expected 3 retained, got {result['retained']}"
        assert result["closed"] == 0, "Should not close without evidence"

        # Verify comments posted for all
        comment_calls = [c for c in mock_run.call_args_list if c[0][0][2] == "comment"]
        assert len(comment_calls) == 3, "Should post comment for each retained issue"
