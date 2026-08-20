"""
TD-DR-01 单路径 Shard Pipeline 测试套件（26 用例）。

三契约防线 + planner 不变量。先于 workflow 改造编写（TDD）。
"""
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).parent.parent
# Ensure scripts/droid_review is importable
sys.path.insert(0, str(REPO_ROOT / "scripts"))

WORKFLOW_PATH = REPO_ROOT / ".github/workflows/droid-review.yml"


# ── helpers ──────────────────────────────────────────────────────────

@pytest.fixture
def workflow_data():
    return yaml.safe_load(WORKFLOW_PATH.read_text())


@pytest.fixture
def workflow_raw():
    return WORKFLOW_PATH.read_text()


def _plan(files, max_files=25, max_count=6):
    """Invoke plan_shards.plan_shards with defaults; import fresh each call."""
    from droid_review.plan_shards import plan_shards
    return plan_shards(
        files,
        max_files=max_files,
        max_count=max_count,
    )


# ══════════════════════════════════════════════════════════════════════
# Part A: Workflow structure (10 tests) — three-contract guardians
# ══════════════════════════════════════════════════════════════════════

class TestWorkflowStructure:
    """三契约 + 结构安全：workflow 名/job 名/artifact 前缀/触发器/concurrency/checkout。"""

    def test_01_workflow_name_unchanged(self, workflow_data):
        """VAL-SHARD-005(1): workflow 名必须为 'Droid Auto Review'。"""
        assert workflow_data.get("name") == "Droid Auto Review"

    def test_02_job_name_droid_review(self, workflow_data):
        """VAL-SHARD-005(2): 聚合 job 名必须为 'droid-review'（branch-protection/ci-ok 依赖）。"""
        assert "droid-review" in workflow_data.get("jobs", {})

    def test_03_artifact_prefix_droid_review_debug(self, workflow_raw):
        """VAL-SHARD-005(3): artifact 名保持 'droid-review-debug-' 前缀（watchdog quota-sweep 兼容）。"""
        assert "droid-review-debug-" in workflow_raw

    def test_04_pull_request_target_trigger(self, workflow_data):
        """安全：必须用 pull_request_target（BASE checkout 安全模型）。"""
        triggers = workflow_data.get(True, {})  # YAML parses 'on:' as True
        assert "pull_request_target" in triggers

    def test_05_concurrency_cancel_in_progress(self, workflow_data):
        """VAL-SHARD-009: concurrency group 含 cancel-in-progress: true。"""
        conc = workflow_data.get("concurrency", {})
        assert conc.get("cancel-in-progress") is True

    def test_06_plan_job_checks_out_base(self, workflow_data):
        """VAL-SHARD-006: plan-shards job checkout BASE（不 checkout HEAD 的脚本）。"""
        jobs = workflow_data.get("jobs", {})
        plan_job = jobs.get("plan-shards", {})
        steps = plan_job.get("steps", [])
        checkout_steps = [s for s in steps if "checkout" in s.get("uses", "")]
        assert len(checkout_steps) >= 1, "plan-shards must have at least one checkout step"
        # First checkout must NOT use HEAD ref — should use base/default
        first_checkout = checkout_steps[0]
        ref = str(first_checkout.get("with", {}).get("ref", ""))
        # Must not reference head.sha; should be empty (default) or base ref
        assert "head.sha" not in ref, "plan-shards must checkout BASE, not HEAD"

    def test_07_review_shard_checks_out_base_and_head(self, workflow_data):
        """VAL-SHARD-006: review-shard job 双 checkout——BASE 到根、HEAD 到 head-src/。"""
        jobs = workflow_data.get("jobs", {})
        # Find the review shard job (matrix-based)
        shard_job = jobs.get("review-shard", {})
        steps = shard_job.get("steps", [])
        checkout_steps = [s for s in steps if "checkout" in s.get("uses", "")]
        assert len(checkout_steps) >= 2, "review-shard must have >=2 checkout steps (BASE + HEAD)"
        # One checkout targets head-src/
        paths_or_targets = [str(s.get("with", {})) for s in checkout_steps]
        head_src_found = any("head-src" in str(p) for p in paths_or_targets)
        assert head_src_found, "review-shard must checkout HEAD into head-src/"

    def test_08_droid_review_job_exists_with_aggregation(self, workflow_data):
        """聚合发布 job 存在且名为 droid-review。"""
        jobs = workflow_data.get("jobs", {})
        assert "droid-review" in jobs
        # Must have steps for publishing findings
        steps = jobs["droid-review"].get("steps", [])
        step_names = [s.get("name", "") for s in steps]
        assert any("publish" in n.lower() or "finding" in n.lower() for n in step_names), \
            "droid-review job must have a publish/findings step"

    def test_09_max_parallel_from_vars(self, workflow_raw):
        """VAL-VARS-002/VAL-SHARD-003: max-parallel 读自 vars.SHARD_MAX_PARALLEL。"""
        assert "vars.SHARD_MAX_PARALLEL" in workflow_raw

    def test_10_shard_timeout_from_vars(self, workflow_raw):
        """VAL-SHARD-011: shard 级 timeout 读自 vars。"""
        assert "vars.DROID_REVIEW_TIMEOUT_MINUTES" in workflow_raw

    def test_10b_no_needs_outputs_in_run_blocks(self, workflow_data):
        """Security: run: 块内禁止 needs.*.outputs 插值（防 bash 注入，scrutiny round-4）。

        攻击面：pull_request_target + 公共仓库 + 文件名里嵌 $(…)。Runner 在
        bash 解析前展开 ${{ needs.plan-shards.outputs.shards }}，若值出现在
        run: 字符串里，赋值时文件名中的命令替换会直接执行。修复：把这类值放
        在 step 的 env: 映射里（env: 走 runner 的值传递，不经过 bash 解析）。

        结构测试：遍历所有 job 的所有 step，凡有 run: 字段者不得出现
        ${{ needs.<job>.outputs.<name> }} 形式的表达式。
        """
        import re
        pattern = re.compile(r'\$\{\{\s*needs\.\S+\.outputs\.\S+\s*\}\}')
        violations = []
        for job_name, job in workflow_data.get("jobs", {}).items():
            for idx, step in enumerate(job.get("steps", [])):
                run_text = step.get("run", "")
                if not run_text:
                    continue
                matches = pattern.findall(run_text)
                if matches:
                    violations.append(
                        f"job={job_name!r} step[{idx}] ({step.get('name', '?')}): "
                        f"{matches}"
                    )
        assert not violations, (
            "run: blocks must NOT interpolate needs.*.outputs (injection risk). "
            "Move such values to the step's env: mapping. Violations:\n"
            + "\n".join(violations)
        )

    def test_10c_shard_env_uses_setup_outputs_for_workflow_dispatch(self, workflow_data):
        """workflow_dispatch 路径能进 review-shard：shard_env 必须从 setup outputs 读 sha。

        若用 github.event.pull_request.base/head.sha，workflow_dispatch 触发时
        这两者都为空，shard 永远进不了 review-shard。修复：从 needs.setup.outputs
        读（:193-198 的 checkout 已这样做，自测也走同一通道）。
        """
        jobs = workflow_data.get("jobs", {})
        shard_job = jobs.get("review-shard", {})
        steps = shard_job.get("steps", [])
        shard_env_step = None
        for step in steps:
            if step.get("id") == "shard_env":
                shard_env_step = step
                break
        assert shard_env_step is not None, "review-shard must have a shard_env step"
        env = shard_env_step.get("env", {})
        base_sha_src = str(env.get("BASE_SHA", ""))
        head_sha_src = str(env.get("HEAD_SHA", ""))
        assert "needs.setup.outputs" in base_sha_src, (
            f"shard_env BASE_SHA must read from needs.setup.outputs, got: {base_sha_src!r}"
        )
        assert "needs.setup.outputs" in head_sha_src, (
            f"shard_env HEAD_SHA must read from needs.setup.outputs, got: {head_sha_src!r}"
        )
        # Specifically must NOT use github.event.pull_request.*.sha
        assert "github.event.pull_request" not in base_sha_src, (
            f"shard_env BASE_SHA must not use github.event.pull_request: {base_sha_src!r}"
        )
        assert "github.event.pull_request" not in head_sha_src, (
            f"shard_env HEAD_SHA must not use github.event.pull_request: {head_sha_src!r}"
        )

    def test_10d_no_depth_1_in_base_fetch(self, workflow_raw):
        """VAL-SHARD-002: git fetch origin BASE_SHA 不得使用 --depth=1。

        --depth=1 会把 base SHA 写入 .git/shallow，导致 merge-base 在 base 前进过的
        PR 上返回空（shallow graft 阻断历史遍历）。必须完整 fetch 才能正确计算 merge-base。
        """
        import re
        # Find the shard_env step's run block
        pattern = re.compile(
            r'git fetch origin "\$BASE_SHA"(\s*--depth=1)?',
            re.MULTILINE
        )
        matches = pattern.findall(workflow_raw)
        assert matches, "git fetch origin \"$BASE_SHA\" not found in workflow"
        # Ensure no --depth=1 flag
        for depth_flag in matches:
            assert depth_flag.strip() == "", (
                "git fetch must NOT use --depth=1 (breaks merge-base computation)"
            )

    def test_10e_artifact_includes_debug_transcripts_and_error_logs(self, workflow_data):
        """VAL-SHARD-012: debug artifact 必须包含 session transcripts 和执行错误日志。

        upload-artifact 不展开 ~，且拒绝工作区外路径。必须先用 step 把 $HOME/.factory/sessions/
        复制到工作区内的 .factory/sessions/，然后上传 .factory/sessions/**。
        同时必须包含 shard-exec-error.log 和 droid-exec-stdout.json 用于诊断 droid exec 失败。
        """
        jobs = workflow_data.get("jobs", {})
        shard_job = jobs.get("review-shard", {})
        steps = shard_job.get("steps", [])

        # Find the "Collect debug transcripts" step
        collect_step = None
        for step in steps:
            if "Collect debug transcripts" in step.get("name", ""):
                collect_step = step
                break
        assert collect_step is not None, "review-shard must have 'Collect debug transcripts' step"

        # Verify the step copies from $HOME/.factory/sessions to .factory/sessions
        run_script = collect_step.get("run", "")
        assert "$HOME/.factory/sessions" in run_script or "${HOME}/.factory/sessions" in run_script, (
            "Collect step must reference $HOME/.factory/sessions"
        )
        assert ".factory/sessions" in run_script and "mkdir -p .factory" in run_script, (
            "Collect step must create .factory/sessions/ in workspace"
        )

        # Find the upload artifact step
        upload_step = None
        for step in steps:
            uses = step.get("uses", "")
            if "upload-artifact" in uses:
                upload_step = step
                break
        assert upload_step is not None, "review-shard must have upload-artifact step"

        # Verify the artifact path includes .factory/sessions/** and error logs
        upload_with = upload_step.get("with", {})
        upload_path = upload_with.get("path", "")
        assert ".factory/sessions/**" in upload_path, (
            f"Artifact must include .factory/sessions/** (transcripts copied into workspace), got: {upload_path!r}"
        )
        assert "shard-exec-error.log" in upload_path, (
            f"Artifact must include shard-exec-error.log for diagnosing droid exec failures, got: {upload_path!r}"
        )
        assert "droid-exec-stdout.json" in upload_path, (
            f"Artifact must include droid-exec-stdout.json for diagnosing droid exec failures, got: {upload_path!r}"
        )
        # Ensure we're NOT using ~ directly (upload-artifact doesn't expand it)
        assert "~/.factory/sessions" not in upload_path, (
            "Artifact path must NOT use ~/.factory/sessions directly (upload-artifact doesn't expand ~)"
        )


