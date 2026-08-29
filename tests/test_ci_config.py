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


class TestGateSetupLabelsGovernance:
    """VAL-GATE-102/115: setup-labels 与 governance 切换契约"""

    def test_setup_labels_is_thin_caller(self):
        """setup-labels.yml 是 thin caller（workflow_dispatch 触发，uses infra-core）"""
        path = REPO_ROOT / ".github/workflows/setup-labels.yml"
        data = yaml.safe_load(path.read_text())

        # 名字节级为 "Setup Labels"
        assert data["name"] == "Setup Labels"

        # 触发器为 workflow_dispatch
        triggers = data.get(True, {})  # YAML parses 'on:' as True key
        assert "workflow_dispatch" in triggers

        # 只有一个 job，且 uses infra-core reusable workflow
        jobs = data.get("jobs", {})
        assert len(jobs) == 1
        job = list(jobs.values())[0]
        uses_str = job.get("uses", "")
        assert "hdot123-org/infra-core/.github/workflows/setup-labels.yml@main" in uses_str

    def test_governance_thin_caller_name(self):
        """governance thin caller 名字节级为 'Evolution Governance'"""
        path = REPO_ROOT / ".github/workflows/evolution-governance.yml"
        data = yaml.safe_load(path.read_text())
        assert data["name"] == "Evolution Governance"

    def test_governance_job_display_name(self):
        """governance job 显示名字节级为 'Block non-owner governance modifications'

        这是 branch protection 第三个 required check。
        """
        path = REPO_ROOT / ".github/workflows/evolution-governance.yml"
        data = yaml.safe_load(path.read_text())
        jobs = data.get("jobs", {})
        assert len(jobs) == 1
        job = list(jobs.values())[0]
        assert job["name"] == "Block non-owner governance modifications"

    def test_governance_uses_infra_core_composite_action(self):
        """governance thin caller 使用 infra-core composite action"""
        path = REPO_ROOT / ".github/workflows/evolution-governance.yml"
        data = yaml.safe_load(path.read_text())
        jobs = data.get("jobs", {})
        job = list(jobs.values())[0]
        steps = job.get("steps", [])
        assert len(steps) == 1
        step = steps[0]
        uses_str = step.get("uses", "")
        assert "hdot123-org/infra-core/actions/governance-check@main" in uses_str

    def test_governance_protected_patterns_parity(self):
        """governance thin caller 保护路径与切换前内联 grep 全集对等

        五类保护路径：
        1. .evolution/**
        2. scripts/evolution_*.py
        3. scripts/** (整个目录，防模块投毒)
        4. .github/workflows/evolution-*.yml
        5. .github/CODEOWNERS
        """
        path = REPO_ROOT / ".github/workflows/evolution-governance.yml"
        data = yaml.safe_load(path.read_text())
        jobs = data.get("jobs", {})
        job = list(jobs.values())[0]
        steps = job.get("steps", [])
        step = steps[0]
        with_block = step.get("with", {})
        patterns = with_block.get("protected-patterns", "")

        # 验证五类模式全部存在
        assert ".evolution/**" in patterns
        assert "scripts/evolution_*.py" in patterns
        assert "scripts/**" in patterns
        assert ".github/workflows/evolution-*.yml" in patterns
        assert ".github/CODEOWNERS" in patterns

    def test_governance_owner_login_is_hdot123(self):
        """governance thin caller owner-login 为 hdot123"""
        path = REPO_ROOT / ".github/workflows/evolution-governance.yml"
        data = yaml.safe_load(path.read_text())
        jobs = data.get("jobs", {})
        job = list(jobs.values())[0]
        steps = job.get("steps", [])
        step = steps[0]
        with_block = step.get("with", {})
        assert with_block.get("owner-login") == "hdot123"


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
        """VAL-GATE-001（M4 切换后）：thin caller 双 job 拓扑——shards 调 reusable +
        本地 droid-review 聚合。原 3-job 流水线（setup/plan-shards/review-shard）迁入
        infra-core droid-review-shards.yml（其结构由引擎仓模板测试锁定）。"""
        jobs = droid_review_data["jobs"]
        assert "shards" in jobs, "shards call job missing"
        assert "droid-review" in jobs, "droid-review job missing"

    def test_val_gate_002_review_shard_uses_matrix(self, droid_review_data):
        """VAL-GATE-002（M4 切换后）：分片 matrix 迁入 infra-core reusable workflow，
        caller 必须委托该 workflow（uses 字节级指向 droid-review-shards.yml@main）。"""
        shards_job = droid_review_data["jobs"]["shards"]
        uses_str = shards_job.get("uses", "")
        assert uses_str == "hdot123-org/infra-core/.github/workflows/droid-review-shards.yml@main", (
            f"shards job 必须调用 infra-core reusable workflow，实际: {uses_str}"
        )

    def test_val_gate_shards_calling_job_grants_callee_permissions(self, droid_review_data):
        """shards 调用 job 的 permissions 必须覆盖 callee review-shard 的请求集。

        GitHub 约束：被调 workflow 的 job 只能获得调用 job 权限的子集（startup
        校验，不满足即 run startup_failure、零 job——2026-08-29 PR #1068 实测
        "nested job 'review-shard' is requesting 'actions: write, id-token: write',
        but is only allowed 'actions: none, id-token: none'"）。授权集与切换前
        本仓 review-shard job（851df10 L187-190）逐项等价：contents: read +
        actions: write + id-token: write（行为等价移植）。"""
        perms = droid_review_data["jobs"]["shards"].get("permissions")
        assert perms == {
            "contents": "read",
            "actions": "write",
            "id-token": "write",
        }, f"shards 调用 job 权限漂移（ callee 需要其超集语义）: {perms}"

    def test_val_gate_003_droid_exec_in_run_shard_script(self):
        """VAL-GATE-003: run_shard.sh calls droid exec with correct flags."""
        script_path = REPO_ROOT / "scripts/droid_review/run_shard.sh"
        content = script_path.read_text()
        assert "droid exec" in content, "droid exec not found in run_shard.sh"
        assert "--auto low" in content, "missing --auto low flag"
        assert "-m qwen3.7-plus" in content, "missing model flag"
        # shard-cwd-layout-fix 已绝对化 --cwd 路径（防 droid CLI 相对路径静默崩溃）
        assert "--cwd" in content, "missing --cwd flag"
        assert "GITHUB_WORKSPACE" in content and "head-src" in content, "missing absolute --cwd path"
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
        result = subprocess.run(["actionlint", str(workflow_path)], capture_output=True, text=True)
        assert result.returncode == 0, f"actionlint failed:\n{result.stdout}\n{result.stderr}"

    def test_val_gate_006_auto_merge_no_bypass(self):
        """VAL-GATE-006: auto-merge.yml respects droid-review check (M4 切换后).

        thin caller 零内联 run block——bypass token 结构性不存在（未来新增本地
        step 仍被本扫描覆盖）；执行体委托 infra-core reusable，shared-workflows
        pin 与零红判定由引擎仓 test_auto_merge_workflow_contract 锁定。
        """
        workflow_path = REPO_ROOT / ".github/workflows/auto-merge.yml"
        content = workflow_path.read_text()
        data = yaml.safe_load(content)

        # Must not contain bypass commands in any local run block
        for _job_name, job_data in data.get("jobs", {}).items():
            for step in job_data.get("steps") or []:
                run_block = step.get("run", "")
                assert "--admin" not in run_block, f"Bypass --admin found: {run_block}"
                assert "--force" not in run_block, f"Bypass --force found: {run_block}"

        # 执行体必须委托 infra-core reusable workflow
        jobs = data["jobs"]
        assert list(jobs.keys()) == ["auto-merge"], f"thin caller 单 job 拓扑漂移: {list(jobs.keys())}"
        assert jobs["auto-merge"].get("uses") == (
            "hdot123-org/infra-core/.github/workflows/auto-merge-pipeline.yml@main"
        )

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
        check_step = next((s for s in steps if "check_droid_review.sh" in s.get("run", "")), None)
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
        """VAL-CROSS-029（M4 切换后）：分片流水线经 shards call job 委托 infra-core，
        聚合 job 本地保留（check 名 `droid-review` 精确契约）。"""
        jobs = droid_review_data["jobs"]
        shards_job = jobs["shards"]
        assert ".github/workflows/droid-review-shards.yml@" in shards_job.get("uses", "")
        aggregate_job = jobs["droid-review"]
        assert aggregate_job.get("uses") is None, (
            "聚合 job 必须是本地 job（不得整体 uses reusable workflow，那会嵌套 check 名）"
        )

    def test_val_cross_030_failed_review_blocks_merge(self):
        """VAL-CROSS-030（M4 切换后）：失败 droid-review 阻断 auto-merge（结构等价）。

        caller 锁定：唯一 job 是 uses 委托 + 事件门控 if（workflow_run 仅
        conclusion==success 才进流水）；零红判定（statusCheckRollup 全绿才
        merge，含 advisory）在 infra-core reusable 执行体内实施并由其契约
        测试锁定（test_auto_merge_workflow_contract.py）。"""
        auto_merge_path = REPO_ROOT / ".github/workflows/auto-merge.yml"
        content = auto_merge_path.read_text()

        # Verify no bypass mechanisms in any local run block
        data = yaml.safe_load(content)
        for _job_name, job_data in data.get("jobs", {}).items():
            for step in job_data.get("steps") or []:
                run_block = step.get("run", "")
                assert "--admin" not in run_block
                assert "merge --force" not in run_block

        # caller 单 job 委托 + workflow_run 仅 success 才尝试合并（快路径门控）
        calling = data["jobs"]["auto-merge"]
        assert ".github/workflows/auto-merge-pipeline.yml@" in calling.get("uses", "")
        job_if = str(calling.get("if", ""))
        assert "github.event.workflow_run.conclusion == 'success'" in job_if

    def test_val_cross_031_findings_schema_validation_exists(self):
        """VAL-CROSS-031: publish_findings.py must validate schema."""
        script_path = REPO_ROOT / "scripts/droid_review/publish_findings.py"
        content = script_path.read_text()
        assert "validate_findings" in content
        assert "REQUIRED_FINDING_FIELDS" in content
        assert "severity" in content and "file" in content and "line" in content

    def test_val_cross_032_artifact_prefix_preserved(self, droid_review_data):
        """VAL-CROSS-032（M4 切换后）：artifact 前缀 `droid-review-debug-` 由
        infra-core reusable workflow 的 review-shard 上传（引擎仓模板测试
        test_droid_review_shards_workflow 锁定字节级前缀）；caller 侧锁定委托关系——
        分片 artifact 生产者必须仍是 droid-review-shards.yml。"""
        shards_job = droid_review_data["jobs"]["shards"]
        assert "droid-review-shards.yml@" in shards_job.get("uses", "")


