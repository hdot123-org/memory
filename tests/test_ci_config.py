"""
CI configuration tests for trust chain reconstruction mission.

Tests for VAL-GATE-* assertions (Audit Gate) and VAL-CROSS-029/030/031/032.
Validates YAML structure of droid-review.yml, auto-merge.yml, and ci.yml.
"""

import functools
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# M4 门禁切换收尾契约（gate-contract-tests，VAL-GATE-101/110/111/112）
# ---------------------------------------------------------------------------

# 七步切换（风险升序）实际落地为 6 个原子 PR：setup-labels 与 governance 合并为
# #1050（同属 governance 域、共用同一 composite action），scan 与 heartbeat 合并
# 为 #1071（同属 per-repo 定时 thin caller 对）。PR 号是 M4 收尾时刻的既成历史
# 事实，可与 squash commit 尾注交叉验证（git log --format='%s' -- <workflow 文件>）。
M4_SWITCH_PRS = {
    1048: {"steps": ("branch-cleanup",), "workflows": ("branch-cleanup.yml",)},
    1050: {"steps": ("setup-labels", "governance"), "workflows": ("setup-labels.yml", "evolution-governance.yml")},
    1066: {"steps": ("droid-review",), "workflows": ("droid-review.yml",)},
    1069: {"steps": ("watchdog",), "workflows": ("droid-review-watchdog.yml",)},
    1070: {"steps": ("auto-merge",), "workflows": ("auto-merge.yml",)},
    1071: {
        "steps": ("evolution-scan", "evolution-heartbeat"),
        "workflows": ("evolution-scan.yml", "evolution-heartbeat.yml"),
    },
}

# 不抽取 workflows（architecture §6：memory-core 自有代码测试与发版）——任何
# 切换 PR 触碰即 VAL-GATE-112 范围纪律违规。
M4_NEVER_SWITCHED_WORKFLOWS = ("ci.yml", "qa.yml", "release-please.yml", "release-and-dispatch.yml")