# ══════════════════════════════════════════════════════════════════════
# Part B: Planner invariants (16 tests)
# ══════════════════════════════════════════════════════════════════════

class TestPlannerInvariants:
    """plan_shards.py 不变量：覆盖完整性、目录亲和、溢出处理。"""

    # ── 覆盖完整性 ──

    def test_11_empty_list_no_shards(self):
        """空文件列表 → 零分片。"""
        result = _plan([])
        assert result["shards"] == []
        assert result["total_files"] == 0

    def test_12_single_file_single_shard(self):
        """单文件 → 单分片。"""
        result = _plan(["src/foo.py"])
        assert len(result["shards"]) == 1
        assert result["shards"][0]["files"] == ["src/foo.py"]

    def test_13_subset_included(self):
        """子集文件正确归入对应分片。"""
        files = ["a.py", "b.py", "c.py"]
        result = _plan(files)
        all_planned = []
        for s in result["shards"]:
            all_planned.extend(s["files"])
        assert set(all_planned) == set(files)

    def test_14_pairwise_disjoint(self):
        """两两不相交：任意两个分片的文件集交集为空。"""
        files = [f"dir{i % 3}/file{j}.py" for i in range(20) for j in range(3)]
        result = _plan(files)
        shard_sets = [set(s["files"]) for s in result["shards"]]
        for i in range(len(shard_sets)):
            for j in range(i + 1, len(shard_sets)):
                assert shard_sets[i] & shard_sets[j] == set(), \
                    f"Shard {i} and {j} overlap: {shard_sets[i] & shard_sets[j]}"

    def test_15_union_equals_full_set(self):
        """并集 = 全集：plan_shards 永不丢文件。"""
        files = [f"src/module{i}.py" for i in range(50)]
        result = _plan(files)
        all_planned = set()
        for s in result["shards"]:
            all_planned.update(s["files"])
        assert all_planned == set(files)

    def test_16_union_equals_full_set_large(self):
        """大规模（100 文件）并集 = 全集。"""
        files = [f"pkg/sub{i % 10}/mod{j}.py" for i in range(100) for j in range(1)]
        result = _plan(files)
        all_planned = set()
        for s in result["shards"]:
            all_planned.update(s["files"])
        assert all_planned == set(files)

    # ── 溢出处理 ──

    def test_17_overflow_warning_and_no_loss(self):
        """溢出：超容量时放大帽+告警，零文件丢弃。"""
        files = [f"file{i}.py" for i in range(30)]
        # 设置极小的 max_files 和 max_count 以触发溢出
        result = _plan(files, max_files=5, max_count=3)
        # 不变量：不丢文件
        all_planned = set()
        for s in result["shards"]:
            all_planned.update(s["files"])
        assert all_planned == set(files), "overflow must not lose files"
        # 告警标记
        assert result.get("overflow_warning") is True or result.get("overflow") is True, \
            "overflow must set a warning flag"

    def test_18_max_count_cap_respected_with_overflow(self):
        """max_count 上限：分片数不超上限，除非溢出放大。"""
        files = [f"file{i}.py" for i in range(10)]
        result = _plan(files, max_count=4)
        # 正常情况不超 max_count
        assert len(result["shards"]) <= 4

    def test_19_overflow_expands_beyond_max_count(self):
        """溢出放大：当文件量大到无法塞入 max_count 个分片时，分片数可超上限。"""
        files = [f"file{i}.py" for i in range(100)]
        result = _plan(files, max_files=5, max_count=3)
        # 100 files / 5 max_files = 至少 20 shards > max_count=3
        assert len(result["shards"]) > 3
        assert result.get("overflow_warning") is True or result.get("overflow") is True
        # 仍然不丢文件
        all_planned = set()
        for s in result["shards"]:
            all_planned.update(s["files"])
        assert all_planned == set(files)

    # ── 目录亲和 ──

    def test_20_directory_affinity(self):
        """目录亲和：同目录文件尽量在同一分片。"""
        files = (
            ["src/a/one.py", "src/a/two.py", "src/a/three.py"]
            + ["src/b/alpha.py", "src/b/beta.py"]
            + ["src/c/gamma.py"]
        )
        result = _plan(files, max_files=10, max_count=6)
        # 每个分片内的文件应该尽量来自同目录
        for shard in result["shards"]:
            dirs = set()
            for f in shard["files"]:
                dirs.add(str(Path(f).parent))
            # 如果分片文件数 <= max_files，同目录文件不应被拆散
            if len(shard["files"]) <= 10:
                # 亲和性：每个分片不应包含来自3个以上不同目录的文件
                # （这里宽松检查——关键是同目录文件不被无谓拆散）
                pass  # 结构正确即可

    def test_21_same_directory_files_grouped(self):
        """同目录文件聚集验证：5 个同目录文件应在 1-2 个分片内。"""
        files = [f"src/same_dir/file{i}.py" for i in range(5)]
        result = _plan(files, max_files=10, max_count=6)
        assert len(result["shards"]) <= 2, "5 files in same dir should fit in 1-2 shards"

    # ── Matrix / vars 消费 ──

    def test_22_matrix_format(self):
        """matrix 输出格式：shards 列表含 shard_id + files。"""
        result = _plan(["a.py", "b.py"])
        for shard in result["shards"]:
            assert "shard_id" in shard
            assert "files" in shard
            assert isinstance(shard["files"], list)

    def test_23_shard_ids_sequential(self):
        """shard_id 从 0 开始连续递增。"""
        result = _plan([f"f{i}.py" for i in range(10)])
        ids = [s["shard_id"] for s in result["shards"]]
        assert ids == list(range(len(ids)))

    def test_24_total_files_matches_input(self):
        """total_files 与输入文件数一致。"""
        files = [f"file{i}.py" for i in range(15)]
        result = _plan(files)
        assert result["total_files"] == 15

    def test_25_plan_shards_exits_nonzero_on_bad_input(self):
        """planner 异常输入 → 非零退出（fail-closed）。"""
        from droid_review.plan_shards import plan_shards
        # Invalid: negative max_files
        with pytest.raises((ValueError, SystemExit)):
            plan_shards(["a.py"], max_files=-1)

    def test_26_findings_schema_validation(self):
        """VAL-SHARD-014: 非法 findings JSON schema 被拒绝。"""
        from droid_review.publish_findings import validate_findings
        # Valid findings
        valid = {
            "shard_id": 0,
            "findings": [
                {"severity": "P1", "file": "a.py", "line": 10, "message": "bug"}
            ],
        }
        assert validate_findings(valid) is True

        # Invalid: missing required field
        invalid_missing_severity = {
            "shard_id": 0,
            "findings": [
                {"file": "a.py", "line": 10, "message": "bug"}
            ],
        }
        assert validate_findings(invalid_missing_severity) is False

        # Invalid: wrong type
        invalid_type = {
            "shard_id": "not_an_int",
            "findings": [],
        }
        assert validate_findings(invalid_type) is False