class TestAutoMergeDispatchTokenGuard:
    """回归防护：auto-merge 的合并凭证禁止回退到 GITHUB_TOKEN（M4 切换后）。

    根因（2026-08-15 两次事故，v0.29.0 / v0.30.0）：GitHub 的递归防护机制会
    抑制由 GITHUB_TOKEN 触发的 push 事件，导致 release-please 监听的
    push(paths: .release-please-manifest.json) 触发器失效，release PR
    合并后 tag/Release 不创建，发版链路断裂，只能靠手动 workflow_dispatch
    补救。M4 切换后 caller 将 DISPATCH_TOKEN 经 workflow_call secrets 显式
    传给 infra-core reusable（引擎仓模板测试锁定 merge 步 env 接线），本测试
    防止 caller 侧转发被静默移除或改绑 GITHUB_TOKEN。
    """

    @pytest.fixture
    def auto_merge_calling_job(self):
        """Load auto-merge.yml and return the single calling job."""
        workflow_path = REPO_ROOT / ".github/workflows/auto-merge.yml"
        data = yaml.safe_load(workflow_path.read_text())
        jobs = data["jobs"]
        assert list(jobs.keys()) == ["auto-merge"], f"thin caller 单 job 拓扑漂移: {list(jobs.keys())}"
        return jobs["auto-merge"]

    def test_auto_merge_caller_is_reusable_delegation(self, auto_merge_calling_job):
        """caller 是纯 uses 委托（执行体在 infra-core，含 shared-workflows merge 步）。"""
        assert auto_merge_calling_job.get("uses") == (
            "hdot123-org/infra-core/.github/workflows/auto-merge-pipeline.yml@main"
        )
        assert auto_merge_calling_job.get("steps") is None, "thin caller 不得保留内联 step"

    def test_auto_merge_uses_dispatch_token(self, auto_merge_calling_job):
        """DISPATCH_TOKEN 必须经 secrets.dispatch-token 显式转发给 reusable。"""
        secrets_block = auto_merge_calling_job.get("secrets", {})
        assert secrets_block.get("dispatch-token") == "${{ secrets.DISPATCH_TOKEN }}"

    def test_auto_merge_does_not_use_github_token_secret(self, auto_merge_calling_job):
        """明确防止回退：转发的不能是 secrets.GITHUB_TOKEN，且禁止 secrets: inherit。"""
        secrets_block = auto_merge_calling_job.get("secrets", {})
        assert secrets_block.get("dispatch-token") != "${{ secrets.GITHUB_TOKEN }}"
        raw = (REPO_ROOT / ".github/workflows/auto-merge.yml").read_text()
        assert "secrets: inherit" not in raw, "禁止 secrets: inherit（凭证显式传入，防漂移）"


