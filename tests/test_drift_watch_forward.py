"""Tests for VAL-DRF-001: Forward Drift Watch — positive consistency check.

D2 正向漂移守望: each actionable finding (not suppressed, not in excluded
category) must either have an open issue or a clearly recorded legitimate
reason (quota pending / suppressed / closed-in-window).

Four forward sample categories:
1. Missing issue (ghost) → FAIL condition, no issue and no reason
2. Closed within time window → legitimate reason recorded
3. Suppressed → legitimate reason recorded
4. Quota pending → legitimate reason recorded
"""
import sys
from datetime import datetime
from pathlib import Path

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from evolution_scanner import Finding  # noqa: E402

# Import the forward drift watch functions
from evolution_utils import (
    ForwardDriftRecord,
    forward_drift_watch,
)


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


class TestForwardDriftWatchMatrix:
    """VAL-DRF-001: Four forward sample categories matrix."""

    def test_drf_001_missing_issue_ghost_is_fail(self):
        """VAL-DRF-001: Finding with no open issue and no legitimate reason
        is a ghost — FAIL condition (drift detected, needs remediation)."""
        findings = [_make_finding()]
        open_issue_keys: set[tuple[str, str]] = set()
        suppressed_keys: set[tuple[str, str]] = set()
        closed_window_keys: set[tuple[str, str]] = set()
        quota_exhausted: dict[str, bool] = {}
        excluded_categories: set[str] = set()

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=open_issue_keys,
            suppressed_keys=suppressed_keys,
            closed_window_keys=closed_window_keys,
            quota_exhausted=quota_exhausted,
            issue_excluded_categories=excluded_categories,
        )

        # Ghost finding: no issue, no reason → GHOST status
        assert len(records) == 1
        assert records[0].status == "GHOST"
        assert records[0].finding_key == ("RULE_A", "src/a.py::L10")
        assert "no_issue_no_reason" in records[0].reason

    def test_drf_001_closed_within_window_recorded(self):
        """VAL-DRF-001: Finding deduped against a closed issue within
        DEDUP_CLOSED_WINDOW_DAYS is a legitimate reason (not drift)."""
        findings = [_make_finding()]
        open_issue_keys: set[tuple[str, str]] = set()
        suppressed_keys: set[tuple[str, str]] = set()
        closed_window_keys = {("RULE_A", "src/a.py::L10")}
        quota_exhausted: dict[str, bool] = {}
        excluded_categories: set[str] = set()

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=open_issue_keys,
            suppressed_keys=suppressed_keys,
            closed_window_keys=closed_window_keys,
            quota_exhausted=quota_exhausted,
            issue_excluded_categories=excluded_categories,
        )

        assert len(records) == 1
        assert records[0].status == "CLOSED_IN_WINDOW"
        assert records[0].finding_key == ("RULE_A", "src/a.py::L10")

    def test_drf_001_suppressed_recorded(self):
        """VAL-DRF-001: Finding removed by suppress.json has a legitimate
        reason — not drift."""
        findings = [_make_finding()]
        open_issue_keys: set[tuple[str, str]] = set()
        suppressed_keys = {("RULE_A", "src/a.py::L10")}
        closed_window_keys: set[tuple[str, str]] = set()
        quota_exhausted: dict[str, bool] = {}
        excluded_categories: set[str] = set()

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=open_issue_keys,
            suppressed_keys=suppressed_keys,
            closed_window_keys=closed_window_keys,
            quota_exhausted=quota_exhausted,
            issue_excluded_categories=excluded_categories,
        )

        assert len(records) == 1
        assert records[0].status == "SUPPRESSED"
        assert records[0].finding_key == ("RULE_A", "src/a.py::L10")

    def test_drf_001_quota_pending_recorded(self):
        """VAL-DRF-001: Finding whose category quota was exhausted has a
        legitimate reason — deferred to next tick, not drift."""
        findings = [_make_finding(category="code_quality")]
        open_issue_keys: set[tuple[str, str]] = set()
        suppressed_keys: set[tuple[str, str]] = set()
        closed_window_keys: set[tuple[str, str]] = set()
        quota_exhausted = {"code_quality": True}
        excluded_categories: set[str] = set()

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=open_issue_keys,
            suppressed_keys=suppressed_keys,
            closed_window_keys=closed_window_keys,
            quota_exhausted=quota_exhausted,
            issue_excluded_categories=excluded_categories,
        )

        assert len(records) == 1
        assert records[0].status == "QUOTA_PENDING"
        assert records[0].finding_key == ("RULE_A", "src/a.py::L10")

    def test_drf_001_open_issue_exists_no_drift(self):
        """VAL-DRF-001: Finding with a matching open issue → no drift."""
        findings = [_make_finding()]
        open_issue_keys = {("RULE_A", "src/a.py::L10")}
        suppressed_keys: set[tuple[str, str]] = set()
        closed_window_keys: set[tuple[str, str]] = set()
        quota_exhausted: dict[str, bool] = {}
        excluded_categories: set[str] = set()

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=open_issue_keys,
            suppressed_keys=suppressed_keys,
            closed_window_keys=closed_window_keys,
            quota_exhausted=quota_exhausted,
            issue_excluded_categories=excluded_categories,
        )

        assert len(records) == 1
        assert records[0].status == "ISSUE_EXISTS"

    def test_drf_001_excluded_category_skipped(self):
        """VAL-DRF-001: Findings in excluded categories (daily_audit, etc.)
        are not actionable — skipped entirely."""
        findings = [_make_finding(category="daily_audit")]
        open_issue_keys: set[tuple[str, str]] = set()
        suppressed_keys: set[tuple[str, str]] = set()
        closed_window_keys: set[tuple[str, str]] = set()
        quota_exhausted: dict[str, bool] = {}
        excluded_categories = {"daily_audit"}

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=open_issue_keys,
            suppressed_keys=suppressed_keys,
            closed_window_keys=closed_window_keys,
            quota_exhausted=quota_exhausted,
            issue_excluded_categories=excluded_categories,
        )

        # Excluded category → no record at all
        assert len(records) == 0


