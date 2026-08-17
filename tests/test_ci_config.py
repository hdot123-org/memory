"""
CI configuration tests for trust chain reconstruction mission.

Tests for VAL-GATE-* assertions (Audit Gate) and VAL-CROSS-029/030/031/032.
Validates YAML structure of droid-review.yml, auto-merge.yml, and ci.yml.
"""
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent


class TestAuditGate:
    """VAL-GATE-* assertions: security_block_on_high configuration (Advisory mode)."""

    @pytest.fixture
    def droid_review_data(self):
        """Load droid-review.yml workflow."""
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        return yaml.safe_load(workflow_path.read_text())

    def _get_droid_action_step(self, data):
        """Extract the droid-action step from the workflow."""
        steps = data["jobs"]["droid-review"]["steps"]
        return next(s for s in steps if "droid-action" in s.get("uses", ""))

    def test_val_gate_001_security_block_on_high_present(self, droid_review_data):
        """VAL-GATE-001: droid-review.yml has security_block_on_high: "false" (Advisory mode, string)."""
        droid_step = self._get_droid_action_step(droid_review_data)
        assert "security_block_on_high" in droid_step["with"]
        assert droid_step["with"]["security_block_on_high"] == "false"

    def test_val_gate_002_security_block_on_critical_remains(self, droid_review_data):
        """VAL-GATE-002: security_block_on_critical remains enabled (not disabled)."""
        droid_step = self._get_droid_action_step(droid_review_data)
        # Key absent (default true) or explicitly "true". NOT "false".
        if "security_block_on_critical" in droid_step["with"]:
            assert droid_step["with"]["security_block_on_critical"] != "false"

    def test_val_gate_003_security_block_on_high_placement(self, droid_review_data):
        """VAL-GATE-003: security_block_on_high is direct child of droid-action with block."""
        droid_step = self._get_droid_action_step(droid_review_data)
        # Must be in the 'with' dict, not in 'env' or job-level
        assert "with" in droid_step
        assert "security_block_on_high" in droid_step["with"]
        # Must not be in env
        assert "security_block_on_high" not in droid_step.get("env", {})

    def test_val_gate_004_existing_inputs_preserved(self, droid_review_data):
        """VAL-GATE-004: Existing droid-action inputs unchanged (except intentionally removed invalid inputs)."""
        droid_step = self._get_droid_action_step(droid_review_data)
        with_block = droid_step["with"]

        # All original inputs must be present
        assert "factory_api_key" in with_block
        assert "automatic_review" in with_block
        assert "automatic_security_review" in with_block
        # security_review_model was intentionally removed (2026-08-16):
        # This input is not recognized by the pinned droid-action version (e5ae502),
        # causing warnings or errors. See feature: droid-review-timeout-hardening.
        assert "security_review_model" not in with_block
        assert "review_model" in with_block
        assert "allowed_bots" in with_block

        # Values must match originals
        assert with_block["factory_api_key"] == "${{ secrets.FACTORY_API_KEY }}"
        assert with_block["automatic_review"] is True
        assert with_block["automatic_security_review"] is True
        assert with_block["review_model"] == "qwen3.7-plus"
        assert with_block["allowed_bots"] == "dependabot[bot]"

    def test_val_gate_005_actionlint_passes(self):
        """VAL-GATE-005: Modified droid-review.yml passes actionlint."""
        import shutil
        if not shutil.which("actionlint"):
            pytest.skip("actionlint not installed")
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        result = subprocess.run(
            ["actionlint", str(workflow_path)],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0, f"actionlint failed:\n{result.stdout}\n{result.stderr}"

    def test_val_gate_006_auto_merge_no_bypass(self):
        """VAL-GATE-006: auto-merge.yml respects droid-review check (no bypass)."""
        workflow_path = REPO_ROOT / ".github/workflows/auto-merge.yml"
        content = workflow_path.read_text()
        data = yaml.safe_load(content)

        # Must not contain bypass commands in any step's run block
        all_steps = []
        for job_name, job_data in data.get("jobs", {}).items():
            all_steps.extend(job_data.get("steps", []))
        run_blocks = [s.get("run", "") for s in all_steps if s.get("run")]
        for run_block in run_blocks:
            assert "--admin" not in run_block, f"Bypass --admin found in run block: {run_block}"
            assert "--force" not in run_block, f"Bypass --force found in run block: {run_block}"

        # Must use shared-workflows/auto-merge (respects check status)
        steps = data["jobs"]["auto-merge"]["steps"]
        auto_merge_step = next(
            (s for s in steps if "auto-merge" in s.get("uses", "")),
            None
        )
        assert auto_merge_step is not None, "auto-merge step using shared-workflows/auto-merge not found"
        assert "shared-workflows/auto-merge" in auto_merge_step["uses"]

        # Must have correct triggers
        triggers = data[True]  # YAML parses 'on:' as True key
        assert "pull_request_target" in triggers

    def test_val_gate_007_ci_ok_checks_droid_review(self):
        """VAL-GATE-007: ci-ok gate checks droid-review status."""
        workflow_path = REPO_ROOT / ".github/workflows/ci.yml"
        data = yaml.safe_load(workflow_path.read_text())

        # ci-ok job must exist
        assert "ci-ok" in data["jobs"]
        ci_ok_job = data["jobs"]["ci-ok"]

        # Must depend on test job
        assert "test" in ci_ok_job.get("needs", [])

        # Must have step that runs check_droid_review.sh
        steps = ci_ok_job["steps"]
        check_step = next(
            (s for s in steps if "check_droid_review.sh" in s.get("run", "")),
            None
        )
        assert check_step is not None

        # Must not be continue-on-error
        assert check_step.get("continue-on-error") is not True


class TestCrossAreaAuditGate:
    """VAL-CROSS-029/030/031/032: Audit gate integration tests."""

    @pytest.fixture
    def droid_review_data(self):
        """Load droid-review.yml workflow."""
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        return yaml.safe_load(workflow_path.read_text())

    def _get_droid_action_step(self, data):
        """Extract the droid-action step from the workflow."""
        steps = data["jobs"]["droid-review"]["steps"]
        return next(s for s in steps if "droid-action" in s.get("uses", ""))

    def test_val_cross_029_high_severity_blocks(self, droid_review_data):
        """VAL-CROSS-029: droid-review advisory on High severity findings (no block)."""
        droid_step = self._get_droid_action_step(droid_review_data)
        # security_block_on_high must be present and "false" (Advisory mode)
        assert droid_step["with"]["security_block_on_high"] == "false"
        # security_block_on_critical must also be present/true (default or explicit)
        if "security_block_on_critical" in droid_step["with"]:
            assert droid_step["with"]["security_block_on_critical"] != "false"

    def test_val_cross_030_failed_review_blocks_merge(self):
        """VAL-CROSS-030: Failed droid-review blocks auto-merge (integration test)."""
        # This is an integration test that verifies the workflow structure.
        # Actual runtime behavior is tested via GitHub Actions.
        auto_merge_path = REPO_ROOT / ".github/workflows/auto-merge.yml"
        content = auto_merge_path.read_text()

        # Verify no bypass mechanisms in any run block
        data = yaml.safe_load(content)
        all_steps = []
        for job_name, job_data in data.get("jobs", {}).items():
            all_steps.extend(job_data.get("steps", []))
        run_blocks = [s.get("run", "") for s in all_steps if s.get("run")]
        for run_block in run_blocks:
            assert "--admin" not in run_block
            assert "merge --force" not in run_block

        # Verify auto-merge uses shared workflow that respects checks
        steps = data["jobs"]["auto-merge"]["steps"]
        merge_step = next(
            (s for s in steps if "auto-merge" in s.get("uses", "")),
            None
        )
        assert merge_step is not None
        # Shared workflow respects check status by design

    def test_val_cross_031_low_medium_no_block(self, droid_review_data):
        """VAL-CROSS-031: Low/Medium findings do NOT block (default behavior)."""
        droid_step = self._get_droid_action_step(droid_review_data)
        # By default, only High and Critical block when explicitly enabled.
        # Low/Medium are advisory only.
        # Verify that security_block_on_medium is NOT set to "true"
        with_block = droid_step["with"]
        assert with_block.get("security_block_on_medium") != "true"
        assert with_block.get("security_block_on_low") != "true"

    def test_val_cross_032_both_configs_coexist(self, droid_review_data):
        """VAL-CROSS-032: Both configs coexist (high advisory + critical block)."""
        droid_step = self._get_droid_action_step(droid_review_data)
        with_block = droid_step["with"]

        # security_block_on_high must be "false" (Advisory mode)
        assert with_block["security_block_on_high"] == "false"

        # security_block_on_critical must be "true" (explicit or default)
        # If present, must not be "false"
        if "security_block_on_critical" in with_block:
            assert with_block["security_block_on_critical"] != "false"
        # If absent, default is "true" per droid-action documentation


class TestAutoMergeDispatchTokenGuard:
    """回归防护：auto-merge.yml 的合并步骤禁止回退到 GITHUB_TOKEN。

    根因（2026-08-15 两次事故，v0.29.0 / v0.30.0）：GitHub 的递归防护机制会
    抑制由 GITHUB_TOKEN 触发的 push 事件，导致 release-please 监听的
    push(paths: .release-please-manifest.json) 触发器失效，release PR
    合并后 tag/Release 不创建，发版链路断裂，只能靠手动 workflow_dispatch
    补救。修复方式是把 auto-merge 步骤的 GITHUB_TOKEN env 换成
    DISPATCH_TOKEN（PAT，不受该抑制机制影响）。本测试防止该改动被静默回退。
    """

    @pytest.fixture
    def auto_merge_step(self):
        """Load auto-merge.yml and return the shared-workflows/auto-merge step."""
        workflow_path = REPO_ROOT / ".github/workflows/auto-merge.yml"
        data = yaml.safe_load(workflow_path.read_text())
        steps = data["jobs"]["auto-merge"]["steps"]
        step = next(
            (s for s in steps if "shared-workflows/auto-merge" in s.get("uses", "")),
            None,
        )
        assert step is not None, "shared-workflows/auto-merge step not found"
        return step

    def test_auto_merge_uses_dispatch_token(self, auto_merge_step):
        """合并步骤的 GITHUB_TOKEN env 必须是 secrets.DISPATCH_TOKEN。"""
        env = auto_merge_step.get("env", {})
        assert "GITHUB_TOKEN" in env
        assert env["GITHUB_TOKEN"] == "${{ secrets.DISPATCH_TOKEN }}"

    def test_auto_merge_does_not_use_github_token_secret(self, auto_merge_step):
        """明确防止回退：GITHUB_TOKEN env 的值不能等于 secrets.GITHUB_TOKEN。"""
        env = auto_merge_step.get("env", {})
        assert env.get("GITHUB_TOKEN") != "${{ secrets.GITHUB_TOKEN }}"


class TestYAMLValidity:
    """Ensure all modified YAML files are valid."""

    def test_droid_review_yaml_valid(self):
        """droid-review.yml is valid YAML."""
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        content = workflow_path.read_text()
        data = yaml.safe_load(content)
        assert data is not None
        assert "jobs" in data
        assert "droid-review" in data["jobs"]

    def test_auto_merge_yaml_valid(self):
        """auto-merge.yml is valid YAML."""
        workflow_path = REPO_ROOT / ".github/workflows/auto-merge.yml"
        content = workflow_path.read_text()
        data = yaml.safe_load(content)
        assert data is not None
        assert "jobs" in data

    def test_ci_yaml_valid(self):
        """ci.yml is valid YAML."""
        workflow_path = REPO_ROOT / ".github/workflows/ci.yml"
        content = workflow_path.read_text()
        data = yaml.safe_load(content)
        assert data is not None
        assert "jobs" in data
        assert "ci-ok" in data["jobs"]


class TestDroidReviewDocsOnlySkip:
    """VAL-DRSKIP-*：droid-review docs-only 快速通过回归防护。

    2026-08-17 CI 异步化配套：纯文档 PR（全部变更文件为 *.md）跳过模型 review，
    全程从 ~17 min 降到 ~4 min。关键约束：必须 step 级跳过（job 结论为 success），
    绝不能 job 级 skip——check_droid_review.sh 把 skipped 判 BLOCK 会卡死 ci-ok。
    检测必须 fail-closed：文件列表为空/API 失败一律走完整 review。
    """

    @pytest.fixture
    def droid_review_steps(self):
        """Load droid-review.yml steps."""
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        data = yaml.safe_load(workflow_path.read_text())
        return data["jobs"]["droid-review"]["steps"]

    def test_docs_only_detect_step_exists(self, droid_review_steps):
        """VAL-DRSKIP-001: Detect docs-only PR step 存在且输出 skip。"""
        detect_step = next(
            (s for s in droid_review_steps if s.get("name") == "Detect docs-only PR"),
            None,
        )
        assert detect_step is not None, "Detect docs-only PR step not found"
        assert "skip=true" in detect_step["run"]
        assert "skip=false" in detect_step["run"]

    def test_docs_only_detect_fail_closed(self, droid_review_steps):
        """VAL-DRSKIP-002: 空文件列表/API 失败时 fail-closed（skip=false）。"""
        detect_step = next(
            (s for s in droid_review_steps if s.get("name") == "Detect docs-only PR"),
            None,
        )
        assert detect_step is not None
        # 空列表分支必须输出 skip=false（走完整 review），绝不能 skip=true
        empty_branch = detect_step["run"]
        assert "fail-closed" in empty_branch
        # 解析 run 块：空文件分支的 skip 值
        import re
        m = re.search(
            r'if \[ -z "\$FILES" \]; then.*?echo "(skip=\w+)"',
            empty_branch, re.DOTALL,
        )
        assert m is not None, "empty file list branch not found"
        assert m.group(1) == "skip=false", "empty file list must fail-closed to full review"

    def test_docs_only_detect_md_suffix_rule(self, droid_review_steps):
        """VAL-DRSKIP-003: 判定规则为 *.md 后缀（非 md 文件即全量 review）。"""
        detect_step = next(
            (s for s in droid_review_steps if s.get("name") == "Detect docs-only PR"),
            None,
        )
        assert detect_step is not None
        assert "grep -v '\\.md$'" in detect_step["run"]

    def test_review_steps_gated_on_skip(self, droid_review_steps):
        """VAL-DRSKIP-004: review 相关 steps 均有 skip 门控（step 级，非 job 级）。"""
        gated_names = {"Write BYOM settings file", "Pre-check credentials", "Run Droid Auto Review"}
        for name in gated_names:
            step = next(s for s in droid_review_steps if s.get("name") == name)
            cond = str(step.get("if", ""))
            assert "steps.docs_only.outputs.skip != 'true'" in cond, (
                f"step '{name}' must be gated on docs_only skip output"
            )

    def test_docs_only_job_not_skipped(self, droid_review_steps):
        """VAL-DRSKIP-005: job 级 if 不含 docs 跳过（保证 check run 结论为 success）。"""
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        data = yaml.safe_load(workflow_path.read_text())
        job_if = str(data["jobs"]["droid-review"].get("if", ""))
        assert "docs" not in job_if.lower(), (
            "job-level if must not skip docs PRs (check_droid_review.sh BLOCKs skipped)"
        )


class TestCiConcurrencyGuard:
    """VAL-CI-CONC-*：ci.yml concurrency 取消守卫回归防护。

    2026-08-17 审计发现：ci.yml 无 concurrency 配置，快速修复迭代的连续 push
    会堆叠多个完整 CI run（实测单 run 5 个并行 job，曾造成 8 分钟 runner 排队）。
    修复：按 PR 分组 + 非 main 分支 cancel-in-progress。本测试防止配置被静默移除，
    并防止误将 main 纳入取消范围（会截断发布链路 CI）。
    """

    @pytest.fixture
    def ci_concurrency(self):
        """Load ci.yml concurrency block."""
        workflow_path = REPO_ROOT / ".github/workflows/ci.yml"
        data = yaml.safe_load(workflow_path.read_text())
        assert "concurrency" in data, "ci.yml missing concurrency block"
        return data["concurrency"]

    def test_ci_concurrency_group_uses_pr_number(self, ci_concurrency):
        """VAL-CI-CONC-001: group 按 PR 号分组（同 PR 连续 push 复用同组）。"""
        group = ci_concurrency["group"]
        assert "github.event.pull_request.number" in str(group)
        # fallback 到 github.ref 覆盖 push 事件（main 无 PR 号）
        assert "github.ref" in str(group)

    def test_ci_concurrency_main_not_cancelled(self, ci_concurrency):
        """VAL-CI-CONC-002: main 分支禁止取消（发布链路 CI 必须完整跑完）。"""
        cancel = ci_concurrency["cancel-in-progress"]
        assert "!= 'refs/heads/main'" in str(cancel), (
            "cancel-in-progress 必须排除 main，否则 push 竞态会截断发布链路 CI"
        )
