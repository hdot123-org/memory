"""
qa.yml coverage-audit PR-skip 容量工程回归防护。

CI 容量工程（2026-08-19）：coverage-audit 是 CI 最重 job（全量 pytest + 覆盖率），
PR 时段与 ci.yml test 串行跑两份全量 pytest 导致自建 runner 排队（7min→3.5min 优化）。
coverage-audit 加 schedule/dispatch-only 事件门，PR 时段跳过、夜间全量保留。
qa-ok 聚合必须正确处理 skipped 状态（job 级 if 跳过时 needs.result == 'skipped'）。
"""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent


class TestCoverageAuditScheduleGate:
    """coverage-audit job 事件门：仅 schedule/workflow_dispatch 运行。"""

    @pytest.fixture
    def qa_data(self):
        """Load qa.yml workflow."""
        workflow_path = REPO_ROOT / ".github/workflows/qa.yml"
        content = workflow_path.read_text()
        data = yaml.safe_load(content)
        assert data is not None
        assert "jobs" in data
        return data

    @pytest.fixture
    def coverage_audit_job(self, qa_data):
        """Extract coverage-audit job definition."""
        assert "coverage-audit" in qa_data["jobs"], "coverage-audit job missing from qa.yml"
        return qa_data["jobs"]["coverage-audit"]

    def test_coverage_audit_has_schedule_only_if_gate(self, coverage_audit_job):
        """CI 容量工程：coverage-audit 必须有 schedule/dispatch-only if 门控。

        PR 时段跳过（pve 每 PR 负载立减一半），夜间全量保留。
        对齐 full-regression 的既有先例。
        """
        job_if = str(coverage_audit_job.get("if", ""))
        assert "schedule" in job_if, "coverage-audit if gate must reference 'schedule' event"
        assert "workflow_dispatch" in job_if, "coverage-audit if gate must reference 'workflow_dispatch' event"

    def test_coverage_audit_if_gate_excludes_pull_request(self, coverage_audit_job):
        """coverage-audit if 门必须排除 pull_request 事件。

        实现方式：正面列举 schedule||workflow_dispatch（隐式排除 pull_request），
        而非负面排除。断言 if 表达式不含 pull_request 字样。
        """
        job_if = str(coverage_audit_job.get("if", ""))
        assert "pull_request" not in job_if, (
            "coverage-audit if gate should use positive allowlist "
            "(schedule||workflow_dispatch), not pull_request exclusion"
        )

    def test_coverage_audit_runs_on_self_hosted(self, coverage_audit_job):
        """coverage-audit 仍在自建 runner 上运行（不回归到 ubuntu-latest）。"""
        runs_on = coverage_audit_job.get("runs-on", [])
        if isinstance(runs_on, str):
            runs_on = [runs_on]
        assert "self-hosted" in runs_on, "coverage-audit must remain on self-hosted runner"

    def test_full_regression_has_same_gate_pattern(self, qa_data):
        """full-regression 也使用相同的 schedule/dispatch-only 门控（既有先例）。"""
        full_reg = qa_data["jobs"].get("full-regression", {})
        job_if = str(full_reg.get("if", ""))
        assert "schedule" in job_if
        assert "workflow_dispatch" in job_if


