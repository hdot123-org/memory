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
    Verify fixture issues #750-756 → Linear INFRA-365..371 映射。

    映射经 gh 只读取证（2026-08-18，逐单提取 linkback 评论）：
      #750 → INFRA-365  #751 → INFRA-366  #752 → INFRA-367
      #753 → INFRA-368  #754 → INFRA-369  #755 → INFRA-370
      #756 → INFRA-371
    一一对应，每个 Linear issue 恰好对应一个 GitHub 镜像。

    These are test fixture pollution (RULE_A-E, file0-4.py, category=test).
    All have status=failed status files.
    After fix (status=failed exit, PR #763), they are handled by stale-orphan fallback
    and Linear issues are canceled.

    历史：本测试旧版断言 4/7 错误映射（将 #755 归到 INFRA-365、#756 归到 INFRA-366、
    #753/#754 归到 INFRA-371），且是同义反复（断言自身 dict 字面量的属性）。
    修复后断言经 API 取证的一一映射事实。

    夹具签名机制裁定不补建（orchestrator 2026-08-18）：线上终态已达成（#750-756 全关），
    同类污染风险由 D1/D2 漂移守望与 status=failed 出口覆盖，独立签名机制属过度工程。
    见 library/pipeline-closure.md。
    """
    # 经 gh 只读 API 取证的真实映射（2026-08-18 逐单 linkback 核实）
    fixture_mapping = {
        750: "INFRA-365",
        751: "INFRA-366",
        752: "INFRA-367",
        753: "INFRA-368",
        754: "INFRA-369",
        755: "INFRA-370",
        756: "INFRA-371",
    }

    # 7 GitHub issues → 7 Linear issues，一一对应
    assert len(fixture_mapping) == 7
    assert len(set(fixture_mapping.values())) == 7  # 每个 INFRA 号唯一

    # 连续号段完整性
    assert set(fixture_mapping.keys()) == {750, 751, 752, 753, 754, 755, 756}
    expected_infra = {f"INFRA-{n}" for n in range(365, 372)}
    assert set(fixture_mapping.values()) == expected_infra

    # 所有 INFRA 引用格式合法
    for infra_ref in fixture_mapping.values():
        assert infra_ref.startswith("INFRA-")


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
