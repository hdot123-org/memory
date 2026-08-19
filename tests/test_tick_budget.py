"""Tests for VAL-DRF-004: Tick budget — duration and API call limits.

D3 守望配额与时长: tick 总时长与 gh/Linear API 调用次数上限常量入库；
超限防护（预算耗尽→跳过守望并记录，不 fail tick）。

Budget requirements:
1. TICK_DURATION_BUDGET: max tick duration (seconds, based on baseline median)
2. API_CALL_BUDGET: max gh/Linear API calls per tick
3. Budget exhaustion: skip drift watch operations, log warning, don't fail tick
4. Integration: tick must respect both duration and API budgets
"""
import sys
import time
from pathlib import Path
from unittest.mock import patch

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from evolution_scanner import Finding  # noqa: E402
from evolution_utils import TICK_DURATION_BUDGET, API_CALL_BUDGET, TickBudgetTracker  # noqa: E402


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


class TestTickBudgetConstants:
    """VAL-DRF-004: Budget constants must exist and be reasonable."""

    def test_drf_004_duration_budget_exists(self):
        """TICK_DURATION_BUDGET constant must be defined in seconds."""
        from evolution_utils import TICK_DURATION_BUDGET
        assert isinstance(TICK_DURATION_BUDGET, (int, float))
        assert TICK_DURATION_BUDGET > 0
        # Should be at least 30 seconds, less than 10 minutes
        assert 30 <= TICK_DURATION_BUDGET <= 600

    def test_drf_004_api_call_budget_exists(self):
        """API_CALL_BUDGET constant must be defined."""
        from evolution_utils import API_CALL_BUDGET
        assert isinstance(API_CALL_BUDGET, int)
        assert API_CALL_BUDGET > 0
        # Should be reasonable: at least 10 calls, less than 1000
        assert 10 <= API_CALL_BUDGET <= 1000


class TestTickBudgetTracking:
    """VAL-DRF-004: Budget tracking infrastructure."""

    def test_drf_004_tick_tracker_class_exists(self):
        """TickBudgetTracker class must exist for tracking budget usage."""
        from evolution_utils import TickBudgetTracker
        tracker = TickBudgetTracker()
        assert tracker is not None

    def test_drf_004_tracker_has_duration_budget(self):
        """Tracker must track duration budget."""
        from evolution_utils import TickBudgetTracker
        tracker = TickBudgetTracker()
        assert hasattr(tracker, 'start_time')
        assert hasattr(tracker, 'elapsed_seconds')

    def test_drf_004_tracker_has_api_budget(self):
        """Tracker must track API call budget."""
        from evolution_utils import TickBudgetTracker
        tracker = TickBudgetTracker()
        assert hasattr(tracker, 'api_calls')
        assert tracker.api_calls == 0

    def test_drf_004_tracker_record_api_call(self):
        """Tracker must increment API call counter."""
        from evolution_utils import TickBudgetTracker
        tracker = TickBudgetTracker()
        tracker.record_api_call()
        assert tracker.api_calls == 1
        tracker.record_api_call()
        assert tracker.api_calls == 2

    def test_drf_004_tracker_check_duration_budget(self):
        """Tracker must check if duration budget is exceeded."""
        from evolution_utils import TICK_DURATION_BUDGET, TickBudgetTracker
        tracker = TickBudgetTracker()
        tracker.start()

        # Initially should not be exceeded
        assert not tracker.is_duration_exceeded()

        # Simulate time passing (mock time)
        tracker.start_time = time.time() - TICK_DURATION_BUDGET - 10
        assert tracker.is_duration_exceeded()

    def test_drf_004_tracker_check_api_budget(self):
        """Tracker must check if API budget is exceeded."""
        from evolution_utils import API_CALL_BUDGET, TickBudgetTracker
        tracker = TickBudgetTracker()

        # Initially should not be exceeded
        assert not tracker.is_api_exceeded()

        # Record calls up to budget
        for _ in range(API_CALL_BUDGET):
            tracker.record_api_call()
        assert not tracker.is_api_exceeded()

        # One more call exceeds budget
        tracker.record_api_call()
        assert tracker.is_api_exceeded()

    def test_drf_004_tracker_check_any_budget_exceeded(self):
        """Tracker must check if ANY budget is exceeded."""
        from evolution_utils import API_CALL_BUDGET, TickBudgetTracker
        tracker = TickBudgetTracker()
        tracker.start()

        # Initially no budget exceeded
        assert not tracker.is_any_budget_exceeded()

        # Exceed API budget
        for _ in range(API_CALL_BUDGET + 1):
            tracker.record_api_call()
        assert tracker.is_any_budget_exceeded()