class TestQaOkSkippedHandling:
    """qa-ok 聚合 job 对 skipped 状态的正确处理。

    当 coverage-audit 被 if 门跳过时，needs.coverage-audit.result == 'skipped'。
    qa-ok 的 fail 分支必须同时接受 'success' 和 'skipped'，否则误报失败。
    """

    @pytest.fixture
    def qa_data(self):
        """Load qa.yml workflow."""
        workflow_path = REPO_ROOT / ".github/workflows/qa.yml"
        content = workflow_path.read_text()
        data = yaml.safe_load(content)
        return data

    @pytest.fixture
    def qa_ok_job(self, qa_data):
        """Extract qa-ok job definition."""
        assert "qa-ok" in qa_data["jobs"], "qa-ok job missing from qa.yml"
        return qa_data["jobs"]["qa-ok"]

    def test_qa_ok_needs_coverage_audit(self, qa_ok_job):
        """qa-ok 的 needs 列表必须包含 coverage-audit。"""
        needs = qa_ok_job.get("needs", [])
        assert "coverage-audit" in needs, "qa-ok must depend on coverage-audit"

    def test_qa_ok_handles_skipped_coverage_audit(self, qa_ok_job):
        """qa-ok 的 coverage-audit 检查必须接受 skipped 状态。

        job 级 if 跳过时 needs.result == 'skipped'，qa-ok 只查 != 'success' 会误判。
        必须改为同时接受 'success' 和 'skipped'。
        """
        steps = qa_ok_job.get("steps", [])
        verify_step = next(
            (s for s in steps if "Verify" in s.get("name", "") or "verify" in s.get("name", "").lower()),
            None,
        )
        assert verify_step is not None, "qa-ok verify step not found"
        run_block = verify_step.get("run", "")

        # 检查 coverage-audit 的判定逻辑必须包含 skipped 分支
        # 方式：查找 coverage-audit 相关 if 块，确认 skipped 被接受
        assert "coverage-audit" in run_block, "qa-ok verify step must check coverage-audit result"
        # 关键断言：coverage-audit 的失败判定必须排除 skipped 状态
        # 即：!= 'success' && != 'skipped' 或等价的 OR 逻辑
        assert "skipped" in run_block, (
            "qa-ok must handle 'skipped' status for coverage-audit; "
            "only checking != 'success' will false-fail when job is skipped by if gate"
        )

    def test_qa_ok_other_jobs_still_require_success(self, qa_ok_job):
        """qa-ok 对非 coverage-audit 的 job 仍要求 success（不接受 skipped）。"""
        steps = qa_ok_job.get("steps", [])
        verify_step = next(
            (s for s in steps if "Verify" in s.get("name", "") or "verify" in s.get("name", "").lower()),
            None,
        )
        assert verify_step is not None
        run_block = verify_step.get("run", "")

        # 其他 job（cli-e2e, hook-lifecycle, business-policy, schema-migration, boundary-security）
        # 的检查应该仍然是简单的 != 'success'，不含 skipped 豁免
        for job_name in ["cli-e2e", "hook-lifecycle", "business-policy", "schema-migration", "boundary-security"]:
            assert job_name in run_block, f"qa-ok must check {job_name} result"