class TestAutoMergeThinCallerContract:
    """VAL-GATE-106（M4 gate-watchdog-automerge）：auto-merge thin caller 契约。

    触发面（四名单 workflow_run / pull_request_target / schedule / dispatch）、
    事件门控（workflow_run 仅 conclusion==success）、concurrency 留在 caller
    （github 事件上下文只在 caller 求值）；resolve+triage+merge 执行体委托
    infra-core auto-merge-pipeline.yml——shared-workflows@5a0fc1b merge pin
    冻结不动（M6 才合并），由引擎仓 TestReusablePipelineTemplateContract 锁定。
    """

    @pytest.fixture
    def auto_merge_data(self):
        workflow_path = REPO_ROOT / ".github/workflows/auto-merge.yml"
        return yaml.safe_load(workflow_path.read_text())

    def test_workflow_name_byte_exact(self, auto_merge_data):
        """VAL-GATE-106: workflow 名字节级为 'Auto Merge'。"""
        assert auto_merge_data["name"] == "Auto Merge"

    def test_workflow_run_listener_four_names_exact(self, auto_merge_data):
        """workflow_run 名单留在 caller 文件且字节级精确（四触发名 + completed）。"""
        triggers = auto_merge_data.get(True, {}) or auto_merge_data.get("on", {})
        wr = triggers["workflow_run"]
        assert wr["workflows"] == ["CI", "QA", "Droid Auto Review", "Evolution Governance"], (
            f"四名单漂移: {wr['workflows']}"
        )
        assert wr["types"] == ["completed"]

    def test_other_triggers_exact(self, auto_merge_data):
        """pull_request_target 三类 + schedule */10 + workflow_dispatch pr_number 原样。"""
        triggers = auto_merge_data.get(True, {}) or auto_merge_data.get("on", {})
        assert triggers["pull_request_target"]["types"] == ["opened", "synchronize", "reopened"]
        assert triggers["schedule"] == [{"cron": "*/10 * * * *"}]
        wd = triggers["workflow_dispatch"]["inputs"]["pr_number"]
        assert wd["required"] is False
        assert wd["type"] == "string"

    def test_concurrency_group_preserved(self, auto_merge_data):
        conc = auto_merge_data["concurrency"]
        assert conc["group"] == "auto-merge-pipeline"
        assert conc["cancel-in-progress"] is False

    def test_permissions_preserved(self, auto_merge_data):
        perms = auto_merge_data.get("permissions", {})
        assert perms == {"contents": "write", "pull-requests": "write", "checks": "read"}

    def test_single_job_delegation_with_event_guard(self, auto_merge_data):
        """单 job uses 委托 + 事件门控 if 留在 caller（workflow_run 仅 success 才进流水）。"""
        jobs = auto_merge_data["jobs"]
        assert list(jobs.keys()) == ["auto-merge"]
        job = jobs["auto-merge"]
        assert job.get("uses") == "hdot123-org/infra-core/.github/workflows/auto-merge-pipeline.yml@main"
        assert job.get("steps") is None
        job_if = str(job.get("if", ""))
        assert "github.event_name == 'pull_request_target'" in job_if
        assert "github.event_name == 'schedule'" in job_if
        assert "github.event_name == 'workflow_dispatch'" in job_if
        assert "(github.event_name == 'workflow_run' && github.event.workflow_run.conclusion == 'success')" in job_if, (
            "workflow_run 快路径门控（仅 success 尝试合并）必须留在 caller"
        )

    def test_calling_job_permissions_match_callee_needs(self, auto_merge_data):
        """调用 job 权限 = callee 所需集合（startup 子集校验，INFRA-613 教训）。"""
        job = auto_merge_data["jobs"]["auto-merge"]
        assert job.get("permissions") == {
            "contents": "write",
            "pull-requests": "write",
            "checks": "read",
        }


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
    """VAL-DRSKIP-*：droid-review docs-only 快速通过回归防护（M4 切换后）。

    2026-08-17 CI 异步化配套：纯文档 PR（全部变更文件为 *.md）跳过模型 review。
    M4 起 docs-only 检测与 review-shard 门控迁入 infra-core
    droid-review-shards.yml（引擎仓 test_droid_review_shards_workflow.
    TestDocsOnlyDetection 锁定 fail-closed 语义与 *.md 规则）；caller 侧锁定
    跳过决策信息（docs_only/shards 输出）必须转发给本地聚合 job。
    关键约束不变：docs-only PR 仍产出结论 success 的 `droid-review` check
    （VAL-DRSKIP-005），检测 fail-closed（引擎仓锁定）。
    """

    @pytest.fixture
    def droid_review_data(self):
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        return yaml.safe_load(workflow_path.read_text())

    @pytest.fixture
    def aggregate_step(self, droid_review_data):
        """本地 droid-review job 的聚合 composite step。"""
        steps = droid_review_data["jobs"]["droid-review"]["steps"]
        step = next((s for s in steps if "droid-review-aggregate" in s.get("uses", "")), None)
        assert step is not None, "droid-review job 缺少 droid-review-aggregate composite step"
        return step

    def test_docs_only_and_shards_forwarded_to_aggregate(self, aggregate_step):
        """VAL-DRSKIP-001/002/003/004（caller 等价）：docs_only 与 shards 输出
        必须转发给聚合 composite——发布端据此跳过 docs-only/空分片（check 仍 success）。"""
        with_block = aggregate_step.get("with", {})
        assert with_block.get("docs-only") == "${{ needs.shards.outputs.docs_only }}"
        assert with_block.get("shards") == "${{ needs.shards.outputs.shards }}"

    def test_droid_review_job_not_skipped_for_docs(self, droid_review_data):
        """VAL-DRSKIP-005: droid-review job 级 if 不含 docs 跳过（保证 check run 结论为 success）。

        job 级 if 门只允许 plan-shards 结果语义（plan_shards_ok），绝不允许按
        docs-only 跳过——check_droid_review.sh 对非 dependabot 的 skipped 判 BLOCK。
        """
        job_if = str(droid_review_data["jobs"]["droid-review"].get("if", ""))
        assert "always()" in job_if, "job-level if 必须含 always()"
        assert "plan_shards_ok" in job_if, "job-level if 必须挂 plan-shards 结果语义"
        assert "docs_only" not in job_if, "job-level if 不得按 docs-only 跳过（docs-only 必须产出 success check）"