class TestForwardDriftWatchDiffList:
    """VAL-DRF-001: Diff list output with classification records."""

    def test_diff_list_empty_when_all_have_issues(self):
        """All actionable findings have open issues → diff list empty."""
        findings = [
            _make_finding("R1", "a.py::L1"),
            _make_finding("R2", "b.py::L2"),
        ]
        open_issue_keys = {("R1", "a.py::L1"), ("R2", "b.py::L2")}

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=open_issue_keys,
            suppressed_keys=set(),
            closed_window_keys=set(),
            quota_exhausted={},
            issue_excluded_categories=set(),
        )

        drift_records = [r for r in records if r.status != "ISSUE_EXISTS"]
        assert len(drift_records) == 0

    def test_diff_list_captures_mixed_findings(self):
        """Mixed matrix: some have issues, some are suppressed, one is ghost."""
        findings = [
            _make_finding("R1", "a.py::L1", category="code_hygiene"),  # has issue
            _make_finding("R2", "b.py::L2", category="code_hygiene"),  # suppressed
            _make_finding("R3", "c.py::L3", category="code_hygiene"),  # ghost (no reason)
            _make_finding("R4", "d.py::L4", category="code_quality"),  # quota
        ]
        open_issue_keys = {("R1", "a.py::L1")}
        suppressed_keys = {("R2", "b.py::L2")}
        closed_window_keys: set[tuple[str, str]] = set()
        quota_exhausted = {"code_quality": True}

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=open_issue_keys,
            suppressed_keys=suppressed_keys,
            closed_window_keys=closed_window_keys,
            quota_exhausted=quota_exhausted,
            issue_excluded_categories=set(),
        )

        status_map = {r.finding_key: r.status for r in records}
        assert status_map[("R1", "a.py::L1")] == "ISSUE_EXISTS"
        assert status_map[("R2", "b.py::L2")] == "SUPPRESSED"
        assert status_map[("R3", "c.py::L3")] == "GHOST"
        assert status_map[("R4", "d.py::L4")] == "QUOTA_PENDING"

    def test_diff_list_includes_timestamp(self):
        """Each record must have an ISO 8601 UTC timestamp (audit trail)."""
        findings = [_make_finding()]
        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=set(),
            suppressed_keys=set(),
            closed_window_keys=set(),
            quota_exhausted={},
            issue_excluded_categories=set(),
        )
        assert records[0].timestamp
        # Verify it's parseable as ISO 8601
        parsed = datetime.fromisoformat(records[0].timestamp)
        assert parsed.tzinfo is not None  # UTC-aware


