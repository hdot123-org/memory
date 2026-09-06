"""
Tests for sediment.py: 去重三态 + git 纪律 + gk-ensure + VAL-SED-002/003/004/005/006
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from memory_core.evolution.sediment import (
    _find_dedup_target,
    _generate_slug,
    _merge_source_refs,
    _ngram_overlap,
    git_commit_if_needed,
    gk_ensure,
    write_candidates,
)

# ---------------------------------------------------------------------------
# 去重三态测试（VAL-SED-002 单元级）
# ---------------------------------------------------------------------------


def test_ngram_overlap_identical():
    """相同文本重叠度应为 1.0"""
    text = "这是一段测试文本"
    assert _ngram_overlap(text, text) == 1.0


def test_ngram_overlap_completely_different():
    """完全不同文本重叠度应接近 0"""
    text_a = "部署回滚策略"
    text_b = "沟通例会只开十五分钟"
    overlap = _ngram_overlap(text_a, text_b)
    assert overlap < 0.3


def test_ngram_overlap_high_similarity():
    """高相似文本重叠度应 > 0.6"""
    text_a = "部署回滚策略回滚前先 restic dry-run 校验备份可用"
    text_b = "部署回滚策略回滚前先 restic dry-run 校验备份可用补充 tag 命名带日期后缀"
    overlap = _ngram_overlap(text_a, text_b)
    assert overlap > 0.6


def test_generate_slug_chinese():
    """中文标题应保留中文字符"""
    slug = _generate_slug("部署回滚策略")
    assert "部署" in slug or "回滚" in slug


def test_generate_slug_english():
    """英文标题应小写连字符"""
    slug = _generate_slug("Deployment Rollback Strategy")
    assert slug == "deployment-rollback-strategy"


def test_find_dedup_target_skip():
    """精确指纹匹配应返回 skip"""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir)
        existing = target_dir / "test.md"
        # 使用相同的内容（无 frontmatter）
        content = "内容完全相同"
        existing.write_text(content, encoding="utf-8")

        action, info = _find_dedup_target(content, target_dir, "test")
        assert action == "skip"
        assert info is not None


def test_find_dedup_target_merge():
    """高相似文本应返回 merge"""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir)
        existing = target_dir / "test.md"
        content = "# 部署回滚策略\n回滚前先 restic dry-run 校验备份可用"
        existing.write_text(content, encoding="utf-8")

        new_body = "部署回滚策略回滚前先 restic dry-run 校验备份可用补充 tag 命名带日期后缀"
        action, info = _find_dedup_target(new_body, target_dir, "test")
        assert action == "merge"
        assert info is not None


def test_find_dedup_target_suffix_new():
    """slug 相同但内容不同应返回 suffix_new"""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir)
        existing = target_dir / "test.md"
        existing.write_text("# 部署回滚策略\n内容 A", encoding="utf-8")

        new_body = "# 部署回滚策略\n完全不同的内容 B"
        action, info = _find_dedup_target(new_body, target_dir, "test")
        assert action == "suffix_new"


def test_find_dedup_target_new():
    """全新内容应返回 new"""
    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir)
        action, info = _find_dedup_target("全新内容", target_dir, "new-slug")
        assert action == "new"
        assert info is None


def test_merge_source_refs():
    """合并应追加 source_refs 且保留原文"""
    with tempfile.TemporaryDirectory() as tmpdir:
        existing = Path(tmpdir) / "test.md"
        existing.write_text("# 测试\n内容\n", encoding="utf-8")

        new_refs = [{"project": "proj-a", "path": "memory/kb/lessons/a.md"}]
        _merge_source_refs(existing, new_refs)

        content = existing.read_text(encoding="utf-8")
        assert "proj-a" in content
        assert "内容" in content  # 原文保留


def test_write_candidates_skip():
    """精确重复应跳过"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        candidates = [
            {
                "title": "测试",
                "domain": "engineering",
                "content": "测试内容",
                "confidence": 0.5,
                "source_refs": [{"project": "p1", "path": "a.md"}],
                "unrefined": True,
            }
        ]

        stats1 = write_candidates(candidates, root)
        assert stats1["written"] == 1

        stats2 = write_candidates(candidates, root)
        assert stats2["skipped_duplicate"] == 1
        assert stats2["written"] == 0


# ---------------------------------------------------------------------------
# gk-ensure 测试（VAL-SED-004）
# ---------------------------------------------------------------------------