class TestDroidReviewThinCallerContract:
    """VAL-GATE-101/103/111/113（M4 gate-droid-review）：droid-review thin caller 契约。

    check 名嵌套陷阱：reusable workflow 内部 job 的 check 名为 `外层/内层` 嵌套
    格式，branch protection / ci-ok（check_droid_review.sh 精确名查询）按
    `droid-review` 精确匹配。聚合 job 必须留在本地跑 composite action。
    """

    @pytest.fixture
    def droid_review_data(self):
        workflow_path = REPO_ROOT / ".github/workflows/droid-review.yml"
        return yaml.safe_load(workflow_path.read_text())

    def test_workflow_name_byte_exact(self, droid_review_data):
        """VAL-GATE-101: workflow 名字节级为 'Droid Auto Review'。"""
        assert droid_review_data["name"] == "Droid Auto Review"

    def test_trigger_surface_preserved(self, droid_review_data):
        """VAL-GATE-113: pull_request_target 四类事件 + workflow_dispatch 输入原样。"""
        triggers = droid_review_data.get(True, {}) or droid_review_data.get("on", {})
        prt = triggers["pull_request_target"]
        assert prt["types"] == ["opened", "ready_for_review", "reopened", "synchronize"]
        wd_inputs = triggers["workflow_dispatch"]["inputs"]
        assert wd_inputs["pr_number"]["type"] == "number"
        assert wd_inputs["pr_number"]["required"] is True
        assert wd_inputs["head_sha"]["type"] == "string"

    def test_concurrency_preserved(self, droid_review_data):
        """concurrency group 字节级保持（github.workflow 仍解析为 Droid Auto Review）。"""
        conc = droid_review_data["concurrency"]
        assert "${{ github.workflow }}-" in conc["group"]
        assert conc["cancel-in-progress"] is True

    def test_job_topology_exactly_two_jobs(self, droid_review_data):
        """caller 恰好两个 job：shards（call）+ droid-review（本地聚合）。"""
        jobs = set(droid_review_data["jobs"].keys())
        assert jobs == {"shards", "droid-review"}

    def test_shards_job_forwards_budget_vars(self, droid_review_data):
        """VAL-GATE-113: 四个预算 vars 必须以 with: 转发（含默认值回退）。"""
        with_block = droid_review_data["jobs"]["shards"].get("with", {})
        assert with_block.get("shard-max-files") == "${{ vars.SHARD_MAX_FILES || '25' }}"
        assert with_block.get("shard-max-count") == "${{ vars.SHARD_MAX_COUNT || '6' }}"
        assert with_block.get("shard-timeout-minutes") == "${{ vars.SHARD_TIMEOUT_MINUTES || '45' }}"
        assert with_block.get("shard-max-parallel") == "${{ vars.SHARD_MAX_PARALLEL || '3' }}"

    def test_shards_job_forwards_dispatch_inputs(self, droid_review_data):
        """workflow_dispatch 的 pr_number/head_sha 必须透传给 reusable workflow。"""
        with_block = droid_review_data["jobs"]["shards"].get("with", {})
        assert with_block.get("pr_number") == "${{ inputs.pr_number }}"
        assert with_block.get("head_sha") == "${{ inputs.head_sha }}"

    def test_secrets_explicitly_forwarded(self, droid_review_data):
        """VAL-GATE-113: secrets 必须显式转发（reusable 不隐式继承 caller secrets）。"""
        secrets_block = droid_review_data["jobs"]["shards"].get("secrets", {})
        assert secrets_block.get("FACTORY_API_KEY") == "${{ secrets.FACTORY_API_KEY }}"
        assert secrets_block.get("NVIDIA_KONG_PROXY_KEY") == "${{ secrets.NVIDIA_KONG_PROXY_KEY }}"

    def test_aggregate_job_is_local_with_composite(self, droid_review_data):
        """VAL-GATE-103 核心断言：聚合 job key `droid-review` 本地存在、无 name
        覆盖、步骤 uses 以 hdot123-org/infra-core/actions/ 开头、绝不调用
        reusable workflow（嵌套 check 名）。"""
        jobs = droid_review_data["jobs"]
        assert "droid-review" in jobs
        aggregate_job = jobs["droid-review"]
        # 无 name 属性（或精确 droid-review）——check 名必须保持 `droid-review`
        assert "name" not in aggregate_job or aggregate_job["name"] == "droid-review"
        # 本地 job（非整体 reusable 调用）
        assert "uses" not in aggregate_job
        assert aggregate_job.get("runs-on") == ["self-hosted", "pve-linux"]
        # 步骤调用 infra-core composite action
        steps = aggregate_job.get("steps", [])
        assert len(steps) == 1
        uses_str = steps[0].get("uses", "")
        assert uses_str.startswith("hdot123-org/infra-core/actions/"), (
            f"聚合步骤必须 uses infra-core composite action，实际: {uses_str}"
        )
        # 嵌套守卫：聚合 job 的任何 uses 不得指向 .github/workflows/
        for step in steps:
            assert ".github/workflows/" not in step.get("uses", ""), (
                "聚合 job 不得调用 reusable workflow（check 名会嵌套为 droid-review / <inner>）"
            )

    def test_aggregate_job_if_keeps_plan_success_semantics(self, droid_review_data):
        """VAL-GATE-103: 聚合 job if 保持 `always() && plan-shards 成功` 语义。"""
        job_if = str(droid_review_data["jobs"]["droid-review"].get("if", ""))
        assert "always()" in job_if
        assert "needs.shards.outputs.plan_shards_ok == 'true'" in job_if

    def test_aggregate_job_github_token_input(self, droid_review_data):
        """composite 内 secrets context 不可用：token 必须经 with 传入。"""
        steps = droid_review_data["jobs"]["droid-review"]["steps"]
        with_block = steps[0].get("with", {})
        assert with_block.get("github-token") == "${{ secrets.GITHUB_TOKEN }}"


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
        assert perms.get("actions") == "write", "watchdog must hold actions:write to call rerun-failed-jobs"
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
            assert "Self-heal" not in str(name), "in-job self-heal step must not return; use droid-review-watchdog.yml"
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
        # shard-cwd-layout-fix 已绝对化 --cwd 路径（防 droid CLI 相对路径静默崩溃）
        assert "--cwd" in content, "missing --cwd flag"
        assert "GITHUB_WORKSPACE" in content and "head-src" in content, "missing absolute --cwd path"


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
            assert not re.search(pat, watchdog_raw), f"watchdog.yml 仍有死代码回退模式（:- 展开先于 -z 判断）：{pat}"

    # 硬编码残留检查（防回退）
    def test_watchdog_no_hardcoded_1800(self, watchdog_raw):
        """quota-sweep 不含硬编码 1800（已通过 vars 引用替代）。"""
        # 排除注释和日志字符串中的 1800
        import re

        # 找到 shell run block 中的 -lt 1800 模式（硬编码残留）
        assert not re.search(r"-lt\s+1800\b", watchdog_raw), (
            "watchdog quota-sweep 仍有硬编码 '-lt 1800'，应改用 $QUOTA_RECOVERY_WINDOW_SECONDS"
        )

    def test_watchdog_no_hardcoded_6_hours(self, watchdog_raw):
        """quota-sweep 不含硬编码 '6 hours ago'（已通过 vars 引用替代）。"""
        import re

        assert not re.search(r"'\d+\s+hours\s+ago'", watchdog_raw), (
            "watchdog quota-sweep 仍有硬编码 'N hours ago'，应改用 $QUOTA_SCAN_WINDOW_HOURS"
        )

    # branch-cleanup.yml 中将来 F4 会添加的 vars 引用
    # （本测试只验证已外置的变量，BRANCH_AGE_* 由 F4 处理）


