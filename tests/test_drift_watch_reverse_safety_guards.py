"""Safety guard tests for D1 reverse drift watch (PR #780 droid-review P1, PR #817).

These tests cover the three safety guards aligned with auto_close_resolved:

1. Self-audit category exemption - evolution_self_audit issues should not be closed
2. Failed categories skip - issues from failed tools should not be closed
3. Partial output fail-closed - when findings count is anomalously low, skip all closing

INFRA-403 (PR #819) superseded the PR #817 silent-skip semantics: protected issues
are now classified BLOCKED_NO_EVIDENCE with an audit trail (visible in the report)
instead of being silently dropped. The safety property is unchanged — neither guard
path ever closes the protected issue. Tests 1/2 below assert the BLOCKED semantics.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path for imports
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

# INFRA-415: shared factory (superset variant with category field folded in),
# imported under the original local name so call sites stay unchanged.
from tests.drift_watch_helpers import make_issue as _make_issue

# ============================================================================
# Test 1: Self-audit category exemption
# ============================================================================

def test_p1_safety_self_audit_not_closed():
    """P1 Safety Guard 1: Self-audit issues must NOT be closed by reverse drift watch.

    evolution_self_audit issues are transient health signals that resolve when
    scanner recovers, not when code is fixed. Closing them triggers flapping loop
    with state gate (Gate A).

    INFRA-403 semantics: the issue is classified BLOCKED_NO_EVIDENCE (visible in
    the report with an audit trail), never CLOSE_READY — so it is never closed.
    """
    current_findings = []  # No current findings (scanner in bad state)
    open_issues = [
        _make_issue(601, "EVOLUTION_HEARTBEAT_STALE", "heartbeat.py",
                   category="evolution_self_audit",
                   linear_linkback="INFRA-601"),
    ]

    # Mock: _verify_fix_merged_via_linear returns True (would normally close)
    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=True) as mock_verify, \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import classify_orphan_issues
        report = classify_orphan_issues(current_findings, open_issues)

        # Self-audit issue must never be CLOSE_READY (would be closed).
        # INFRA-403: it is classified BLOCKED_NO_EVIDENCE with audit trail.
        self_audit_issues = [r for r in report if r.issue_number == 601]

        assert len(self_audit_issues) == 1, \
            "Self-audit issue 601 should be classified BLOCKED_NO_EVIDENCE with audit trail"
        assert self_audit_issues[0].classification == "BLOCKED_NO_EVIDENCE", \
            f"Self-audit issue 601 classified {self_audit_issues[0].classification}; " \
            "closing it triggers the Gate A flapping loop. Must be BLOCKED_NO_EVIDENCE."
        # Verification must not even run — protection is decided before evidence check
        mock_verify.assert_not_called()


# ============================================================================
# Test 2: Failed categories skip
# ============================================================================

def test_p1_safety_failed_category_not_closed():
    """P1 Safety Guard 2: Issues from failed audit categories must NOT be closed.

    A failed tool emits no findings, so its issues vanish from current scan even
    though the underlying problem may still exist. Closing them is premature.

    INFRA-403 semantics: the issue is classified BLOCKED_NO_EVIDENCE (visible in
    the report with an audit trail), never CLOSE_READY — so it is never closed.
    """
    current_findings = []  # No current findings (tool failed, emitted nothing)
    open_issues = [
        _make_issue(602, "RULE_602", "file602.py",
                   category="code_hygiene",  # This tool failed
                   linear_linkback="INFRA-602"),
    ]

    failed_categories = {"code_hygiene"}  # Tool failed this tick

    # Mock: _verify_fix_merged_via_linear returns True (would normally close)
    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=True) as mock_verify, \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import classify_orphan_issues
        report = classify_orphan_issues(
            current_findings, open_issues,
            failed_categories=failed_categories
        )

        # Failed-category issue must never be CLOSE_READY (would be closed).
        # INFRA-403: it is classified BLOCKED_NO_EVIDENCE with audit trail.
        failed_cat_issues = [r for r in report if r.issue_number == 602]

        assert len(failed_cat_issues) == 1, \
            "Issue 602 from failed category should be classified BLOCKED_NO_EVIDENCE with audit trail"
        assert failed_cat_issues[0].classification == "BLOCKED_NO_EVIDENCE", \
            f"Issue 602 classified {failed_cat_issues[0].classification}; " \
            "a failed tool emits no findings, absence is not resolution. Must be BLOCKED_NO_EVIDENCE."
        # Verification must not even run — protection is decided before evidence check
        mock_verify.assert_not_called()


# ============================================================================
# Test 3: Partial output fail-closed
# ============================================================================

def test_p1_safety_partial_output_skip_all_closing():
    """P1 Safety Guard 3: When findings count is anomalously low, skip all closing.

    When audit tools emit partial output (anomalously few findings), the reverse
    drift watch must not close issues based on incomplete data — that would cause
    premature closure of issues that still exist.
    """
    current_findings = []  # Anomalously low (tool crashed, emitted nothing)
    open_issues = [
        _make_issue(603, "RULE_603", "file603.py", linear_linkback="INFRA-603"),
        _make_issue(604, "RULE_604", "file604.py", linear_linkback="INFRA-604"),
    ]

    # Mock history with high baseline (recent snapshots had many findings)
    mock_history_data = {
        "snapshots": [
            {"findings": [{"rule_id": f"R{i}", "location": f"f{i}"} for i in range(10)]}
            for _ in range(5)
        ]
    }

    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=True), \
         patch('evolution_utils.subprocess.run') as mock_run, \
         patch('evolution_utils.load_history', return_value=mock_history_data):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import reverse_drift_watch

        # RED: Current reverse_drift_watch doesn't check for partial output
        # It will attempt to close all orphan issues based on incomplete findings
        # FAIL: Should detect partial output and skip all closing
        result = reverse_drift_watch(
            current_findings, open_issues,
            history_path=Path("/tmp/test_history.json")
        )

        # With partial output protection, should NOT close any issues
        # because findings count (0) is below 80% of baseline median (10)
        assert result["closed"] == 0, \
            f"RED FAIL: Should not close any issues when findings count ({len(current_findings)}) " \
            f"is below 80% of baseline median (10). Closed {result['closed']} issues. " \
            "Without this guard, partial output causes premature closure."


# ============================================================================
# Combined test: All three guards together
# ============================================================================

def test_p1_safety_all_three_guards_combined():
    """P1 Combined: All three safety guards work together.

    Without the guards, reverse drift watch would close:
    - Self-audit issues (transient health signals)
    - Issues from failed tools (problem still exists)
    - Issues when findings are anomalously low (partial output)
    """
    current_findings = []  # Anomalously low
    open_issues = [
        _make_issue(701, "HEARTBEAT_STALE", "hb.py",
                   category="evolution_self_audit",
                   linear_linkback="INFRA-701"),
        _make_issue(702, "RULE_702", "f702.py",
                   category="code_hygiene",
                   linear_linkback="INFRA-702"),
        _make_issue(703, "RULE_703", "f703.py",
                   linear_linkback="INFRA-703"),
    ]

    failed_categories = {"code_hygiene"}
    mock_history_data = {
        "snapshots": [
            {"findings": [{"rule_id": f"R{i}"} for i in range(10)]}
            for _ in range(5)
        ]
    }

    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=True), \
         patch('evolution_utils.subprocess.run') as mock_run, \
         patch('evolution_utils.load_history', return_value=mock_history_data):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import reverse_drift_watch

        result = reverse_drift_watch(
            current_findings, open_issues,
            history_path=Path("/tmp/test_history.json"),
            failed_categories=failed_categories
        )

        # With all three guards active (partial output short-circuits first):
        # - 701/702/703: none closed
        assert result["closed"] == 0, \
            f"Should close 0 issues with all guards. Closed {result['closed']}."


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
