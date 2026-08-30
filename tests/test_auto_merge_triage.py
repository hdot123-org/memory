"""Tests for scripts/auto_merge_triage.sh (auto-merge blind-spot triage).

Blind-spot forms (PR #829 / INFRA-416 / INFRA-428):
1. CONFLICTING: PR silently skipped, no notification (#794 停滞 11h+)
2. BEHIND + all green: needs update-branch self-heal (#814/#819/#825/#827/#828)
3. Early-fire + no re-trigger: schedule sweep should catch BEHIND PRs
4. BLOCKED/DRAFT misclassified as mergeable → blind merge attempts
5. Checks incomplete/failed at triage time → premature or poisoned merges

Contract:
- Input: gh pr view/list --json number,mergeable,mergeStateStatus,isDraft,statusCheckRollup JSON
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


def _run_triage(prs: list, *extra_args: str) -> dict:
    """Run the triage script on a PR list and return its JSON output.

    Shared by INFRA-428 / SKIPPED-checks test classes (dedup INFRA-439/445).
    """
    result = subprocess.run(
        ["bash", str(get_script_path()), *extra_args],
        input=json.dumps(prs),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    return json.loads(result.stdout)


def _assert_caller_delegates(data: dict) -> None:
    """thin caller 委托断言（M4 切换后）：硬化不变量已随执行体迁入 infra-core
    auto-merge-pipeline.yml（引擎仓 test_auto_merge_pipeline_hardening.py 锁定），
    caller 只需保持单 job uses 委托。"""
    job = data["jobs"]["auto-merge"]
    assert ".github/workflows/auto-merge-pipeline.yml@" in job.get("uses", ""), (
        "执行体必须委托 infra-core auto-merge-pipeline.yml"
    )


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
        assert output == {
            "mergeable": [],
            "behind": [],
            "conflicting": [],
            "pending": [],
            "stalled": [],
            "unknown": [],
        }

    def test_mergeable_pr_classified(self):
        """PR with mergeable=MERGEABLE + green rollup → mergeable list."""
        prs = [
            {
                "number": 123,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [{"conclusion": "SUCCESS"}],
            }
        ]
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
            {
                "number": 1,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [{"conclusion": "SUCCESS"}],
            },
            {"number": 2, "mergeable": "MERGEABLE", "mergeStateStatus": "BEHIND"},
            {"number": 3, "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY"},
            {"number": 4, "mergeable": "UNKNOWN", "mergeStateStatus": "UNKNOWN"},
            {
                "number": 5,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "BLOCKED",
                "isDraft": False,
                "statusCheckRollup": [{"conclusion": "SUCCESS"}],
            },
            {
                "number": 6,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "DRAFT",
                "isDraft": True,
                "statusCheckRollup": [{"conclusion": "SUCCESS"}],
            },
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
        assert [p["number"] for p in output["pending"]] == [5, 6]

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
        assert output == {
            "mergeable": [],
            "behind": [],
            "conflicting": [],
            "pending": [],
            "stalled": [],
            "unknown": [],
        }


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

    def test_mergeable_pr_has_merge_action(self):
        """MERGEABLE + green rollup PR → action=merge."""
        prs = [
            {
                "number": 123,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [{"conclusion": "SUCCESS"}],
            }
        ]
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
        assert pr["action"] == "merge"


class TestAutoMergeTriageWorkflow:
    """Workflow integration tests (YAML structure)——M4 切换后为 thin caller 委托断言。

    triage/notify/behind/stalled 执行体迁入 infra-core auto-merge-pipeline.yml
    （reusable）；硬化不变量（sentinel 幂等、NotFound 降级、UNKNOWN 重试、
    timeout、stalled 标志等）由引擎仓 test_auto_merge_pipeline_hardening.py
    在 reusable 载体上逐条锁定。caller 只锁委托关系与事件门控。
    """

    def test_auto_merge_yaml_delegates_to_infra_core_pipeline(self):
        """auto-merge.yml 是 thin caller：单 job 委托 infra-core reusable（triage 执行体所在）。"""
        import yaml

        workflow_path = Path(__file__).parent.parent / ".github/workflows/auto-merge.yml"
        data = yaml.safe_load(workflow_path.read_text())

        assert "jobs" in data
        jobs = data["jobs"]
        assert list(jobs.keys()) == ["auto-merge"], f"thin caller 单 job 拓扑漂移: {list(jobs.keys())}"
        job = jobs["auto-merge"]
        assert job.get("uses") == "hdot123-org/infra-core/.github/workflows/auto-merge-pipeline.yml@main", (
            "执行体必须委托 infra-core auto-merge-pipeline.yml"
        )
        assert job.get("steps") is None, "thin caller 不得保留内联 step"

    def test_auto_merge_yaml_schedule_not_just_resolve(self):
        """Schedule 路径有完整 triage/self-heal 语义（M4 切换后：由委托的
        infra-core reusable 承载——其模板测试锁定 resolve+triage+merge 拓扑）。"""
        import yaml

        workflow_path = Path(__file__).parent.parent / ".github/workflows/auto-merge.yml"
        data = yaml.safe_load(workflow_path.read_text())
        job = data["jobs"]["auto-merge"]
        # 委托关系即语义承载证明：reusable 内含 resolve + auto-merge(triage) 双 job
        assert ".github/workflows/auto-merge-pipeline.yml@" in job.get("uses", "")
        # 事件门控留在 caller：schedule 事件允许进入流水
        job_if = str(job.get("if", ""))
        assert "github.event_name == 'schedule'" in job_if


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

    # ----- VAL-T416-001/002：CONFLICTING 通知幂等（执行体在 reusable，
    # 引擎仓 test_auto_merge_pipeline_hardening.py::TestNotifyStepIdempotency 锁定） -----

    def test_notify_step_has_sentinel_dedup(self):
        """VAL-T416-001（M4 切换后）：caller 保持委托，sentinel 幂等在 reusable 锁定。"""
        _assert_caller_delegates(self._load_workflow())

    def test_notify_skip_branch_does_not_comment(self):
        """VAL-T416-002（M4 切换后）：caller 保持委托，去重短路语义在 reusable 锁定。"""
        _assert_caller_delegates(self._load_workflow())

    # ----- VAL-T416-003：resolve/triage 竞态守卫（reusable 锁定） -----

    def test_triage_step_handles_pr_not_found(self):
        """VAL-T416-003（M4 切换后）：caller 保持委托，NotFound→skip 在 reusable 锁定。"""
        _assert_caller_delegates(self._load_workflow())

    # ----- VAL-T416-004：UNKNOWN 重试（reusable 锁定） -----

    def test_triage_step_retries_unknown_state(self):
        """VAL-T416-004（M4 切换后）：caller 保持委托，UNKNOWN 重取在 reusable 锁定。"""
        _assert_caller_delegates(self._load_workflow())

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

    # ----- VAL-T416-006：job 超时（执行体在 reusable，引擎仓锁定 timeout=10） -----

    def test_auto_merge_job_has_timeout(self):
        """VAL-T416-006（M4 切换后）：caller 保持委托，timeout-minutes: 10 在 reusable 锁定。"""
        _assert_caller_delegates(self._load_workflow())


class TestAutoMergeTriageHardeningInfra428:
    """INFRA-428：triage 第二轮硬化——盲区分类补全 + 红腿治理 + 竞态收敛。

    2026-08-19 审计发现的残留盲区与对应硬化：
    - BLOCKED/DRAFT 掉进 mergeable → 每 10 分钟盲合并尝试 → 红腿 +
      shared action 自身失败 check 毒化 head SHA（2026-08-18 自毒死锁）
      → 新增 pending 类别，action=wait（VAL-428-001）
    - early-fire：pull_request_target(opened)/workflow_run 单工作流完成即
      触发，mergeStateStatus 异步缓存可短暂 stale-CLEAN → cross-check
      statusCheckRollup，merge 仅在 rollup 全绿时发出；空 rollup =
      check 未报齐 = fail-closed wait（VAL-428-002）
    - CONFLICTING 去重命中仍 exit 1 → 未解决冲突每 10 分钟永久红腿 →
      去重命中 exit 0，仅首次通知失败保持红色（VAL-428-003）
    - update-branch 无竞态守卫：并行腿刚更新完，本腿再调用报错红腿 →
      失败降级绿腿 skip（VAL-428-004）
    - rollup 报齐但非全绿（check 失败/残留毒化）无任何信号 → stalled
      类别 + head SHA sentinel 幂等评论（VAL-428-005）
    - 无 workflow 级并发控制：schedule + workflow_run 腿竞态（评论
      TOCTOU / update-branch 双发）→ concurrency 组排队（VAL-428-006）
    """

    def _load_workflow(self) -> dict:
        import yaml

        workflow_path = Path(__file__).parent.parent / ".github/workflows/auto-merge.yml"
        return yaml.safe_load(workflow_path.read_text())

    GREEN = [{"conclusion": "SUCCESS"}]

    # ----- VAL-428-001：BLOCKED/DRAFT → pending，绝不 merge -----

    def test_blocked_pr_waits_not_merges(self):
        """VAL-428-001a：mergeStateStatus=BLOCKED → pending/wait，不再盲合并。"""
        prs = [
            {
                "number": 5,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "BLOCKED",
                "isDraft": False,
                "statusCheckRollup": self.GREEN,
            }
        ]
        output = _run_triage(prs)
        assert output["pending"][0]["number"] == 5
        assert output["pending"][0]["action"] == "wait"
        assert output["mergeable"] == [], "BLOCKED PR 不得进入 mergeable（盲合并 + 毒化 head SHA）"

    def test_draft_pr_by_flag_waits(self):
        """VAL-428-001b：isDraft=true → pending/wait（即使 rollup 全绿）。"""
        prs = [
            {
                "number": 6,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": True,
                "statusCheckRollup": self.GREEN,
            }
        ]
        output = _run_triage(prs)
        assert output["pending"][0]["number"] == 6
        assert output["pending"][0]["action"] == "wait"
        assert output["mergeable"] == []

    def test_draft_pr_by_state_waits(self):
        """VAL-428-001c：mergeStateStatus=DRAFT → pending/wait。"""
        prs = [
            {
                "number": 7,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "DRAFT",
                "isDraft": True,
            }
        ]
        output = _run_triage(prs)
        assert output["pending"][0]["number"] == 7
        assert output["mergeable"] == []

    # ----- VAL-428-002：early-fire 防护（rollup cross-check） -----

    def test_early_fire_no_rollup_waits(self):
        """VAL-428-002a：rollup 为空（check 未报）→ pending/wait，fail-closed。"""
        prs = [
            {
                "number": 8,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
            }
        ]
        output = _run_triage(prs)
        assert output["pending"][0]["number"] == 8
        assert output["mergeable"] == [], "check 未报齐时不得 merge（early-fire 盲合并）"

    def test_early_fire_pending_check_waits(self):
        """VAL-428-002b：rollup 有 in_progress check → pending/wait。"""
        prs = [
            {
                "number": 9,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"status": "in_progress", "conclusion": None},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["pending"][0]["number"] == 9
        assert output["mergeable"] == []

    def test_green_rollup_merges(self):
        """VAL-428-002c：MERGEABLE + rollup 全绿 → mergeable/merge（正向路径保持）。"""
        prs = [
            {
                "number": 10,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "SUCCESS"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["mergeable"][0]["number"] == 10
        assert output["mergeable"][0]["action"] == "merge"

    def test_conflicting_wins_over_rollup(self):
        """VAL-428-002d：CONFLICTING 优先级最高，rollup 全绿也不掩盖冲突。"""
        prs = [
            {
                "number": 11,
                "mergeable": "CONFLICTING",
                "mergeStateStatus": "BEHIND",
                "isDraft": False,
                "statusCheckRollup": self.GREEN,
            }
        ]
        output = _run_triage(prs)
        assert output["conflicting"][0]["number"] == 11
        assert output["behind"] == [], "冲突 PR 不得 update-branch 盲合并"
        assert output["mergeable"] == []

    def test_behind_wins_over_pending_states(self):
        """VAL-428-002e：BEHIND 优先于 draft/blocked/rollup（先追平再谈其他）。"""
        prs = [
            {
                "number": 12,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "BEHIND",
                "isDraft": True,
            }
        ]
        output = _run_triage(prs)
        assert output["behind"][0]["number"] == 12
        assert output["pending"] == []

    def test_unknown_mergeable_skips_even_with_rollup(self):
        """VAL-428-002f：mergeable=UNKNOWN → skip（GitHub 未算完，不猜测）。"""
        prs = [
            {
                "number": 13,
                "mergeable": "UNKNOWN",
                "mergeStateStatus": "UNKNOWN",
                "statusCheckRollup": self.GREEN,
            }
        ]
        output = _run_triage(prs)
        assert output["unknown"][0]["number"] == 13

    def test_workflow_triage_fetches_rollup_and_draft(self):
        """VAL-428-002g（M4 切换后）：caller 保持委托，取数字段（isDraft +
        statusCheckRollup）在引擎仓 test_auto_merge_pipeline_hardening.py 锁定。"""
        _assert_caller_delegates(self._load_workflow())

    # ----- VAL-428-003：notify 去重命中 exit 0（红腿治理，reusable 锁定） -----

    def test_notify_dedup_hit_exits_zero(self):
        """VAL-428-003（M4 切换后）：caller 保持委托，去重命中 exit 0 在 reusable 锁定。"""
        _assert_caller_delegates(self._load_workflow())

    # ----- VAL-428-004：update-branch 竞态守卫（reusable 锁定） -----

    def test_update_branch_race_guard(self):
        """VAL-428-004（M4 切换后）：caller 保持委托，update-branch 降级守卫在 reusable 锁定。"""
        _assert_caller_delegates(self._load_workflow())

    # ----- VAL-428-005：stalled 类别 -----

    def test_stalled_check_reported_not_success(self):
        """VAL-428-005a：rollup 报齐但含 FAILURE → stalled/wait。"""
        prs = [
            {
                "number": 14,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "FAILURE"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["stalled"][0]["number"] == 14
        assert output["stalled"][0]["action"] == "wait"
        assert output["mergeable"] == [], "存在失败 check 时不得 merge"

    def test_workflow_has_stalled_step_with_sentinel(self):
        """VAL-428-005b（M4 切换后）：caller 保持委托，stalled sentinel 幂等在 reusable 锁定。"""
        _assert_caller_delegates(self._load_workflow())

    def test_workflow_triage_outputs_stalled_flag(self):
        """VAL-428-005c（M4 切换后）：caller 保持委托，stalled 标志输出/消费在 reusable 锁定。"""
        _assert_caller_delegates(self._load_workflow())

    # ----- VAL-428-006：workflow 级并发控制（concurrency 留在 caller） -----

    def test_workflow_has_concurrency_group(self):
        """VAL-428-006：caller 保留 workflow 级 concurrency（消除跨 run 竞态窗口）。"""
        data = self._load_workflow()
        concurrency = data.get("concurrency")
        assert concurrency is not None, "缺少 workflow 级 concurrency（评论 TOCTOU/update-branch 双发）"
        assert "group" in concurrency
        assert concurrency["group"] == "auto-merge-pipeline"
        assert concurrency["cancel-in-progress"] is False

    # ----- --get-category 模式 -----

    def test_get_category_mode(self):
        """--get-category 返回类别名（stalled 辅助输出的事实源）。"""
        prs = [
            {
                "number": 14,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [{"conclusion": "FAILURE"}],
            }
        ]
        result = subprocess.run(
            ["bash", str(get_script_path()), "--get-category", "14"],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "stalled"

    def test_get_category_missing_pr_unknown(self):
        """--get-category 对不在输入中的 PR 返回 unknown（容错）。"""
        prs = [{"number": 1, "mergeable": "MERGEABLE", "mergeStateStatus": "BEHIND"}]
        result = subprocess.run(
            ["bash", str(get_script_path()), "--get-category", "999"],
            input=json.dumps(prs),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "unknown"

    def test_get_category_invalid_input_unknown(self):
        """--get-category 对非法 JSON 输入返回 unknown（never fails workflow）。"""
        result = subprocess.run(
            ["bash", str(get_script_path()), "--get-category", "5"],
            input="not json",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert result.stdout.strip() == "unknown"

    # ----- 防退化：分类完备性 -----

    def test_categories_are_exhaustive_and_exclusive(self):
        """全状态矩阵每个 PR 恰好落一个类别（分类完备性 + 互斥性）。"""
        matrix = [
            # (mergeable, mergeStateStatus, isDraft, rollup) -> 期望类别
            ("MERGEABLE", "CLEAN", False, [{"conclusion": "SUCCESS"}]),  # mergeable
            ("MERGEABLE", "CLEAN", False, []),  # pending (early-fire)
            ("MERGEABLE", "CLEAN", False, [{"conclusion": "FAILURE"}]),  # stalled
            ("MERGEABLE", "CLEAN", False, [{"status": "in_progress"}]),  # pending
            ("MERGEABLE", "BEHIND", False, [{"conclusion": "SUCCESS"}]),  # behind
            ("MERGEABLE", "BEHIND", True, []),  # behind (BEHIND 优先)
            ("MERGEABLE", "BLOCKED", False, [{"conclusion": "SUCCESS"}]),  # pending
            ("MERGEABLE", "DRAFT", True, []),  # pending
            ("CONFLICTING", "BEHIND", False, [{"conclusion": "SUCCESS"}]),  # conflicting
            ("CONFLICTING", "CLEAN", False, [{"conclusion": "SUCCESS"}]),  # conflicting
            ("UNKNOWN", "UNKNOWN", False, []),  # unknown
            ("UNKNOWN", "BLOCKED", False, [{"conclusion": "SUCCESS"}]),  # unknown (UNKNOWN 优先)
        ]
        expected = [
            "mergeable",
            "pending",
            "stalled",
            "pending",
            "behind",
            "behind",
            "pending",
            "pending",
            "conflicting",
            "conflicting",
            "unknown",
            "unknown",
        ]
        prs = [
            {
                "number": i + 1,
                "mergeable": m,
                "mergeStateStatus": s,
                "isDraft": d,
                "statusCheckRollup": r,
            }
            for i, (m, s, d, r) in enumerate(matrix)
        ]
        output = _run_triage(prs)
        category_numbers: dict[str, list[int]] = {cat: [p["number"] for p in prs_] for cat, prs_ in output.items()}
        for idx, exp in enumerate(expected):
            found = [cat for cat, nums in category_numbers.items() if (idx + 1) in nums]
            assert found == [exp], (
                f"PR #{idx + 1} (mergeable={matrix[idx][0]}, state={matrix[idx][1]}, "
                f"draft={matrix[idx][2]}, rollup={matrix[idx][3]}) 应为 {exp}，实际 {found}"
            )


class TestAutoMergeTriageSkippedChecks:
    """scrutiny R1 blocking / INFRA-428 修复：SKIPPED/NEUTRAL 防假绿约束。

    根因：qa.yml #830 起两个夜间 job（Coverage Audit / Full Regression）
    在 PR 事件报 SKIPPED——旧逻辑要求所有 check 的 conclusion == "SUCCESS"，
    导致任何 PR 的 rollup 永久含 SKIPPED，checks_green 永远 false，sweep
    判定永远 stalled，零 merge（历史 #855/#856 实际靠 GitHub 原生 auto-merge 合的）。

    PR #862 修复了死锁，接受 SKIPPED/NEUTRAL 为非失败（与 branch protection 对齐）。
    但 PR #862 的实现缺 any(SUCCESS) 下限——全 SKIPPED 的 rollup 会被判 mergeable，
    造成假绿洞（reviewer 实测证实）。

    修复后（本提交）：
    - SKIPPED/NEUTRAL 视为非失败（branch protection 对齐）
    - any(SUCCESS) 防假绿下限（全 SKIPPED/NEUTRAL 需人工审查）
    - null conclusion（排队中）仍不算 complete
    - FAILURE/CANCELLED/TIMED_OUT/ACTION_REQUIRED 仍判非绿

    sweep 与原生 --auto 并存无害（原生优先，sweep 兜底）。
    """

    # ----- 判定矩阵：SKIPPED 场景 -----

    def test_success_plus_skipped_is_green(self):
        """SUCCESS + SKIPPED 混合 → mergeable（SKIPPED 不阻塞合并）。"""
        prs = [
            {
                "number": 100,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "SKIPPED"},  # 夜间 job 在 PR 事件报 SKIPPED
                    {"conclusion": "SUCCESS"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["mergeable"][0]["number"] == 100, "SUCCESS+SKIPPED 应判为 green（修复前会被误判为 stalled）"
        assert output["mergeable"][0]["action"] == "merge"
        assert output["stalled"] == [], "SKIPPED 不应触发 stalled"

    def test_all_skipped_is_not_mergeable(self):
        """防假绿：全 SKIPPED（无任何 SUCCESS）→ 非 mergeable（需人工审查）。

        scrutiny R1 blocking：reviewer 实测证实 PR #862 实现缺 any(SUCCESS) 下限，
        全 SKIPPED rollup 会被判 mergeable/action=merge，造成功能规格禁止的假绿洞。
        """
        prs = [
            {
                "number": 101,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SKIPPED"},
                    {"conclusion": "SKIPPED"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["mergeable"] == [], "全 SKIPPED 不得判 mergeable（防假绿下限 any(SUCCESS) 生效）"
        # 全 SKIPPED 但非空 rollup → stalled（所有 check 已报告但无 SUCCESS）
        assert len(output["stalled"]) == 1 or len(output["pending"]) == 1

    def test_skipped_plus_failure_is_stalled(self):
        """SKIPPED + FAILURE → stalled（FAILURE 仍阻塞合并）。"""
        prs = [
            {
                "number": 102,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "SKIPPED"},
                    {"conclusion": "FAILURE"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["stalled"][0]["number"] == 102, "FAILURE 仍应触发 stalled（SKIPPED 不应掩盖真实失败）"
        assert output["mergeable"] == []

    def test_failure_only_is_stalled(self):
        """仅 FAILURE → stalled（旧逻辑与新逻辑行为一致）。"""
        prs = [
            {
                "number": 103,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "FAILURE"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["stalled"][0]["number"] == 103
        assert output["mergeable"] == []

    def test_timed_out_is_stalled(self):
        """TIMED_OUT → stalled（失败结论之一）。"""
        prs = [
            {
                "number": 104,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "TIMED_OUT"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["stalled"][0]["number"] == 104
        assert output["mergeable"] == []

    def test_cancelled_is_stalled(self):
        """CANCELLED → stalled（失败结论之一）。"""
        prs = [
            {
                "number": 105,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "CANCELLED"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["stalled"][0]["number"] == 105
        assert output["mergeable"] == []

    def test_action_required_is_stalled(self):
        """ACTION_REQUIRED → stalled（失败结论之一）。"""
        prs = [
            {
                "number": 106,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "ACTION_REQUIRED"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["stalled"][0]["number"] == 106
        assert output["mergeable"] == []

    # ----- 判定矩阵：NEUTRAL 场景 -----

    def test_success_plus_neutral_is_green(self):
        """SUCCESS + NEUTRAL 混合 → mergeable（NEUTRAL 不阻塞合并）。"""
        prs = [
            {
                "number": 107,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "NEUTRAL"},  # 某些 check 可能报 NEUTRAL
                    {"conclusion": "SUCCESS"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["mergeable"][0]["number"] == 107
        assert output["stalled"] == []

    def test_all_neutral_is_not_mergeable(self):
        """防假绿：全 NEUTRAL（无任何 SUCCESS）→ 非 mergeable（需人工审查）。

        与全 SKIPPED 同理：any(SUCCESS) 下限要求至少一个真实成功。
        NEUTRAL 是 annotation-only check（branch protection 对齐），但单独
        存在时不代表代码被验证过。
        """
        prs = [
            {
                "number": 108,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "NEUTRAL"},
                    {"conclusion": "NEUTRAL"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["mergeable"] == [], "全 NEUTRAL 不得判 mergeable（防假绿下限 any(SUCCESS) 生效）"
        assert len(output["stalled"]) == 1 or len(output["pending"]) == 1

    def test_neutral_plus_failure_is_stalled(self):
        """NEUTRAL + FAILURE → stalled（FAILURE 仍阻塞）。"""
        prs = [
            {
                "number": 109,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "NEUTRAL"},
                    {"conclusion": "FAILURE"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["stalled"][0]["number"] == 109
        assert output["mergeable"] == []

    # ----- 混合场景：SKIPPED + NEUTRAL + 失败结论 -----

    def test_complex_matrix_real_world_scenario(self):
        """真实场景：多个 SUCCESS + SKIPPED（夜间 job）+ NEUTRAL → mergeable。"""
        prs = [
            {
                "number": 110,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},  # CI
                    {"conclusion": "SUCCESS"},  # Droid Auto Review
                    {"conclusion": "SKIPPED"},  # Coverage Audit（夜间 job）
                    {"conclusion": "SKIPPED"},  # Full Regression（夜间 job）
                    {"conclusion": "NEUTRAL"},  # 某些 lint check
                    {"conclusion": "SUCCESS"},  # Evolution Governance
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["mergeable"][0]["number"] == 110, "真实 PR 场景（含夜间 job SKIPPED）应判为 green 并可合并"
        assert output["mergeable"][0]["action"] == "merge"
        assert output["stalled"] == []

    def test_regression_old_behavior_preserved(self):
        """回归测试：纯 SUCCESS 仍判为 mergeable（旧逻辑行为不变）。"""
        prs = [
            {
                "number": 111,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "SUCCESS"},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["mergeable"][0]["number"] == 111
        assert output["mergeable"][0]["action"] == "merge"

    def test_in_progress_plus_skipped_still_pending(self):
        """in_progress + SKIPPED → pending（in_progress 未报齐，fail-closed）。"""
        prs = [
            {
                "number": 112,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [
                    {"conclusion": "SUCCESS"},
                    {"conclusion": "SKIPPED"},
                    {"status": "in_progress", "conclusion": None},
                ],
            }
        ]
        output = _run_triage(prs)
        assert output["pending"][0]["number"] == 112, "in_progress check 未报齐时应判 pending（early-fire 防护优先）"
        assert output["mergeable"] == []

    # ----- 判定矩阵覆盖总结 -----

    def test_judgment_matrix_documentation(self):
        """判定矩阵文档：SUCCESS/SKIPPED/NEUTRAL 非失败，FAILURE/TIMED_OUT/CANCELLED/ACTION_REQUIRED 失败。

        本测试用注释形式记录判定矩阵，便于后续维护。
        """
        # 非失败结论（视为 green 的前提条件）：
        non_failure_conclusions = ["SUCCESS", "SKIPPED", "NEUTRAL"]
        # 失败结论（触发 stalled）：
        failure_conclusions = ["FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED"]

        # 验证 SUCCESS 单独存在时判 mergeable
        prs = [
            {
                "number": 200,
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "isDraft": False,
                "statusCheckRollup": [{"conclusion": "SUCCESS"}],
            }
        ]
        output = _run_triage(prs)
        assert output["mergeable"], "SUCCESS 应判为 green"

        # 验证 SKIPPED/NEUTRAL 单独存在时 NOT 判 mergeable（防假绿下限）
        for conclusion in ["SKIPPED", "NEUTRAL"]:
            prs = [
                {
                    "number": 200 + non_failure_conclusions.index(conclusion),
                    "mergeable": "MERGEABLE",
                    "mergeStateStatus": "CLEAN",
                    "isDraft": False,
                    "statusCheckRollup": [{"conclusion": conclusion}],
                }
            ]
            output = _run_triage(prs)
            assert not output["mergeable"], f"{conclusion} 单独存在时 NOT 判为 green（防假绿下限 any(SUCCESS)）"

        # 验证失败结论单独存在时判 stalled
        for conclusion in failure_conclusions:
            prs = [
                {
                    "number": 300 + failure_conclusions.index(conclusion),
                    "mergeable": "MERGEABLE",
                    "mergeStateStatus": "CLEAN",
                    "isDraft": False,
                    "statusCheckRollup": [{"conclusion": conclusion}],
                }
            ]
            output = _run_triage(prs)
            assert output["stalled"], f"{conclusion} 应判为 stalled（失败）"