class TestBranchCleanupNamingContract:
    """M4-GATE-001: Branch Cleanup 命名契约测试

    验证 thin caller 保持原有命名，确保：
    1. workflow 名 'Branch Cleanup' 不变（auto-merge/workflow_run 依赖）
    2. job key 'cleanup' 不变（check 名契约）
    3. 调用 infra-core composite action
    4. 保留原有 triggers 和 permissions
    """

    @pytest.fixture
    def branch_cleanup_data(self):
        """加载 branch-cleanup.yml workflow"""
        workflow_path = REPO_ROOT / ".github/workflows/branch-cleanup.yml"
        return yaml.safe_load(workflow_path.read_text())

    def test_workflow_name_exact(self, branch_cleanup_data):
        """workflow 名必须精确为 'Branch Cleanup'"""
        assert branch_cleanup_data["name"] == "Branch Cleanup", f"workflow 名被修改: {branch_cleanup_data['name']}"

    def test_job_key_cleanup(self, branch_cleanup_data):
        """job key 必须为 'cleanup'"""
        jobs = branch_cleanup_data["jobs"]
        assert "cleanup" in jobs, "job key 'cleanup' 缺失"
        assert len(jobs) == 1, f"期望只有一个 job，实际: {list(jobs.keys())}"

    def test_calls_infra_core_composite_action(self, branch_cleanup_data):
        """必须调用 infra-core composite action"""
        job = branch_cleanup_data["jobs"]["cleanup"]
        steps = job.get("steps", [])

        # 找到 uses step
        uses_steps = [s for s in steps if "uses" in s]
        assert len(uses_steps) > 0, "未找到 uses step"

        uses_value = uses_steps[0]["uses"]
        assert "hdot123-org/infra-core/actions/branch-cleanup@" in uses_value, (
            f"未调用正确的 composite action: {uses_value}"
        )

    def test_triggers_preserved(self, branch_cleanup_data):
        """必须保留原有 triggers: schedule + pull_request + workflow_dispatch"""
        # YAML 解析时 "on:" 会变成 True: (YAML 关键字)
        triggers = branch_cleanup_data.get(True, {}) or branch_cleanup_data.get("on", {})
        assert "schedule" in triggers, "schedule trigger 缺失"
        assert "pull_request" in triggers, "pull_request trigger 缺失"
        assert "workflow_dispatch" in triggers, "workflow_dispatch trigger 缺失"

        # 验证 schedule cron
        schedule_list = triggers["schedule"]
        assert isinstance(schedule_list, list) and len(schedule_list) > 0
        assert schedule_list[0].get("cron") == "0 * * * *", f"cron 表达式被修改: {schedule_list[0].get('cron')}"

    def test_permissions_preserved(self, branch_cleanup_data):
        """必须保留原有 permissions"""
        perms = branch_cleanup_data.get("permissions", {})
        assert perms.get("contents") == "write"
        assert perms.get("issues") == "write"
        assert perms.get("pull-requests") == "read"

    def test_dispatch_token_forwarded(self, branch_cleanup_data):
        """DISPATCH_TOKEN 必须通过 inputs 转发"""
        job = branch_cleanup_data["jobs"]["cleanup"]
        steps = job.get("steps", [])

        # 找到 uses step
        uses_step = next((s for s in steps if "uses" in s), None)
        assert uses_step is not None, "未找到 uses step"

        with_block = uses_step.get("with", {})
        assert "dispatch-token" in with_block, "dispatch-token input 缺失"
        assert "secrets.DISPATCH_TOKEN" in with_block["dispatch-token"], "dispatch-token 未引用 secrets.DISPATCH_TOKEN"

    def test_workflow_dispatch_inputs(self, branch_cleanup_data):
        """workflow_dispatch 必须提供 mode 和 branch inputs"""
        triggers = branch_cleanup_data.get(True, {}) or branch_cleanup_data.get("on", {})
        wd = triggers.get("workflow_dispatch", {})
        inputs = wd.get("inputs", {})

        assert "mode" in inputs, "workflow_dispatch 缺少 mode input"
        assert inputs["mode"].get("type") == "choice", "mode input 应为 choice 类型"
        assert "scheduled" in inputs["mode"].get("options", []), "mode 选项必须包含 scheduled"
        assert "immediate" in inputs["mode"].get("options", []), "mode 选项必须包含 immediate"

        assert "branch" in inputs, "workflow_dispatch 缺少 branch input"
        assert inputs["branch"].get("type") == "string", "branch input 应为 string 类型"

    def test_branch_age_vars_forwarded(self, branch_cleanup_data):
        """VAL-GATE-113: thin caller 必须通过 with: 转发三个 vars.BRANCH_AGE_*（2026-08-27 vars context 修复）"""
        job = branch_cleanup_data["jobs"]["cleanup"]
        steps = job.get("steps", [])

        # 找到 uses step
        uses_step = next((s for s in steps if "uses" in s), None)
        assert uses_step is not None, "未找到 uses step"

        with_block = uses_step.get("with", {})
        # 三个 vars 转发必须存在
        assert "branch-age-merged-hours" in with_block, "branch-age-merged-hours input 缺失"
        assert "branch-age-closed-hours" in with_block, "branch-age-closed-hours input 缺失"
        assert "branch-age-orphan-hours" in with_block, "branch-age-orphan-hours input 缺失"
        # 验证引用 vars context（workflow 层合法）
        assert "vars.BRANCH_AGE_MERGED_HOURS" in with_block["branch-age-merged-hours"], (
            "branch-age-merged-hours 未引用 vars.BRANCH_AGE_MERGED_HOURS"
        )
        assert "vars.BRANCH_AGE_CLOSED_HOURS" in with_block["branch-age-closed-hours"], (
            "branch-age-closed-hours 未引用 vars.BRANCH_AGE_CLOSED_HOURS"
        )
        assert "vars.BRANCH_AGE_ORPHAN_HOURS" in with_block["branch-age-orphan-hours"], (
            "branch-age-orphan-hours 未引用 vars.BRANCH_AGE_ORPHAN_HOURS"
        )

    def test_linear_forwarding(self, branch_cleanup_data):
        """VAL-GATE-118/INFRA-586: thin caller 必须转发 Linear credentials 给 composite action

        composite action 的 branch_cleanup_issue.sh 依赖 LINEAR_API_KEY +
        LINEAR_PROJECT_ID 环境变量把 tracking issue 同步到正确 Linear project；
        caller 不转发则同步静默跳过（project 字段保持 null）。
        """
        job = branch_cleanup_data["jobs"]["cleanup"]
        steps = job.get("steps", [])

        # 找到 uses step
        uses_step = next((s for s in steps if "uses" in s), None)
        assert uses_step is not None, "未找到 uses step"

        with_block = uses_step.get("with", {})
        assert "linear-api-key" in with_block, "linear-api-key input 缺失"
        assert with_block["linear-api-key"] == "${{ secrets.LINEAR_API_KEY }}", (
            f"linear-api-key 应引用 secrets.LINEAR_API_KEY，实际: {with_block.get('linear-api-key')}"
        )
        assert "linear-project-id" in with_block, "linear-project-id input 缺失"
        assert with_block["linear-project-id"] == "${{ vars.LINEAR_PROJECT_MEMORY_CORE_ID }}", (
            f"linear-project-id 应引用 vars.LINEAR_PROJECT_MEMORY_CORE_ID，实际: {with_block.get('linear-project-id')}"
        )