class TestForwardDriftWatchPriority:
    """Reason priority: if multiple reasons apply, most specific wins."""

    def test_suppressed_takes_priority_over_closed_window(self):
        """If a finding is both suppressed AND closed-in-window, suppressed wins
        (suppression is the primary reason it has no issue)."""
        findings = [_make_finding()]
        suppressed_keys = {("RULE_A", "src/a.py::L10")}
        closed_window_keys = {("RULE_A", "src/a.py::L10")}

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=set(),
            suppressed_keys=suppressed_keys,
            closed_window_keys=closed_window_keys,
            quota_exhausted={},
            issue_excluded_categories=set(),
        )

        assert len(records) == 1
        assert records[0].status == "SUPPRESSED"

    def test_open_issue_takes_priority_over_all(self):
        """If an open issue exists, that's the definitive status regardless
        of other reasons."""
        findings = [_make_finding()]
        open_issue_keys = {("RULE_A", "src/a.py::L10")}
        suppressed_keys = {("RULE_A", "src/a.py::L10")}

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=open_issue_keys,
            suppressed_keys=suppressed_keys,
            closed_window_keys=set(),
            quota_exhausted={},
            issue_excluded_categories=set(),
        )

        assert len(records) == 1
        assert records[0].status == "ISSUE_EXISTS"

    def test_closed_window_takes_priority_over_quota(self):
        """Closed-in-window is more specific than quota pending."""
        findings = [_make_finding(category="code_quality")]
        closed_window_keys = {("RULE_A", "src/a.py::L10")}
        quota_exhausted = {"code_quality": True}

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=set(),
            suppressed_keys=set(),
            closed_window_keys=closed_window_keys,
            quota_exhausted=quota_exhausted,
            issue_excluded_categories=set(),
        )

        assert len(records) == 1
        assert records[0].status == "CLOSED_IN_WINDOW"


class TestForwardDriftWatchActionability:
    """VAL-DRF-001: Only actionable findings are checked."""

    def test_multiple_excluded_categories_all_skipped(self):
        """All excluded categories are skipped."""
        findings = [
            _make_finding("R1", "a.py::L1", category="daily_audit"),
            _make_finding("R2", "b.py::L2", category="evolution_self_audit"),
        ]
        excluded = {"daily_audit", "evolution_self_audit"}

        records = forward_drift_watch(
            findings=findings,
            open_issue_keys=set(),
            suppressed_keys=set(),
            closed_window_keys=set(),
            quota_exhausted={},
            issue_excluded_categories=excluded,
        )

        assert len(records) == 0

    def test_empty_findings_empty_result(self):
        """No findings → no drift records."""
        records = forward_drift_watch(
            findings=[],
            open_issue_keys=set(),
            suppressed_keys=set(),
            closed_window_keys=set(),
            quota_exhausted={},
            issue_excluded_categories=set(),
        )
        assert records == []


class TestForwardDriftRecordDataclass:
    """ForwardDriftRecord dataclass structure."""

    def test_record_has_required_fields(self):
        """Each record must have finding_key, status, reason, timestamp."""
        rec = ForwardDriftRecord(
            finding_key=("R1", "a.py::L1"),
            status="GHOST",
            reason="no_issue_no_reason",
            timestamp="2026-08-18T12:00:00+00:00",
        )
        assert rec.finding_key == ("R1", "a.py::L1")
        assert rec.status == "GHOST"
        assert rec.reason == "no_issue_no_reason"
        assert rec.timestamp == "2026-08-18T12:00:00+00:00"
