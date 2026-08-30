"""Tests for D1 reverse drift watch - VAL-DRF-002, VAL-DRF-003.

Tests the classification of orphan issues (open issues not in current findings):
1. Has merge evidence → grace then close
2. Has session evidence → grace then close
3. No evidence → retain with blocking reason recorded

All tests follow TDD: written before implementation, must fail initially.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path for imports
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from evolution_scanner import Finding

# INFRA-415: shared factory, imported under the original local name so call
# sites stay unchanged.
from tests.drift_watch_helpers import make_issue as _make_issue


def test_val_drf_002_orphan_with_merge_evidence_closes():
    """VAL-DRF-002: Orphan issue with merged PR evidence → grace then close.

    Red evidence: This test will fail because the current implementation doesn't
    explicitly classify and record the decision to close.
    """
    # Setup: One finding exists, one open issue exists with different key
    current_findings = [Finding("RULE_001", "warning", "test", "desc", "file1.py", "ev")]
    open_issues = [
        _make_issue(101, "RULE_001", "file1.py"),  # In findings, not orphan
        _make_issue(102, "RULE_002", "file2.py", linear_linkback="INFRA-123"),  # Orphan with Linear link
    ]

    # Mock: _verify_fix_merged_via_linear returns True (merged PR evidence)
    with (
        patch("evolution_utils._verify_fix_merged_via_linear", return_value=True),
        patch("evolution_utils.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import classify_orphan_issues

        report = classify_orphan_issues(current_findings, open_issues)

        # Should classify issue 102 as CLOSE_READY
        orphan_102 = next((r for r in report if r.issue_number == 102), None)
        assert orphan_102 is not None, "Issue 102 should be classified"
        assert orphan_102.classification == "CLOSE_READY", f"Expected CLOSE_READY, got {orphan_102.classification}"
        assert orphan_102.reason == "merged_pr_verified", (
            f"Expected reason 'merged_pr_verified', got {orphan_102.reason}"
        )


def test_val_drf_002_orphan_with_session_evidence_closes():
    """VAL-DRF-002: Orphan issue with session-completed evidence → grace then close.

    Red evidence: This test will fail because deadlock sentinel path isn't
    explicitly classified.
    """
    current_findings = [Finding("RULE_001", "warning", "test", "desc", "file1.py", "ev")]
    open_issues = [
        _make_issue(
            103,
            "RULE_003",
            "file3.py",
            linear_linkback="INFRA-456",
            deadlock_sentinel="<!-- deadlock-exit INFRA-456 session=abc123 -->",
        ),
    ]

    with (
        patch("evolution_utils._verify_fix_merged_via_linear", return_value=True),
        patch("evolution_utils.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import classify_orphan_issues

        report = classify_orphan_issues(current_findings, open_issues)

        orphan_103 = next((r for r in report if r.issue_number == 103), None)
        assert orphan_103 is not None
        assert orphan_103.classification == "CLOSE_READY"
        assert orphan_103.reason in ["merged_pr_verified", "session_completed_verified"], (
            "Should accept either merge or session evidence"
        )


def test_val_drf_002_orphan_no_evidence_retains_with_reason():
    """VAL-DRF-002: Orphan issue without evidence → retain with blocking reason.

    Red evidence: This test will fail because current implementation only logs
    but doesn't structure the "retain" decision.
    """
    current_findings = [Finding("RULE_001", "warning", "test", "desc", "file1.py", "ev")]
    open_issues = [
        _make_issue(104, "RULE_004", "file4.py", linear_linkback="INFRA-789"),
    ]

    # Mock: verification fails (no evidence)
    with (
        patch("evolution_utils._verify_fix_merged_via_linear", return_value=False),
        patch("evolution_utils.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import classify_orphan_issues

        report = classify_orphan_issues(current_findings, open_issues)

        orphan_104 = next((r for r in report if r.issue_number == 104), None)
        assert orphan_104 is not None
        assert orphan_104.classification == "BLOCKED_NO_EVIDENCE", (
            f"Expected BLOCKED_NO_EVIDENCE, got {orphan_104.classification}"
        )
        assert orphan_104.reason != "", "Must record blocking reason (audit trail requirement)"
        assert "not_verified" in orphan_104.reason or "no_evidence" in orphan_104.reason, (
            f"Reason should indicate lack of evidence, got: {orphan_104.reason}"
        )


def test_val_drf_003_audit_trail_required():
    """VAL-DRF-003: Every orphan issue decision must leave audit trail.

    Red evidence: Current implementation only prints log lines, doesn't
    return structured report.
    """
    current_findings = [Finding("RULE_001", "warning", "test", "desc", "file1.py", "ev")]
    open_issues = [
        _make_issue(105, "RULE_005", "file5.py"),
        _make_issue(106, "RULE_006", "file6.py", linear_linkback="INFRA-111"),
    ]

    with (
        patch("evolution_utils._verify_fix_merged_via_linear", side_effect=[True, False]),
        patch("evolution_utils.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import classify_orphan_issues

        report = classify_orphan_issues(current_findings, open_issues)

        # Must have classification for both orphan issues
        assert len(report) == 2, f"Expected 2 classifications, got {len(report)}"

        # Each must have non-empty reason
        for classification in report:
            assert classification.issue_number in [105, 106]
            assert classification.reason != "", f"Issue {classification.issue_number} must have audit trail reason"
            assert classification.timestamp != "", f"Issue {classification.issue_number} must have timestamp"


def test_val_drf_002_three_reverse_sample_types():
    """Test matrix for three reverse sample types.

    Type 1: Orphan with merge evidence → CLOSE_READY
    Type 2: Orphan with session evidence → CLOSE_READY
    Type 3: Orphan without evidence → BLOCKED_NO_EVIDENCE

    Red evidence: classify_orphan_issues doesn't exist yet.
    """
    current_findings = [Finding("RULE_001", "warning", "test", "desc", "file1.py", "ev")]
    open_issues = [
        # Type 1: Merge evidence
        _make_issue(201, "RULE_201", "file201.py", linear_linkback="INFRA-201"),
        # Type 2: Session evidence
        _make_issue(
            202,
            "RULE_202",
            "file202.py",
            linear_linkback="INFRA-202",
            deadlock_sentinel="<!-- deadlock-exit INFRA-202 -->",
        ),
        # Type 3: No evidence
        _make_issue(203, "RULE_203", "file203.py", linear_linkback="INFRA-203"),
    ]

    with (
        patch("evolution_utils._verify_fix_merged_via_linear", side_effect=[True, True, False]),
        patch("evolution_utils.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import classify_orphan_issues

        report = classify_orphan_issues(current_findings, open_issues)

        # Verify each type
        type1 = next(r for r in report if r.issue_number == 201)
        assert type1.classification == "CLOSE_READY"

        type2 = next(r for r in report if r.issue_number == 202)
        assert type2.classification == "CLOSE_READY"

        type3 = next(r for r in report if r.issue_number == 203)
        assert type3.classification == "BLOCKED_NO_EVIDENCE"
        assert type3.reason != ""


def test_val_drf_003_action_occurs_not_just_alert():
    """VAL-DRF-003: Drift watch must take action, not just alert.

    When orphan issue has evidence, must attempt close (action).
    When orphan issue has no evidence, must record blocking reason (action).

    Red evidence: Current implementation doesn't distinguish between
    "action taken" and "just logged".
    """
    current_findings = [Finding("RULE_001", "warning", "test", "desc", "file1.py", "ev")]
    open_issues = [
        _make_issue(301, "RULE_301", "file301.py", linear_linkback="INFRA-301"),
    ]

    close_attempts = []

    def mock_close_issue(*args, **kwargs):
        close_attempts.append(args[0])
        return MagicMock(returncode=0, stdout="", stderr="")

    with (
        patch("evolution_utils._verify_fix_merged_via_linear", return_value=True),
        patch("evolution_utils.subprocess.run", side_effect=mock_close_issue),
    ):
        from evolution_utils import classify_orphan_issues

        report = classify_orphan_issues(current_findings, open_issues)

        # Must have attempted action (close or record)
        orphan_301 = next(r for r in report if r.issue_number == 301)
        assert orphan_301.action_taken != "", "Must record what action was taken (close attempt or record reason)"


def test_val_drf_002_incremental_no_new_full_scan():
    """VAL-DRF-004: Drift watch uses current tick data, no new full scan.

    The function must accept open_issues as parameter (not fetch them),
    proving incremental implementation.

    Red evidence: Current auto_close_resolved fetches issues internally.
    """
    current_findings = [Finding("RULE_001", "warning", "test", "desc", "file1.py", "ev")]
    open_issues = [
        _make_issue(401, "RULE_401", "file401.py"),
    ]

    with patch("evolution_utils.subprocess.run") as mock_run:
        from evolution_utils import classify_orphan_issues

        classify_orphan_issues(current_findings, open_issues)

        # Should NOT call subprocess.run to fetch issues
        # (it may call it for verification, but not for initial fetch)
        fetch_calls = [
            call
            for call in mock_run.call_args_list
            if "issue" in str(call) and "list" in str(call) and "open" in str(call)
        ]
        assert len(fetch_calls) == 0, "classify_orphan_issues must not fetch issues (incremental requirement)"


def test_b2_fixture_exit_classification():
    """B2 fixture exit classification regression test.

    Issues with fixture-like characteristics (RULE_A-E, file0-4.py, category=test)
    should be classified appropriately by the drift watch.

    Red evidence: No explicit fixture classification exists.
    """
    current_findings = []  # No current findings
    open_issues = [
        # Fixture-like issue
        _make_issue(501, "RULE_A", "file0.py"),
        _make_issue(502, "RULE_B", "file1.py"),
    ]

    with (
        patch("evolution_utils._verify_fix_merged_via_linear", return_value=False),
        patch("evolution_utils.subprocess.run") as mock_run,
    ):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import classify_orphan_issues

        report = classify_orphan_issues(current_findings, open_issues)

        # Fixture issues without evidence should be classified
        assert len(report) == 2
        for classification in report:
            assert classification.issue_number in [501, 502]
            # Should be classified (either CLOSE_READY or BLOCKED)
            assert classification.classification in ["CLOSE_READY", "BLOCKED_NO_EVIDENCE"]
            # Must have reason recorded
            assert classification.reason != ""