@functools.lru_cache(maxsize=1)
def _gh_memory_api_available() -> bool:
    """gh CLI 存在且能只读访问 hdot123-org/memory（公开仓，任意有效 token 即可）。"""
    if shutil.which("gh") is None:
        return False
    probe = subprocess.run(
        ["gh", "api", "repos/hdot123-org/memory", "--jq", ".full_name"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    return probe.returncode == 0


@functools.cache
def _m4_switch_pr_merged_at(pr_number: int) -> str:
    """切换 PR 的合并时间戳（ISO8601 Zulu，同格式字符串可按字典序比较时间）。"""
    result = subprocess.run(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--repo",
            "hdot123-org/memory",
            "--json",
            "mergedAt",
            "--jq",
            ".mergedAt",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"gh pr view {pr_number}（mergedAt）失败: {result.stderr.strip()}"
    return result.stdout.strip()


@functools.cache
def _m4_switch_pr_changed_files(pr_number: int) -> tuple[str, ...]:
    """切换 PR 的变更文件清单（gh pr diff --name-only，VAL-GATE-112 契约证据面）。"""
    result = subprocess.run(
        ["gh", "pr", "diff", str(pr_number), "--repo", "hdot123-org/memory", "--name-only"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"gh pr diff {pr_number} --name-only 失败: {result.stderr.strip()}"
    return tuple(line.strip() for line in result.stdout.splitlines() if line.strip())


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
        assert "hdot123-org/infra-core/.github/workflows/setup-labels.yml@v0.11.1" in uses_str

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
        assert "hdot123-org/infra-core/actions/governance-check@v0.11.1" in uses_str

    def test_governance_protected_patterns_parity(self):
        """governance thin caller 保护路径与切换前内联 grep 全集对等

        四类保护路径：
        1. .evolution/**
        2. scripts/** (整个目录，防模块投毒)
        3. .github/workflows/evolution-*.yml
        4. .github/CODEOWNERS
        """
        path = REPO_ROOT / ".github/workflows/evolution-governance.yml"
        data = yaml.safe_load(path.read_text())
        jobs = data.get("jobs", {})
        job = list(jobs.values())[0]
        steps = job.get("steps", [])
        step = steps[0]
        with_block = step.get("with", {})
        patterns = with_block.get("protected-patterns", "")

        # 验证四类模式全部存在
        assert ".evolution/**" in patterns
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
        caller 必须委托该 workflow（uses 字节级指向 droid-review-shards.yml@v0.11.1）。"""
        shards_job = droid_review_data["jobs"]["shards"]
        uses_str = shards_job.get("uses", "")
        assert uses_str == "hdot123-org/infra-core/.github/workflows/droid-review-shards.yml@v0.11.1", (
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
        step 仍被本扫描覆盖）；执行体委托 infra-core reusable，merge action
        引用与零红判定由引擎仓 test_auto_merge_workflow_contract 锁定。
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
            "hdot123-org/infra-core/.github/workflows/auto-merge-pipeline.yml@v0.11.1"
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
        """caller 是纯 uses 委托（执行体在 infra-core，merge 步走引擎仓 actions/auto-merge）。"""
        assert auto_merge_calling_job.get("uses") == (
            "hdot123-org/infra-core/.github/workflows/auto-merge-pipeline.yml@v0.11.1"
        )
        assert auto_merge_calling_job.get("steps") is None, "thin caller 不得保留内联 step"

    def test_auto_merge_uses_dispatch_token(self, auto_merge_calling_job):
        """DISPATCH_TOKEN 必须经显式具名 secret 转发给 reusable（snake 单形态）。

        M5 R1(3) 终态：infra-core #82 已将 callee 契约切换为 snake_case
        （required dispatch_token），caller 收敛纯 snake。禁止恢复 hyphen
        旧名或双写：callee 声明面严格校验下，未声明多余键/缺失 required 键均
        → startup_failure（2026-08-30 snake-only 期实证，run 33295631722）。
        #86 双形态兼容窗后双写实测可过（07:20Z）——早期「-/_ 键名归一化重复键」
        机制归因有误，已推翻；终态仍收敛 snake 单形态，单形态在 callee 任一
        形态下都合法。
        """
        secrets_block = auto_merge_calling_job.get("secrets", {})
        assert secrets_block.get("dispatch_token") == "${{ secrets.DISPATCH_TOKEN }}"
        assert "dispatch-token" not in secrets_block, (
            "hyphen 键违反 snake 单形态终态（callee 严格校验拒绝未声明键），禁止恢复"
        )

    def test_auto_merge_does_not_use_github_token_secret(self, auto_merge_calling_job):
        """明确防止回退：转发的不能是 secrets.GITHUB_TOKEN，且禁止 secrets: inherit。"""
        secrets_block = auto_merge_calling_job.get("secrets", {})
        assert secrets_block.get("dispatch_token") != "${{ secrets.GITHUB_TOKEN }}"
        raw = (REPO_ROOT / ".github/workflows/auto-merge.yml").read_text()
        assert "secrets: inherit" not in raw, "禁止 secrets: inherit（凭证显式传入，防漂移）"


class TestAutoMergeThinCallerContract:
    """VAL-GATE-106（M4 gate-watchdog-automerge）：auto-merge thin caller 契约。

    触发面（四名单 workflow_run / pull_request_target / schedule / dispatch）、
    事件门控（workflow_run 仅 conclusion==success）、concurrency 留在 caller
    （github 事件上下文只在 caller 求值）；resolve+triage+merge 执行体委托
    infra-core auto-merge-pipeline.yml——merge action 已于 M6 收编为引擎仓
    actions/auto-merge（VAL-HARD-104，原共享仓退役归档），
    由引擎仓 TestReusablePipelineTemplateContract 锁定。
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
        assert job.get("uses") == "hdot123-org/infra-core/.github/workflows/auto-merge-pipeline.yml@v0.11.1"
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


class TestScanHeartbeatThinCallerContract:
    """VAL-GATE-108/109/113（M4 gate-scan-heartbeat）：scan/heartbeat thin caller 契约。

    文件名 evolution-scan.yml 字节级保留（heartbeat 按 SCANNER_WORKFLOW 文件名
    解析）、schedule cron INFRA-578 错峰位（13,43 与 47 */2）、workflow_dispatch、
    concurrency、workflow 名、secrets 显式转发（禁 inherit）——全部留在本仓
    caller 文件；执行体委托 infra-core reusable（模板契约由 infra-core 侧
    test_evolution_scan_heartbeat_workflow.py 锁定，VAL-GATE-108 环境契约
    DISPATCH_TOKEN/LINEAR_API_KEY/PYTHONSAFEPATH/pip install -e ./label-ensure/
    evolution-history cache 在 reusable 内保持）。
    """

    @pytest.fixture
    def scan_data(self):
        path = REPO_ROOT / ".github/workflows/evolution-scan.yml"
        return yaml.safe_load(path.read_text())

    @pytest.fixture
    def heartbeat_data(self):
        path = REPO_ROOT / ".github/workflows/evolution-heartbeat.yml"
        return yaml.safe_load(path.read_text())

    def test_scan_workflow_name_byte_exact(self, scan_data):
        """VAL-GATE-108/VAL-CROSS-005: workflow 名字节级为 'Evolution Scan'。"""
        assert scan_data["name"] == "Evolution Scan"

    def test_scan_filename_preserved(self):
        """VAL-GATE-108: 文件名字节级 evolution-scan.yml（heartbeat 解析依赖）。"""
        assert (REPO_ROOT / ".github/workflows/evolution-scan.yml").exists()

    def test_scan_triggers_exact(self, scan_data):
        """schedule cron INFRA-578 错峰 '13,43 * * * *' + workflow_dispatch。"""
        triggers = scan_data.get(True, {}) or scan_data.get("on", {})
        assert triggers["schedule"] == [{"cron": "13,43 * * * *"}]
        assert triggers["workflow_dispatch"] == {}

    def test_scan_concurrency_preserved(self, scan_data):
        conc = scan_data["concurrency"]
        assert conc["group"] == "evolution-scan"
        assert conc["cancel-in-progress"] is False

    def test_scan_single_job_delegation(self, scan_data):
        """scan job 纯 uses 委托 infra-core reusable，无本地 steps。

        INFRA-651: uses 钉 tag v0.11.1（与 pyproject 引擎 pin 同版本）——禁浮动
        @main，钉 @v0.11.1；浮动期间 infra-core 模板先行漂移会让本仓定时管道
        run 级 startup_failure（M5 键名切换窗 6h 断链实证）。升级 = pyproject pin
        + 此处 tag 同 PR 双写。
        """
        jobs = scan_data["jobs"]
        assert list(jobs.keys()) == ["scan"]
        job = jobs["scan"]
        assert job.get("uses") == "hdot123-org/infra-core/.github/workflows/evolution-scan.yml@v0.11.1"
        assert job.get("steps") is None

    def test_scan_secrets_explicit_named_mapping(self, scan_data):
        """VAL-GATE-113: DISPATCH_TOKEN + LINEAR_API_KEY 显式转发，禁 secrets: inherit。

        M5 R1(3) 终态（infra-core #82 后）：纯 snake_case。禁止 hyphen 旧名
        （required secret 读不到）或双写（callee 严格校验拒绝未声明多余键；
        #86 双形态兼容窗后可过，终态仍收敛 snake 单形态）。
        """
        secrets = scan_data["jobs"]["scan"].get("secrets", {})
        assert secrets.get("dispatch_token") == "${{ secrets.DISPATCH_TOKEN }}"
        assert secrets.get("linear_api_key") == "${{ secrets.LINEAR_API_KEY }}"
        assert "dispatch-token" not in secrets, (
            "hyphen 键违反 snake 单形态终态（callee 严格校验拒绝未声明键），禁止恢复"
        )
        assert "linear-api-key" not in secrets, (
            "hyphen 键违反 snake 单形态终态（callee 严格校验拒绝未声明键），禁止恢复"
        )

    def test_scan_calling_job_permissions_match_callee_needs(self, scan_data):
        """调用 job 权限 = callee 所需集合（contents read + issues write）。"""
        assert scan_data["jobs"]["scan"].get("permissions") == {"contents": "read", "issues": "write"}

    def test_heartbeat_workflow_name_byte_exact(self, heartbeat_data):
        """VAL-GATE-109: workflow 名字节级为 'Evolution Heartbeat'。"""
        assert heartbeat_data["name"] == "Evolution Heartbeat"

    def test_heartbeat_triggers_exact(self, heartbeat_data):
        """schedule cron INFRA-578 错峰 '47 */2 * * *' + workflow_dispatch。"""
        triggers = heartbeat_data.get(True, {}) or heartbeat_data.get("on", {})
        assert triggers["schedule"] == [{"cron": "47 */2 * * *"}]
        assert triggers["workflow_dispatch"] == {}

    def test_heartbeat_concurrency_preserved(self, heartbeat_data):
        conc = heartbeat_data["concurrency"]
        assert conc["group"] == "evolution-heartbeat"
        assert conc["cancel-in-progress"] is False

    def test_heartbeat_single_job_delegation(self, heartbeat_data):
        """heartbeat job 纯 uses 委托；SCANNER_WORKFLOW 契约由引擎仓锁定。

        INFRA-651: uses 钉 tag v0.11.1，与 scan caller 及 pyproject 引擎 pin
        同版本（模板/引擎版本锁定，禁浮动 @main，钉 @v0.11.1）。
        """
        jobs = heartbeat_data["jobs"]
        assert list(jobs.keys()) == ["heartbeat"]
        job = jobs["heartbeat"]
        assert job.get("uses") == "hdot123-org/infra-core/.github/workflows/evolution-heartbeat.yml@v0.11.1"
        assert job.get("steps") is None

    def test_heartbeat_secrets_explicit_named_mapping(self, heartbeat_data):
        """VAL-GATE-113: DISPATCH_TOKEN 显式转发（M5 R1(3) 终态纯 snake）。"""
        secrets = heartbeat_data["jobs"]["heartbeat"].get("secrets", {})
        assert secrets.get("dispatch_token") == "${{ secrets.DISPATCH_TOKEN }}"
        assert "dispatch-token" not in secrets, (
            "hyphen 键违反 snake 单形态终态（callee 严格校验拒绝未声明键），禁止恢复"
        )

    def test_heartbeat_engine_scanner_workflow_constant(self):
        """VAL-GATE-109(d): 引擎 SCANNER_WORKFLOW = "evolution-scan.yml" 字节精确。

        对安装的 infra-core 引擎源码做字节级 grep（契约 Evidence 原文口径）。
        不走 import：engine/__init__ 会连带 import evolution_scanner，其裸名
        evolution_utils 与本仓 scripts/ 同名模块在 pytest 进程内可能碰撞
        （P1-A module poisoning 同型），源码 grep 免疫该干扰且更贴近契约。
        """
        import importlib.util

        spec = importlib.util.find_spec("infra_core")
        assert spec and spec.origin, "infra_core must be installed (pyproject pin)"
        engine_src = Path(spec.origin).parent / "engine" / "evolution_heartbeat.py"
        content = engine_src.read_text()
        assert 'SCANNER_WORKFLOW = "evolution-scan.yml"' in content, (
            "infra-core 引擎 SCANNER_WORKFLOW 必须字节精确指向本仓文件名 evolution-scan.yml"
        )

    def test_thin_caller_tags_match_engine_pin(self, scan_data, heartbeat_data):
        """INFRA-651: thin caller uses 钉的 tag 必须与 pyproject 引擎 pin 同版本。

        引擎（pip install -e . 按 pyproject pin 装 infra-core 引擎模块）与
        reusable 模板（uses: ...@tag）版本分裂时，infra-core main 的破坏性
        模板变更会绕过 pin 瞬时打进本仓定时管道——M5 键名切换窗（#1071/
        #1075）双通道 run 级 startup_failure 6h 的直接机理。升级 infra-core
        = pyproject pin + 两个 uses tag 同 PR 三写，本测试机械 enforce。
        """
        pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        import re

        pin_match = re.search(r"infra-core @ git\+\S+?@v([\d.]+)", pyproject)
        assert pin_match, "pyproject 必须以 git+...@vX.Y.Z 形式 pin infra-core"
        pinned = "v" + pin_match.group(1)

        for data, name in ((scan_data, "evolution-scan.yml"), (heartbeat_data, "evolution-heartbeat.yml")):
            jobs = data["jobs"]
            job = next(iter(jobs.values()))
            uses = job.get("uses", "")
            assert uses.endswith(f"@{pinned}"), (
                f"{name} 的 uses 必须钉在与 pyproject 引擎 pin 一致的 {pinned}，"
                f"当前: {uses}（升级需 pyproject pin + uses tag 同 PR 双写）"
            )
            assert not uses.endswith("@main"), f"{name} 禁止浮动 @main 引用（INFRA-651：模板漂移绕过引擎 pin）"


class TestOrgRefsAnonymouslyResolvable:
    """INFRA-651（reopen #3）：公共仓引用的 org reusable/action 必须可匿名解析。

    事故链（2026-09-01 14:56Z → 2026-09-02 03:37Z，约 13h 定时管道零 job 停摆）：
    本仓转公开而 infra-core 仍私有 → 公共仓无法解析私有 reusable workflow，
    scan/heartbeat 全部定时 run run 级 startup_failure（零 job）→ 仓内互拉
    监控（INFRA-578/588）因同源引用一起下线、公共仓 cron 槽位被 load-shed
    丢弃 → EVOLUTION_HEARTBEAT_STALE 第 4 次触发（self-audit 恢复后补报）。
    infra-core 转公开 + DISPATCH_TOKEN 补 Actions 权限（INFRA-722）后恢复。

    本守护把「org 依赖仓可见性回退」的发现时机从 scanner 事后数小时提前到
    下一次 CI 即拦截：匿名 HTTP 探针逐个解析 uses 目标（私有仓 → 404）。
    与 test_thin_caller_tags_match_engine_pin（版本锁定）互补：那把锁管
    「引哪个版本」，这把锁管「匿名能不能解析到」。
    """

    @staticmethod
    def _collect_org_uses() -> dict[str, set[str]]:
        """收集全仓 workflows 的 hdot123-org/* uses 引用（目标 → ref 集合）。

        YAML 树遍历而非文本 grep：同时覆盖 job 级 reusable workflow 与
        step 级 composite action（infra-core/actions/*），且免疫注释行。
        解析成本为微秒级（十几个 YAML 文件），各测试直接调用免 fixture。
        """

        def _walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "uses" and isinstance(value, str):
                        yield value
                    else:
                        yield from _walk(value)
            elif isinstance(node, list):
                for item in node:
                    yield from _walk(item)

        found: dict[str, set[str]] = {}
        for path in sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml")):
            for uses in _walk(yaml.safe_load(path.read_text(encoding="utf-8"))):
                if uses.startswith("hdot123-org/") and "@" in uses:
                    target, _, ref = uses.rpartition("@")
                    found.setdefault(target, set()).add(ref)
        return found

    def _org_uses_refs(self) -> dict[str, set[str]]:
        found = self._collect_org_uses()
        assert found, "本仓管道全部委托 hdot123-org/*（M4 thin caller 架构），uses 引用不可能为空"
        return found

    def test_org_refs_are_version_tags(self):
        """全部 org uses 引用钉 vX.Y.Z 版本 tag，禁浮动分支。

        test_thin_caller_tags_match_engine_pin 只覆盖 scan/heartbeat 两个
        caller 与 pyproject pin 的一致性；本断言把钉 tag 纪律推广到全部 org
        引用面（auto-merge/branch-cleanup/droid-review/watchdog/setup-labels/
        governance，#1096 曾一次性钉 8 处）——浮动分支让 infra-core 声明面
        先行漂移绕过引擎 pin（M5 键名切换窗 6h 断链实证）。
        """
        import re

        org_uses_refs = self._org_uses_refs()
        violations = [
            f"{target}@{ref}"
            for target, refs in sorted(org_uses_refs.items())
            for ref in sorted(refs)
            if not re.fullmatch(r"v\d+\.\d+\.\d+", ref)
        ]
        assert not violations, (
            "org uses 引用必须钉 vX.Y.Z 版本 tag（INFRA-651：浮动分支让 infra-core "
            f"先行漂移绕过引擎 pin）：{violations}"
        )

    def test_org_refs_anonymously_resolvable(self):
        """每个 org uses 目标必须可匿名 HTTP 解析（公共仓依赖可见性守护）。

        探针 = curl HEAD https://github.com/<org>/<repo>/archive/<ref>.tar.gz
        （匿名、跟随重定向）：公共仓 + 有效 tag → 200；私有/已删除 → 404。
        GitHub 限制公共仓不得引用私有 reusable workflow/action——违反时所有
        引用该目标的 run 直接 run 级 startup_failure（零 job），包括本守护
        所在的 CI 本身，因此探针失败 = 即时红灯而非静默断链。
        网络级故障（DNS/超时）→ skip（本地离线开发容错）；HTTP 4xx/5xx →
        fail（可见性回退/引用失效，不允许被网络抖动掩盖）。
        """
        org_uses_refs = self._org_uses_refs()
        offline: list[str] = []
        violations: list[str] = []
        for target, refs in sorted(org_uses_refs.items()):
            repo = target.split("/")[1]  # hdot123-org/<repo>/{.github/workflows|actions}/...
            for ref in sorted(refs):
                url = f"https://github.com/hdot123-org/{repo}/archive/{ref}.tar.gz"
                probe = subprocess.run(
                    ["curl", "-sI", "-o", "/dev/null", "-w", "%{http_code}", "-L", "--max-time", "30", url],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if probe.returncode != 0:
                    offline.append(f"{url} (curl exit {probe.returncode})")
                    continue
                status = probe.stdout.strip()
                if status.isdigit() and int(status) >= 400:
                    violations.append(
                        f"{target}@{ref} → HTTP {status}（私有/已删除：公共仓定时管道将 "
                        "run 级 startup_failure 零 job，INFRA-651 reopen #3 事故类）"
                    )
        assert not violations, "org uses 引用存在不可匿名解析的目标:\n" + "\n".join(violations)
        if offline:
            pytest.skip(f"网络不可用，跳过匿名解析守护: {offline}")


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
        """VAL-GATE-113: 四个预算 vars 必须以 with: 转发（snake 单形态，含默认值回退）。

        M5 R1(3) 终态（infra-core #82 后）：禁止 hyphen 旧名或双写——
        callee 声明面严格校验拒绝未声明多余键（snake-only 期双写实测
        startup_failure；#86 双形态兼容窗后可过，终态仍收敛 snake 单形态）。
        """
        with_block = droid_review_data["jobs"]["shards"].get("with", {})
        assert with_block.get("shard_max_files") == "${{ vars.SHARD_MAX_FILES || '25' }}"
        assert with_block.get("shard_max_count") == "${{ vars.SHARD_MAX_COUNT || '6' }}"
        assert with_block.get("shard_timeout_minutes") == "${{ vars.SHARD_TIMEOUT_MINUTES || '45' }}"
        assert with_block.get("shard_max_parallel") == "${{ vars.SHARD_MAX_PARALLEL || '3' }}"
        for legacy in ("shard-max-files", "shard-max-count", "shard-max-timeout-minutes", "shard-max-parallel"):
            assert legacy not in with_block, (
                f"{legacy} hyphen 键违反 snake 单形态终态（callee 严格校验拒绝未声明键），禁止恢复"
            )

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
        """VAL-503-003: run_attempt 限界防止 rerun 死循环（M4 切换后）。

        执行体迁入 infra-core droid-review-watchdog-handlers.yml（引擎仓模板测试
        test_droid_review_watchdog_handlers_workflow 锁定 MAX_ATTEMPT 限界与 -z
        回退）；caller 锁定委托关系——run_attempt/max_attempt 必须显式转发
        （snake 单形态终态；双写在 callee snake-only 期实测 startup_failure
        ——多余未声明键被严格校验拒绝，非键名归一化）。"""
        job = watchdog_data["jobs"]["self-heal-rerun"]
        assert "conclusion == 'failure'" in str(job.get("if", "")), "watchdog must only fire on failure"
        with_block = job.get("with", {})
        assert with_block.get("run_attempt") == "${{ github.event.workflow_run.run_attempt }}", (
            "run_attempt 必须经 with 转发给 reusable workflow"
        )
        assert with_block.get("max_attempt") == "${{ vars.WATCHDOG_MAX_ATTEMPT || '3' }}", (
            "max_attempt 必须转发 vars.WATCHDOG_MAX_ATTEMPT（caller 层 || '3' 回退）"
        )
        assert "run-attempt" not in with_block, (
            "hyphen 键违反 snake 单形态终态（callee 严格校验拒绝未声明键），禁止恢复"
        )
        assert "max-attempt" not in with_block, (
            "hyphen 键违反 snake 单形态终态（callee 严格校验拒绝未声明键），禁止恢复"
        )

    def test_watchdog_matches_503_patterns_only(self, watchdog_data):
        """VAL-503-004（M4 切换后）：503 特征表随执行体迁入 infra-core reusable
        （引擎仓 test_droid_review_watchdog_handlers_workflow.TestSelfHealHandlerBody
        锁定特征表与 rerun-failed-jobs fail-closed 语义）；caller 锁定委托——
        self-heal-rerun 必须是纯 uses 委托 job（零内联 run step）。"""
        job = watchdog_data["jobs"]["self-heal-rerun"]
        assert ".github/workflows/droid-review-watchdog-handlers.yml@" in job.get("uses", ""), (
            "self-heal-rerun 必须委托 infra-core reusable workflow"
        )
        assert job.get("steps") is None, "handler 执行体已迁出，caller 不得保留内联 step"

    def test_watchdog_no_gate_bypass(self, watchdog_data):
        """VAL-503-005（M4 切换后）：caller 全部 run block 零 bypass token
        （含 "merge" 子串——quota-sweep 本地 job 也在扫描面内）；
        handler 执行体在引擎仓，其模板测试同样锁 no bypass。"""
        for job_name, job in watchdog_data["jobs"].items():
            for step in job.get("steps") or []:
                run_block = step.get("run", "")
                for forbidden in ("--admin", "--force", "merge"):
                    assert forbidden not in run_block, f"forbidden token in {job_name}: {forbidden}"

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
        """VAL-CIF-003（M4 切换后）：取消过滤逻辑（name == Droid Auto Review +
        head_sha 定位 + /cancel API）随执行体迁入 infra-core reusable（引擎仓
        TestCancelOnCiFailHandlerBody 锁定）；caller 锁定委托与 head_sha 转发。"""
        job = watchdog_data["jobs"]["cancel-on-ci-fail"]
        assert ".github/workflows/droid-review-watchdog-handlers.yml@" in job.get("uses", ""), (
            "cancel-on-ci-fail 必须委托 infra-core reusable workflow"
        )
        with_block = job.get("with", {})
        assert with_block.get("mode") == "cancel-on-ci-fail"
        assert with_block.get("head_sha") == "${{ github.event.workflow_run.head_sha }}", (
            "head_sha 必须经 with 转发（取消范围锚定失败 CI 的 head SHA）"
        )
        assert "head-sha" not in with_block, "hyphen 键违反 snake 单形态终态（callee 严格校验拒绝未声明键），禁止恢复"

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


class TestWatchdogThinCallerContract:
    """VAL-GATE-107（M4 gate-watchdog-automerge）：watchdog thin caller 契约。

    事件守卫（workflow_run.name 精确名比较）只在 caller 求值，必须留在本文件；
    quota-sweep 的 artifact 前缀过滤（droid-review-debug-）与 run 名过滤
    （Droid Auto Review）同样保留在 caller 文件可断言。self-heal-rerun /
    cancel-on-ci-fail 执行体迁入 infra-core droid-review-watchdog-handlers.yml
    （引擎仓 test_droid_review_watchdog_handlers_workflow 锁定执行体契约）。
    """

    @pytest.fixture
    def watchdog_data(self):
        workflow_path = REPO_ROOT / ".github/workflows/droid-review-watchdog.yml"
        return yaml.safe_load(workflow_path.read_text())

    def test_workflow_name_byte_exact(self, watchdog_data):
        """VAL-GATE-107: workflow 名字节级为 'Droid Review Watchdog'。"""
        assert watchdog_data["name"] == "Droid Review Watchdog"

    def test_workflow_run_listener_names_exact(self, watchdog_data):
        """监听名集合精确 = {Droid Auto Review, CI}，types=[completed]。"""
        triggers = watchdog_data.get(True, {}) or watchdog_data.get("on", {})
        wr = triggers["workflow_run"]
        assert sorted(wr["workflows"]) == ["CI", "Droid Auto Review"], f"监听名集合漂移: {wr['workflows']}"
        assert wr["types"] == ["completed"]

    def test_schedule_preserved(self, watchdog_data):
        """schedule '*/30 * * * *' 原样（quota-sweep 唯一触发源）。"""
        triggers = watchdog_data.get(True, {}) or watchdog_data.get("on", {})
        assert triggers["schedule"] == [{"cron": "*/30 * * * *"}]

    def test_concurrency_group_preserved(self, watchdog_data):
        conc = watchdog_data["concurrency"]
        assert conc["group"] == "droid-review-watchdog-${{ github.event.workflow_run.id }}"
        assert conc["cancel-in-progress"] is False

    def test_job_topology_three_jobs(self, watchdog_data):
        jobs = set(watchdog_data["jobs"].keys())
        assert jobs == {"self-heal-rerun", "cancel-on-ci-fail", "quota-sweep"}

    def test_handler_jobs_delegate_to_infra_core(self, watchdog_data):
        """两个 handler job 纯 uses 委托 + 调用 job 权限恰为 actions: write
        （callee 子集校验：缺声明 = startup_failure 零 job，INFRA-613 教训）。"""
        expected = "hdot123-org/infra-core/.github/workflows/droid-review-watchdog-handlers.yml@v0.11.1"
        for job_name in ("self-heal-rerun", "cancel-on-ci-fail"):
            job = watchdog_data["jobs"][job_name]
            assert job.get("uses") == expected, f"{job_name} 必须委托 infra-core reusable"
            assert job.get("runs-on") is None, "uses job 不得声明 runs-on"
            assert job.get("permissions") == {"actions": "write"}, f"{job_name} 调用 job 权限必须恰为 actions: write"

    def test_handler_modes_and_guards(self, watchdog_data):
        """VAL-GATE-107 核心断言：两个 if 守卫含精确名比较（留在 caller）。"""
        jobs = watchdog_data["jobs"]
        assert jobs["self-heal-rerun"]["with"]["mode"] == "self-heal-rerun"
        assert jobs["cancel-on-ci-fail"]["with"]["mode"] == "cancel-on-ci-fail"
        self_heal_if = str(jobs["self-heal-rerun"].get("if", ""))
        assert "github.event.workflow_run.name == 'Droid Auto Review'" in self_heal_if
        assert "github.event.workflow_run.conclusion == 'failure'" in self_heal_if
        cancel_if = str(jobs["cancel-on-ci-fail"].get("if", ""))
        assert "github.event.workflow_run.name == 'CI'" in cancel_if
        assert "github.event.workflow_run.conclusion == 'failure'" in cancel_if

    def test_quota_sweep_stays_local_with_prefix_filter(self, watchdog_data):
        """VAL-GATE-107 核心断言：quota-sweep 本地 job 保留 droid-review-debug-
        前缀过滤与 Droid Auto Review run 名过滤，runs-on 自建 runner。"""
        job = watchdog_data["jobs"]["quota-sweep"]
        assert job.get("uses") is None, "quota-sweep 必须是本地 job（前缀过滤契约在本文件）"
        assert job.get("if") == "github.event_name == 'schedule'"
        assert job.get("runs-on") == ["self-hosted", "pve-linux"]
        run_block = next(s["run"] for s in job["steps"] if s.get("run"))
        assert '.name | startswith("droid-review-debug-")' in run_block, (
            "quota-sweep 必须保留 droid-review-debug- artifact 前缀过滤"
        )
        assert '.name == \\"Droid Auto Review\\"' in run_block, "quota-sweep 必须保留 Droid Auto Review run 名过滤"


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
        """WATCHDOG_MAX_ATTEMPT 变量缺失时有回退（M4 切换后：caller 层 || '3'
        表达式回退；执行体层 -z 判断由引擎仓模板测试锁定）。"""
        assert "vars.WATCHDOG_MAX_ATTEMPT || '3'" in watchdog_raw

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


class TestM4NamingContractNet:
    """VAL-GATE-101/111（gate-contract-tests）：M4 全集 workflow 名 ⇄ 文件路径契约网。

    architecture §3：workflow 名 + check 名 + artifact 前缀 + 文件名构成隐式契约
    网，任何一处静默改名会杀死 auto-merge/watchdog/branch protection。各 thin
    caller 的细节契约由各切换 PR 落地的专项类锁定；本类把 M4 全集（8 个切换
    workflow + 2 个不抽取 + 2 个发版）的字节级 name ⇄ path 表收敛到单一视图——
    单点改名（含 GitHub 回退到路径派生显示名）立即红。
    """

    EXPECTED_WORKFLOW_NAMES = {
        "branch-cleanup.yml": "Branch Cleanup",
        "setup-labels.yml": "Setup Labels",
        "evolution-governance.yml": "Evolution Governance",
        "droid-review.yml": "Droid Auto Review",
        "droid-review-watchdog.yml": "Droid Review Watchdog",
        "auto-merge.yml": "Auto Merge",
        "evolution-scan.yml": "Evolution Scan",
        "evolution-heartbeat.yml": "Evolution Heartbeat",
        "ci.yml": "CI",
        "qa.yml": "QA",
        "release-please.yml": "Release Please",
        "release-and-dispatch.yml": "Release Pipeline",
    }

    @pytest.mark.parametrize(("filename", "expected_name"), sorted(EXPECTED_WORKFLOW_NAMES.items()))
    def test_workflow_name_byte_exact(self, filename: str, expected_name: str):
        data = yaml.safe_load((REPO_ROOT / ".github/workflows" / filename).read_text())
        assert data["name"] == expected_name, (
            f"{filename} workflow 名漂移（契约网单点改名会静默杀死 auto-merge/watchdog）："
            f"{data['name']!r} != {expected_name!r}"
        )


class TestM4SwitchoverDiscipline:
    """VAL-GATE-110/112（gate-contract-tests）：M4 七步切换的顺序、范围与保护面纪律。

    **顺序（VAL-GATE-112）**：7 步按风险升序落地为 6 个原子 PR，合并时间戳必须
    风险升序非降。唯一例外（编排器注 2026-08-29，已记录）：#1070（auto-merge
    thin caller）18:36:01Z 由**旧** auto-merge 流水线 bootstrap 合并——旧 caller
    合并了"切换它自己"的 PR；晚 13 分钟的 #1069（watchdog）18:49:08Z 由**新**
    caller 合并，属正确引导、功能无损（run 33268692153 / 33269255927 实证，
    详见 mission library gate-watchdog-automerge-facts.md）。断言把该例外作为
    显式记录处理：除该对外任何倒置都红；例外对若不再倒置（时间线被重写）也红。

    **范围（VAL-GATE-112）**：每个切换 PR 的 workflow 改动恰好是自己那一步的
    文件（爆炸半径纪律：坏切换 = 单文件 revert）；并集绝不触碰不抽取的
    ci.yml/qa.yml/release-*。非 workflow 伴生文件限白名单（测试伴生 +
    pyproject.toml；#1071 另含已记录的 memory_core/tools/version_sync.py
    mypy redundant-cast 清理——infra-core v0.5.1 标注精确返回类型使历史 cast
    冗余，随 pin bump v0.2.0→v0.5.1 同 PR 收敛）。

    **保护面（VAL-GATE-110）**：branch protection 全程零修改——切换的安全性
    恰恰建立在"名字保持所以保护规则无需改动"之上。M4 期间各切换 worker 的
    只读快照与本断言同源（gh api .../branches/main/protection）；本断言在 M4
    收尾时刻把终态钉进测试套。

    gh 依赖：三类断言均为 gh CLI 只读查询（契约证据面即 gh CLI）；gh 缺失、
    未认证或凭证无 protection 读权限时跳过（CI 浅克隆/无凭证环境不误报）。
    """

    # 已记录的顺序例外对（earlier_pr, later_pr)：auto-merge(#1070) bootstrap 早于
    # watchdog(#1069)——除该对外任何倒置即违规。
    DOCUMENTED_ORDER_INVERSIONS = frozenset({(1069, 1070)})

    @staticmethod
    def _require_gh() -> None:
        if not _gh_memory_api_available():
            pytest.skip("gh CLI 不可用或无法只读访问 hdot123-org/memory（跳过 gh 契约断言）")

    def test_switch_prs_merge_order_risk_ascending(self):
        """7 步切换（6 PR）合并时间戳风险升序非降，唯一例外 = 已记录的 bootstrap 对。"""
        self._require_gh()
        # PR 号升序 == 风险升序落地序（branch-cleanup → setup-labels+governance
        # → droid-review → watchdog → auto-merge → scan/heartbeat）
        ordered = sorted(M4_SWITCH_PRS)
        merged_at = {pr: _m4_switch_pr_merged_at(pr) for pr in ordered}
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            if (earlier, later) in self.DOCUMENTED_ORDER_INVERSIONS:
                # 例外必须真的处于倒置方向，否则例外记录失效（时间线被重写的信号）
                assert merged_at[later] <= merged_at[earlier], (
                    f"已记录例外对 #{earlier}→#{later} 不再倒置"
                    f"（{merged_at[earlier]} vs {merged_at[later]}）——"
                    "例外记录已失效，应从 DOCUMENTED_ORDER_INVERSIONS 移除并复核时间线"
                )
                continue
            assert merged_at[earlier] <= merged_at[later], (
                f"切换序倒置：#{earlier}（{merged_at[earlier]}）晚于 #{later}（{merged_at[later]}）——"
                f"风险升序契约违反（已记录例外：{sorted(self.DOCUMENTED_ORDER_INVERSIONS)}）"
            )

    @pytest.mark.parametrize("pr_number", sorted(M4_SWITCH_PRS))
    def test_switch_pr_workflow_scope_exact(self, pr_number: int):
        """每个切换 PR 的 workflow 改动恰好是本步文件集，伴生文件限白名单。"""
        self._require_gh()
        expected_wf = {f".github/workflows/{name}" for name in M4_SWITCH_PRS[pr_number]["workflows"]}
        files = set(_m4_switch_pr_changed_files(pr_number))
        actual_wf = {f for f in files if f.startswith(".github/workflows/")}
        assert actual_wf == expected_wf, (
            f"PR #{pr_number} workflow 改动越集（爆炸半径纪律）：{sorted(actual_wf)} != 本步集合 {sorted(expected_wf)}"
        )
        extra = files - expected_wf
        for path in sorted(extra):
            allowed = (
                path.startswith("tests/")
                or path == "pyproject.toml"
                or (pr_number == 1071 and path == "memory_core/tools/version_sync.py")
            )
            assert allowed, f"PR #{pr_number} 含白名单外伴生文件: {path}"

    def test_switch_prs_never_touch_unextracted_workflows(self):
        """切换 PR 并集绝不触碰 ci.yml/qa.yml/release-*（architecture §6 不抽取）。"""
        self._require_gh()
        forbidden = {f".github/workflows/{name}" for name in M4_NEVER_SWITCHED_WORKFLOWS}
        union: set[str] = set()
        for pr_number in M4_SWITCH_PRS:
            union.update(_m4_switch_pr_changed_files(pr_number))
        hit = sorted(union & forbidden)
        assert not hit, f"切换 PR 触碰不抽取 workflows（architecture §6）：{hit}"

    def test_branch_protection_required_contexts_unchanged(self):
        """VAL-GATE-110：required contexts 与 admin 强制在 M4 全程字节级不变。"""
        self._require_gh()
        result = subprocess.run(
            ["gh", "api", "repos/hdot123-org/memory/branches/main/protection"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "HTTP 403" in stderr or "HTTP 404" in stderr:
                pytest.skip(f"当前 gh 凭证无 branch protection 只读权（admin 域），跳过: {stderr}")
            pytest.fail(f"branch protection 只读查询失败: {stderr}")
        protection = json.loads(result.stdout)
        contexts = set(protection["required_status_checks"]["contexts"])
        assert contexts == {"ci-ok", "droid-review", "Block non-owner governance modifications"}, (
            f"required contexts 漂移（VAL-GATE-110 基线：三 required check 精确名）：{sorted(contexts)}"
        )
        assert protection["enforce_admins"]["enabled"] is True, (
            "enforce_admins 必须保持开启（--admin 旁路在 GitHub 层面堵死，铁律）"
        )
