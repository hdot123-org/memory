"""
E2E 验证测试：VAL-CROSS-001 ~ VAL-CROSS-005, VAL-CMP-002, VAL-CMP-003

验证完整管道在真实项目上的端到端行为：
- VAL-CROSS-001: 全管道运行 + 真实 LLM（llm_e2e marker，默认跳过）
- VAL-CROSS-002: 中文 git 提交 + 报告 + 游标
- VAL-CROSS-003: 消费项目只读
- VAL-CROSS-004: 幂等重跑（计入 D15 cap 接续轮次语义）
- VAL-CROSS-005: 新项目接入（手工注入注册后验证 status + run）
- VAL-CMP-002: .evolution/config.yml 未修改
- VAL-CMP-003: 蒸馏非复制
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# 仓库根目录：通过 __file__ 推导，不硬编码绝对路径
REPO_ROOT = Path(__file__).resolve().parent.parent


# E2E subprocess PYTHONPATH 钉位（与 test_val_defuse.py 目标一致，但实现必须调用时快照）
# 确保 subprocess 加载当前源码树而非已安装的旧版本，防止 predicate 回归被掩盖。
# 注意：本文件的 e2e_env fixture 通过 os.environ 注入 MEMORY_CORE_GLOBAL_KB_ROOT /
# MEMORY_CORE_EVOLUTION_ROOT 指向每测试的临时目录，因此必须在调用时拷贝 os.environ，
# 不能用模块导入时快照（会丢失 fixture 设置的变量，导致候选写入默认全局库路径）。
def _e2e_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


# 判断当前环境是否具备真实项目条件（本地开发机）
_HAS_REAL_PROJECT = (REPO_ROOT / ".evolution").exists() or (REPO_ROOT / "memory").exists()


@pytest.fixture(autouse=True)
def _skip_llm_e2e_by_default(request):
    """Skip tests marked with llm_e2e unless --run-llm-e2e is explicitly passed.

    These tests make real LLM API calls (AXONHUB glm-5.3), consuming tokens
    and taking 5+ minutes. They must be explicitly opted into via CLI flag.
    """
    if "llm_e2e" in request.keywords and not request.config.getoption("--run-llm-e2e", default=False):
        pytest.skip("llm_e2e test requires --run-llm-e2e flag (real LLM API calls)")


@pytest.mark.skipif(not shutil.which("git"), reason="git not available")
class TestEvolutionE2E:
    """E2E 验证测试类"""

    @pytest.fixture
    def e2e_env(self):
        """E2E 测试环境：临时全局库 + 临时演进状态"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # 创建临时全局库
            gk_root = tmpdir / "global-kb"
            gk_root.mkdir()
            subprocess.run(["git", "init", "-q", "-b", "main"], cwd=gk_root, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=gk_root, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=gk_root, check=True)

            # 创建演进状态目录
            evo_root = tmpdir / "evolution"
            evo_root.mkdir()

            # 设置环境变量
            old_gk = os.environ.get("MEMORY_CORE_GLOBAL_KB_ROOT")
            old_evo = os.environ.get("MEMORY_CORE_EVOLUTION_ROOT")
            os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = str(gk_root)
            os.environ["MEMORY_CORE_EVOLUTION_ROOT"] = str(evo_root)

            try:
                yield {
                    "tmpdir": tmpdir,
                    "gk_root": gk_root,
                    "evo_root": evo_root,
                }
            finally:
                # 恢复环境变量
                if old_gk is None:
                    os.environ.pop("MEMORY_CORE_GLOBAL_KB_ROOT", None)
                else:
                    os.environ["MEMORY_CORE_GLOBAL_KB_ROOT"] = old_gk
                if old_evo is None:
                    os.environ.pop("MEMORY_CORE_EVOLUTION_ROOT", None)
                else:
                    os.environ["MEMORY_CORE_EVOLUTION_ROOT"] = old_evo

    @pytest.mark.llm_e2e
    @pytest.mark.timeout(600)
    def test_val_cross_001_full_pipeline_with_llm(self, e2e_env):
        """VAL-CROSS-001: 全管道运行 + 真实 LLM

        需要真实 LLM API 密钥（AXONHUB_API_KEY）。
        默认跳过；本地手动执行：pytest -m llm_e2e --run-llm-e2e
        超时 600s（10 分钟），因为真实 LLM 调用较慢。
        """
        gk_root = e2e_env["gk_root"]

        # 使用仓库自身作为测试项目（保证存在）
        test_projects = [str(REPO_ROOT)]

        # 尝试添加更多真实项目（如果存在）
        for candidate_name in ["infra-core", "workbot"]:
            candidate = REPO_ROOT.parent / candidate_name
            if candidate.exists() and (candidate / ".git").exists():
                test_projects.append(str(candidate))

        # 记录运行前的文件状态
        before_files = set()
        for p in gk_root.rglob("*.md"):
            if ".git" not in p.parts:
                before_files.add(p)

        # 运行管道（每个项目单独运行，避免超时）
        for project in test_projects:
            if not Path(project).exists():
                continue

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "memory_core.tools.evolve_cli",
                    "run",
                    "--project",
                    project,
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=540,  # 9 分钟超时（留余量给 600s pytest timeout）
                env=_e2e_env(),
            )

            # 应该成功退出
            assert result.returncode == 0, f"Pipeline failed for {project}: {result.stderr}"

        # 验证：产生了候选文件
        after_files = set()
        for p in gk_root.rglob("*.md"):
            if ".git" not in p.parts:
                after_files.add(p)

        new_files = after_files - before_files
        assert len(new_files) > 0, "No candidates generated"

        # 验证：pending 或 formal domain 中有新文件
        pending_dir = gk_root / "pending"
        formal_dirs = [
            gk_root / d for d in ["operations", "engineering", "collaboration", "governance", "infra", "audit"]
        ]

        has_candidates = False
        if pending_dir.exists() and any(pending_dir.glob("*.md")):
            has_candidates = True
        for d in formal_dirs:
            if d.exists() and any(d.glob("*.md")):
                has_candidates = True
                break

        assert has_candidates, "No candidates in pending or formal domains"

    def test_val_cross_002_git_commit_report_cursor(self, e2e_env):
        """VAL-CROSS-002: 中文 git 提交 + 报告 + 游标"""
        gk_root = e2e_env["gk_root"]
        evo_root = e2e_env["evo_root"]

        # 使用仓库自身作为测试项目
        project = str(REPO_ROOT)
        if not Path(project).exists():
            pytest.skip(f"Project {project} not available")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.evolve_cli",
                "run",
                "--project",
                project,
                "--no-llm",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            env=_e2e_env(),
        )
        assert result.returncode == 0, f"Pipeline failed: {result.stderr}"

        # 验证 1: 中文 git 提交
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=gk_root,
            capture_output=True,
            text=True,
        )
        assert log_result.returncode == 0
        commit_msg = log_result.stdout.strip()
        assert commit_msg, "No commits found"
        # 验证提交信息包含中文字符
        has_chinese = any("\u4e00" <= c <= "\u9fff" for c in commit_msg)
        assert has_chinese, f"Commit message not in Chinese: {commit_msg}"

        # 验证 2: 报告生成
        reports_dir = evo_root / "reports"
        assert reports_dir.exists(), "Reports directory not created"
        reports = list(reports_dir.glob("*.json"))
        assert len(reports) > 0, "No report files generated"

        # 验证报告内容
        latest_report = reports[-1]
        with latest_report.open() as f:
            report_data = json.load(f)
        assert "run_at" in report_data
        assert "projects" in report_data
        assert "total_candidates" in report_data

        # 验证 3: 游标更新
        state_file = evo_root / "state.json"
        assert state_file.exists(), "state.json not created"
        with state_file.open() as f:
            state_data = json.load(f)
        assert "projects" in state_data
        assert project in state_data["projects"]
        assert "file_cursors" in state_data["projects"][project]

    def test_val_cross_003_consumer_readonly(self, e2e_env):
        """VAL-CROSS-003: 消费项目只读验证"""

        # 使用仓库自身作为测试项目
        test_project = str(REPO_ROOT)
        if not Path(test_project).exists():
            pytest.skip(f"Project {test_project} not available")

        # 记录运行前的 git 状态
        status_before = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_project,
            capture_output=True,
            text=True,
        )
        before_changes = (
            set(line for line in status_before.stdout.strip().split("\n") if line.strip())
            if status_before.stdout.strip()
            else set()
        )

        # 记录 config.yml 的哈希
        config_file = Path(test_project) / ".evolution" / "config.yml"
        config_hash_before = None
        if config_file.exists():
            import hashlib

            config_hash_before = hashlib.sha256(config_file.read_bytes()).hexdigest()

        # 记录 memory 目录的文件列表
        memory_dir = Path(test_project) / "memory"
        memory_files_before = set()
        if memory_dir.exists():
            for f in memory_dir.rglob("*"):
                if f.is_file():
                    memory_files_before.add(f.relative_to(test_project))

        # 运行管道
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.evolve_cli",
                "run",
                "--project",
                test_project,
                "--no-llm",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            env=_e2e_env(),
        )
        assert result.returncode == 0, f"Pipeline failed: {result.stderr}"

        # 验证 1: git 状态未改变
        status_after = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_project,
            capture_output=True,
            text=True,
        )
        after_changes = (
            set(line for line in status_after.stdout.strip().split("\n") if line.strip())
            if status_after.stdout.strip()
            else set()
        )
        assert before_changes == after_changes, f"Git status changed: before={before_changes}, after={after_changes}"

        # 验证 2: config.yml 哈希未改变
        if config_hash_before is not None:
            import hashlib

            config_hash_after = hashlib.sha256(config_file.read_bytes()).hexdigest()
            assert config_hash_before == config_hash_after, "config.yml was modified"

        # 验证 3: memory 目录无新文件
        memory_files_after = set()
        if memory_dir.exists():
            for f in memory_dir.rglob("*"):
                if f.is_file():
                    memory_files_after.add(f.relative_to(test_project))

        new_memory_files = memory_files_after - memory_files_before
        assert len(new_memory_files) == 0, f"New files in memory/: {new_memory_files}"

    def test_val_cross_004_idempotent_rerun(self, e2e_env):
        """VAL-CROSS-004: 幂等重跑验证

        D15 max_files_per_project 超限场景：被 cap 跳过的文件游标不推进，
        下轮（无新输入）自动接续分析。因此需要运行 N 次直到稳定：
        - Run K: 处理一批文件，可能受 cap 限制
        - Run K+1: 接续处理被跳过的文件
        - ... 直到所有文件游标已推进
        - Run N: 真正幂等，零新增文件
        验证最后两次运行之间零新增。
        """
        gk_root = e2e_env["gk_root"]
        evo_root = e2e_env["evo_root"]

        # 使用仓库自身作为测试项目
        test_project = str(REPO_ROOT)
        if not Path(test_project).exists():
            pytest.skip(f"Project {test_project} not available")

        def run_evolve():
            """Helper to run evolve CLI"""
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "memory_core.tools.evolve_cli",
                    "run",
                    "--project",
                    test_project,
                    "--no-llm",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=180,
                env=_e2e_env(),
            )

        def count_files():
            return set(p for p in gk_root.rglob("*.md") if ".git" not in p.parts)

        # 持续运行直到稳定（零新增文件）
        prev_files = count_files()
        max_runs = 10  # 安全上限
        for run_count in range(1, max_runs + 1):
            result = run_evolve()
            assert result.returncode == 0, f"Run {run_count} failed: {result.stderr}"

            curr_files = count_files()
            new_files = curr_files - prev_files
            if len(new_files) == 0:
                break
            prev_files = curr_files

        # 记录稳定状态
        stable_files = prev_files
        commit_count_before = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=gk_root,
            capture_output=True,
            text=True,
        )
        commits_before = int(commit_count_before.stdout.strip())

        # 再运行一次，确认幂等
        result = run_evolve()
        assert result.returncode == 0

        final_files = count_files()
        new_files = final_files - stable_files
        assert len(new_files) == 0, f"New files after stable (should be idempotent): {new_files}"

        commit_count_after = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=gk_root,
            capture_output=True,
            text=True,
        )
        commits_after = int(commit_count_after.stdout.strip())
        assert commits_before == commits_after, f"New commits after stable: {commits_before} -> {commits_after}"

        # 验证报告存在（至少 2 个：最后一次稳定前 + 最后一次幂等运行）
        reports_dir = evo_root / "reports"
        reports = sorted(reports_dir.glob("*.json"))
        assert len(reports) >= 2, f"Expected at least 2 reports, got {len(reports)}"
        with reports[-1].open() as f:
            last_report = json.load(f)
        # 最后一次运行的 total_candidates 应该为 0（无变更，游标全覆盖）
        assert last_report.get("total_candidates", 0) == 0, (
            f"Final run should have 0 candidates, got {last_report.get('total_candidates', 0)}"
        )

    def test_val_cross_005_new_project_manual_inject(self, e2e_env):
        """VAL-CROSS-005: 新项目接入验证（手工注入注册方式）

        原设计断言 registry 自动发现临时项目，但 registry 只读 lifecycle
        注册表（path-index.json ∪ projects/*.json），不会自动发现未注册的
        临时目录。改为：手工向 lifecycle projects/ 注入临时项目 json，
        然后验证 status 包含该项目 + run 能处理该项目。

        收尾时清理注入的 json（不污染生产注册表）。
        """
        gk_root = e2e_env["gk_root"]
        tmpdir = e2e_env["tmpdir"]

        # 创建临时项目
        temp_project = tmpdir / "test-new-project"
        temp_project.mkdir()

        # 初始化 git
        subprocess.run(["git", "init", "-q"], cwd=temp_project, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_project, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=temp_project, check=True)

        # 创建 memory 结构
        memory_dir = temp_project / "memory"
        kb_dir = memory_dir / "kb"
        lessons_dir = kb_dir / "lessons"
        lessons_dir.mkdir(parents=True)

        # 写入测试经验
        lesson_file = lessons_dir / "test-lesson.md"
        lesson_file.write_text("""# 测试经验

这是一个测试经验，用于验证新项目接入。

## 关键点

- 关键点 1
- 关键点 2
""")

        # 提交
        subprocess.run(["git", "add", "."], cwd=temp_project, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "Initial commit"], cwd=temp_project, check=True)

        # 手工注入 lifecycle 注册表
        lifecycle_projects_dir = Path.home() / ".memory-core" / "project-lifecycle" / "projects"
        inject_file = lifecycle_projects_dir / "zz-val-e2e-test.json"
        lifecycle_projects_dir.mkdir(parents=True, exist_ok=True)
        inject_file.write_text(json.dumps({"git_root": str(temp_project)}))

        try:
            # 验证 1: status 能列出该项目（注入后立即可见，D12 现读）
            status_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "memory_core.tools.evolve_cli",
                    "status",
                    "--json",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                env=_e2e_env(),
            )
            assert status_result.returncode == 0
            status_data = json.loads(status_result.stdout)
            project_roots = [p["git_root"] for p in status_data["projects"]]
            assert str(temp_project) in project_roots, f"New project not in status after injection: {project_roots}"

            # 验证 2: run 能处理该项目
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "memory_core.tools.evolve_cli",
                    "run",
                    "--project",
                    str(temp_project),
                    "--no-llm",
                ],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                timeout=180,
                env=_e2e_env(),
            )
            assert result.returncode == 0, f"Pipeline failed for new project: {result.stderr}"

            # 验证 3: 产生候选
            pending_dir = gk_root / "pending"
            has_candidates = False
            if pending_dir.exists():
                pending_files = list(pending_dir.glob("*.md"))
                for f in pending_files:
                    content = f.read_text()
                    if "test-new-project" in content or "测试经验" in content:
                        has_candidates = True
                        break

            # 也可能进 formal domain
            formal_dirs = [
                gk_root / d for d in ["operations", "engineering", "collaboration", "governance", "infra", "audit"]
            ]
            for d in formal_dirs:
                if d.exists():
                    for f in d.glob("*.md"):
                        content = f.read_text()
                        if "test-new-project" in content or "测试经验" in content:
                            has_candidates = True
                            break

            assert has_candidates, "No candidates from new project"

        finally:
            # 清理：删除注入的 lifecycle json
            if inject_file.exists():
                inject_file.unlink()

    def test_val_cmp_002_config_unchanged(self, e2e_env):
        """VAL-CMP-002: .evolution/config.yml 未修改"""
        test_project = str(REPO_ROOT)
        if not Path(test_project).exists():
            pytest.skip(f"Project {test_project} not available")

        config_file = Path(test_project) / ".evolution" / "config.yml"
        if not config_file.exists():
            pytest.skip("config.yml not present")

        # 记录哈希
        import hashlib

        hash_before = hashlib.sha256(config_file.read_bytes()).hexdigest()

        # 运行管道
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.evolve_cli",
                "run",
                "--project",
                test_project,
                "--no-llm",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            env=_e2e_env(),
        )
        assert result.returncode == 0

        # 验证哈希未变
        hash_after = hashlib.sha256(config_file.read_bytes()).hexdigest()
        assert hash_before == hash_after, "config.yml was modified by pipeline"

    def test_val_cmp_003_distillation_not_copy(self, e2e_env):
        """VAL-CMP-003: 蒸馏非复制验证"""
        gk_root = e2e_env["gk_root"]

        # 使用仓库自身作为测试项目
        test_project = str(REPO_ROOT)
        if not Path(test_project).exists():
            pytest.skip(f"Project {test_project} not available")

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "memory_core.tools.evolve_cli",
                "run",
                "--project",
                test_project,
                "--no-llm",
            ],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=180,
            env=_e2e_env(),
        )
        assert result.returncode == 0

        # 检查 formal domain 中的文件
        formal_dirs = [
            gk_root / d for d in ["operations", "engineering", "collaboration", "governance", "infra", "audit"]
        ]

        for domain_dir in formal_dirs:
            if not domain_dir.exists():
                continue

            for candidate_file in domain_dir.glob("*.md"):
                content = candidate_file.read_text()

                # 读取 frontmatter
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        frontmatter = parts[1]

                        # 验证不包含 unrefined 标记
                        assert "unrefined: true" not in frontmatter, (
                            f"Formal domain file contains unrefined: {candidate_file}"
                        )

                        # 验证 source: memory-evolve
                        assert "source: memory-evolve" in frontmatter, (
                            f"Missing source: memory-evolve in {candidate_file}"
                        )
