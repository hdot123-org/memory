"""Tests for scripts/auto_merge_triage.sh (auto-merge blind-spot triage).

Three blind-spot forms (scrutiny r1/r2 + 编排器增补 2026-08-19):
1. CONFLICTING: PR silently skipped, no notification (#794 停滞 11h+)
2. BEHIND + all green: needs update-branch self-heal (#814/#819/#825/#827/#828)
3. Early-fire + no re-trigger: schedule sweep should catch BEHIND PRs

Contract:
- Input: gh pr list --json number,mergeable,mergeStateStatus,statusCheckRollup JSON
- Output: JSON triage result with classified PRs + actions
- Exit 0 always (triage never fails the workflow)
- No side effects (pure classification + command generation)
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


def get_script_path() -> Path:
    """Get path to auto_merge_triage.sh script."""
    return Path(__file__).parent.parent / "scripts" / "auto_merge_triage.sh"


class TestAutoMergeTriage:
    """Triage classification tests."""

    def test_script_exists_and_executable(self):
        """Script exists and is executable."""
        script = get_script_path()
        assert script.exists(), f"{script} not found"
        assert os.access(script, os.X_OK), f"{script} not executable"

    def test_empty_input_returns_empty(self):
        """Empty PR list → empty triage result."""
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input="[]",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output == {"mergeable": [], "behind": [], "conflicting": [], "unknown": []}

    def test_mergeable_pr_classified(self):
        """PR with mergeable=MERGEABLE → mergeable list."""
        prs = [{"number": 123, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["mergeable"]) == 1
        assert output["mergeable"][0]["number"] == 123
        assert output["behind"] == []
        assert output["conflicting"] == []

    def test_behind_pr_classified(self):
        """PR with mergeStateStatus=BEHIND → behind list."""
        prs = [{"number": 456, "mergeable": "MERGEABLE", "mergeStateStatus": "BEHIND"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["behind"]) == 1
        assert output["behind"][0]["number"] == 456
        assert output["mergeable"] == []

    def test_conflicting_pr_classified(self):
        """PR with mergeable=CONFLICTING → conflicting list."""
        prs = [{"number": 789, "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["conflicting"]) == 1
        assert output["conflicting"][0]["number"] == 789
        assert output["mergeable"] == []
        assert output["behind"] == []

    def test_unknown_state_classified(self):
        """PR with mergeable=UNKNOWN → unknown list."""
        prs = [{"number": 101, "mergeable": "UNKNOWN", "mergeStateStatus": "UNKNOWN"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["unknown"]) == 1
        assert output["unknown"][0]["number"] == 101

    def test_mixed_prs_classified(self):
        """Mixed PRs → correct classification into all categories."""
        prs = [
            {"number": 1, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"},
            {"number": 2, "mergeable": "MERGEABLE", "mergeStateStatus": "BEHIND"},
            {"number": 3, "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY"},
            {"number": 4, "mergeable": "UNKNOWN", "mergeStateStatus": "UNKNOWN"},
        ]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert [p["number"] for p in output["mergeable"]] == [1]
        assert [p["number"] for p in output["behind"]] == [2]
        assert [p["number"] for p in output["conflicting"]] == [3]
        assert [p["number"] for p in output["unknown"]] == [4]

    def test_invalid_json_exits_zero(self):
        """Invalid JSON input → exit 0 with empty result (triage never fails workflow)."""
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input="not json",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output == {"mergeable": [], "behind": [], "conflicting": [], "unknown": []}


class TestAutoMergeTriageActions:
    """Action generation tests."""

    def test_behind_pr_generates_update_branch_command(self):
        """BEHIND PR → generates update-branch command."""
        prs = [{"number": 456, "mergeable": "MERGEABLE", "mergeStateStatus": "BEHIND"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["behind"]) == 1
        pr = output["behind"][0]
        assert "action" in pr
        assert pr["action"] == "update-branch"

    def test_conflicting_pr_generates_notify_command(self):
        """CONFLICTING PR → generates notify action."""
        prs = [{"number": 789, "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["conflicting"]) == 1
        pr = output["conflicting"][0]
        assert "action" in pr
        assert pr["action"] == "notify"

    def test_mergeable_pr_has_no_action(self):
        """MERGEABLE PR → no special action (workflow proceeds to merge)."""
        prs = [{"number": 123, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert len(output["mergeable"]) == 1
        pr = output["mergeable"][0]
        # mergeable PRs don't need special actions
        assert pr.get("action") is None or pr.get("action") == "merge"


class TestAutoMergeTriageWorkflow:
    """Workflow integration tests (YAML structure)."""

    def test_auto_merge_yaml_has_triage_step(self):
        """auto-merge.yml includes triage step in schedule path."""
        import yaml

        workflow_path = Path(__file__).parent.parent / ".github/workflows/auto-merge.yml"
        data = yaml.safe_load(workflow_path.read_text())

        # Find the auto-merge job
        assert "jobs" in data
        assert "auto-merge" in data["jobs"]

        # Check for triage-related steps or comments
        steps = data["jobs"]["auto-merge"].get("steps", [])
        step_names = [s.get("name", "") for s in steps]

        # At least one step should mention triage, conflicting, or behind
        has_triage = any(
            "triage" in name.lower() or "conflict" in name.lower() or "behind" in name.lower()
            for name in step_names
        )
        # Or the workflow uses the triage script
        uses_triage = any(
            "auto_merge_triage" in str(s) for s in steps
        )

        assert has_triage or uses_triage, (
            f"auto-merge.yml lacks triage logic. Steps: {step_names}"
        )

    def test_auto_merge_yaml_schedule_not_just_resolve(self):
        """Schedule path does more than just resolve (has triage/self-heal)."""
        import yaml

        workflow_path = Path(__file__).parent.parent / ".github/workflows/auto-merge.yml"
        data = yaml.safe_load(workflow_path.read_text())

        # The workflow should have logic beyond just resolve → merge
        # Either a triage job or triage steps in auto-merge job
        jobs = data.get("jobs", {})

        # Check if there's a dedicated triage job
        has_triage_job = any("triage" in job_name.lower() for job_name in jobs.keys())

        # Or check if auto-merge job has triage steps
        auto_merge_steps = jobs.get("auto-merge", {}).get("steps", [])
        has_triage_steps = any(
            "triage" in str(s).lower() or "auto_merge_triage" in str(s)
            for s in auto_merge_steps
        )

        assert has_triage_job or has_triage_steps, (
            "auto-merge.yml schedule path lacks triage/self-heal logic"
        )


class TestAutoMergeTriageHardeningInfra416:
    """INFRA-416：triage 第一版（PR #829）落地后的生产化硬化回归防护。

    审查发现的第一版缺陷与对应硬化：
    - CONFLICTING 评论刷屏：notify 每 10 分钟重复评论 → 按 head SHA
      sentinel 幂等（VAL-T416-001/002）
    - resolve/triage 竞态红腿：并行 matrix 腿合并后 gh pr view NotFound
      → 降级 skip 而非 fail（VAL-T416-003）
    - UNKNOWN 一次性放弃：push 后 GitHub 异步计算 mergeable → 重取一次
      后交 schedule 兜底（VAL-T416-004）
    - 分类缺陷：CONFLICTING+BEHIND 同时出现时 jq 分支互斥导致 PR 掉进
      两个 category → DIRTY 优先，绝不盲合并冲突 PR（VAL-T416-005+脚本测试）
    - job 无超时 → timeout-minutes: 10（VAL-T416-006）
    """

    def _load_workflow(self) -> dict:
        import yaml

        workflow_path = Path(__file__).parent.parent / ".github/workflows/auto-merge.yml"
        return yaml.safe_load(workflow_path.read_text())

    def _triage_step(self, data: dict) -> dict:
        steps = data["jobs"]["auto-merge"]["steps"]
        return next(s for s in steps if s.get("name") == "Triage PR mergeable state")

    def _notify_step(self, data: dict) -> dict:
        steps = data["jobs"]["auto-merge"]["steps"]
        return next(s for s in steps if s.get("name") == "Handle CONFLICTING PR (notify)")

    # ----- VAL-T416-001/002：CONFLICTING 通知幂等 -----

    def test_notify_step_has_sentinel_dedup(self):
        """VAL-T416-001：notify 步骤按 head SHA sentinel 去重评论。"""
        data = self._load_workflow()
        run_block = self._notify_step(data)["run"]
        assert "auto-merge-conflict-" in run_block, (
            "notify 步骤必须包含 head SHA sentinel（幂等去重）"
        )
        assert "--json comments" in run_block or "--json headRefOid" in run_block, (
            "notify 步骤必须查询既有评论/head SHA"
        )

    def test_notify_skip_branch_does_not_comment(self):
        """VAL-T416-002：已有同 SHA sentinel 时跳过评论（仍 exit 1 保持红色告警）。"""
        data = self._load_workflow()
        run_block = self._notify_step(data)["run"]
        assert "Skipping duplicate notification" in run_block, (
            "去重命中分支必须显式跳过且不调 gh pr comment"
        )
        # 去重分支在 gh pr comment 之前短路
        assert run_block.index("Skipping duplicate notification") < run_block.index("gh pr comment")

    # ----- VAL-T416-003：resolve/triage 竞态守卫 -----

    def test_triage_step_handles_pr_not_found(self):
        """VAL-T416-003：PR 被并行腿合并后 gh pr view NotFound → skip 而非红腿。"""
        data = self._load_workflow()
        run_block = self._triage_step(data)["run"]
        assert "not found" in run_block or "Could not resolve" in run_block, (
            "triage 步骤必须识别 NotFound 并降级 skip（竞态守卫）"
        )
        assert "action=skip" in run_block

    # ----- VAL-T416-004：UNKNOWN 重试 -----

    def test_triage_step_retries_unknown_state(self):
        """VAL-T416-004：mergeable=UNKNOWN 时等待重取一次，仍未知交 schedule 兜底。"""
        data = self._load_workflow()
        run_block = self._triage_step(data)["run"]
        assert '"$MERGEABLE" = "UNKNOWN"' in run_block, (
            "triage 步骤必须对 UNKNOWN 状态做一次重取"
        )
        # UNKNOWN 路径最终动作只能是 skip（脚本分类保证），workflow 不猜测
        assert "UNKNOWN retry" in run_block

    # ----- VAL-T416-005：分类互斥（DIRTY 优先于 BEHIND） -----

    def test_conflicting_behind_goes_to_conflicting_only(self):
        """VAL-T416-005a：CONFLICTING+BEHIND 只进 conflicting（notify），不进 behind。

        第一版 jq 的各 category select 条件互不感知，同一 PR 可同时命中
        conflicting 与 behind 两个数组。本硬化版 behind 排除 CONFLICTING，
        保证绝不 blind-merge 一个有冲突的 PR。
        """
        prs = [{"number": 7, "mergeable": "CONFLICTING", "mergeStateStatus": "BEHIND"}]
        result = subprocess.run(
            ["bash", str(get_script_path())],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert [p["number"] for p in output["conflicting"]] == [7]
        assert output["behind"] == [], "CONFLICTING PR 不得进入 behind（会触发 update-branch 掩盖冲突）"
        assert output["mergeable"] == []

    def test_get_action_mode_single_action(self):
        """VAL-T416-005b：--get-action 返回单一 action，workflow 不再重复 jq。"""
        prs = [{"number": 9, "mergeable": "MERGEABLE", "mergeStateStatus": "BEHIND"}]
        result = subprocess.run(
            ["bash", str(get_script_path()), "--get-action", "9"],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "update-branch"

    def test_get_action_mode_unknown_pr_skips(self):
        """--get-action 对不在输入中的 PR 返回 skip（容错）。"""
        prs = [{"number": 11, "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"}]
        result = subprocess.run(
            ["bash", str(get_script_path()), "--get-action", "999"],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "skip"

    def test_get_action_mode_invalid_input_skips(self):
        """--get-action 对非法 JSON 输入返回 skip（triage never fails workflow）。"""
        result = subprocess.run(
            ["bash", str(get_script_path()), "--get-action", "5"],
            input="not json",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "skip"

    # ----- VAL-T416-006：job 超时 -----

    def test_auto_merge_job_has_timeout(self):
        """VAL-T416-006：auto-merge job 限时 10 分钟，防 gh/网络挂死堆叠。"""
        data = self._load_workflow()
        assert data["jobs"]["auto-merge"].get("timeout-minutes") == 10
