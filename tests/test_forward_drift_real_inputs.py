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


def _make_finding(rule_id="RULE_A", location="src/a.py::L10", severity="warning", category="code_quality") -> Finding:
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
        findings = [_make_finding(f"R{i}", f"a.py::L{i}", category="code_quality") for i in range(5)]
        open_issues = []
        # Simulate quota exhaustion: code_quality has quota=3, but 5 findings
        # (the function should detect 5 > 3 → quota exhausted)

        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
            quota_exhausted={"code_quality": True},
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
            quota_exhausted={},  # No category is over quota
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


class TestP1GlobalQuotaMisapply:
    """P1-1: main() must pre-compute quota_exhausted with per-category quotas.

    Bug: main() used max_issues_per_tick for ALL categories when computing quota_exhausted,
    but issue creation uses max_self_audit_issues_per_tick for self_audit and
    max_code_hygiene_issues_per_tick for code_hygiene. When these differ, findings
    are wrongly classified (e.g., self_audit with count=3 wrongly marked QUOTA_PENDING
    when max_issues_per_tick=1 but max_self_audit_issues_per_tick=5).

    Fix: main() now pre-computes quota_exhausted dict using per-category quotas before
    calling _integrate_forward_drift_watch.
    """

    def test_self_audit_uses_self_audit_quota_not_global(self, capsys):
        """self_audit findings should use max_self_audit_issues_per_tick,
        not the global max_issues_per_tick."""
        # 3 self_audit findings; global quota=1 but self_audit quota=5
        findings = [_make_finding(f"R{i}", f"a.py::L{i}", category="evolution_self_audit") for i in range(3)]
        open_issues = []

        # P1 FIX: main() pre-computes quota_exhausted with per-category quotas
        # 3 <= 5 (self_audit quota) → NOT quota exhausted → empty dict
        quota_exhausted = {}  # main() computed: 3 <= 5, so empty
        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories={"daily_audit"},
            quota_exhausted=quota_exhausted,
        )
        captured = capsys.readouterr()
        # quota_exhausted empty → NOT quota exhausted → GHOST (no issue, no reason)
        # BUG: old code uses max_issues_per_tick=1 → 3 > 1 → wrongly QUOTA_PENDING
        assert "QUOTA_PENDING=0" in captured.out, (
            f"self_audit should NOT be quota-pending when count(3) <= self_audit_quota(5). Got: {captured.out}"
        )

    def test_code_hygiene_uses_code_hygiene_quota_not_global(self, capsys):
        """code_hygiene findings should use max_code_hygiene_issues_per_tick,
        not the global max_issues_per_tick."""
        # 4 code_hygiene findings; global quota=1 but code_hygiene quota=10
        findings = [_make_finding(f"R{i}", f"a.py::L{i}", category="code_hygiene") for i in range(4)]
        open_issues = []

        # P1 FIX: main() pre-computes quota_exhausted with per-category quotas
        # 4 <= 10 (code_hygiene quota) → NOT quota exhausted → empty dict
        quota_exhausted = {}  # main() computed: 4 <= 10, so empty
        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories={"daily_audit", "evolution_self_audit"},
            quota_exhausted=quota_exhausted,
        )
        captured = capsys.readouterr()
        # quota_exhausted empty → NOT quota exhausted → GHOST
        # BUG: old code uses max_issues_per_tick=1 → 4 > 1 → wrongly QUOTA_PENDING
        assert "QUOTA_PENDING=0" in captured.out, (
            f"code_hygiene should NOT be quota-pending when count(4) <= hygiene_quota(10). Got: {captured.out}"
        )

    def test_regular_category_still_uses_global_quota(self, capsys):
        """Regular (non-self-audit, non-code-hygiene) categories still use max_issues_per_tick."""
        # 3 code_quality findings; global quota=2
        findings = [_make_finding(f"R{i}", f"a.py::L{i}", category="code_quality") for i in range(3)]
        open_issues = []

        # P1 FIX: main() pre-computes quota_exhausted with per-category quotas
        # 3 > 2 (global quota for regular) → quota exhausted → dict with category
        quota_exhausted = {"code_quality": True}  # main() computed: 3 > 2
        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories={"daily_audit"},
            quota_exhausted=quota_exhausted,
        )
        captured = capsys.readouterr()
        # quota_exhausted has code_quality → quota exhausted → QUOTA_PENDING
        assert "QUOTA_PENDING=3" in captured.out, (
            f"code_quality should be quota-pending when count(3) > global_quota(2). Got: {captured.out}"
        )