class TestSetupVenvFastFail:
    """预装环境锁定第 3 层：setup-venv composite checkout 完整性 fast-fail

    checkout 残缺（半死 checkout，2026-08-27 runner-02/03 工作区中毒）时，
    composite 第一步必须立即以可操作错误失败，不让下游报迷惑性错误。
    """

    @pytest.fixture
    def setup_venv_data(self):
        """加载 setup-venv composite action"""
        action_path = REPO_ROOT / ".github/actions/setup-venv/action.yml"
        return yaml.safe_load(action_path.read_text())

    def test_fast_fail_is_first_step(self, setup_venv_data):
        """fast-fail 步骤必须是 composite 的第一步"""
        steps = setup_venv_data["runs"]["steps"]
        assert steps[0].get("name") == "Fast-fail on incomplete checkout", (
            f"第一步应为 fast-fail，实际: {steps[0].get('name')}"
        )

    def test_fast_fail_checks_key_files(self, setup_venv_data):
        """检查三件关键文件：.git / pyproject.toml / setup-venv action.yml 自身"""
        run = setup_venv_data["runs"]["steps"][0]["run"]
        for key in (".git", "pyproject.toml", ".github/actions/setup-venv/action.yml"):
            assert key in run, f"fast-fail 未检查关键文件：{key}"

    def test_fast_fail_carries_actionable_message(self, setup_venv_data):
        """错误消息含 'checkout 残缺' 指引并以非零退出"""
        run = setup_venv_data["runs"]["steps"][0]["run"]
        assert "checkout 残缺" in run
        assert "exit 1" in run
        assert "::error::" in run
