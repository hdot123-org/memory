"""RED tests for D1 reverse drift watch safety guards (PR #780 droid-review P1).

These tests demonstrate the three safety guards missing from classify_orphan_issues
and execute_orphan_classifications that exist in auto_close_resolved:

1. Self-audit category exemption - evolution_self_audit issues should not be closed
2. Failed categories skip - issues from failed tools should not be closed
3. Partial output fail-closed - when findings count is anomalously low, skip all closing

RED state: These tests FAIL against current code because the safety guards are missing.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts directory to path for imports
scripts_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from evolution_scanner import Finding


def _make_issue(number: int, rule_id: str, location: str,
                linear_linkback: str = "", deadlock_sentinel: str = "",
                category: str = "") -> dict:
    """Create a test issue with optional fields."""
    body = f"**Rule ID**: {rule_id}\n**Location**: {location}"
    if category:
        body += f"\n**Category**: {category}"
    if linear_linkback:
        body += f"\n<!-- linear-linkback {linear_linkback} -->"
    if deadlock_sentinel:
        body += f"\n{deadlock_sentinel}"
    return {"number": number, "body": body}


# ============================================================================
# RED Test 1: Self-audit category exemption
# ============================================================================

def test_p1_safety_self_audit_not_closed():
    """P1 Safety Guard 1: Self-audit issues must NOT be closed by reverse drift watch.

    RED evidence: Without this guard, evolution_self_audit issues get closed prematurely.
    These are transient health signals that resolve when scanner recovers, not when code
    is fixed. Closing them triggers flapping loop with state gate (Gate A).

    This test FAILS against current code (classify_orphan_issues lacks the guard).
    """
    current_findings = []  # No current findings (scanner in bad state)
    open_issues = [
        _make_issue(601, "EVOLUTION_HEARTBEAT_STALE", "heartbeat.py",
                   category="evolution_self_audit",
                   linear_linkback="INFRA-601"),
    ]

    # Mock: _verify_fix_merged_via_linear returns True (would normally close)
    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=True), \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import classify_orphan_issues
        report = classify_orphan_issues(current_findings, open_issues)

        # RED: Without safety guard, issue 601 would be classified as CLOSE_READY
        # and would be closed. With the guard, it should NOT be in the report
        # (skipped entirely, like auto_close_resolved does).
        self_audit_issues = [r for r in report if r.issue_number == 601]

        # FAIL: Current code classifies it as CLOSE_READY
        # PASS: After fix, it should be skipped (not in report)
        assert len(self_audit_issues) == 0, \
            f"RED FAIL: Self-audit issue 601 should be skipped, but got {len(self_audit_issues)} classifications. " \
            "Without this guard, evolution_self_audit issues get closed prematurely (flapping loop)."


# ============================================================================
# RED Test 2: Failed categories skip
# ============================================================================

def test_p1_safety_failed_category_not_closed():
    """P1 Safety Guard 2: Issues from failed audit categories must NOT be closed.

    RED evidence: Without this guard, issues whose category tool failed get closed.
    A failed tool emits no findings, so its issues vanish from current scan even though
    the underlying problem still exists. This causes premature closure.

    This test FAILS against current code (classify_orphan_issues lacks failed_categories param).
    """
    current_findings = []  # No current findings (tool failed, emitted nothing)
    open_issues = [
        _make_issue(602, "RULE_602", "file602.py",
                   category="code_hygiene",  # This tool failed
                   linear_linkback="INFRA-602"),
    ]

    failed_categories = {"code_hygiene"}  # Tool failed this tick

    # Mock: _verify_fix_merged_via_linear returns True (would normally close)
    with patch('evolution_utils._verify_fix_merged_via_linear', return_value=True), \
         patch('evolution_utils.subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        from evolution_utils import classify_orphan_issues

        # RED: Current classify_orphan_issues doesn't accept failed_categories parameter
        # FAIL: TypeError - unexpected keyword argument 'failed_categories'
        # PASS: After fix, it accepts failed_categories and skips issues from failed tools
        try:
            report = classify_orphan_issues(
                current_findings, open_issues,
                failed_categories=failed_categories
            )

            # Should skip issue 602 (category in failed_categories)
            failed_cat_issues = [r for r in report if r.issue_number == 602]
            assert len(failed_cat_issues) == 0, \
                f"RED FAIL: Issue 602 from failed category should be skipped, but got {len(failed_cat_issues)} classifications. " \
                "Without this guard, issues from failed tools get closed prematurely."
        except TypeError as e:
            # RED: Expected failure - function doesn't accept failed_categories yet
            raise AssertionError(
                f"RED FAIL: classify_orphan_issues doesn't accept failed_categories parameter. "
                f"Error: {e}. Without this guard, issues from failed tools get closed prematurely."
            )


# ============================================================================
# RED Test 3: Partial output fail-closed
# ============================================================================

def test_p1_safety_partial_output_skip_all_closing():
    """P1 Safety Guard 3: When findings count is anomalously low, skip all closing.

    RED evidence: Without this guard, when audit tools emit partial output (anomalously
    few findings), the reverse drift watch closes issues based on incomplete data.
    This causes premature closure of issues that still exist.

    This test FAILS against current code (reverse_drift_watch lacks partial output check).
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

    RED evidence: Without the guards, reverse drift watch would close:
    - Self-audit issues (transient health signals)
    - Issues from failed tools (problem still exists)
    - Issues when findings are anomalously low (partial output)

    This test FAILS against current code (all three guards missing).
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

        # RED: Without guards, would close all 3 issues
        # FAIL: Should close 0 (partial output protection)
        try:
            result = reverse_drift_watch(
                current_findings, open_issues,
                history_path=Path("/tmp/test_history.json"),
                failed_categories=failed_categories
            )

            # With all three guards:
            # - 701: Skipped (self-audit)
            # - 702: Skipped (failed category)
            # - 703: Skipped (partial output)
            assert result["closed"] == 0, \
                f"RED FAIL: Should close 0 issues with all guards. Closed {result['closed']}."
        except TypeError as e:
            # RED: Expected failure - reverse_drift_watch doesn't accept failed_categories
            raise AssertionError(
                f"RED FAIL: reverse_drift_watch doesn't accept failed_categories. Error: {e}. "
                "Without all three guards, premature closure occurs."
            )


if __name__ == "__main__":
    # Run tests to demonstrate RED state
    import pytest
    pytest.main([__file__, "-v"])
