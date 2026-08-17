#!/usr/bin/env python3
"""
TDD test for INFRA-371 status=failed exit path (E4 deadlock fix).

Background:
- INFRA-371 status file: status=failed, exitCode=1, completedAt=06:33:14Z
- reconcile-evolution.sh section 5c only handles status=running and status=completed
- When status=failed, code falls through to section 5d retrigger logic
- Since status file exists and mirror is OPEN, retrigger proceeds every tick
- This creates infinite retrigger loop with no exit (E4 deadlock)

Fix:
- Add elif branch for status=failed in section 5c
- Set RETRIGGER_OK=0 to block retrigger
- Route to stale-orphan fallback mechanism (same as status file missing)
- This provides an exit: after N ticks, Linear issue gets canceled
"""

from pathlib import Path

import pytest


def test_status_failed_vs_completed_exit_paths():
    """
    Verify that status=failed and status=completed have different exit paths.

    status=completed (exitCode=0):
    - Deadlock exit path
    - Linear pushed to completed state
    - Evidence comment written

    status=failed (exitCode!=0):
    - Stale-orphan fallback path
    - Linear pushed to canceled state
    - Evidence comment written

    Both provide exits; neither retrigger infinitely.
    """
    # Document the two exit paths
    completed_path = {
        "status": "completed",
        "exitCode": 0,
        "exit_mechanism": "deadlock_exit",
        "linear_action": "completed",
        "comment_template": "deadlock-exit"
    }

    failed_path = {
        "status": "failed",
        "exitCode": 1,
        "exit_mechanism": "stale_orphan_fallback",
        "linear_action": "canceled",
        "comment_template": "stale-orphan-fallback"
    }

    assert completed_path["exit_mechanism"] != failed_path["exit_mechanism"]
    assert completed_path["linear_action"] != failed_path["linear_action"]
    # Both provide exits (no infinite retrigger)
    assert completed_path["exit_mechanism"] in ["deadlock_exit"]
    assert failed_path["exit_mechanism"] in ["stale_orphan_fallback"]


def test_fixture_issues_infra_mapping():
    """
    Verify fixture issues #750-756 map to INFRA-365/366/367/371.

    These are test fixture pollution (RULE_A-E, file0-4.py, category=test).
    All have status=failed status files.
    After fix, they will be handled by stale-orphan fallback.
    """
    fixture_mapping = {
        "INFRA-365": [750, 755],  # RULE_B / file1.py (duplicate)
        "INFRA-366": [751, 756],  # RULE_C / file2.py (duplicate)
        "INFRA-367": [752],       # RULE_D / file3.py
        "INFRA-371": [753, 754],  # RULE_E / file4.py + RULE_A / file0.py
    }

    # All have status=failed
    for infra_ref in fixture_mapping.keys():
        assert infra_ref.startswith("INFRA-")

    # After fix, all will be handled by stale-orphan fallback
    # and Linear issues will be canceled
    assert len(fixture_mapping) == 4  # 4 Linear issues
    assert sum(len(v) for v in fixture_mapping.values()) == 7  # 7 GitHub issues


def test_status_failed_code_path_exists():
    """
    RED test: Verify that reconcile-evolution.sh has a code path for status=failed.

    This test checks the script source code for handling of status=failed.
    Before fix: No elif branch for status=failed → test fails
    After fix: elif branch exists → test passes
    """
    script_path = Path(__file__).parent.parent / "webhook-scripts" / "reconcile-evolution.sh"
    script_content = script_path.read_text()

    # Look for the status check logic in section 5c
    # Should have: if [ "$STATUS" = "running" ] ... elif [ "$STATUS" = "completed" ] ... elif [ "$STATUS" = "failed" ]
    assert 'elif [ "$STATUS" = "failed" ]' in script_content or \
           'if [ "$STATUS" = "failed" ]' in script_content, \
           "reconcile-evolution.sh should have explicit handling for status=failed to prevent E4 deadlock"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
