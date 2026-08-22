"""Tests for scripts/check_droid_review.sh jq decision logic.

Validates the fix for the stale-check race condition:
When a stale concluded check (e.g., 'skipped' from draft era) coexists
with a new in-progress review on the same SHA, the poller must NOT
immediately read the stale conclusion. It must return 'pending' until
all check runs are completed.

Bug: run 32435306919/32435603998 — ci-ok read stale 'skipped' while
review was in_progress, causing cancel-on-ci-fail to kill the running
review and creating a merge deadlock.

Fix: The jq expression first checks for any active (non-completed) check
runs. If found, returns 'pending'. Only when all runs are completed does
it read the latest non-cancelled conclusion.
"""

import json
import subprocess
from pathlib import Path

import pytest

# The jq expression extracted from check_droid_review.sh
# This must be kept in sync with the script's actual jq logic.
SCRIPT_PATH = Path(__file__).resolve().parent.parent / "scripts" / "check_droid_review.sh"


def _extract_jq_expression():
    """Extract the jq expression from the script source.

    Returns the raw jq filter string used for check-run decision logic.
    """
    script_text = SCRIPT_PATH.read_text()
    # The jq expression is between the single-quoted delimiters in the
    # STATUS=$(echo "$CHECKS" | jq -r '...') block
    # We search for the block that starts after 'STATUS=$(echo "$CHECKS" | jq -r'
    start_marker = 'STATUS=$(echo "$CHECKS" | jq -r \''
    start_idx = script_text.find(start_marker)
    assert start_idx != -1, "Could not find STATUS jq block in script"
    start_idx += len(start_marker)
    # Find matching closing single-quote — the jq expression ends at
    # the line that contains only "  ')"
    end_marker = "\n  ')"
    end_idx = script_text.find(end_marker, start_idx)
    assert end_idx != -1, "Could not find end of jq expression"
    return script_text[start_idx:end_idx]


