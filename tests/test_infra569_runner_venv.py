"""
INFRA-569 回归防护：CI 全量自建 runner + 按运行隔离 venv。

背景（2026-08-27）：
1. GitHub-hosted runner 在配额/rerun 场景会 queued 无作业永久卡死
   （实证：run 32215817674 六个 ubuntu-latest job 挂起 7 天未获 runner）；
2. 自建 runner 持久化环境中 pip 装进 ~/.local 跨 run 残留，且系统
   site-packages 存在 pip install -e 管不到的旧包副本
   （2026-08-25 教训 selfhosted-runner-env-shadowing），rerun 被旧状态毒化。

裁决：ci.yml 全部 job + qa.yml 夜间重计算 job（coverage-audit /
full-regression）切 [self-hosted, pve-linux]，Python job 统一经
.github/actions/setup-venv 在 RUNNER_TEMP 按 run_id+run_attempt 建一次性
venv（job 结束自动清理）。安全敏感的 pull_request_target 工作流
（droid-review / evolution-governance）必须保持 GitHub-hosted。

本测试拦截三类退化：job 回退 ubuntu-latest、venv action 被移除、
安全边界工作流被搬上自建 runner。
"""

from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).parent.parent
CI_PATH = REPO_ROOT / ".github/workflows/ci.yml"
QA_PATH = REPO_ROOT / ".github/workflows/qa.yml"
SETUP_VENV_ACTION = "./.github/actions/setup-venv"


def _load(path: Path) -> dict[str, Any]:
    data: Any = yaml.safe_load(path.read_text())
    assert isinstance(data, dict) and "jobs" in data
    return data


def _runs_on(job: dict[str, Any]) -> list[str]:
    runs_on: Any = job.get("runs-on", [])
    return [runs_on] if isinstance(runs_on, str) else runs_on


def _uses_setup_venv(job: dict[str, Any]) -> bool:
    return any("actions/setup-venv" in str(step.get("uses", "")) for step in job.get("steps", []) if "uses" in step)


class TestCiAllJobsOnSelfHosted:
    """ci.yml 全部 job 必须跑在自建 runner 上（INFRA-569 主断言）。"""

    def test_all_ci_jobs_on_pve_linux(self) -> None:
        ci = _load(CI_PATH)
        for name, job in ci["jobs"].items():
            runs_on = _runs_on(job)
            assert "self-hosted" in runs_on and "pve-linux" in runs_on, (
                f"ci.yml job '{name}' must run on [self-hosted, pve-linux] "
                f"(INFRA-569: GitHub-hosted queued-deadlock), got: {runs_on}"
            )

    def test_all_ci_jobs_have_timeout(self) -> None:
        """所有 job 必须有 timeout-minutes——挂死 job 会永久占用自建 runner 槽位。"""
        ci = _load(CI_PATH)
        for name, job in ci["jobs"].items():
            assert "timeout-minutes" in job, (
                f"ci.yml job '{name}' must set timeout-minutes "
                f"(INFRA-569: unbounded jobs dead-lock self-hosted runner slots)"
            )


class TestCiVenvIsolation:
    """装 Python 包的 ci.yml job 必须走 setup-venv composite action。"""

    # 纯 shell/gate job 不装 Python 包，无需 venv
    JOBS_NEEDING_VENV = {
        "test",
        "advisory-security",
        "mypy-strict-memory-core",
        "mypy-strict-scripts",
    }

    def test_python_jobs_use_setup_venv(self) -> None:
        ci = _load(CI_PATH)
        for name in self.JOBS_NEEDING_VENV:
            job = ci["jobs"][name]
            assert _uses_setup_venv(job), (
                f"ci.yml job '{name}' must use {SETUP_VENV_ACTION} "
                f"(INFRA-569: per-run venv isolation prevents ~/.local residue "
                f"and site-packages shadowing on rerun)"
            )

    def test_no_job_scoped_pip_break_system_packages(self) -> None:
        """旧模式残留检测：job 级 PIP_BREAK_SYSTEM_PACKAGES 是 pip 装系统目录的信号。"""
        ci = _load(CI_PATH)
        for name, job in ci["jobs"].items():
            env = job.get("env", {})
            assert "PIP_BREAK_SYSTEM_PACKAGES" not in env, (
                f"ci.yml job '{name}' must not set PIP_BREAK_SYSTEM_PACKAGES "
                f"(INFRA-569: pip belongs in the per-run venv, not system site-packages)"
            )