def test_gk_ensure_no_branch():
    """无 fix/audit-round2 分支应 no-op exit 0（D8）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True)

        (root / "a.md").write_text("A", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        exit_code, message = gk_ensure(root)
        assert exit_code == 0
        assert "no-op" in message.lower() or "no fix/audit-round2" in message.lower()


def test_gk_ensure_merge_branch():
    """有 fix/audit-round2 应合并到 main"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True)

        # main: init A
        (root / "a.md").write_text("A", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init A"], cwd=root, check=True, capture_output=True)

        # 创建 fix/audit-round2 并添加 B
        subprocess.run(["git", "checkout", "-b", "fix/audit-round2"], cwd=root, check=True, capture_output=True)
        (root / "b.md").write_text("B", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "feature B"], cwd=root, check=True, capture_output=True)

        # 归位
        exit_code, message = gk_ensure(root)
        assert exit_code == 0

        # 验证 b.md 在 main 中
        result = subprocess.run(
            ["git", "branch", "--show-current"], cwd=root, check=True, capture_output=True, text=True
        )
        assert result.stdout.strip() == "main"

        result = subprocess.run(["git", "cat-file", "-e", "main:b.md"], cwd=root, check=True, capture_output=True)
        assert result.returncode == 0  # b.md 存在于 main


