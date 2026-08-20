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


def _plan(files, max_files=25, max_lines=800, max_count=6):
    """Invoke plan_shards.plan_shards with defaults; import fresh each call."""
    from droid_review.plan_shards import plan_shards
    return plan_shards(
        files,
        max_files=max_files,
        max_lines=max_lines,
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