class TestQaNightlyHeavyJobs:
    """qa.yml 夜间重计算 job 的 runner 与 venv 隔离。"""

    def test_coverage_audit_keeps_self_hosted_and_venv(self) -> None:
        qa = _load(QA_PATH)
        job = qa["jobs"]["coverage-audit"]
        runs_on = _runs_on(job)
        assert "self-hosted" in runs_on and "pve-linux" in runs_on
        assert _uses_setup_venv(job), "coverage-audit must use setup-venv (INFRA-569)"

    def test_full_regression_on_self_hosted_with_venv(self) -> None:
        qa = _load(QA_PATH)
        job = qa["jobs"]["full-regression"]
        runs_on = _runs_on(job)
        assert "self-hosted" in runs_on and "pve-linux" in runs_on, (
            "full-regression must run on [self-hosted, pve-linux] "
            "(INFRA-569: nightly heaviest job, aligned with coverage-audit)"
        )
        assert _uses_setup_venv(job), "full-regression must use setup-venv (INFRA-569)"
        assert "timeout-minutes" in job, "full-regression must set timeout-minutes (INFRA-569)"


class TestSecurityBoundaryWorkflowsStayHosted:
    """pull_request_target + secrets 的安全边界工作流 runner 归属。

    INFRA-569（2026-08-27）原裁决：droid-review / evolution-governance 保持
    GitHub-hosted（自建 runner 对 PR 代码 job 是持久化多租户环境）。

    2026-08-29 更新（M4 gate-droid-review）：droid-review 从本边界移出——
    (1) 共享 runner 池落地（memory-runnerz 同时服务 memory-core 与 infra-core），
        infra-core 自仓 droid-review（同为 pull_request_target + FACTORY_API_KEY，
        PR 上下文执行面更大）自 #43 起即生产运行在同一批 pve 机器上并被牺牲 PR
        端到端验证，"GitHub-hosted 才隔离" 的边界已不存在；
    (2) 分片流水线引擎唯一活体在 infra-core reusable workflow
        （[self-hosted, pve-linux]），caller 侧改 runs-on 无法改变实际执行面；
    (3) INFRA-569 自身背景记录了 GitHub-hosted 的 queued-deadlock 可靠性问题。
    evolution-governance 仍保持 GitHub-hosted（无 PR 内容执行，低成本维持原边界）。
    """

    PROTECTED_WORKFLOWS = ["evolution-governance.yml"]

    def test_pr_target_workflows_not_self_hosted(self) -> None:
        for wf_name in self.PROTECTED_WORKFLOWS:
            path = REPO_ROOT / ".github/workflows" / wf_name
            data = yaml.safe_load(path.read_text())
            triggers = data.get(True, {})  # YAML 'on:' parses as True
            assert "pull_request_target" in triggers, (
                f"{wf_name} expected pull_request_target trigger; if this changed, revisit the security boundary list"
            )
            for job_name, job in data.get("jobs", {}).items():
                runs_on = _runs_on(job)
                assert "self-hosted" not in runs_on, (
                    f"{wf_name} job '{job_name}' must stay GitHub-hosted: "
                    f"pull_request_target + secrets on a self-hosted runner "
                    f"widens the attack surface (INFRA-569 boundary)"
                )

    def test_droid_review_aggregate_job_runner_alignment(self) -> None:
        """droid-review 聚合 job 与引擎流水线一致跑共享池（runner 铁律），
        且聚合 job 本身无 PR 内容执行面（composite 只做 artifact 下载 + gh 发布）。"""
        path = REPO_ROOT / ".github/workflows/droid-review.yml"
        data = yaml.safe_load(path.read_text())
        aggregate_job = data["jobs"]["droid-review"]
        runs_on = _runs_on(aggregate_job)
        assert "self-hosted" in runs_on and "pve-linux" in runs_on, (
            f"droid-review aggregate job must run on [self-hosted, pve-linux], got: {runs_on}"
        )