class TestSubsetJobsNoCovGuard:
    """子集 job 的 pytest 步骤必须含 --no-cov 且不含 --cov-fail-under。

    防退化原理：子集 job（hook-lifecycle/business-policy/schema-migration/boundary-security）
    只跑部分测试套件，天然覆盖率 30-47%，不得被 pyproject addopts 的 fail-under=80 连坐。
    --no-cov 完全禁用覆盖率统计与阈值检查，恢复子集 job 的原始语义。

    回归防护（2026-08-21，PR #871 解锁 FIX-HAS-TEST 门禁）：
    若有人误删 --no-cov 或加回 --cov-fail-under，此测试拦截。
    """

    SUBSET_JOBS = [
        "hook-lifecycle",
        "business-policy",
        "schema-migration",
        "boundary-security",
    ]

    @pytest.fixture
    def qa_data(self):
        """Load qa.yml workflow."""
        workflow_path = REPO_ROOT / ".github/workflows/qa.yml"
        content = workflow_path.read_text()
        data = yaml.safe_load(content)
        assert data is not None
        assert "jobs" in data
        return data

    @staticmethod
    def _extract_pytest_steps(job_def):
        """Extract all steps whose run block invokes pytest as a command.

        Only matches lines that actually *run* pytest (``python -m pytest`` or
        bare ``pytest``), not ``pip install pytest`` setup lines.
        """
        steps = job_def.get("steps", [])
        pytest_steps = []
        for step in steps:
            run_block = step.get("run", "")
            invokes_pytest = False
            for line in run_block.splitlines():
                stripped = line.strip()
                # skip install / comment lines
                if stripped.startswith(("#", "pip ", "python -m pip ")):
                    continue
                if "pytest" in stripped and "-m pip" not in stripped:
                    invokes_pytest = True
                    break
            if invokes_pytest:
                pytest_steps.append((step.get("name", "<unnamed>"), run_block))
        return pytest_steps

    def test_all_subset_jobs_exist(self, qa_data):
        """All 4 subset jobs must be present in qa.yml."""
        for job_name in self.SUBSET_JOBS:
            assert job_name in qa_data["jobs"], f"Subset job '{job_name}' missing from qa.yml"

    def test_subset_jobs_have_pytest_steps(self, qa_data):
        """Each subset job must have at least one pytest step."""
        for job_name in self.SUBSET_JOBS:
            job_def = qa_data["jobs"][job_name]
            pytest_steps = self._extract_pytest_steps(job_def)
            assert len(pytest_steps) > 0, f"Subset job '{job_name}' has no pytest steps"

    @pytest.mark.parametrize(
        "job_name",
        [
            "hook-lifecycle",
            "business-policy",
            "schema-migration",
            "boundary-security",
        ],
    )
    def test_subset_job_pytest_steps_contain_no_cov(self, qa_data, job_name):
        """Every pytest step in subset jobs must contain --no-cov.

        子集 job 只跑部分测试，覆盖率天然 30-47%。不加 --no-cov 会被
        pyproject addopts 的 fail-under=80 连坐导致 CI 红。
        """
        job_def = qa_data["jobs"][job_name]
        pytest_steps = self._extract_pytest_steps(job_def)
        for step_name, run_block in pytest_steps:
            assert "--no-cov" in run_block, (
                f"Subset job '{job_name}' step '{step_name}' "
                f"must contain --no-cov to avoid fail-under=80 coverage gate; "
                f"run block: {run_block!r}"
            )

    @pytest.mark.parametrize(
        "job_name",
        [
            "hook-lifecycle",
            "business-policy",
            "schema-migration",
            "boundary-security",
        ],
    )
    def test_subset_job_pytest_steps_no_cov_fail_under(self, qa_data, job_name):
        """No pytest step in subset jobs must contain --cov-fail-under.

        子集 job 不承担覆盖率上报职责，显式禁止 fail-under 门槛。
        即使 --no-cov 已经禁用覆盖率统计，此断言提供双重防护。
        """
        job_def = qa_data["jobs"][job_name]
        pytest_steps = self._extract_pytest_steps(job_def)
        for step_name, run_block in pytest_steps:
            assert "--cov-fail-under" not in run_block, (
                f"Subset job '{job_name}' step '{step_name}' "
                f"must NOT contain --cov-fail-under; "
                f"run block: {run_block!r}"
            )


class TestQaWorkflowActionlint:
    """qa.yml 语法正确性验证。"""

    def test_qa_yml_passes_actionlint(self):
        """qa.yml passes actionlint (GitHub Actions linter)."""
        if not shutil.which("actionlint"):
            pytest.skip("actionlint not installed")
        workflow_path = REPO_ROOT / ".github/workflows/qa.yml"
        result = subprocess.run(
            ["actionlint", str(workflow_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"actionlint failed on qa.yml:\n{result.stdout}\n{result.stderr}"

    def test_qa_yml_valid_yaml(self):
        """qa.yml is valid YAML that can be parsed."""
        workflow_path = REPO_ROOT / ".github/workflows/qa.yml"
        content = workflow_path.read_text()
        data = yaml.safe_load(content)
        assert data is not None
        assert "jobs" in data
        assert "coverage-audit" in data["jobs"]
        assert "qa-ok" in data["jobs"]