class TestTickBudgetIntegration:
    """VAL-DRF-004: Integration with drift watch operations."""

    def test_drf_004_forward_drift_watch_respects_budget(self):
        """Forward drift watch must skip when budget exceeded."""
        from evolution_utils import API_CALL_BUDGET, TickBudgetTracker
        from evolution_utils import forward_drift_watch

        tracker = TickBudgetTracker()
        # Exhaust API budget
        for _ in range(API_CALL_BUDGET + 1):
            tracker.record_api_call()

        findings = [_make_finding()]
        open_issue_keys = set()
        suppressed_keys = set()
        closed_window_keys = set()
        quota_exhausted = {}
        issue_excluded_categories = set()

        # Should skip and return empty when budget exceeded
        with patch('evolution_utils.get_tick_tracker', return_value=tracker):
            result = forward_drift_watch(
                findings,
                open_issue_keys,
                suppressed_keys,
                closed_window_keys,
                quota_exhausted,
                issue_excluded_categories,
            )
            assert result == []

    def test_drf_004_budget_exhaustion_logged_not_failed(self):
        """Budget exhaustion must log warning but not raise exception."""
        from evolution_utils import API_CALL_BUDGET, TickBudgetTracker
        from evolution_utils import forward_drift_watch

        tracker = TickBudgetTracker()
        # Exhaust API budget
        for _ in range(API_CALL_BUDGET + 1):
            tracker.record_api_call()

        findings = [_make_finding()]

        # Should not raise, just log and return empty
        with patch('evolution_utils.get_tick_tracker', return_value=tracker), \
             patch('builtins.print') as mock_print:
            result = forward_drift_watch(
                findings,
                set(), set(), set(), {}, set()
            )
            assert result == []
            # Should have logged budget exhaustion
            logged_messages = [str(call) for call in mock_print.call_args_list]
            budget_warning = any('budget' in msg.lower() for msg in logged_messages)
            assert budget_warning, f"Expected budget warning in: {logged_messages}"

    def test_drf_004_normal_operation_within_budget(self):
        """Normal drift watch operation should work when within budget."""
        from evolution_utils import TickBudgetTracker
        from evolution_utils import forward_drift_watch

        tracker = TickBudgetTracker()
        # Start tracker but don't exhaust budget
        tracker.start()

        findings = [_make_finding()]

        # Should work normally within budget
        with patch('evolution_utils.get_tick_tracker', return_value=tracker):
            result = forward_drift_watch(
                findings,
                set(), set(), set(), {}, set()
            )
            # Should return records (ghost finding detected)
            assert len(result) > 0
            assert result[0].status == "GHOST"


class TestTickBudgetBaseline:
    """VAL-DRF-004: Budget values based on baseline median."""

    def test_drf_004_duration_budget_reasonable(self):
        """Duration budget should be based on baseline tick duration."""
        from evolution_utils import TICK_DURATION_BUDGET
        # Baseline tick duration is ~30-60 seconds
        # Budget should allow some headroom but not be excessive
        # At least 30s for actual work, but not more than 10min
        assert 30 <= TICK_DURATION_BUDGET <= 600

    def test_drf_004_api_budget_reasonable(self):
        """API budget should be based on baseline API calls."""
        from evolution_utils import API_CALL_BUDGET
        # Baseline tick makes ~20-50 API calls
        # Budget should allow for drift watch overhead but not be excessive
        assert 20 <= API_CALL_BUDGET <= 200
