"""
E2E 验证测试：VAL-CROSS-001 ~ VAL-CROSS-005, VAL-CMP-002, VAL-CMP-003

验证完整管道在真实项目上的端到端行为：
- VAL-CROSS-001: 全管道运行 + 真实 LLM
- VAL-CROSS-002: 中文 git 提交 + 报告 + 游标
- VAL-CROSS-003: 消费项目只读
- VAL-CROSS-004: 幂等重跑
- VAL-CROSS-005: 新项目自动接入
- VAL-CMP-002: .evolution/config.yml 未修改
- VAL-CMP-003: 蒸馏非复制
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


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
            import os

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

    def test_val_cross_001_full_pipeline_with_llm(self, e2e_env):
        """VAL-CROSS-001: 全管道运行 + 真实 LLM"""
        gk_root = e2e_env["gk_root"]

        # 选择 3 个真实项目
        test_projects = [
            "/Users/busiji/memory",
            "/Users/busiji/infra-core",
            "/Users/busiji/workbot",
        ]

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
                    "python3",
                    "-m",
                    "memory_core.tools.evolve_cli",
                    "run",
                    "--project",
                    project,
                ],
                cwd="/Users/busiji/memory",
                capture_output=True,
                text=True,
                timeout=180,  # 3 分钟超时
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

        # 运行一次管道
        project = "/Users/busiji/memory"
        if not Path(project).exists():
            pytest.skip(f"Project {project} not available")

        result = subprocess.run(
            [
                "python3",
                "-m",
                "memory_core.tools.evolve_cli",
                "run",
                "--project",
                project,
            ],
            cwd="/Users/busiji/memory",
            capture_output=True,
            text=True,
            timeout=180,
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

        # 选择测试项目
        test_project = "/Users/busiji/memory"
        if not Path(test_project).exists():
            pytest.skip(f"Project {test_project} not available")

        # 记录运行前的 git 状态
        status_before = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_project,
            capture_output=True,
            text=True,
        )
        before_changes = set(status_before.stdout.strip().split("\n")) if status_before.stdout.strip() else set()

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
                "python3",
                "-m",
                "memory_core.tools.evolve_cli",
                "run",
                "--project",
                test_project,
            ],
            cwd="/Users/busiji/memory",
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0, f"Pipeline failed: {result.stderr}"

        # 验证 1: git 状态未改变
        status_after = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=test_project,
            capture_output=True,
            text=True,
        )
        after_changes = set(status_after.stdout.strip().split("\n")) if status_after.stdout.strip() else set()
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
        """VAL-CROSS-004: 幂等重跑验证"""
        gk_root = e2e_env["gk_root"]
        evo_root = e2e_env["evo_root"]

        # 选择测试项目
        test_project = "/Users/busiji/memory"
        if not Path(test_project).exists():
            pytest.skip(f"Project {test_project} not available")

        # 第一次运行
        result1 = subprocess.run(
            [
                "python3",
                "-m",
                "memory_core.tools.evolve_cli",
                "run",
                "--project",
                test_project,
            ],
            cwd="/Users/busiji/memory",
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result1.returncode == 0

        # 记录第一次运行后的文件状态
        files_after_first = set()
        for p in gk_root.rglob("*.md"):
            if ".git" not in p.parts:
                files_after_first.add(p)

        commit_count_before = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=gk_root,
            capture_output=True,
            text=True,
        )
        commits_before = int(commit_count_before.stdout.strip())

        # 第二次运行（无新输入）
        result2 = subprocess.run(
            [
                "python3",
                "-m",
                "memory_core.tools.evolve_cli",
                "run",
                "--project",
                test_project,
            ],
            cwd="/Users/busiji/memory",
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result2.returncode == 0

        # 验证 1: 无新文件
        files_after_second = set()
        for p in gk_root.rglob("*.md"):
            if ".git" not in p.parts:
                files_after_second.add(p)

        new_files = files_after_second - files_after_first
        assert len(new_files) == 0, f"New files on second run: {new_files}"

        # 验证 2: 无新提交
        commit_count_after = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=gk_root,
            capture_output=True,
            text=True,
        )
        commits_after = int(commit_count_after.stdout.strip())
        assert commits_before == commits_after, f"New commits on second run: {commits_before} -> {commits_after}"

        # 验证 3: 报告显示 0 新分析
        reports_dir = evo_root / "reports"
        reports = sorted(reports_dir.glob("*.json"))
        assert len(reports) >= 2
        with reports[-1].open() as f:
            last_report = json.load(f)
        assert last_report["total_changed"] == 0, "Second run should find 0 changed files"

    def test_val_cross_005_new_project_auto_onboard(self, e2e_env):
        """VAL-CROSS-005: 新项目自动接入验证"""
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

这是一个测试经验，用于验证新项目自动接入。

## 关键点

- 关键点 1
- 关键点 2
""")

        # 提交
        subprocess.run(["git", "add", "."], cwd=temp_project, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "Initial commit"], cwd=temp_project, check=True)

        # 验证 1: status 能列出该项目
        status_result = subprocess.run(
            [
                "python3",
                "-m",
                "memory_core.tools.evolve_cli",
                "status",
                "--json",
            ],
            cwd="/Users/busiji/memory",
            capture_output=True,
            text=True,
        )
        assert status_result.returncode == 0
        status_data = json.loads(status_result.stdout)
        project_roots = [p["git_root"] for p in status_data["projects"]]
        assert str(temp_project) in project_roots, f"New project not in status: {project_roots}"

        # 验证 2: run 能处理该项目
        result = subprocess.run(
            [
                "python3",
                "-m",
                "memory_core.tools.evolve_cli",
                "run",
                "--project",
                str(temp_project),
            ],
            cwd="/Users/busiji/memory",
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0

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

    def test_val_cmp_002_config_unchanged(self, e2e_env):
        """VAL-CMP-002: .evolution/config.yml 未修改"""
        test_project = "/Users/busiji/memory"
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
                "python3",
                "-m",
                "memory_core.tools.evolve_cli",
                "run",
                "--project",
                test_project,
            ],
            cwd="/Users/busiji/memory",
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert result.returncode == 0

        # 验证哈希未变
        hash_after = hashlib.sha256(config_file.read_bytes()).hexdigest()
        assert hash_before == hash_after, "config.yml was modified by pipeline"

    def test_val_cmp_003_distillation_not_copy(self, e2e_env):
        """VAL-CMP-003: 蒸馏非复制验证"""
        gk_root = e2e_env["gk_root"]

        # 运行一次管道
        test_project = "/Users/busiji/memory"
        if not Path(test_project).exists():
            pytest.skip(f"Project {test_project} not available")

        result = subprocess.run(
            [
                "python3",
                "-m",
                "memory_core.tools.evolve_cli",
                "run",
                "--project",
                test_project,
            ],
            cwd="/Users/busiji/memory",
            capture_output=True,
            text=True,
            timeout=180,
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