def test_gk_ensure_dirty_abort():
    """脏工作区应 exit 1 且不动现场"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True)

        (root / "a.md").write_text("A", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        # 创建 fix/audit-round2
        subprocess.run(["git", "checkout", "-b", "fix/audit-round2"], cwd=root, check=True, capture_output=True)
        (root / "b.md").write_text("B", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "feature B"], cwd=root, check=True, capture_output=True)

        # 切回 main 并制造脏状态
        subprocess.run(["git", "checkout", "main"], cwd=root, check=True, capture_output=True)
        (root / "a.md").write_text("dirty", encoding="utf-8")

        # 归位应失败
        exit_code, message = gk_ensure(root)
        assert exit_code == 1
        assert "dirty" in message.lower()

        # 验证 dirty 行仍在
        content = (root / "a.md").read_text(encoding="utf-8")
        assert "dirty" in content

        # 验证无 stash
        result = subprocess.run(["git", "stash", "list"], cwd=root, check=True, capture_output=True, text=True)
        assert not result.stdout.strip()


def test_gk_ensure_idempotent():
    """重复执行应幂等"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True)

        (root / "a.md").write_text("A", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        # 第一次归位
        exit_code1, _ = gk_ensure(root)
        assert exit_code1 == 0

        # 第二次归位（应 no-op）
        exit_code2, _ = gk_ensure(root)
        assert exit_code2 == 0


# ---------------------------------------------------------------------------
# git 纪律测试（VAL-SED-003）
# ---------------------------------------------------------------------------


def test_git_commit_if_needed_no_changes():
    """无变更应不提交"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True)

        (root / "a.md").write_text("A", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        )
        count_before = int(result.stdout.strip())

        committed = git_commit_if_needed(root)
        assert not committed

        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        )
        count_after = int(result.stdout.strip())
        assert count_after == count_before


def test_git_commit_if_needed_with_changes():
    """有变更应提交"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True)

        (root / "a.md").write_text("A", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        # 添加新文件
        (root / "b.md").write_text("B", encoding="utf-8")

        committed = git_commit_if_needed(root)
        assert committed

        # 验证提交
        result = subprocess.run(["git", "log", "--oneline", "-1"], cwd=root, check=True, capture_output=True, text=True)
        assert "feat(evolve)" in result.stdout or "feat" in result.stdout

        # 验证工作区干净
        result = subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True)
        assert not result.stdout.strip()


def test_git_commit_auto_commit_false():
    """auto_commit=false 应只写不提交"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True)

        (root / "a.md").write_text("A", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        # 添加新文件
        (root / "b.md").write_text("B", encoding="utf-8")

        config = {"git": {"auto_commit": False}}
        committed = git_commit_if_needed(root, config)
        assert not committed

        # 验证新文件未提交
        result = subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True)
        assert "b.md" in result.stdout


def test_git_commit_push_false():
    """push=false 应提交但不推送"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True)

        (root / "a.md").write_text("A", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        # 添加新文件
        (root / "b.md").write_text("B", encoding="utf-8")

        config = {"git": {"auto_commit": True, "push": False}}
        committed = git_commit_if_needed(root, config)
        assert committed

        # 验证已提交
        result = subprocess.run(["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True)
        assert not result.stdout.strip()


# ---------------------------------------------------------------------------
# CLI 集成测试（VAL-SED-005）
# ---------------------------------------------------------------------------


def test_cli_gk_ensure_command():
    """CLI gk-ensure 子命令应存在"""
    result = subprocess.run(
        [sys.executable, "-m", "memory_core.tools.evolve_cli", "gk-ensure", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "gk-ensure" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_cli_run_auto_gk_ensure_dirty_abort():
    """run 自动前置 gk-ensure：脏工作区应 exit 1"""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True)

        (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        # 创建 fix/audit-round2
        subprocess.run(["git", "checkout", "-b", "fix/audit-round2"], cwd=root, check=True, capture_output=True)
        (root / "b.md").write_text("B", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "feature B"], cwd=root, check=True, capture_output=True)

        # 切回 main 并制造脏状态
        subprocess.run(["git", "checkout", "main"], cwd=root, check=True, capture_output=True)
        (root / "INDEX.md").write_text("dirty\n", encoding="utf-8")

        # 创建项目夹具
        proj = Path(tmpdir) / "proj"
        proj.mkdir()
        (proj / "memory" / "kb" / "lessons").mkdir(parents=True)
        (proj / "memory" / "kb" / "lessons" / "a.md").write_text("# 教训\n内容\n", encoding="utf-8")

        with tempfile.TemporaryDirectory() as evo_root:
            env = {
                "MEMORY_CORE_GLOBAL_KB_ROOT": str(root),
                "MEMORY_CORE_EVOLUTION_ROOT": evo_root,
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            }

            result = subprocess.run(
                [sys.executable, "-m", "memory_core.tools.evolve_cli", "run", "--project", str(proj), "--no-llm"],
                capture_output=True,
                text=True,
                env=env,
            )

            assert result.returncode == 1  # D4: 脏工作区中止

            # 验证 dirty 行仍在
            content = (root / "INDEX.md").read_text(encoding="utf-8")
            assert "dirty" in content


def test_cursor_not_advanced_when_no_candidates():
    """游标在沉淀成功后才推进：当无候选时游标不推进（沉淀失败文件下轮重析）"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 创建项目夹具
        proj = tmpdir / "proj"
        lessons_dir = proj / "memory" / "kb" / "lessons"
        lessons_dir.mkdir(parents=True)

        test_file = lessons_dir / "lesson.md"
        test_file.write_text("# Test Lesson\n\nThis is test content.")

        # 创建 evolution 根和 global-kb 根
        evo_root = tmpdir / "evolution"
        evo_root.mkdir()
        gk_root = tmpdir / "global_kb"
        gk_root.mkdir()

        from memory_core.evolution.analyzer import IncrementalAnalyzer
        from memory_core.evolution.config import load_or_create_config

        config = load_or_create_config(evo_root)
        state_file = evo_root / "state.json"
        analyzer = IncrementalAnalyzer(state_file, config)

        # 第一次分析：文件应该有变更
        result1 = analyzer.analyze_project(proj)
        assert len(result1.changed_files) == 1

        # 不推进游标（模拟沉淀失败场景）
        # analyzer.update_cursors(proj, result1.changed_files)  # 故意不调用

        # 第二次分析：文件应该仍然有变更（因为游标未推进）
        result2 = analyzer.analyze_project(proj)
        assert len(result2.changed_files) == 1, "游标未推进时，文件应仍被视为变更"

        # 现在推进游标（模拟沉淀成功场景）
        analyzer.update_cursors(proj, result2.changed_files)

        # 第三次分析：文件不应再有变更
        result3 = analyzer.analyze_project(proj)
        assert len(result3.changed_files) == 0, "游标推进后，文件不应再被视为变更"


# ---------------------------------------------------------------------------
# fix-sediment-report-dryrun 四项修复测试
# ---------------------------------------------------------------------------


def test_dry_run_no_gk_ensure():
    """
    D3: dry-run 在未合并分支 root 上零变更零提交零 checkout（dry-run 在 gk-ensure 之前早退）

    构造 fix/audit-round2 分支（未合并到 main），执行 --dry-run 后：
    - 当前分支仍为 fix/audit-round2（零 checkout）
    - 提交计数不变（零提交）
    - 工作区无新增文件（零写入）
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "global_kb"
        root.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=root, check=True)

        # main 初始提交
        (root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)

        # 创建 fix/audit-round2 分支
        subprocess.run(["git", "checkout", "-b", "fix/audit-round2"], cwd=root, check=True, capture_output=True)
        (root / "fix-file.md").write_text("fix content", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        subprocess.run(["git", "commit", "-m", "fix"], cwd=root, check=True, capture_output=True)

        # 记录当前状态
        result_branch_before = subprocess.run(
            ["git", "branch", "--show-current"], cwd=root, check=True, capture_output=True, text=True
        )
        branch_before = result_branch_before.stdout.strip()
        assert branch_before == "fix/audit-round2"

        result_rev_before = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        )
        rev_count_before = int(result_rev_before.stdout.strip())

        # 创建项目夹具
        proj = Path(tmpdir) / "proj"
        proj.mkdir()
        (proj / "memory" / "kb" / "lessons").mkdir(parents=True)
        (proj / "memory" / "kb" / "lessons" / "a.md").write_text("# 教训\n内容\n", encoding="utf-8")

        with tempfile.TemporaryDirectory() as evo_root:
            env = {
                "MEMORY_CORE_GLOBAL_KB_ROOT": str(root),
                "MEMORY_CORE_EVOLUTION_ROOT": evo_root,
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
            }

            result = subprocess.run(
                [sys.executable, "-m", "memory_core.tools.evolve_cli", "run", "--project", str(proj), "--dry-run"],
                capture_output=True,
                text=True,
                env=env,
            )

            assert result.returncode == 0, f"dry-run should succeed: {result.stderr}"

        # 验证 1: 分支未变（零 checkout）
        result_branch_after = subprocess.run(
            ["git", "branch", "--show-current"], cwd=root, check=True, capture_output=True, text=True
        )
        assert result_branch_after.stdout.strip() == "fix/audit-round2", (
            f"dry-run 不应改变分支，期望 fix/audit-round2，实际 {result_branch_after.stdout.strip()}"
        )

        # 验证 2: 提交计数不变（零提交）
        result_rev_after = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        )
        rev_count_after = int(result_rev_after.stdout.strip())
        assert rev_count_after == rev_count_before, (
            f"dry-run 不应产生新提交，期望 {rev_count_before}，实际 {rev_count_after}"
        )

        # 验证 3: 工作区干净（零写入）
        result_status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True
        )
        assert not result_status.stdout.strip(), f"dry-run 不应产生文件变更，实际: {result_status.stdout}"


def test_run_report_total_merged_unrefined():
    """
    VAL-SED-002 场景 C: --no-llm 合并轮报告 total_merged >= 1

    两次运行同一项目（相同内容），第二次应触发 merge 路径，
    报告 total_merged 应 >= 1
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 创建 global_kb 根（git 仓库）
        gk_root = tmpdir / "global_kb"
        gk_root.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=gk_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=gk_root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=gk_root, check=True)
        (gk_root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=gk_root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=gk_root, check=True, capture_output=True)

        # 创建项目夹具
        proj = tmpdir / "proj"
        lessons_dir = proj / "memory" / "kb" / "lessons"
        lessons_dir.mkdir(parents=True)
        (lessons_dir / "a.md").write_text(
            "# 部署回滚策略\n回滚前先 restic dry-run 校验备份可用\n",
            encoding="utf-8",
        )

        evo_root = tmpdir / "evolution"
        evo_root.mkdir()

        env = {
            "MEMORY_CORE_GLOBAL_KB_ROOT": str(gk_root),
            "MEMORY_CORE_EVOLUTION_ROOT": str(evo_root),
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        }

        # 第一次运行：写入 pending
        result1 = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.evolve_cli", "run", "--project", str(proj), "--no-llm"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result1.returncode == 0, f"first run failed: {result1.stderr}"

        # 修改文件以触发第二次分析（游标已推进，需新内容）
        (lessons_dir / "a.md").write_text(
            "# 部署回滚策略\n回滚前先 restic dry-run 校验备份可用补充 tag 命名带日期后缀\n",
            encoding="utf-8",
        )

        # 第二次运行：应触发 merge 路径（高 n-gram 重叠）
        result2 = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.evolve_cli", "run", "--project", str(proj), "--no-llm"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result2.returncode == 0, f"second run failed: {result2.stderr}"

        # 查找报告文件并检查 total_merged
        # 注意：两次运行可能发生在同一秒内，报告文件名基于秒级时间戳，
        # 第二次会覆盖第一次。所以我们读取最后一个（最新的）报告。
        reports_dir = evo_root / "reports"
        report_files = sorted(reports_dir.glob("*.json"))
        assert len(report_files) >= 1, f"期望至少 1 个报告，实际 {len(report_files)}"

        # 读取最后一个报告（第二次运行的结果）
        import json

        with report_files[-1].open(encoding="utf-8") as f:
            report = json.load(f)

        # total_merged 应 >= 1（合并路径触发）
        assert report.get("total_merged", 0) >= 1, (
            f"期望 total_merged >= 1（merge 路径触发），实际: {report.get('total_merged', 0)}"
        )


def test_merge_source_refs_dedup():
    """
    重复合并 source_refs 时不应产生重复行/重复区段

    对同一文件多次调用 _merge_source_refs（相同引用），
    文件中每个引用只出现一次，且只有一个 ## Sources 区
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        existing = Path(tmpdir) / "test.md"
        existing.write_text("# 测试\n内容\n", encoding="utf-8")

        refs = [{"project": "proj-a", "path": "memory/kb/lessons/a.md"}]

        # 第一次合并
        _merge_source_refs(existing, refs)
        content1 = existing.read_text(encoding="utf-8")

        # 第二次合并（相同引用）
        _merge_source_refs(existing, refs)
        content2 = existing.read_text(encoding="utf-8")

        # 第三次合并（相同引用）
        _merge_source_refs(existing, refs)
        content3 = existing.read_text(encoding="utf-8")

        # 验证 1: 内容在第二次和第三次合并后不应变化（无新引用可加）
        assert content1 == content2 == content3, "重复合并已存在的引用不应改变文件内容"

        # 验证 2: ## Sources 区只出现一次
        sources_count = content3.count("## Sources")
        assert sources_count == 1, f"期望 1 个 ## Sources 区，实际 {sources_count} 个"

        # 验证 3: proj-a 只出现一次
        proj_a_count = content3.count("proj-a")
        assert proj_a_count == 1, f"期望 proj-a 出现 1 次，实际 {proj_a_count} 次"

        # 验证 4: 原文保留
        assert "内容" in content3, "原文应保留"


def test_run_report_no_dead_fields():
    """
    报告不应包含恒为 0 的死字段（per-project written/skipped_duplicate）

    运行一次后读取报告，验证项目级报告不包含 written/skipped_duplicate 字段
    （这些字段已删除，只保留全局汇总 total_written/total_skipped_duplicate）
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # 创建 global_kb 根
        gk_root = tmpdir / "global_kb"
        gk_root.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=gk_root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=gk_root, check=True)
        subprocess.run(["git", "config", "user.email", "test@test"], cwd=gk_root, check=True)
        (gk_root / "INDEX.md").write_text("# INDEX\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=gk_root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=gk_root, check=True, capture_output=True)

        # 创建项目夹具
        proj = tmpdir / "proj"
        lessons_dir = proj / "memory" / "kb" / "lessons"
        lessons_dir.mkdir(parents=True)
        (lessons_dir / "a.md").write_text("# 教训\n内容\n", encoding="utf-8")

        evo_root = tmpdir / "evolution"
        evo_root.mkdir()

        env = {
            "MEMORY_CORE_GLOBAL_KB_ROOT": str(gk_root),
            "MEMORY_CORE_EVOLUTION_ROOT": str(evo_root),
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        }

        result = subprocess.run(
            [sys.executable, "-m", "memory_core.tools.evolve_cli", "run", "--project", str(proj), "--no-llm"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"run failed: {result.stderr}"

        # 读取报告
        import json

        reports_dir = evo_root / "reports"
        report_files = sorted(reports_dir.glob("*.json"))
        assert report_files, "应至少有一个报告"

        with report_files[-1].open(encoding="utf-8") as f:
            report = json.load(f)

        # 验证项目级报告不含死字段 written/skipped_duplicate
        for proj_report in report.get("projects", []):
            assert "written" not in proj_report, f"项目级报告不应包含死字段 'written': {proj_report}"
            assert "skipped_duplicate" not in proj_report, (
                f"项目级报告不应包含死字段 'skipped_duplicate': {proj_report}"
            )

        # 验证全局汇总字段存在
        assert "total_written" in report, "报告应包含全局汇总字段 total_written"
        assert "total_skipped_duplicate" in report, "报告应包含全局汇总字段 total_skipped_duplicate"