def _run_jq(jq_expr: str, check_runs_json: dict) -> str:
    """Run a jq expression against a check-runs API response fixture.

    Returns the stripped stdout string (the decision result).
    """
    payload = json.dumps(check_runs_json)
    result = subprocess.run(
        ["jq", "-r", jq_expr],
        input=payload,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"jq failed: {result.stderr}"
    return result.stdout.strip()


def _make_check_run(status: str, conclusion, started_at: str = "2026-08-21T00:00:00Z"):
    """Helper to build a single check_run entry."""
    return {
        "status": status,
        "conclusion": conclusion,
        "started_at": started_at,
    }


@pytest.fixture
def jq_expr():
    """Extract the jq expression from the script (cached per session)."""
    return _extract_jq_expression()


class TestStaleCheckRaceCondition:
    """Four fixture scenarios for the stale-check race condition."""

    def test_stale_skip_only_returns_skipped(self, jq_expr):
        """Fixture 1: Only a stale concluded 'skipped' check exists.

        Expected: 'skipped' — no active runs, so read the conclusion.
        This is the Dependabot path: when droid-review is skipped,
        the Dependabot exception can allow merge.
        """
        fixture = {
            "total_count": 1,
            "check_runs": [
                _make_check_run("completed", "skipped", "2026-08-21T00:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "skipped"

    def test_stale_skip_plus_inprogress_returns_pending(self, jq_expr):
        """Fixture 2: Stale 'skipped' + new in-progress review.

        Expected: 'pending' — must NOT read stale 'skipped'.
        This is the exact race condition from run 32435306919.
        """
        fixture = {
            "total_count": 2,
            "check_runs": [
                _make_check_run("completed", "skipped", "2026-08-21T00:00:00Z"),
                _make_check_run("in_progress", None, "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "pending"

    def test_inprogress_only_no_concluded_returns_pending(self, jq_expr):
        """Fixture 3: Only in-progress check, no concluded checks.

        Expected: 'pending' — review is running, keep polling.
        """
        fixture = {
            "total_count": 1,
            "check_runs": [
                _make_check_run("in_progress", None, "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "pending"

    def test_latest_success_returns_success(self, jq_expr):
        """Fixture 4: All completed, latest is 'success'.

        Expected: 'success' — normal happy path.
        """
        fixture = {
            "total_count": 1,
            "check_runs": [
                _make_check_run("completed", "success", "2026-08-21T02:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "success"


class TestDualTriggerCancelled:
    """Dual-trigger scenario: one cancelled, one completed."""

    def test_cancelled_plus_success_returns_success(self, jq_expr):
        """When dual triggers create two runs and one is cancelled,
        the non-cancelled conclusion should be returned."""
        fixture = {
            "total_count": 2,
            "check_runs": [
                _make_check_run("completed", "cancelled", "2026-08-21T00:00:00Z"),
                _make_check_run("completed", "success", "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "success"

    def test_cancelled_plus_queued_returns_pending(self, jq_expr):
        """One cancelled (old) + one queued (new) — must wait."""
        fixture = {
            "total_count": 2,
            "check_runs": [
                _make_check_run("completed", "cancelled", "2026-08-21T00:00:00Z"),
                _make_check_run("queued", None, "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "pending"


class TestEdgeCases:
    """Edge cases for the jq decision logic."""

    def test_empty_check_runs_returns_pending(self, jq_expr):
        """No check runs at all → pending (keep polling)."""
        fixture = {"total_count": 0, "check_runs": []}
        assert _run_jq(jq_expr, fixture) == "pending"

    def test_completed_failure_returns_failure(self, jq_expr):
        """All completed, latest is 'failure'."""
        fixture = {
            "total_count": 1,
            "check_runs": [
                _make_check_run("completed", "failure", "2026-08-21T02:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "failure"

    def test_completed_neutral_returns_neutral(self, jq_expr):
        """All completed, latest is 'neutral'."""
        fixture = {
            "total_count": 1,
            "check_runs": [
                _make_check_run("completed", "neutral", "2026-08-21T02:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "neutral"

    def test_stale_failure_plus_inprogress_returns_pending(self, jq_expr):
        """Stale 'failure' + new in-progress review — must wait,
        not immediately report failure."""
        fixture = {
            "total_count": 2,
            "check_runs": [
                _make_check_run("completed", "failure", "2026-08-21T00:00:00Z"),
                _make_check_run("in_progress", None, "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "pending"

    def test_multiple_completed_latest_wins(self, jq_expr):
        """Multiple completed runs (dual trigger), latest non-cancelled wins."""
        fixture = {
            "total_count": 3,
            "check_runs": [
                _make_check_run("completed", "cancelled", "2026-08-21T00:00:00Z"),
                _make_check_run("completed", "failure", "2026-08-21T00:30:00Z"),
                _make_check_run("completed", "success", "2026-08-21T01:00:00Z"),
            ],
        }
        assert _run_jq(jq_expr, fixture) == "success"


class TestActiveCheckGuardStructure:
    """Structural lock: the script must contain an active-check guard.

    This ensures the fix is not accidentally reverted — the script must
    check for non-completed check runs BEFORE reading conclusions.
    """

    def test_script_checks_active_runs_before_conclusion(self):
        """The jq expression must reference .status to detect active runs."""
        jq_expr = _extract_jq_expression()
        # Must contain a check for non-completed status
        assert ".status" in jq_expr, (
            "Script must check .status of check runs to detect active runs "
            "before reading conclusions (stale-check race guard)"
        )
        assert "completed" in jq_expr, (
            "Script must compare .status against 'completed' to identify active (in-progress/queued) check runs"
        )

    def test_script_preserves_cancelled_exclusion(self):
        """The cancelled exclusion must remain for dual-trigger handling."""
        jq_expr = _extract_jq_expression()
        assert "cancelled" in jq_expr, (
            "Script must still exclude 'cancelled' conclusions for dual-trigger race handling"
        )
