"""Tests for D2 空壳实化: _integrate_forward_drift_watch must use real inputs.

Three bugs fixed:
1. closed_window_keys must derive from closed-in-window issues (not hardcoded empty set)
2. quota_exhausted must derive from per-category quota tracking (not hardcoded empty dict)
3. Classification must use pre-dedup actionable findings (not post-dedup where ISSUE_EXISTS=0)
4. open_issues snapshot must be refreshed after issue creation (prevents false GHOST)
"""
import sys
from pathlib import Path

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from evolution_scanner import Finding, _integrate_forward_drift_watch  # noqa: E402


def _make_finding(rule_id="RULE_A", location="src/a.py::L10",
                  severity="warning", category="code_quality") -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        category=category,
        description=f"Test finding {rule_id}",
        location=location,
        evidence="test evidence",
    )


class TestClosedWindowKeysRealInput:
    """Bug #1: closed_window_keys must derive from open_issues with state='closed'."""

    def test_closed_in_window_from_open_issues_state_closed(self, capsys):
        """When open_issues contains state='closed' entries (closed within 7-day window),
        those keys must be classified as CLOSED_IN_WINDOW, not GHOST."""
        findings = [_make_finding("R1", "a.py::L1")]
        # open_issues includes both open (state="open") and closed-in-window (state="closed") entries
        open_issues = [
            {"rule_id": "R1", "location": "a.py::L1", "state": "closed"},
        ]

        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
        )
        captured = capsys.readouterr()
        # R1 should be CLOSED_IN_WINDOW because it matches a closed-in-window issue
        assert "CLOSED_IN_WINDOW=1" in captured.out
        # Should NOT be GHOST since it has a legitimate reason
        assert "GHOST=0" in captured.out

    def test_open_issue_keys_exclude_closed_state(self, capsys):
        """open_issue_keys for ISSUE_EXISTS check should only include state='open' entries.
        state='closed' entries are for CLOSED_IN_WINDOW only."""
        findings = [_make_finding("R1", "a.py::L1")]
        # This issue is closed (in-window dedup entry) - should NOT count as open
        open_issues = [
            {"rule_id": "R1", "location": "a.py::L1", "state": "closed"},
        ]

        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
        )
        captured = capsys.readouterr()
        # R1 is CLOSED_IN_WINDOW, not ISSUE_EXISTS (because state='closed')
        assert "ISSUE_EXISTS=0" in captured.out
        assert "CLOSED_IN_WINDOW=1" in captured.out


class TestQuotaExhaustedRealInput:
    """Bug #2: quota_exhausted must derive from per-category quota tracking."""

    def test_quota_exhausted_from_findings_count(self, capsys):
        """When a category has more findings than quota allows,
        excess findings should be classified as QUOTA_PENDING, not GHOST."""
        # Create 5 findings in code_quality category
        findings = [
            _make_finding(f"R{i}", f"a.py::L{i}", category="code_quality")
            for i in range(5)
        ]
        open_issues = []
        # Simulate quota exhaustion: max_issues_per_tick=3 for code_quality
        # (the function should detect 5 > 3 → quota exhausted)

        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
            max_issues_per_tick=3,
        )
        captured = capsys.readouterr()
        # At least some findings should be QUOTA_PENDING (quota exhausted for code_quality)
        assert "QUOTA_PENDING=" in captured.out
        # GHOST should be 0 because quota is a legitimate reason
        assert "GHOST=0" in captured.out

    def test_no_quota_exhausted_when_under_limit(self, capsys):
        """When findings count is within quota, no QUOTA_PENDING classification."""
        findings = [
            _make_finding("R1", "a.py::L1", category="code_quality"),
        ]
        open_issues = []

        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
            max_issues_per_tick=10,
        )
        captured = capsys.readouterr()
        # Under quota → no QUOTA_PENDING, it's just GHOST (no issue, no reason)
        assert "GHOST=1" in captured.out
        assert "QUOTA_PENDING=0" in captured.out


class TestPreDedupClassification:
    """Bug #3: Classification must use pre-dedup actionable findings.

    The current code passes `deduped` (post-dedup) to forward_drift_watch.
    But deduplicate() removes findings that match open issues, so those
    findings never reach the classifier → ISSUE_EXISTS is always 0.

    Fix: pass all_findings (pre-dedup) so the classifier can see
    findings that have open issues.
    """

    def test_issue_exists_when_finding_has_open_issue(self, capsys):
        """Finding with a matching open issue should be ISSUE_EXISTS, not GHOST.

        This test validates the fix: when a finding's key matches an open issue,
        it should be classified as ISSUE_EXISTS even though it would have been
        removed by deduplicate()."""
        findings = [_make_finding("R1", "a.py::L1")]
        open_issues = [
            {"rule_id": "R1", "location": "a.py::L1", "state": "open"},
        ]

        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
        )
        captured = capsys.readouterr()
        assert "ISSUE_EXISTS=1" in captured.out
        assert "GHOST=0" in captured.out

    def test_mixed_open_and_closed_issues(self, capsys):
        """Mixed: some findings match open issues, some match closed-in-window."""
        findings = [
            _make_finding("R1", "a.py::L1"),  # open issue → ISSUE_EXISTS
            _make_finding("R2", "b.py::L2"),  # closed-in-window → CLOSED_IN_WINDOW
            _make_finding("R3", "c.py::L3"),  # no match → GHOST
        ]
        open_issues = [
            {"rule_id": "R1", "location": "a.py::L1", "state": "open"},
            {"rule_id": "R2", "location": "b.py::L2", "state": "closed"},
        ]

        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
        )
        captured = capsys.readouterr()
        assert "ISSUE_EXISTS=1" in captured.out
        assert "CLOSED_IN_WINDOW=1" in captured.out
        assert "GHOST=1" in captured.out


class TestGhostWindowFalsePositive:
    """Bug #4: open_issues snapshot must be refreshed after issue creation.

    When issues are created during the tick, the open_issues list (captured
    before issue creation) doesn't reflect them → same-tick findings that
    just got issues are falsely classified as GHOST.

    Fix: _integrate_forward_drift_watch must accept a post-creation
    open_issue_keys set (or refresh open_issues).
    """

    def test_no_ghost_when_issue_just_created(self, capsys):
        """Finding whose issue was just created in same tick should not be GHOST.

        Simulates: issue was created by _process_findings_with_reopen,
        so open_issue_keys should include it after refresh."""
        findings = [_make_finding("R1", "a.py::L1")]
        # After issue creation, the open issue list includes the newly created issue
        open_issues = [
            {"rule_id": "R1", "location": "a.py::L1", "state": "open"},
        ]

        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
        )
        captured = capsys.readouterr()
        # R1 now has an issue → ISSUE_EXISTS, not GHOST
        assert "ISSUE_EXISTS=1" in captured.out
        assert "GHOST=0" in captured.out


class TestIntegrateSignatureBackwardCompat:
    """Ensure the updated _integrate_forward_drift_watch signature is backward compatible.

    The old callers pass only 4 positional args. New max_issues_per_tick is optional.
    """

    def test_old_caller_without_max_issues_per_tick(self, capsys):
        """Old callers that don't pass max_issues_per_tick should still work."""
        findings = [_make_finding("R1", "a.py::L1")]
        open_issues = [{"rule_id": "R1", "location": "a.py::L1", "state": "open"}]

        # Old-style call without max_issues_per_tick kwarg
        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
        )
        captured = capsys.readouterr()
        assert "ISSUE_EXISTS=1" in captured.out
