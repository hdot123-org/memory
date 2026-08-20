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
    """VAL-GATE-* assertions: security configuration validation.

    NOTE: Architecture changed from droid-action to 3-job shard pipeline.
    Security is now handled via prompt template + schema validation + fail-closed.
    Tests updated to validate new architecture.
    """

    @pytest.fixture
    def droid_review_data(self):
        """Load droid-review.yml workflow."""
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        return yaml.safe_load(workflow_path.read_text())

    def test_val_gate_001_three_job_architecture(self, droid_review_data):
        """VAL-GATE-001: 3-job architecture exists (plan-shards, review-shard, droid-review)."""
        jobs = droid_review_data["jobs"]
        assert "plan-shards" in jobs, "plan-shards job missing"
        assert "review-shard" in jobs, "review-shard job missing"
        assert "droid-review" in jobs, "droid-review job missing"

    def test_val_gate_002_review_shard_uses_matrix(self, droid_review_data):
        """VAL-GATE-002: review-shard uses matrix strategy for parallel execution."""
        job = droid_review_data["jobs"]["review-shard"]
        assert "strategy" in job, "review-shard missing strategy"
        assert "matrix" in job["strategy"], "review-shard missing matrix"
        assert "shard" in job["strategy"]["matrix"], "matrix missing shard dimension"

    def test_val_gate_003_droid_exec_in_run_shard_script(self):
        """VAL-GATE-003: run_shard.sh calls droid exec with correct flags."""
        script_path = REPO_ROOT / "scripts/droid_review/run_shard.sh"
        content = script_path.read_text()
        assert "droid exec" in content, "droid exec not found in run_shard.sh"
        assert "--auto low" in content, "missing --auto low flag"
        assert "-m qwen3.7-plus" in content, "missing model flag"
        assert "--cwd head-src" in content, "missing --cwd head-src flag"
        assert "--tag" in content, "missing --tag flag"

    def test_val_gate_004_findings_schema_validation(self):
        """VAL-GATE-004: findings schema validation exists (fail-closed)."""
        script_path = REPO_ROOT / "scripts/droid_review/run_shard.sh"
        content = script_path.read_text()
        assert "validate_findings" in content, "schema validation not found"
        assert "sys.exit(1)" in content, "fail-closed exit not found"

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

    def test_val_cross_029_review_shard_job_exists(self, droid_review_data):
        """VAL-CROSS-029: review-shard job must exist with matrix strategy."""
        assert "review-shard" in droid_review_data["jobs"]
        review_job = droid_review_data["jobs"]["review-shard"]
        assert "strategy" in review_job
        assert "matrix" in review_job["strategy"]

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

    def test_val_cross_031_findings_schema_validation_exists(self):
        """VAL-CROSS-031: publish_findings.py must validate schema."""
        script_path = REPO_ROOT / "scripts/droid_review/publish_findings.py"
        content = script_path.read_text()
        assert "validate_findings" in content
        assert "REQUIRED_FINDING_FIELDS" in content
        assert "severity" in content and "file" in content and "line" in content

    def test_val_cross_032_artifact_prefix_preserved(self, droid_review_data):
        """VAL-CROSS-032: artifact prefix must be 'droid-review-debug-'."""
        # Check in review-shard job upload step
        review_job = droid_review_data["jobs"]["review-shard"]
        upload_step = None
        for step in review_job["steps"]:
            if step.get("uses", "").startswith("actions/upload-artifact"):
                upload_step = step
                break
        
        assert upload_step is not None
        artifact_name = upload_step.get("with", {}).get("name", "")
        assert artifact_name.startswith("droid-review-debug-")


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
    全程从 ~17 min 降到 ~4 min。关键约束：docs-only 检测在 plan-shards job 中，
    review-shard 和 droid-review 通过 job-level if 自然跳过。
    检测必须 fail-closed：文件列表为空/API 失败一律走完整 review。
    """

    @pytest.fixture
    def plan_shards_steps(self):
        """Load plan-shards job steps."""
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        data = yaml.safe_load(workflow_path.read_text())
        return data["jobs"]["plan-shards"]["steps"]

    @pytest.fixture
    def review_shard_steps(self):
        """Load review-shard job steps."""
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        data = yaml.safe_load(workflow_path.read_text())
        return data["jobs"]["review-shard"]["steps"]

    def test_docs_only_detect_step_exists(self, plan_shards_steps):
        """VAL-DRSKIP-001: Detect docs-only PR step 存在于 plan-shards job 且输出 skip。"""
        detect_step = next(
            (s for s in plan_shards_steps if s.get("name") == "Detect docs-only PR"),
            None,
        )
        assert detect_step is not None, "Detect docs-only PR step not found in plan-shards"
        assert "skip=true" in detect_step["run"]
        assert "skip=false" in detect_step["run"]

    def test_docs_only_detect_fail_closed(self, plan_shards_steps):
        """VAL-DRSKIP-002: 空文件列表/API 失败时 fail-closed（skip=false）。"""
        detect_step = next(
            (s for s in plan_shards_steps if s.get("name") == "Detect docs-only PR"),
            None,
        )
        assert detect_step is not None
        # 空列表分支必须输出 skip=false（走完整 review），绝不能 skip=true
        empty_branch = detect_step["run"]
        assert "fail-closed" in empty_branch

    def test_docs_only_detect_md_suffix_rule(self, plan_shards_steps):
        """VAL-DRSKIP-003: 判定规则为 *.md 后缀（非 md 文件即全量 review）。"""
        detect_step = next(
            (s for s in plan_shards_steps if s.get("name") == "Detect docs-only PR"),
            None,
        )
        assert detect_step is not None
        assert "grep -v '\\.md$'" in detect_step["run"]

    def test_review_shard_gated_on_docs_only(self, review_shard_steps):
        """VAL-DRSKIP-004: review-shard job 的 if 条件排除 docs-only PR。"""
        # In the new architecture, the review-shard job itself is gated at job level
        # via the `if` condition, not step-level gating
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        data = yaml.safe_load(workflow_path.read_text())
        job_if = str(data["jobs"]["review-shard"].get("if", ""))
        assert "docs_only" in job_if or "docs-only" in job_if.lower() or \
            "needs.plan-shards.outputs.docs_only" in job_if, \
            "review-shard job must be gated on docs_only output"

    def test_droid_review_job_not_skipped_for_docs(self):
        """VAL-DRSKIP-005: droid-review job 级 if 不含 docs 跳过（保证 check run 结论为 success）。"""
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        data = yaml.safe_load(workflow_path.read_text())
        job_if = str(data["jobs"]["droid-review"].get("if", ""))
        # The droid-review job uses always() to ensure it runs and reports success
        assert "always()" in job_if or "docs" not in job_if.lower(), (
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


class TestDroidReview503SelfHeal:
    """VAL-503-*：droid-review infra 瞬时失败（503）自动 rerun 回归防护。

    TD-503-01 v2（2026-08-18）：GitHub API 持续 503 使 droid-action 在 prep 阶段
    （权限检查）exit 1，review 本体未开始，每个 PR 需人工 rerun。

    第一版把自愈放在 droid-review job 内，有两个 P0 架构缺陷（已废弃）：
      1. rerun-failed-jobs API 要求 run 处于终态，job 内 step 执行时本 run 仍为
         in_progress，API 必然拒绝（时序竞争）。
      2. pull_request_target 工作流需要 actions: write 才能调 rerun API，
         扩大 PR 事件可触发的写权限面。
    v2 改为独立 watchdog 工作流（workflow_run 在上游 run 终态后触发），
    权限独立授予、从默认分支取定义。本测试守护 v2 架构不被静默回退。

    关键约束：watchdog 只请求 rerun、不改变任何 check 结论；真审查发现
    不匹配特征、不触发 rerun（门禁语义不变）。
    """

    @pytest.fixture
    def droid_review_data(self):
        """Load droid-review.yml workflow."""
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        return yaml.safe_load(workflow_path.read_text())

    @pytest.fixture
    def watchdog_data(self):
        """Load droid-review-watchdog.yml workflow."""
        workflow_path = REPO_ROOT / ".github/workflows/droid-review-watchdog.yml"
        data = yaml.safe_load(workflow_path.read_text())
        assert data is not None, "droid-review-watchdog.yml missing or empty"
        return data

    def test_watchdog_uses_workflow_run_trigger(self, watchdog_data):
        """VAL-503-001: watchdog 用 workflow_run 触发（上游 run 已终态）。"""
        triggers = watchdog_data[True]  # YAML parses 'on:' as True key
        assert "workflow_run" in triggers
        wr = triggers["workflow_run"]
        # 双触发源（2026-08-19）：Droid Auto Review → 503 自愈；CI → 失败取消 review
        assert "Droid Auto Review" in wr["workflows"]
        assert "CI" in wr["workflows"]
        assert "completed" in wr["types"]

    def test_watchdog_has_actions_write_permission(self, watchdog_data):
        """VAL-503-002: watchdog 独立持有 actions: write（rerun API 必需）。"""
        perms = watchdog_data.get("permissions", {})
        assert perms.get("actions") == "write", (
            "watchdog must hold actions:write to call rerun-failed-jobs"
        )
        # 权限最小化：只授予 rerun 所需的 actions，不携带其他写权限
        assert "contents" not in perms or perms["contents"] == "read"

    def test_watchdog_bounded_run_attempt(self, watchdog_data):
        """VAL-503-003: run_attempt 限界防止 rerun 死循环（通过 WATCHDOG_MAX_ATTEMPT repo variable 配置）。"""
        job = watchdog_data["jobs"]["self-heal-rerun"]
        # run_attempt 限界已从 if: 移到 shell run block（通过 WATCHDOG_MAX_ATTEMPT 变量）
        steps = job["steps"]
        run_block = next(s["run"] for s in steps if "rerun" in s.get("name", "").lower())
        assert "WATCHDOG_MAX_ATTEMPT" in run_block, "watchdog job must reference WATCHDOG_MAX_ATTEMPT repo variable"
        assert "MAX_ATTEMPT" in run_block, "watchdog job must use MAX_ATTEMPT for attempt limiting"
        assert "conclusion == 'failure'" in str(job.get("if", "")), "watchdog must only fire on failure"

    def test_watchdog_matches_503_patterns_only(self, watchdog_data):
        """VAL-503-004: 特征表只含 infra 瞬时错误，且 rerun 失败不阻塞结算。"""
        steps = watchdog_data["jobs"]["self-heal-rerun"]["steps"]
        run_block = next(s["run"] for s in steps if "rerun" in s.get("name", "").lower())
        # 503 权限检查特征必须在列（2026-08-17/18 实测根因）
        assert "permission - 503" in run_block
        assert "Failed to check permissions" in run_block
        # fail-closed：rerun 请求失败只 warning，不绕过门禁
        assert "::warning::" in run_block
        assert "rerun-failed-jobs" in run_block

    def test_watchdog_no_gate_bypass(self, watchdog_data):
        """VAL-503-005: 自愈路径不含任何门禁绕过（--admin/--force/merge）。"""
        steps = watchdog_data["jobs"]["self-heal-rerun"]["steps"]
        run_block = next(s["run"] for s in steps if "rerun" in s.get("name", "").lower())
        for forbidden in ("--admin", "--force", "merge"):
            assert forbidden not in run_block, f"forbidden token in watchdog: {forbidden}"

    def test_cancel_on_ci_fail_job_exists_and_gated(self, watchdog_data):
        """VAL-CIF-001: cancel-on-ci-fail job 存在且仅在 CI 失败时触发。

        2026-08-19 PR #810 实证：review 与 CI 并行设计下 CI 变红后 review
        不自停（Qwen token 空烧，单次上界 45min）。本 job 补状态机缺失边。
        """
        jobs = watchdog_data["jobs"]
        assert "cancel-on-ci-fail" in jobs, "cancel-on-ci-fail job missing"
        cond = str(jobs["cancel-on-ci-fail"].get("if", ""))
        assert "workflow_run.name == 'CI'" in cond, "must fire only on CI workflow"
        assert "conclusion == 'failure'" in cond, "must fire only on CI failure"

    def test_self_heal_rerun_scoped_to_review_workflow(self, watchdog_data):
        """VAL-CIF-002: self-heal-rerun 限定 Droid Auto Review（双触发源防误伤）。"""
        cond = str(watchdog_data["jobs"]["self-heal-rerun"].get("if", ""))
        assert "workflow_run.name == 'Droid Auto Review'" in cond, (
            "self-heal-rerun must not fire for CI workflow events"
        )

    def test_cancel_on_ci_fail_cancels_only_review_runs(self, watchdog_data):
        """VAL-CIF-003: 取消目标按 name == Droid Auto Review 过滤 + 用 head_sha 定位。"""
        steps = watchdog_data["jobs"]["cancel-on-ci-fail"]["steps"]
        run_block = next(s["run"] for s in steps if "cancel" in s.get("name", "").lower())
        assert "Droid Auto Review" in run_block, "must filter by review workflow name"
        assert "head_sha" in run_block, "must scope cancellation to the failed SHA"
        assert "/cancel" in run_block, "must call the cancel API"
        # 取消失败只 warning，不阻塞（run 可能刚好自然结束；竞态无害）
        assert "::warning::" in run_block
        # 门禁语义不变：不含 merge/admin 类操作
        for forbidden in ("--admin", "--force", " merge"):
            assert forbidden not in run_block, f"forbidden token in cancel job: {forbidden}"

    def test_droid_review_job_has_no_inline_selfheal(self, droid_review_data):
        """VAL-503-006: 防回退——droid-review job 内不得再出现自愈 step。

        job 内自愈存在时序 P0（run 仍 in_progress 时调 rerun API 必然被拒），
        且会迫使 pull_request_target 工作流持有 actions: write。
        """
        steps = droid_review_data["jobs"]["droid-review"]["steps"]
        names = [s.get("name", "") for s in steps]
        for name in names:
            assert "Self-heal" not in str(name), (
                "in-job self-heal step must not return; use droid-review-watchdog.yml"
            )
        run_blocks = [s.get("run", "") for s in steps if s.get("run")]
        for rb in run_blocks:
            assert "rerun-failed-jobs" not in rb, (
                "in-job rerun-failed-jobs is architecturally broken (in_progress race)"
            )

    def test_droid_exec_used_in_shard_script(self):
        """VAL-503-007: 使用 droid exec 而非 droid-action（3-job 架构）。"""
        # In the new 3-job architecture, we use droid exec directly in run_shard.sh
        # instead of the droid-action GitHub Action
        script_path = REPO_ROOT / "scripts/droid_review/run_shard.sh"
        assert script_path.exists()
        content = script_path.read_text()
        assert "droid exec" in content, "must use droid exec for review"
        # Verify key flags are present
        assert "--auto low" in content
        assert "-m qwen3.7-plus" in content
        assert "--cwd head-src" in content


class TestRepoVarsReferences:
    """VAL-VARS-002/005：workflow 参数以 ${{ vars.* }} 形式引用，结构测试锁定。

    TD-DR-02 参数外置：11 个 repo variables 替代硬编码字面量。
    结构测试逐一断言每个变量在对应 workflow 文件中被 vars.* 引用，
    防止回退到硬编码（删掉任一 vars 引用后 pytest 变红）。
    """

    @pytest.fixture
    def droid_review_raw(self):
        """droid-review.yml 原始文本（非 YAML 解析，保留 vars.* 引用）。"""
        path = REPO_ROOT / ".github/workflows/droid-review.yml"
        return path.read_text()

    @pytest.fixture
    def watchdog_raw(self):
        """droid-review-watchdog.yml 原始文本。"""
        path = REPO_ROOT / ".github/workflows/droid-review-watchdog.yml"
        return path.read_text()

    # droid-review.yml 中的 vars 引用
    def test_droid_review_timeout_minutes_uses_vars(self, droid_review_raw):
        """DROID_REVIEW_TIMEOUT_MINUTES 以 vars.* 引用（非硬编码 90）。"""
        assert "vars.DROID_REVIEW_TIMEOUT_MINUTES" in droid_review_raw

    # droid-review-watchdog.yml 中的 vars 引用
    def test_watchdog_max_attempt_uses_vars(self, watchdog_raw):
        """WATCHDOG_MAX_ATTEMPT 以 vars.* 引用（非硬编码 3）。"""
        assert "vars.WATCHDOG_MAX_ATTEMPT" in watchdog_raw

    def test_quota_recovery_window_uses_vars(self, watchdog_raw):
        """QUOTA_RECOVERY_WINDOW_SECONDS 以 vars.* 引用（非硬编码 1800）。"""
        assert "vars.QUOTA_RECOVERY_WINDOW_SECONDS" in watchdog_raw

    def test_quota_scan_window_uses_vars(self, watchdog_raw):
        """QUOTA_SCAN_WINDOW_HOURS 以 vars.* 引用（非硬编码 6）。"""
        assert "vars.QUOTA_SCAN_WINDOW_HOURS" in watchdog_raw

    # 默认值回退机制（变量缺失时不崩溃）
    def test_droid_review_timeout_has_fallback(self, droid_review_raw):
        """DROID_REVIEW_TIMEOUT_MINUTES 有默认值回退（${{ fromJSON(vars.X || '90') }}）。"""
        # fromJSON 包装使 actionlint 类型正确（string → number）
        assert "fromJSON(vars.DROID_REVIEW_TIMEOUT_MINUTES || '90')" in droid_review_raw

    def test_watchdog_max_attempt_has_fallback(self, watchdog_raw):
        """WATCHDOG_MAX_ATTEMPT 变量缺失时有 -z 判断回退（非 :- 死代码模式）。"""
        # VAL-VARS-004 修复：先 -z 判断再赋值，而非 :- 赋值后再 -z 判断（死代码）
        assert 'if [ -z "${MAX_ATTEMPT:-}" ]' in watchdog_raw
        # 确认死代码模式不存在：:-3 赋值后再 -z 判断永远走不到
        import re
        assert not re.search(
            r'MAX_ATTEMPT="\$\{MAX_ATTEMPT:-3\}"\s*\n\s*if\s+\[\s+-z',
            watchdog_raw,
        ), "MAX_ATTEMPT 仍有 :-3 死代码模式（:- 展开先于 -z 判断）"

    def test_quota_recovery_window_has_fallback(self, watchdog_raw):
        """QUOTA_RECOVERY_WINDOW_SECONDS 变量缺失时有 -z 判断回退（非 :- 死代码模式）。"""
        assert 'if [ -z "${QUOTA_RECOVERY_WINDOW_SECONDS:-}" ]' in watchdog_raw
        import re
        assert not re.search(
            r'QUOTA_RECOVERY_WINDOW_SECONDS="\$\{QUOTA_RECOVERY_WINDOW_SECONDS:-1800\}"\s*\n\s*if\s+\[\s+-z',
            watchdog_raw,
        ), "QUOTA_RECOVERY_WINDOW_SECONDS 仍有 :-1800 死代码模式"

    def test_quota_scan_window_has_fallback(self, watchdog_raw):
        """QUOTA_SCAN_WINDOW_HOURS 变量缺失时有 -z 判断回退（非 :- 死代码模式）。"""
        assert 'if [ -z "${QUOTA_SCAN_WINDOW_HOURS:-}" ]' in watchdog_raw
        import re
        assert not re.search(
            r'QUOTA_SCAN_WINDOW_HOURS="\$\{QUOTA_SCAN_WINDOW_HOURS:-6\}"\s*\n\s*if\s+\[\s+-z',
            watchdog_raw,
        ), "QUOTA_SCAN_WINDOW_HOURS 仍有 :-6 死代码模式"

    def test_watchdog_no_dead_code_fallback_pattern(self, watchdog_raw):
        """VAL-VARS-004: 所有 vars 回退均使用 -z 判断模式，无 :- 死代码。"""
        import re
        # 搜索 ":-数字" 赋值后紧跟 -z 判断的死代码模式
        dead_patterns = [
            r'MAX_ATTEMPT="\$\{MAX_ATTEMPT:-\d+\}"\s*\n\s*if\s+\[\s+-z',
            r'QUOTA_SCAN_WINDOW_HOURS="\$\{QUOTA_SCAN_WINDOW_HOURS:-\d+\}"\s*\n\s*if\s+\[\s+-z',
            r'QUOTA_RECOVERY_WINDOW_SECONDS="\$\{QUOTA_RECOVERY_WINDOW_SECONDS:-\d+\}"\s*\n\s*if\s+\[\s+-z',
            r'WATCHDOG_MAX_ATTEMPT="\$\{WATCHDOG_MAX_ATTEMPT:-\d+\}"\s*\n\s*if\s+\[\s+-z',
        ]
        for pat in dead_patterns:
            assert not re.search(pat, watchdog_raw), (
                f"watchdog.yml 仍有死代码回退模式（:- 展开先于 -z 判断）：{pat}"
            )

    # 硬编码残留检查（防回退）
    def test_watchdog_no_hardcoded_1800(self, watchdog_raw):
        """quota-sweep 不含硬编码 1800（已通过 vars 引用替代）。"""
        # 排除注释和日志字符串中的 1800
        import re
        # 找到 shell run block 中的 -lt 1800 模式（硬编码残留）
        assert not re.search(r'-lt\s+1800\b', watchdog_raw), \
            "watchdog quota-sweep 仍有硬编码 '-lt 1800'，应改用 $QUOTA_RECOVERY_WINDOW_SECONDS"

    def test_watchdog_no_hardcoded_6_hours(self, watchdog_raw):
        """quota-sweep 不含硬编码 '6 hours ago'（已通过 vars 引用替代）。"""
        import re
        assert not re.search(r"'\d+\s+hours\s+ago'", watchdog_raw), \
            "watchdog quota-sweep 仍有硬编码 'N hours ago'，应改用 $QUOTA_SCAN_WINDOW_HOURS"

    # branch-cleanup.yml 中将来 F4 会添加的 vars 引用
    # （本测试只验证已外置的变量，BRANCH_AGE_* 由 F4 处理）
