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
        """VAL-GATE-004: Existing droid-action inputs unchanged."""
        droid_step = self._get_droid_action_step(droid_review_data)
        with_block = droid_step["with"]

        # All original inputs must be present
        assert "factory_api_key" in with_block
        assert "automatic_review" in with_block
        assert "automatic_security_review" in with_block
        assert "security_review_model" in with_block
        assert "review_model" in with_block
        assert "allowed_bots" in with_block

        # Values must match originals
        assert with_block["factory_api_key"] == "${{ secrets.FACTORY_API_KEY }}"
        assert with_block["automatic_review"] is True
        assert with_block["automatic_security_review"] is True
        assert with_block["security_review_model"] == "qwen3.7-plus"
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
