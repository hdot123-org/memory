"""
Tests for sediment.py: 去重三态 + git 纪律 + gk-ensure + VAL-SED-002/003/004/005/006
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from memory_core.evolution.sediment import (
    _find_dedup_target,
    _generate_slug,
    _merge_source_refs,
    _ngram_overlap,
    gk_ensure,
    git_commit_if_needed,
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
        result = subprocess.run(["git", "branch", "--show-current"], cwd=root, check=True, capture_output=True, text=True)
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

        result = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=root, check=True, capture_output=True, text=True)
        count_before = int(result.stdout.strip())

        committed = git_commit_if_needed(root)
        assert not committed

        result = subprocess.run(["git", "rev-list", "--count", "HEAD"], cwd=root, check=True, capture_output=True, text=True)
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