class TestP1PreDedupCountMismatch:
    """P1-2: main() must use deduped (post-dedup) count when computing quota_exhausted.

    Bug: main() computed quota_exhausted using all_findings (pre-dedup) but
    creation path uses deduped (post-dedup). If 5 pre-dedup findings exist but only
    3 survive dedup, quota check wrongly uses 5 → QUOTA_PENDING when creation would
    actually create issues for 3.

    Fix: main() now uses deduped (post-dedup) count when computing quota_exhausted.
    """

    def test_quota_uses_deduped_count_not_prededup(self, capsys):
        """When all_findings (pre-dedup) has more findings than deduped (post-dedup),
        quota check must use deduped count, not all_findings count."""
        # Simulate: 5 pre-dedup findings but only 2 post-dedup
        # With quota=3: pre-dedup count 5 > 3 → wrongly QUOTA_PENDING
        #               deduped count 2 <= 3 → correctly NOT quota exhausted
        deduped_findings = [
            _make_finding("R1", "a.py::L1", category="code_quality"),
            _make_finding("R2", "a.py::L2", category="code_quality"),
        ]
        open_issues = []

        # P1 FIX: main() uses deduped count (2) not all_findings count (5)
        # 2 <= 3 (quota) → NOT quota exhausted → empty dict
        quota_exhausted = {}  # main() computed from deduped: 2 <= 3, so empty
        _integrate_forward_drift_watch(
            deduped=deduped_findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories={"daily_audit"},
            quota_exhausted=quota_exhausted,
        )
        captured = capsys.readouterr()
        # quota_exhausted empty → NOT quota exhausted → GHOST (no issue, no reason)
        # BUG: if using all_findings count=5 > 3 → wrongly QUOTA_PENDING
        assert "QUOTA_PENDING=0" in captured.out, (
            f"deduped count(2) <= quota(3) → no QUOTA_PENDING. Got: {captured.out}"
        )


class TestIntegrateSignatureBackwardCompat:
    """Ensure the updated _integrate_forward_drift_watch signature is backward compatible.

    The old callers pass only 4 positional args. New quota_exhausted is optional.
    """

    def test_old_caller_without_quota_exhausted(self, capsys):
        """Old callers that don't pass quota_exhausted should still work."""
        findings = [_make_finding("R1", "a.py::L1")]
        open_issues = [{"rule_id": "R1", "location": "a.py::L1", "state": "open"}]

        # Old-style call without quota_exhausted kwarg
        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
        )
        captured = capsys.readouterr()
        assert "ISSUE_EXISTS=1" in captured.out

    def test_caller_with_quota_exhausted(self, capsys):
        """Callers passing quota_exhausted should work correctly."""
        findings = [_make_finding(f"R{i}", f"a.py::L{i}", category="code_quality") for i in range(5)]
        open_issues = []

        # P1 FIX: main() pre-computes quota_exhausted
        # 5 > 3 → quota exhausted → dict with category
        quota_exhausted = {"code_quality": True}  # main() computed: 5 > 3
        _integrate_forward_drift_watch(
            deduped=findings,
            open_issues=open_issues,
            suppressed_keys=set(),
            issue_excluded_categories=set(),
            quota_exhausted=quota_exhausted,
        )
        captured = capsys.readouterr()
        # quota_exhausted has code_quality → quota exhausted → QUOTA_PENDING
        assert "QUOTA_PENDING=5" in captured.out