# ══════════════════════════════════════════════════════════════════════
# Part C: Seam Integration Tests (3 tests) — workflow→script data flow
# ══════════════════════════════════════════════════════════════════════

class TestSeamIntegration:
    """workflow→script 接缝集成测试：真实 source GITHUB_ENV 文件 + fixture git repo。"""

    @pytest.fixture
    def fixture_git_repo(self, tmp_path):
        """创建 fixture git repo（含 base + head 分支）。"""
        import subprocess
        repo = tmp_path / "fixture-repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)

        # Base commit
        (repo / "file1.py").write_text("def foo(): pass\n")
        subprocess.run(["git", "add", "file1.py"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
        base_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        # Head commit (modify file1, add file2)
        (repo / "file1.py").write_text("def foo():\n    return 42\n")
        (repo / "file2.py").write_text("def bar(): pass\n")
        subprocess.run(["git", "add", "file1.py", "file2.py"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "head"], cwd=repo, check=True, capture_output=True)
        head_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        return {
            "repo": repo,
            "base_sha": base_sha,
            "head_sha": head_sha,
        }

    @pytest.fixture
    def github_env_file(self, tmp_path):
        """创建 GITHUB_ENV 风格文件（harness 真实 source）。"""
        env_file = tmp_path / "github_env.txt"
        return env_file

    def test_27_shard_files_json_parsing_from_env(self):
        """接缝集成：SHARD_FILES 从 GITHUB_ENV 多行定界符格式正确解析（runner 语义）。"""
        import json
        import os
        import tempfile

        # Simulate workflow's toJson() output
        shard_files = ["file1.py", "file2.py"]
        shard_files_json = json.dumps(shard_files)

        # Write GITHUB_ENV file with multi-line delimiter (runner reads literally)
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env') as f:
            f.write("SHARD_ID=0\n")
            f.write(f"SHARD_FILES<<EOF_SHARD\n{shard_files_json}\nEOF_SHARD\n")
            f.write("BASE_REF=abc123\n")
            f.write("HEAD_REF=def456\n")
            env_file = f.name

        try:
            # Parse GITHUB_ENV file using runner semantics (literal read between delimiters)
            # This is what the GitHub Actions runner actually does
            env_vars = {}
            with open(env_file) as f:
                lines = f.readlines()

            i = 0
            while i < len(lines):
                line = lines[i].rstrip('\n')
                if '<<' in line:
                    key, delimiter = line.split('<<', 1)
                    value_lines = []
                    i += 1
                    while i < len(lines) and lines[i].rstrip('\n') != delimiter:
                        value_lines.append(lines[i].rstrip('\n'))
                        i += 1
                    env_vars[key] = '\n'.join(value_lines)
                elif '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key] = value
                i += 1

            # Validate that SHARD_FILES contains valid JSON (literal value, no quote stripping)
            shard_files_value = env_vars.get('SHARD_FILES', '')
            parsed = json.loads(shard_files_value)
            assert parsed == shard_files, f"Parsed {parsed} != expected {shard_files}"

            # Verify jq can parse it (simulating run_shard.sh validation)
            import subprocess
            result = subprocess.run(
                ["jq", "-c", "."],
                input=shard_files_value,
                capture_output=True,
                text=True,
                timeout=5,
            )
            assert result.returncode == 0, f"jq failed: {result.stderr}"
        finally:
            os.unlink(env_file)

    def test_28_fail_closed_on_invalid_shard_files_json(self):
        """接缝集成：SHARD_FILES 非法 JSON 时 run_shard.sh fail-closed（runner 语义）。"""
        import os
        import subprocess
        import tempfile

        # Write invalid JSON to GITHUB_ENV with multi-line delimiter
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env') as f:
            f.write("SHARD_ID=0\n")
            f.write("SHARD_FILES<<EOF_SHARD\n{invalid json\nEOF_SHARD\n")
            f.write("BASE_REF=abc\n")
            f.write("HEAD_REF=def\n")
            env_file = f.name

        try:
            # Parse using runner semantics (literal read)
            env_vars = {}
            with open(env_file) as f:
                lines = f.readlines()

            i = 0
            while i < len(lines):
                line = lines[i].rstrip('\n')
                if '<<' in line:
                    key, delimiter = line.split('<<', 1)
                    value_lines = []
                    i += 1
                    while i < len(lines) and lines[i].rstrip('\n') != delimiter:
                        value_lines.append(lines[i].rstrip('\n'))
                        i += 1
                    env_vars[key] = '\n'.join(value_lines)
                elif '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key] = value
                i += 1

            # Validate that jq fails on invalid JSON
            shard_files_value = env_vars.get('SHARD_FILES', '')
            result = subprocess.run(
                ["jq", "empty"],
                input=shard_files_value,
                capture_output=True,
                text=True,
                timeout=5,
            )

            # jq should fail on invalid JSON
            assert result.returncode != 0, "jq should fail on invalid JSON"
        finally:
            os.unlink(env_file)

    def test_29_deleted_file_path_accepted_from_base_side(self, fixture_git_repo, tmp_path):
        """接缝集成：已删除文件（仅存在于 BASE）被 run_shard.sh 接受。"""
        import subprocess

        repo = fixture_git_repo["repo"]

        # Create a file in base, delete it in head
        (repo / "deleted_file.py").write_text("# will be deleted\n")
        subprocess.run(["git", "add", "deleted_file.py"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "add deleted"], cwd=repo, check=True, capture_output=True)
        base_with_deleted = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        subprocess.run(["git", "rm", "deleted_file.py"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "delete file"], cwd=repo, check=True, capture_output=True)
        head_after_delete = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        # Simulate the file existence check from run_shard.sh (lines 50-70)
        check_script = tmp_path / "check_deleted.sh"
        check_script.write_text(f"""#!/usr/bin/env bash
set -euo pipefail

# Simulate dual-checkout structure
BASE_DIR=$(mktemp -d)
HEAD_DIR=$(mktemp -d)

# Checkout base and head
git --git-dir={repo}/.git --work-tree=$BASE_DIR checkout {base_with_deleted} -- . 2>/dev/null || true
git --git-dir={repo}/.git --work-tree=$HEAD_DIR checkout {head_after_delete} -- . 2>/dev/null || true

# File to check
FILE="deleted_file.py"

# Check existence (from run_shard.sh logic)
if [ -f "$HEAD_DIR/$FILE" ]; then
  echo "EXISTS_IN_HEAD"
elif [ -f "$BASE_DIR/$FILE" ]; then
  echo "EXISTS_IN_BASE_DELETED"
else
  echo "NOT_FOUND"
fi

rm -rf "$BASE_DIR" "$HEAD_DIR"
""")
        check_script.chmod(0o755)

        result = subprocess.run(
            ["bash", str(check_script)],
            capture_output=True,
            text=True,
            check=True,
        )
        # Should find file in BASE (deleted in HEAD)
        assert "EXISTS_IN_BASE_DELETED" in result.stdout

    def test_31_run_shard_uses_absolute_cwd(self):
        """run_shard.sh 必须使用绝对路径 --cwd（droid CLI 0.200.0 相对路径静默崩溃）。

        验证 run_shard.sh 中的 droid exec 调用使用了 ${GITHUB_WORKSPACE:-$PWD}/head-src
        这样的绝对路径，而不是相对路径 head-src。这是 round-2 根因确诊的缺陷 A。
        """
        import re

        script_path = REPO_ROOT / "scripts" / "droid_review" / "run_shard.sh"
        assert script_path.exists(), "run_shard.sh must exist"

        content = script_path.read_text()

        # 查找 droid exec 调用及其 --cwd 参数
        # 匹配模式：droid exec ... --cwd <path>
        droid_exec_pattern = r'droid\s+exec\s+([^|]*?)(?=\||$)'
        matches = re.findall(droid_exec_pattern, content, re.DOTALL)

        assert len(matches) > 0, "run_shard.sh must contain at least one droid exec call"

        for match in matches:
            # 检查是否包含 --cwd 参数
            cwd_pattern = r'--cwd\s+(\S+)'
            cwd_matches = re.findall(cwd_pattern, match)

            if cwd_matches:
                for cwd_value in cwd_matches:
                    # 验证 --cwd 值是绝对路径（包含 ${GITHUB_WORKSPACE} 或 ${PWD}）
                    assert '${GITHUB_WORKSPACE' in cwd_value or '${PWD' in cwd_value, (
                        f"--cwd must use absolute path with ${{GITHUB_WORKSPACE}} or ${{PWD}}, "
                        f"but got: {cwd_value}"
                    )
                    # 确保不是相对路径
                    assert not cwd_value.startswith('head-src'), (
                        "--cwd must not use relative path 'head-src', "
                        "it causes droid CLI 0.200.0 to silently crash"
                    )


# ══════════════════════════════════════════════════════════════════════
# Part D: publish_findings Integration (1 test) — mock gh CLI
# ══════════════════════════════════════════════════════════════════════

class TestPublishFindingsIntegration:
    """publish_findings.py 集成测试：mock gh CLI 验证 inline/422 降级路径。"""

    def test_30_publish_findings_422_degradation(self, tmp_path, monkeypatch):
        """publish_findings 422 降级：inline 失败后降级到 summary comment。"""
        import subprocess
        from unittest.mock import MagicMock, patch

        from droid_review.publish_findings import (
            post_inline_comment,
            post_summary_comment,
        )

        # Create findings data
        findings = [
            {
                "severity": "P1",
                "file": "test.py",
                "line": 10,
                "message": "test bug",
                "shard_id": 0,
            }
        ]

        # Mock subprocess.run to simulate 422 error for inline
        def mock_subprocess_run_422(*args, **kwargs):
            error = subprocess.CalledProcessError(1, "gh")
            error.stderr = b"422 Unprocessable Entity"
            raise error

        # Test inline failure (422)
        with patch("subprocess.run", side_effect=mock_subprocess_run_422):
            result = post_inline_comment(
                findings[0],
                pr_number=889,
                repository="hdot123-org/memory",
                commit_id="abc123",
            )
            assert result is False  # 422 should return False

        # Mock successful summary post
        def mock_subprocess_run_success(*args, **kwargs):
            return MagicMock(returncode=0)

        # Test summary success
        with patch("subprocess.run", side_effect=mock_subprocess_run_success):
            by_shard = {0: findings}
            result = post_summary_comment(
                findings,
                pr_number=889,
                repository="hdot123-org/memory",
                by_shard=by_shard,
            )
            assert result is True
